"""Backend-first main-shift lifecycle helpers."""

from __future__ import annotations

import logging
import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytz
from sqlalchemy.orm import Session

from app.engine.balance_config import (
    apply_health_decay_rate,
    apply_income_multiplier,
    apply_stress_sensitivity,
)
from app.engine.daily_engine import get_or_create_game_state
from app.engine.work_engine import MAX_FATIGUE_FOR_SECOND_SHIFT, MAX_MAIN_HOURS_PER_DAY, MAX_TOTAL_HOURS_PER_DAY
from app.models.contribution_event import ContributionEvent
from app.models.job_action import JobAction
from app.models.job_definition import JOB_CATALOG, MAIN_JOBS
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.xgp_transaction import XGPTransaction
from app.services.job_progress_service import normalize_shift_type, upsert_employment_foundation, work_xp_for_hours
from app.services.player_transaction_log_service import record_player_transaction

logger = logging.getLogger(__name__)

HOUSTON_TZ = pytz.timezone("America/Chicago")
SHIFT_STATUS_IDLE = "idle"
SHIFT_STATUS_ACTIVE = "active"
SHIFT_STATUS_COMPLETED = "completed"
RIDESHARE_DAILY_CAP = 6


def get_houston_now() -> datetime:
    return datetime.now(HOUSTON_TZ)


def _as_houston(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return HOUSTON_TZ.localize(value)
    return value.astimezone(HOUSTON_TZ)


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _q4(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0001"))


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _current_game_day(db: Session) -> int:
    return int(get_or_create_game_state(db).current_day)


def _configured_shift_duration_seconds(hours_worked: int) -> int:
    direct_seconds = os.getenv("SHIFT_TIMER_SECONDS") or os.getenv("EXPO_PUBLIC_SHIFT_TIMER_SECONDS")
    if direct_seconds:
        try:
            return max(30, int(float(direct_seconds)))
        except Exception:
            pass

    short_mode = str(
        os.getenv("SHIFT_TIMER_SHORT_MODE")
        or os.getenv("EXPO_PUBLIC_SHIFT_TIMER_SHORT_MODE")
        or ""
    ).strip().lower()
    if short_mode in {"1", "true", "yes", "on"}:
        return 90

    return max(1, int(hours_worked)) * 60 * 60


def _maybe_reset_daily_counters(player: Player, current_day: int) -> None:
    if player.last_worked_day == current_day:
        return

    player.main_job_hours_today = 0
    player.side_job_hours_today = 0
    player.total_hours_worked_today = 0
    player.work_actions_today = 0
    player.hours_available = 16

    if not bool(getattr(player, "main_shift_active_flag", False)):
        player.main_shift_status = SHIFT_STATUS_IDLE
        player.main_shift_started_at = None
        player.main_shift_ends_at = None
        player.main_shift_job_name = None
        player.main_shift_shift_type = None
        player.main_shift_hours = 0
        player.main_shift_number = 0


def _get_or_create_player_daily_state_in_txn(
    db: Session,
    player: Player,
    *,
    day_number: int,
    hours_available_start: int | None = None,
    cash_start: Decimal | None = None,
    stress_start: int | None = None,
    health_start: int | None = None,
) -> PlayerDailyState:
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == day_number,
        )
        .first()
    )
    if pds is not None:
        return pds

    cash_value = _q4(cash_start if cash_start is not None else getattr(player, "cash", 0))
    pds = PlayerDailyState(
        player_id=player.id,
        day_number=day_number,
        hours_available_start=int(hours_available_start if hours_available_start is not None else int(player.hours_available or 0)),
        hours_available_end=int(player.hours_available or 0),
        worked_main_job=False,
        did_settlement=False,
        stress_start=int(stress_start if stress_start is not None else int(player.stress or 0)),
        stress_end=int(player.stress or 0),
        health_start=int(health_start if health_start is not None else int(player.health or 0)),
        health_end=int(player.health or 0),
        cash_start=cash_value,
        cash_end=_q4(getattr(player, "cash", 0)),
        main_shift_hours_today=0,
        side_income_hours=0,
        side_income_gross_xgp=0,
        side_income_fuel_cost_xgp=0,
        side_income_net_xgp=0,
    )
    db.add(pds)
    db.flush()
    return pds


def _validate_main_shift_start(player: Player, *, job_name: str, hours_worked: int, shift_number: int) -> None:
    if job_name not in MAIN_JOBS:
        raise ValueError(f"Main shift requires a main job. Received '{job_name}'.")

    if job_name != str(getattr(player, "main_job", None) or "").strip().lower():
        raise ValueError(f"Your assigned main job is '{player.main_job}', not '{job_name}'.")

    if hours_worked < 1 or hours_worked > MAX_MAIN_HOURS_PER_DAY:
        raise ValueError(
            f"Main job shifts cannot exceed {MAX_MAIN_HOURS_PER_DAY} hours. Requested: {hours_worked}."
        )

    if int(player.work_actions_today or 0) >= 2:
        raise ValueError("You have already completed the maximum of 2 work actions today.")

    if int(player.health or 0) <= 15:
        raise ValueError(f"Health is too low to work ({player.health}/100). Minimum required: 16.")

    if shift_number == 2 and float(player.fatigue or 0) >= MAX_FATIGUE_FOR_SECOND_SHIFT:
        raise ValueError(
            f"Fatigue is too high for a second shift ({float(player.fatigue or 0):.1f}/100). "
            f"Must be below {MAX_FATIGUE_FOR_SECOND_SHIFT}."
        )

    if int(player.main_job_hours_today or 0) > 0:
        raise ValueError("You have already worked your main job shift today.")

    if int(player.main_job_hours_today or 0) + hours_worked > MAX_MAIN_HOURS_PER_DAY:
        raise ValueError(
            f"Main job hour cap is {MAX_MAIN_HOURS_PER_DAY} hours/day. "
            f"You already worked {player.main_job_hours_today} main-shift hours."
        )

    if int(player.total_hours_worked_today or 0) + hours_worked > MAX_TOTAL_HOURS_PER_DAY:
        hours_left = MAX_TOTAL_HOURS_PER_DAY - int(player.total_hours_worked_today or 0)
        raise ValueError(
            f"Total work cap is {MAX_TOTAL_HOURS_PER_DAY} hours/day. "
            f"You can work at most {hours_left} more hours today."
        )

    if hours_worked > int(player.hours_available or 0):
        raise ValueError(
            f"Not enough available hours. Requested {hours_worked}h but only {player.hours_available}h remaining today."
        )


def _shift_number_for_start(player: Player) -> int:
    return int(player.work_actions_today or 0) + 1


def _productivity(player: Player, *, shift_number: int) -> float:
    raw = (
        1.0
        - 0.004 * float(player.stress or 0)
        - 0.003 * (100.0 - float(player.health or 100))
        - 0.002 * float(player.fatigue or 0)
        + 0.01 * float(player.skill_level or 1)
    )
    clamped = max(0.45, min(1.10, raw))
    if shift_number == 2:
        clamped *= 0.85
    return clamped


def _stress_change(job_base_stress: int, *, hours_worked: int, shift_number: int, overtime_penalty: bool) -> int:
    gain = job_base_stress + round(hours_worked * 0.6)
    if overtime_penalty:
        gain += 2
    if shift_number == 2:
        gain = round(gain * 1.35)
    return gain


def _health_loss(*, hours_worked: int, shift_number: int, overtime_penalty: bool) -> int:
    if hours_worked < 4:
        loss = 0
    elif hours_worked < 8:
        loss = 1
    else:
        loss = 2
    if overtime_penalty:
        loss += 1
    if shift_number == 2:
        loss += 1
    return loss


def _fatigue_change(*, hours_worked: int, shift_number: int) -> float:
    gain = hours_worked * 0.8
    if shift_number == 2:
        gain *= 1.4
    return gain


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def build_work_state_payload(db: Session, player: Player, *, now_houston: datetime | None = None) -> dict[str, Any]:
    now = _as_houston(now_houston) or get_houston_now()
    current_day = _current_game_day(db)
    _maybe_reset_daily_counters(player, current_day)
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == current_day,
        )
        .first()
    )

    shift_started_at = _as_houston(getattr(player, "main_shift_started_at", None))
    shift_ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    shift_completed_at = _as_houston(getattr(player, "main_shift_completed_at", None))
    active_shift = bool(getattr(player, "main_shift_active_flag", False) and getattr(player, "main_shift_status", "") == SHIFT_STATUS_ACTIVE)
    shift_expired = bool(active_shift and shift_ends_at and now >= shift_ends_at)
    main_shift_hours_today = _safe_float(
        getattr(pds, "main_shift_hours_today", None),
        _safe_float(getattr(player, "main_job_hours_today", 0), 0.0),
    )
    side_income_hours_today = _safe_float(getattr(pds, "side_income_hours", 0), 0.0)
    recovery_hours_today = _safe_float(getattr(pds, "recovery_hours_today", getattr(pds, "recovery_hours", 0)) if pds is not None else 0, 0.0)
    total_time_used_today = _safe_float(getattr(pds, "total_time_used_today", getattr(pds, "total_hours_used", 0)) if pds is not None else 0, 0.0)

    completed_shift_confirmed = bool(
        not active_shift
        and str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE) == SHIFT_STATUS_COMPLETED
        and int(getattr(player, "last_worked_day", 0) or 0) == current_day
        and main_shift_hours_today > 0
    )
    day_settled = int(getattr(player, "last_settled_day", 0) or 0) == current_day
    remaining_side_cap = max(0.0, float(RIDESHARE_DAILY_CAP) - side_income_hours_today)
    rideshare_unlocked = completed_shift_confirmed
    rideshare_available = bool(
        rideshare_unlocked
        and not day_settled
        and remaining_side_cap >= 1.0
        and int(getattr(player, "hours_available", 0) or 0) >= 1
    )

    return {
        "player_id": str(player.id),
        "current_houston_time": now.isoformat(),
        "current_game_day": current_day,
        "day_settled": day_settled,
        "shift_status": str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE),
        "main_shift_active_flag": active_shift,
        "shift_started_at": shift_started_at.isoformat() if shift_started_at else None,
        "shift_ends_at": shift_ends_at.isoformat() if shift_ends_at else None,
        "shift_completed_at": shift_completed_at.isoformat() if shift_completed_at else None,
        "shift_job_name": str(getattr(player, "main_shift_job_name", None) or getattr(player, "main_job", None) or ""),
        "shift_type": str(getattr(player, "main_shift_shift_type", None) or "standard_shift"),
        "shift_hours": int(getattr(player, "main_shift_hours", 0) or 0),
        "shift_number": int(getattr(player, "main_shift_number", 0) or 0),
        "shift_expired": shift_expired,
        "shift_found": active_shift,
        "hours_available": int(getattr(player, "hours_available", 0) or 0),
        "main_shift_hours_today": round(main_shift_hours_today, 4),
        "side_income_hours_today": round(side_income_hours_today, 4),
        "recovery_hours_today": round(recovery_hours_today, 4),
        "total_time_used_today": round(total_time_used_today, 4),
        "last_completed_shift": {
            "earned_cash_xgp": round(_safe_float(getattr(player, "main_shift_last_cash_xgp", 0), 0.0), 4),
            "xp_gained": int(getattr(player, "main_shift_last_xp_gained", 0) or 0),
            "stress_change": int(getattr(player, "main_shift_last_stress_delta", 0) or 0),
            "health_change": int(getattr(player, "main_shift_last_health_delta", 0) or 0),
        },
        "rideshare_unlocked": rideshare_unlocked,
        "rideshare_available": rideshare_available,
        "remaining_side_income_hours_today": round(remaining_side_cap, 4),
    }


def start_main_shift(
    db: Session,
    *,
    player: Player,
    job_name: str,
    shift_type: str | None,
    hours_worked: int,
    now_houston: datetime | None = None,
) -> dict[str, Any]:
    current_day = _current_game_day(db)
    _maybe_reset_daily_counters(player, current_day)
    now = _as_houston(now_houston) or get_houston_now()

    resolve_expired_shift_if_needed(db, player=player, now_houston=now)

    if bool(getattr(player, "main_shift_active_flag", False)) and str(getattr(player, "main_shift_status", "")) == SHIFT_STATUS_ACTIVE:
        state = build_work_state_payload(db, player, now_houston=now)
        raise ValueError(
            f"Main shift is already active and ends at {state.get('shift_ends_at') or 'the scheduled Houston end time'}."
        )

    normalized_job = str(job_name or "").strip().lower()
    shift_number = _shift_number_for_start(player)
    _validate_main_shift_start(player, job_name=normalized_job, hours_worked=hours_worked, shift_number=shift_number)

    hours_before = int(player.hours_available or 0)
    cash_before = _money(getattr(player, "cash", 0))
    stress_before = int(player.stress or 0)
    health_before = int(player.health or 0)
    normalized_shift_type = normalize_shift_type(shift_type)

    duration_seconds = _configured_shift_duration_seconds(hours_worked)
    shift_ends_at = now + timedelta(seconds=duration_seconds)

    player.hours_available = max(0, hours_before - hours_worked)
    player.main_job_hours_today = int(player.main_job_hours_today or 0) + hours_worked
    player.total_hours_worked_today = int(player.total_hours_worked_today or 0) + hours_worked
    player.work_actions_today = int(player.work_actions_today or 0) + 1
    player.last_worked_day = current_day

    player.main_shift_active_flag = True
    player.main_shift_status = SHIFT_STATUS_ACTIVE
    player.main_shift_started_at = now
    player.main_shift_ends_at = shift_ends_at
    player.main_shift_completed_at = None
    player.main_shift_job_name = normalized_job
    player.main_shift_shift_type = normalized_shift_type
    player.main_shift_hours = int(hours_worked)
    player.main_shift_number = int(shift_number)
    player.main_shift_last_cash_xgp = Decimal("0.0000")
    player.main_shift_last_xp_gained = 0
    player.main_shift_last_stress_delta = 0
    player.main_shift_last_health_delta = 0

    pds = _get_or_create_player_daily_state_in_txn(
        db,
        player,
        day_number=current_day,
        hours_available_start=hours_before,
        cash_start=cash_before,
        stress_start=stress_before,
        health_start=health_before,
    )
    pds.main_shift_hours_today = _q4(Decimal(str(getattr(pds, "main_shift_hours_today", 0) or 0)) + Decimal(str(hours_worked)))
    pds.job_hours = _q4(Decimal(str(getattr(pds, "job_hours", 0) or 0)) + Decimal(str(hours_worked)))
    pds.total_hours_used = _q4(Decimal(str(getattr(pds, "total_hours_used", 0) or 0)) + Decimal(str(hours_worked)))
    pds.hours_available_end = int(player.hours_available or 0)
    pds.stress_end = int(player.stress or 0)
    pds.health_end = int(player.health or 0)
    pds.cash_end = _q4(getattr(player, "cash", 0))

    db.commit()
    db.refresh(player)

    work_state = build_work_state_payload(db, player, now_houston=now)
    logger.info(
        "shift.start_main_shift succeeded.",
        extra={
            "player_id": str(player.id),
            "shift_started_at": work_state.get("shift_started_at"),
            "shift_ends_at": work_state.get("shift_ends_at"),
            "shift_status": work_state.get("shift_status"),
            "main_shift_hours_today": work_state.get("main_shift_hours_today"),
            "side_income_hours_today": work_state.get("side_income_hours_today"),
            "rideshare_unlocked": work_state.get("rideshare_unlocked"),
        },
    )
    return work_state


def finalize_active_main_shift(
    db: Session,
    *,
    player: Player,
    now_houston: datetime | None = None,
    trigger: str = "manual_finalize",
    require_expired: bool = False,
) -> dict[str, Any]:
    now = _as_houston(now_houston) or get_houston_now()
    current_day = _current_game_day(db)
    _maybe_reset_daily_counters(player, current_day)

    active = bool(getattr(player, "main_shift_active_flag", False)) and str(getattr(player, "main_shift_status", "")) == SHIFT_STATUS_ACTIVE
    if not active:
        return build_work_state_payload(db, player, now_houston=now)

    shift_ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    if require_expired and shift_ends_at is not None and now < shift_ends_at:
        return build_work_state_payload(db, player, now_houston=now)

    job_name = str(getattr(player, "main_shift_job_name", None) or getattr(player, "main_job", None) or "").strip().lower()
    hours_worked = max(1, int(getattr(player, "main_shift_hours", 0) or 0))
    shift_number = max(1, int(getattr(player, "main_shift_number", 1) or 1))
    job_def = JOB_CATALOG.get(job_name)
    if job_def is None:
        raise ValueError(f"Cannot finalize unknown active main shift job '{job_name}'.")

    base_hourly_pay = job_def.monthly_salary / 30 / 8
    productivity = _productivity(player, shift_number=shift_number)
    earned_cash_raw = base_hourly_pay * hours_worked * productivity
    overtime_penalty = int(player.total_hours_worked_today or 0) > 8
    stress_change = _stress_change(job_def.base_stress, hours_worked=hours_worked, shift_number=shift_number, overtime_penalty=overtime_penalty)
    health_loss = _health_loss(hours_worked=hours_worked, shift_number=shift_number, overtime_penalty=overtime_penalty)
    fatigue_delta = _fatigue_change(hours_worked=hours_worked, shift_number=shift_number)

    earned_cash = apply_income_multiplier(earned_cash_raw)
    stress_change = apply_stress_sensitivity(stress_change)
    health_loss = apply_health_decay_rate(health_loss)
    health_delta = -int(health_loss)
    xp_gained = work_xp_for_hours(hours_worked)

    balance_before = _money(getattr(player, "cash", 0))
    stress_before = int(player.stress or 0)
    health_before = int(player.health or 0)

    player.cash = balance_before + Decimal(str(earned_cash))
    player.stress = _clamp_int(stress_before + int(stress_change), 0, 100)
    player.health = _clamp_int(health_before + health_delta, 0, 100)
    player.fatigue = max(0.0, min(100.0, float(player.fatigue or 0) + float(fatigue_delta)))
    player.main_shift_active_flag = False
    player.main_shift_status = SHIFT_STATUS_COMPLETED
    player.main_shift_completed_at = now
    player.main_shift_last_cash_xgp = _q4(earned_cash)
    player.main_shift_last_xp_gained = int(xp_gained)
    player.main_shift_last_stress_delta = int(stress_change)
    player.main_shift_last_health_delta = int(health_delta)

    action = JobAction(
        player_id=player.id,
        job_name=job_name,
        job_type="main",
        shift_number=shift_number,
        day=current_day,
        hours_worked=hours_worked,
        base_hourly_pay=round(base_hourly_pay, 4),
        productivity=round(productivity, 4),
        earned_cash=_money(earned_cash),
        stress_change=int(stress_change),
        health_change=int(health_delta),
        fatigue_change=round(float(fatigue_delta), 4),
        overtime_penalty_applied=bool(overtime_penalty),
        hours_remaining_after=int(player.hours_available or 0),
    )
    db.add(action)
    db.flush()

    balance_after = _money(getattr(player, "cash", 0))
    xgp_tx = XGPTransaction(
        player_id=player.id,
        transaction_type="job_income",
        direction="in",
        amount=_q4(earned_cash),
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type="job_action",
        reference_id=str(action.id),
        description=f"Main job income - {job_name} shift {shift_number}",
    )
    db.add(xgp_tx)

    record_player_transaction(
        db,
        player=player,
        day=current_day,
        transaction_type="wage_income",
        category="work",
        quantity=hours_worked,
        unit_price=round(base_hourly_pay, 4),
        gross_amount=_q4(earned_cash),
        fee_amount=0,
        net_cash_delta=_q4(earned_cash),
        resulting_cash_balance=balance_after,
        metadata={
            "job_name": job_name,
            "job_type": "main",
            "shift_number": shift_number,
            "productivity": round(productivity, 4),
            "trigger": trigger,
            "main_shift_status": SHIFT_STATUS_COMPLETED,
            "houston_finalized_at": now.isoformat(),
        },
    )

    contribution = ContributionEvent(
        player_id=player.id,
        event_type="job_work",
        xgp_value=_q4(earned_cash),
        event_units=float(hours_worked),
        metadata_json=json.dumps(
            {
                "job_id": job_name,
                "job_type": "main",
                "day_number": current_day,
                "shift_number": shift_number,
                "productivity_multiplier": round(productivity, 4),
                "base_hourly_pay": round(base_hourly_pay, 4),
                "overtime_penalty": bool(overtime_penalty),
                "trigger": trigger,
                "houston_finalized_at": now.isoformat(),
            }
        ),
    )
    db.add(contribution)

    pds = _get_or_create_player_daily_state_in_txn(db, player, day_number=current_day)
    pds.worked_main_job = True
    pds.worked_hours = int(getattr(pds, "worked_hours", 0) or 0) + hours_worked
    pds.gross_income_xgp = _q4(Decimal(str(getattr(pds, "gross_income_xgp", 0) or 0)) + Decimal(str(earned_cash)))
    pds.hours_available_end = int(player.hours_available or 0)
    pds.stress_end = int(player.stress or 0)
    pds.health_end = int(player.health or 0)
    pds.cash_end = _q4(getattr(player, "cash", 0))

    try:
        player.lifetime_xgp_earned = round(float(player.lifetime_xgp_earned or 0.0) + float(earned_cash), 4)
    except AttributeError:
        pass

    upsert_employment_foundation(
        db,
        player=player,
        settled_day=max(1, _safe_int(getattr(player, "last_settled_day", None), 0) + 1),
        job_key=job_name,
        shift_type=getattr(player, "main_shift_shift_type", None),
        grant_work_xp=xp_gained,
    )

    db.commit()
    db.refresh(player)

    work_state = build_work_state_payload(db, player, now_houston=now)
    logger.info(
        "shift.finalize_active_main_shift completed.",
        extra={
            "player_id": str(player.id),
            "shift_started_at": work_state.get("shift_started_at"),
            "shift_ends_at": work_state.get("shift_ends_at"),
            "current_houston_time": work_state.get("current_houston_time"),
            "shift_expired": bool(shift_ends_at and now >= shift_ends_at) if shift_ends_at else False,
            "shift_finalized": True,
            "work_income_awarded": work_state.get("last_completed_shift", {}).get("earned_cash_xgp"),
            "xp_awarded": work_state.get("last_completed_shift", {}).get("xp_gained"),
            "rideshare_unlocked": work_state.get("rideshare_unlocked"),
            "side_income_hours_today": work_state.get("side_income_hours_today"),
            "main_shift_hours_today": work_state.get("main_shift_hours_today"),
            "trigger": trigger,
        },
    )
    return work_state


def resolve_expired_shift_if_needed(
    db: Session,
    player: Player | None = None,
    *,
    player_id: UUID | str | None = None,
    now_houston: datetime | None = None,
) -> dict[str, Any]:
    if player is None:
        if player_id is None:
            raise ValueError("resolve_expired_shift_if_needed requires player or player_id.")
        target_id = UUID(str(player_id))
        player = db.query(Player).filter(Player.id == target_id).first()
        if player is None:
            raise ValueError("Player not found for expired-shift resolution.")

    now = _as_houston(now_houston) or get_houston_now()
    current_day = _current_game_day(db)
    _maybe_reset_daily_counters(player, current_day)
    started_at = _as_houston(getattr(player, "main_shift_started_at", None))
    ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    active_shift = bool(getattr(player, "main_shift_active_flag", False) and getattr(player, "main_shift_status", "") == SHIFT_STATUS_ACTIVE)
    expired = bool(active_shift and ends_at and now >= ends_at)

    logger.info(
        "shift.resolve_expired_shift_if_needed evaluated.",
        extra={
            "player_id": str(player.id),
            "active_shift_found": active_shift,
            "shift_started_at": started_at.isoformat() if started_at else None,
            "shift_ends_at": ends_at.isoformat() if ends_at else None,
            "current_houston_time": now.isoformat(),
            "shift_expired": expired,
            "shift_finalized": expired,
            "side_income_hours_today": _safe_float(
                getattr(
                    (
                        db.query(PlayerDailyState)
                        .filter(
                            PlayerDailyState.player_id == player.id,
                            PlayerDailyState.day_number == current_day,
                        )
                        .first()
                    ),
                    "side_income_hours",
                    0,
                ),
                0.0,
            ),
            "main_shift_hours_today": int(getattr(player, "main_job_hours_today", 0) or 0),
        },
    )

    if expired:
        return finalize_active_main_shift(
            db,
            player=player,
            now_houston=now,
            trigger="auto_resolve_expired_shift",
            require_expired=True,
        )

    return build_work_state_payload(db, player, now_houston=now)
