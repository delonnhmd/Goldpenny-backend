"""Step 34 population pressure + local competition service.

This service composes existing simulation outputs into a bounded regional layer
that models:
  - activity density
  - opportunity upside
  - congestion / housing friction
  - local business competition

It is deterministic and state-driven. The service persists compact rolling
region state and short history rows; it does not replace the macro engine.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_housing_state import PlayerHousingState
from app.models.region_population_history import RegionPopulationHistory
from app.models.region_population_state import RegionPopulationState

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
WINDOW_DAYS = 14
TREND_LOOKBACK = 5

SUPPORTED_REGIONS: tuple[str, ...] = ("suburban", "downtown")

PRACTICAL_RESPONSES: tuple[str, ...] = (
    "Stay and absorb the current pressure while protecting recovery.",
    "Move to reduce commute burden and daily friction.",
    "Rent closer to opportunity zones and accept higher housing expense.",
)

FUTURE_LOCKED_RESPONSES: tuple[str, ...] = (
    "Transport venture path (locked)",
    "Mobility service path (locked)",
    "Vehicle/brand path (locked)",
    "Logistics optimization business path (locked)",
)

REGION_PROFILE = {
    "suburban": {
        "opportunity_bias": Decimal("-0.09"),
        "congestion_bias": Decimal("-0.14"),
        "housing_bias": Decimal("-0.16"),
        "competition_bias": Decimal("-0.10"),
        "consumer_flow_bias": Decimal("-0.06"),
        "population_bias": Decimal("-0.07"),
    },
    "downtown": {
        "opportunity_bias": Decimal("0.12"),
        "congestion_bias": Decimal("0.16"),
        "housing_bias": Decimal("0.15"),
        "competition_bias": Decimal("0.11"),
        "consumer_flow_bias": Decimal("0.08"),
        "population_bias": Decimal("0.08"),
    },
}


class PopulationPressureError(Exception):
    """Base exception for population-pressure service."""


class PopulationPressureNotFoundError(PopulationPressureError):
    """Raised when player resources cannot be resolved."""


class PopulationPressureValidationError(PopulationPressureError):
    """Raised when invalid dates/regions are supplied."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _safe_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except Exception:
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise PopulationPressureValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise PopulationPressureValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise PopulationPressureNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise PopulationPressureNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date

    latest_macro = db.query(func.max(MacroDailyState.day)).scalar()
    latest_housing = db.query(func.max(HousingDailyLog.day)).scalar()
    latest_business = db.query(func.max(BusinessDailyLog.day)).scalar()
    latest_settlement = db.query(func.max(DailySettlementLog.day_number)).scalar()
    day = max(
        int(latest_macro or 0),
        int(latest_housing or 0),
        int(latest_business or 0),
        int(latest_settlement or 0),
        1,
    )
    return day, _day_to_date(day)


def _window_start(day: int, window_days: int = WINDOW_DAYS) -> int:
    return max(1, int(day) - max(1, int(window_days)) + 1)


def _normalize_region(region_key: str | None) -> str:
    normalized = (region_key or "").strip().lower()
    if normalized not in SUPPORTED_REGIONS:
        return "suburban"
    return normalized


def _active_region_for_player(db: Session, player: Player) -> str:
    housing = (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player.id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc(), PlayerHousingState.created_at.desc())
        .first()
    )
    return _normalize_region(getattr(housing, "region", None) or player.region or "suburban")


def _latest_macro(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= int(day))
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )
    if row is not None:
        return row
    return db.query(MacroDailyState).order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc()).first()


def _recent_housing_rows(db: Session, region_key: str, day: int) -> list[HousingDailyLog]:
    return (
        db.query(HousingDailyLog)
        .filter(
            HousingDailyLog.region == region_key,
            HousingDailyLog.day >= _window_start(day),
            HousingDailyLog.day <= int(day),
        )
        .order_by(HousingDailyLog.day.asc(), HousingDailyLog.created_at.asc())
        .all()
    )


def _recent_business_rows(db: Session, region_key: str, day: int) -> list[BusinessDailyLog]:
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.region_key == region_key,
            BusinessDailyLog.day >= _window_start(day),
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.asc(), BusinessDailyLog.created_at.asc())
        .all()
    )


def _effective_region_counts(db: Session) -> dict[str, int]:
    counts = {region: 0 for region in SUPPORTED_REGIONS}
    players = db.query(Player.id, Player.region).all()
    active_housing = (
        db.query(PlayerHousingState.player_id, PlayerHousingState.region)
        .filter(PlayerHousingState.active_flag.is_(True))
        .all()
    )
    housing_map: dict[UUID, str] = {
        row.player_id: _normalize_region(row.region)
        for row in active_housing
        if row.player_id is not None
    }
    for row in players:
        region = housing_map.get(row.id, _normalize_region(row.region))
        counts[region] = counts.get(region, 0) + 1
    return counts


def _score_level(score: Decimal) -> str:
    value = _clamp(score, Decimal("0"), Decimal("100"))
    if value >= Decimal("72"):
        return "high"
    if value >= Decimal("44"):
        return "moderate"
    return "low"


def _competition_label(score: Decimal) -> str:
    value = _clamp(score, Decimal("0"), Decimal("100"))
    if value >= Decimal("72"):
        return "tight"
    if value >= Decimal("44"):
        return "active"
    return "calm"


def _heat_label(opportunity: Decimal, congestion: Decimal, housing: Decimal, competition: Decimal) -> str:
    upside = _q4((opportunity + (Decimal("0.65") * _clamp(opportunity, Decimal("0"), Decimal("100")))) / Decimal("1.65"))
    friction = _q4((congestion + housing + competition) / Decimal("3"))
    if upside >= Decimal("68") and friction >= Decimal("52"):
        return "hot"
    if upside >= Decimal("52") or friction >= Decimal("42"):
        return "warm"
    return "cool"


def _avg(values: list[Decimal], default: Decimal = Decimal("0")) -> Decimal:
    if not values:
        return default
    return _q4(sum(values, Decimal("0")) / Decimal(str(len(values))))


def _compute_region_scores(db: Session, region_key: str, day: int) -> dict:
    region = _normalize_region(region_key)
    profile = REGION_PROFILE[region]
    counts = _effective_region_counts(db)
    region_players = Decimal(str(counts.get(region, 0)))
    total_players = Decimal(str(max(1, sum(counts.values()))))
    share = _q4(region_players / total_players)

    macro = _latest_macro(db, day)
    confidence = _d(getattr(macro, "consumer_confidence", 50))
    unemployment = _d(getattr(macro, "unemployment_rate", 5.5))
    oil = _d(getattr(macro, "oil_index", 100))
    supply_stress = _d(getattr(macro, "supply_chain_stress", 0.8))

    housing_rows = _recent_housing_rows(db, region, day)
    business_rows = _recent_business_rows(db, region, day)

    avg_commute_hours = _avg([_d(getattr(row, "commute_hours", 0)) for row in housing_rows], Decimal("0.90"))
    avg_commute_pressure = _avg([_d(getattr(row, "commute_pressure", 0)) for row in housing_rows], Decimal("0.85"))
    avg_housing_cost_daily = _avg(
        [_d(getattr(row, "housing_cost_xgp", 0)) for row in housing_rows],
        Decimal("20.00") if region == "downtown" else Decimal("14.00"),
    )
    avg_region_opportunity = _avg([_d(getattr(row, "opportunity_modifier", 1.0)) for row in housing_rows], Decimal("1.00"))

    business_rows_count = Decimal(str(len(business_rows)))
    avg_units_sold = _avg([_d(getattr(row, "units_sold", 0)) for row in business_rows], Decimal("18.0"))
    avg_net_profit = _avg([_d(getattr(row, "net_profit_xgp", 0)) for row in business_rows], Decimal("0"))
    negative_profit_ratio = (
        Decimal(str(sum(1 for row in business_rows if _d(getattr(row, "net_profit_xgp", 0)) < Decimal("0"))))
        / max(Decimal("1"), business_rows_count)
    ) if business_rows else Decimal("0.30")

    active_population_score = _clamp(
        Decimal("18.0")
        + (share * Decimal("54.0"))
        + (region_players * Decimal("3.1"))
        + (profile["population_bias"] * Decimal("30.0")),
        Decimal("5.0"),
        Decimal("100.0"),
    )

    opportunity_density_score = _clamp(
        Decimal("30.0")
        + (active_population_score * Decimal("0.45"))
        + ((confidence - Decimal("50.0")) * Decimal("0.75"))
        + ((Decimal("5.8") - unemployment) * Decimal("6.2"))
        + (profile["opportunity_bias"] * Decimal("36.0"))
        + ((_clamp(avg_region_opportunity, Decimal("0.80"), Decimal("1.20")) - Decimal("1.0")) * Decimal("40.0")),
        Decimal("5.0"),
        Decimal("100.0"),
    )

    congestion_score = _clamp(
        Decimal("15.0")
        + (active_population_score * Decimal("0.52"))
        + ((_clamp(avg_commute_hours, Decimal("0.30"), Decimal("3.50")) - Decimal("0.90")) * Decimal("22.0"))
        + ((_clamp(avg_commute_pressure, Decimal("0.0"), Decimal("3.5")) - Decimal("0.85")) * Decimal("16.0"))
        + (profile["congestion_bias"] * Decimal("34.0")),
        Decimal("0.0"),
        Decimal("100.0"),
    )

    housing_pressure_score = _clamp(
        Decimal("12.0")
        + (opportunity_density_score * Decimal("0.37"))
        + (congestion_score * Decimal("0.31"))
        + ((_clamp(avg_housing_cost_daily, Decimal("8.0"), Decimal("48.0")) - Decimal("16.0")) * Decimal("1.45"))
        + (profile["housing_bias"] * Decimal("40.0")),
        Decimal("0.0"),
        Decimal("100.0"),
    )

    business_competition_score = _clamp(
        Decimal("10.0")
        + (active_population_score * Decimal("0.32"))
        + (opportunity_density_score * Decimal("0.28"))
        + (_clamp(business_rows_count, Decimal("0"), Decimal("120")) * Decimal("0.35"))
        + (negative_profit_ratio * Decimal("18.0"))
        + (profile["competition_bias"] * Decimal("34.0")),
        Decimal("0.0"),
        Decimal("100.0"),
    )

    consumer_flow_score = _clamp(
        Decimal("20.0")
        + (opportunity_density_score * Decimal("0.44"))
        + ((confidence - Decimal("50.0")) * Decimal("0.60"))
        + ((avg_units_sold - Decimal("18.0")) * Decimal("0.75"))
        - (business_competition_score * Decimal("0.16"))
        - ((oil - Decimal("100.0")) * Decimal("0.09"))
        - ((supply_stress - Decimal("0.80")) * Decimal("8.5"))
        + (profile["consumer_flow_bias"] * Decimal("36.0")),
        Decimal("0.0"),
        Decimal("100.0"),
    )

    return {
        "region_key": region,
        "active_population_score": _q4(active_population_score),
        "opportunity_density_score": _q4(opportunity_density_score),
        "congestion_score": _q4(congestion_score),
        "housing_pressure_score": _q4(housing_pressure_score),
        "business_competition_score": _q4(business_competition_score),
        "consumer_flow_score": _q4(consumer_flow_score),
        "population_count": int(region_players),
        "total_population_count": int(total_players),
        "share_of_population": float(_q4(share)),
        "avg_commute_hours": float(_q4(avg_commute_hours)),
        "avg_commute_pressure": float(_q4(avg_commute_pressure)),
        "avg_housing_cost_daily_xgp": float(_q4(avg_housing_cost_daily)),
        "avg_units_sold": float(_q4(avg_units_sold)),
        "avg_business_net_xgp": float(_q4(avg_net_profit)),
        "negative_profit_ratio": float(_q4(_clamp(negative_profit_ratio, Decimal("0"), Decimal("1")))),
        "macro_context": {
            "consumer_confidence": float(_q4(confidence)),
            "unemployment_rate": float(_q4(unemployment)),
            "oil_index": float(_q4(oil)),
            "supply_chain_stress": float(_q4(supply_stress)),
        },
    }


def _growth_direction_for_region(db: Session, region_key: str, as_of_day: int, current_population_score: Decimal) -> str:
    rows = (
        db.query(RegionPopulationHistory)
        .filter(
            RegionPopulationHistory.region_key == region_key,
            RegionPopulationHistory.as_of_day < int(as_of_day),
        )
        .order_by(RegionPopulationHistory.as_of_day.desc(), RegionPopulationHistory.updated_at.desc())
        .limit(TREND_LOOKBACK)
        .all()
    )
    if not rows:
        return "stable"
    prev = _avg([_d(row.active_population_score) for row in rows], _d(rows[0].active_population_score))
    delta = _q4(current_population_score - prev)
    if delta >= Decimal("2.00"):
        return "rising"
    if delta <= Decimal("-2.00"):
        return "falling"
    return "stable"


def _upsert_region_rows(
    db: Session,
    *,
    region_scores: dict,
    day: int,
    as_of_date: date,
) -> tuple[RegionPopulationState, RegionPopulationHistory]:
    region_key = str(region_scores["region_key"])
    growth_direction = _growth_direction_for_region(
        db=db,
        region_key=region_key,
        as_of_day=day,
        current_population_score=_d(region_scores["active_population_score"]),
    )
    heat_level = _heat_label(
        _d(region_scores["opportunity_density_score"]),
        _d(region_scores["congestion_score"]),
        _d(region_scores["housing_pressure_score"]),
        _d(region_scores["business_competition_score"]),
    )
    state = (
        db.query(RegionPopulationState)
        .filter(RegionPopulationState.region_key == region_key)
        .first()
    )
    if state is None:
        state = RegionPopulationState(region_key=region_key)
        db.add(state)
        db.flush()

    start_day = _window_start(day, WINDOW_DAYS)
    state.region_key = region_key
    state.memory_window_start_day = int(start_day)
    state.memory_window_end_day = int(day)
    state.memory_window_start = _day_to_date(start_day)
    state.memory_window_end = as_of_date
    state.active_population_score = _q4(_d(region_scores["active_population_score"]))
    state.opportunity_density_score = _q4(_d(region_scores["opportunity_density_score"]))
    state.congestion_score = _q4(_d(region_scores["congestion_score"]))
    state.housing_pressure_score = _q4(_d(region_scores["housing_pressure_score"]))
    state.business_competition_score = _q4(_d(region_scores["business_competition_score"]))
    state.consumer_flow_score = _q4(_d(region_scores["consumer_flow_score"]))
    state.recent_growth_direction = growth_direction
    state.state_debug_json = _dump_json(
        {
            "heat_level": heat_level,
            "inputs": {
                "population_count": int(region_scores.get("population_count", 0)),
                "total_population_count": int(region_scores.get("total_population_count", 0)),
                "share_of_population": float(region_scores.get("share_of_population", 0.0)),
                "avg_commute_hours": float(region_scores.get("avg_commute_hours", 0.0)),
                "avg_housing_cost_daily_xgp": float(region_scores.get("avg_housing_cost_daily_xgp", 0.0)),
                "avg_units_sold": float(region_scores.get("avg_units_sold", 0.0)),
                "negative_profit_ratio": float(region_scores.get("negative_profit_ratio", 0.0)),
            },
            "macro_context": region_scores.get("macro_context", {}),
        }
    )
    state.last_updated_on = int(day)
    state.last_updated_date = as_of_date

    history = (
        db.query(RegionPopulationHistory)
        .filter(
            RegionPopulationHistory.region_key == region_key,
            RegionPopulationHistory.as_of_day == int(day),
        )
        .first()
    )
    if history is None:
        history = RegionPopulationHistory(region_key=region_key, as_of_day=int(day))
        db.add(history)
        db.flush()

    history.region_key = region_key
    history.as_of_day = int(day)
    history.as_of_date = as_of_date
    history.active_population_score = _q4(_d(region_scores["active_population_score"]))
    history.opportunity_density_score = _q4(_d(region_scores["opportunity_density_score"]))
    history.congestion_score = _q4(_d(region_scores["congestion_score"]))
    history.housing_pressure_score = _q4(_d(region_scores["housing_pressure_score"]))
    history.business_competition_score = _q4(_d(region_scores["business_competition_score"]))
    history.consumer_flow_score = _q4(_d(region_scores["consumer_flow_score"]))
    history.heat_level = heat_level
    history.recent_growth_direction = growth_direction
    history.summary_json = _dump_json(
        {
            "heat_level": heat_level,
            "upside_label": _score_level(_d(region_scores["opportunity_density_score"])),
            "friction_label": _score_level(
                (_d(region_scores["congestion_score"]) + _d(region_scores["housing_pressure_score"])) / Decimal("2")
            ),
        }
    )
    history.debug_json = _dump_json(
        {
            "population_count": int(region_scores.get("population_count", 0)),
            "total_population_count": int(region_scores.get("total_population_count", 0)),
            "macro_context": region_scores.get("macro_context", {}),
        }
    )

    db.flush()
    return state, history


def _serialize_region_state(state: RegionPopulationState) -> dict:
    return {
        "region_key": str(state.region_key or "suburban"),
        "active_population_score": float(_q4(_d(state.active_population_score))),
        "opportunity_density_score": float(_q4(_d(state.opportunity_density_score))),
        "congestion_score": float(_q4(_d(state.congestion_score))),
        "housing_pressure_score": float(_q4(_d(state.housing_pressure_score))),
        "business_competition_score": float(_q4(_d(state.business_competition_score))),
        "consumer_flow_score": float(_q4(_d(state.consumer_flow_score))),
        "recent_growth_direction": str(state.recent_growth_direction or "stable"),
        "last_updated_on": int(state.last_updated_on or 0),
        "last_updated_date": state.last_updated_date.isoformat() if state.last_updated_date else None,
        "memory_window_start": state.memory_window_start.isoformat() if state.memory_window_start else None,
        "memory_window_end": state.memory_window_end.isoformat() if state.memory_window_end else None,
        "debug_meta": _safe_json(state.state_debug_json, {}),
    }


def _get_region_state(db: Session, region_key: str) -> RegionPopulationState | None:
    return (
        db.query(RegionPopulationState)
        .filter(RegionPopulationState.region_key == _normalize_region(region_key))
        .first()
    )


def _ensure_region_state(
    db: Session,
    player: Player,
    region_key: str,
    day: int,
    as_of_date: date,
) -> RegionPopulationState:
    state = _get_region_state(db, region_key)
    if state is None or int(state.last_updated_on or 0) < int(day):
        update_population_pressure(db=db, player_id=player.id, as_of_date=as_of_date)
        state = _get_region_state(db, region_key)
    if state is None:
        raise PopulationPressureValidationError("Region population state could not be resolved.")
    return state


def _state_scores(state: RegionPopulationState) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    return (
        _d(state.active_population_score),
        _d(state.opportunity_density_score),
        _d(state.congestion_score),
        _d(state.housing_pressure_score),
        _d(state.business_competition_score),
        _d(state.consumer_flow_score),
    )


def get_population_effect_multipliers(
    db: Session,
    *,
    region_key: str,
    as_of_date: date | None = None,
    player_id: str | UUID | None = None,
) -> dict:
    """Return bounded integration multipliers for other engines/services.

    This helper is intentionally read-only for callers. It may refresh
    population state for the day when stale.
    """

    day, resolved_date = _resolve_day(db, as_of_date)
    if player_id is not None:
        player = _resolve_player(db, player_id)
    else:
        player = db.query(Player).order_by(Player.created_at.asc()).first()
        if player is None:
            return {
                "region_key": _normalize_region(region_key),
                "as_of_date": resolved_date.isoformat(),
                "business_demand_multiplier": 1.0,
                "business_competition_penalty": 0.0,
                "job_opportunity_modifier": 0.0,
                "side_income_density_multiplier": 1.0,
                "commute_congestion_hours": 0.0,
                "housing_pressure_additive": 0.0,
                "travel_stress_additive": 0.0,
                "debug_meta": {"source": "no_players_fallback"},
            }

    state = _ensure_region_state(
        db=db,
        player=player,
        region_key=region_key,
        day=day,
        as_of_date=resolved_date,
    )
    pop, opp, congestion, housing, competition, consumer_flow = _state_scores(state)

    opp_centered = _clamp((opp - Decimal("50")) / Decimal("100"), Decimal("-0.45"), Decimal("0.45"))
    flow_centered = _clamp((consumer_flow - Decimal("50")) / Decimal("100"), Decimal("-0.45"), Decimal("0.45"))
    competition_centered = _clamp((competition - Decimal("50")) / Decimal("100"), Decimal("-0.45"), Decimal("0.45"))

    business_demand_multiplier = _clamp(
        Decimal("1.00")
        + (opp_centered * Decimal("0.24"))
        + (flow_centered * Decimal("0.18"))
        - (competition_centered * Decimal("0.15")),
        Decimal("0.88"),
        Decimal("1.20"),
    )
    competition_penalty = _clamp(
        (competition / Decimal("100")) * Decimal("0.20"),
        Decimal("0.00"),
        Decimal("0.20"),
    )
    job_opportunity_modifier = _clamp(
        (opp_centered * Decimal("0.28")) - ((congestion - Decimal("50")) / Decimal("100") * Decimal("0.04")),
        Decimal("-0.15"),
        Decimal("0.15"),
    )
    side_income_density_multiplier = _clamp(
        Decimal("1.00")
        + (opp_centered * Decimal("0.18"))
        + (flow_centered * Decimal("0.12"))
        + ((_clamp(pop, Decimal("0"), Decimal("100")) - Decimal("50")) / Decimal("100") * Decimal("0.05"))
        - (competition_centered * Decimal("0.06")),
        Decimal("0.90"),
        Decimal("1.16"),
    )
    commute_congestion_hours = _clamp(
        (congestion / Decimal("100")) * Decimal("1.10"),
        Decimal("0.00"),
        Decimal("1.10"),
    )
    housing_pressure_additive = _clamp(
        ((housing - Decimal("50")) / Decimal("100")) * Decimal("0.14"),
        Decimal("-0.06"),
        Decimal("0.14"),
    )
    travel_stress_additive = _clamp(
        (congestion / Decimal("100")) * Decimal("1.35"),
        Decimal("0.00"),
        Decimal("1.35"),
    )

    return {
        "region_key": str(state.region_key or "suburban"),
        "as_of_date": resolved_date.isoformat(),
        "business_demand_multiplier": float(_q4(business_demand_multiplier)),
        "business_competition_penalty": float(_q4(competition_penalty)),
        "job_opportunity_modifier": float(_q4(job_opportunity_modifier)),
        "side_income_density_multiplier": float(_q4(side_income_density_multiplier)),
        "commute_congestion_hours": float(_q4(commute_congestion_hours)),
        "housing_pressure_additive": float(_q4(housing_pressure_additive)),
        "travel_stress_additive": float(_q4(travel_stress_additive)),
        "debug_meta": {
            "active_population_score": float(_q4(pop)),
            "opportunity_density_score": float(_q4(opp)),
            "congestion_score": float(_q4(congestion)),
            "housing_pressure_score": float(_q4(housing)),
            "business_competition_score": float(_q4(competition)),
            "consumer_flow_score": float(_q4(consumer_flow)),
        },
    }


def update_population_pressure(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Update bounded region population states for the resolved day.

    This updates both supported regions (suburban + downtown) so the world state
    remains coherent, then returns the player's active-region state snapshot.
    """

    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)

    updated_regions: list[dict] = []
    for region_key in SUPPORTED_REGIONS:
        scores = _compute_region_scores(db, region_key=region_key, day=day)
        state, _history = _upsert_region_rows(
            db=db,
            region_scores=scores,
            day=day,
            as_of_date=resolved_date,
        )
        updated_regions.append(_serialize_region_state(state))

    player_region = _active_region_for_player(db, player)
    player_state = next((row for row in updated_regions if row["region_key"] == player_region), None)
    if player_state is None:
        state = _get_region_state(db, player_region)
        if state is None:
            raise PopulationPressureValidationError("Failed to update player region population state.")
        player_state = _serialize_region_state(state)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "region_key": player_region,
        "region_state": player_state,
        "updated_regions": updated_regions,
        "debug_meta": {
            "day": int(day),
            "updated_region_count": len(updated_regions),
        },
    }


def build_region_population_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return the player's current-region population pressure state."""

    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    region_key = _active_region_for_player(db, player)
    state = _ensure_region_state(
        db=db,
        player=player,
        region_key=region_key,
        day=day,
        as_of_date=resolved_date,
    )
    payload = _serialize_region_state(state)
    heat_level = _heat_label(
        _d(state.opportunity_density_score),
        _d(state.congestion_score),
        _d(state.housing_pressure_score),
        _d(state.business_competition_score),
    )
    if heat_level == "hot":
        short_summary = "Region is hot: opportunity is strong, but congestion and competition are elevated."
    elif heat_level == "warm":
        short_summary = "Region is warm: opportunity and friction are both present in moderate range."
    else:
        short_summary = "Region is cool: lower friction with steadier but lighter upside."
    payload.update(
        {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "heat_level": heat_level,
            "short_summary": short_summary,
            "practical_current_responses": list(PRACTICAL_RESPONSES),
            "future_locked_response_options": list(FUTURE_LOCKED_RESPONSES),
        }
    )
    return payload


def build_local_opportunity_pressure(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build player-local opportunity pressure summary from region state."""

    region_state = build_region_population_state(db=db, player_id=player_id, as_of_date=as_of_date)
    opp = _d(region_state["opportunity_density_score"])
    consumer = _d(region_state["consumer_flow_score"])
    competition = _d(region_state["business_competition_score"])
    congestion = _d(region_state["congestion_score"])

    opportunity_density_label = _score_level(opp)
    job_access_label = "stronger" if opp >= Decimal("62") else ("weaker" if opp <= Decimal("42") else "balanced")
    business_demand_label = "strong" if consumer >= Decimal("60") else ("soft" if consumer <= Decimal("40") else "steady")

    local_advantage_summary = (
        "Local opportunity density supports more job/customer flow."
        if opp >= Decimal("58")
        else "Local opportunity is present but not deeply stacked."
    )
    local_friction_summary = (
        "Competition and congestion are the price of this opportunity density."
        if (competition >= Decimal("55") or congestion >= Decimal("55"))
        else "Friction remains moderate in this local environment."
    )

    return {
        "player_id": region_state["player_id"],
        "as_of_date": region_state["as_of_date"],
        "region_key": region_state["region_key"],
        "opportunity_density_label": opportunity_density_label,
        "job_access_label": job_access_label,
        "business_demand_label": business_demand_label,
        "local_advantage_summary": local_advantage_summary,
        "local_friction_summary": local_friction_summary,
        "debug_meta": {
            "opportunity_density_score": float(_q4(opp)),
            "consumer_flow_score": float(_q4(consumer)),
            "business_competition_score": float(_q4(competition)),
            "congestion_score": float(_q4(congestion)),
        },
    }


def build_local_competition_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build bounded local competition summary for business opportunity sharing."""

    region_state = build_region_population_state(db=db, player_id=player_id, as_of_date=as_of_date)
    competition = _d(region_state["business_competition_score"])
    consumer = _d(region_state["consumer_flow_score"])

    competition_level = _score_level(competition)
    business_competition_label = _competition_label(competition)
    demand_share_pressure = _clamp(
        Decimal("0.10")
        + (competition / Decimal("100") * Decimal("0.65"))
        - (consumer / Decimal("100") * Decimal("0.18")),
        Decimal("0.05"),
        Decimal("0.72"),
    )

    if competition_level == "high":
        short_summary = "Customer flow is strong, but keeping share requires tighter execution and pricing discipline."
    elif competition_level == "moderate":
        short_summary = "Opportunity is contested but manageable; margins depend on mode and consistency."
    else:
        short_summary = "Competition is calmer, though growth pace is usually slower."

    return {
        "player_id": region_state["player_id"],
        "as_of_date": region_state["as_of_date"],
        "region_key": region_state["region_key"],
        "competition_level": competition_level,
        "business_competition_label": business_competition_label,
        "demand_share_pressure": float(_q4(demand_share_pressure)),
        "short_summary": short_summary,
        "debug_meta": {
            "business_competition_score": float(_q4(competition)),
            "consumer_flow_score": float(_q4(consumer)),
        },
    }


def build_region_heat_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build region identity summary showing upside + friction together."""

    region_state = build_region_population_state(db=db, player_id=player_id, as_of_date=as_of_date)
    opp = _d(region_state["opportunity_density_score"])
    congestion = _d(region_state["congestion_score"])
    housing = _d(region_state["housing_pressure_score"])
    competition = _d(region_state["business_competition_score"])
    consumer = _d(region_state["consumer_flow_score"])
    region_key = str(region_state["region_key"])

    heat_level = _heat_label(opp, congestion, housing, competition)

    if opp >= Decimal("62"):
        dominant_upside = "Higher local job/customer opportunity density."
    elif opp <= Decimal("42"):
        dominant_upside = "Calmer and steadier cost environment."
    else:
        dominant_upside = "Balanced opportunity with manageable volatility."

    if congestion >= Decimal("62") or housing >= Decimal("62"):
        dominant_friction = "Commute and housing pressure are compounding."
    elif competition >= Decimal("58"):
        dominant_friction = "Competition is tightening easy-margin growth."
    else:
        dominant_friction = "Friction is moderate, but upside is also less explosive."

    if region_key == "downtown":
        housing_tradeoff_summary = (
            "Downtown remains opportunity-rich, but housing and congestion pressure are higher."
        )
    else:
        housing_tradeoff_summary = (
            "Suburban remains cheaper and calmer, but opportunity density is lighter and commute drag is higher."
        )

    if consumer >= Decimal("58") and competition >= Decimal("55"):
        business_climate_summary = "Business demand is active, but contested share keeps margins under pressure."
    elif consumer >= Decimal("55"):
        business_climate_summary = "Business demand support is healthy with moderate competition."
    else:
        business_climate_summary = "Business demand is softer; cash discipline and mode selection matter more."

    if congestion >= Decimal("64"):
        commute_summary = "Congestion is high and now a core daily planning constraint."
    elif congestion >= Decimal("44"):
        commute_summary = "Commute friction is moderate and increasingly important in time budgeting."
    else:
        commute_summary = "Commute friction is relatively calm in this region now."

    return {
        "player_id": region_state["player_id"],
        "as_of_date": region_state["as_of_date"],
        "region_key": region_key,
        "heat_level": heat_level,
        "dominant_upside": dominant_upside,
        "dominant_friction": dominant_friction,
        "housing_tradeoff_summary": housing_tradeoff_summary,
        "business_climate_summary": business_climate_summary,
        "commute_summary": commute_summary,
        "debug_meta": {
            "active_population_score": region_state["active_population_score"],
            "opportunity_density_score": float(_q4(opp)),
            "congestion_score": float(_q4(congestion)),
            "housing_pressure_score": float(_q4(housing)),
            "business_competition_score": float(_q4(competition)),
            "consumer_flow_score": float(_q4(consumer)),
            "recent_growth_direction": region_state.get("recent_growth_direction", "stable"),
        },
    }


def build_population_response_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build current practical response framing for population-pressure conditions."""

    heat = build_region_heat_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    region_key = str(heat["region_key"])
    level = str(heat["heat_level"])

    if level == "hot":
        pressure_summary = (
            f"{region_key.title()} is hot: upside is real, but congestion, cost pressure, and competition are elevated."
        )
        recommendation = "If commute and stress are compounding, prioritize move/rent-closer math before extra grind."
    elif level == "warm":
        pressure_summary = (
            f"{region_key.title()} is active: opportunity and friction are both present in moderate range."
        )
        recommendation = "Balance growth actions with time-protection to avoid hidden commute/stress drag."
    else:
        pressure_summary = (
            f"{region_key.title()} is calmer: lower friction but slower opportunity flow."
        )
        recommendation = "Use calm windows to stabilize debt, health, and disciplined progression."

    return {
        "player_id": heat["player_id"],
        "as_of_date": heat["as_of_date"],
        "region_key": region_key,
        "current_pressure_summary": pressure_summary,
        "practical_current_responses": list(PRACTICAL_RESPONSES),
        "short_recommendation": recommendation,
        "future_locked_response_options": list(FUTURE_LOCKED_RESPONSES),
        "debug_meta": {
            "heat_level": level,
            "dominant_upside": heat.get("dominant_upside"),
            "dominant_friction": heat.get("dominant_friction"),
        },
    }


def build_population_pressure_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compose Step 34 population-pressure payload for frontend/debug hydration."""

    state = build_region_population_state(db=db, player_id=player_id, as_of_date=as_of_date)
    opportunity = build_local_opportunity_pressure(db=db, player_id=player_id, as_of_date=as_of_date)
    competition = build_local_competition_state(db=db, player_id=player_id, as_of_date=as_of_date)
    heat = build_region_heat_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    response = build_population_response_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    return {
        "player_id": state["player_id"],
        "as_of_date": state["as_of_date"],
        "region_state": state,
        "opportunity_pressure": opportunity,
        "competition_state": competition,
        "region_heat": heat,
        "response_summary": response,
        "debug_meta": {
            "service": "population_pressure_service",
            "version": "step34_v1",
        },
    }
