"""Backend-first main-shift lifecycle helpers."""

from __future__ import annotations

import logging
import os
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytz
from sqlalchemy import func, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.engine.career_config import CAREER_CONFIG, CERTIFICATION_CATALOG
from app.engine.balance_config import (
    apply_health_decay_rate,
    apply_income_multiplier,
    apply_stress_sensitivity,
)
from app.engine.daily_engine import get_or_create_game_state
from app.engine.work_engine import MAX_FATIGUE_FOR_SECOND_SHIFT, MAX_MAIN_HOURS_PER_DAY, MAX_TOTAL_HOURS_PER_DAY
from app.models.contribution_event import ContributionEvent
from app.models.gameplay_transaction import GameplayTransaction
from app.models.job_action import JobAction
from app.models.job_definition import MAIN_JOBS, resolve_job_definition
from app.models.player import Player
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.side_income_action import SideIncomeAction
from app.models.xgp_transaction import XGPTransaction
from app.services.dinner_survival_service import (
    compute_night_dinner_reminder,
    ensure_day_dinner_resolved,
    run_offline_survival_catchup,
)
from app.services.city_map_service import (
    build_city_map_snapshot,
    ensure_player_location,
    get_location_label,
    get_location_region,
    get_rideshare_location_profile,
    estimate_rideshare_pay_range,
)
from app.services.gameplay_transaction_service import record_gameplay_transaction
from app.services.job_key_service import normalize_main_job_key, supported_main_job_keys_text
from app.services.job_progress_service import normalize_shift_type, upsert_employment_foundation, work_xp_for_hours
from app.services.player_job_progression_service import (
    SHIFT_COMPLETION_XP_GAIN,
    award_completed_shift_xp,
    progression_lookup_map,
    safe_default_progression_for_job,
)
from app.services.player_daily_state_service import ensure_player_daily_state
from app.services.player_transaction_log_service import record_player_transaction

logger = logging.getLogger(__name__)

HOUSTON_TZ = pytz.timezone("America/Chicago")
SHIFT_STATUS_IDLE = "idle"
SHIFT_STATUS_ACTIVE = "active"
SHIFT_STATUS_COMPLETED = "completed"
RIDESHARE_DAILY_CAP = 6
GAME_EPOCH = date(2026, 1, 1)
MISSED_SHIFT_HEALTH_DELTA = -5
MISSED_SHIFT_STRESS_DELTA = 6
AUTO_ROLLOVER_MAX_DAYS = 30
HOUSTON_DAY_RESET_LABEL = "12:00 AM CT"

JOB_DISPLAY_NAMES: dict[str, str] = {
    "auto_mechanic": "Auto Mechanic",
    "aircraft_mechanic": "Aircraft Mechanic",
    "banker": "Banker",
    "chef": "Chef",
    "cleaner": "Cleaner",
    "warehouse_operator": "Warehouse Operator",
    "real_estate_agent": "Real Estate Agent",
    "retail": "Retail Worker",
    "delivery": "Delivery Driver",
}

JOB_SHIFT_MAP: dict[str, dict[str, str]] = {
    "banker": {"start": "10:00", "end": "18:00"},
    "chef": {"start": "09:00", "end": "17:00"},
    "cleaner": {"start": "07:00", "end": "15:00"},
    "warehouse_operator": {"start": "07:00", "end": "16:00"},
    "real_estate_agent": {"start": "10:00", "end": "18:00"},
    "retail": {"start": "10:00", "end": "18:00"},
    "delivery": {"start": "08:00", "end": "16:00"},
    "auto_mechanic": {"start": "08:00", "end": "17:00"},
    "aircraft_mechanic": {"start": "06:00", "end": "14:00"},
}

JOB_MARKET_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "job_key": "retail",
        "display_name": "Retail Worker",
        "tier": "entry",
        "stress_level": "Moderate",
        "certification_key": None,
        "future_unlock": False,
    },
    {
        "job_key": "delivery",
        "display_name": "Delivery Driver",
        "tier": "entry",
        "stress_level": "Moderate",
        "certification_key": None,
        "future_unlock": False,
    },
    {
        "job_key": "cleaner",
        "display_name": "Cleaner",
        "tier": "entry",
        "stress_level": "Low",
        "certification_key": None,
        "future_unlock": False,
    },
    {
        "job_key": "chef",
        "display_name": "Chef",
        "tier": "mid",
        "stress_level": "High",
        "certification_key": "chef_cert",
        "future_unlock": False,
    },
    {
        "job_key": "auto_mechanic",
        "display_name": "Auto Mechanic",
        "tier": "mid",
        "stress_level": "High",
        "certification_key": "auto_mechanic_cert",
        "future_unlock": False,
    },
    {
        "job_key": "warehouse_operator",
        "display_name": "Warehouse Operator",
        "tier": "mid",
        "stress_level": "Moderate",
        "certification_key": None,
        "future_unlock": False,
    },
    {
        "job_key": "aircraft_mechanic",
        "display_name": "Aircraft Mechanic",
        "tier": "high",
        "stress_level": "High",
        "certification_key": "aircraft_mechanic_cert",
        "future_unlock": False,
    },
    {
        "job_key": "banker",
        "display_name": "Banker",
        "tier": "high",
        "stress_level": "High",
        "certification_key": "banking_license",
        "future_unlock": False,
    },
    {
        "job_key": "real_estate_agent",
        "display_name": "Real Estate Agent",
        "tier": "high",
        "stress_level": "Moderate",
        "certification_key": "real_estate_license",
        "future_unlock": False,
    },
    {
        "job_key": "business_owner",
        "display_name": "Business Owner",
        "tier": "future",
        "stress_level": "Critical",
        "certification_key": None,
        "future_unlock": True,
    },
)


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


def _current_game_day_for_player(db: Session, player: Player) -> int:
    """Resolve in-game day for player-facing work/rideshare state.

    We prioritize whichever is ahead between:
    - global GameState day (legacy/global systems)
    - player's personal progression day (latest PlayerDailyState / last_settled_day)
    """
    global_day = _current_game_day(db)
    player_progress_day = max(1, int(getattr(player, "last_settled_day", 0) or 0) + 1)
    latest_pds = (
        db.query(PlayerDailyState)
        .filter(PlayerDailyState.player_id == player.id)
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .first()
    )
    if latest_pds is not None:
        pds_day = int(getattr(latest_pds, "day_number", player_progress_day) or player_progress_day)
        if bool(getattr(latest_pds, "did_settlement", False)):
            pds_day += 1
        player_progress_day = max(player_progress_day, pds_day)
    return max(global_day, player_progress_day)


def _day_to_date(day_number: int) -> date:
    return GAME_EPOCH + timedelta(days=max(1, int(day_number)) - 1)


def _parse_houston_hhmm(value: str | None) -> time | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None


def _format_houston_hhmm(value: str | None) -> str | None:
    parsed = _parse_houston_hhmm(value)
    if parsed is None:
        return None
    return datetime.combine(date(2026, 1, 1), parsed).strftime("%I:%M %p").lstrip("0")


def _format_houston_datetime_label(value: datetime | None) -> str | None:
    resolved = _as_houston(value)
    if resolved is None:
        return None
    return f"{resolved.strftime('%I:%M %p').lstrip('0')} CT"


def _is_table_available(db: Session, table_name: str) -> bool:
    normalized_name = str(table_name or "").strip()
    if not normalized_name:
        return False

    table_cache = db.info.setdefault("_table_exists_cache", {})
    cached = table_cache.get(normalized_name)
    if cached is not None:
        return bool(cached)

    bind = db.get_bind()
    if bind is None:
        table_cache[normalized_name] = False
        return False

    try:
        # Use the session's current connection so capability checks don't open
        # a separate transactional connection that can interfere with in-flight
        # writes on SQLite test sessions.
        available = bool(inspect(db.connection()).has_table(normalized_name))
    except Exception:
        available = False

    table_cache[normalized_name] = available
    return available


def _job_display_name(job_key: str | None) -> str:
    canonical = _canonical_main_job(job_key or "")
    if not canonical:
        return "No job selected"
    return JOB_DISPLAY_NAMES.get(canonical, canonical.replace("_", " ").title())


def _latest_employment_state_for_player(db: Session, player: Player) -> PlayerEmploymentState | None:
    if not _is_table_available(db, "player_employment_states"):
        return None
    try:
        return (
            db.query(PlayerEmploymentState)
            .filter(PlayerEmploymentState.player_id == player.id)
            .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
            .first()
        )
    except OperationalError:
        logger.warning(
            "shift.job_truth employment table unavailable; falling back to player main_job.",
            extra={"player_id": str(player.id)},
        )
        return None


def _latest_career_state_for_player(db: Session, player: Player) -> PlayerCareer | None:
    if not _is_table_available(db, "player_career_states"):
        return None
    try:
        return (
            db.query(PlayerCareer)
            .filter(PlayerCareer.player_id == player.id)
            .order_by(PlayerCareer.updated_at.desc(), PlayerCareer.created_at.desc())
            .first()
        )
    except OperationalError:
        logger.warning(
            "shift.job_truth career table unavailable; falling back to player main_job.",
            extra={"player_id": str(player.id)},
        )
        return None


def _resolve_job_truth_context(
    db: Session,
    *,
    player: Player,
    scheduled_shift_job_id: str | None,
    active_shift_job_id: str | None,
) -> dict[str, Any]:
    latest_employment = _latest_employment_state_for_player(db, player)
    latest_career = _latest_career_state_for_player(db, player)

    player_job_id = _canonical_main_job(getattr(player, "main_job", None))
    scheduled_job_id = _canonical_main_job(scheduled_shift_job_id or "")
    active_job_id = _canonical_main_job(active_shift_job_id or "")
    employment_job_id = _canonical_main_job(
        getattr(latest_employment, "current_job_code", None) if latest_employment is not None else None
    )
    career_job_id = _canonical_main_job(
        getattr(latest_career, "current_job_key", None) if latest_career is not None else None
    )

    authoritative_current_job_id = (
        active_job_id
        or player_job_id
        or career_job_id
        or employment_job_id
        or scheduled_job_id
    )
    ui_job_id = authoritative_current_job_id
    pay_calculation_job_id = active_job_id or authoritative_current_job_id

    if (
        latest_employment is not None
        and authoritative_current_job_id
        and employment_job_id == authoritative_current_job_id
    ):
        current_job_level = max(1, _safe_int(getattr(latest_employment, "skill_level", 1), 1))
    else:
        current_job_level = max(1, _safe_int(getattr(player, "skill_level", 1), 1))

    distinct_job_ids = {
        value
        for value in [
            player_job_id,
            scheduled_job_id,
            active_job_id,
            employment_job_id,
            career_job_id,
            pay_calculation_job_id,
            ui_job_id,
        ]
        if value
    }
    mismatch_detected = len(distinct_job_ids) > 1

    return {
        "authoritative_current_job_id": authoritative_current_job_id or "",
        "current_job_display_name": _job_display_name(authoritative_current_job_id),
        "current_job_level": int(current_job_level),
        "scheduled_shift_job_id": scheduled_job_id or "",
        "active_shift_job_id": active_job_id or "",
        "pay_calculation_job_id": pay_calculation_job_id or "",
        "ui_job_id": ui_job_id or "",
        "job_truth_mismatch_detected": mismatch_detected,
        "job_truth_sources": {
            "player.current_job_id": player_job_id or "",
            "player_profile.selected_job": player_job_id or "",
            "active_shift.job_id": active_job_id or "",
            "generated_shift.job_id": scheduled_job_id or "",
            "compensation_job_id": pay_calculation_job_id or "",
            "latest_work_session_label": _canonical_main_job(getattr(player, "main_shift_job_name", None) or "") or "",
            "frontend_cached_work_card_job": ui_job_id or "",
            "employment_state.current_job_code": employment_job_id or "",
            "career_state.current_job_key": career_job_id or "",
        },
    }


def _career_completed_certification_keys(career: PlayerCareer | None) -> set[str]:
    if career is None:
        return set()
    keys: set[str] = set()
    if bool(getattr(career, "certification_completed", False)):
        active_track = str(getattr(career, "certification_track_key", "") or "").strip().lower()
        if active_track:
            keys.add(active_track)
    raw_debug = getattr(career, "career_debug_json", None)
    if raw_debug:
        try:
            decoded = json.loads(raw_debug)
            rows = decoded.get("completed_certification_keys")
            if isinstance(rows, list):
                for row in rows:
                    key = str(row or "").strip().lower()
                    if key:
                        keys.add(key)
        except Exception:
            pass
    return keys


def _build_job_market_payload(
    *,
    player: Player,
    career: PlayerCareer | None,
    authoritative_current_job_id: str | None,
    progression_by_job: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    progression_by_job = progression_by_job or {}
    active_training_track = str(getattr(career, "certification_track_key", "") or "").strip().lower()
    active_training_completed = bool(getattr(career, "certification_completed", False))
    training_active = bool(active_training_track and not active_training_completed)
    completed_cert_keys = _career_completed_certification_keys(career)

    certification_rows: list[dict[str, Any]] = []
    for cert_key in [
        "chef_cert",
        "auto_mechanic_cert",
        "aircraft_mechanic_cert",
        "banking_license",
        "real_estate_license",
    ]:
        meta = CERTIFICATION_CATALOG.get(cert_key, {})
        required_days = int(meta.get("required_days") or 0)
        completed = cert_key in completed_cert_keys
        in_progress = bool(training_active and active_training_track == cert_key)
        progress_days = (
            int(getattr(career, "certification_progress_days", 0) or 0)
            if in_progress
            else (required_days if completed else 0)
        )
        certification_rows.append(
            {
                "certification_key": cert_key,
                "display_name": str(meta.get("display_name") or cert_key.replace("_", " ").title()),
                "unlocks_job": str(meta.get("unlocks_job") or ""),
                "duration_days": required_days,
                "cost_xgp": int(meta.get("cost_xgp") or 0),
                "completed": completed,
                "in_progress": in_progress,
                "progress_days": int(max(0, progress_days)),
                "days_remaining": int(max(0, required_days - progress_days)),
            }
        )

    canonical_current_job = _canonical_main_job(authoritative_current_job_id or getattr(player, "main_job", None))
    job_rows: list[dict[str, Any]] = []
    career_progression_rows: list[dict[str, Any]] = []
    for template in JOB_MARKET_TEMPLATES:
        job_key = str(template.get("job_key") or "")
        cert_key = str(template.get("certification_key") or "").strip().lower() or None
        cert_meta = CERTIFICATION_CATALOG.get(cert_key or "", {})
        is_future_unlock = bool(template.get("future_unlock"))
        is_current = bool(canonical_current_job and canonical_current_job == job_key)
        certification_completed = bool(not cert_key or cert_key in completed_cert_keys)
        supported_switch = bool(job_key in CAREER_CONFIG)

        if is_current:
            status = "current"
        elif is_future_unlock:
            status = "locked"
        elif certification_completed and supported_switch:
            status = "available"
        else:
            status = "locked"

        required_track_name = str(cert_meta.get("display_name") or "").strip()
        requirement_label = (
            "No certification needed"
            if not cert_key
            else f"Requires: {required_track_name or cert_key.replace('_', ' ').title()}"
        )
        can_start_training = bool(
            cert_key
            and not certification_completed
            and not is_future_unlock
            and cert_key in CERTIFICATION_CATALOG
        )
        can_switch = bool(status == "available")
        cfg = CAREER_CONFIG.get(job_key)
        base_salary = float(getattr(cfg, "base_pay_reference", 0) or 0)

        training_days_completed = (
            int(getattr(career, "certification_progress_days", 0) or 0)
            if training_active and cert_key and active_training_track == cert_key
            else (int(cert_meta.get("required_days") or 0) if certification_completed and cert_key else 0)
        )
        training_days_required = int(cert_meta.get("required_days") or 0) if cert_key else 0
        training_in_progress = bool(training_active and cert_key and active_training_track == cert_key)

        progression_snapshot = progression_by_job.get(job_key)
        if progression_snapshot is None and (is_current or training_in_progress):
            progression_snapshot = safe_default_progression_for_job(job_key)
        if is_future_unlock and not training_in_progress and job_key not in progression_by_job:
            progression_snapshot = None

        job_rows.append(
            {
                "job_key": job_key,
                "display_name": str(template.get("display_name") or _job_display_name(job_key)),
                "tier": str(template.get("tier") or "entry"),
                "base_salary_xgp": round(base_salary, 2),
                "stress_level": str(template.get("stress_level") or "Moderate"),
                "status": status,
                "is_current_job": is_current,
                "is_future_unlock": is_future_unlock,
                "requires_certification": bool(cert_key),
                "certification_key": cert_key,
                "certification_name": required_track_name,
                "certification_completed": certification_completed,
                "requirement_label": requirement_label,
                "can_start_training": can_start_training,
                "can_switch": can_switch,
                "training_in_progress": training_in_progress,
                "training_days_completed": training_days_completed,
                "training_days_required": training_days_required,
                "progression": progression_snapshot,
                "is_locked": bool(status == "locked"),
                "is_unlocked": bool(status in {"available", "current"}),
            }
        )
        career_progression_rows.append(
            {
                "job_key": job_key,
                "display_name": str(template.get("display_name") or _job_display_name(job_key)),
                "status": status,
                "locked": bool(status == "locked"),
                "requires_certification": bool(cert_key),
                "certification_key": cert_key,
                "certification_name": required_track_name or None,
                "requirement_label": requirement_label,
                "has_progression": bool(progression_snapshot),
                "job_level": int((progression_snapshot or {}).get("job_level") or 1),
                "promotion_tier": str((progression_snapshot or {}).get("promotion_tier") or "Junior"),
                "job_xp": int((progression_snapshot or {}).get("job_xp") or 0),
                "job_xp_to_next_level": int((progression_snapshot or {}).get("job_xp_to_next_level") or 0),
                "shifts_completed": int((progression_snapshot or {}).get("shifts_completed") or 0),
                "estimated_current_monthly_salary_xgp": round(
                    _safe_float((progression_snapshot or {}).get("estimated_current_monthly_salary_xgp"), 0.0),
                    2,
                ),
                "estimated_next_level_monthly_salary_xgp": round(
                    _safe_float((progression_snapshot or {}).get("estimated_next_level_monthly_salary_xgp"), 0.0),
                    2,
                ),
                "next_level_salary_increase_pct": round(
                    _safe_float((progression_snapshot or {}).get("next_level_salary_increase_pct"), 3.0),
                    2,
                ),
                "salary_preview_note": str(
                    (progression_snapshot or {}).get("salary_preview_note")
                    or "Estimated only - live payroll remains unchanged."
                ),
                "last_worked_at": (progression_snapshot or {}).get("last_worked_at"),
            }
        )

    active_cert_meta = CERTIFICATION_CATALOG.get(active_training_track, {})
    training_required = int(getattr(career, "certification_required_days", 0) or active_cert_meta.get("required_days") or 0)
    training_progress = int(getattr(career, "certification_progress_days", 0) or 0)

    return {
        "current_job_key": canonical_current_job or "",
        "current_job_display_name": _job_display_name(canonical_current_job),
        "has_main_job": bool(canonical_current_job),
        "jobs": job_rows,
        "certifications": certification_rows,
        "training_active": training_active,
        "training_certification_key": active_training_track if training_active else "",
        "training_certification_name": str(active_cert_meta.get("display_name") or "") if training_active else "",
        "training_days_completed": int(training_progress if training_active else 0),
        "training_days_required": int(training_required if training_active else 0),
        "training_days_remaining": int(max(0, training_required - training_progress)) if training_active else 0,
        "completed_certification_keys": sorted(completed_cert_keys),
        "career_progression": career_progression_rows,
    }


def _resolve_houston_rollover_days(player: Player, *, now_houston: datetime) -> tuple[int, date]:
    today = now_houston.date()
    last_sync = getattr(player, "last_survival_resolved_date", None)
    if not isinstance(last_sync, date):
        updated_at = _as_houston(getattr(player, "updated_at", None))
        last_sync = (updated_at or now_houston).date()
    return max(0, int((today - last_sync).days)), last_sync


def _run_houston_auto_rollover_if_needed(
    db: Session,
    *,
    player: Player,
    now_houston: datetime,
) -> dict[str, Any]:
    missed_days, previous_sync_date = _resolve_houston_rollover_days(player, now_houston=now_houston)
    if missed_days <= 0:
        return {
            "applied_days": 0,
            "missed_days": 0,
            "truncated_days": 0,
            "previous_sync_date": str(previous_sync_date),
            "today_date": str(now_houston.date()),
            "settlement_days": [],
            "triggered": False,
        }

    if not _is_table_available(db, "stock_daily_prices"):
        logger.warning(
            "shift.auto_rollover skipped because stock_daily_prices table is unavailable.",
            extra={
                "player_id": str(player.id),
                "missed_days": int(missed_days),
                "previous_sync_date": str(previous_sync_date),
                "today_date": str(now_houston.date()),
            },
        )
        return {
            "applied_days": 0,
            "missed_days": int(missed_days),
            "truncated_days": int(missed_days),
            "previous_sync_date": str(previous_sync_date),
            "today_date": str(now_houston.date()),
            "settlement_days": [],
            "triggered": False,
            "skipped_reason": "missing_stock_daily_prices_table",
        }

    # Import lazily to avoid circular import at module load time.
    from app.services.day_progression_service import run_player_next_day

    days_to_apply = min(missed_days, AUTO_ROLLOVER_MAX_DAYS)
    settlement_days: list[int] = []
    for _ in range(days_to_apply):
        db.refresh(player)
        active_shift = bool(
            getattr(player, "main_shift_active_flag", False)
            and str(getattr(player, "main_shift_status", "") or "") == SHIFT_STATUS_ACTIVE
        )
        if active_shift:
            finalize_active_main_shift(
                db,
                player=player,
                now_houston=now_houston,
                trigger="auto_houston_midnight_rollover",
                require_expired=False,
            )
            db.refresh(player)

        settled = run_player_next_day(db, player.id)
        settlement_days.append(int(settled.get("settled_day") or 0))
        db.refresh(player)

    player.last_survival_resolved_date = now_houston.date()
    db.commit()
    db.refresh(player)

    return {
        "applied_days": int(days_to_apply),
        "missed_days": int(missed_days),
        "truncated_days": max(0, int(missed_days - days_to_apply)),
        "previous_sync_date": str(previous_sync_date),
        "today_date": str(now_houston.date()),
        "settlement_days": settlement_days,
        "triggered": True,
    }


def _empty_offline_survival_catchup(current_day: int) -> dict[str, Any]:
    return {
        "applied_days": 0,
        "missed_days": 0,
        "truncated_days": 0,
        "processed_days": [],
        "current_day_after": int(current_day),
        "sync_date_updated": False,
    }


def _should_run_offline_survival_catchup(player: Player, *, current_day: int) -> bool:
    # Dinner/survival catchup should only process days that have already been
    # settled; running it on an open current day can create unintended costs.
    return int(getattr(player, "last_settled_day", 0) or 0) >= int(current_day)


def _scheduled_shift_context(player: Player, *, day_number: int, now_houston: datetime) -> dict[str, Any]:
    resolved_now = _as_houston(now_houston) or get_houston_now()
    resolved_date = _day_to_date(day_number)
    canonical_main_job = _canonical_main_job(getattr(player, "main_job", None))
    day_of_week = resolved_date.strftime("%A")
    is_weekend = resolved_date.weekday() >= 5
    shift_template = JOB_SHIFT_MAP.get(canonical_main_job or "")
    scheduled_shift_start = str((shift_template or {}).get("start") or "")
    scheduled_shift_end = str((shift_template or {}).get("end") or "")
    scheduled_start_time = _parse_houston_hhmm(scheduled_shift_start)
    scheduled_end_time = _parse_houston_hhmm(scheduled_shift_end)
    current_local_time = resolved_now.timetz().replace(tzinfo=None)
    current_day_matches_houston_date = bool(resolved_now.date() == resolved_date)
    reached_shift_end = bool(
        current_day_matches_houston_date
        and scheduled_end_time
        and current_local_time >= scheduled_end_time
    )
    passed_shift_end = bool(
        current_day_matches_houston_date
        and scheduled_end_time
        and current_local_time > scheduled_end_time
    )
    return {
        "day_of_week": day_of_week,
        "current_day_matches_houston_date": current_day_matches_houston_date,
        "is_weekend": is_weekend,
        "has_main_job": bool(canonical_main_job),
        "canonical_main_job": canonical_main_job or "",
        "shift_required_today": bool(canonical_main_job and not is_weekend and shift_template),
        "scheduled_shift_start": scheduled_shift_start or None,
        "scheduled_shift_end": scheduled_shift_end or None,
        "scheduled_shift_start_label": _format_houston_hhmm(scheduled_shift_start),
        "scheduled_shift_end_label": _format_houston_hhmm(scheduled_shift_end),
        "scheduled_shift_window_label": (
            f"{_format_houston_hhmm(scheduled_shift_start)}-{_format_houston_hhmm(scheduled_shift_end)}"
            if scheduled_shift_start and scheduled_shift_end
            else None
        ),
        "reached_shift_end": reached_shift_end,
        "passed_shift_end": passed_shift_end,
    }


def _gameplay_event_exists(
    db: Session,
    *,
    player_id: UUID,
    day_number: int,
    category: str,
    description: str,
) -> bool:
    if not _is_table_available(db, "gameplay_transactions"):
        return False
    try:
        return bool(
            db.query(GameplayTransaction.id)
            .filter(
                GameplayTransaction.player_id == player_id,
                GameplayTransaction.day == int(day_number),
                GameplayTransaction.category == str(category or "").strip().lower(),
                GameplayTransaction.description == str(description or "").strip(),
            )
            .first()
        )
    except OperationalError:
        logger.warning(
            "shift.gameplay_event_exists gameplay_transactions table unavailable; treating as no existing event.",
            extra={
                "player_id": str(player_id),
                "day_number": int(day_number),
                "category": str(category or "").strip().lower(),
            },
        )
        return False


def _record_gameplay_event_once(
    db: Session,
    *,
    player: Player,
    day_number: int,
    category: str,
    description: str,
) -> bool:
    normalized_description = str(description or "").strip()
    if not normalized_description:
        return False
    if not _is_table_available(db, "gameplay_transactions"):
        return False
    if _gameplay_event_exists(
        db,
        player_id=player.id,
        day_number=day_number,
        category=category,
        description=normalized_description,
    ):
        return False
    try:
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category=category,
            amount=0,
            description=normalized_description,
        )
        return True
    except OperationalError:
        logger.warning(
            "shift.record_gameplay_event_once skipped because gameplay_transactions table is unavailable.",
            extra={
                "player_id": str(player.id),
                "day_number": int(day_number),
                "category": str(category or "").strip().lower(),
                "description": normalized_description,
            },
        )
        return False


def _did_work_for_day(player: Player, pds: PlayerDailyState | None, *, current_day: int, active_shift: bool) -> bool:
    main_shift_hours_today = _safe_float(
        getattr(pds, "main_shift_hours_today", None),
        _safe_float(getattr(player, "main_job_hours_today", 0), 0.0),
    )
    return bool(
        (bool(getattr(pds, "did_work", False)) if pds is not None else False)
        or (bool(getattr(pds, "worked_main_job", False)) if pds is not None else False)
        or (bool(getattr(pds, "salary_earned", 0)) if pds is not None else False)
        or (
            not active_shift
            and str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE) == SHIFT_STATUS_COMPLETED
            and int(getattr(player, "last_worked_day", 0) or 0) == current_day
            and main_shift_hours_today > 0
        )
        or (main_shift_hours_today > 0)
    )


def sync_shift_day_rules_if_needed(
    db: Session,
    *,
    player: Player,
    day_number: int | None = None,
    now_houston: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = _as_houston(now_houston) or get_houston_now()
    inferred_day = _current_game_day_for_player(db, player)
    current_day = max(1, int(day_number or inferred_day))
    if current_day == inferred_day:
        _maybe_reset_daily_counters(player, current_day)

    pds = _get_or_create_player_daily_state_in_txn(db, player, day_number=current_day)
    active_shift = bool(
        getattr(player, "main_shift_active_flag", False)
        and str(getattr(player, "main_shift_status", "") or "") == SHIFT_STATUS_ACTIVE
    )
    schedule = _scheduled_shift_context(player, day_number=current_day, now_houston=resolved_now)
    did_work_today = _did_work_for_day(player, pds, current_day=current_day, active_shift=active_shift)
    changes_applied = False

    if (
        schedule["shift_required_today"]
        and not active_shift
        and not did_work_today
        and schedule["passed_shift_end"]
        and not bool(getattr(pds, "missed_shift", False))
    ):
        player.health = _clamp_int(int(player.health or 0) + MISSED_SHIFT_HEALTH_DELTA, 0, 100)
        player.stress = _clamp_int(int(player.stress or 0) + MISSED_SHIFT_STRESS_DELTA, 0, 100)
        pds.missed_shift = True
        pds.did_work = False
        pds.salary_earned = Decimal("0")
        pds.missed_penalty = Decimal("0")
        pds.health_end = int(player.health or 0)
        pds.stress_end = int(player.stress or 0)
        pds.cash_end = _q4(getattr(player, "cash", 0))
        pds.notes = (
            f"Missed shift on {schedule['day_of_week']} "
            f"({schedule['scheduled_shift_window_label'] or 'unscheduled'})."
        )
        job_label = (schedule["canonical_main_job"] or "main job").replace("_", " ").title()
        window_label = schedule["scheduled_shift_window_label"] or "scheduled window"
        _record_gameplay_event_once(
            db,
            player=player,
            day_number=current_day,
            category="missed_work",
            description=f"Missed shift ({job_label} {window_label}) - no salary earned",
        )
        _record_gameplay_event_once(
            db,
            player=player,
            day_number=current_day,
            category="health_penalty",
            description=f"Health {MISSED_SHIFT_HEALTH_DELTA}, Stress +{MISSED_SHIFT_STRESS_DELTA}",
        )
        changes_applied = True

    rideshare_unlocked = bool(
        not active_shift
        and (
            bool(schedule["is_weekend"])
            or not bool(schedule["has_main_job"])
            or bool(schedule["reached_shift_end"])
        )
    )
    if rideshare_unlocked:
        if bool(schedule["is_weekend"]):
            rideshare_description = "Rideshare available all day (weekend)"
        elif not bool(schedule["has_main_job"]):
            rideshare_description = "Rideshare available all day (no required shift)"
        else:
            rideshare_description = f"Rideshare unlocked at {schedule['scheduled_shift_end_label'] or 'shift end'}"
        if _record_gameplay_event_once(
            db,
            player=player,
            day_number=current_day,
            category="ride_share",
            description=rideshare_description,
        ):
            changes_applied = True

    if changes_applied:
        db.flush()

    return {
        "applied": changes_applied,
        "current_day": current_day,
        "missed_shift_today": bool(getattr(pds, "missed_shift", False)),
        "rideshare_unlocked": rideshare_unlocked,
        "schedule": schedule,
    }


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


def _maybe_reset_daily_counters(player: Player, current_day: int) -> bool:
    if player.last_worked_day == current_day:
        return False

    reset_applied = bool(
        int(getattr(player, "main_job_hours_today", 0) or 0) != 0
        or int(getattr(player, "side_job_hours_today", 0) or 0) != 0
        or int(getattr(player, "total_hours_worked_today", 0) or 0) != 0
        or int(getattr(player, "work_actions_today", 0) or 0) != 0
        or int(getattr(player, "hours_available", 16) or 16) != 16
        or bool(getattr(player, "main_shift_active_flag", False))
        or str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE) != SHIFT_STATUS_IDLE
    )

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
    return reset_applied


def _rideshare_mode_for_houston_hour(hour: int) -> str:
    if 6 <= int(hour) < 9:
        return "morning_peak"
    if 9 <= int(hour) < 16:
        return "midday"
    if 16 <= int(hour) < 19:
        return "evening_peak"
    if int(hour) >= 20 or int(hour) < 1:
        return "night"
    return "midday"


def _build_rideshare_state(
    *,
    active_shift: bool,
    rideshare_unlocked: bool,
    day_settled: bool,
    is_weekend: bool,
    no_shift_scheduled: bool,
    scheduled_shift_end_label: str | None,
    side_income_hours_today: float,
    hours_available: int,
    current_location_key: str,
    now_houston: datetime,
) -> dict[str, Any]:
    max_trips = int(RIDESHARE_DAILY_CAP)
    trips_today = max(0, min(max_trips, int(round(float(side_income_hours_today or 0.0)))))
    hours_remaining_today = max(0, int(hours_available or 0))
    remaining_by_cap = max(0, max_trips - trips_today)
    remaining_trips = max(0, min(remaining_by_cap, hours_remaining_today))
    mode = _rideshare_mode_for_houston_hour(int(now_houston.hour))
    location_profile = get_rideshare_location_profile(current_location_key, mode)
    pay_min, pay_max = estimate_rideshare_pay_range(
        mode=mode,
        location_key=current_location_key,
        trips=1,
    )

    status = "available"
    reason = "Ride Share is available now."
    if day_settled:
        status = "not_enough_time"
        reason = "Day already settled. Start next day to run ride share."
    elif active_shift:
        status = "shift_active"
        reason = "Ride Share is unavailable during an active shift."
    elif not bool(location_profile.get("allowed")):
        status = "location_restricted"
        reason = str(
            location_profile.get("reason_if_blocked")
            or "Ride share is unavailable at this location."
        )
    elif not rideshare_unlocked:
        status = "shift_active"
        reason = f"Available after {scheduled_shift_end_label or 'shift end'} (shift end)."
    elif remaining_by_cap <= 0:
        status = "limit_reached"
        reason = "Daily ride share limit reached."
    elif hours_remaining_today <= 0 or remaining_trips <= 0:
        status = "not_enough_time"
        reason = "Not enough time remaining for ride share."
    elif is_weekend:
        reason = "Available all day (weekend)."
    elif no_shift_scheduled:
        reason = "Available all day (no required shift)."
    else:
        demand_note = str(location_profile.get("label") or "").strip()
        if demand_note:
            reason = f"Ride Share is available now. {demand_note}."

    return {
        "can_rideshare": status == "available",
        "status": status,
        "reason": reason,
        "trips_today": trips_today,
        "max_trips": max_trips,
        "remaining_trips": remaining_trips,
        "hours_remaining_today": hours_remaining_today,
        "mode": mode,
        "time_cost_per_trip_units": 1,
        "current_location_key": str(location_profile.get("location_key") or current_location_key),
        "current_location_label": str(location_profile.get("location_label") or get_location_label(current_location_key)),
        "current_location_region": str(location_profile.get("region") or get_location_region(current_location_key)),
        "location_tier": str(location_profile.get("tier") or "moderate"),
        "rideshare_allowed_here": bool(location_profile.get("allowed")),
        "location_label": str(location_profile.get("label") or ""),
        "demand_bonus_pct": _safe_float(location_profile.get("demand_bonus_pct"), 0.0),
        "stress_delta_modifier": _safe_int(location_profile.get("stress_delta_modifier"), 0),
        "estimated_pay_min_per_trip": round(pay_min, 2),
        "estimated_pay_max_per_trip": round(pay_max, 2),
    }


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
    cash_value = _q4(cash_start if cash_start is not None else getattr(player, "cash", 0))
    return ensure_player_daily_state(
        db,
        player=player,
        day_number=day_number,
        defaults={
            "hours_available_start": int(
                hours_available_start if hours_available_start is not None else int(player.hours_available or 0)
            ),
            "hours_available_end": int(player.hours_available or 0),
            "worked_main_job": False,
            "did_work": False,
            "did_settlement": False,
            "stress_start": int(stress_start if stress_start is not None else int(player.stress or 0)),
            "stress_end": int(player.stress or 0),
            "health_start": int(health_start if health_start is not None else int(player.health or 0)),
            "health_end": int(player.health or 0),
            "cash_start": cash_value,
            "cash_end": _q4(getattr(player, "cash", 0)),
            "shift_start": None,
            "shift_end": None,
            "salary_earned": 0,
            "missed_penalty": 0,
            "main_shift_hours_today": 0,
            "side_income_hours": 0,
            "side_income_gross_xgp": 0,
            "side_income_fuel_cost_xgp": 0,
            "side_income_net_xgp": 0,
        },
    )


def _canonical_main_job(value: object) -> str | None:
    return normalize_main_job_key(value, allow_aliases=True)


def _validate_main_shift_start(player: Player, *, job_name: str, hours_worked: int, shift_number: int) -> None:
    canonical_job_name = _canonical_main_job(job_name)
    canonical_player_job = _canonical_main_job(getattr(player, "main_job", None))
    if canonical_job_name not in MAIN_JOBS:
        raise ValueError(
            f"Invalid main job key: {job_name}. Expected one of: {supported_main_job_keys_text()}"
        )

    if not canonical_player_job:
        raise ValueError("No main job is assigned yet. Choose a job before starting a shift.")

    if canonical_player_job != canonical_job_name:
        raise ValueError(
            f"Your assigned main job is '{canonical_player_job or player.main_job}', not '{canonical_job_name}'."
        )

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
    current_day = _current_game_day_for_player(db, player)
    _maybe_reset_daily_counters(player, current_day)
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == current_day,
        )
        .first()
    )

    canonical_main_job = _canonical_main_job(getattr(player, "main_job", None))
    canonical_shift_job_name = _canonical_main_job(getattr(player, "main_shift_job_name", None) or "")
    shift_started_at = _as_houston(getattr(player, "main_shift_started_at", None))
    shift_ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    shift_completed_at = _as_houston(getattr(player, "main_shift_completed_at", None))
    active_shift = bool(getattr(player, "main_shift_active_flag", False) and getattr(player, "main_shift_status", "") == SHIFT_STATUS_ACTIVE)
    shift_expired = bool(active_shift and shift_ends_at and now >= shift_ends_at)
    schedule = _scheduled_shift_context(player, day_number=current_day, now_houston=now)
    resolved_shift_job_name = canonical_shift_job_name or _canonical_main_job(schedule["canonical_main_job"]) or canonical_main_job
    job_truth_context = _resolve_job_truth_context(
        db,
        player=player,
        scheduled_shift_job_id=_canonical_main_job(schedule["canonical_main_job"]),
        active_shift_job_id=canonical_shift_job_name if active_shift else None,
    )
    latest_career = _latest_career_state_for_player(db, player)
    try:
        progression_by_job = progression_lookup_map(db, player_id=player.id)
    except Exception:
        progression_by_job = {}
    job_market_payload = _build_job_market_payload(
        player=player,
        career=latest_career,
        authoritative_current_job_id=str(job_truth_context.get("authoritative_current_job_id") or ""),
        progression_by_job=progression_by_job,
    )
    current_job_key = str(job_truth_context.get("authoritative_current_job_id") or "").strip().lower()
    current_job_progression = progression_by_job.get(current_job_key) if current_job_key else None
    if current_job_key and current_job_progression is None:
        current_job_progression = safe_default_progression_for_job(current_job_key)
    career_job_progression = list(job_market_payload.get("career_progression") or [])
    if bool(job_truth_context.get("job_truth_mismatch_detected")):
        logger.warning(
            "shift.job_truth_mismatch_detected",
            extra={
                "player_id": str(player.id),
                "authoritative_current_job_id": str(job_truth_context.get("authoritative_current_job_id") or ""),
                "scheduled_shift_job_id": str(job_truth_context.get("scheduled_shift_job_id") or ""),
                "active_shift_job_id": str(job_truth_context.get("active_shift_job_id") or ""),
                "pay_calculation_job_id": str(job_truth_context.get("pay_calculation_job_id") or ""),
                "ui_job_id": str(job_truth_context.get("ui_job_id") or ""),
                "job_truth_sources": dict(job_truth_context.get("job_truth_sources") or {}),
            },
        )
    main_shift_hours_today = _safe_float(
        getattr(pds, "main_shift_hours_today", None),
        _safe_float(getattr(player, "main_job_hours_today", 0), 0.0),
    )
    side_income_hours_today_from_actions = _safe_float(
        (
            db.query(func.coalesce(func.sum(SideIncomeAction.hours_worked), 0))
            .filter(
                SideIncomeAction.player_id == player.id,
                SideIncomeAction.day_number == current_day,
            )
            .scalar()
            if _is_table_available(db, "side_income_actions")
            else 0
        ),
        0.0,
    )
    side_income_hours_today = max(0.0, side_income_hours_today_from_actions)
    rideshare_earned_today = _safe_float(
        (
            db.query(func.coalesce(func.sum(GameplayTransaction.amount), 0))
            .filter(
                GameplayTransaction.player_id == player.id,
                GameplayTransaction.day == int(current_day),
                GameplayTransaction.type == "income",
                GameplayTransaction.category == "ride_share",
            )
            .scalar()
            if _is_table_available(db, "gameplay_transactions")
            else 0
        ),
        0.0,
    )
    recovery_hours_today = _safe_float(getattr(pds, "recovery_hours_today", getattr(pds, "recovery_hours", 0)) if pds is not None else 0, 0.0)
    total_time_used_today = _safe_float(getattr(pds, "total_time_used_today", getattr(pds, "total_hours_used", 0)) if pds is not None else 0, 0.0)
    salary_earned_today = _safe_float(getattr(pds, "salary_earned", 0) if pds is not None else 0, 0.0)
    salary_earned_yesterday = _safe_float(
        (
            db.query(PlayerDailyState.salary_earned)
            .filter(
                PlayerDailyState.player_id == player.id,
                PlayerDailyState.day_number == max(1, current_day - 1),
            )
            .scalar()
        ),
        0.0,
    ) if current_day > 1 else 0.0

    completed_shift_confirmed = bool(
        not active_shift
        and str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE) == SHIFT_STATUS_COMPLETED
        and int(getattr(player, "last_worked_day", 0) or 0) == current_day
        and main_shift_hours_today > 0
    )
    no_shift_scheduled = not bool(schedule["has_main_job"])
    day_settled = int(getattr(player, "last_settled_day", 0) or 0) == current_day
    current_location_key = ensure_player_location(player)
    current_location_label = get_location_label(current_location_key)
    current_location_region = get_location_region(current_location_key)
    city_map_snapshot = build_city_map_snapshot(current_location_key=current_location_key)
    if day_settled and (pds is not None) and not bool(getattr(pds, "dinner_resolved", False)):
        ensure_day_dinner_resolved(
            db,
            player=player,
            day_number=current_day,
            source="day_settled_guard",
            now_houston=now,
            allow_debt_extension=True,
        )
        pds = (
            db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == player.id,
                PlayerDailyState.day_number == current_day,
            )
            .first()
        )

    dinner_resolved_today = bool(getattr(pds, "dinner_resolved", False)) if pds is not None else False
    dinner_mode_today = str(getattr(pds, "dinner_mode", "") or "") if pds is not None else ""
    dinner_cost_today = _safe_float(getattr(pds, "dinner_cost", 0) if pds is not None else 0, 0.0)
    food_debt_added_today = _safe_float(getattr(pds, "food_debt_added", 0) if pds is not None else 0, 0.0)
    needs_dinner_reminder, dinner_reminder_message = compute_night_dinner_reminder(
        day_settled=day_settled,
        active_shift=active_shift,
        dinner_resolved=dinner_resolved_today,
        now_houston=now,
    )
    if needs_dinner_reminder and pds is not None:
        pds.night_eat_reminder_shown = True

    rideshare_unlocked = bool(
        not active_shift
        and (
            bool(schedule["is_weekend"])
            or no_shift_scheduled
            or bool(schedule["reached_shift_end"])
        )
    )
    rideshare_state = _build_rideshare_state(
        active_shift=active_shift,
        rideshare_unlocked=rideshare_unlocked,
        day_settled=day_settled,
        is_weekend=bool(schedule["is_weekend"]),
        no_shift_scheduled=no_shift_scheduled,
        scheduled_shift_end_label=schedule["scheduled_shift_end_label"],
        side_income_hours_today=side_income_hours_today,
        hours_available=int(getattr(player, "hours_available", 0) or 0),
        current_location_key=current_location_key,
        now_houston=now,
    )
    rideshare_available = bool(rideshare_state.get("can_rideshare"))
    remaining_side_cap = max(0.0, float(rideshare_state.get("remaining_trips") or 0.0))
    did_work_today = _did_work_for_day(player, pds, current_day=current_day, active_shift=active_shift)
    missed_shift_today = bool(getattr(pds, "missed_shift", False)) if pds is not None else False

    return {
        "player_id": str(player.id),
        "current_houston_time": now.isoformat(),
        "current_houston_time_label": _format_houston_datetime_label(now),
        "current_game_day": current_day,
        "day_of_week": str(schedule["day_of_week"]),
        "is_weekend": bool(schedule["is_weekend"]),
        "day_rollover_timezone": "America/Chicago",
        "day_rollover_time_label": HOUSTON_DAY_RESET_LABEL,
        "next_day_rollover_time": "00:00",
        "day_settled": day_settled,
        "authoritative_current_job_id": str(job_truth_context.get("authoritative_current_job_id") or ""),
        "current_job_display_name": str(job_truth_context.get("current_job_display_name") or ""),
        "current_job_level": int(job_truth_context.get("current_job_level") or 1),
        "current_job_progression": current_job_progression,
        "career_job_progression": career_job_progression,
        "scheduled_shift_job_id": str(job_truth_context.get("scheduled_shift_job_id") or ""),
        "active_shift_job_id": str(job_truth_context.get("active_shift_job_id") or ""),
        "pay_calculation_job_id": str(job_truth_context.get("pay_calculation_job_id") or ""),
        "ui_job_id": str(job_truth_context.get("ui_job_id") or ""),
        "job_truth_mismatch_detected": bool(job_truth_context.get("job_truth_mismatch_detected")),
        "job_truth_sources": dict(job_truth_context.get("job_truth_sources") or {}),
        "job_market": job_market_payload,
        "shift_status": str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE),
        "main_shift_active_flag": active_shift,
        "shift_started_at": shift_started_at.isoformat() if shift_started_at else None,
        "shift_ends_at": shift_ends_at.isoformat() if shift_ends_at else None,
        "shift_completed_at": shift_completed_at.isoformat() if shift_completed_at else None,
        "shift_start_time_label": _format_houston_datetime_label(shift_started_at),
        "shift_end_time_label": _format_houston_datetime_label(shift_ends_at),
        "shift_completed_time_label": _format_houston_datetime_label(shift_completed_at),
        "shift_job_name": resolved_shift_job_name or "",
        "shift_job_display_name": _job_display_name(resolved_shift_job_name),
        "shift_type": str(getattr(player, "main_shift_shift_type", None) or "standard_shift"),
        "shift_hours": int(getattr(player, "main_shift_hours", 0) or 0),
        "shift_number": int(getattr(player, "main_shift_number", 0) or 0),
        "shift_expired": shift_expired,
        "shift_found": active_shift,
        "shift_completed_today": completed_shift_confirmed,
        "shift_required_today": bool(schedule["shift_required_today"]),
        "no_shift_scheduled": no_shift_scheduled,
        "scheduled_shift_start": schedule["scheduled_shift_start"],
        "scheduled_shift_end": schedule["scheduled_shift_end"],
        "scheduled_shift_start_label": schedule["scheduled_shift_start_label"],
        "scheduled_shift_end_label": schedule["scheduled_shift_end_label"],
        "scheduled_shift_window_label": schedule["scheduled_shift_window_label"],
        "hours_available": int(getattr(player, "hours_available", 0) or 0),
        "main_shift_hours_today": round(main_shift_hours_today, 4),
        "side_income_hours_today": round(side_income_hours_today, 4),
        "rideshare_time_today": round(side_income_hours_today, 4),
        "rideshare_earned_today": round(rideshare_earned_today, 4),
        "recovery_hours_today": round(recovery_hours_today, 4),
        "total_time_used_today": round(total_time_used_today, 4),
        "did_work_today": did_work_today,
        "salary_earned_today": round(salary_earned_today, 4),
        "salary_earned_yesterday": round(salary_earned_yesterday, 4),
        "pay_model": "daily_after_shift_completion",
        "pay_model_label": "Paid daily after shift completion",
        "salary_pending_until_completion": bool(active_shift),
        "missed_penalty_today": round(_safe_float(getattr(pds, "missed_penalty", 0) if pds is not None else 0, 0.0), 4),
        "missed_shift_today": missed_shift_today,
        "missed_shift_health_delta": MISSED_SHIFT_HEALTH_DELTA if missed_shift_today else 0,
        "missed_shift_stress_delta": MISSED_SHIFT_STRESS_DELTA if missed_shift_today else 0,
        "survival_penalty_today": bool(getattr(pds, "survival_penalty_applied", False)) if pds is not None else False,
        "survival_health_delta": -5 if bool(getattr(pds, "survival_penalty_applied", False)) else 0,
        "survival_stress_delta": 4 if bool(getattr(pds, "survival_penalty_applied", False)) else 0,
        "meals_recorded_today": _safe_int(getattr(pds, "meals_recorded", 0) if pds is not None else 0, 0),
        "current_location_key": current_location_key,
        "current_location_label": current_location_label,
        "current_location_region": current_location_region,
        "city_map": city_map_snapshot,
        "travel_options": city_map_snapshot.get("travel_options", []),
        "dinner_resolved_today": dinner_resolved_today,
        "dinner_mode_today": dinner_mode_today,
        "dinner_cost_today": round(dinner_cost_today, 4),
        "food_debt_added_today": round(food_debt_added_today, 4),
        "needs_dinner_reminder": needs_dinner_reminder,
        "dinner_reminder_message": dinner_reminder_message,
        "night_eat_reminder_shown": bool(getattr(pds, "night_eat_reminder_shown", False)) if pds is not None else False,
        "last_completed_shift": {
            "earned_cash_xgp": round(_safe_float(getattr(player, "main_shift_last_cash_xgp", 0), 0.0), 4),
            "xp_gained": int(getattr(player, "main_shift_last_xp_gained", 0) or 0),
            "stress_change": int(getattr(player, "main_shift_last_stress_delta", 0) or 0),
            "health_change": int(getattr(player, "main_shift_last_health_delta", 0) or 0),
        },
        "rideshare_state": rideshare_state,
        "rideshare_unlocked": rideshare_unlocked,
        "rideshare_available": rideshare_available,
        "rideshare_unlock_time_label": schedule["scheduled_shift_end_label"],
        "remaining_side_income_hours_today": round(remaining_side_cap, 4),
        "auto_finalized_previous_day": False,
        "auto_finalized_days_count": 0,
        "new_day_started_houston_time": False,
        "auto_rollover_recap_lines": [],
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
    current_day = _current_game_day_for_player(db, player)
    _maybe_reset_daily_counters(player, current_day)
    now = _as_houston(now_houston) or get_houston_now()

    resolve_expired_shift_if_needed(db, player=player, now_houston=now)
    current_work_state = build_work_state_payload(db, player, now_houston=now)
    if bool(current_work_state.get("missed_shift_today")):
        raise ValueError(
            "Today's required shift window has already ended. Ride share is the available work option now."
        )

    if bool(getattr(player, "main_shift_active_flag", False)) and str(getattr(player, "main_shift_status", "")) == SHIFT_STATUS_ACTIVE:
        raise ValueError(
            f"Main shift is already active and ends at {current_work_state.get('shift_end_time_label') or current_work_state.get('scheduled_shift_end_label') or 'the scheduled Houston end time'}."
        )

    canonical_player_job = _canonical_main_job(getattr(player, "main_job", None))
    if canonical_player_job and player.main_job != canonical_player_job:
        player.main_job = canonical_player_job
    normalized_job = _canonical_main_job(job_name)
    if not normalized_job:
        raise ValueError(
            f"Invalid main job key: {job_name}. Expected one of: {supported_main_job_keys_text()}"
        )
    shift_number = _shift_number_for_start(player)
    _validate_main_shift_start(player, job_name=normalized_job, hours_worked=hours_worked, shift_number=shift_number)
    logger.info(
        "shift.start_main_shift validating clock-in request.",
        extra={
            "player_id": str(player.id),
            "incoming_clock_in_payload": {
                "job_name": str(job_name or ""),
                "hours_worked": int(hours_worked),
                "shift_type": str(shift_type or ""),
            },
            "current_persisted_main_job": canonical_player_job,
            "resolved_job_name": normalized_job,
            "validation_result": "passed",
        },
    )

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
    pds.shift_start = now
    pds.shift_end = None
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
            "authoritative_current_job_id": work_state.get("authoritative_current_job_id"),
            "scheduled_shift_job_id": work_state.get("scheduled_shift_job_id"),
            "active_shift_job_id": work_state.get("active_shift_job_id"),
            "pay_calculation_job_id": work_state.get("pay_calculation_job_id"),
            "ui_job_id": work_state.get("ui_job_id"),
            "job_truth_mismatch_detected": bool(work_state.get("job_truth_mismatch_detected")),
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
    current_day = _current_game_day_for_player(db, player)
    reset_applied = _maybe_reset_daily_counters(player, current_day)

    active = bool(getattr(player, "main_shift_active_flag", False)) and str(getattr(player, "main_shift_status", "")) == SHIFT_STATUS_ACTIVE
    if not active:
        return build_work_state_payload(db, player, now_houston=now)

    shift_ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    if require_expired and shift_ends_at is not None and now < shift_ends_at:
        return build_work_state_payload(db, player, now_houston=now)

    job_name = _canonical_main_job(
        getattr(player, "main_shift_job_name", None) or getattr(player, "main_job", None) or ""
    ) or ""
    hours_worked = max(1, int(getattr(player, "main_shift_hours", 0) or 0))
    shift_number = max(1, int(getattr(player, "main_shift_number", 1) or 1))
    job_def = resolve_job_definition(job_name)
    if job_def is None:
        raise ValueError(f"Cannot finalize unknown active main shift job '{job_name}'.")
    if job_name and getattr(player, "main_job", None) != job_name:
        player.main_job = job_name

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
    record_gameplay_transaction(
        db,
        player=player,
        day=current_day,
        transaction_type="income",
        category="salary",
        amount=_q4(earned_cash),
        description=(
            f"Main job salary for Day {int(current_day)} "
            f"({str(getattr(job_def, 'title', None) or getattr(job_def, 'display_name', None) or job_name.replace('_', ' ').title())})"
        ),
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
    pds.did_work = True
    pds.shift_start = _as_houston(getattr(player, "main_shift_started_at", None)) or now
    pds.shift_end = now
    pds.worked_hours = int(getattr(pds, "worked_hours", 0) or 0) + hours_worked
    pds.salary_earned = _q4(Decimal(str(getattr(pds, "salary_earned", 0) or 0)) + Decimal(str(earned_cash)))
    pds.missed_penalty = Decimal("0")
    pds.gross_income_xgp = _q4(Decimal(str(getattr(pds, "gross_income_xgp", 0) or 0)) + Decimal(str(earned_cash)))
    pds.hours_available_end = int(player.hours_available or 0)
    pds.stress_end = int(player.stress or 0)
    pds.health_end = int(player.health or 0)
    pds.cash_end = _q4(getattr(player, "cash", 0))

    try:
        player.lifetime_xgp_earned = round(float(player.lifetime_xgp_earned or 0.0) + float(earned_cash), 4)
    except AttributeError:
        pass

    if _is_table_available(db, "player_employment_states") and _is_table_available(db, "stock_daily_prices"):
        upsert_employment_foundation(
            db,
            player=player,
            settled_day=max(1, _safe_int(getattr(player, "last_settled_day", None), 0) + 1),
            job_key=job_name,
            shift_type=getattr(player, "main_shift_shift_type", None),
            grant_work_xp=xp_gained,
        )
    progression_feedback: dict[str, Any] | None = None
    try:
        progression_feedback = award_completed_shift_xp(
            db,
            player_id=player.id,
            job_key=job_name,
            xp_gain=SHIFT_COMPLETION_XP_GAIN,
            worked_at=now,
        )
    except Exception:
        # Safe-mode guarantee: never block payroll/shift finalization on progression write failures.
        progression_feedback = None
    sync_shift_day_rules_if_needed(
        db,
        player=player,
        day_number=current_day,
        now_houston=now,
    )

    db.commit()
    db.refresh(player)

    work_state = build_work_state_payload(db, player, now_houston=now)
    if progression_feedback is not None:
        work_state["job_progression_feedback"] = progression_feedback
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
            "authoritative_current_job_id": work_state.get("authoritative_current_job_id"),
            "scheduled_shift_job_id": work_state.get("scheduled_shift_job_id"),
            "active_shift_job_id": work_state.get("active_shift_job_id"),
            "pay_calculation_job_id": work_state.get("pay_calculation_job_id"),
            "ui_job_id": work_state.get("ui_job_id"),
            "job_truth_mismatch_detected": bool(work_state.get("job_truth_mismatch_detected")),
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
    current_day = _current_game_day_for_player(db, player)
    reset_applied = _maybe_reset_daily_counters(player, current_day)
    started_at = _as_houston(getattr(player, "main_shift_started_at", None))
    ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    active_shift = bool(getattr(player, "main_shift_active_flag", False) and getattr(player, "main_shift_status", "") == SHIFT_STATUS_ACTIVE)
    expired = bool(active_shift and ends_at and now >= ends_at)

    preview_state = None
    try:
        preview_state = build_work_state_payload(db, player, now_houston=now)
    except Exception:
        preview_state = None

    logger.info(
        "shift.resolve_expired_shift_if_needed evaluated.",
        extra={
            "player_id": str(player.id),
            "previous_in_game_day": int(getattr(player, "last_worked_day", 0) or 0),
            "current_in_game_day": int(current_day),
            "daily_reset_applied": bool(reset_applied),
            "rideshare_counters_reset": bool(reset_applied),
            "active_shift_found": active_shift,
            "shift_started_at": started_at.isoformat() if started_at else None,
            "shift_ends_at": ends_at.isoformat() if ends_at else None,
            "current_houston_time": now.isoformat(),
            "shift_expired": expired,
            "shift_finalized": expired,
            "rideshare_status": (
                str(((preview_state or {}).get("rideshare_state") or {}).get("status") or "")
            ),
            "rideshare_can_run": bool(((preview_state or {}).get("rideshare_state") or {}).get("can_rideshare")),
            "rideshare_reason": str(((preview_state or {}).get("rideshare_state") or {}).get("reason") or ""),
            "rideshare_trips_today": int(((preview_state or {}).get("rideshare_state") or {}).get("trips_today") or 0),
            "rideshare_trips_today_after_reset": int(((preview_state or {}).get("rideshare_state") or {}).get("trips_today") or 0),
            "rideshare_max_trips": int(((preview_state or {}).get("rideshare_state") or {}).get("max_trips") or int(RIDESHARE_DAILY_CAP)),
            "current_location_key": str((preview_state or {}).get("current_location_key") or ""),
            "current_location_label": str((preview_state or {}).get("current_location_label") or ""),
            "travel_options_count": len(((preview_state or {}).get("travel_options") or [])),
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

    rollover_result = _run_houston_auto_rollover_if_needed(db, player=player, now_houston=now)
    if int(rollover_result.get("applied_days") or 0) > 0:
        refreshed_day = _current_game_day_for_player(db, player)
        sync_result = sync_shift_day_rules_if_needed(
            db,
            player=player,
            day_number=refreshed_day,
            now_houston=now,
        )
        if bool(sync_result.get("applied")):
            db.commit()
            db.refresh(player)
        work_state = build_work_state_payload(db, player, now_houston=now)
        applied_days = int(rollover_result.get("applied_days") or 0)
        recap_lines = [
            "Yesterday was automatically finalized."
            if applied_days == 1
            else f"{applied_days} days were automatically finalized.",
            "New day started in Houston time.",
        ]
        work_state["offline_survival_catchup"] = {
            "applied_days": 0,
            "missed_days": 0,
            "truncated_days": 0,
            "current_day_after": int(work_state.get("current_game_day") or refreshed_day),
            "sync_date_updated": False,
            "processed_days": [],
        }
        work_state["auto_day_rollover"] = rollover_result
        work_state["auto_finalized_previous_day"] = True
        work_state["auto_finalized_days_count"] = applied_days
        work_state["new_day_started_houston_time"] = True
        work_state["auto_rollover_recap_lines"] = recap_lines
        logger.info(
            "shift.resolve_expired_shift_if_needed applied Houston auto-rollover.",
            extra={
                "player_id": str(player.id),
                "applied_days": applied_days,
                "missed_days": int(rollover_result.get("missed_days") or 0),
                "truncated_days": int(rollover_result.get("truncated_days") or 0),
                "previous_sync_date": str(rollover_result.get("previous_sync_date") or ""),
                "today_date": str(rollover_result.get("today_date") or ""),
                "settlement_days": list(rollover_result.get("settlement_days") or []),
            },
        )
        return work_state

    if expired:
        finalized_state = finalize_active_main_shift(
            db,
            player=player,
            now_houston=now,
            trigger="auto_resolve_expired_shift",
            require_expired=True,
        )
        finalized_day = int(finalized_state.get("current_game_day") or _current_game_day_for_player(db, player))
        catchup_result = (
            run_offline_survival_catchup(
                db,
                player=player,
                current_day=finalized_day,
                now_houston=now,
            )
            if _should_run_offline_survival_catchup(player, current_day=finalized_day)
            else _empty_offline_survival_catchup(finalized_day)
        )
        if (
            int(catchup_result.get("applied_days") or 0) > 0
            or bool(catchup_result.get("sync_date_updated"))
        ):
            db.commit()
            db.refresh(player)
            finalized_state = build_work_state_payload(db, player, now_houston=now)
        finalized_state["offline_survival_catchup"] = catchup_result
        finalized_state["auto_day_rollover"] = rollover_result
        finalized_state["auto_finalized_previous_day"] = False
        finalized_state["auto_finalized_days_count"] = 0
        finalized_state["new_day_started_houston_time"] = False
        finalized_state["auto_rollover_recap_lines"] = []
        return finalized_state

    sync_result = sync_shift_day_rules_if_needed(
        db,
        player=player,
        day_number=current_day,
        now_houston=now,
    )
    catchup_result = (
        run_offline_survival_catchup(
            db,
            player=player,
            current_day=current_day,
            now_houston=now,
        )
        if _should_run_offline_survival_catchup(player, current_day=current_day)
        else _empty_offline_survival_catchup(current_day)
    )
    if (
        bool(sync_result.get("applied"))
        or int(catchup_result.get("applied_days") or 0) > 0
        or bool(catchup_result.get("sync_date_updated"))
    ):
        db.commit()
        db.refresh(player)

    work_state = build_work_state_payload(db, player, now_houston=now)
    work_state["offline_survival_catchup"] = catchup_result
    work_state["auto_day_rollover"] = rollover_result
    work_state["auto_finalized_previous_day"] = False
    work_state["auto_finalized_days_count"] = 0
    work_state["new_day_started_houston_time"] = False
    work_state["auto_rollover_recap_lines"] = []
    return work_state

