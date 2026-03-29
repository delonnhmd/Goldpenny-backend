"""Step 35 personal shock and life-event engine."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.personal_event_catalog import PERSONAL_EVENT_CATALOG, PersonalLifeEventTemplate
from app.models.daily_settlement_log import DailySettlementLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_shock_state import PlayerShockState
from app.models.region_population_state import RegionPopulationState

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
GAME_EPOCH = date(2026, 1, 1)

SEVERITY_ORDER = {"light": 1, "moderate": 2, "heavy": 3}
NEGATIVE_FAMILIES = {"financial_shock", "health_stress_shock", "work_disruption"}
POSITIVE_FAMILIES = {"opportunity", "recovery_support"}
MIN_EVENT_CHANCE = Decimal("0.08")
MAX_EVENT_CHANCE = Decimal("0.48")
HEAVY_REPEAT_COOLDOWN_DAYS = 3

PRACTICAL_ACTIONS = [
    "reduce optional spending",
    "rest / avoid extra strain",
    "hold more cash",
    "avoid risky expansion",
    "move closer if commute stress is crushing",
    "delay non-essential growth",
]


class PersonalShockError(Exception):
    """Base personal shock error."""


class PersonalShockNotFoundError(PersonalShockError):
    """Raised when player/resources are missing."""


class PersonalShockValidationError(PersonalShockError):
    """Raised for invalid inputs."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _parse_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        value = json.loads(raw)
        return value if isinstance(value, type(fallback)) else fallback
    except Exception:
        return fallback


def _deterministic_ratio(seed: str) -> Decimal:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return Decimal(n) / Decimal((16**16) - 1)


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise PersonalShockValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise PersonalShockNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise PersonalShockNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, player: Player, as_of_date: date | None, day_number: int | None) -> tuple[int, date]:
    if day_number is not None:
        day = int(day_number)
        if day <= 0:
            raise PersonalShockValidationError("day_number must be greater than 0.")
        return day, _day_to_date(day)
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        if day <= 0:
            raise PersonalShockValidationError("as_of_date must be on or after game epoch.")
        return day, as_of_date
    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


def _latest_settlement(db: Session, player_id: UUID, day: int) -> DailySettlementLog | None:
    return (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player_id,
            DailySettlementLog.day_number <= day,
        )
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )


def _recent_settlements(db: Session, player_id: UUID, day: int, window: int = 7) -> list[DailySettlementLog]:
    start_day = max(1, day - max(1, window) + 1)
    return (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player_id,
            DailySettlementLog.day_number >= start_day,
            DailySettlementLog.day_number <= day,
        )
        .order_by(DailySettlementLog.day_number.asc(), DailySettlementLog.created_at.asc())
        .all()
    )


def _recent_daily_states(db: Session, player_id: UUID, day: int, window: int = 7) -> list[PlayerDailyState]:
    start_day = max(1, day - max(1, window) + 1)
    return (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player_id,
            PlayerDailyState.day_number >= start_day,
            PlayerDailyState.day_number <= day,
        )
        .order_by(PlayerDailyState.day_number.asc(), PlayerDailyState.created_at.asc())
        .all()
    )


def _latest_housing_state(db: Session, player_id: UUID) -> PlayerHousingState | None:
    return (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player_id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc())
        .first()
    )


def _latest_employment_state(db: Session, player_id: UUID, day: int) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player_id,
            PlayerEmploymentState.day <= day,
        )
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _active_businesses(db: Session, player_id: UUID) -> list[PlayerBusiness]:
    return (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player_id,
            PlayerBusiness.is_active.is_(True),
        )
        .order_by(PlayerBusiness.business_type.asc(), PlayerBusiness.created_at.asc())
        .all()
    )


def _get_or_create_shock_state(db: Session, player_id: UUID) -> PlayerShockState:
    row = db.query(PlayerShockState).filter(PlayerShockState.player_id == player_id).first()
    if row is not None:
        return row
    row = PlayerShockState(player_id=player_id)
    db.add(row)
    db.flush()
    return row


def _get_or_create_recovery_state(db: Session, player_id: UUID) -> PlayerRecoveryState:
    row = db.query(PlayerRecoveryState).filter(PlayerRecoveryState.player_id == player_id).first()
    if row is not None:
        return row
    row = PlayerRecoveryState(player_id=player_id)
    db.add(row)
    db.flush()
    return row


def _latest_event_row(db: Session, player_id: UUID, day: int | None = None) -> PlayerLifeEventHistory | None:
    q = db.query(PlayerLifeEventHistory).filter(PlayerLifeEventHistory.player_id == player_id)
    if day is not None:
        q = q.filter(PlayerLifeEventHistory.day_number == int(day))
    return q.order_by(PlayerLifeEventHistory.day_number.desc(), PlayerLifeEventHistory.created_at.desc()).first()


def _serialize_event_row(row: PlayerLifeEventHistory | None) -> dict:
    if row is None:
        return {
            "event_triggered": False,
            "event_key": None,
            "event_family": None,
            "headline": "No personal life event triggered.",
            "severity_band": "none",
            "as_of_date": None,
            "day_number": None,
            "cash_impact_xgp": 0.0,
            "stress_impact_delta": 0.0,
            "health_impact_delta": 0.0,
            "time_impact_hours": 0.0,
            "work_income_impact": 0.0,
            "business_impact": 0.0,
            "side_income_impact": 0.0,
            "duration_days": 0,
            "recovery_hint": "",
            "trigger_tags": [],
            "impact": {},
            "debug_meta": {},
        }
    impact = _parse_json(row.impact_json, {})
    debug = _parse_json(row.debug_json, {})
    trigger_tags = _parse_json(row.trigger_tags_json, [])
    return {
        "event_triggered": True,
        "event_key": str(row.event_key),
        "event_family": str(row.event_family),
        "headline": str(row.headline),
        "severity_band": str(row.severity_band),
        "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
        "day_number": int(row.day_number),
        "cash_impact_xgp": float(_money(_d(row.cash_impact_xgp))),
        "stress_impact_delta": float(_q4(_d(row.stress_impact_delta))),
        "health_impact_delta": float(_q4(_d(row.health_impact_delta))),
        "time_impact_hours": float(_q4(_d(row.time_impact_hours))),
        "work_income_impact": float(_q4(_d(row.work_income_impact))),
        "business_impact": float(_q4(_d(row.business_impact))),
        "side_income_impact": float(_q4(_d(row.side_income_impact))),
        "duration_days": int(row.duration_days or 0),
        "recovery_hint": str(row.recovery_hint or ""),
        "trigger_tags": [str(tag) for tag in trigger_tags if tag],
        "impact": impact if isinstance(impact, dict) else {},
        "debug_meta": debug if isinstance(debug, dict) else {},
    }


def _serialize_recovery_state(row: PlayerRecoveryState | None) -> dict:
    if row is None:
        return {
            "player_id": None,
            "recovery_days_remaining": 0,
            "temporary_stress_modifier": 0.0,
            "temporary_health_modifier": 0.0,
            "temporary_income_modifier": 0.0,
            "temporary_business_modifier": 0.0,
            "temporary_time_modifier": 0.0,
            "recovery_status_label": "stable",
            "short_summary": "No active recovery window.",
            "debug_meta": {},
        }
    days = int(row.recovery_days_remaining or 0)
    status = str(row.recovery_status_label or "stable")
    summary = (
        "No active recovery window."
        if days <= 0
        else f"Recovery effects active for ~{days} more day(s)."
    )
    return {
        "player_id": str(row.player_id),
        "recovery_days_remaining": days,
        "temporary_stress_modifier": float(_q4(_d(row.temporary_stress_modifier))),
        "temporary_health_modifier": float(_q4(_d(row.temporary_health_modifier))),
        "temporary_income_modifier": float(_q4(_d(row.temporary_income_modifier))),
        "temporary_business_modifier": float(_q4(_d(row.temporary_business_modifier))),
        "temporary_time_modifier": float(_q4(_d(row.temporary_time_modifier))),
        "recovery_status_label": status,
        "source_event_key": row.source_event_key,
        "source_event_severity": row.source_event_severity,
        "last_applied_day": int(row.last_applied_day) if row.last_applied_day is not None else None,
        "next_expire_day": int(row.next_expire_day) if row.next_expire_day is not None else None,
        "short_summary": summary,
        "debug_meta": _parse_json(row.recovery_debug_json, {}),
    }


def _label_from_score(score: Decimal) -> str:
    s = _clamp(score, Decimal("0"), Decimal("100"))
    if s >= Decimal("72"):
        return "high"
    if s >= Decimal("48"):
        return "moderate"
    return "low"


def _weighted_choice(seed: str, weighted: list[tuple[PersonalLifeEventTemplate, Decimal]]) -> PersonalLifeEventTemplate:
    total = sum((max(Decimal("0.0001"), weight) for _, weight in weighted), Decimal("0"))
    if total <= Decimal("0"):
        return weighted[0][0]
    roll = _deterministic_ratio(seed) * total
    cursor = Decimal("0")
    for event, weight in weighted:
        cursor += max(Decimal("0.0001"), weight)
        if roll <= cursor:
            return event
    return weighted[-1][0]


def _sample_range(seed: str, lo: float, hi: float) -> Decimal:
    lo_d = _d(lo)
    hi_d = _d(hi)
    if hi_d <= lo_d:
        return _q4(lo_d)
    ratio = _deterministic_ratio(seed)
    return _q4(lo_d + ((hi_d - lo_d) * ratio))


def _profile_debug_payload(
    *,
    cash_buffer_days: Decimal,
    avg_daily_expenses: Decimal,
    avg_daily_income: Decimal,
    housing_burden_ratio: Decimal,
    commute_hours_effective: Decimal,
    avg_sleep_hours: Decimal,
    avg_overtime_hours: Decimal,
    negative_streak_days: int,
    recovery_support_days: int,
) -> dict:
    return {
        "cash_buffer_days": float(_q4(cash_buffer_days)),
        "avg_daily_expenses": float(_money(avg_daily_expenses)),
        "avg_daily_income": float(_money(avg_daily_income)),
        "housing_burden_ratio": float(_q4(housing_burden_ratio)),
        "commute_hours_effective": float(_q4(commute_hours_effective)),
        "avg_sleep_hours": float(_q4(avg_sleep_hours)),
        "avg_overtime_hours": float(_q4(avg_overtime_hours)),
        "negative_streak_days": int(max(0, negative_streak_days)),
        "recovery_support_days": int(max(0, recovery_support_days)),
    }


def build_personal_shock_profile(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    persist: bool = False,
) -> dict:
    """Build rolling personal fragility/resilience profile for one player/day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    settlements = _recent_settlements(db, player.id, day, window=7)
    daily_rows = _recent_daily_states(db, player.id, day, window=7)
    housing_state = _latest_housing_state(db, player.id)
    employment = _latest_employment_state(db, player.id, day)
    businesses = _active_businesses(db, player.id)

    region_key = str(getattr(housing_state, "region", None) or player.region or "suburban").lower()
    region_state = (
        db.query(RegionPopulationState)
        .filter(RegionPopulationState.region_key == region_key)
        .first()
    )

    avg_expenses = (
        _q4(sum((_d(getattr(row, "expenses_xgp", 0)) for row in settlements), Decimal("0")) / Decimal(str(len(settlements))))
        if settlements
        else Decimal("58.00")
    )
    avg_income = (
        _q4(sum((_d(getattr(row, "income_xgp", 0)) for row in settlements), Decimal("0")) / Decimal(str(len(settlements))))
        if settlements
        else Decimal("68.00")
    )
    avg_sleep = (
        _q4(sum((_d(getattr(row, "sleep_hours", 7)) for row in daily_rows), Decimal("0")) / Decimal(str(len(daily_rows))))
        if daily_rows
        else Decimal("7.00")
    )
    avg_overtime = (
        _q4(sum((_d(getattr(row, "overtime_hours", 0)) for row in daily_rows), Decimal("0")) / Decimal(str(len(daily_rows))))
        if daily_rows
        else Decimal("0.00")
    )

    negative_streak_days = 0
    recovery_support_days = 0
    for row in settlements[-5:]:
        net = _d(getattr(row, "income_xgp", 0)) - _d(getattr(row, "expenses_xgp", 0))
        stress_after = _d(getattr(row, "stress_after", 0))
        if net < Decimal("0") or stress_after >= Decimal("68"):
            negative_streak_days += 1
        if net >= Decimal("0") and stress_after <= Decimal("58"):
            recovery_support_days += 1

    cash_buffer_days = _q4(_d(player.cash_xgp) / max(Decimal("1.00"), avg_expenses))
    housing_monthly = _d(getattr(housing_state, "monthly_housing_cost_xgp", 0))
    utilities_monthly = _d(getattr(housing_state, "monthly_utilities_cost_xgp", 0))
    housing_daily = (housing_monthly + utilities_monthly) / Decimal("30")
    housing_burden_ratio = _q4(housing_daily / max(Decimal("1.00"), avg_income))
    commute_hours_effective = _q4(
        _d((region_state.congestion_score if region_state is not None else Decimal("45"))) / Decimal("70")
        + (_d(getattr(housing_state, "monthly_transport_base_xgp", 0)) / Decimal("300"))
        + (Decimal("0.70") if region_key == "suburban" else Decimal("0.40"))
    )

    debt_pressure = _clamp(_d(player.debt_xgp) / max(Decimal("200"), _d(player.cash_xgp) + Decimal("200")), Decimal("0"), Decimal("1"))
    distress_component = _clamp(_d(player.distress_score) / Decimal("100"), Decimal("0"), Decimal("1"))
    stress_component = _clamp(_d(player.stress) / Decimal("100"), Decimal("0"), Decimal("1"))
    health_component = _clamp((Decimal("100") - _d(player.health)) / Decimal("100"), Decimal("0"), Decimal("1"))
    burnout_component = _clamp(_d(player.burnout_risk) / Decimal("0.40"), Decimal("0"), Decimal("1"))
    business_exposure = _clamp(Decimal(str(len(businesses))) / Decimal("3.0"), Decimal("0"), Decimal("1"))
    job_instability = _clamp(
        _d(getattr(employment, "layoff_risk_pct", 0)) / Decimal("35")
        + (Decimal("0.25") if str(getattr(employment, "job_status", "employed")) != "employed" else Decimal("0")),
        Decimal("0"),
        Decimal("1"),
    )

    financial_fragility_score = _clamp(
        _clamp((Decimal("4.0") - cash_buffer_days) / Decimal("4.0"), Decimal("0"), Decimal("1")) * Decimal("42")
        + debt_pressure * Decimal("31")
        + _clamp(housing_burden_ratio / Decimal("0.45"), Decimal("0"), Decimal("1")) * Decimal("12")
        + distress_component * Decimal("15"),
        Decimal("0"),
        Decimal("100"),
    )
    health_fragility_score = _clamp(
        stress_component * Decimal("34")
        + health_component * Decimal("27")
        + _clamp((Decimal("7.0") - avg_sleep) / Decimal("3.0"), Decimal("0"), Decimal("1")) * Decimal("19")
        + burnout_component * Decimal("12")
        + _clamp((commute_hours_effective - Decimal("0.9")) / Decimal("1.8"), Decimal("0"), Decimal("1")) * Decimal("8"),
        Decimal("0"),
        Decimal("100"),
    )
    work_disruption_risk_score = _clamp(
        _clamp((commute_hours_effective - Decimal("0.8")) / Decimal("2.2"), Decimal("0"), Decimal("1")) * Decimal("30")
        + job_instability * Decimal("25")
        + _clamp(health_fragility_score / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("30")
        + business_exposure * Decimal("15"),
        Decimal("0"),
        Decimal("100"),
    )
    recovery_capacity_score = _clamp(
        Decimal("56")
        + _clamp(cash_buffer_days / Decimal("8.0"), Decimal("0"), Decimal("1")) * Decimal("16")
        + _clamp(_d(player.health) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("13")
        + _clamp(Decimal(str(recovery_support_days)) / Decimal("5"), Decimal("0"), Decimal("1")) * Decimal("10")
        - stress_component * Decimal("20")
        - debt_pressure * Decimal("11"),
        Decimal("0"),
        Decimal("100"),
    )
    shock_risk_score = _clamp(
        Decimal("18")
        + financial_fragility_score * Decimal("0.35")
        + health_fragility_score * Decimal("0.29")
        + work_disruption_risk_score * Decimal("0.25")
        + Decimal(str(negative_streak_days)) * Decimal("2.1")
        - recovery_capacity_score * Decimal("0.21"),
        Decimal("0"),
        Decimal("100"),
    )

    if len(settlements) >= 4:
        recent_stress = _q4(
            sum((_d(getattr(row, "stress_after", 0)) for row in settlements[-2:]), Decimal("0")) / Decimal("2")
        )
        prior_stress = _q4(
            sum((_d(getattr(row, "stress_after", 0)) for row in settlements[-4:-2]), Decimal("0")) / Decimal("2")
        )
        recent_cash = _q4(
            sum((_d(getattr(row, "cash_after", 0)) for row in settlements[-2:]), Decimal("0")) / Decimal("2")
        )
        prior_cash = _q4(
            sum((_d(getattr(row, "cash_after", 0)) for row in settlements[-4:-2]), Decimal("0")) / Decimal("2")
        )
        if recent_stress - prior_stress >= Decimal("4") or prior_cash - recent_cash >= Decimal("70"):
            recent_pressure_direction = "worsening"
        elif prior_stress - recent_stress >= Decimal("4") or recent_cash - prior_cash >= Decimal("70"):
            recent_pressure_direction = "improving"
        else:
            recent_pressure_direction = "stable"
    else:
        recent_pressure_direction = "stable"

    debug_meta = _profile_debug_payload(
        cash_buffer_days=cash_buffer_days,
        avg_daily_expenses=avg_expenses,
        avg_daily_income=avg_income,
        housing_burden_ratio=housing_burden_ratio,
        commute_hours_effective=commute_hours_effective,
        avg_sleep_hours=avg_sleep,
        avg_overtime_hours=avg_overtime,
        negative_streak_days=negative_streak_days,
        recovery_support_days=recovery_support_days,
    )

    payload = {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "shock_risk_score": float(_q4(shock_risk_score)),
        "financial_fragility_score": float(_q4(financial_fragility_score)),
        "health_fragility_score": float(_q4(health_fragility_score)),
        "work_disruption_risk_score": float(_q4(work_disruption_risk_score)),
        "recovery_capacity_score": float(_q4(recovery_capacity_score)),
        "recent_pressure_direction": recent_pressure_direction,
        "recent_negative_streak": int(max(0, negative_streak_days)),
        "recent_recovery_support": int(max(0, recovery_support_days)),
        "last_updated_on": int(day),
        "last_updated_date": resolved_date.isoformat(),
        "debug_meta": debug_meta,
    }

    if persist:
        row = _get_or_create_shock_state(db, player.id)
        row.shock_risk_score = _q4(shock_risk_score)
        row.financial_fragility_score = _q4(financial_fragility_score)
        row.health_fragility_score = _q4(health_fragility_score)
        row.work_disruption_risk_score = _q4(work_disruption_risk_score)
        row.recovery_capacity_score = _q4(recovery_capacity_score)
        row.recent_pressure_direction = recent_pressure_direction
        row.recent_negative_streak = int(max(0, negative_streak_days))
        row.recent_recovery_support = int(max(0, recovery_support_days))
        row.last_updated_on = int(day)
        row.last_updated_date = resolved_date
        row.profile_debug_json = json.dumps(debug_meta, sort_keys=True)
        db.flush()

    return payload


def build_shock_risk_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build bounded event-frequency/severity risk state from shock profile."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    profile = build_personal_shock_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    recovery_state = _get_or_create_recovery_state(db, player.id)
    shock_state = _get_or_create_shock_state(db, player.id)

    shock_risk = _d(profile["shock_risk_score"])
    financial_fragility = _d(profile["financial_fragility_score"])
    health_fragility = _d(profile["health_fragility_score"])
    recovery_capacity = _d(profile["recovery_capacity_score"])

    event_chance = _clamp(
        Decimal("0.12")
        + (shock_risk / Decimal("100")) * Decimal("0.23")
        + (financial_fragility / Decimal("100")) * Decimal("0.12")
        + (health_fragility / Decimal("100")) * Decimal("0.10")
        - (recovery_capacity / Decimal("100")) * Decimal("0.18"),
        MIN_EVENT_CHANCE,
        MAX_EVENT_CHANCE,
    )
    if int(profile.get("recent_negative_streak", 0)) >= 4:
        event_chance = _clamp(event_chance + Decimal("0.04"), MIN_EVENT_CHANCE, MAX_EVENT_CHANCE)
    if int(recovery_state.recovery_days_remaining or 0) > 0:
        event_chance = _clamp(event_chance - Decimal("0.04"), MIN_EVENT_CHANCE, MAX_EVENT_CHANCE)

    risk = _clamp(shock_risk / Decimal("100"), Decimal("0"), Decimal("1"))
    resil = _clamp(recovery_capacity / Decimal("100"), Decimal("0"), Decimal("1"))
    light_weight = _clamp(Decimal("0.68") - (risk * Decimal("0.25")) + (resil * Decimal("0.18")), Decimal("0.40"), Decimal("0.80"))
    moderate_weight = _clamp(Decimal("0.25") + (risk * Decimal("0.20")), Decimal("0.15"), Decimal("0.45"))
    heavy_weight = _clamp(Decimal("0.07") + (risk * Decimal("0.12")) - (resil * Decimal("0.08")), Decimal("0.03"), Decimal("0.20"))

    heavy_cooldown_active = False
    if (
        str(getattr(shock_state, "last_event_severity", "")).lower() == "heavy"
        and getattr(shock_state, "last_event_day", None) is not None
        and int(day) - int(shock_state.last_event_day) <= HEAVY_REPEAT_COOLDOWN_DAYS
    ):
        heavy_weight = _clamp(heavy_weight * Decimal("0.25"), Decimal("0.01"), Decimal("0.10"))
        moderate_weight = _clamp(moderate_weight * Decimal("1.08"), Decimal("0.10"), Decimal("0.60"))
        heavy_cooldown_active = True

    early_guided_days_active = int(day) <= 3
    if early_guided_days_active:
        event_chance = _clamp(event_chance * Decimal("0.82"), MIN_EVENT_CHANCE, Decimal("0.18"))
        light_weight = _clamp(light_weight + Decimal("0.10"), Decimal("0.48"), Decimal("0.85"))
        moderate_weight = _clamp(moderate_weight * Decimal("0.92"), Decimal("0.12"), Decimal("0.42"))
        heavy_weight = _clamp(heavy_weight * Decimal("0.22"), Decimal("0.01"), Decimal("0.08"))

    total = light_weight + moderate_weight + heavy_weight
    light_weight = _q4(light_weight / max(Decimal("0.0001"), total))
    moderate_weight = _q4(moderate_weight / max(Decimal("0.0001"), total))
    heavy_weight = _q4(Decimal("1.0") - light_weight - moderate_weight)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "shock_risk_label": _label_from_score(shock_risk),
        "event_roll_chance": float(_q4(event_chance)),
        "severity_weights": {
            "light": float(light_weight),
            "moderate": float(moderate_weight),
            "heavy": float(_clamp(heavy_weight, Decimal("0.00"), Decimal("1.00"))),
        },
        "major_event_probability": float(_q4(_clamp(moderate_weight + heavy_weight, Decimal("0"), Decimal("1")))),
        "repeat_shock_protection_active": bool(heavy_cooldown_active),
        "debug_meta": {
            "profile": profile,
            "recovery_days_remaining": int(recovery_state.recovery_days_remaining or 0),
            "last_event_severity": getattr(shock_state, "last_event_severity", None),
            "last_event_day": getattr(shock_state, "last_event_day", None),
            "early_guided_days_active": early_guided_days_active,
        },
    }


def _event_tags_for_context(
    player: Player,
    profile: dict,
    housing_state: PlayerHousingState | None,
    employment: PlayerEmploymentState | None,
    businesses: list[PlayerBusiness],
    region_state: RegionPopulationState | None,
) -> set[str]:
    tags: set[str] = set()

    cash_buffer_days = _d((profile.get("debug_meta") or {}).get("cash_buffer_days", 0))
    if cash_buffer_days < Decimal("3.00"):
        tags.add("low_cash_buffer")
    if _d(getattr(player, "debt_utilization_ratio", 0)) >= Decimal("0.60") or _d(player.debt_xgp) > (_d(player.cash_xgp) * Decimal("1.20")):
        tags.add("high_debt")
    if _d(player.distress_score) >= Decimal("55"):
        tags.add("distress_high")
    if int(player.stress or 0) >= 65:
        tags.add("high_stress")
    if int(player.health or 100) <= 66:
        tags.add("low_health")
    if _d((profile.get("debug_meta") or {}).get("avg_sleep_hours", 7)) < Decimal("6.00"):
        tags.add("low_sleep")
    if _d((profile.get("debug_meta") or {}).get("avg_overtime_hours", 0)) >= Decimal("1.20"):
        tags.add("overtime")
    if _d((profile.get("debug_meta") or {}).get("commute_hours_effective", 0)) >= Decimal("1.20"):
        tags.add("high_commute")
    if _d((profile.get("debug_meta") or {}).get("housing_burden_ratio", 0)) >= Decimal("0.33"):
        tags.add("housing_burden_high")
    if _d(player.burnout_risk) >= Decimal("0.24"):
        tags.add("burnout_risk_high")

    region = str((getattr(housing_state, "region", None) or player.region or "suburban")).lower()
    if region == "downtown":
        tags.add("high_opportunity_region")
    if str(getattr(housing_state, "commute_mode", "")).lower() == "car":
        tags.add("car_mode")

    job_code = str(getattr(employment, "current_job_code", "") or player.main_job or "").lower()
    if "delivery" in job_code or "rideshare" in job_code:
        tags.update({"job_delivery", "side_income_ready"})
    if "chef" in job_code:
        tags.update({"job_chef", "job_service"})
    if "banker" in job_code or "finance" in job_code:
        tags.add("job_banker")
        tags.add("career_push")
    if "retail" in job_code:
        tags.update({"job_retail", "job_service"})
    if "aircraft" in job_code:
        tags.update({"job_aircraft_mechanic", "job_mechanic"})
    elif "mechanic" in job_code:
        tags.add("job_mechanic")
    if str(getattr(employment, "job_status", "employed")) == "employed":
        tags.add("job_stable")

    if businesses:
        tags.add("has_business")
        for row in businesses:
            bt = str(row.business_type or "").lower()
            if bt == "fruit_shop":
                tags.add("has_fruit_shop")
            elif bt == "food_truck":
                tags.add("has_food_truck")

    if region_state is not None:
        if _d(region_state.opportunity_density_score) >= Decimal("58"):
            tags.update({"opportunity_density_high", "networking_high"})
        if _d(region_state.business_competition_score) >= Decimal("62"):
            tags.add("competition_high")
        if _d(region_state.congestion_score) >= Decimal("62"):
            tags.add("high_commute")

    if _d((profile.get("debug_meta") or {}).get("commute_hours_effective", 0)) >= Decimal("1.30"):
        tags.add("move_or_rent_closer_recent")

    return tags


def roll_personal_life_event(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Deterministically roll bounded personal life event for one player/day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    existing = _latest_event_row(db, player.id, day)
    if existing is not None:
        payload = _serialize_event_row(existing)
        payload["already_recorded"] = True
        return payload

    profile = build_personal_shock_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk_state = build_shock_risk_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)

    roll_seed = f"personal_shock:roll:{player.id}:{day}"
    chance_roll = _deterministic_ratio(roll_seed)
    trigger_threshold = _d(risk_state["event_roll_chance"])
    if chance_roll > trigger_threshold:
        return {
            "event_triggered": False,
            "event_key": None,
            "event_family": None,
            "headline": "No major personal disruption today.",
            "severity_band": "none",
            "as_of_date": resolved_date.isoformat(),
            "day_number": int(day),
            "cash_impact_xgp": 0.0,
            "stress_impact_delta": 0.0,
            "health_impact_delta": 0.0,
            "time_impact_hours": 0.0,
            "work_income_impact": 0.0,
            "business_impact": 0.0,
            "side_income_impact": 0.0,
            "duration_days": 0,
            "recovery_hint": "Stay disciplined and keep your buffer healthy.",
            "trigger_tags": [],
            "impact": {},
            "debug_meta": {
                "chance_roll": float(_q4(chance_roll)),
                "trigger_threshold": float(_q4(trigger_threshold)),
                "risk_state": risk_state,
                "profile": profile,
            },
        }

    severity_roll = _deterministic_ratio(f"personal_shock:severity:{player.id}:{day}")
    severity_weights = risk_state["severity_weights"]
    light_cut = _d(severity_weights.get("light", 0.65))
    moderate_cut = light_cut + _d(severity_weights.get("moderate", 0.25))
    if severity_roll <= light_cut:
        severity_band = "light"
    elif severity_roll <= moderate_cut:
        severity_band = "moderate"
    else:
        severity_band = "heavy"

    housing_state = _latest_housing_state(db, player.id)
    employment = _latest_employment_state(db, player.id, day)
    businesses = _active_businesses(db, player.id)
    region_key = str(getattr(housing_state, "region", None) or player.region or "suburban").lower()
    region_state = (
        db.query(RegionPopulationState)
        .filter(RegionPopulationState.region_key == region_key)
        .first()
    )
    tags = _event_tags_for_context(
        player=player,
        profile=profile,
        housing_state=housing_state,
        employment=employment,
        businesses=businesses,
        region_state=region_state,
    )

    risk = _d(profile["shock_risk_score"]) / Decimal("100")
    resilience = _d(profile["recovery_capacity_score"]) / Decimal("100")
    weighted: list[tuple[PersonalLifeEventTemplate, Decimal]] = []
    for event in PERSONAL_EVENT_CATALOG:
        if event.severity_band != severity_band:
            continue
        weight = Decimal("1.0")
        matches = 0
        for tag in event.trigger_tags:
            if tag in tags:
                matches += 1
        if matches > 0:
            weight += Decimal(str(matches)) * Decimal("0.55")
        else:
            weight *= Decimal("0.86")

        if event.event_family in NEGATIVE_FAMILIES:
            weight *= _clamp(Decimal("0.90") + (risk * Decimal("0.35")), Decimal("0.70"), Decimal("1.30"))
        elif event.event_family in POSITIVE_FAMILIES:
            weight *= _clamp(Decimal("0.78") + (resilience * Decimal("0.42")), Decimal("0.55"), Decimal("1.35"))

        if "has_business" in tags and "has_business" in event.trigger_tags:
            weight *= Decimal("1.05")
        if "job_delivery" in tags and "job_delivery" in event.trigger_tags:
            weight *= Decimal("1.08")
        if "job_chef" in tags and "job_chef" in event.trigger_tags:
            weight *= Decimal("1.05")
        if "job_banker" in tags and "job_banker" in event.trigger_tags:
            weight *= Decimal("1.04")

        weighted.append((event, _clamp(weight, Decimal("0.05"), Decimal("5.0"))))
    if not weighted:
        weighted = [(item, Decimal("1.0")) for item in PERSONAL_EVENT_CATALOG if item.severity_band == "light"]

    selected = _weighted_choice(f"personal_shock:event_select:{player.id}:{day}:{severity_band}", weighted)
    harm_multiplier = _clamp(
        Decimal("0.86") + (risk * Decimal("0.36")) - (resilience * Decimal("0.24")),
        Decimal("0.60"),
        Decimal("1.25"),
    )
    support_multiplier = _clamp(
        Decimal("0.82") + (resilience * Decimal("0.34")),
        Decimal("0.60"),
        Decimal("1.18"),
    )

    def sample(field: str, lo: float, hi: float) -> Decimal:
        raw = _sample_range(f"personal_shock:impact:{player.id}:{day}:{selected.event_key}:{field}", lo, hi)
        if selected.event_family in NEGATIVE_FAMILIES and raw < 0:
            raw *= harm_multiplier
        elif selected.event_family in POSITIVE_FAMILIES and raw > 0:
            raw *= support_multiplier
        return raw

    cash_impact = _money(_clamp(sample("cash", *selected.cash_impact_range), Decimal("-250"), Decimal("120")))
    stress_impact = _q4(_clamp(sample("stress", *selected.stress_impact_range), Decimal("-8"), Decimal("18")))
    health_impact = _q4(_clamp(sample("health", *selected.health_impact_range), Decimal("-9"), Decimal("6")))
    time_impact = _q4(_clamp(sample("time", *selected.time_impact_range), Decimal("-1.5"), Decimal("3.2")))
    work_impact = _q4(_clamp(sample("work_income", *selected.work_income_impact_range), Decimal("-0.30"), Decimal("0.20")))
    business_impact = _q4(_clamp(sample("business", *selected.business_impact_range), Decimal("-0.28"), Decimal("0.22")))
    side_income_impact = _q4(_clamp(sample("side_income", *selected.side_income_impact_range), Decimal("-0.28"), Decimal("0.22")))

    return {
        "event_triggered": True,
        "event_key": selected.event_key,
        "event_family": selected.event_family,
        "headline": selected.headline,
        "severity_band": selected.severity_band,
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "cash_impact_xgp": float(cash_impact),
        "stress_impact_delta": float(stress_impact),
        "health_impact_delta": float(health_impact),
        "time_impact_hours": float(time_impact),
        "work_income_impact": float(work_impact),
        "business_impact": float(business_impact),
        "side_income_impact": float(side_income_impact),
        "duration_days": int(selected.duration_days),
        "recovery_hint": selected.recovery_hint,
        "trigger_tags": sorted(tags),
        "impact": {
            "cash_impact_xgp": float(cash_impact),
            "stress_impact_delta": float(stress_impact),
            "health_impact_delta": float(health_impact),
            "time_impact_hours": float(time_impact),
            "work_income_impact": float(work_impact),
            "business_impact": float(business_impact),
            "side_income_impact": float(side_income_impact),
        },
        "debug_meta": {
            "risk_state": risk_state,
            "profile": profile,
            "chance_roll": float(_q4(chance_roll)),
            "severity_roll": float(_q4(severity_roll)),
            "selected_event_key": selected.event_key,
            "selected_weight": float(
                next((weight for event, weight in weighted if event.event_key == selected.event_key), Decimal("1.0"))
            ),
            "harm_multiplier": float(_q4(harm_multiplier)),
            "support_multiplier": float(_q4(support_multiplier)),
        },
    }


def build_recovery_window(
    event_payload: dict | None,
    *,
    profile: dict | None = None,
) -> dict:
    """Build bounded short-lived recovery window from rolled event outcome."""
    payload = event_payload or {}
    if not payload.get("event_triggered"):
        return {
            "recovery_days_remaining": 0,
            "temporary_stress_modifier": 0.0,
            "temporary_health_modifier": 0.0,
            "temporary_income_modifier": 0.0,
            "temporary_business_modifier": 0.0,
            "temporary_time_modifier": 0.0,
            "recovery_status_label": "stable",
            "short_summary": "No active recovery modifiers.",
            "debug_meta": {"source": "no_event"},
        }

    severity = str(payload.get("severity_band", "light")).lower()
    duration = int(payload.get("duration_days", 0) or 0)
    if duration <= 0:
        duration = 2 if severity == "light" else 3 if severity == "moderate" else 4
    if profile is not None:
        risk = _d(profile.get("shock_risk_score", 50))
        duration = int(_clamp(_d(duration) + (risk / Decimal("100")) * Decimal("1.2"), Decimal("1"), Decimal("6")))
    stress_mod = _q4(
        _clamp(_d(payload.get("stress_impact_delta", 0)) * Decimal("0.34"), Decimal("-4.0"), Decimal("6.0"))
    )
    health_mod = _q4(
        _clamp(_d(payload.get("health_impact_delta", 0)) * Decimal("0.34"), Decimal("-3.5"), Decimal("2.5"))
    )
    income_mod = _q4(
        _clamp(_d(payload.get("work_income_impact", 0)) * Decimal("0.45"), Decimal("-0.18"), Decimal("0.12"))
    )
    business_mod = _q4(
        _clamp(_d(payload.get("business_impact", 0)) * Decimal("0.45"), Decimal("-0.18"), Decimal("0.12"))
    )
    time_mod = _q4(
        _clamp(_d(payload.get("time_impact_hours", 0)) * Decimal("0.42"), Decimal("-0.80"), Decimal("1.40"))
    )

    if duration <= 1:
        status = "brief_recovery"
    elif duration <= 3:
        status = "active_recovery"
    else:
        status = "extended_recovery"
    summary = (
        f"Recovery effects from '{payload.get('event_key')}' are active for about {duration} day(s)."
        if duration > 0
        else "No active recovery modifiers."
    )
    return {
        "recovery_days_remaining": int(max(0, duration)),
        "temporary_stress_modifier": float(stress_mod),
        "temporary_health_modifier": float(health_mod),
        "temporary_income_modifier": float(income_mod),
        "temporary_business_modifier": float(business_mod),
        "temporary_time_modifier": float(time_mod),
        "recovery_status_label": status if duration > 0 else "stable",
        "short_summary": summary,
        "debug_meta": {
            "severity_band": severity,
            "duration_days_input": int(payload.get("duration_days", 0) or 0),
        },
    }


def _build_practical_actions(profile: dict, recovery_snapshot: dict, event_payload: dict | None = None) -> list[str]:
    actions: list[str] = []
    if _d(profile.get("financial_fragility_score", 0)) >= Decimal("58"):
        actions.extend(["reduce optional spending", "hold more cash"])
    if _d(profile.get("health_fragility_score", 0)) >= Decimal("56"):
        actions.extend(["rest / avoid extra strain", "delay non-essential growth"])
    if _d(profile.get("work_disruption_risk_score", 0)) >= Decimal("60"):
        actions.append("move closer if commute stress is crushing")
    if _d((recovery_snapshot or {}).get("temporary_business_modifier", 0)) < Decimal("-0.04"):
        actions.append("avoid risky expansion")
    if event_payload and str(event_payload.get("event_family", "")) == "financial_shock":
        actions.append("reduce optional spending")
    out: list[str] = []
    for action in actions:
        if action in PRACTICAL_ACTIONS and action not in out:
            out.append(action)
    if not out:
        out = ["hold more cash", "delay non-essential growth"]
    return out[:5]


def apply_personal_life_event(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    worked_hours: int | None = None,
    job_income_xgp: Decimal | float | int | None = None,
    business_net_xgp: Decimal | float | int | None = None,
    side_income_net_xgp: Decimal | float | int | None = None,
    commit: bool = False,
) -> dict:
    """Apply one deterministic personal life-event pass and update recovery state."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    shock_state = _get_or_create_shock_state(db, player.id)
    recovery_state = _get_or_create_recovery_state(db, player.id)
    existing_for_day = _latest_event_row(db, player.id, day)

    if existing_for_day is not None and int(recovery_state.last_applied_day or 0) == int(day):
        event_payload = _serialize_event_row(existing_for_day)
        recovery_payload = _serialize_recovery_state(recovery_state)
        impact = event_payload.get("impact", {}) if isinstance(event_payload.get("impact"), dict) else {}
        practical = _build_practical_actions(
            profile=build_personal_shock_profile(db, player.id, resolved_date, day),
            recovery_snapshot=recovery_payload,
            event_payload=event_payload,
        )
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "day_number": int(day),
            "already_applied_for_day": True,
            "shock_profile": build_personal_shock_profile(db, player.id, resolved_date, day),
            "risk_state": build_shock_risk_state(db, player.id, resolved_date, day),
            "recent_event": event_payload,
            "recovery_state": recovery_payload,
            "applied_impacts": impact,
            "practical_current_actions": practical,
            "short_summary": event_payload.get("headline", "No personal disruption."),
            "debug_meta": {
                "idempotent": True,
                "last_applied_day": int(recovery_state.last_applied_day or 0),
            },
        }

    profile = build_personal_shock_profile(db, player.id, resolved_date, day, persist=True)
    risk_state = build_shock_risk_state(db, player.id, resolved_date, day)
    if existing_for_day is None:
        event_payload = roll_personal_life_event(db, player.id, resolved_date, day)
    else:
        event_payload = _serialize_event_row(existing_for_day)

    old_days_remaining = int(recovery_state.recovery_days_remaining or 0)
    old_days_after = max(0, old_days_remaining - 1)
    old_decay = Decimal("0.78") if old_days_after > 0 else Decimal("0")
    carry_stress = _q4(_d(recovery_state.temporary_stress_modifier) * old_decay)
    carry_health = _q4(_d(recovery_state.temporary_health_modifier) * old_decay)
    carry_income = _q4(_d(recovery_state.temporary_income_modifier) * old_decay)
    carry_business = _q4(_d(recovery_state.temporary_business_modifier) * old_decay)
    carry_time = _q4(_d(recovery_state.temporary_time_modifier) * old_decay)

    new_window = build_recovery_window(event_payload, profile=profile)
    new_days = int(new_window.get("recovery_days_remaining", 0) or 0)
    next_days = max(old_days_after, new_days)
    next_stress = _q4(_clamp(carry_stress + _d(new_window.get("temporary_stress_modifier", 0)), Decimal("-5.0"), Decimal("6.0")))
    next_health = _q4(_clamp(carry_health + _d(new_window.get("temporary_health_modifier", 0)), Decimal("-3.8"), Decimal("2.8")))
    next_income = _q4(_clamp(carry_income + _d(new_window.get("temporary_income_modifier", 0)), Decimal("-0.20"), Decimal("0.12")))
    next_business = _q4(_clamp(carry_business + _d(new_window.get("temporary_business_modifier", 0)), Decimal("-0.20"), Decimal("0.12")))
    next_time = _q4(_clamp(carry_time + _d(new_window.get("temporary_time_modifier", 0)), Decimal("-0.90"), Decimal("1.60")))

    event_stress = _d(event_payload.get("stress_impact_delta", 0))
    event_health = _d(event_payload.get("health_impact_delta", 0))
    event_cash = _money(_d(event_payload.get("cash_impact_xgp", 0)))
    event_time = _q4(_d(event_payload.get("time_impact_hours", 0)))
    event_income_mod = _q4(_d(event_payload.get("work_income_impact", 0)))
    event_business_mod = _q4(_d(event_payload.get("business_impact", 0)))
    event_side_income_mod = _q4(_d(event_payload.get("side_income_impact", 0)))

    applied_stress_delta = _q4(_clamp(carry_stress + event_stress, Decimal("-10"), Decimal("18")))
    applied_health_delta = _q4(_clamp(carry_health + event_health, Decimal("-10"), Decimal("6")))
    applied_time_hours = _q4(_clamp(carry_time + event_time, Decimal("-1.2"), Decimal("3.4")))
    work_income_modifier = _q4(_clamp(Decimal("1.0") + carry_income + event_income_mod, Decimal("0.70"), Decimal("1.18")))
    business_modifier = _q4(_clamp(Decimal("1.0") + carry_business + event_business_mod, Decimal("0.70"), Decimal("1.18")))
    side_income_modifier = _q4(_clamp(Decimal("1.0") + (carry_income * Decimal("0.50")) + event_side_income_mod, Decimal("0.70"), Decimal("1.18")))

    work_base = _money(_d(job_income_xgp))
    business_base = _money(_d(business_net_xgp))
    side_base = _money(_d(side_income_net_xgp))
    adjusted_work = _money(work_base * work_income_modifier)
    adjusted_business = _money(business_base * business_modifier)
    adjusted_side = _money(side_base * side_income_modifier)
    operational_delta = _money((adjusted_business - business_base) + (adjusted_side - side_base))

    if existing_for_day is None and event_payload.get("event_triggered"):
        row = PlayerLifeEventHistory(
            player_id=player.id,
            day_number=int(day),
            as_of_date=resolved_date,
            event_key=str(event_payload.get("event_key")),
            event_family=str(event_payload.get("event_family")),
            headline=str(event_payload.get("headline")),
            severity_band=str(event_payload.get("severity_band")),
            cash_impact_xgp=event_cash,
            stress_impact_delta=_q4(event_stress),
            health_impact_delta=_q4(event_health),
            time_impact_hours=event_time,
            work_income_impact=event_income_mod,
            business_impact=event_business_mod,
            side_income_impact=event_side_income_mod,
            duration_days=int(event_payload.get("duration_days", 0) or 0),
            recovery_hint=str(event_payload.get("recovery_hint", "")),
            trigger_tags_json=json.dumps(event_payload.get("trigger_tags", []), sort_keys=True),
            impact_json=json.dumps(
                {
                    "cash_impact_xgp": float(event_cash),
                    "stress_impact_delta": float(applied_stress_delta),
                    "health_impact_delta": float(applied_health_delta),
                    "time_impact_hours": float(applied_time_hours),
                    "work_income_modifier": float(work_income_modifier),
                    "business_modifier": float(business_modifier),
                    "side_income_modifier": float(side_income_modifier),
                    "operational_delta_xgp": float(operational_delta),
                    "adjusted_work_income_xgp": float(adjusted_work),
                    "adjusted_business_net_xgp": float(adjusted_business),
                    "adjusted_side_income_net_xgp": float(adjusted_side),
                },
                sort_keys=True,
            ),
            debug_json=json.dumps(event_payload.get("debug_meta", {}), sort_keys=True),
        )
        db.add(row)

    if event_payload.get("event_triggered"):
        shock_state.last_event_key = str(event_payload.get("event_key"))
        shock_state.last_event_family = str(event_payload.get("event_family"))
        shock_state.last_event_severity = str(event_payload.get("severity_band"))
        shock_state.last_event_day = int(day)
        shock_state.last_event_date = resolved_date
    shock_state.shock_risk_score = _q4(_d(profile["shock_risk_score"]))
    shock_state.financial_fragility_score = _q4(_d(profile["financial_fragility_score"]))
    shock_state.health_fragility_score = _q4(_d(profile["health_fragility_score"]))
    shock_state.work_disruption_risk_score = _q4(_d(profile["work_disruption_risk_score"]))
    shock_state.recovery_capacity_score = _q4(_d(profile["recovery_capacity_score"]))
    shock_state.recent_pressure_direction = str(profile["recent_pressure_direction"])
    shock_state.recent_negative_streak = int(profile.get("recent_negative_streak", 0))
    shock_state.recent_recovery_support = int(profile.get("recent_recovery_support", 0))
    shock_state.last_updated_on = int(day)
    shock_state.last_updated_date = resolved_date
    shock_state.profile_debug_json = json.dumps(profile.get("debug_meta", {}), sort_keys=True)

    recovery_state.recovery_days_remaining = int(max(0, next_days))
    recovery_state.temporary_stress_modifier = next_stress
    recovery_state.temporary_health_modifier = next_health
    recovery_state.temporary_income_modifier = next_income
    recovery_state.temporary_business_modifier = next_business
    recovery_state.temporary_time_modifier = next_time
    recovery_state.recovery_status_label = (
        "stable"
        if next_days <= 0
        else "brief_recovery"
        if next_days <= 1
        else "active_recovery"
        if next_days <= 3
        else "extended_recovery"
    )
    recovery_state.source_event_key = str(event_payload.get("event_key")) if event_payload.get("event_triggered") else recovery_state.source_event_key
    recovery_state.source_event_severity = str(event_payload.get("severity_band")) if event_payload.get("event_triggered") else recovery_state.source_event_severity
    recovery_state.last_applied_day = int(day)
    recovery_state.next_expire_day = int(day + next_days - 1) if next_days > 0 else None
    recovery_state.last_updated_on = int(day)
    recovery_state.last_updated_date = resolved_date
    recovery_state.recovery_debug_json = json.dumps(
        {
            "old_days_remaining": old_days_remaining,
            "old_days_after_decay": old_days_after,
            "new_window": new_window,
            "carry_modifiers": {
                "stress": float(carry_stress),
                "health": float(carry_health),
                "income": float(carry_income),
                "business": float(carry_business),
                "time": float(carry_time),
            },
        },
        sort_keys=True,
    )

    player.stress = _clamp_int(
        int(round(float(_d(player.stress) + applied_stress_delta))),
        0,
        100,
    )
    player.health = _clamp_int(
        int(round(float(_d(player.health) + applied_health_delta))),
        0,
        100,
    )
    db.flush()

    recovery_payload = _serialize_recovery_state(recovery_state)
    practical = _build_practical_actions(profile, recovery_payload, event_payload)
    short_summary = (
        str(event_payload.get("headline"))
        if event_payload.get("event_triggered")
        else "No major personal disruption today."
    )
    result = {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "already_applied_for_day": False,
        "shock_profile": profile,
        "risk_state": risk_state,
        "recent_event": event_payload,
        "recovery_state": recovery_payload,
        "applied_impacts": {
            "cash_impact_xgp": float(event_cash),
            "stress_impact_delta": float(applied_stress_delta),
            "health_impact_delta": float(applied_health_delta),
            "time_impact_hours": float(applied_time_hours),
            "work_income_modifier": float(work_income_modifier),
            "business_modifier": float(business_modifier),
            "side_income_modifier": float(side_income_modifier),
            "operational_delta_xgp": float(operational_delta),
            "adjusted_work_income_xgp": float(adjusted_work),
            "adjusted_business_net_xgp": float(adjusted_business),
            "adjusted_side_income_net_xgp": float(adjusted_side),
        },
        "practical_current_actions": practical,
        "short_summary": short_summary,
        "debug_meta": {
            "worked_hours": int(worked_hours or 0),
            "base_job_income_xgp": float(work_base),
            "base_business_net_xgp": float(business_base),
            "base_side_income_net_xgp": float(side_base),
            "event_triggered": bool(event_payload.get("event_triggered", False)),
            "repeat_shock_protection_active": bool(risk_state.get("repeat_shock_protection_active", False)),
            "catalog_size": int(len(PERSONAL_EVENT_CATALOG)),
        },
    }

    if commit:
        db.commit()
    else:
        db.flush()
    return result


def get_recent_personal_life_event(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Return latest recorded personal event (or none payload)."""
    player = _resolve_player(db, player_id)
    day, _ = _resolve_day(db, player, as_of_date, day_number)
    row = _latest_event_row(db, player.id, day)
    return _serialize_event_row(row)


def get_player_recovery_state(
    db: Session,
    player_id: str | UUID,
) -> dict:
    """Return active recovery state snapshot."""
    player = _resolve_player(db, player_id)
    return _serialize_recovery_state(
        db.query(PlayerRecoveryState).filter(PlayerRecoveryState.player_id == player.id).first()
    )


def build_player_resilience_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build compact resilience label and top drivers for planning/debug."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    profile = build_personal_shock_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)

    shock_risk = _d(profile["shock_risk_score"])
    financial = _d(profile["financial_fragility_score"])
    health = _d(profile["health_fragility_score"])
    work = _d(profile["work_disruption_risk_score"])
    recovery = _d(profile["recovery_capacity_score"])

    if shock_risk >= Decimal("72"):
        resilience_label = "fragile"
    elif shock_risk >= Decimal("56"):
        resilience_label = "stretched"
    elif recovery >= Decimal("66") and financial <= Decimal("42") and health <= Decimal("42"):
        resilience_label = "resilient"
    else:
        resilience_label = "stable"

    cash_buffer_days = _d((profile.get("debug_meta") or {}).get("cash_buffer_days", 0))
    if cash_buffer_days >= Decimal("8"):
        cash_buffer_label = "strong"
    elif cash_buffer_days >= Decimal("4"):
        cash_buffer_label = "adequate"
    elif cash_buffer_days >= Decimal("2"):
        cash_buffer_label = "thin"
    else:
        cash_buffer_label = "critical"

    stress_value = _d(player.stress)
    if stress_value >= Decimal("75"):
        stress_load_label = "heavy"
    elif stress_value >= Decimal("58"):
        stress_load_label = "elevated"
    else:
        stress_load_label = "manageable"

    if recovery >= Decimal("70"):
        recovery_capacity_label = "high"
    elif recovery >= Decimal("52"):
        recovery_capacity_label = "moderate"
    else:
        recovery_capacity_label = "low"

    drivers = {
        "financial_fragility": financial,
        "health_fragility": health,
        "work_disruption_risk": work,
    }
    top_risk_driver = max(drivers.items(), key=lambda kv: kv[1])[0]
    stabilizers = {
        "cash_buffer": cash_buffer_days,
        "recovery_capacity": recovery,
        "health_level": _d(player.health),
    }
    top_stabilizer = max(stabilizers.items(), key=lambda kv: kv[1])[0]

    short_summary = (
        "Personal resilience is under pressure; prioritize stability before aggressive growth."
        if resilience_label in {"fragile", "stretched"}
        else "Resilience is holding; controlled growth remains viable with basic guardrails."
    )
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "resilience_label": resilience_label,
        "cash_buffer_label": cash_buffer_label,
        "stress_load_label": stress_load_label,
        "recovery_capacity_label": recovery_capacity_label,
        "top_risk_driver": top_risk_driver,
        "top_stabilizer": top_stabilizer,
        "short_summary": short_summary,
        "debug_meta": {
            "shock_risk_score": float(_q4(shock_risk)),
            "financial_fragility_score": float(_q4(financial)),
            "health_fragility_score": float(_q4(health)),
            "work_disruption_risk_score": float(_q4(work)),
            "recovery_capacity_score": float(_q4(recovery)),
            "profile": profile,
        },
    }


def build_personal_shock_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build compact player-facing summary of current shock + recovery state."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    profile = build_personal_shock_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk_state = build_shock_risk_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    recent_event = get_recent_personal_life_event(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    recovery_state = get_player_recovery_state(db=db, player_id=player.id)
    practical_actions = _build_practical_actions(profile, recovery_state, recent_event)

    risk_label = str(risk_state.get("shock_risk_label", "low"))
    if recent_event.get("event_triggered"):
        recent_event_summary = str(recent_event.get("headline"))
    else:
        recent_event_summary = "No major personal shock today."
    active_recovery_summary = str(recovery_state.get("short_summary", "No active recovery window."))

    recommendation = (
        "Stabilize first: protect sleep/recovery and cash cushion before pushing growth."
        if risk_label in {"high", "moderate"}
        else "Keep balanced momentum and avoid unnecessary risk stacking."
    )
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "current_shock_risk_label": risk_label,
        "recent_event_summary": recent_event_summary,
        "active_recovery_summary": active_recovery_summary,
        "practical_current_actions": practical_actions,
        "short_recommendation": recommendation,
        "debug_meta": {
            "profile": profile,
            "risk_state": risk_state,
            "recent_event": recent_event,
            "recovery_state": recovery_state,
        },
    }


def build_personal_shock_system_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Return full composed Step 35 payload for UI/debug hydration."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    profile = build_personal_shock_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk = build_shock_risk_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    event = get_recent_personal_life_event(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    recovery = get_player_recovery_state(db=db, player_id=player.id)
    resilience = build_player_resilience_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    summary = build_personal_shock_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "shock_profile": profile,
        "risk_state": risk,
        "recent_event": event,
        "recovery_state": recovery,
        "resilience_summary": resilience,
        "shock_summary": summary,
        "debug_meta": {
            "day_number": int(day),
            "catalog_size": int(len(PERSONAL_EVENT_CATALOG)),
            "supported_severity_bands": sorted(SEVERITY_ORDER.keys()),
            "supported_event_families": sorted({row.event_family for row in PERSONAL_EVENT_CATALOG}),
        },
    }
