"""Step 17 housing + region pressure full integration engine."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.balance_config import REGION_SWITCH_GUARDRAILS
from app.engine.housing_region_config import REGION_CONFIG, SUPPORTED_REGION_KEYS, RegionConfig
from app.engine.population_pressure_service import get_population_effect_multipliers
from app.models.business_daily_log import BusinessDailyLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing_state import PlayerHousingState

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
INT_Q = Decimal("1")

GAME_EPOCH = date(2026, 1, 1)
GAS_BASE_XGP = Decimal("3.20")
BASE_MPG = Decimal("28.0")

FRUIT_OPERATION_HOURS_BY_LEVEL = {
    "starter": Decimal("4.00"),
    "cart": Decimal("5.00"),
    "small_shop": Decimal("5.50"),
    "large_store": Decimal("6.00"),
}
TRUCK_OPERATION_HOURS_BY_LEVEL = {
    "starter": Decimal("5.00"),
    "truck": Decimal("6.50"),
}


class HousingRegionError(Exception):
    """Base exception for housing region integration."""


class HousingNotFoundError(HousingRegionError):
    """Raised when player or housing state/log data cannot be found."""


class HousingValidationError(HousingRegionError):
    """Raised when invalid region or invalid requests are received."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _to_int(value: Decimal) -> int:
    return int(value.quantize(INT_Q, rounding=ROUND_HALF_UP))


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _normalize_region(region: str | None) -> str:
    normalized = (region or "").strip().lower()
    if normalized not in SUPPORTED_REGION_KEYS:
        raise HousingValidationError("Unsupported region. Use suburban or downtown.")
    return normalized


def _region_config(region_key: str) -> RegionConfig:
    return REGION_CONFIG[_normalize_region(region_key)]


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise HousingValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _resolve_day(as_of_date: date | None, day: int | None) -> tuple[int, date]:
    if day is not None:
        return int(day), _day_to_date(int(day))
    if as_of_date is None:
        raise HousingValidationError("as_of_date or day is required.")
    day_num = _date_to_day(as_of_date)
    if day_num <= 0:
        raise HousingValidationError("as_of_date must be on or after game epoch.")
    return day_num, as_of_date


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise HousingNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise HousingNotFoundError("Player not found.")
    return player


def _get_or_create_player_daily_state(db: Session, player: Player, day: int) -> PlayerDailyState:
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == int(day),
        )
        .first()
    )
    if pds is not None:
        return pds

    cash_now = _money(_d(player.cash_xgp))
    pds = PlayerDailyState(
        player_id=player.id,
        day_number=int(day),
        hours_available_start=int(player.hours_available or 24),
        hours_available_end=int(player.hours_available or 24),
        worked_main_job=False,
        did_settlement=False,
        stress_start=int(player.stress or 0),
        stress_end=int(player.stress or 0),
        health_start=int(player.health or 100),
        health_end=int(player.health or 100),
        cash_start=cash_now,
        cash_end=cash_now,
    )
    db.add(pds)
    db.flush()
    return pds


def _latest_macro_for_day(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= int(day))
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )
    if row is not None:
        return row
    return db.query(MacroDailyState).order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc()).first()


def _business_hours_for_day(db: Session, player_id: UUID, day: int) -> tuple[Decimal, list[BusinessDailyLog]]:
    logs = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player_id,
            BusinessDailyLog.day == int(day),
        )
        .order_by(BusinessDailyLog.created_at.asc(), BusinessDailyLog.id.asc())
        .all()
    )
    total = Decimal("0.00")
    for row in logs:
        btype = (row.business_type or "").strip().lower()
        if btype == "fruit_shop":
            total += FRUIT_OPERATION_HOURS_BY_LEVEL["starter"]
        elif btype == "food_truck":
            total += TRUCK_OPERATION_HOURS_BY_LEVEL["starter"]
    return _q4(total), logs


def _safe_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _serialize_housing_state(state: PlayerHousingState) -> dict:
    return {
        "id": str(state.id),
        "player_id": str(state.player_id),
        "region_key": state.region,
        "region": state.region,
        "housing_type": state.housing_type,
        "monthly_housing_cost_xgp": float(_money(_d(state.monthly_housing_cost_xgp))),
        "monthly_utilities_cost_xgp": float(_money(_d(state.monthly_utilities_cost_xgp))),
        "monthly_transport_base_xgp": float(_money(_d(state.monthly_transport_base_xgp))),
        "daily_housing_cost_xgp": float(_money(_d(state.daily_housing_cost_xgp))),
        "commute_mode": state.commute_mode,
        "commute_modifier": float(_q4(_d(state.commute_modifier))),
        "stress_modifier": int(state.stress_modifier or 0),
        "opportunity_modifier": float(_q4(_d(state.opportunity_modifier))),
        "business_demand_modifier": float(_q4(_d(state.business_demand_modifier))),
        "side_income_modifier": float(_q4(_d(state.side_income_modifier))),
        "networking_modifier": float(_q4(_d(state.networking_modifier))),
        "active_flag": bool(state.active_flag),
        "created_at": state.created_at.isoformat() if state.created_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_housing_daily_log(row: HousingDailyLog) -> dict:
    return {
        "id": str(row.id),
        "player_id": str(row.player_id),
        "day": int(row.day),
        "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
        "region_key": row.region,
        "region": row.region,
        "housing_cost_daily_xgp": float(_money(_d(row.housing_cost_xgp))),
        "housing_cost_xgp": float(_money(_d(row.housing_cost_xgp))),
        "utilities_cost_daily_xgp": float(_money(_d(getattr(row, "utilities_cost_xgp", 0)))),
        "commute_hours": float(_q4(_d(getattr(row, "commute_hours", 0)))),
        "commute_fuel_cost_xgp": float(_money(_d(getattr(row, "commute_fuel_cost_xgp", 0)))),
        "commute_pressure": float(_q4(_d(row.commute_pressure))),
        "region_stress_delta": float(_q4(_d(getattr(row, "region_stress_delta", row.stress_delta)))),
        "stress_delta": int(row.stress_delta or 0),
        "region_opportunity_modifier": float(_q4(_d(getattr(row, "region_opportunity_modifier", 0)))),
        "opportunity_modifier": float(_q4(_d(row.opportunity_modifier))),
        "region_business_demand_modifier": float(_q4(_d(getattr(row, "region_business_demand_modifier", 0)))),
        "region_side_income_modifier": float(_q4(_d(getattr(row, "region_side_income_modifier", 0)))),
        "networking_modifier": float(_q4(_d(getattr(row, "networking_modifier", 0)))),
        "opportunity_quality_signal": float(_q4(_d(getattr(row, "opportunity_quality_signal", 1)))),
        "housing_debug_json": _safe_json(getattr(row, "housing_debug_json", None)),
        "notes_json": _safe_json(row.notes_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_active_housing_state(db: Session, player_id: str | UUID) -> PlayerHousingState | None:
    """Return current active housing state for a player, if any."""
    player = _resolve_player(db, player_id)
    return (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player.id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc(), PlayerHousingState.created_at.desc())
        .first()
    )


def get_or_create_player_housing(
    db: Session,
    player_id: str | UUID,
    *,
    region_key: str | None = None,
    housing_type: str | None = None,
    monthly_housing_cost_xgp: Decimal | int | float | None = None,
    monthly_utilities_cost_xgp: Decimal | int | float | None = None,
    monthly_transport_base_xgp: Decimal | int | float | None = None,
    commute_mode: str | None = None,
    force_new_active: bool = False,
) -> dict:
    """Get or create active player housing state with Step 17 fields."""
    player = _resolve_player(db, player_id)
    resolved_region = _normalize_region(region_key or player.housing_region_id or player.region or "suburban")
    cfg = _region_config(resolved_region)
    active = get_active_housing_state(db, player.id)

    if active is not None and not force_new_active and _normalize_region(active.region) == resolved_region:
        return {
            "created": False,
            "player_id": str(player.id),
            **_serialize_housing_state(active),
        }

    if force_new_active or active is None or _normalize_region(active.region) != resolved_region:
        (
            db.query(PlayerHousingState)
            .filter(
                PlayerHousingState.player_id == player.id,
                PlayerHousingState.active_flag.is_(True),
            )
            .update({"active_flag": False}, synchronize_session=False)
        )

        state = PlayerHousingState(
            player_id=player.id,
            region=resolved_region,
            housing_type=(housing_type or cfg.housing_type_default or "rent").strip().lower(),
            monthly_housing_cost_xgp=_money(
                _clamp(
                    _d(monthly_housing_cost_xgp) if monthly_housing_cost_xgp is not None else cfg.monthly_housing_cost_xgp,
                    Decimal("0.00"),
                    Decimal("99999.00"),
                )
            ),
            monthly_utilities_cost_xgp=_money(
                _clamp(
                    _d(monthly_utilities_cost_xgp)
                    if monthly_utilities_cost_xgp is not None
                    else cfg.monthly_utilities_cost_xgp,
                    Decimal("0.00"),
                    Decimal("99999.00"),
                )
            ),
            monthly_transport_base_xgp=_money(
                _clamp(
                    _d(monthly_transport_base_xgp)
                    if monthly_transport_base_xgp is not None
                    else cfg.monthly_transport_base_xgp,
                    Decimal("0.00"),
                    Decimal("99999.00"),
                )
            ),
            daily_housing_cost_xgp=_money(
                _clamp(
                    (
                        _d(monthly_housing_cost_xgp)
                        if monthly_housing_cost_xgp is not None
                        else cfg.monthly_housing_cost_xgp
                    )
                    / Decimal("30.00"),
                    Decimal("0.00"),
                    Decimal("9999.00"),
                )
            ),
            commute_mode=(commute_mode or cfg.commute_mode_default or "car").strip().lower(),
            commute_modifier=_q4(
                _clamp(
                    Decimal("1.00") + (cfg.commute_hours_baseline - Decimal("0.80")) / Decimal("2.00"),
                    Decimal("0.70"),
                    Decimal("1.50"),
                )
            ),
            stress_modifier=_to_int(_clamp(cfg.region_stress_load, Decimal("-3"), Decimal("5"))),
            opportunity_modifier=_q4(_clamp(Decimal("1.00") + cfg.job_opportunity_modifier, Decimal("0.85"), Decimal("1.15"))),
            business_demand_modifier=_q4(_clamp(Decimal("1.00") + cfg.business_demand_modifier, Decimal("0.85"), Decimal("1.20"))),
            side_income_modifier=_q4(_clamp(Decimal("1.00") + cfg.side_income_modifier, Decimal("0.90"), Decimal("1.15"))),
            networking_modifier=_q4(_clamp(cfg.networking_modifier, Decimal("-0.20"), Decimal("0.20"))),
            active_flag=True,
        )
        db.add(state)
        db.flush()
        active = state

    player.region = resolved_region
    player.housing_region_id = resolved_region
    player.has_active_housing = True
    db.flush()

    return {
        "created": True,
        "player_id": str(player.id),
        **_serialize_housing_state(active),
    }


def update_player_region(
    db: Session,
    player_id: str | UUID,
    region_key: str,
    *,
    housing_type: str | None = None,
    commute_mode: str | None = None,
) -> dict:
    """Switch player to another region with a new active housing state row."""
    return get_or_create_player_housing(
        db=db,
        player_id=player_id,
        region_key=region_key,
        housing_type=housing_type,
        commute_mode=commute_mode,
        force_new_active=True,
    )


def _existing_housing_log_for_day(db: Session, player_id: UUID, day: int) -> HousingDailyLog | None:
    return (
        db.query(HousingDailyLog)
        .filter(
            HousingDailyLog.player_id == player_id,
            HousingDailyLog.day == int(day),
        )
        .order_by(HousingDailyLog.created_at.desc())
        .first()
    )


def compute_daily_housing_region_effects(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    day: int | None = None,
) -> dict:
    """Compute deterministic daily housing/region effects and persist daily state."""
    player = _resolve_player(db, player_id)
    day_num, resolved_date = _resolve_day(as_of_date, day)
    if day_num <= 0:
        raise HousingValidationError("day must be greater than 0.")

    existing = _existing_housing_log_for_day(db, player.id, day_num)
    if existing is not None:
        pds = _get_or_create_player_daily_state(db, player, day_num)
        payload = _serialize_housing_daily_log(existing)
        _apply_housing_fields_to_daily_state(pds, payload)
        db.flush()
        payload["already_processed"] = True
        return payload

    housing_payload = get_or_create_player_housing(db, player.id)
    state = (
        db.query(PlayerHousingState)
        .filter(PlayerHousingState.id == UUID(housing_payload["id"]))
        .first()
    )
    if state is None:
        raise HousingNotFoundError("Player housing state not found.")

    cfg = _region_config(state.region)
    pds = _get_or_create_player_daily_state(db, player, day_num)
    population_effects = {
        "business_demand_multiplier": 1.0,
        "business_competition_penalty": 0.0,
        "job_opportunity_modifier": 0.0,
        "side_income_density_multiplier": 1.0,
        "commute_congestion_hours": 0.0,
        "housing_pressure_additive": 0.0,
        "travel_stress_additive": 0.0,
        "debug_meta": {},
    }
    try:
        population_effects = get_population_effect_multipliers(
            db=db,
            region_key=state.region,
            as_of_date=resolved_date,
            player_id=player.id,
        )
    except Exception:
        population_effects = {
            "business_demand_multiplier": 1.0,
            "business_competition_penalty": 0.0,
            "job_opportunity_modifier": 0.0,
            "side_income_density_multiplier": 1.0,
            "commute_congestion_hours": 0.0,
            "housing_pressure_additive": 0.0,
            "travel_stress_additive": 0.0,
            "debug_meta": {"population_fallback": True},
        }

    # Step 21 anti-exploit guardrail: rapid region switching creates a
    # short transition friction window (time, fuel, and stress).
    previous_region_log = (
        db.query(HousingDailyLog)
        .filter(
            HousingDailyLog.player_id == player.id,
            HousingDailyLog.day < int(day_num),
        )
        .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
        .first()
    )
    friction_window_days = int(REGION_SWITCH_GUARDRAILS["friction_window_days"])
    switch_friction_active = False
    switch_days_since: int | None = None
    switch_commute_bonus = Decimal("0.00")
    switch_stress_bonus = Decimal("0.00")
    switch_fuel_surcharge = Decimal("0.00")
    if previous_region_log is not None:
        prev_region = (str(previous_region_log.region or "")).strip().lower()
        if prev_region and prev_region != state.region:
            switch_days_since = max(0, int(day_num) - int(previous_region_log.day))
            if switch_days_since <= friction_window_days:
                switch_friction_active = True
                switch_commute_bonus = _d(REGION_SWITCH_GUARDRAILS["commute_bonus_hours"])
                switch_stress_bonus = _d(REGION_SWITCH_GUARDRAILS["stress_bonus"])
                switch_fuel_surcharge = _d(REGION_SWITCH_GUARDRAILS["fuel_surcharge_xgp"])

    job_hours = _q4(_d(getattr(pds, "worked_hours", 0) or getattr(player, "main_job_hours_today", 0)))
    side_income_hours = _q4(_d(getattr(pds, "side_income_hours", 0)))
    business_hours_from_logs, business_logs = _business_hours_for_day(db, player.id, day_num)
    business_hours = _q4(
        _d(getattr(pds, "business_hours", 0))
        if _d(getattr(pds, "business_hours", 0)) > 0
        else business_hours_from_logs
    )

    activity_count = 0
    if job_hours > 0:
        activity_count += 1
    if business_hours > 0:
        activity_count += 1
    if side_income_hours > 0:
        activity_count += 1

    mismatch_penalty = Decimal("0.00")
    for log in business_logs:
        if (log.region_key or "").strip().lower() and (log.region_key or "").strip().lower() != state.region:
            mismatch_penalty += Decimal("0.20")

    if activity_count <= 0:
        commute_hours = Decimal("0.00")
    else:
        side_deadhead = Decimal("0.18") if side_income_hours > 0 and state.region == "suburban" else Decimal("0.05")
        commute_hours = _clamp(
            cfg.commute_hours_baseline
            + (cfg.commute_hours_per_activity * Decimal(str(max(0, activity_count - 1))))
            + mismatch_penalty
            + side_deadhead,
            Decimal("0.30"),
            Decimal("3.50"),
        )
        if switch_friction_active:
            commute_hours = _clamp(commute_hours + switch_commute_bonus, Decimal("0.30"), Decimal("4.00"))
        commute_hours = _clamp(
            commute_hours + _d(population_effects.get("commute_congestion_hours", 0)),
            Decimal("0.30"),
            Decimal("4.00"),
        )

    housing_cost_daily = _money(_clamp(_d(state.monthly_housing_cost_xgp) / Decimal("30.00"), Decimal("0.00"), Decimal("9999.00")))
    housing_cost_daily = _money(
        _clamp(
            housing_cost_daily
            * (
                Decimal("1.00")
                + _d(population_effects.get("housing_pressure_additive", 0))
            ),
            Decimal("0.00"),
            Decimal("9999.00"),
        )
    )
    utilities_cost_daily = _money(
        _clamp(_d(state.monthly_utilities_cost_xgp) / Decimal("30.00"), Decimal("0.00"), Decimal("9999.00"))
    )

    macro = _latest_macro_for_day(db, day_num)
    oil_index = _q4(_d(getattr(macro, "oil_index", 100)))
    gas_price = _q4(GAS_BASE_XGP * (oil_index / Decimal("100.00")))
    commute_mode_factor = Decimal("0.65") if (state.commute_mode or "car").strip().lower() == "transit" else Decimal("1.00")
    baseline_miles = _q4(
        Decimal("8.0")
        + (commute_hours * Decimal("7.5"))
        + (Decimal(str(max(0, activity_count - 1))) * Decimal("2.2"))
        + (mismatch_penalty * Decimal("10"))
    )
    transport_anchor = _q4(_d(state.monthly_transport_base_xgp) / Decimal("30.00"))
    commute_fuel_cost = Decimal("0.00")
    if activity_count > 0:
        direct_fuel = _q4((baseline_miles / BASE_MPG) * gas_price * commute_mode_factor)
        commute_fuel_cost = _money(
            _clamp(
                (direct_fuel * Decimal("0.55")) + (transport_anchor * Decimal("0.45") * (oil_index / Decimal("100.00"))),
                Decimal("0.00"),
                Decimal("14.00"),
            )
        )
        if switch_friction_active:
            commute_fuel_cost = _money(_clamp(commute_fuel_cost + switch_fuel_surcharge, Decimal("0.00"), Decimal("18.00")))

    commute_pressure = _q4(_clamp((commute_hours - Decimal("0.50")) * Decimal("1.20"), Decimal("0.00"), Decimal("3.00")))
    region_stress_delta = _clamp(
        cfg.region_stress_load + (max(Decimal("0.0"), commute_hours - Decimal("0.80")) * Decimal("0.90")) + (mismatch_penalty * Decimal("0.80")),
        Decimal("-1.50"),
        Decimal("2.50"),
    )
    region_stress_delta = _clamp(
        region_stress_delta + _d(population_effects.get("travel_stress_additive", 0)),
        Decimal("-1.50"),
        Decimal("2.50"),
    )
    if switch_friction_active:
        region_stress_delta = _clamp(region_stress_delta + switch_stress_bonus, Decimal("-1.50"), Decimal("2.50"))
    region_opportunity_modifier = _clamp(
        cfg.job_opportunity_modifier
        + (cfg.networking_modifier * Decimal("0.25"))
        + _d(population_effects.get("job_opportunity_modifier", 0)),
        Decimal("-0.15"),
        Decimal("0.15"),
    )
    region_business_demand_modifier = _clamp(
        cfg.business_demand_modifier
        + (cfg.networking_modifier * Decimal("0.20"))
        + ((_d(population_effects.get("business_demand_multiplier", 1)) - Decimal("1.00")) * Decimal("0.50")),
        Decimal("-0.15"),
        Decimal("0.20"),
    )
    region_side_income_modifier = _clamp(
        cfg.side_income_modifier
        + (cfg.networking_modifier * Decimal("0.10"))
        + ((_d(population_effects.get("side_income_density_multiplier", 1)) - Decimal("1.00")) * Decimal("0.45")),
        Decimal("-0.10"),
        Decimal("0.15"),
    )
    networking_modifier = _clamp(cfg.networking_modifier, Decimal("-0.20"), Decimal("0.20"))
    opportunity_quality_signal = _clamp(
        Decimal("1.00")
        + networking_modifier
        + (region_opportunity_modifier * Decimal("0.80"))
        - (max(Decimal("0"), region_stress_delta) * Decimal("0.04")),
        Decimal("0.80"),
        Decimal("1.25"),
    )

    opportunity_multiplier = _q4(_clamp(Decimal("1.00") + region_opportunity_modifier, Decimal("0.85"), Decimal("1.15")))
    stress_delta_int = _to_int(region_stress_delta)

    debug_meta = {
        "day": int(day_num),
        "as_of_date": resolved_date.isoformat(),
        "activity_count": int(activity_count),
        "job_hours": float(_q4(job_hours)),
        "business_hours": float(_q4(business_hours)),
        "side_income_hours": float(_q4(side_income_hours)),
        "mismatch_penalty_hours": float(_q4(mismatch_penalty)),
        "commute_mode_factor": float(_q4(commute_mode_factor)),
        "oil_index": float(_q4(oil_index)),
        "gas_price_xgp": float(_q4(gas_price)),
        "baseline_miles": float(_q4(baseline_miles)),
        "transport_anchor_xgp": float(_q4(transport_anchor)),
        "region_switch_friction": {
            "active": bool(switch_friction_active),
            "days_since_switch": int(switch_days_since) if switch_days_since is not None else None,
            "window_days": int(friction_window_days),
            "commute_bonus_hours": float(_q4(switch_commute_bonus)),
            "stress_bonus": float(_q4(switch_stress_bonus)),
            "fuel_surcharge_xgp": float(_money(switch_fuel_surcharge)),
        },
        "config": {
            "region_key": cfg.region_key,
            "commute_hours_baseline": float(_q4(cfg.commute_hours_baseline)),
            "commute_hours_per_activity": float(_q4(cfg.commute_hours_per_activity)),
            "region_stress_load": float(_q4(cfg.region_stress_load)),
            "job_opportunity_modifier": float(_q4(cfg.job_opportunity_modifier)),
            "business_demand_modifier": float(_q4(cfg.business_demand_modifier)),
            "side_income_modifier": float(_q4(cfg.side_income_modifier)),
            "networking_modifier": float(_q4(cfg.networking_modifier)),
        },
        "population_effects": population_effects,
    }

    row = HousingDailyLog(
        player_id=player.id,
        day=int(day_num),
        as_of_date=resolved_date,
        region=state.region,
        housing_cost_xgp=housing_cost_daily,
        utilities_cost_xgp=utilities_cost_daily,
        commute_hours=_q4(commute_hours),
        commute_fuel_cost_xgp=commute_fuel_cost,
        commute_pressure=commute_pressure,
        stress_delta=stress_delta_int,
        opportunity_modifier=opportunity_multiplier,
        region_stress_delta=_q4(region_stress_delta),
        region_opportunity_modifier=_q4(region_opportunity_modifier),
        region_business_demand_modifier=_q4(region_business_demand_modifier),
        region_side_income_modifier=_q4(region_side_income_modifier),
        networking_modifier=_q4(networking_modifier),
        opportunity_quality_signal=_q4(opportunity_quality_signal),
        housing_debug_json=json.dumps(debug_meta, sort_keys=True),
        notes_json=json.dumps(debug_meta, sort_keys=True),
    )
    db.add(row)
    db.flush()
    db.refresh(row)

    payload = _serialize_housing_daily_log(row)
    _apply_housing_fields_to_daily_state(pds, payload)
    db.flush()
    payload["already_processed"] = False
    return payload


def _apply_housing_fields_to_daily_state(pds: PlayerDailyState, payload: dict) -> None:
    pds.region_key = payload.get("region_key")
    pds.housing_cost_daily_xgp = _money(_d(payload.get("housing_cost_daily_xgp", payload.get("housing_cost_xgp", 0))))
    pds.utilities_cost_daily_xgp = _money(_d(payload.get("utilities_cost_daily_xgp", 0)))
    pds.commute_hours = _q4(_d(payload.get("commute_hours", 0)))
    pds.commute_fuel_cost_xgp = _money(_d(payload.get("commute_fuel_cost_xgp", 0)))
    pds.region_stress_delta = _q4(_d(payload.get("region_stress_delta", payload.get("stress_delta", 0))))
    pds.region_opportunity_modifier = _q4(_d(payload.get("region_opportunity_modifier", 0)))
    pds.region_business_demand_modifier = _q4(_d(payload.get("region_business_demand_modifier", 0)))
    pds.region_side_income_modifier = _q4(_d(payload.get("region_side_income_modifier", 0)))
    pds.networking_modifier = _q4(_d(payload.get("networking_modifier", 0)))
    pds.opportunity_quality_signal = _q4(_d(payload.get("opportunity_quality_signal", 1)))
    pds.housing_debug_json = json.dumps(payload.get("housing_debug_json", {}), sort_keys=True)


def get_player_housing_snapshot(db: Session, player_id: str | UUID) -> dict:
    """Return current player housing state and latest housing-region day signal."""
    player = _resolve_player(db, player_id)
    state_payload = get_or_create_player_housing(db, player.id)
    latest_row = (
        db.query(HousingDailyLog)
        .filter(HousingDailyLog.player_id == player.id)
        .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
        .first()
    )
    debug_meta: dict[str, object] = {"latest_daily_effect_found": bool(latest_row is not None)}
    if latest_row is not None:
        debug_meta["latest_day"] = int(latest_row.day)
    return {
        "player_id": str(player.id),
        "region_key": state_payload["region_key"],
        "housing_type": state_payload["housing_type"],
        "monthly_housing_cost_xgp": float(state_payload["monthly_housing_cost_xgp"]),
        "monthly_utilities_cost_xgp": float(state_payload["monthly_utilities_cost_xgp"]),
        "monthly_transport_base_xgp": float(state_payload["monthly_transport_base_xgp"]),
        "commute_mode": state_payload["commute_mode"],
        "networking_modifier": float(state_payload["networking_modifier"]),
        "region_opportunity_modifier": float(_q4(_d(state_payload["opportunity_modifier"]) - Decimal("1.0"))),
        "region_business_demand_modifier": float(_q4(_d(state_payload["business_demand_modifier"]) - Decimal("1.0"))),
        "region_side_income_modifier": float(_q4(_d(state_payload["side_income_modifier"]) - Decimal("1.0"))),
        "latest_daily": _serialize_housing_daily_log(latest_row) if latest_row is not None else None,
        "debug_meta": debug_meta,
    }


def get_player_housing_history(db: Session, player_id: str | UUID, *, limit: int = 30) -> dict:
    """Return recent housing-region daily entries + trailing 7d averages."""
    if int(limit) <= 0:
        raise HousingValidationError("limit must be greater than 0.")
    player = _resolve_player(db, player_id)
    rows = (
        db.query(HousingDailyLog)
        .filter(HousingDailyLog.player_id == player.id)
        .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
        .limit(int(limit))
        .all()
    )
    entries = [_serialize_housing_daily_log(row) for row in rows]
    recent = entries[:7]
    n = Decimal(str(max(1, len(recent))))
    trailing_commute = sum((Decimal(str(item["commute_hours"])) for item in recent), Decimal("0")) / n
    trailing_housing = sum((Decimal(str(item["housing_cost_daily_xgp"])) for item in recent), Decimal("0")) / n
    trailing_stress = sum((Decimal(str(item["region_stress_delta"])) for item in recent), Decimal("0")) / n

    return {
        "player_id": str(player.id),
        "entries": entries,
        "trailing_7d_avg_commute_hours": float(_q4(trailing_commute)),
        "trailing_7d_avg_housing_cost_xgp": float(_money(trailing_housing)),
        "trailing_7d_avg_region_stress_delta": float(_q4(trailing_stress)),
    }


def get_business_region_demand_modifier(db: Session, player_id: str | UUID, business_type: str) -> Decimal:
    """Return bounded multiplicative region demand factor for business operations."""
    state = get_active_housing_state(db, player_id)
    if state is None:
        return Decimal("1.0000")
    region = (state.region or "suburban").strip().lower()
    base = _q4(_d(state.business_demand_modifier))
    network_factor = _q4(Decimal("1.00") + (_d(state.networking_modifier) * Decimal("0.20")))
    btype = (business_type or "").strip().lower()
    type_bias = Decimal("1.00")
    if btype == "food_truck":
        type_bias = Decimal("1.0200") if region == "downtown" else Decimal("0.9900")
    elif btype == "fruit_shop":
        type_bias = Decimal("1.0100") if region == "downtown" else Decimal("1.0000")
    population_mult = Decimal("1.0000")
    competition_penalty = Decimal("0.0000")
    try:
        population = get_population_effect_multipliers(
            db=db,
            region_key=region,
            player_id=str(player_id),
        )
        population_mult = _q4(_d(population.get("business_demand_multiplier", 1)))
        competition_penalty = _q4(_d(population.get("business_competition_penalty", 0)))
    except Exception:
        population_mult = Decimal("1.0000")
        competition_penalty = Decimal("0.0000")
    modifier = _q4(base * network_factor * type_bias * population_mult * (Decimal("1.00") - (competition_penalty * Decimal("0.40"))))
    return _clamp(modifier, Decimal("0.8500"), Decimal("1.2000"))


def get_side_income_region_modifier(db: Session, player_id: str | UUID) -> Decimal:
    """Return bounded multiplicative region modifier for side-income demand quality."""
    state = get_active_housing_state(db, player_id)
    if state is None:
        return Decimal("1.0000")
    region = (state.region or "suburban").strip().lower()
    base = _q4(_d(state.side_income_modifier))
    network_factor = _q4(Decimal("1.00") + (_d(state.networking_modifier) * Decimal("0.12")))
    population_mult = Decimal("1.0000")
    try:
        population = get_population_effect_multipliers(
            db=db,
            region_key=region,
            player_id=str(player_id),
        )
        population_mult = _q4(_d(population.get("side_income_density_multiplier", 1)))
    except Exception:
        population_mult = Decimal("1.0000")
    modifier = _q4(base * network_factor * population_mult)
    return _clamp(modifier, Decimal("0.9000"), Decimal("1.1500"))


def get_job_region_opportunity_modifier(db: Session, player_id: str | UUID) -> Decimal:
    """Return additive job-access modifier in [-0.15, +0.15]."""
    state = get_active_housing_state(db, player_id)
    if state is None:
        return Decimal("0.0000")
    region = (state.region or "suburban").strip().lower()
    population_additive = Decimal("0.0000")
    try:
        population = get_population_effect_multipliers(
            db=db,
            region_key=region,
            player_id=str(player_id),
        )
        population_additive = _q4(_d(population.get("job_opportunity_modifier", 0)))
    except Exception:
        population_additive = Decimal("0.0000")
    return _q4(
        _clamp(
            (_d(state.opportunity_modifier) - Decimal("1.00"))
            + (_d(state.networking_modifier) * Decimal("0.10"))
            + population_additive,
            Decimal("-0.1500"),
            Decimal("0.1500"),
        )
    )


# ---------------------------------------------------------------------------
# Backward-compatible wrappers used by existing services/routes/tests
# ---------------------------------------------------------------------------


def assign_player_housing(
    db: Session,
    player_id: str | UUID,
    region: str,
    housing_type: str = "starter_rent",
    *,
    commit: bool = True,
) -> dict:
    payload = update_player_region(
        db=db,
        player_id=player_id,
        region_key=region,
        housing_type=housing_type,
    )
    if commit:
        db.commit()
    else:
        db.flush()
    payload["region"] = payload["region_key"]
    payload["active_flag"] = True
    return payload


def compute_housing_effects_for_day(db: Session, player_id: str | UUID, day: int) -> dict:
    payload = compute_daily_housing_region_effects(db=db, player_id=player_id, day=int(day))
    payload["region"] = payload["region_key"]
    payload["housing_cost_xgp"] = payload["housing_cost_daily_xgp"]
    payload["stress_delta"] = int(_to_int(_d(payload["region_stress_delta"])))
    payload["opportunity_modifier"] = float(
        _q4(Decimal("1.00") + _d(payload.get("region_opportunity_modifier", 0)))
    )
    return payload


def get_player_housing_summary(db: Session, player_id: str | UUID) -> dict:
    snapshot = get_player_housing_snapshot(db=db, player_id=player_id)
    latest = snapshot.get("latest_daily")
    return {
        "player_id": snapshot["player_id"],
        "active_housing_state": {
            "player_id": snapshot["player_id"],
            "region": snapshot["region_key"],
            "region_key": snapshot["region_key"],
            "housing_type": snapshot["housing_type"],
            "monthly_housing_cost_xgp": snapshot["monthly_housing_cost_xgp"],
            "monthly_utilities_cost_xgp": snapshot["monthly_utilities_cost_xgp"],
            "monthly_transport_base_xgp": snapshot["monthly_transport_base_xgp"],
            "commute_mode": snapshot["commute_mode"],
            "networking_modifier": snapshot["networking_modifier"],
            "region_opportunity_modifier": snapshot["region_opportunity_modifier"],
            "region_business_demand_modifier": snapshot["region_business_demand_modifier"],
            "region_side_income_modifier": snapshot["region_side_income_modifier"],
        },
        "latest_housing_log": latest,
        "summary": {
            "region": snapshot["region_key"],
            "daily_housing_cost_xgp": (latest or {}).get("housing_cost_daily_xgp", snapshot["monthly_housing_cost_xgp"] / 30.0),
            "commute_hours": (latest or {}).get("commute_hours", 0.0),
            "region_stress_delta": (latest or {}).get("region_stress_delta", 0.0),
            "opportunity_modifier": float(_q4(Decimal("1.00") + _d(snapshot["region_opportunity_modifier"]))),
        },
    }


def get_player_housing_logs(db: Session, player_id: str | UUID, limit: int = 20) -> dict:
    payload = get_player_housing_history(db=db, player_id=player_id, limit=limit)
    return {
        "player_id": payload["player_id"],
        "count": len(payload["entries"]),
        "logs": payload["entries"],
        "trailing_7d_avg_commute_hours": payload["trailing_7d_avg_commute_hours"],
        "trailing_7d_avg_housing_cost_xgp": payload["trailing_7d_avg_housing_cost_xgp"],
        "trailing_7d_avg_region_stress_delta": payload["trailing_7d_avg_region_stress_delta"],
    }
