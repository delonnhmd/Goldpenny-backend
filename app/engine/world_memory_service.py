"""Step 30 world memory service.

This module adds a lightweight persistence and interpretation layer so the
world feels historically continuous over rolling windows. It is compositional:
it reads existing daily outputs and stores compact memory snapshots/patterns.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_housing_state import PlayerHousingState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_shock_state import PlayerShockState
from app.models.region_population_state import RegionPopulationState
from app.models.player_world_memory_state import PlayerWorldMemoryState
from app.models.player_world_pattern_history import PlayerWorldPatternHistory

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
WINDOW_DAYS = 14
SHORT_WINDOW_DAYS = 7

ACTIVE_STATUS = "active"
FADING_STATUS = "fading"
RESOLVED_STATUS = "resolved"

PRACTICAL_COMMUTE_RESPONSES = [
    "Stay and absorb commute cost and stress for now.",
    "Move to reduce daily commute burden.",
    "Rent closer now and accept higher housing expense.",
]

FUTURE_LOCKED_SOLUTIONS = [
    "Mobility ventures (locked)",
    "Transportation startup paths (locked)",
    "Logistics optimization businesses (locked)",
    "Vehicle/brand commute solutions (locked)",
]


class WorldMemoryError(Exception):
    """Base exception for world memory composition."""


class WorldMemoryNotFoundError(WorldMemoryError):
    """Raised when player cannot be found."""


class WorldMemoryValidationError(WorldMemoryError):
    """Raised when invalid dates/inputs are supplied."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise WorldMemoryValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise WorldMemoryValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise WorldMemoryNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise WorldMemoryNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, player: Player, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date

    latest_settlement = (
        db.query(func.max(DailySettlementLog.day_number))
        .filter(DailySettlementLog.player_id == player.id)
        .scalar()
    )
    latest_housing = (
        db.query(func.max(HousingDailyLog.day))
        .filter(HousingDailyLog.player_id == player.id)
        .scalar()
    )
    latest_business = (
        db.query(func.max(BusinessDailyLog.day))
        .filter(BusinessDailyLog.player_id == player.id)
        .scalar()
    )
    latest_daily = (
        db.query(func.max(PlayerDailyState.day_number))
        .filter(PlayerDailyState.player_id == player.id)
        .scalar()
    )
    try:
        latest_payment = (
            db.query(func.max(PlayerPaymentHistory.day_number))
            .filter(PlayerPaymentHistory.player_id == player.id)
            .scalar()
        )
    except Exception:
        # PlayerPaymentHistory may be absent in minimal/legacy test schemas.
        latest_payment = None
    try:
        latest_borrowing = (
            db.query(func.max(PlayerBorrowingHistory.day_number))
            .filter(PlayerBorrowingHistory.player_id == player.id)
            .scalar()
        )
    except Exception:
        latest_borrowing = None
    latest_macro = db.query(func.max(MacroDailyState.day)).scalar()

    day = max(
        int(latest_settlement or 0),
        int(latest_housing or 0),
        int(latest_business or 0),
        int(latest_daily or 0),
        int(latest_payment or 0),
        int(latest_borrowing or 0),
        int(latest_macro or 0),
        1,
    )
    return day, _day_to_date(day)


def _window_start(day: int, window_days: int) -> int:
    return max(1, int(day) - max(1, int(window_days)) + 1)


def _parse_json(value: str | None, default):
    if not value:
        return default
    try:
        payload = json.loads(value)
    except Exception:
        return default
    return payload if isinstance(payload, type(default)) else default


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


def _consecutive_true(flags: list[bool]) -> int:
    count = 0
    for flag in reversed(flags):
        if not flag:
            break
        count += 1
    return count


def _direction_from_values(values: list[Decimal], tolerance: Decimal) -> str:
    if len(values) < 2:
        return "stable"
    delta = values[-1] - values[0]
    if delta > tolerance:
        return "rising"
    if delta < -tolerance:
        return "falling"
    return "stable"


def _severity_from_score(score: Decimal) -> str:
    value = _clamp(score, Decimal("0"), Decimal("100"))
    if value >= Decimal("70"):
        return "high"
    if value >= Decimal("40"):
        return "moderate"
    return "low"


def _confidence_from_consecutive(consecutive_days: int) -> str:
    if consecutive_days >= 5:
        return "high"
    if consecutive_days >= 3:
        return "moderate"
    return "low"


def _pressure_level_from_score(score: Decimal) -> str:
    value = _clamp(score, Decimal("0"), Decimal("100"))
    if value >= Decimal("70"):
        return "high"
    if value >= Decimal("40"):
        return "moderate"
    return "low"


def _avg(values: list[Decimal], default: Decimal = Decimal("0")) -> Decimal:
    if not values:
        return default
    return _q4(sum(values, Decimal("0")) / Decimal(str(len(values))))


def _recent_macro_rows(db: Session, day: int, window_days: int) -> list[MacroDailyState]:
    return (
        db.query(MacroDailyState)
        .filter(
            MacroDailyState.day >= _window_start(day, window_days),
            MacroDailyState.day <= int(day),
        )
        .order_by(MacroDailyState.day.asc(), MacroDailyState.created_at.asc())
        .all()
    )


def _recent_basket_rows(
    db: Session,
    basket_type: BasketType,
    day: int,
    window_days: int,
) -> list[BasketDailyPrice]:
    return (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day >= _window_start(day, window_days),
            BasketDailyPrice.day <= int(day),
        )
        .order_by(BasketDailyPrice.day.asc(), BasketDailyPrice.created_at.asc())
        .all()
    )


def _recent_housing_rows(db: Session, player_id: UUID, day: int, window_days: int) -> list[HousingDailyLog]:
    return (
        db.query(HousingDailyLog)
        .filter(
            HousingDailyLog.player_id == player_id,
            HousingDailyLog.day >= _window_start(day, window_days),
            HousingDailyLog.day <= int(day),
        )
        .order_by(HousingDailyLog.day.asc(), HousingDailyLog.created_at.asc())
        .all()
    )


def _recent_business_rows(
    db: Session,
    player_id: UUID,
    business_type: str,
    day: int,
    window_days: int,
) -> list[BusinessDailyLog]:
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player_id,
            BusinessDailyLog.business_type == business_type,
            BusinessDailyLog.day >= _window_start(day, window_days),
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.asc(), BusinessDailyLog.created_at.asc())
        .all()
    )


def _recent_settlement_rows(
    db: Session,
    player_id: UUID,
    day: int,
    window_days: int,
) -> list[DailySettlementLog]:
    return (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player_id,
            DailySettlementLog.day_number >= _window_start(day, window_days),
            DailySettlementLog.day_number <= int(day),
        )
        .order_by(DailySettlementLog.day_number.asc(), DailySettlementLog.created_at.asc())
        .all()
    )


def _recent_daily_rows(
    db: Session,
    player_id: UUID,
    day: int,
    window_days: int,
) -> list[PlayerDailyState]:
    return (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player_id,
            PlayerDailyState.day_number >= _window_start(day, window_days),
            PlayerDailyState.day_number <= int(day),
        )
        .order_by(PlayerDailyState.day_number.asc(), PlayerDailyState.created_at.asc())
        .all()
    )


def _recent_distress_rows(
    db: Session,
    player_id: UUID,
    day: int,
    window_days: int,
    ) -> list[FinancialDistressLog]:
    return (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player_id,
            FinancialDistressLog.day >= _window_start(day, window_days),
            FinancialDistressLog.day <= int(day),
        )
        .order_by(FinancialDistressLog.day.asc(), FinancialDistressLog.created_at.asc())
        .all()
    )


def _recent_payment_rows(
    db: Session,
    player_id: UUID,
    day: int,
    window_days: int,
) -> list[PlayerPaymentHistory]:
    try:
        return (
            db.query(PlayerPaymentHistory)
            .filter(
                PlayerPaymentHistory.player_id == player_id,
                PlayerPaymentHistory.day_number >= _window_start(day, window_days),
                PlayerPaymentHistory.day_number <= int(day),
            )
            .order_by(PlayerPaymentHistory.day_number.asc(), PlayerPaymentHistory.created_at.asc())
            .all()
        )
    except Exception:
        # Table may be absent in legacy/minimal test schemas.
        return []


def _recent_personal_event_rows(
    db: Session,
    player_id: UUID,
    day: int,
    window_days: int,
) -> list[PlayerLifeEventHistory]:
    start_day = _window_start(day, window_days)
    try:
        return (
            db.query(PlayerLifeEventHistory)
            .filter(
                PlayerLifeEventHistory.player_id == player_id,
                PlayerLifeEventHistory.day_number >= start_day,
                PlayerLifeEventHistory.day_number <= int(day),
            )
            .order_by(PlayerLifeEventHistory.day_number.asc(), PlayerLifeEventHistory.created_at.asc())
            .all()
        )
    except Exception:
        return []


def _latest_recovery_state(db: Session, player_id: UUID) -> PlayerRecoveryState | None:
    try:
        return (
            db.query(PlayerRecoveryState)
            .filter(PlayerRecoveryState.player_id == player_id)
            .first()
        )
    except Exception:
        return None


def _latest_shock_state(db: Session, player_id: UUID) -> PlayerShockState | None:
    try:
        return (
            db.query(PlayerShockState)
            .filter(PlayerShockState.player_id == player_id)
            .first()
        )
    except Exception:
        return None


def _active_region(db: Session, player: Player) -> str:
    housing = (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player.id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc(), PlayerHousingState.created_at.desc())
        .first()
    )
    region = str(getattr(housing, "region", "") or player.region or "suburban").strip().lower()
    return region or "suburban"


def _recent_borrowing_rows(db: Session, player_id: UUID, day: int, window_days: int) -> list[PlayerBorrowingHistory]:
    try:
        return (
            db.query(PlayerBorrowingHistory)
            .filter(
                PlayerBorrowingHistory.player_id == player_id,
                PlayerBorrowingHistory.day_number >= _window_start(day, window_days),
                PlayerBorrowingHistory.day_number <= int(day),
            )
            .order_by(PlayerBorrowingHistory.day_number.asc(), PlayerBorrowingHistory.created_at.asc())
            .all()
        )
    except Exception:
        return []


def _player_population_congestion_factor(db: Session, region_key: str | None = None) -> Decimal:
    """Return bounded congestion-memory additive from world activity.

    Prefer Step 34 region population state when available; fallback to a global
    player-count proxy so older tests/state remain stable.
    """
    normalized_region = str(region_key or "").strip().lower()
    if normalized_region:
        try:
            state = (
                db.query(RegionPopulationState)
                .filter(RegionPopulationState.region_key == normalized_region)
                .first()
            )
            if state is not None:
                congestion = _d(getattr(state, "congestion_score", 0))
                active_population = _d(getattr(state, "active_population_score", 0))
                # Region-local memory scales up as congestion/activity persist.
                local_factor = _clamp(
                    ((congestion - Decimal("45")) / Decimal("100")) * Decimal("0.32")
                    + ((active_population - Decimal("50")) / Decimal("100")) * Decimal("0.08"),
                    Decimal("0"),
                    Decimal("0.40"),
                )
                return _q4(local_factor)
        except Exception:
            # Region population tables may not exist in older test setups.
            pass

    player_count = int(db.query(func.count(Player.id)).scalar() or 0)
    # Fallback proxy starts near zero and climbs as the world gets busier.
    return _clamp((Decimal(str(player_count)) - Decimal("25")) / Decimal("200"), Decimal("0"), Decimal("0.40"))


def _pattern_item(
    *,
    pattern_key: str,
    category: str,
    title: str,
    short_description: str,
    direction: str,
    consecutive_days: int,
    persistence_score: Decimal,
    affected_systems: list[str],
    recommended_response: str,
    debug_meta: dict,
    future_locked_response: str | None = None,
) -> dict:
    score = _clamp(_q4(persistence_score), Decimal("0"), Decimal("100"))
    return {
        "pattern_key": str(pattern_key),
        "category": str(category),
        "title": str(title),
        "short_description": str(short_description),
        "direction": str(direction),
        "consecutive_days": int(max(1, consecutive_days)),
        "persistence_score": float(score),
        "severity": _severity_from_score(score),
        "confidence": _confidence_from_consecutive(int(max(1, consecutive_days))),
        "affected_systems": sorted(set(str(item) for item in affected_systems if item)),
        "current_status": ACTIVE_STATUS,
        "recommended_response": str(recommended_response),
        "future_locked_response": str(
            future_locked_response
            or "Long-term mobility/startup paths remain locked for now."
        ),
        "debug_meta": debug_meta,
    }


def detect_recurring_patterns(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Detect recurring/sustained patterns from recent real simulation outputs."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)

    macro_rows = _recent_macro_rows(db, day, WINDOW_DAYS)
    produce_rows = _recent_basket_rows(db, BasketType.produce, day, WINDOW_DAYS)
    housing_rows = _recent_housing_rows(db, player.id, day, WINDOW_DAYS)
    fruit_rows = _recent_business_rows(db, player.id, "fruit_shop", day, WINDOW_DAYS)
    truck_rows = _recent_business_rows(db, player.id, "food_truck", day, WINDOW_DAYS)
    settlements = _recent_settlement_rows(db, player.id, day, WINDOW_DAYS)
    daily_rows = _recent_daily_rows(db, player.id, day, WINDOW_DAYS)
    distress_rows = _recent_distress_rows(db, player.id, day, WINDOW_DAYS)
    payment_rows = _recent_payment_rows(db, player.id, day, WINDOW_DAYS)
    borrowing_rows = _recent_borrowing_rows(db, player.id, day, WINDOW_DAYS)
    personal_event_rows = _recent_personal_event_rows(db, player.id, day, WINDOW_DAYS)
    recovery_state = _latest_recovery_state(db, player.id)
    shock_state = _latest_shock_state(db, player.id)
    region_key = _active_region(db, player)
    population_factor = _player_population_congestion_factor(db, region_key=region_key)

    patterns: list[dict] = []

    inflation_values = [_d(row.inflation_rate) for row in macro_rows]
    if inflation_values:
        inflation_flags = [value >= Decimal("2.60") for value in inflation_values]
        inflation_consecutive = _consecutive_true(inflation_flags)
        if sum(1 for flag in inflation_flags if flag) >= 3:
            inflation_score = _clamp(
                (Decimal(str(inflation_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(_avg(inflation_values) - Decimal("2.60"), Decimal("0"), Decimal("2.00")) * Decimal("16"),
                Decimal("12"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="macro_inflation_persistence",
                    category="macro",
                    title="Inflation pressure keeps repeating",
                    short_description="Everyday costs have stayed elevated for several days.",
                    direction=_direction_from_values(inflation_values, Decimal("0.08")),
                    consecutive_days=max(1, inflation_consecutive),
                    persistence_score=inflation_score,
                    affected_systems=["baskets", "household_costs", "business_inputs"],
                    recommended_response="Protect cash buffer and avoid aggressive discretionary spend this week.",
                    future_locked_response="Future scale opportunities may hedge cost pressure later, but remain locked.",
                    debug_meta={
                        "avg_inflation_rate": float(_avg(inflation_values)),
                        "inflation_flags": inflation_flags,
                    },
                )
            )

    oil_values = [_d(row.oil_index) for row in macro_rows]
    if oil_values:
        oil_flags = [value >= Decimal("108") for value in oil_values]
        oil_consecutive = _consecutive_true(oil_flags)
        if sum(1 for flag in oil_flags if flag) >= 3:
            oil_score = _clamp(
                (Decimal(str(oil_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(_avg(oil_values) - Decimal("108"), Decimal("0"), Decimal("30")) * Decimal("1.2"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="macro_oil_fuel_drag",
                    category="macro",
                    title="Fuel drag has become persistent",
                    short_description="Oil pressure keeps fuel-sensitive income and business margins tight.",
                    direction=_direction_from_values(oil_values, Decimal("0.90")),
                    consecutive_days=max(1, oil_consecutive),
                    persistence_score=oil_score,
                    affected_systems=["commute_fuel", "food_truck", "rideshare"],
                    recommended_response="Prioritize fuel-efficient actions and avoid low-margin grind windows.",
                    debug_meta={
                        "avg_oil_index": float(_avg(oil_values)),
                        "oil_flags": oil_flags,
                    },
                )
            )

    confidence_values = [_d(row.consumer_confidence) for row in macro_rows]
    if confidence_values:
        confidence_flags = [value <= Decimal("48") for value in confidence_values]
        confidence_consecutive = _consecutive_true(confidence_flags)
        if sum(1 for flag in confidence_flags if flag) >= 3:
            confidence_score = _clamp(
                (Decimal(str(confidence_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(Decimal("50") - _avg(confidence_values), Decimal("0"), Decimal("20")) * Decimal("2.2"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="macro_confidence_weakness",
                    category="macro",
                    title="Consumer confidence has stayed weak",
                    short_description="Demand quality is softer than normal and stays fragile.",
                    direction=_direction_from_values(confidence_values, Decimal("0.45")),
                    consecutive_days=max(1, confidence_consecutive),
                    persistence_score=confidence_score,
                    affected_systems=["retail_demand", "business_sales", "job_security"],
                    recommended_response="Favor resilient modes and keep downside risk moderate.",
                    debug_meta={
                        "avg_consumer_confidence": float(_avg(confidence_values)),
                        "confidence_flags": confidence_flags,
                    },
                )
            )

    supply_values = [_d(row.supply_chain_stress) for row in macro_rows]
    if supply_values:
        supply_flags = [value >= Decimal("0.95") for value in supply_values]
        supply_consecutive = _consecutive_true(supply_flags)
        if sum(1 for flag in supply_flags if flag) >= 3:
            supply_score = _clamp(
                (Decimal(str(supply_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(_avg(supply_values) - Decimal("0.95"), Decimal("0"), Decimal("1.00")) * Decimal("35"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="macro_supply_chain_strain",
                    category="macro",
                    title="Supply chain strain has lasted multiple days",
                    short_description="Input flow remains tighter than normal, especially in food-linked baskets.",
                    direction=_direction_from_values(supply_values, Decimal("0.03")),
                    consecutive_days=max(1, supply_consecutive),
                    persistence_score=supply_score,
                    affected_systems=["produce_costs", "inventory_timing", "business_margins"],
                    recommended_response="Use conservative inventory timing and avoid overcommitting on weak margins.",
                    debug_meta={
                        "avg_supply_chain_stress": float(_avg(supply_values)),
                        "supply_flags": supply_flags,
                    },
                )
            )

    produce_index_values = [_d(row.price_index) for row in produce_rows]
    produce_change_values = [_d(row.daily_change_pct) for row in produce_rows]
    if produce_rows:
        produce_flags = [
            (_d(row.price_index) >= Decimal("10.70")) or (_d(row.daily_change_pct) >= Decimal("0.35"))
            for row in produce_rows
        ]
        produce_consecutive = _consecutive_true(produce_flags)
        if sum(1 for flag in produce_flags if flag) >= 3:
            produce_score = _clamp(
                (Decimal(str(produce_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(_avg(produce_index_values) - Decimal("10.70"), Decimal("0"), Decimal("3.00")) * Decimal("9.5"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="basket_produce_pressure_persistence",
                    category="macro",
                    title="Produce pressure is no longer a one-day spike",
                    short_description="Produce basket costs have stayed elevated long enough to squeeze Fruit Shop runs.",
                    direction=_direction_from_values(produce_index_values, Decimal("0.20")),
                    consecutive_days=max(1, produce_consecutive),
                    persistence_score=produce_score,
                    affected_systems=["fruit_shop", "household_produce_costs"],
                    recommended_response="Stay disciplined on markup and spoilage-sensitive inventory.",
                    debug_meta={
                        "avg_produce_index": float(_avg(produce_index_values)),
                        "avg_produce_change_pct": float(_avg(produce_change_values)),
                        "produce_flags": produce_flags,
                    },
                )
            )

    commute_pressure_values = [
        _d(row.commute_pressure) + population_factor for row in housing_rows
    ]
    commute_hour_values = [_d(row.commute_hours) for row in housing_rows]
    if housing_rows:
        congestion_flags = [
            (commute_pressure_values[idx] >= Decimal("1.00")) or (commute_hour_values[idx] >= Decimal("1.20"))
            for idx in range(len(housing_rows))
        ]
        congestion_consecutive = _consecutive_true(congestion_flags)
        if sum(1 for flag in congestion_flags if flag) >= 3:
            congestion_score = _clamp(
                (Decimal(str(congestion_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(_avg(commute_pressure_values) - Decimal("1.00"), Decimal("0"), Decimal("1.20")) * Decimal("38"),
                Decimal("15"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="commute_congestion_building",
                    category="commute",
                    title="Commute congestion has been building",
                    short_description=(
                        "Travel friction is compounding, and busier player activity is starting to show up in commute burden."
                    ),
                    direction=_direction_from_values(commute_pressure_values, Decimal("0.04")),
                    consecutive_days=max(1, congestion_consecutive),
                    persistence_score=congestion_score,
                    affected_systems=["time_budget", "stress", "job_access"],
                    recommended_response="If friction keeps rising, move or rent closer even with higher housing expense.",
                    future_locked_response="Advanced mobility/startup solutions remain locked for now.",
                    debug_meta={
                        "avg_commute_pressure_effective": float(_avg(commute_pressure_values)),
                        "avg_commute_hours": float(_avg(commute_hour_values)),
                        "population_congestion_factor": float(_q4(population_factor)),
                        "congestion_flags": congestion_flags,
                    },
                )
            )

        time_loss_flags = [value >= Decimal("1.35") for value in commute_hour_values]
        time_loss_consecutive = _consecutive_true(time_loss_flags)
        if sum(1 for flag in time_loss_flags if flag) >= 3:
            time_loss_score = _clamp(
                (Decimal(str(time_loss_consecutive)) / Decimal("6")) * Decimal("100")
                + _clamp(_avg(commute_hour_values) - Decimal("1.35"), Decimal("0"), Decimal("2.00")) * Decimal("21"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="commute_sustained_time_loss",
                    category="commute",
                    title="Commute time loss has become a repeating cost",
                    short_description="Your recent days keep sacrificing time to travel before productive actions begin.",
                    direction=_direction_from_values(commute_hour_values, Decimal("0.05")),
                    consecutive_days=max(1, time_loss_consecutive),
                    persistence_score=time_loss_score,
                    affected_systems=["time_budget", "life_balance", "productivity"],
                    recommended_response="Treat commute hours as a real budget and compare move/rent-closer tradeoffs.",
                    debug_meta={
                        "avg_commute_hours": float(_avg(commute_hour_values)),
                        "time_loss_flags": time_loss_flags,
                    },
                )
            )

    fruit_margin_flags = []
    for row in fruit_rows:
        revenue = _d(getattr(row, "gross_revenue_xgp", 0))
        total_cost = (
            _d(getattr(row, "input_cost_xgp", 0))
            + _d(getattr(row, "overhead_cost_xgp", 0))
            + _d(getattr(row, "spoilage_cost_xgp", 0))
        )
        ratio = total_cost / max(Decimal("1"), revenue)
        flag = (_d(getattr(row, "net_profit_xgp", 0)) <= Decimal("0")) or (ratio >= Decimal("0.90"))
        fruit_margin_flags.append(flag)
    fruit_consecutive = _consecutive_true(fruit_margin_flags)
    if sum(1 for flag in fruit_margin_flags if flag) >= 3:
        fruit_score = _clamp(
            (Decimal(str(fruit_consecutive)) / Decimal("6")) * Decimal("100")
            + Decimal("16"),
            Decimal("12"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="business_fruit_shop_margin_strain",
                category="business",
                title="Fruit Shop margin strain is persisting",
                short_description="Recent Fruit Shop outcomes show repeated squeeze from input cost and spoilage drag.",
                direction="falling",
                consecutive_days=max(1, fruit_consecutive),
                persistence_score=fruit_score,
                affected_systems=["fruit_shop_profit", "inventory_risk"],
                recommended_response="Use conservative pricing and inventory discipline until cost pressure cools.",
                debug_meta={
                    "rows_considered": len(fruit_rows),
                    "margin_pressure_flags": fruit_margin_flags,
                },
            )
        )

    truck_fuel_flags = []
    for row in truck_rows:
        revenue = _d(getattr(row, "gross_revenue_xgp", 0))
        fuel_ratio = _d(getattr(row, "fuel_cost_xgp", 0)) / max(Decimal("1"), revenue)
        flag = (fuel_ratio >= Decimal("0.12")) or (_d(getattr(row, "net_profit_xgp", 0)) <= Decimal("0"))
        truck_fuel_flags.append(flag)
    truck_consecutive = _consecutive_true(truck_fuel_flags)
    if sum(1 for flag in truck_fuel_flags if flag) >= 3:
        truck_score = _clamp(
            (Decimal(str(truck_consecutive)) / Decimal("6")) * Decimal("100")
            + Decimal("14"),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="business_food_truck_fuel_strain",
                category="business",
                title="Food Truck fuel and cost drag has lasted",
                short_description="Fuel-sensitive cost pressure keeps narrowing Food Truck margin room.",
                direction="rising",
                consecutive_days=max(1, truck_consecutive),
                persistence_score=truck_score,
                affected_systems=["food_truck_profit", "fuel_exposure"],
                recommended_response="Run resilient menu mode and avoid high-risk restocks until margin conditions stabilize.",
                debug_meta={
                    "rows_considered": len(truck_rows),
                    "fuel_drag_flags": truck_fuel_flags,
                },
            )
        )

    stress_values = [_d(getattr(row, "stress_after", 0)) for row in settlements]
    stress_flags = [value >= Decimal("65") for value in stress_values]
    stress_consecutive = _consecutive_true(stress_flags)
    if sum(1 for flag in stress_flags if flag) >= 3:
        stress_score = _clamp(
            (Decimal(str(stress_consecutive)) / Decimal("6")) * Decimal("100")
            + _clamp(_avg(stress_values) - Decimal("65"), Decimal("0"), Decimal("20")) * Decimal("2.0"),
            Decimal("12"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_persistent_high_stress",
                category="life",
                title="High stress pattern is repeating",
                short_description="Stress has remained elevated across consecutive days, not just one spike.",
                direction="rising",
                consecutive_days=max(1, stress_consecutive),
                persistence_score=stress_score,
                affected_systems=["productivity", "burnout_risk", "decision_quality"],
                recommended_response="Insert recovery actions before pushing another heavy sequence.",
                debug_meta={
                    "avg_stress_after": float(_avg(stress_values)),
                    "stress_flags": stress_flags,
                },
            )
        )

    overtime_values = [_d(getattr(row, "overtime_hours", 0)) for row in daily_rows]
    overtime_flags = [value >= Decimal("1.50") for value in overtime_values]
    overtime_consecutive = _consecutive_true(overtime_flags)
    if sum(1 for flag in overtime_flags if flag) >= 3:
        overtime_score = _clamp(
            (Decimal(str(overtime_consecutive)) / Decimal("6")) * Decimal("100")
            + _clamp(_avg(overtime_values) - Decimal("1.50"), Decimal("0"), Decimal("4.00")) * Decimal("12"),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_repeated_overwork",
                category="life",
                title="Overwork pattern is becoming persistent",
                short_description="Overtime has repeated enough to create ongoing stress and productivity drag risk.",
                direction="rising",
                consecutive_days=max(1, overtime_consecutive),
                persistence_score=overtime_score,
                affected_systems=["stress", "health", "next_day_output"],
                recommended_response="Trade one grind action for recovery and sleep stability.",
                debug_meta={
                    "avg_overtime_hours": float(_avg(overtime_values)),
                    "overtime_flags": overtime_flags,
                },
            )
        )

    sleep_values = [_d(getattr(row, "sleep_hours", 7)) for row in daily_rows]
    recovery_values = [_d(getattr(row, "recovery_hours", 1)) for row in daily_rows]
    low_recovery_flags = [
        (sleep_values[idx] < Decimal("6.00")) or (recovery_values[idx] < Decimal("1.00"))
        for idx in range(min(len(sleep_values), len(recovery_values)))
    ]
    low_recovery_consecutive = _consecutive_true(low_recovery_flags)
    if sum(1 for flag in low_recovery_flags if flag) >= 3:
        low_recovery_score = _clamp(
            (Decimal(str(low_recovery_consecutive)) / Decimal("6")) * Decimal("100")
            + Decimal("12"),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_low_recovery_cycle",
                category="life",
                title="Recovery deficit has lasted several days",
                short_description="Sleep and recovery windows have stayed below healthy targets repeatedly.",
                direction="falling",
                consecutive_days=max(1, low_recovery_consecutive),
                persistence_score=low_recovery_score,
                affected_systems=["stress", "health", "burnout_risk"],
                recommended_response="Protect at least one recovery block and avoid stacking overtime again tomorrow.",
                debug_meta={
                    "avg_sleep_hours": float(_avg(sleep_values, Decimal("7"))),
                    "avg_recovery_hours": float(_avg(recovery_values, Decimal("1"))),
                    "low_recovery_flags": low_recovery_flags,
                },
            )
        )

    distress_values = [_d(getattr(row, "distress_score_after", 0)) for row in distress_rows]
    distress_flags = [
        (_d(getattr(row, "distress_score_after", 0)) >= Decimal("55"))
        or bool(getattr(row, "debt_payment_missed", False))
        for row in distress_rows
    ]
    distress_consecutive = _consecutive_true(distress_flags)
    if sum(1 for flag in distress_flags if flag) >= 2:
        distress_score = _clamp(
            (Decimal(str(distress_consecutive)) / Decimal("6")) * Decimal("100")
            + _clamp(_avg(distress_values) - Decimal("50"), Decimal("0"), Decimal("40")) * Decimal("1.2"),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_debt_pressure_persistence",
                category="life",
                title="Debt pressure has stayed persistent",
                short_description="Financial pressure keeps reappearing despite day-to-day adjustments.",
                direction="rising",
                consecutive_days=max(1, distress_consecutive),
                persistence_score=distress_score,
                affected_systems=["stress", "opportunity_access", "recovery_quality"],
                recommended_response="Prioritize debt-control actions until distress trend clearly cools.",
                debug_meta={
                    "avg_distress_score": float(_avg(distress_values)),
                    "distress_flags": distress_flags,
                },
            )
        )

    payment_flags = [
        (str(getattr(row, "payment_outcome", "")).strip().lower() in {"missed", "paid_partial", "delayed"})
        or (_d(getattr(row, "obligation_load_ratio", 0)) >= Decimal("1.20"))
        or (_d(getattr(row, "liquidity_buffer_days", 0)) <= Decimal("2.00"))
        for row in payment_rows
    ]
    payment_consecutive = _consecutive_true(payment_flags)
    if sum(1 for flag in payment_flags if flag) >= 2:
        avg_payment_load = _avg([_d(getattr(row, "obligation_load_ratio", 0)) for row in payment_rows], Decimal("0"))
        avg_payment_liquidity = _avg(
            [_d(getattr(row, "liquidity_buffer_days", 0)) for row in payment_rows],
            Decimal("6"),
        )
        payment_pressure_score = _clamp(
            (Decimal(str(payment_consecutive)) / Decimal("6")) * Decimal("100")
            + _clamp(avg_payment_load - Decimal("1.00"), Decimal("0"), Decimal("3.00")) * Decimal("18")
            + _clamp(Decimal("3.50") - avg_payment_liquidity, Decimal("0"), Decimal("3.50")) * Decimal("10"),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_payment_survival_pressure",
                category="life",
                title="Payment survival pressure is repeating",
                short_description="Required obligations are repeatedly squeezing liquidity and increasing delinquency risk.",
                direction=(
                    "rising"
                    if avg_payment_load >= Decimal("1.15") or avg_payment_liquidity <= Decimal("2.50")
                    else "stable"
                ),
                consecutive_days=max(1, payment_consecutive),
                persistence_score=payment_pressure_score,
                affected_systems=["cash_buffer", "credit_health", "planning_flexibility"],
                recommended_response="Prioritize required obligations and buffer-building before growth pushes.",
                debug_meta={
                    "rows_considered": len(payment_rows),
                    "payment_flags": payment_flags,
                    "avg_obligation_load_ratio": float(_q4(avg_payment_load)),
                    "avg_liquidity_buffer_days": float(_q4(avg_payment_liquidity)),
                },
            )
        )

    borrow_accept_flags = [str(getattr(row, "event_type", "")).strip().lower() == "offer_accepted" for row in borrowing_rows]
    borrow_accept_consecutive = _consecutive_true(borrow_accept_flags)
    borrow_high_cost_flags = [
        (
            str(((_parse_json(getattr(row, "summary_json", None), {}) or {}).get("risk_label", "")).strip().lower())
            in {"high", "very_high"}
        )
        for row in borrowing_rows
    ]
    if sum(1 for flag in borrow_accept_flags if flag) >= 2:
        borrow_score = _clamp(
            (Decimal(str(borrow_accept_consecutive)) / Decimal("6")) * Decimal("100")
            + (Decimal(str(sum(1 for flag in borrow_high_cost_flags if flag))) * Decimal("8.0")),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_emergency_borrowing_dependence",
                category="life",
                title="Emergency borrowing dependence is emerging",
                short_description="Recent bridge usage is repeating and may shift pressure into future obligation cycles.",
                direction="rising",
                consecutive_days=max(1, borrow_accept_consecutive),
                persistence_score=borrow_score,
                affected_systems=["future_obligations", "credit_health", "liquidity_flexibility"],
                recommended_response="Favor smaller bridges and rebuild cash buffer before taking another high-cost offer.",
                future_locked_response="Future refinance/restructure paths remain locked for now.",
                debug_meta={
                    "borrowing_rows_considered": len(borrowing_rows),
                    "offer_accept_flags": borrow_accept_flags,
                    "high_cost_offer_flags": borrow_high_cost_flags,
                },
            )
        )

    negative_event_flags = [
        str(getattr(row, "event_family", "")).strip().lower()
        in {"financial_shock", "health_stress_shock", "work_disruption"}
        for row in personal_event_rows
    ]
    negative_event_consecutive = _consecutive_true(negative_event_flags)
    if sum(1 for flag in negative_event_flags if flag) >= 3:
        negative_event_score = _clamp(
            (Decimal(str(negative_event_consecutive)) / Decimal("6")) * Decimal("100") + Decimal("12"),
            Decimal("10"),
            Decimal("100"),
        )
        patterns.append(
            _pattern_item(
                pattern_key="life_personal_shock_cycle",
                category="life",
                title="Personal disruption days are repeating",
                short_description="Recent life events have repeatedly added cash, stress, or time pressure.",
                direction="rising",
                consecutive_days=max(1, negative_event_consecutive),
                persistence_score=negative_event_score,
                affected_systems=["cash_buffer", "stress", "time_budget", "work_output"],
                recommended_response="Prioritize stability actions until disruption frequency cools.",
                debug_meta={
                    "event_rows_considered": len(personal_event_rows),
                    "negative_event_flags": negative_event_flags,
                },
            )
        )

    if recovery_state is not None and int(getattr(recovery_state, "recovery_days_remaining", 0) or 0) >= 2:
        recovery_drag = _clamp(
            _d(getattr(recovery_state, "temporary_stress_modifier", 0)) * Decimal("5.0")
            + _clamp(-_d(getattr(recovery_state, "temporary_income_modifier", 0)), Decimal("0"), Decimal("1")) * Decimal("60")
            + _clamp(_d(getattr(recovery_state, "temporary_time_modifier", 0)), Decimal("0"), Decimal("3")) * Decimal("15"),
            Decimal("0"),
            Decimal("100"),
        )
        if recovery_drag >= Decimal("20"):
            patterns.append(
                _pattern_item(
                    pattern_key="life_recovery_window_active",
                    category="life",
                    title="Recovery window is still affecting daily output",
                    short_description="Recent shocks are still carrying modifiers into current-day performance.",
                    direction="stable",
                    consecutive_days=max(1, int(getattr(recovery_state, "recovery_days_remaining", 0) or 0)),
                    persistence_score=_clamp(recovery_drag, Decimal("10"), Decimal("85")),
                    affected_systems=["income_quality", "business_execution", "time_flexibility"],
                    recommended_response="Use lower-volatility actions until recovery modifiers fade.",
                    debug_meta={
                        "recovery_days_remaining": int(getattr(recovery_state, "recovery_days_remaining", 0) or 0),
                        "temporary_stress_modifier": float(_q4(_d(getattr(recovery_state, "temporary_stress_modifier", 0)))),
                        "temporary_income_modifier": float(_q4(_d(getattr(recovery_state, "temporary_income_modifier", 0)))),
                        "temporary_business_modifier": float(_q4(_d(getattr(recovery_state, "temporary_business_modifier", 0)))),
                        "temporary_time_modifier": float(_q4(_d(getattr(recovery_state, "temporary_time_modifier", 0)))),
                    },
                )
            )

    if shock_state is not None:
        shock_risk_score = _d(getattr(shock_state, "shock_risk_score", 0))
        if shock_risk_score >= Decimal("58"):
            fragility_score = _clamp(
                (shock_risk_score * Decimal("0.72"))
                + _d(getattr(shock_state, "financial_fragility_score", 0)) * Decimal("0.14"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key="life_resilience_fragility_pressure",
                    category="life",
                    title="Resilience remains fragile",
                    short_description="Current risk profile suggests a higher chance of disruption without cushion-building.",
                    direction=str(getattr(shock_state, "recent_pressure_direction", "stable") or "stable"),
                    consecutive_days=max(1, int(getattr(shock_state, "recent_negative_streak", 0) or 1)),
                    persistence_score=fragility_score,
                    affected_systems=["shock_exposure", "planning_flexibility", "recovery_capacity"],
                    recommended_response="Rebuild cash buffer and avoid stacking high-strain choices for several days.",
                    debug_meta={
                        "shock_risk_score": float(_q4(shock_risk_score)),
                        "financial_fragility_score": float(
                            _q4(_d(getattr(shock_state, "financial_fragility_score", 0)))
                        ),
                        "health_fragility_score": float(
                            _q4(_d(getattr(shock_state, "health_fragility_score", 0)))
                        ),
                        "work_disruption_risk_score": float(
                            _q4(_d(getattr(shock_state, "work_disruption_risk_score", 0)))
                        ),
                        "recovery_capacity_score": float(
                            _q4(_d(getattr(shock_state, "recovery_capacity_score", 0)))
                        ),
                    },
                )
            )

    if housing_rows:
        opp_values = [_d(getattr(row, "region_opportunity_modifier", 0)) for row in housing_rows]
        region_stress_values = [_d(getattr(row, "region_stress_delta", 0)) for row in housing_rows]
        region_flags = [
            (opp_values[idx] >= Decimal("0.04")) and (region_stress_values[idx] >= Decimal("0.70"))
            for idx in range(min(len(opp_values), len(region_stress_values)))
        ]
        region_consecutive = _consecutive_true(region_flags)
        if sum(1 for flag in region_flags if flag) >= 3:
            region_score = _clamp(
                (Decimal(str(region_consecutive)) / Decimal("6")) * Decimal("100")
                + Decimal("10"),
                Decimal("10"),
                Decimal("100"),
            )
            patterns.append(
                _pattern_item(
                    pattern_key=f"region_{region_key}_high_opportunity_high_friction",
                    category="region",
                    title=f"{region_key.title()} is trending high-opportunity, high-friction",
                    short_description="Opportunity access has stayed strong while stress and congestion pressures remain elevated.",
                    direction="rising",
                    consecutive_days=max(1, region_consecutive),
                    persistence_score=region_score,
                    affected_systems=["region_identity", "commute", "work_output"],
                    recommended_response="If friction is compounding, compare move/rent-closer costs against lost time.",
                    future_locked_response="Future mobility and transport venture paths remain locked.",
                    debug_meta={
                        "avg_region_opportunity_modifier": float(_avg(opp_values)),
                        "avg_region_stress_delta": float(_avg(region_stress_values)),
                        "region_flags": region_flags,
                    },
                )
            )

    patterns = sorted(
        patterns,
        key=lambda item: (
            -float(item["persistence_score"]),
            str(item["category"]),
            str(item["pattern_key"]),
        ),
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": patterns,
        "debug_meta": {
            "window_days": WINDOW_DAYS,
            "region_key": region_key,
            "population_congestion_factor": float(_q4(population_factor)),
            "rows_used": {
                "macro": len(macro_rows),
                "produce": len(produce_rows),
                "housing": len(housing_rows),
                "fruit_shop": len(fruit_rows),
                "food_truck": len(truck_rows),
                "settlement": len(settlements),
                "daily_state": len(daily_rows),
                "distress": len(distress_rows),
                "payment_rows": len(payment_rows),
                "borrowing_rows": len(borrowing_rows),
                "personal_events": len(personal_event_rows),
            },
        },
    }


def _persist_pattern_rows(
    db: Session,
    player: Player,
    day: int,
    as_of_date: date,
    patterns: list[dict],
) -> dict:
    upserted = 0
    created = 0
    for item in patterns:
        key = str(item.get("pattern_key", "")).strip()
        if not key:
            continue
        existing = (
            db.query(PlayerWorldPatternHistory)
            .filter(
                PlayerWorldPatternHistory.player_id == player.id,
                PlayerWorldPatternHistory.pattern_key == key,
                PlayerWorldPatternHistory.status.in_([ACTIVE_STATUS, FADING_STATUS]),
            )
            .order_by(PlayerWorldPatternHistory.first_seen_on_day.desc(), PlayerWorldPatternHistory.updated_at.desc())
            .first()
        )
        if existing is None or int(day) - int(existing.last_seen_on_day or 0) > 2:
            row = PlayerWorldPatternHistory(
                player_id=player.id,
                pattern_key=key,
                category=str(item.get("category", "macro")),
                title=str(item.get("title", key.replace("_", " ").title())),
                first_seen_on_day=int(day),
                first_seen_on_date=as_of_date,
                last_seen_on_day=int(day),
                last_seen_on_date=as_of_date,
                consecutive_days=int(item.get("consecutive_days", 1) or 1),
                persistence_score=_q4(_d(item.get("persistence_score", 0))),
                severity=str(item.get("severity", "low")),
                direction=str(item.get("direction", "stable")),
                status=ACTIVE_STATUS,
                summary_json=_dump_json(
                    {
                        "short_description": item.get("short_description"),
                        "affected_systems": item.get("affected_systems", []),
                        "recommended_response": item.get("recommended_response"),
                        "future_locked_response": item.get("future_locked_response"),
                        "current_status": item.get("current_status", ACTIVE_STATUS),
                    }
                ),
                debug_json=_dump_json(item.get("debug_meta", {})),
                last_updated_on=int(day),
            )
            db.add(row)
            created += 1
            upserted += 1
            continue

        delta_days = int(day) - int(existing.last_seen_on_day or 0)
        if delta_days > 0:
            existing.consecutive_days = int(existing.consecutive_days or 0) + delta_days
        existing.last_seen_on_day = int(day)
        existing.last_seen_on_date = as_of_date
        existing.category = str(item.get("category", existing.category))
        existing.title = str(item.get("title", existing.title))
        existing.persistence_score = _q4(_d(item.get("persistence_score", existing.persistence_score)))
        existing.severity = str(item.get("severity", existing.severity))
        existing.direction = str(item.get("direction", existing.direction))
        existing.status = ACTIVE_STATUS
        existing.summary_json = _dump_json(
            {
                "short_description": item.get("short_description"),
                "affected_systems": item.get("affected_systems", []),
                "recommended_response": item.get("recommended_response"),
                "future_locked_response": item.get("future_locked_response"),
                "current_status": item.get("current_status", ACTIVE_STATUS),
            }
        )
        existing.debug_json = _dump_json(item.get("debug_meta", {}))
        existing.last_updated_on = int(day)
        upserted += 1

    db.flush()
    return {
        "upserted": int(upserted),
        "created": int(created),
    }


def decay_world_memory(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    active_pattern_keys: set[str] | None = None,
) -> dict:
    """Decay stale pattern rows so old pressure fades instead of dominating forever."""
    player = _resolve_player(db, player_id)
    day, _ = _resolve_day(db, player, as_of_date)
    active_keys = set(active_pattern_keys or set())

    rows = (
        db.query(PlayerWorldPatternHistory)
        .filter(
            PlayerWorldPatternHistory.player_id == player.id,
            PlayerWorldPatternHistory.status.in_([ACTIVE_STATUS, FADING_STATUS]),
        )
        .order_by(PlayerWorldPatternHistory.last_seen_on_day.asc(), PlayerWorldPatternHistory.updated_at.asc())
        .all()
    )

    decayed = 0
    resolved = 0
    for row in rows:
        key = str(row.pattern_key or "")
        if key in active_keys:
            continue
        days_since_seen = int(day) - int(row.last_seen_on_day or 0)
        if days_since_seen <= 0:
            continue

        old_score = _q4(_d(row.persistence_score))
        decay_factor = Decimal("0.86") ** Decimal(str(min(days_since_seen, 10)))
        new_score = _clamp(old_score * decay_factor, Decimal("0"), Decimal("100"))

        if days_since_seen >= 7 or new_score < Decimal("15"):
            new_status = RESOLVED_STATUS
            resolved += 1
        elif days_since_seen >= 3 or new_score < Decimal("45"):
            new_status = FADING_STATUS
        else:
            new_status = ACTIVE_STATUS

        row.persistence_score = _q4(new_score)
        row.status = new_status
        row.severity = _severity_from_score(new_score)
        row.last_updated_on = int(day)
        decayed += 1

    db.flush()
    return {
        "decayed_rows": int(decayed),
        "resolved_rows": int(resolved),
        "active_pattern_keys": sorted(active_keys),
    }


def build_local_pressure_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Summarize local pressure chain around commute, cost, opportunity, and business climate."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    region_key = _active_region(db, player)
    housing_rows = _recent_housing_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    settlement_rows = _recent_settlement_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    business_rows = _recent_business_rows(db, player.id, "food_truck", day, SHORT_WINDOW_DAYS) + _recent_business_rows(
        db, player.id, "fruit_shop", day, SHORT_WINDOW_DAYS
    )
    population_factor = _player_population_congestion_factor(db, region_key=region_key)

    commute_values = [_d(row.commute_hours) for row in housing_rows]
    commute_pressure_values = [_d(row.commute_pressure) + population_factor for row in housing_rows]
    region_opp_values = [_d(getattr(row, "region_opportunity_modifier", 0)) for row in housing_rows]
    housing_cost_values = [
        _d(getattr(row, "housing_cost_xgp", 0)) + _d(getattr(row, "utilities_cost_xgp", 0))
        for row in housing_rows
    ]
    net_values = [_d(getattr(row, "income_xgp", 0)) - _d(getattr(row, "expenses_xgp", 0)) for row in settlement_rows]
    business_net_values = [_d(getattr(row, "net_profit_xgp", 0)) for row in business_rows]

    congestion_score = _clamp(
        _avg(commute_pressure_values, Decimal("0.6")) * Decimal("55")
        + _avg(commute_values, Decimal("0.8")) * Decimal("14"),
        Decimal("0"),
        Decimal("100"),
    )
    opportunity_score = _clamp((_avg(region_opp_values, Decimal("0")) + Decimal("0.15")) * Decimal("260"), Decimal("0"), Decimal("100"))
    cost_pressure_score = _clamp(
        _avg(housing_cost_values, Decimal("18")) * Decimal("2.3")
        + _clamp(Decimal("0") - _avg(net_values, Decimal("0")), Decimal("0"), Decimal("120")) * Decimal("0.35"),
        Decimal("0"),
        Decimal("100"),
    )
    business_climate_score = _clamp(
        Decimal("50") + _avg(business_net_values, Decimal("0")) * Decimal("1.2"),
        Decimal("0"),
        Decimal("100"),
    )

    local_pressure_score = _clamp(
        congestion_score * Decimal("0.34")
        + cost_pressure_score * Decimal("0.33")
        + (Decimal("100") - business_climate_score) * Decimal("0.20")
        + (Decimal("100") - opportunity_score) * Decimal("0.13"),
        Decimal("0"),
        Decimal("100"),
    )

    congestion_label = _pressure_level_from_score(congestion_score)
    opportunity_label = _pressure_level_from_score(opportunity_score)
    cost_label = _pressure_level_from_score(cost_pressure_score)
    if business_climate_score >= Decimal("60"):
        business_climate_label = "supportive"
    elif business_climate_score >= Decimal("40"):
        business_climate_label = "mixed"
    else:
        business_climate_label = "pressured"

    if congestion_label == "high":
        short_summary = (
            "Congestion has been building in your region. Time loss and stress friction are no longer one-day noise."
        )
    elif cost_label == "high":
        short_summary = "Local living cost pressure is rising faster than comfort, so cash discipline matters."
    elif business_climate_label == "pressured":
        short_summary = "Neighborhood business climate is less forgiving; margin discipline matters right now."
    else:
        short_summary = "Local pressure is manageable, but commute and cost tradeoffs still need weekly attention."

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "region_key": region_key,
        "local_pressure_level": _pressure_level_from_score(local_pressure_score),
        "congestion_label": congestion_label,
        "opportunity_label": opportunity_label,
        "cost_pressure_label": cost_label,
        "business_climate_label": business_climate_label,
        "short_summary": short_summary,
        "practical_response_options": list(PRACTICAL_COMMUTE_RESPONSES),
        "future_locked_solution_teasers": list(FUTURE_LOCKED_SOLUTIONS),
        "debug_meta": {
            "population_congestion_factor": float(_q4(population_factor)),
            "avg_commute_hours": float(_avg(commute_values, Decimal("0.8"))),
            "avg_commute_pressure_effective": float(_avg(commute_pressure_values, Decimal("0.6"))),
            "avg_housing_plus_utilities": float(_avg(housing_cost_values, Decimal("18"))),
            "avg_region_opportunity_modifier": float(_avg(region_opp_values, Decimal("0"))),
            "avg_business_net": float(_avg(business_net_values, Decimal("0"))),
            "local_pressure_score": float(_q4(local_pressure_score)),
            "current_practical_solutions": ["stay", "move", "rent_closer"],
        },
    }


def build_player_pattern_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Summarize recent player behavior patterns using life, debt, and action outcomes."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    settlements = _recent_settlement_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    daily_rows = _recent_daily_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    distress_rows = _recent_distress_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    payment_rows = _recent_payment_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    borrowing_rows = _recent_borrowing_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    personal_event_rows = _recent_personal_event_rows(db, player.id, day, SHORT_WINDOW_DAYS)
    recovery_state = _latest_recovery_state(db, player.id)
    shock_state = _latest_shock_state(db, player.id)

    overwork_days = sum(1 for row in daily_rows if _d(getattr(row, "overtime_hours", 0)) >= Decimal("1.50"))
    low_sleep_days = sum(1 for row in daily_rows if _d(getattr(row, "sleep_hours", 7)) < Decimal("6.00"))
    recovery_days = sum(1 for row in daily_rows if _d(getattr(row, "recovery_hours", 0)) >= Decimal("1.25"))
    high_stress_days = sum(1 for row in settlements if _d(getattr(row, "stress_after", 0)) >= Decimal("65"))
    positive_net_days = sum(
        1
        for row in settlements
        if (_d(getattr(row, "income_xgp", 0)) - _d(getattr(row, "expenses_xgp", 0))) > Decimal("0")
    )
    high_distress_days = sum(1 for row in distress_rows if _d(getattr(row, "distress_score_after", 0)) >= Decimal("55"))
    payment_stress_days = sum(
        1
        for row in payment_rows
        if str(getattr(row, "payment_outcome", "")).strip().lower() in {"missed", "paid_partial", "delayed"}
        or _d(getattr(row, "obligation_load_ratio", 0)) >= Decimal("1.20")
        or _d(getattr(row, "liquidity_buffer_days", 0)) <= Decimal("2.00")
    )
    borrow_accept_days = sum(
        1
        for row in borrowing_rows
        if str(getattr(row, "event_type", "")).strip().lower() == "offer_accepted"
    )
    borrow_high_cost_days = sum(
        1
        for row in borrowing_rows
        if str((_parse_json(getattr(row, "summary_json", None), {}) or {}).get("risk_label", "")).strip().lower()
        in {"high", "very_high"}
    )
    negative_event_days = sum(
        1
        for row in personal_event_rows
        if str(getattr(row, "event_family", "")).strip().lower()
        in {"financial_shock", "health_stress_shock", "work_disruption"}
    )
    recovery_event_days = sum(
        1
        for row in personal_event_rows
        if str(getattr(row, "event_family", "")).strip().lower() == "recovery_support"
    )

    risk_patterns: list[str] = []
    improving_patterns: list[str] = []
    supporting_patterns: list[str] = []

    if overwork_days >= 3:
        risk_patterns.append("Repeated overwork pattern")
    if low_sleep_days >= 3:
        risk_patterns.append("Sleep deficit pattern")
    if high_stress_days >= 3:
        risk_patterns.append("Persistent high stress cycle")
    if high_distress_days >= 2:
        risk_patterns.append("Debt pressure remains elevated")
    if payment_stress_days >= 2:
        risk_patterns.append("Payment survival pressure is repeating")
    if borrow_accept_days >= 2:
        risk_patterns.append("Emergency borrowing dependence is rising")
    if borrow_high_cost_days >= 2:
        risk_patterns.append("High-cost bridge usage is compounding future burden")
    if negative_event_days >= 3:
        risk_patterns.append("Frequent personal disruption days")
    if shock_state is not None and _d(getattr(shock_state, "shock_risk_score", 0)) >= Decimal("60"):
        risk_patterns.append("Low resilience / high shock-risk pattern")
    if recovery_state is not None and int(getattr(recovery_state, "recovery_days_remaining", 0) or 0) >= 3:
        risk_patterns.append("Recovery drag still active")

    if recovery_days >= 3:
        improving_patterns.append("Recovery discipline improving")
    if positive_net_days >= 4:
        improving_patterns.append("Cash-flow consistency improving")
    if recovery_event_days >= 2:
        improving_patterns.append("Support/recovery events improving stability")
    if borrow_accept_days == 0 and payment_stress_days <= 1:
        improving_patterns.append("No emergency borrowing dependence this week")
    if shock_state is not None and str(getattr(shock_state, "recent_pressure_direction", "stable")) == "improving":
        improving_patterns.append("Personal resilience trend is improving")

    if positive_net_days >= 2:
        supporting_patterns.append("Income actions still producing net support")
    if recovery_days >= 2:
        supporting_patterns.append("Some recovery windows are preserved")
    if high_distress_days <= 1:
        supporting_patterns.append("Distress has not fully dominated this week")
    if payment_stress_days <= 1:
        supporting_patterns.append("Required obligation pressure has remained mostly contained")
    if borrow_accept_days <= 1:
        supporting_patterns.append("Emergency borrowing remains limited")
    if negative_event_days <= 1:
        supporting_patterns.append("Life disruption frequency has stayed bounded")

    if risk_patterns:
        dominant = risk_patterns[0]
        summary = (
            f"Recent behavior shows '{dominant.lower()}'. This is becoming a repeating pressure, not random variance."
        )
        suggested_correction = "Reduce one high-pressure action and protect recovery/sleep for the next 2 days."
    elif improving_patterns:
        dominant = improving_patterns[0]
        summary = f"Your recent pattern is improving: {dominant.lower()}."
        suggested_correction = "Keep this rhythm for 3-5 days to convert momentum into stable gains."
    else:
        dominant = "Mixed but stable pattern"
        summary = "Your recent behavior is mixed but not yet locked into a harmful cycle."
        suggested_correction = "Choose one clear weekly focus so progress compounds."

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "dominant_player_pattern": dominant,
        "supporting_patterns": supporting_patterns[:3],
        "risk_patterns": risk_patterns[:3],
        "improving_patterns": improving_patterns[:3],
        "summary": summary,
        "suggested_correction": suggested_correction,
        "debug_meta": {
            "overwork_days": int(overwork_days),
            "low_sleep_days": int(low_sleep_days),
            "recovery_days": int(recovery_days),
            "high_stress_days": int(high_stress_days),
            "positive_net_days": int(positive_net_days),
            "high_distress_days": int(high_distress_days),
            "payment_stress_days": int(payment_stress_days),
            "borrowing_offer_accept_days": int(borrow_accept_days),
            "borrowing_high_cost_days": int(borrow_high_cost_days),
            "negative_event_days": int(negative_event_days),
            "recovery_event_days": int(recovery_event_days),
            "shock_risk_score": float(
                _q4(_d(getattr(shock_state, "shock_risk_score", 0)))
            ) if shock_state is not None else 0.0,
            "recovery_days_remaining": int(getattr(recovery_state, "recovery_days_remaining", 0) or 0)
            if recovery_state is not None
            else 0,
        },
    }


def build_region_memory_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Describe region identity drift over recent days so regions feel historically alive."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    region_key = _active_region(db, player)
    housing_rows = _recent_housing_rows(db, player.id, day, WINDOW_DAYS)
    business_rows = (
        _recent_business_rows(db, player.id, "fruit_shop", day, WINDOW_DAYS)
        + _recent_business_rows(db, player.id, "food_truck", day, WINDOW_DAYS)
    )
    population_factor = _player_population_congestion_factor(db, region_key=region_key)

    commute_values = [_d(getattr(row, "commute_hours", 0)) for row in housing_rows]
    pressure_values = [_d(getattr(row, "commute_pressure", 0)) + population_factor for row in housing_rows]
    stress_values = [_d(getattr(row, "region_stress_delta", 0)) for row in housing_rows]
    opp_values = [_d(getattr(row, "region_opportunity_modifier", 0)) for row in housing_rows]
    housing_cost_values = [
        _d(getattr(row, "housing_cost_xgp", 0)) + _d(getattr(row, "utilities_cost_xgp", 0))
        for row in housing_rows
    ]
    business_net_values = [_d(getattr(row, "net_profit_xgp", 0)) for row in business_rows]

    avg_pressure = _avg(pressure_values, Decimal("0.6"))
    avg_stress = _avg(stress_values, Decimal("0"))
    avg_opp = _avg(opp_values, Decimal("0"))
    avg_commute = _avg(commute_values, Decimal("0.8"))
    avg_cost = _avg(housing_cost_values, Decimal("18"))
    avg_business_net = _avg(business_net_values, Decimal("0"))

    dominant_pressures: list[str] = []
    dominant_opportunities: list[str] = []

    if avg_pressure >= Decimal("1.00") or avg_commute >= Decimal("1.25"):
        dominant_pressures.append("Commute congestion")
    if avg_cost >= Decimal("30"):
        dominant_pressures.append("Housing and utility burden")
    if avg_stress >= Decimal("0.8"):
        dominant_pressures.append("Background region stress load")
    if avg_business_net < Decimal("0"):
        dominant_pressures.append("Business climate squeeze")

    if avg_opp >= Decimal("0.04"):
        dominant_opportunities.append("Stronger opportunity access")
    if avg_business_net > Decimal("4"):
        dominant_opportunities.append("Supportive local demand windows")
    if region_key == "downtown":
        dominant_opportunities.append("Dense network exposure")
    if region_key == "suburban" and avg_stress <= Decimal("0.5"):
        dominant_opportunities.append("Lower baseline stress profile")

    if avg_opp >= Decimal("0.04") and (avg_pressure >= Decimal("1.00") or avg_stress >= Decimal("0.8")):
        region_identity_trend = "high_opportunity_high_friction"
    elif avg_opp <= Decimal("-0.03") and avg_cost <= Decimal("26"):
        region_identity_trend = "lower_cost_slower_access"
    elif avg_pressure >= Decimal("1.00"):
        region_identity_trend = "congestion_dominant"
    else:
        region_identity_trend = "mixed_transition"

    if region_identity_trend == "high_opportunity_high_friction":
        recent_change_summary = (
            f"{region_key.title()} has stayed opportunity-rich, but congestion and stress friction keep building."
        )
    elif region_identity_trend == "lower_cost_slower_access":
        recent_change_summary = (
            f"{region_key.title()} remains lower-cost, but access speed and opportunity density feel weaker."
        )
    elif region_identity_trend == "congestion_dominant":
        recent_change_summary = (
            f"{region_key.title()} has been defined by commute pressure more than opportunity gains lately."
        )
    else:
        recent_change_summary = (
            f"{region_key.title()} is in a mixed phase with no single pressure fully dominating yet."
        )

    if region_identity_trend == "high_opportunity_high_friction":
        current_tradeoff_identity = "Higher upside access, higher commute and stress tax."
    elif region_identity_trend == "lower_cost_slower_access":
        current_tradeoff_identity = "Lower daily cost, but slower access and weaker opportunity density."
    elif region_identity_trend == "congestion_dominant":
        current_tradeoff_identity = "Commute and time loss are the key tax right now."
    else:
        current_tradeoff_identity = "Balanced region profile with moderate tradeoffs."

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "region_key": region_key,
        "region_identity_trend": region_identity_trend,
        "dominant_region_pressures": dominant_pressures[:4],
        "dominant_region_opportunities": dominant_opportunities[:4],
        "recent_change_summary": recent_change_summary,
        "current_tradeoff_identity": current_tradeoff_identity,
        "debug_meta": {
            "avg_commute_pressure_effective": float(avg_pressure),
            "avg_commute_hours": float(avg_commute),
            "avg_region_stress_delta": float(avg_stress),
            "avg_region_opportunity_modifier": float(avg_opp),
            "avg_housing_plus_utilities": float(avg_cost),
            "avg_business_net": float(avg_business_net),
            "population_congestion_factor": float(_q4(population_factor)),
        },
    }


def build_world_narrative(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Convert active/fading patterns into a compact continuity narrative."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    patterns_payload = detect_recurring_patterns(db=db, player_id=player.id, as_of_date=resolved_date)
    local_pressure = build_local_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    player_patterns = build_player_pattern_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    region_memory = build_region_memory_summary(db=db, player_id=player.id, as_of_date=resolved_date)

    active_items = list(patterns_payload.get("items", []))
    active_titles = [str(item.get("title", "")) for item in active_items[:3] if item.get("title")]

    fading_rows = (
        db.query(PlayerWorldPatternHistory)
        .filter(
            PlayerWorldPatternHistory.player_id == player.id,
            PlayerWorldPatternHistory.status == FADING_STATUS,
        )
        .order_by(PlayerWorldPatternHistory.persistence_score.desc(), PlayerWorldPatternHistory.updated_at.desc())
        .limit(3)
        .all()
    )
    fading_titles = [str(row.title) for row in fading_rows if row.title]

    top = active_items[0] if active_items else None
    if top is None:
        headline = "World pressure is mixed, with no dominant persistence yet."
    else:
        category = str(top.get("category", "macro"))
        if category == "commute":
            headline = "Commute friction is persisting, not just daily noise."
        elif category == "business":
            headline = "Business pressure has become a repeating pattern."
        elif category == "life":
            headline = "Life pressure patterns are carrying across days."
        elif category == "region":
            headline = "Your region is developing a clear pressure identity."
        else:
            headline = "Macro pressure is carrying forward across multiple days."

    persisting_text = active_titles[0] if active_titles else "No high-confidence persistent pattern yet."
    body = (
        f"{persisting_text} {local_pressure.get('short_summary', '')} "
        f"{region_memory.get('recent_change_summary', '')}"
    ).strip()

    watch_items: list[str] = []
    if active_items:
        first = active_items[0]
        watch_items.append(str(first.get("recommended_response", "")))
    if player_patterns.get("suggested_correction"):
        watch_items.append(str(player_patterns["suggested_correction"]))
    if not watch_items:
        watch_items.append("Monitor stress, commute burden, and margin pressure together this week.")

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "headline": headline,
        "body": body,
        "key_active_patterns": active_titles[:3],
        "what_is_persisting": active_titles[:3],
        "what_is_fading": fading_titles[:3],
        "what_to_watch_next": watch_items[:3],
        "recommended_short_response": PRACTICAL_COMMUTE_RESPONSES[1],
        "future_locked_long_response": (
            "Long-term mobility and transport venture paths may matter later, but remain locked now."
        ),
        "debug_meta": {
            "active_pattern_count": len(active_items),
            "fading_pattern_count": len(fading_titles),
            "local_pressure_level": local_pressure.get("local_pressure_level"),
            "dominant_player_pattern": player_patterns.get("dominant_player_pattern"),
            "region_identity_trend": region_memory.get("region_identity_trend"),
        },
    }


def _pressure_scores_from_patterns(patterns: list[dict]) -> dict[str, Decimal]:
    macro = [Decimal(str(item.get("persistence_score", 0))) for item in patterns if item.get("category") == "macro"]
    commute = [Decimal(str(item.get("persistence_score", 0))) for item in patterns if item.get("category") == "commute"]
    business = [Decimal(str(item.get("persistence_score", 0))) for item in patterns if item.get("category") == "business"]
    life = [Decimal(str(item.get("persistence_score", 0))) for item in patterns if item.get("category") == "life"]
    region = [Decimal(str(item.get("persistence_score", 0))) for item in patterns if item.get("category") == "region"]

    # Opportunity score is inversely tied to pressure but can be lifted by region opportunity patterns.
    base_opportunity = Decimal("55")
    if region:
        base_opportunity += _avg(region, Decimal("0")) * Decimal("0.12")
    base_opportunity -= _avg(commute, Decimal("0")) * Decimal("0.20")
    base_opportunity -= _avg(life, Decimal("0")) * Decimal("0.16")

    return {
        "macro": _q4(_avg(macro, Decimal("0"))),
        "commute": _q4(_avg(commute, Decimal("0"))),
        "business": _q4(_avg(business, Decimal("0"))),
        "life": _q4(_avg(life, Decimal("0"))),
        "opportunity": _q4(_clamp(base_opportunity, Decimal("0"), Decimal("100"))),
    }


def _serialize_memory_state(state: PlayerWorldMemoryState) -> dict:
    dominant_patterns = _parse_json(state.dominant_patterns_json, []) or []
    narrative_state = _parse_json(state.narrative_state_json, {}) or {}
    local_pressure = _parse_json(state.local_pressure_json, {}) or {}
    player_pattern = _parse_json(state.player_pattern_json, {}) or {}
    region_memory = _parse_json(state.region_memory_json, {}) or {}

    return {
        "player_id": str(state.player_id),
        "as_of_date": state.last_updated_date.isoformat() if state.last_updated_date else None,
        "region_key": str(state.region_key or "suburban"),
        "memory_window_start": state.memory_window_start.isoformat() if state.memory_window_start else None,
        "memory_window_end": state.memory_window_end.isoformat() if state.memory_window_end else None,
        "macro_pressure_score": float(_q4(_d(state.macro_pressure_score))),
        "commute_pressure_score": float(_q4(_d(state.commute_pressure_score))),
        "business_pressure_score": float(_q4(_d(state.business_pressure_score))),
        "life_pressure_score": float(_q4(_d(state.life_pressure_score))),
        "opportunity_score": float(_q4(_d(state.opportunity_score))),
        "dominant_patterns": dominant_patterns,
        "narrative_state": narrative_state,
        "local_pressure_summary": local_pressure,
        "player_pattern_summary": player_pattern,
        "region_memory_summary": region_memory,
        "debug_meta": {
            "memory_window_start_day": int(state.memory_window_start_day or 1),
            "memory_window_end_day": int(state.memory_window_end_day or 1),
            "last_updated_on": int(state.last_updated_on or 0),
        },
    }


def update_world_memory(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Update rolling world memory snapshot for one player/day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)

    patterns_payload = detect_recurring_patterns(db=db, player_id=player.id, as_of_date=resolved_date)
    patterns = list(patterns_payload.get("items", []))
    active_keys = {str(item.get("pattern_key", "")) for item in patterns if item.get("pattern_key")}

    decay_info = decay_world_memory(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        active_pattern_keys=active_keys,
    )
    persist_info = _persist_pattern_rows(
        db=db,
        player=player,
        day=day,
        as_of_date=resolved_date,
        patterns=patterns,
    )

    local_pressure = build_local_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    player_patterns = build_player_pattern_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    region_memory = build_region_memory_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    narrative = build_world_narrative(db=db, player_id=player.id, as_of_date=resolved_date)

    scores = _pressure_scores_from_patterns(patterns)

    state = (
        db.query(PlayerWorldMemoryState)
        .filter(PlayerWorldMemoryState.player_id == player.id)
        .first()
    )
    if state is None:
        state = PlayerWorldMemoryState(player_id=player.id)
        db.add(state)
        db.flush()

    start_day = _window_start(day, WINDOW_DAYS)
    state.region_key = str(_active_region(db, player))
    state.memory_window_start_day = int(start_day)
    state.memory_window_end_day = int(day)
    state.memory_window_start = _day_to_date(start_day)
    state.memory_window_end = resolved_date
    state.macro_pressure_score = scores["macro"]
    state.commute_pressure_score = scores["commute"]
    state.business_pressure_score = scores["business"]
    state.life_pressure_score = scores["life"]
    state.opportunity_score = scores["opportunity"]
    state.dominant_patterns_json = _dump_json(patterns[:8])
    state.narrative_state_json = _dump_json(narrative)
    state.local_pressure_json = _dump_json(local_pressure)
    state.player_pattern_json = _dump_json(player_patterns)
    state.region_memory_json = _dump_json(region_memory)
    state.last_updated_on = int(day)
    state.last_updated_date = resolved_date

    db.flush()
    snapshot = _serialize_memory_state(state)
    snapshot["debug_meta"] = {
        **snapshot.get("debug_meta", {}),
        "detect_debug": patterns_payload.get("debug_meta", {}),
        "decay_info": decay_info,
        "persist_info": persist_info,
    }
    return snapshot


def get_world_memory_snapshot(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return latest world memory snapshot; refresh if stale or missing."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)

    state = (
        db.query(PlayerWorldMemoryState)
        .filter(PlayerWorldMemoryState.player_id == player.id)
        .first()
    )
    if state is None:
        return update_world_memory(db=db, player_id=player.id, as_of_date=resolved_date)

    if int(state.last_updated_on or 0) < int(day):
        return update_world_memory(db=db, player_id=player.id, as_of_date=resolved_date)

    payload = _serialize_memory_state(state)
    payload["as_of_date"] = resolved_date.isoformat()
    payload["debug_meta"] = {
        **payload.get("debug_meta", {}),
        "stale_refresh_needed": False,
    }
    return payload


def build_world_memory_history(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    limit: int = 30,
) -> dict:
    """Return recent pattern lifecycle history rows."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    rows = (
        db.query(PlayerWorldPatternHistory)
        .filter(PlayerWorldPatternHistory.player_id == player.id)
        .order_by(PlayerWorldPatternHistory.updated_at.desc(), PlayerWorldPatternHistory.first_seen_on_day.desc())
        .limit(max(1, min(200, int(limit))))
        .all()
    )

    entries = []
    for row in rows:
        summary = _parse_json(row.summary_json, {}) or {}
        entries.append(
            {
                "pattern_key": str(row.pattern_key),
                "category": str(row.category),
                "title": str(row.title),
                "first_seen_on": row.first_seen_on_date.isoformat() if row.first_seen_on_date else None,
                "last_seen_on": row.last_seen_on_date.isoformat() if row.last_seen_on_date else None,
                "consecutive_days": int(row.consecutive_days or 0),
                "persistence_score": float(_q4(_d(row.persistence_score))),
                "severity": str(row.severity or "low"),
                "direction": str(row.direction or "stable"),
                "status": str(row.status or ACTIVE_STATUS),
                "summary": str(summary.get("short_description") or ""),
                "recommended_response": str(summary.get("recommended_response") or ""),
                "future_locked_response": str(summary.get("future_locked_response") or ""),
                "debug_meta": _parse_json(row.debug_json, {}) or {},
            }
        )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "entries": entries,
        "debug_meta": {
            "limit": int(max(1, min(200, int(limit)))),
            "entry_count": len(entries),
        },
    }


def build_world_memory_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build composed summary payload for frontend hydration."""
    snapshot = get_world_memory_snapshot(db=db, player_id=player_id, as_of_date=as_of_date)
    resolved_date = date.fromisoformat(str(snapshot.get("as_of_date") or _day_to_date(1).isoformat()))
    patterns = detect_recurring_patterns(db=db, player_id=player_id, as_of_date=resolved_date)
    narrative = build_world_narrative(db=db, player_id=player_id, as_of_date=resolved_date)
    local_pressure = build_local_pressure_summary(db=db, player_id=player_id, as_of_date=resolved_date)
    player_patterns = build_player_pattern_summary(db=db, player_id=player_id, as_of_date=resolved_date)
    region_memory = build_region_memory_summary(db=db, player_id=player_id, as_of_date=resolved_date)
    return {
        "player_id": str(snapshot.get("player_id")),
        "as_of_date": str(snapshot.get("as_of_date")),
        "snapshot": snapshot,
        "patterns": patterns,
        "narrative": narrative,
        "local_pressure": local_pressure,
        "player_patterns": player_patterns,
        "region_memory": region_memory,
        "debug_meta": {
            "source": "world_memory_summary",
        },
    }

