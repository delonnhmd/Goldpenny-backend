"""Life consequences + time budget engine (Step 16 MVP)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.balance_config import ZERO_REST_GUARDRAILS
from app.models.business_daily_log import BusinessDailyLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.services.job_market_service import JobMarketError, compute_job_market_pressure

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
INT_Q = Decimal("1")

GAME_EPOCH = date(2026, 1, 1)
HOURS_IN_DAY = Decimal("24.0")
SLEEP_FLOOR = Decimal("4.0")
SLEEP_CAP = Decimal("10.0")

COMMUTE_HOURS_BY_REGION = {
    "downtown": Decimal("1.20"),
    "suburban": Decimal("1.80"),
    "rural": Decimal("2.20"),
}
FRUIT_SHOP_HOURS_BY_LEVEL = {
    "starter": Decimal("4.00"),
    "cart": Decimal("5.00"),
    "small_shop": Decimal("5.50"),
    "large_store": Decimal("6.00"),
}
FOOD_TRUCK_HOURS_BY_LEVEL = {
    "starter": Decimal("5.00"),
    "truck": Decimal("6.50"),
}


class LifeBalanceError(Exception):
    """Base error for life-balance operations."""


class LifeBalanceNotFoundError(LifeBalanceError):
    """Raised when player/resources are missing."""


class LifeBalanceValidationError(LifeBalanceError):
    """Raised for invalid request inputs."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _round_int(value: Decimal) -> int:
    return int(value.quantize(INT_Q, rounding=ROUND_HALF_UP))


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _deterministic_ratio(seed: str) -> Decimal:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return Decimal(n) / Decimal((16**16) - 1)


def _parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise LifeBalanceValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise LifeBalanceNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise LifeBalanceNotFoundError("Player not found.")
    return row


def _resolve_day(player: Player, db: Session, as_of_date: date | None) -> tuple[int, date]:
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        if day <= 0:
            raise LifeBalanceValidationError("as_of_date must be on or after game epoch.")
        return day, as_of_date
    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


def _get_or_create_daily_state(db: Session, player: Player, day: int) -> PlayerDailyState:
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


def _business_hours_for_log(log: BusinessDailyLog, business_lookup: dict[UUID, PlayerBusiness]) -> Decimal:
    btype = (getattr(log, "business_type", "") or "").strip().lower()
    business = business_lookup.get(log.business_id)
    level = ((getattr(business, "level_key", None) if business is not None else None) or "starter").strip().lower()
    if btype == "fruit_shop":
        return FRUIT_SHOP_HOURS_BY_LEVEL.get(level, Decimal("4.00"))
    if btype == "food_truck":
        return FOOD_TRUCK_HOURS_BY_LEVEL.get(level, Decimal("5.00"))
    return Decimal("0.00")


def _base_productivity_modifier(stress: Decimal, health: Decimal) -> Decimal:
    stress_penalty = _clamp((stress - Decimal("50")) * Decimal("0.003"), Decimal("0.0"), Decimal("0.18"))
    health_penalty = _clamp((Decimal("70") - health) * Decimal("0.0025"), Decimal("0.0"), Decimal("0.15"))
    base = Decimal("1.00") - stress_penalty - health_penalty
    return _q4(_clamp(base, Decimal("0.70"), Decimal("1.03")))


def _serialize_time_budget(time_budget: dict) -> dict:
    return {
        "as_of_date": time_budget["as_of_date"],
        "total_hours_used": float(_q4(_d(time_budget["total_hours_used"]))),
        "job_hours": float(_q4(_d(time_budget["job_hours"]))),
        "business_hours": float(_q4(_d(time_budget["business_hours"]))),
        "side_income_hours": float(_q4(_d(time_budget["side_income_hours"]))),
        "commute_hours": float(_q4(_d(time_budget["commute_hours"]))),
        "sleep_hours": float(_q4(_d(time_budget["sleep_hours"]))),
        "recovery_hours": float(_q4(_d(time_budget["recovery_hours"]))),
        "overtime_hours": float(_q4(_d(time_budget["overtime_hours"]))),
    }


def compute_daily_time_budget(
    *,
    as_of_date: date,
    region_key: str,
    job_hours: Decimal,
    business_hours: Decimal,
    side_income_hours: Decimal,
    recovery_hours: Decimal | None = None,
    sleep_hours: Decimal | None = None,
    commute_hours_override: Decimal | None = None,
) -> dict:
    """Compute bounded daily time allocation for one player/day."""
    region = (region_key or "suburban").strip().lower()
    commute_hours = (
        _q4(_d(commute_hours_override))
        if commute_hours_override is not None
        else COMMUTE_HOURS_BY_REGION.get(region, Decimal("1.60"))
    )
    if job_hours <= 0 and business_hours <= 0 and side_income_hours <= 0:
        commute_hours = Decimal("0.00")

    recovery = _clamp(
        _q4(_d(recovery_hours) if recovery_hours is not None else Decimal("1.00")),
        Decimal("0.0"),
        Decimal("6.0"),
    )
    non_sleep = _q4(
        _clamp(_d(job_hours), Decimal("0"), Decimal("16"))
        + _clamp(_d(business_hours), Decimal("0"), Decimal("12"))
        + _clamp(_d(side_income_hours), Decimal("0"), Decimal("12"))
        + _clamp(_d(commute_hours), Decimal("0"), Decimal("4"))
        + recovery
    )

    inferred_sleep = _q4(_d(sleep_hours) if sleep_hours is not None else (HOURS_IN_DAY - non_sleep))
    sleep = _clamp(inferred_sleep, SLEEP_FLOOR, SLEEP_CAP)

    overflow = _q4(max(Decimal("0.00"), (non_sleep + sleep) - HOURS_IN_DAY))
    total_hours_used = _q4(min(HOURS_IN_DAY, non_sleep + sleep))

    return {
        "as_of_date": as_of_date.isoformat(),
        "total_hours_used": total_hours_used,
        "job_hours": _q4(_clamp(_d(job_hours), Decimal("0"), Decimal("16"))),
        "business_hours": _q4(_clamp(_d(business_hours), Decimal("0"), Decimal("12"))),
        "side_income_hours": _q4(_clamp(_d(side_income_hours), Decimal("0"), Decimal("12"))),
        "commute_hours": _q4(_clamp(_d(commute_hours), Decimal("0"), Decimal("4"))),
        "sleep_hours": _q4(sleep),
        "recovery_hours": _q4(recovery),
        "overtime_hours": _q4(overflow),
    }


def compute_daily_stress_update(
    *,
    stress_before: Decimal,
    overtime_hours: Decimal,
    sleep_hours: Decimal,
    recovery_hours: Decimal,
    debt_pressure_score: Decimal,
    business_net_profit_xgp: Decimal,
    job_pressure: Decimal,
    layoff_risk_pct: Decimal,
    region_key: str,
    region_stress_delta: Decimal | None = None,
    distress_score: Decimal = Decimal("0.0"),
    distress_state: str = "stable",
    sustained_zero_rest_streak: int = 0,
) -> dict:
    """Compute bounded daily stress movement and debug driver chain."""
    overtime_component = _clamp(overtime_hours * Decimal("1.5"), Decimal("0"), Decimal("8"))
    low_sleep_component = _clamp(
        max(Decimal("0"), Decimal("7.0") - sleep_hours) * Decimal("1.8"),
        Decimal("0"),
        Decimal("8"),
    )
    debt_pressure_component = _clamp(debt_pressure_score * Decimal("5.0"), Decimal("0"), Decimal("5"))
    business_loss_component = (
        _clamp((abs(business_net_profit_xgp) / Decimal("60.0")), Decimal("0"), Decimal("4"))
        if business_net_profit_xgp < 0
        else Decimal("0.0")
    )
    unstable_job_component = _clamp(
        max(Decimal("0"), -job_pressure) * Decimal("5.0")
        + max(Decimal("0"), layoff_risk_pct - Decimal("12")) / Decimal("14"),
        Decimal("0"),
        Decimal("5"),
    )
    if region_stress_delta is None:
        region_pressure_component = Decimal("0.80") if (region_key or "").strip().lower() == "downtown" else Decimal("0.00")
    else:
        region_pressure_component = _clamp(_d(region_stress_delta), Decimal("-1.50"), Decimal("2.50"))
    stress_inertia_component = _clamp(max(Decimal("0"), stress_before - Decimal("70")) / Decimal("10"), Decimal("0"), Decimal("3"))
    distress_pressure_component = _clamp(max(Decimal("0"), _d(distress_score) - Decimal("35")) / Decimal("12"), Decimal("0"), Decimal("4"))
    distress_state_component = Decimal("0.0")
    normalized_distress_state = (distress_state or "stable").strip().lower()
    if normalized_distress_state == "stretched":
        distress_state_component = Decimal("0.40")
    elif normalized_distress_state == "distressed":
        distress_state_component = Decimal("1.00")
    elif normalized_distress_state == "critical":
        distress_state_component = Decimal("1.90")

    recovery_effectiveness = _clamp(Decimal("1.00") - (_d(distress_score) / Decimal("250")), Decimal("0.70"), Decimal("1.00"))
    recovery_component = _clamp(recovery_hours * Decimal("1.2") * recovery_effectiveness, Decimal("0"), Decimal("6"))
    sustained_grind_component = Decimal("0.0")
    grind_threshold = int(ZERO_REST_GUARDRAILS["streak_days"])
    if int(sustained_zero_rest_streak) >= grind_threshold:
        sustained_grind_component = _clamp(
            _d(ZERO_REST_GUARDRAILS["stress_surcharge"])
            + (Decimal(str(max(0, int(sustained_zero_rest_streak) - grind_threshold))) * Decimal("0.35")),
            Decimal("0.0"),
            Decimal("4.0"),
        )
    stable_day_relief_component = Decimal("0.0")
    if (
        business_net_profit_xgp >= Decimal("0")
        and layoff_risk_pct <= Decimal("10")
        and overtime_hours <= Decimal("1")
        and sleep_hours >= Decimal("7")
    ):
        stable_day_relief_component = Decimal("1.20")

    delta_raw = (
        overtime_component
        + low_sleep_component
        + debt_pressure_component
        + business_loss_component
        + unstable_job_component
        + region_pressure_component
        + stress_inertia_component
        + distress_pressure_component
        + distress_state_component
        + sustained_grind_component
        - recovery_component
        - stable_day_relief_component
    )
    delta_clamped = _clamp(delta_raw, Decimal("-12"), Decimal("15"))
    after = _clamp(stress_before + delta_clamped, Decimal("0"), Decimal("100"))
    before_i = _clamp_int(_round_int(stress_before), 0, 100)
    after_i = _clamp_int(_round_int(after), 0, 100)

    return {
        "stress_before": before_i,
        "stress_after": after_i,
        "stress_delta": after_i - before_i,
        "drivers": {
            "overtime_component": float(_q4(overtime_component)),
            "low_sleep_component": float(_q4(low_sleep_component)),
            "debt_pressure_component": float(_q4(debt_pressure_component)),
            "business_loss_component": float(_q4(business_loss_component)),
            "unstable_job_component": float(_q4(unstable_job_component)),
            "region_pressure_component": float(_q4(region_pressure_component)),
            "region_stress_delta_input": float(_q4(_d(region_stress_delta))) if region_stress_delta is not None else None,
            "stress_inertia_component": float(_q4(stress_inertia_component)),
            "distress_pressure_component": float(_q4(distress_pressure_component)),
            "distress_state_component": float(_q4(distress_state_component)),
            "sustained_zero_rest_streak": int(max(0, sustained_zero_rest_streak)),
            "sustained_grind_component": float(_q4(sustained_grind_component)),
            "recovery_effectiveness": float(_q4(recovery_effectiveness)),
            "recovery_component": float(_q4(recovery_component)),
            "stable_day_relief_component": float(_q4(stable_day_relief_component)),
            "stress_delta_raw": float(_q4(delta_raw)),
        },
    }


def compute_daily_health_update(
    *,
    health_before: Decimal,
    stress_after: Decimal,
    sleep_hours: Decimal,
    recovery_hours: Decimal,
    overtime_hours: Decimal,
    medical_event_triggered: bool,
    burnout_event_triggered: bool,
    medical_event_health_penalty: Decimal = Decimal("0.0"),
) -> dict:
    """Compute bounded daily health movement (slower than stress by design)."""
    sleep_recovery_component = Decimal("0.0")
    if sleep_hours >= Decimal("8.0"):
        sleep_recovery_component = Decimal("1.10")
    elif sleep_hours >= Decimal("7.0"):
        sleep_recovery_component = Decimal("0.70")

    low_stress_component = Decimal("0.50") if stress_after <= Decimal("40") else Decimal("0.0")
    high_stress_component = (
        _clamp((stress_after - Decimal("75")) / Decimal("10"), Decimal("0.0"), Decimal("2.8"))
        if stress_after > Decimal("75")
        else Decimal("0.0")
    )
    overwork_component = (
        _clamp((overtime_hours - Decimal("2.0")) * Decimal("0.8"), Decimal("0.0"), Decimal("2.5"))
        if overtime_hours > Decimal("2.0")
        else Decimal("0.0")
    )
    recovery_component = _clamp(recovery_hours * Decimal("0.25"), Decimal("0"), Decimal("1.20"))

    burnout_component = Decimal("0.80") if burnout_event_triggered else Decimal("0.00")
    medical_event_component = (
        _clamp(medical_event_health_penalty, Decimal("0.0"), Decimal("4.0"))
        if medical_event_triggered
        else Decimal("0.00")
    )

    delta_raw = (
        sleep_recovery_component
        + low_stress_component
        + recovery_component
        - high_stress_component
        - overwork_component
        - burnout_component
        - medical_event_component
    )
    delta_clamped = _clamp(delta_raw, Decimal("-6"), Decimal("3"))
    after = _clamp(health_before + delta_clamped, Decimal("0"), Decimal("100"))

    before_i = _clamp_int(_round_int(health_before), 0, 100)
    after_i = _clamp_int(_round_int(after), 0, 100)
    return {
        "health_before": before_i,
        "health_after": after_i,
        "health_delta": after_i - before_i,
        "drivers": {
            "sleep_recovery_component": float(_q4(sleep_recovery_component)),
            "low_stress_component": float(_q4(low_stress_component)),
            "recovery_component": float(_q4(recovery_component)),
            "high_stress_component": float(_q4(high_stress_component)),
            "overwork_component": float(_q4(overwork_component)),
            "burnout_component": float(_q4(burnout_component)),
            "medical_event_component": float(_q4(medical_event_component)),
            "health_delta_raw": float(_q4(delta_raw)),
        },
    }


def compute_productivity_modifier(
    stress: Decimal,
    health: Decimal,
    sleep_hours: Decimal,
) -> Decimal:
    """Compute bounded productivity modifier from stress/health/sleep."""
    stress_penalty = _clamp((stress - Decimal("50")) * Decimal("0.003"), Decimal("0.0"), Decimal("0.20"))
    health_penalty = _clamp((Decimal("70") - health) * Decimal("0.0025"), Decimal("0.0"), Decimal("0.16"))

    sleep_adjustment = Decimal("0.0")
    if sleep_hours >= Decimal("7.0") and sleep_hours <= Decimal("8.2"):
        sleep_adjustment = Decimal("0.03")
    elif sleep_hours < Decimal("5.0"):
        sleep_adjustment = _clamp(
            -Decimal("0.06") - ((Decimal("5.0") - sleep_hours) * Decimal("0.02")),
            Decimal("-0.14"),
            Decimal("0.0"),
        )
    elif sleep_hours < Decimal("7.0"):
        sleep_adjustment = _clamp(
            -((Decimal("7.0") - sleep_hours) * Decimal("0.015")),
            Decimal("-0.05"),
            Decimal("0.0"),
        )
    elif sleep_hours > Decimal("8.2"):
        sleep_adjustment = Decimal("0.01")

    modifier = Decimal("1.00") - stress_penalty - health_penalty + sleep_adjustment
    return _q4(_clamp(modifier, Decimal("0.70"), Decimal("1.05")))


def compute_burnout_and_medical_risk(
    *,
    stress: Decimal,
    health: Decimal,
    sleep_hours: Decimal,
    overtime_hours: Decimal,
    previous_burnout_risk: Decimal,
    previous_medical_event_risk: Decimal,
    distress_score: Decimal = Decimal("0.0"),
) -> dict:
    """Compute bounded burnout + medical risk signals for one day."""
    distress_component = _clamp(max(Decimal("0"), distress_score - Decimal("55")) / Decimal("420"), Decimal("0"), Decimal("0.10"))
    burnout_risk = _clamp(
        _clamp((stress - Decimal("60")) / Decimal("130"), Decimal("0"), Decimal("0.22"))
        + _clamp((Decimal("7") - sleep_hours) / Decimal("20"), Decimal("0"), Decimal("0.10"))
        + _clamp(overtime_hours / Decimal("20"), Decimal("0"), Decimal("0.10"))
        + _clamp((Decimal("55") - health) / Decimal("180"), Decimal("0"), Decimal("0.10"))
        + distress_component
        + _clamp(previous_burnout_risk * Decimal("0.25"), Decimal("0"), Decimal("0.08")),
        Decimal("0.00"),
        Decimal("0.40"),
    )
    medical_risk = _clamp(
        _clamp((Decimal("65") - health) / Decimal("150"), Decimal("0"), Decimal("0.12"))
        + _clamp((stress - Decimal("80")) / Decimal("180"), Decimal("0"), Decimal("0.08"))
        + _clamp((overtime_hours - Decimal("1")) / Decimal("30"), Decimal("0"), Decimal("0.05"))
        + _clamp(distress_component * Decimal("0.70"), Decimal("0"), Decimal("0.07"))
        + _clamp(previous_medical_event_risk * Decimal("0.20"), Decimal("0"), Decimal("0.05")),
        Decimal("0.00"),
        Decimal("0.20"),
    )
    return {
        "burnout_risk": _q4(burnout_risk),
        "medical_event_risk": _q4(medical_risk),
    }


def _life_response_from_state(player: Player, pds: PlayerDailyState, as_of_date: date) -> dict:
    debug_meta = _parse_json(getattr(pds, "life_debug_json", None))
    time_budget = {
        "as_of_date": as_of_date.isoformat(),
        "total_hours_used": _q4(_d(getattr(pds, "total_hours_used", 0))),
        "job_hours": _q4(_d(getattr(pds, "job_hours", 0))),
        "business_hours": _q4(_d(getattr(pds, "business_hours", 0))),
        "side_income_hours": _q4(_d(getattr(pds, "side_income_hours", 0))),
        "commute_hours": _q4(_d(getattr(pds, "commute_hours", 0))),
        "sleep_hours": _q4(_d(getattr(pds, "sleep_hours", 0))),
        "recovery_hours": _q4(_d(getattr(pds, "recovery_hours", 0))),
        "overtime_hours": _q4(_d(getattr(pds, "overtime_hours", 0))),
    }
    return {
        "player_id": str(player.id),
        "as_of_date": as_of_date.isoformat(),
        "life_summary": (
            f"Stress {int(getattr(pds, 'stress_start', 0))}->{int(getattr(pds, 'stress_end', player.stress or 0))}, "
            f"health {int(getattr(pds, 'health_start', 100))}->{int(getattr(pds, 'health_end', player.health or 100))}."
        ),
        "time_budget_summary": (
            f"Used {float(time_budget['total_hours_used']):.2f}h "
            f"(sleep {float(time_budget['sleep_hours']):.2f}h, overtime {float(time_budget['overtime_hours']):.2f}h)."
        ),
        "stress": int(player.stress or 0),
        "health": int(player.health or 100),
        "productivity_modifier": float(
            _q4(_d(getattr(pds, "productivity_modifier", getattr(player, "productivity_modifier", 1))))
        ),
        "burnout_risk": float(_q4(_d(getattr(pds, "burnout_risk", getattr(player, "burnout_risk", 0))))),
        "medical_event_risk": float(
            _q4(_d(getattr(pds, "medical_event_risk", getattr(player, "medical_event_risk", 0))))
        ),
        "medical_cost_xgp": float(_money(_d(getattr(pds, "medical_cost_xgp", 0)))),
        "missed_work_penalty_xgp": float(_money(_d(getattr(pds, "missed_work_penalty_xgp", 0)))),
        "overtime_hours": float(_q4(_d(getattr(pds, "overtime_hours", 0)))),
        "sleep_hours": float(_q4(_d(getattr(pds, "sleep_hours", 0)))),
        "recovery_hours": float(_q4(_d(getattr(pds, "recovery_hours", 0)))),
        "time_budget": _serialize_time_budget(time_budget),
        "debug_meta": debug_meta,
        "already_processed": bool(debug_meta.get("life_applied", False)),
    }


def apply_life_consequences_for_player(
    db: Session,
    player_id: int | str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compute + persist deterministic daily life consequences for one player."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date)
    pds = _get_or_create_daily_state(db, player, day)

    existing_debug = _parse_json(getattr(pds, "life_debug_json", None))
    if bool(existing_debug.get("life_applied", False)):
        return _life_response_from_state(player, pds, resolved_date)

    business_logs = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day == int(day),
        )
        .order_by(BusinessDailyLog.business_id.asc())
        .all()
    )
    businesses = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id)
        .all()
    )
    business_lookup = {b.id: b for b in businesses}

    business_net_profit = _money(sum((_d(log.net_profit_xgp) for log in business_logs), Decimal("0")))
    business_hours = _q4(sum((_business_hours_for_log(log, business_lookup) for log in business_logs), Decimal("0")))

    job_hours = _q4(_d(getattr(pds, "worked_hours", 0) or getattr(player, "main_job_hours_today", 0)))
    side_income_hours = _q4(_d(getattr(pds, "side_income_hours", 0)))

    try:
        job_pressure_snapshot = compute_job_market_pressure(db, player.id, int(day))
    except (JobMarketError, Exception):
        job_pressure_snapshot = {}

    job_pressure = _q4(_d(job_pressure_snapshot.get("active_job_pressure", 0)))
    layoff_risk_pct = _q4(_d(job_pressure_snapshot.get("layoff_risk_pct", 0)))
    region_key = (
        (getattr(pds, "region_key", None) or player.housing_region_id or player.region or "suburban")
        .strip()
        .lower()
    )
    commute_hours_from_housing = _q4(_d(getattr(pds, "commute_hours", 0)))
    region_stress_from_housing = _q4(_d(getattr(pds, "region_stress_delta", 0)))
    has_housing_overrides = bool(getattr(pds, "region_key", None) or getattr(pds, "housing_debug_json", None))

    debt_pressure_score = _clamp(
        (_d(player.debt_xgp) / max(_d(player.cash_xgp) + Decimal("1.00"), Decimal("1.00"))) / Decimal("6.00"),
        Decimal("0.0"),
        Decimal("1.20"),
    )
    distress_score = _clamp(_d(getattr(player, "distress_score", 0)), Decimal("0.0"), Decimal("100.0"))
    distress_state = (str(getattr(player, "distress_state", "stable") or "stable")).strip().lower()
    if distress_state not in {"stable", "stretched", "distressed", "critical"}:
        distress_state = "stable"
    zero_rest_sleep_threshold = _d(ZERO_REST_GUARDRAILS["sleep_threshold_hours"])
    zero_rest_overtime_threshold = _d(ZERO_REST_GUARDRAILS["overtime_threshold_hours"])
    zero_rest_streak_target = int(ZERO_REST_GUARDRAILS["streak_days"])

    recent_life_rows = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number < int(day),
        )
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .limit(max(7, zero_rest_streak_target + 1))
        .all()
    )
    sustained_zero_rest_streak = 0
    for row in recent_life_rows:
        if (
            _d(getattr(row, "sleep_hours", 0)) <= zero_rest_sleep_threshold
            and _d(getattr(row, "overtime_hours", 0)) >= zero_rest_overtime_threshold
        ):
            sustained_zero_rest_streak += 1
        else:
            break

    time_budget = compute_daily_time_budget(
        as_of_date=resolved_date,
        region_key=region_key,
        job_hours=job_hours,
        business_hours=business_hours,
        side_income_hours=side_income_hours,
        recovery_hours=_d(getattr(pds, "recovery_hours", 0) or Decimal("1.00")),
        commute_hours_override=(commute_hours_from_housing if has_housing_overrides else None),
    )

    stress_before = _d(player.stress)
    health_before = _d(player.health)

    stress_update = compute_daily_stress_update(
        stress_before=stress_before,
        overtime_hours=_d(time_budget["overtime_hours"]),
        sleep_hours=_d(time_budget["sleep_hours"]),
        recovery_hours=_d(time_budget["recovery_hours"]),
        debt_pressure_score=debt_pressure_score,
        business_net_profit_xgp=business_net_profit,
        job_pressure=job_pressure,
        layoff_risk_pct=layoff_risk_pct,
        region_key=region_key,
        region_stress_delta=(region_stress_from_housing if has_housing_overrides else None),
        distress_score=distress_score,
        distress_state=distress_state,
        sustained_zero_rest_streak=sustained_zero_rest_streak,
    )

    risk_update = compute_burnout_and_medical_risk(
        stress=_d(stress_update["stress_after"]),
        health=health_before,
        sleep_hours=_d(time_budget["sleep_hours"]),
        overtime_hours=_d(time_budget["overtime_hours"]),
        previous_burnout_risk=_d(getattr(player, "burnout_risk", 0)),
        previous_medical_event_risk=_d(getattr(player, "medical_event_risk", 0)),
        distress_score=distress_score,
    )

    event_seed = f"{player.id}:{day}:life"
    medical_roll = _q4(_deterministic_ratio(f"{event_seed}:medical"))
    burnout_roll = _q4(_deterministic_ratio(f"{event_seed}:burnout"))

    medical_triggered = bool(medical_roll < _d(risk_update["medical_event_risk"]))
    burnout_triggered = bool(
        (not medical_triggered) and (burnout_roll < (_d(risk_update["burnout_risk"]) * Decimal("0.60")))
    )

    medical_cost_xgp = Decimal("0.00")
    missed_work_penalty_xgp = Decimal("0.00")
    event_health_penalty = Decimal("0.00")
    event_stress_jump = 0
    if medical_triggered:
        medical_cost_xgp = _money(
            _clamp(
                Decimal("20.00")
                + (_d(risk_update["medical_event_risk"]) * Decimal("700"))
                + (_d(time_budget["overtime_hours"]) * Decimal("14"))
                + ((Decimal("100") - health_before) * Decimal("0.60")),
                Decimal("20.00"),
                Decimal("250.00"),
            )
        )
        missed_work_penalty_xgp = _money(
            _clamp(
                Decimal("8.00")
                + (_d(risk_update["burnout_risk"]) * Decimal("180"))
                + (_d(time_budget["overtime_hours"]) * Decimal("8")),
                Decimal("8.00"),
                Decimal("95.00"),
            )
        )
        event_health_penalty = Decimal("2.00") + (Decimal("1.00") if health_before < Decimal("45") else Decimal("0.00"))
        event_stress_jump = 3
    elif burnout_triggered:
        missed_work_penalty_xgp = _money(
            _clamp(
                Decimal("5.00")
                + (_d(risk_update["burnout_risk"]) * Decimal("130"))
                + (_d(time_budget["overtime_hours"]) * Decimal("6")),
                Decimal("5.00"),
                Decimal("60.00"),
            )
        )
        event_health_penalty = Decimal("1.00")
        event_stress_jump = 2

    stress_after_event = _clamp_int(int(stress_update["stress_after"]) + event_stress_jump, 0, 100)
    stress_delta = int(stress_after_event) - int(stress_update["stress_before"])

    health_update = compute_daily_health_update(
        health_before=health_before,
        stress_after=Decimal(str(stress_after_event)),
        sleep_hours=_d(time_budget["sleep_hours"]),
        recovery_hours=_d(time_budget["recovery_hours"]),
        overtime_hours=_d(time_budget["overtime_hours"]),
        medical_event_triggered=medical_triggered,
        burnout_event_triggered=burnout_triggered,
        medical_event_health_penalty=event_health_penalty,
    )
    health_after = int(health_update["health_after"])
    health_delta = int(health_update["health_delta"])

    productivity_modifier = compute_productivity_modifier(
        stress=Decimal(str(stress_after_event)),
        health=Decimal(str(health_after)),
        sleep_hours=_d(time_budget["sleep_hours"]),
    )
    grind_productivity_drag = Decimal("0.0")
    if (
        sustained_zero_rest_streak >= zero_rest_streak_target
        and _d(time_budget["sleep_hours"]) <= zero_rest_sleep_threshold
    ):
        grind_productivity_drag = _clamp(
            _d(ZERO_REST_GUARDRAILS["productivity_drag"])
            * Decimal(str(max(1, sustained_zero_rest_streak - zero_rest_streak_target + 1))),
            Decimal("0.0"),
            Decimal("0.09"),
        )
    productivity_modifier = _q4(_clamp(productivity_modifier - grind_productivity_drag, Decimal("0.70"), Decimal("1.05")))
    base_productivity_modifier = _base_productivity_modifier(
        stress=Decimal(str(stress_after_event)),
        health=Decimal(str(health_after)),
    )

    player.stress = int(stress_after_event)
    player.health = int(health_after)
    player.productivity_modifier = _q4(productivity_modifier)
    player.base_productivity_modifier = _q4(base_productivity_modifier)
    player.burnout_risk = _q4(_d(risk_update["burnout_risk"]))
    player.medical_event_risk = _q4(_d(risk_update["medical_event_risk"]))

    pds.stress_start = int(stress_update["stress_before"])
    pds.stress_end = int(stress_after_event)
    pds.health_start = int(_clamp_int(_round_int(health_before), 0, 100))
    pds.health_end = int(health_after)
    pds.total_hours_used = _q4(_d(time_budget["total_hours_used"]))
    pds.job_hours = _q4(_d(time_budget["job_hours"]))
    pds.business_hours = _q4(_d(time_budget["business_hours"]))
    pds.side_income_hours = _q4(_d(time_budget["side_income_hours"]))
    pds.commute_hours = _q4(_d(time_budget["commute_hours"]))
    pds.sleep_hours = _q4(_d(time_budget["sleep_hours"]))
    pds.recovery_hours = _q4(_d(time_budget["recovery_hours"]))
    pds.overtime_hours = _q4(_d(time_budget["overtime_hours"]))
    pds.stress_delta = int(stress_delta)
    pds.health_delta = int(health_delta)
    pds.productivity_modifier = _q4(productivity_modifier)
    pds.burnout_risk = _q4(_d(risk_update["burnout_risk"]))
    pds.medical_event_risk = _q4(_d(risk_update["medical_event_risk"]))
    pds.medical_cost_xgp = _money(medical_cost_xgp)
    pds.missed_work_penalty_xgp = _money(missed_work_penalty_xgp)

    debug_meta = {
        "life_applied": True,
        "day": int(day),
        "job_pressure": float(_q4(job_pressure)),
        "layoff_risk_pct": float(_q4(layoff_risk_pct)),
        "debt_pressure_score": float(_q4(debt_pressure_score)),
        "distress_score_input": float(_q4(distress_score)),
        "distress_state_input": distress_state,
        "business_net_profit_xgp": float(_money(business_net_profit)),
        "housing_region_inputs": {
            "region_key": region_key,
            "used_housing_overrides": bool(has_housing_overrides),
            "commute_hours_input": float(_q4(commute_hours_from_housing)),
            "region_stress_delta_input": float(_q4(region_stress_from_housing)),
        },
        "stress_drivers": stress_update["drivers"],
        "health_drivers": health_update["drivers"],
        "sustained_zero_rest_streak": int(sustained_zero_rest_streak),
        "zero_rest_guardrails": {
            "sleep_threshold_hours": float(_q4(zero_rest_sleep_threshold)),
            "overtime_threshold_hours": float(_q4(zero_rest_overtime_threshold)),
            "streak_target_days": int(zero_rest_streak_target),
            "productivity_drag_applied": float(_q4(grind_productivity_drag)),
        },
        "risk_inputs": {
            "burnout_risk": float(_q4(_d(risk_update["burnout_risk"]))),
            "medical_event_risk": float(_q4(_d(risk_update["medical_event_risk"]))),
            "medical_roll": float(_q4(medical_roll)),
            "burnout_roll": float(_q4(burnout_roll)),
        },
        "event": {
            "medical_triggered": bool(medical_triggered),
            "burnout_triggered": bool(burnout_triggered),
            "medical_cost_xgp": float(_money(medical_cost_xgp)),
            "missed_work_penalty_xgp": float(_money(missed_work_penalty_xgp)),
            "event_stress_jump": int(event_stress_jump),
            "event_health_penalty": float(_q4(event_health_penalty)),
        },
        "productivity_inputs": {
            "stress_after": int(stress_after_event),
            "health_after": int(health_after),
            "sleep_hours": float(_q4(_d(time_budget["sleep_hours"]))),
            "base_productivity_modifier": float(_q4(base_productivity_modifier)),
            "productivity_modifier": float(_q4(productivity_modifier)),
        },
    }
    pds.life_debug_json = json.dumps(debug_meta, sort_keys=True)
    db.flush()

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "life_summary": (
            f"Stress {int(stress_update['stress_before'])}->{int(stress_after_event)}, "
            f"health {int(_clamp_int(_round_int(health_before), 0, 100))}->{int(health_after)}."
        ),
        "time_budget_summary": (
            f"Used {float(_q4(_d(time_budget['total_hours_used']))):.2f}h "
            f"(sleep {float(_q4(_d(time_budget['sleep_hours']))):.2f}h, overtime {float(_q4(_d(time_budget['overtime_hours']))):.2f}h)."
        ),
        "stress": int(stress_after_event),
        "health": int(health_after),
        "productivity_modifier": float(_q4(productivity_modifier)),
        "burnout_risk": float(_q4(_d(risk_update["burnout_risk"]))),
        "medical_event_risk": float(_q4(_d(risk_update["medical_event_risk"]))),
        "medical_cost_xgp": float(_money(medical_cost_xgp)),
        "missed_work_penalty_xgp": float(_money(missed_work_penalty_xgp)),
        "overtime_hours": float(_q4(_d(time_budget["overtime_hours"]))),
        "sleep_hours": float(_q4(_d(time_budget["sleep_hours"]))),
        "recovery_hours": float(_q4(_d(time_budget["recovery_hours"]))),
        "time_budget": _serialize_time_budget(time_budget),
        "debug_meta": debug_meta,
        "already_processed": False,
    }


def get_player_life_snapshot(
    db: Session,
    player_id: str | UUID,
    *,
    as_of_date: date | None = None,
) -> dict:
    """Return compact life snapshot for a player/day (latest by default)."""
    player = _resolve_player(db, player_id)

    q = db.query(PlayerDailyState).filter(PlayerDailyState.player_id == player.id)
    if as_of_date is not None:
        q = q.filter(PlayerDailyState.day_number == _date_to_day(as_of_date))

    pds = q.order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc()).first()
    if pds is None:
        raise LifeBalanceNotFoundError("Life snapshot not found for player.")

    day = int(pds.day_number)
    resolved_date = _day_to_date(day)
    debug_meta = _parse_json(getattr(pds, "life_debug_json", None))
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "stress_before": int(getattr(pds, "stress_start", player.stress or 0)),
        "stress_after": int(getattr(pds, "stress_end", player.stress or 0)),
        "health_before": int(getattr(pds, "health_start", player.health or 100)),
        "health_after": int(getattr(pds, "health_end", player.health or 100)),
        "stress_delta": int(getattr(pds, "stress_delta", 0)),
        "health_delta": int(getattr(pds, "health_delta", 0)),
        "productivity_modifier": float(
            _q4(_d(getattr(pds, "productivity_modifier", player.productivity_modifier)))
        ),
        "burnout_risk": float(_q4(_d(getattr(pds, "burnout_risk", player.burnout_risk)))),
        "medical_event_risk": float(
            _q4(_d(getattr(pds, "medical_event_risk", player.medical_event_risk)))
        ),
        "medical_cost_xgp": float(_money(_d(getattr(pds, "medical_cost_xgp", 0)))),
        "missed_work_penalty_xgp": float(_money(_d(getattr(pds, "missed_work_penalty_xgp", 0)))),
        "time_budget": _serialize_time_budget(
            {
                "as_of_date": resolved_date.isoformat(),
                "total_hours_used": _q4(_d(getattr(pds, "total_hours_used", 0))),
                "job_hours": _q4(_d(getattr(pds, "job_hours", 0))),
                "business_hours": _q4(_d(getattr(pds, "business_hours", 0))),
                "side_income_hours": _q4(_d(getattr(pds, "side_income_hours", 0))),
                "commute_hours": _q4(_d(getattr(pds, "commute_hours", 0))),
                "sleep_hours": _q4(_d(getattr(pds, "sleep_hours", 0))),
                "recovery_hours": _q4(_d(getattr(pds, "recovery_hours", 0))),
                "overtime_hours": _q4(_d(getattr(pds, "overtime_hours", 0))),
            }
        ),
        "debug_meta": debug_meta,
    }


def get_player_life_history(
    db: Session,
    player_id: str | UUID,
    *,
    limit: int = 30,
) -> dict:
    """Return recent life history rows + trailing 7-day averages."""
    if int(limit) <= 0:
        raise LifeBalanceValidationError("limit must be greater than 0.")

    player = _resolve_player(db, player_id)
    rows = (
        db.query(PlayerDailyState)
        .filter(PlayerDailyState.player_id == player.id)
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .limit(int(limit))
        .all()
    )

    entries: list[dict] = []
    for row in rows:
        as_of = _day_to_date(int(row.day_number)).isoformat()
        entries.append(
            {
                "as_of_date": as_of,
                "day": int(row.day_number),
                "stress_before": int(getattr(row, "stress_start", 0)),
                "stress_after": int(getattr(row, "stress_end", 0)),
                "health_before": int(getattr(row, "health_start", 100)),
                "health_after": int(getattr(row, "health_end", 100)),
                "stress_delta": int(getattr(row, "stress_delta", 0)),
                "health_delta": int(getattr(row, "health_delta", 0)),
                "sleep_hours": float(_q4(_d(getattr(row, "sleep_hours", 0)))),
                "overtime_hours": float(_q4(_d(getattr(row, "overtime_hours", 0)))),
                "productivity_modifier": float(_q4(_d(getattr(row, "productivity_modifier", 1)))),
                "burnout_risk": float(_q4(_d(getattr(row, "burnout_risk", 0)))),
                "medical_event_risk": float(_q4(_d(getattr(row, "medical_event_risk", 0)))),
                "medical_cost_xgp": float(_money(_d(getattr(row, "medical_cost_xgp", 0)))),
                "missed_work_penalty_xgp": float(_money(_d(getattr(row, "missed_work_penalty_xgp", 0)))),
                "time_budget": {
                    "total_hours_used": float(_q4(_d(getattr(row, "total_hours_used", 0)))),
                    "job_hours": float(_q4(_d(getattr(row, "job_hours", 0)))),
                    "business_hours": float(_q4(_d(getattr(row, "business_hours", 0)))),
                    "side_income_hours": float(_q4(_d(getattr(row, "side_income_hours", 0)))),
                    "commute_hours": float(_q4(_d(getattr(row, "commute_hours", 0)))),
                    "sleep_hours": float(_q4(_d(getattr(row, "sleep_hours", 0)))),
                    "recovery_hours": float(_q4(_d(getattr(row, "recovery_hours", 0)))),
                    "overtime_hours": float(_q4(_d(getattr(row, "overtime_hours", 0)))),
                },
                "debug_meta": _parse_json(getattr(row, "life_debug_json", None)),
            }
        )

    recent = entries[:7]
    n = Decimal(str(max(1, len(recent))))
    avg_stress = sum((Decimal(str(item["stress_after"])) for item in recent), Decimal("0")) / n
    avg_health = sum((Decimal(str(item["health_after"])) for item in recent), Decimal("0")) / n
    avg_sleep = sum((Decimal(str(item["sleep_hours"])) for item in recent), Decimal("0")) / n
    avg_prod = sum((Decimal(str(item["productivity_modifier"])) for item in recent), Decimal("0")) / n

    return {
        "player_id": str(player.id),
        "entries": entries,
        "trailing_7d_avg_stress": float(_q4(avg_stress)),
        "trailing_7d_avg_health": float(_q4(avg_health)),
        "trailing_7d_avg_sleep": float(_q4(avg_sleep)),
        "trailing_7d_avg_productivity": float(_q4(avg_prod)),
    }
