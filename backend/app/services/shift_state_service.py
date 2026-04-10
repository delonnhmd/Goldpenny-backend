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
from sqlalchemy.exc import IntegrityError, OperationalError
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
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.shift_salary_audit_log import ShiftSalaryAuditLog
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
from app.services.main_job_sync_service import inspect_and_repair_main_job_sync
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
WORK_STATUS_ON_SHIFT = "on_shift"
WORK_STATUS_OFF_SHIFT = "off_shift"
WORK_STATUS_OFF_SHIFT_AFTER_WORK = "off_shift_after_work"
SALARY_PAYMENT_STATUS_PENDING = "pending"
SALARY_PAYMENT_STATUS_POSTED = "posted"
SALARY_PAYMENT_STATUS_FAILED = "failed"
RIDESHARE_DAILY_CAP = 6
RIDESHARE_MIN_HEALTH = 16
RIDESHARE_MAX_STRESS = 95
GAME_EPOCH = date(2026, 1, 1)
MISSED_SHIFT_HEALTH_DELTA = -5
MISSED_SHIFT_STRESS_DELTA = 6
AUTO_ROLLOVER_MAX_DAYS = 30
HOUSTON_DAY_RESET_LABEL = "12:00 AM CT"
GAMEPLAY_TESTING_MODE_DEFAULTS: dict[str, Any] = {
    "shift_minutes": 15,
    "two_shift_jobs": ["retail_worker", "warehouse_operator"],
    "max_daily_shifts_for_two_shift_jobs": 2,
    "second_shift_overtime_multiplier": 1.5,
    "weekday_rideshare_cap": 6,
    "weekend_rideshare_cap": 18,
    "weekend_main_shift_enabled": False,
}

JOB_DISPLAY_NAMES: dict[str, str] = {
    "auto_mechanic": "Auto Mechanic",
    "aircraft_mechanic": "Aircraft Mechanic",
    "banker": "Banker",
    "chef": "Chef",
    "cleaner": "Cleaner",
    "warehouse_operator": "Warehouse Manager",
    "real_estate_agent": "Real Estate Agent",
    "retail": "Retail Seller",
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
        "display_name": "Retail Seller",
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
        "display_name": "Warehouse Manager",
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


def _format_houston_date_label(value: date | None) -> str | None:
    if value is None:
        return None
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def _env_flag(*names: str) -> bool:
    for name in names:
        raw = str(os.getenv(name) or "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
    return False


def get_gameplay_testing_mode_config() -> dict[str, Any]:
    enabled = _env_flag(
        "GAMEPLAY_TESTING_MODE",
        "EXPO_PUBLIC_GAMEPLAY_TESTING_MODE",
        "SHIFT_TIMER_SHORT_MODE",
        "EXPO_PUBLIC_SHIFT_TIMER_SHORT_MODE",
    )
    raw_two_shift_jobs = list(GAMEPLAY_TESTING_MODE_DEFAULTS["two_shift_jobs"])
    canonical_two_shift_jobs = sorted(
        {
            normalize_main_job_key(job_key, allow_aliases=True)
            for job_key in raw_two_shift_jobs
            if normalize_main_job_key(job_key, allow_aliases=True)
        }
    )
    return {
        "testing_mode": bool(enabled),
        "shift_minutes": int(GAMEPLAY_TESTING_MODE_DEFAULTS["shift_minutes"]),
        "two_shift_jobs": raw_two_shift_jobs,
        "two_shift_jobs_canonical": canonical_two_shift_jobs,
        "max_daily_shifts_for_two_shift_jobs": int(
            GAMEPLAY_TESTING_MODE_DEFAULTS["max_daily_shifts_for_two_shift_jobs"]
        ),
        "second_shift_overtime_multiplier": Decimal(
            str(GAMEPLAY_TESTING_MODE_DEFAULTS["second_shift_overtime_multiplier"])
        ),
        "weekday_rideshare_cap": int(GAMEPLAY_TESTING_MODE_DEFAULTS["weekday_rideshare_cap"]),
        "weekend_rideshare_cap": int(GAMEPLAY_TESTING_MODE_DEFAULTS["weekend_rideshare_cap"]),
        "weekend_main_shift_enabled": bool(
            GAMEPLAY_TESTING_MODE_DEFAULTS["weekend_main_shift_enabled"]
        ),
    }


def _testing_mode_job_eligible(job_key: object, *, config: dict[str, Any] | None = None) -> bool:
    resolved = normalize_main_job_key(job_key, allow_aliases=True)
    if not resolved:
        return False
    active_config = config or get_gameplay_testing_mode_config()
    return bool(active_config.get("testing_mode")) and resolved in set(
        active_config.get("two_shift_jobs_canonical") or []
    )


def _max_daily_main_shifts_for_job(
    job_key: object,
    *,
    config: dict[str, Any] | None = None,
) -> int:
    active_config = config or get_gameplay_testing_mode_config()
    if _testing_mode_job_eligible(job_key, config=active_config):
        return max(1, int(active_config.get("max_daily_shifts_for_two_shift_jobs") or 2))
    return 1


def _rideshare_daily_cap(*, is_weekend: bool, config: dict[str, Any] | None = None) -> int:
    active_config = config or get_gameplay_testing_mode_config()
    if bool(active_config.get("testing_mode")):
        if is_weekend:
            return max(1, int(active_config.get("weekend_rideshare_cap") or RIDESHARE_DAILY_CAP))
        return max(1, int(active_config.get("weekday_rideshare_cap") or RIDESHARE_DAILY_CAP))
    return int(RIDESHARE_DAILY_CAP)


def _testing_shift_length_label(config: dict[str, Any] | None = None) -> str:
    active_config = config or get_gameplay_testing_mode_config()
    if bool(active_config.get("testing_mode")):
        return f"{int(active_config.get('shift_minutes') or 15)} minutes"
    return "Standard shift schedule"


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


def _build_shift_salary_token(
    *,
    player_id: UUID,
    day_number: int,
    job_key: str,
    shift_number: int,
    hours_worked: int,
    shift_started_at: datetime | None,
) -> str:
    started_marker = (_as_houston(shift_started_at) or get_houston_now()).isoformat()
    return (
        f"{player_id}:{int(day_number)}:{str(job_key or '').strip().lower()}:"
        f"{int(shift_number)}:{int(hours_worked)}:{started_marker}"
    )


def _serialize_shift_salary_audit(row: ShiftSalaryAuditLog | None) -> dict[str, Any] | None:
    if row is None:
        return None
    overtime_multiplier_used = _q4(
        _overtime_multiplier_for_shift(
            job_key=str(getattr(row, "job_key", "") or ""),
            shift_number=int(getattr(row, "shift_number", 0) or 0),
        )
    )
    return {
        "audit_id": str(row.id),
        "player_id": str(row.player_id),
        "day_number": int(getattr(row, "day_number", 0) or 0),
        "shift_token": str(getattr(row, "shift_token", "") or ""),
        "shift_id": str(getattr(row, "shift_id", "") or ""),
        "job_key": str(getattr(row, "job_key", "") or ""),
        "job_display_name": str(getattr(row, "job_display_name", "") or ""),
        "shift_started_at": _as_houston(getattr(row, "shift_started_at", None)).isoformat()
        if getattr(row, "shift_started_at", None)
        else None,
        "shift_ends_at": _as_houston(getattr(row, "shift_ends_at", None)).isoformat()
        if getattr(row, "shift_ends_at", None)
        else None,
        "shift_completed_at": _as_houston(getattr(row, "shift_completed_at", None)).isoformat()
        if getattr(row, "shift_completed_at", None)
        else None,
        "shift_type": str(getattr(row, "shift_type", "") or ""),
        "shift_number": int(getattr(row, "shift_number", 0) or 0),
        "hours_worked": int(getattr(row, "hours_worked", 0) or 0),
        "trigger": str(getattr(row, "trigger", "") or ""),
        "payment_status": str(getattr(row, "payment_status", "") or ""),
        "failure_reason": str(getattr(row, "failure_reason", "") or ""),
        "base_monthly_salary": round(_safe_float(getattr(row, "base_monthly_salary", 0), 0.0), 4),
        "pay_snapshot_used": round(_safe_float(getattr(row, "pay_snapshot_used", 0), 0.0), 4),
        "base_hourly_pay": round(_safe_float(getattr(row, "base_hourly_pay", 0), 0.0), 4),
        "productivity_multiplier": round(_safe_float(getattr(row, "productivity_multiplier", 1), 1.0), 4),
        "income_multiplier": round(_safe_float(getattr(row, "income_multiplier", 1), 1.0), 4),
        "job_level_multiplier": round(_safe_float(getattr(row, "job_level_multiplier", 1), 1.0), 4),
        "gross_shift_pay": round(_safe_float(getattr(row, "gross_shift_pay", 0), 0.0), 4),
        "final_salary_paid": round(_safe_float(getattr(row, "final_salary_paid", 0), 0.0), 4),
        "xp_gained": int(getattr(row, "xp_gained", 0) or 0),
        "stress_change": int(getattr(row, "stress_change", 0) or 0),
        "health_change": int(getattr(row, "health_change", 0) or 0),
        "fatigue_change": round(_safe_float(getattr(row, "fatigue_change", 0), 0.0), 4),
        "overtime_penalty_applied": bool(getattr(row, "overtime_penalty_applied", False)),
        "overtime_applied": bool(overtime_multiplier_used > Decimal("1.0")),
        "overtime_multiplier_used": round(_safe_float(overtime_multiplier_used, 1.0), 4),
        "salary_transaction_id": str(getattr(row, "salary_transaction_id", "") or ""),
        "xgp_transaction_id": str(getattr(row, "xgp_transaction_id", "") or ""),
        "player_transaction_log_id": str(getattr(row, "player_transaction_log_id", "") or ""),
        "salary_posted_at": _as_houston(getattr(row, "salary_posted_at", None)).isoformat()
        if getattr(row, "salary_posted_at", None)
        else None,
        "cash_before": round(_safe_float(getattr(row, "cash_before", 0), 0.0), 4),
        "cash_after": round(_safe_float(getattr(row, "cash_after", 0), 0.0), 4),
        "transaction_confirmed": bool(getattr(row, "salary_transaction_id", None)),
    }


def _latest_shift_salary_audit_for_player(
    db: Session,
    *,
    player_id: UUID,
    day_number: int | None = None,
) -> ShiftSalaryAuditLog | None:
    if not _is_table_available(db, "shift_salary_audit_logs"):
        return None
    query = db.query(ShiftSalaryAuditLog).filter(ShiftSalaryAuditLog.player_id == player_id)
    if day_number is not None:
        query = query.filter(ShiftSalaryAuditLog.day_number == int(day_number))
    return (
        query.order_by(
            ShiftSalaryAuditLog.shift_completed_at.desc(),
            ShiftSalaryAuditLog.created_at.desc(),
        )
        .first()
    )


def _latest_posted_shift_salary_audit_for_player(db: Session, *, player_id: UUID) -> ShiftSalaryAuditLog | None:
    if not _is_table_available(db, "shift_salary_audit_logs"):
        return None
    return (
        db.query(ShiftSalaryAuditLog)
        .filter(
            ShiftSalaryAuditLog.player_id == player_id,
            ShiftSalaryAuditLog.payment_status == SALARY_PAYMENT_STATUS_POSTED,
        )
        .order_by(
            ShiftSalaryAuditLog.salary_posted_at.desc(),
            ShiftSalaryAuditLog.created_at.desc(),
        )
        .first()
    )


def _list_recent_shift_salary_audits_for_player(
    db: Session,
    *,
    player_id: UUID,
    limit: int = 3,
) -> list[dict[str, Any]]:
    if not _is_table_available(db, "shift_salary_audit_logs"):
        return []
    rows = (
        db.query(ShiftSalaryAuditLog)
        .filter(ShiftSalaryAuditLog.player_id == player_id)
        .order_by(
            ShiftSalaryAuditLog.shift_completed_at.desc(),
            ShiftSalaryAuditLog.created_at.desc(),
        )
        .limit(max(1, int(limit)))
        .all()
    )
    return [item for item in (_serialize_shift_salary_audit(row) for row in rows) if item is not None]


def _salary_status_from_audit(
    *,
    active_shift: bool,
    missed_shift_today: bool,
    current_day_audit: dict[str, Any] | None,
) -> tuple[str, str, str]:
    if active_shift:
        return (
            SALARY_PAYMENT_STATUS_PENDING,
            "Shift active · Salary pending until completion",
            "Salary pending until the active shift completes.",
        )
    if current_day_audit:
        payment_status = str(current_day_audit.get("payment_status") or "").strip().lower()
        amount = _safe_float(current_day_audit.get("final_salary_paid"), 0.0)
        if payment_status == SALARY_PAYMENT_STATUS_PENDING:
            return (
                SALARY_PAYMENT_STATUS_PENDING,
                "Shift completed - Salary pending verification",
                "Shift completed, but salary is still pending posting.",
            )
        if payment_status == SALARY_PAYMENT_STATUS_POSTED:
            return (
                SALARY_PAYMENT_STATUS_POSTED,
                "Shift completed · Salary posted",
                f"Shift completed · Salary +{amount:.2f} XGP posted",
            )
        if payment_status == SALARY_PAYMENT_STATUS_FAILED:
            return (
                SALARY_PAYMENT_STATUS_FAILED,
                "Shift completed · Salary calculation failed",
                "Shift completed, but salary could not be posted yet.",
            )
    if missed_shift_today:
        return (
            "missed",
            "Missed shift · No salary earned",
            "Missed shift · No salary earned",
        )
    return ("none", "No salary posted", "No salary posted yet.")


def _salary_total_for_day(
    db: Session,
    *,
    player_id: UUID,
    day_number: int,
    fallback_amount: float = 0.0,
) -> float:
    if not _is_table_available(db, "gameplay_transactions"):
        return _safe_float(fallback_amount, 0.0)
    total = (
        db.query(func.coalesce(func.sum(GameplayTransaction.amount), 0))
        .filter(
            GameplayTransaction.player_id == player_id,
            GameplayTransaction.day == max(1, int(day_number)),
            GameplayTransaction.type == "income",
            GameplayTransaction.category == "salary",
        )
        .scalar()
    )
    resolved_total = _safe_float(total, 0.0)
    if resolved_total > 0:
        return resolved_total
    return _safe_float(fallback_amount, 0.0)


def _get_gameplay_transaction_by_id(
    db: Session,
    *,
    transaction_id: str | None,
) -> GameplayTransaction | None:
    raw_id = str(transaction_id or "").strip()
    if not raw_id or not _is_table_available(db, "gameplay_transactions"):
        return None
    try:
        return db.query(GameplayTransaction).filter(GameplayTransaction.id == UUID(raw_id)).first()
    except Exception:
        return None


def _find_salary_gameplay_transaction_for_shift(
    db: Session,
    *,
    player_id: UUID,
    day_number: int,
    description: str,
) -> GameplayTransaction | None:
    if not _is_table_available(db, "gameplay_transactions"):
        return None
    return (
        db.query(GameplayTransaction)
        .filter(
            GameplayTransaction.player_id == player_id,
            GameplayTransaction.day == max(1, int(day_number)),
            GameplayTransaction.category == "salary",
            GameplayTransaction.description == str(description or "").strip(),
        )
        .order_by(GameplayTransaction.timestamp.desc())
        .first()
    )


def _find_player_transaction_log_for_shift(
    db: Session,
    *,
    player_id: UUID,
    shift_token: str,
) -> PlayerTransactionLog | None:
    if not _is_table_available(db, "player_transaction_logs"):
        return None
    raw_shift_token = str(shift_token or "").strip()
    if not raw_shift_token:
        return None
    return (
        db.query(PlayerTransactionLog)
        .filter(
            PlayerTransactionLog.player_id == player_id,
            PlayerTransactionLog.category == "work",
            PlayerTransactionLog.transaction_type == "wage_income",
            PlayerTransactionLog.metadata_json.contains(raw_shift_token),
        )
        .order_by(PlayerTransactionLog.created_at.desc())
        .first()
    )


def _find_xgp_transaction_for_shift(
    db: Session,
    *,
    player_id: UUID,
    shift_id: str | None,
) -> XGPTransaction | None:
    raw_shift_id = str(shift_id or "").strip()
    if not raw_shift_id or not _is_table_available(db, "xgp_transactions"):
        return None
    return (
        db.query(XGPTransaction)
        .filter(
            XGPTransaction.player_id == player_id,
            XGPTransaction.transaction_type == "job_income",
            XGPTransaction.reference_type == "job_action",
            XGPTransaction.reference_id == raw_shift_id,
        )
        .order_by(XGPTransaction.created_at.desc())
        .first()
    )


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
    main_job_sync: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_employment = _latest_employment_state_for_player(db, player)
    latest_career = _latest_career_state_for_player(db, player)

    player_job_id = _canonical_main_job(
        (main_job_sync or {}).get("authoritative_main_job_key") or getattr(player, "main_job", None)
    )
    scheduled_job_id = _canonical_main_job(scheduled_shift_job_id or "")
    active_job_id = _canonical_main_job(active_shift_job_id or "")
    employment_job_id = _canonical_main_job(
        getattr(latest_employment, "current_job_code", None) if latest_employment is not None else None
    )
    career_job_id = _canonical_main_job(
        getattr(latest_career, "current_job_key", None) if latest_career is not None else None
    )

    if str((main_job_sync or {}).get("sync_status") or "") == "repair_needed":
        authoritative_current_job_id = ""
    else:
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
        "job_sync_status": str((main_job_sync or {}).get("sync_status") or ""),
        "job_sync_warning_message": str((main_job_sync or {}).get("sync_warning_message") or ""),
        "job_sync_repair_source": str((main_job_sync or {}).get("repair_source") or ""),
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

    canonical_current_job = _canonical_main_job(authoritative_current_job_id)
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


def _rollover_degraded_result(
    *,
    player: Player,
    now_houston: datetime,
    reason: str,
) -> dict[str, Any]:
    missed_days, previous_sync_date = _resolve_houston_rollover_days(player, now_houston=now_houston)
    return {
        "applied_days": 0,
        "missed_days": int(missed_days),
        "truncated_days": int(missed_days),
        "previous_sync_date": str(previous_sync_date),
        "today_date": str(now_houston.date()),
        "settlement_days": [],
        "triggered": False,
        "skipped_reason": "market_data_temporarily_unavailable",
        "degraded": True,
        "error": reason,
    }


def _apply_market_degradation_to_work_state(
    work_state: dict[str, Any],
    *,
    rollover_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(work_state, dict):
        return work_state
    if not isinstance(rollover_result, dict) or not bool(rollover_result.get("degraded")):
        return work_state

    degraded_sections = [
        str(section)
        for section in (work_state.get("degraded_sections") or [])
        if str(section).strip()
    ]
    if "market_data" not in degraded_sections:
        degraded_sections.append("market_data")
    reason = str(rollover_result.get("error") or "").strip() or "Market data temporarily unavailable."
    work_state["degraded_sections"] = degraded_sections
    work_state["market_data_available"] = False
    work_state["market_data_message"] = (
        "Market data temporarily unavailable. Core dashboard loaded with limited economy data."
    )
    work_state["auto_rollover_warning"] = reason
    return work_state


def _scheduled_shift_context(player: Player, *, day_number: int, now_houston: datetime) -> dict[str, Any]:
    resolved_now = _as_houston(now_houston) or get_houston_now()
    houston_local_date = resolved_now.date()
    mapped_game_day_date = _day_to_date(day_number)
    weekday_index = int(houston_local_date.weekday())
    canonical_main_job = _canonical_main_job(getattr(player, "main_job", None))
    day_of_week = houston_local_date.strftime("%A")
    is_weekend = weekday_index >= 5
    phase_status_label = "Weekend" if is_weekend else "Weekday"
    shift_template = JOB_SHIFT_MAP.get(canonical_main_job or "")
    scheduled_shift_start = str((shift_template or {}).get("start") or "")
    scheduled_shift_end = str((shift_template or {}).get("end") or "")
    scheduled_start_time = _parse_houston_hhmm(scheduled_shift_start)
    scheduled_end_time = _parse_houston_hhmm(scheduled_shift_end)
    current_local_time = resolved_now.timetz().replace(tzinfo=None)
    current_day_matches_houston_date = bool(houston_local_date == mapped_game_day_date)
    reached_shift_end = bool(
        scheduled_end_time
        and current_local_time >= scheduled_end_time
    )
    passed_shift_end = bool(
        scheduled_end_time
        and current_local_time > scheduled_end_time
    )
    logger.info(
        "shift.calendar_classification_resolved",
        extra={
            "player_id": str(player.id),
            "current_game_day": int(day_number),
            "utc_timestamp": resolved_now.astimezone(pytz.UTC).isoformat(),
            "houston_local_timestamp": resolved_now.isoformat(),
            "houston_local_date": str(houston_local_date),
            "mapped_game_day_date": str(mapped_game_day_date),
            "day_matches_game_day_date": current_day_matches_houston_date,
            "derived_weekday_index": weekday_index,
            "derived_weekday_label": day_of_week,
            "derived_phase_status": phase_status_label,
            "timer_mode": (
                "accelerated"
                if _configured_shift_duration_seconds(1) == 90
                else "normal"
            ),
        },
    )
    return {
        "houston_local_date": houston_local_date,
        "houston_local_date_label": _format_houston_date_label(houston_local_date),
        "mapped_game_day_date": mapped_game_day_date,
        "day_of_week": day_of_week,
        "weekday_index": weekday_index,
        "current_day_matches_houston_date": current_day_matches_houston_date,
        "is_weekend": is_weekend,
        "phase_status_label": phase_status_label,
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


def _completed_main_shift_for_day(
    player: Player,
    pds: PlayerDailyState | None,
    *,
    current_day: int,
    active_shift: bool,
) -> bool:
    main_shift_hours_today = _safe_float(
        getattr(pds, "main_shift_hours_today", None),
        _safe_float(getattr(player, "main_job_hours_today", 0), 0.0),
    )
    return bool(
        not active_shift
        and str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE) == SHIFT_STATUS_COMPLETED
        and int(getattr(player, "last_worked_day", 0) or 0) == current_day
        and main_shift_hours_today > 0
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
    completed_shift_today = _completed_main_shift_for_day(
        player,
        pds,
        current_day=current_day,
        active_shift=active_shift,
    )
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
            or completed_shift_today
            or bool(schedule["reached_shift_end"])
        )
    )
    if rideshare_unlocked:
        if bool(schedule["is_weekend"]):
            rideshare_description = "Rideshare available all day (weekend)"
        elif not bool(schedule["has_main_job"]):
            rideshare_description = "Rideshare available all day (no required shift)"
        elif completed_shift_today:
            rideshare_description = "Shift completed. You are now off shift."
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
    testing_config = get_gameplay_testing_mode_config()
    if bool(testing_config.get("testing_mode")):
        return max(60, int(testing_config.get("shift_minutes") or 15) * 60)

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
    shift_completed_today: bool,
    day_settled: bool,
    is_weekend: bool,
    no_shift_scheduled: bool,
    scheduled_shift_end_label: str | None,
    side_income_hours_today: float,
    hours_available: int,
    health: int,
    stress: int,
    current_location_key: str,
    now_houston: datetime,
    testing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_testing_config = testing_config or get_gameplay_testing_mode_config()
    max_trips = _rideshare_daily_cap(is_weekend=is_weekend, config=active_testing_config)
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
        reason = "Not enough time left today for rideshare."
    elif active_shift:
        status = "shift_active"
        reason = "Unavailable: shift still active."
    elif health < RIDESHARE_MIN_HEALTH:
        status = "health_low"
        reason = f"Unavailable: health too low ({int(health)}/100)."
    elif stress >= RIDESHARE_MAX_STRESS:
        status = "stress_high"
        reason = f"Unavailable: stress too high ({int(stress)}/100)."
    elif not bool(location_profile.get("allowed")):
        status = "location_restricted"
        reason = str(
            location_profile.get("reason_if_blocked")
            or "Unavailable: not at valid rideshare location."
        )
    elif not rideshare_unlocked:
        status = "shift_active"
        reason = (
            "Shift completed. You are now off shift."
            if shift_completed_today
            else f"Unavailable: shift still active until {scheduled_shift_end_label or 'shift end'}."
        )
    elif remaining_by_cap <= 0:
        status = "limit_reached"
        reason = "Unavailable: daily trip limit reached."
    elif hours_remaining_today <= 0 or remaining_trips <= 0:
        status = "not_enough_time"
        reason = "Not enough time left today for rideshare."
    elif is_weekend:
        if bool(active_testing_config.get("testing_mode")) and not bool(
            active_testing_config.get("weekend_main_shift_enabled")
        ):
            reason = "Weekend testing rule active. Rideshare only."
        else:
            reason = "Available all day (weekend)."
    elif no_shift_scheduled:
        reason = "Available all day (no required shift)."
    elif shift_completed_today:
        reason = "Shift completed. You are now off shift. Ride share is available now."
    else:
        demand_note = str(location_profile.get("label") or "").strip()
        if demand_note:
            reason = f"Ride Share is available now. {demand_note}."

    return {
        "can_rideshare": status == "available",
        "status": status,
        "reason": reason,
        "block_reason": reason if status != "available" else None,
        "trips_today": trips_today,
        "max_trips": max_trips,
        "remaining_trips": remaining_trips,
        "trips_remaining": remaining_trips,
        "hours_remaining_today": hours_remaining_today,
        "remaining_time_units": hours_remaining_today,
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


def _apply_main_job_sync_result_to_work_state(
    work_state: dict[str, Any],
    main_job_sync: dict[str, Any],
) -> dict[str, Any]:
    if not bool(main_job_sync.get("repair_applied")):
        return work_state
    sync_message = "Current job data was repaired from career state."
    work_state["job_sync_status"] = "auto_repaired"
    work_state["job_sync_auto_repaired"] = True
    work_state["job_sync_repair_source"] = str(main_job_sync.get("repair_source") or "")
    work_state["job_sync_warning_message"] = sync_message
    job_market = work_state.get("job_market")
    if isinstance(job_market, dict):
        job_market["job_sync_status"] = "auto_repaired"
        job_market["job_sync_warning_message"] = sync_message
    return work_state


def _overtime_multiplier_for_shift(
    *,
    job_key: str,
    shift_number: int,
    config: dict[str, Any] | None = None,
) -> Decimal:
    active_config = config or get_gameplay_testing_mode_config()
    if (
        bool(active_config.get("testing_mode"))
        and int(shift_number) == 2
        and _testing_mode_job_eligible(job_key, config=active_config)
    ):
        return Decimal(str(active_config.get("second_shift_overtime_multiplier") or Decimal("1.5")))
    return Decimal("1.0")


def _salary_transaction_label_for_shift(
    *,
    job_display_name: str,
    shift_number: int,
    overtime_multiplier_used: Decimal,
) -> str:
    if int(shift_number) == 2 and overtime_multiplier_used > Decimal("1.0"):
        return (
            f"Overtime Salary - Shift {int(shift_number)} - {job_display_name} "
            f"({float(overtime_multiplier_used):.1f}x)"
        )
    return f"Salary - Shift {int(shift_number)} - {job_display_name}"


def _build_shift_salary_snapshot(
    player: Player,
    *,
    current_day: int,
    now_houston: datetime,
    trigger: str,
) -> dict[str, Any]:
    testing_config = get_gameplay_testing_mode_config()
    shift_started_at = _as_houston(getattr(player, "main_shift_started_at", None)) or now_houston
    shift_ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    job_key = _canonical_main_job(
        getattr(player, "main_shift_job_name", None) or getattr(player, "main_job", None) or ""
    ) or ""
    hours_worked = max(1, int(getattr(player, "main_shift_hours", 0) or 0))
    shift_number = max(1, int(getattr(player, "main_shift_number", 1) or 1))
    shift_type = str(getattr(player, "main_shift_shift_type", None) or "standard_shift")
    job_def = resolve_job_definition(job_key)
    if job_def is None:
        raise ValueError(f"Cannot finalize unknown active main shift job '{job_key}'.")

    base_monthly_salary = _q4(Decimal(str(job_def.monthly_salary or 0)))
    pay_snapshot_used = _q4(base_monthly_salary)
    base_hourly_pay = _q4(base_monthly_salary / Decimal("30") / Decimal("8"))
    overtime_multiplier_used = _q4(
        _overtime_multiplier_for_shift(
            job_key=job_key,
            shift_number=shift_number,
            config=testing_config,
        )
    )
    overtime_applied = bool(overtime_multiplier_used > Decimal("1.0"))
    productivity_multiplier = _q4(
        Decimal(
            str(
                _productivity(
                    player,
                    shift_number=shift_number,
                )
                if not overtime_applied
                else _productivity(player, shift_number=1)
            )
        )
    )
    job_level_multiplier = _q4(Decimal("1"))
    gross_shift_pay = _q4(
        base_hourly_pay
        * Decimal(str(hours_worked))
        * productivity_multiplier
        * job_level_multiplier
        * overtime_multiplier_used
    )
    income_multiplier = _q4(Decimal(str(apply_income_multiplier(1.0))))
    final_salary_paid = _q4(gross_shift_pay * income_multiplier)
    overtime_penalty = bool(int(player.total_hours_worked_today or 0) > 8)
    stress_change = int(
        apply_stress_sensitivity(
            _stress_change(
                job_def.base_stress,
                hours_worked=hours_worked,
                shift_number=shift_number,
                overtime_penalty=overtime_penalty,
            )
        )
    )
    health_delta = -int(
        apply_health_decay_rate(
            _health_loss(
                hours_worked=hours_worked,
                shift_number=shift_number,
                overtime_penalty=overtime_penalty,
            )
        )
    )
    fatigue_change = _q4(
        Decimal(str(_fatigue_change(hours_worked=hours_worked, shift_number=shift_number)))
    )
    cash_before = _q4(getattr(player, "cash", 0))
    shift_token = _build_shift_salary_token(
        player_id=player.id,
        day_number=current_day,
        job_key=job_key,
        shift_number=shift_number,
        hours_worked=hours_worked,
        shift_started_at=shift_started_at,
    )
    return {
        "player_id": player.id,
        "current_day": int(current_day),
        "shift_token": shift_token,
        "job_key": job_key,
        "job_display_name": str(
            getattr(job_def, "title", None)
            or getattr(job_def, "display_name", None)
            or _job_display_name(job_key)
        ),
        "shift_started_at": shift_started_at,
        "shift_ends_at": shift_ends_at,
        "shift_completed_at": now_houston,
        "shift_type": shift_type,
        "shift_number": int(shift_number),
        "hours_worked": int(hours_worked),
        "trigger": str(trigger or ""),
        "base_monthly_salary": base_monthly_salary,
        "pay_snapshot_used": pay_snapshot_used,
        "base_hourly_pay": base_hourly_pay,
        "productivity_multiplier": productivity_multiplier,
        "income_multiplier": income_multiplier,
        "job_level_multiplier": job_level_multiplier,
        "gross_shift_pay": gross_shift_pay,
        "final_salary_paid": final_salary_paid,
        "xp_gained": int(work_xp_for_hours(hours_worked)),
        "stress_change": int(stress_change),
        "health_change": int(health_delta),
        "fatigue_change": fatigue_change,
        "overtime_penalty_applied": bool(overtime_penalty),
        "overtime_applied": overtime_applied,
        "overtime_multiplier_used": overtime_multiplier_used,
        "cash_before": cash_before,
    }


def _shift_salary_snapshot_from_audit(audit_row: ShiftSalaryAuditLog) -> dict[str, Any]:
    overtime_multiplier_used = _q4(
        _overtime_multiplier_for_shift(
            job_key=str(getattr(audit_row, "job_key", "") or ""),
            shift_number=int(getattr(audit_row, "shift_number", 0) or 0),
        )
    )
    return {
        "player_id": getattr(audit_row, "player_id"),
        "current_day": int(getattr(audit_row, "day_number", 0) or 0),
        "shift_token": str(getattr(audit_row, "shift_token", "") or ""),
        "job_key": str(getattr(audit_row, "job_key", "") or ""),
        "job_display_name": str(getattr(audit_row, "job_display_name", "") or ""),
        "shift_started_at": _as_houston(getattr(audit_row, "shift_started_at", None)),
        "shift_ends_at": _as_houston(getattr(audit_row, "shift_ends_at", None)),
        "shift_completed_at": _as_houston(getattr(audit_row, "shift_completed_at", None)) or get_houston_now(),
        "shift_type": str(getattr(audit_row, "shift_type", "") or ""),
        "shift_number": int(getattr(audit_row, "shift_number", 0) or 0),
        "hours_worked": int(getattr(audit_row, "hours_worked", 0) or 0),
        "trigger": str(getattr(audit_row, "trigger", "") or ""),
        "base_monthly_salary": _q4(getattr(audit_row, "base_monthly_salary", 0)),
        "pay_snapshot_used": _q4(getattr(audit_row, "pay_snapshot_used", 0)),
        "base_hourly_pay": _q4(getattr(audit_row, "base_hourly_pay", 0)),
        "productivity_multiplier": _q4(getattr(audit_row, "productivity_multiplier", 1)),
        "income_multiplier": _q4(getattr(audit_row, "income_multiplier", 1)),
        "job_level_multiplier": _q4(getattr(audit_row, "job_level_multiplier", 1)),
        "gross_shift_pay": _q4(getattr(audit_row, "gross_shift_pay", 0)),
        "final_salary_paid": _q4(getattr(audit_row, "final_salary_paid", 0)),
        "xp_gained": int(getattr(audit_row, "xp_gained", 0) or 0),
        "stress_change": int(getattr(audit_row, "stress_change", 0) or 0),
        "health_change": int(getattr(audit_row, "health_change", 0) or 0),
        "fatigue_change": _q4(getattr(audit_row, "fatigue_change", 0)),
        "overtime_penalty_applied": bool(getattr(audit_row, "overtime_penalty_applied", False)),
        "overtime_applied": bool(overtime_multiplier_used > Decimal("1.0")),
        "overtime_multiplier_used": overtime_multiplier_used,
        "cash_before": _q4(getattr(audit_row, "cash_before", 0)),
        "shift_id": str(getattr(audit_row, "shift_id", "") or ""),
    }


def _get_shift_salary_audit_by_token(db: Session, *, shift_token: str) -> ShiftSalaryAuditLog | None:
    if not _is_table_available(db, "shift_salary_audit_logs"):
        return None
    return (
        db.query(ShiftSalaryAuditLog)
        .filter(ShiftSalaryAuditLog.shift_token == str(shift_token or "").strip())
        .first()
    )


def _upsert_shift_salary_audit_row(
    db: Session,
    *,
    snapshot: dict[str, Any],
    payment_status: str,
    failure_reason: str | None = None,
    shift_id: str | None = None,
    salary_transaction_id: str | None = None,
    xgp_transaction_id: str | None = None,
    player_transaction_log_id: str | None = None,
    salary_posted_at: datetime | None = None,
    cash_before: Decimal | None = None,
    cash_after: Decimal | None = None,
) -> ShiftSalaryAuditLog | None:
    if not _is_table_available(db, "shift_salary_audit_logs"):
        return None
    shift_token = str(snapshot.get("shift_token") or "").strip()
    row = _get_shift_salary_audit_by_token(db, shift_token=shift_token)
    existed_already = row is not None
    if row is None:
        row = ShiftSalaryAuditLog(
            player_id=snapshot["player_id"],
            shift_token=shift_token,
        )

    row.day_number = int(snapshot.get("current_day") or 0)
    row.shift_id = shift_id or str(getattr(row, "shift_id", "") or "") or None
    row.job_key = str(snapshot.get("job_key") or "")
    row.job_display_name = str(snapshot.get("job_display_name") or "")
    row.shift_started_at = _as_houston(snapshot.get("shift_started_at"))
    row.shift_ends_at = _as_houston(snapshot.get("shift_ends_at"))
    row.shift_completed_at = _as_houston(snapshot.get("shift_completed_at"))
    row.shift_type = str(snapshot.get("shift_type") or "")
    row.shift_number = int(snapshot.get("shift_number") or 0)
    row.hours_worked = int(snapshot.get("hours_worked") or 0)
    row.trigger = str(snapshot.get("trigger") or "")
    row.payment_status = str(payment_status or SALARY_PAYMENT_STATUS_PENDING)
    row.failure_reason = str(failure_reason or "").strip() or None
    row.base_monthly_salary = _q4(snapshot.get("base_monthly_salary", 0))
    row.pay_snapshot_used = _q4(snapshot.get("pay_snapshot_used", 0))
    row.base_hourly_pay = _q4(snapshot.get("base_hourly_pay", 0))
    row.productivity_multiplier = _q4(snapshot.get("productivity_multiplier", 1))
    row.income_multiplier = _q4(snapshot.get("income_multiplier", 1))
    row.job_level_multiplier = _q4(snapshot.get("job_level_multiplier", 1))
    row.gross_shift_pay = _q4(snapshot.get("gross_shift_pay", 0))
    row.final_salary_paid = _q4(snapshot.get("final_salary_paid", 0))
    row.xp_gained = int(snapshot.get("xp_gained") or 0)
    row.stress_change = int(snapshot.get("stress_change") or 0)
    row.health_change = int(snapshot.get("health_change") or 0)
    row.fatigue_change = _q4(snapshot.get("fatigue_change", 0))
    row.overtime_penalty_applied = bool(snapshot.get("overtime_penalty_applied"))
    row.salary_transaction_id = str(salary_transaction_id or getattr(row, "salary_transaction_id", "") or "") or None
    row.xgp_transaction_id = str(xgp_transaction_id or getattr(row, "xgp_transaction_id", "") or "") or None
    row.player_transaction_log_id = str(
        player_transaction_log_id or getattr(row, "player_transaction_log_id", "") or ""
    ) or None
    row.salary_posted_at = _as_houston(salary_posted_at or getattr(row, "salary_posted_at", None))
    row.cash_before = _q4(cash_before if cash_before is not None else snapshot.get("cash_before", 0))
    row.cash_after = _q4(
        cash_after
        if cash_after is not None
        else getattr(row, "cash_after", None)
        if getattr(row, "cash_after", None) is not None
        else snapshot.get("cash_before", 0)
    )
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        row = _get_shift_salary_audit_by_token(db, shift_token=shift_token)
        if row is None:
            raise
        existed_already = True
        row.day_number = int(snapshot.get("current_day") or 0)
        row.shift_id = shift_id or str(getattr(row, "shift_id", "") or "") or None
        row.job_key = str(snapshot.get("job_key") or "")
        row.job_display_name = str(snapshot.get("job_display_name") or "")
        row.shift_started_at = _as_houston(snapshot.get("shift_started_at"))
        row.shift_ends_at = _as_houston(snapshot.get("shift_ends_at"))
        row.shift_completed_at = _as_houston(snapshot.get("shift_completed_at"))
        row.shift_type = str(snapshot.get("shift_type") or "")
        row.shift_number = int(snapshot.get("shift_number") or 0)
        row.hours_worked = int(snapshot.get("hours_worked") or 0)
        row.trigger = str(snapshot.get("trigger") or "")
        row.payment_status = str(payment_status or SALARY_PAYMENT_STATUS_PENDING)
        row.failure_reason = str(failure_reason or "").strip() or None
        row.base_monthly_salary = _q4(snapshot.get("base_monthly_salary", 0))
        row.pay_snapshot_used = _q4(snapshot.get("pay_snapshot_used", 0))
        row.base_hourly_pay = _q4(snapshot.get("base_hourly_pay", 0))
        row.productivity_multiplier = _q4(snapshot.get("productivity_multiplier", 1))
        row.income_multiplier = _q4(snapshot.get("income_multiplier", 1))
        row.job_level_multiplier = _q4(snapshot.get("job_level_multiplier", 1))
        row.gross_shift_pay = _q4(snapshot.get("gross_shift_pay", 0))
        row.final_salary_paid = _q4(snapshot.get("final_salary_paid", 0))
        row.xp_gained = int(snapshot.get("xp_gained") or 0)
        row.stress_change = int(snapshot.get("stress_change") or 0)
        row.health_change = int(snapshot.get("health_change") or 0)
        row.fatigue_change = _q4(snapshot.get("fatigue_change", 0))
        row.overtime_penalty_applied = bool(snapshot.get("overtime_penalty_applied"))
        row.salary_transaction_id = str(
            salary_transaction_id or getattr(row, "salary_transaction_id", "") or ""
        ) or None
        row.xgp_transaction_id = str(
            xgp_transaction_id or getattr(row, "xgp_transaction_id", "") or ""
        ) or None
        row.player_transaction_log_id = str(
            player_transaction_log_id or getattr(row, "player_transaction_log_id", "") or ""
        ) or None
        row.salary_posted_at = _as_houston(salary_posted_at or getattr(row, "salary_posted_at", None))
        row.cash_before = _q4(cash_before if cash_before is not None else snapshot.get("cash_before", 0))
        row.cash_after = _q4(
            cash_after
            if cash_after is not None
            else getattr(row, "cash_after", None)
            if getattr(row, "cash_after", None) is not None
            else snapshot.get("cash_before", 0)
        )
        db.add(row)
        db.flush()
        logger.info(
            "shift.salary_audit_reused_after_conflict",
            extra={
                "player_id": str(snapshot.get("player_id") or ""),
                "shift_token": shift_token,
                "day_number": int(snapshot.get("current_day") or 0),
                "job_key": str(snapshot.get("job_key") or ""),
                "payment_status": str(payment_status or SALARY_PAYMENT_STATUS_PENDING),
            },
        )

    logger.info(
        "shift.salary_audit_upserted",
        extra={
            "player_id": str(snapshot.get("player_id") or ""),
            "shift_token": shift_token,
            "day_number": int(snapshot.get("current_day") or 0),
            "job_key": str(snapshot.get("job_key") or ""),
            "payment_status": str(payment_status or SALARY_PAYMENT_STATUS_PENDING),
            "row_existed_already": bool(existed_already),
        },
    )
    return row


def _record_completed_shift_pending_salary(
    db: Session,
    *,
    player: Player,
    snapshot: dict[str, Any],
) -> ShiftSalaryAuditLog | None:
    existing_audit = _get_shift_salary_audit_by_token(db, shift_token=str(snapshot.get("shift_token") or ""))
    if existing_audit is not None:
        return existing_audit

    action = JobAction(
        player_id=player.id,
        job_name=str(snapshot.get("job_key") or ""),
        job_type="main",
        shift_number=int(snapshot.get("shift_number") or 1),
        day=int(snapshot.get("current_day") or 1),
        hours_worked=int(snapshot.get("hours_worked") or 0),
        base_hourly_pay=float(_q4(snapshot.get("base_hourly_pay", 0))),
        productivity=float(_q4(snapshot.get("productivity_multiplier", 1))),
        earned_cash=_money(snapshot.get("final_salary_paid", 0)),
        stress_change=int(snapshot.get("stress_change") or 0),
        health_change=int(snapshot.get("health_change") or 0),
        fatigue_change=float(_q4(snapshot.get("fatigue_change", 0))),
        overtime_penalty_applied=bool(snapshot.get("overtime_penalty_applied")),
        hours_remaining_after=int(player.hours_available or 0),
    )
    db.add(action)
    db.flush()

    if str(snapshot.get("job_key") or "") and getattr(player, "main_job", None) != snapshot.get("job_key"):
        player.main_job = str(snapshot.get("job_key") or "")
    player.main_shift_active_flag = False
    player.main_shift_status = SHIFT_STATUS_COMPLETED
    player.main_shift_completed_at = _as_houston(snapshot.get("shift_completed_at"))
    player.main_shift_last_cash_xgp = Decimal("0.0000")
    player.main_shift_last_xp_gained = 0
    player.main_shift_last_stress_delta = 0
    player.main_shift_last_health_delta = 0
    pds = _get_or_create_player_daily_state_in_txn(
        db,
        player,
        day_number=int(snapshot.get("current_day") or 1),
    )
    pds.worked_main_job = True
    pds.did_work = True
    pds.shift_start = _as_houston(snapshot.get("shift_started_at")) or pds.shift_start
    pds.shift_end = _as_houston(snapshot.get("shift_completed_at")) or pds.shift_end
    pds.worked_hours = max(
        int(getattr(pds, "worked_hours", 0) or 0),
        int(snapshot.get("hours_worked") or 0),
    )
    pds.hours_available_end = int(player.hours_available or 0)

    audit_row = _upsert_shift_salary_audit_row(
        db,
        snapshot=snapshot,
        payment_status=SALARY_PAYMENT_STATUS_PENDING,
        shift_id=str(action.id),
        cash_before=_q4(getattr(player, "cash", 0)),
        cash_after=_q4(getattr(player, "cash", 0)),
    )
    db.commit()
    db.refresh(player)
    return audit_row


def _post_shift_salary_from_audit(
    db: Session,
    *,
    player: Player,
    audit_row: ShiftSalaryAuditLog,
    trigger: str,
    now_houston: datetime,
) -> ShiftSalaryAuditLog:
    if str(getattr(audit_row, "payment_status", "") or "").strip().lower() == SALARY_PAYMENT_STATUS_POSTED:
        return audit_row
    if not _is_table_available(db, "gameplay_transactions"):
        raise ValueError("Shift salary could not be posted because gameplay transaction ledger is unavailable.")

    snapshot = _shift_salary_snapshot_from_audit(audit_row)
    pds = _get_or_create_player_daily_state_in_txn(
        db,
        player,
        day_number=int(snapshot.get("current_day") or 1),
    )
    existing_salary_tx_id = str(getattr(audit_row, "salary_transaction_id", None) or "").strip()
    if existing_salary_tx_id:
        existing_gameplay_tx = _get_gameplay_transaction_by_id(db, transaction_id=existing_salary_tx_id)
        if existing_gameplay_tx is None:
            raise ValueError(
                f"Salary transaction {existing_salary_tx_id} is missing from gameplay ledger."
            )
        existing_amount = _q4(getattr(existing_gameplay_tx, "amount", 0))
        pds.salary_earned = _q4(
            _salary_total_for_day(
                db,
                player_id=player.id,
                day_number=int(snapshot.get("current_day") or 1),
                fallback_amount=float(existing_amount),
            )
        )
        pds.salary_transaction_id = existing_salary_tx_id
        pds.salary_posted_at = _as_houston(getattr(existing_gameplay_tx, "timestamp", None)) or getattr(
            pds, "salary_posted_at", None
        )
        updated_audit = _upsert_shift_salary_audit_row(
            db,
            snapshot=snapshot,
            payment_status=SALARY_PAYMENT_STATUS_POSTED,
            shift_id=str(getattr(audit_row, "shift_id", "") or ""),
            salary_transaction_id=existing_salary_tx_id,
            salary_posted_at=pds.salary_posted_at,
            cash_before=_q4(getattr(audit_row, "cash_before", getattr(player, "cash", 0))),
            cash_after=_q4(getattr(player, "cash", 0)),
        )
        db.commit()
        db.refresh(player)
        return updated_audit or audit_row

    shift_id = str(getattr(audit_row, "shift_id", "") or "")
    salary_label = _salary_transaction_label_for_shift(
        job_display_name=str(
            snapshot.get("job_display_name") or _job_display_name(str(snapshot.get("job_key") or ""))
        ),
        shift_number=int(snapshot.get("shift_number") or 1),
        overtime_multiplier_used=_q4(snapshot.get("overtime_multiplier_used", Decimal("1.0"))),
    )
    action = None
    if shift_id:
        action = db.query(JobAction).filter(JobAction.id == UUID(shift_id)).first()
    if action is None:
        action = JobAction(
            player_id=player.id,
            job_name=str(snapshot.get("job_key") or ""),
            job_type="main",
            shift_number=int(snapshot.get("shift_number") or 1),
            day=int(snapshot.get("current_day") or 1),
            hours_worked=int(snapshot.get("hours_worked") or 0),
            base_hourly_pay=float(_q4(snapshot.get("base_hourly_pay", 0))),
            productivity=float(_q4(snapshot.get("productivity_multiplier", 1))),
            earned_cash=_money(snapshot.get("final_salary_paid", 0)),
            stress_change=int(snapshot.get("stress_change") or 0),
            health_change=int(snapshot.get("health_change") or 0),
            fatigue_change=float(_q4(snapshot.get("fatigue_change", 0))),
            overtime_penalty_applied=bool(snapshot.get("overtime_penalty_applied")),
            hours_remaining_after=int(player.hours_available or 0),
        )
        db.add(action)
        db.flush()
        shift_id = str(action.id)

    existing_gameplay_tx = _find_salary_gameplay_transaction_for_shift(
        db,
        player_id=player.id,
        day_number=int(snapshot.get("current_day") or 1),
        description=salary_label,
    )
    if existing_gameplay_tx is not None:
        player_tx = _find_player_transaction_log_for_shift(
            db,
            player_id=player.id,
            shift_token=str(snapshot.get("shift_token") or ""),
        )
        xgp_tx = _find_xgp_transaction_for_shift(
            db,
            player_id=player.id,
            shift_id=shift_id,
        )
        existing_amount = _q4(getattr(existing_gameplay_tx, "amount", 0))
        pds.salary_earned = _q4(
            _salary_total_for_day(
                db,
                player_id=player.id,
                day_number=int(snapshot.get("current_day") or 1),
                fallback_amount=float(existing_amount),
            )
        )
        pds.salary_transaction_id = str(existing_gameplay_tx.id)
        pds.salary_posted_at = _as_houston(getattr(existing_gameplay_tx, "timestamp", None)) or now_houston
        updated_audit = _upsert_shift_salary_audit_row(
            db,
            snapshot=snapshot,
            payment_status=SALARY_PAYMENT_STATUS_POSTED,
            shift_id=shift_id,
            salary_transaction_id=str(existing_gameplay_tx.id),
            xgp_transaction_id=str(getattr(xgp_tx, "id", "") or "") or None,
            player_transaction_log_id=str(getattr(player_tx, "id", "") or "") or None,
            salary_posted_at=pds.salary_posted_at,
            cash_before=_q4(getattr(audit_row, "cash_before", getattr(player, "cash", 0))),
            cash_after=_q4(getattr(player, "cash", 0)),
        )
        db.commit()
        db.refresh(player)
        return updated_audit or audit_row

    balance_before = _q4(getattr(player, "cash", 0))
    final_salary_paid = _q4(snapshot.get("final_salary_paid", 0))
    player.cash = _money(balance_before + final_salary_paid)
    player.stress = _clamp_int(int(player.stress or 0) + int(snapshot.get("stress_change") or 0), 0, 100)
    player.health = _clamp_int(int(player.health or 0) + int(snapshot.get("health_change") or 0), 0, 100)
    player.fatigue = max(
        0.0,
        min(100.0, float(player.fatigue or 0) + float(_safe_float(snapshot.get("fatigue_change"), 0.0))),
    )
    player.main_shift_active_flag = False
    player.main_shift_status = SHIFT_STATUS_COMPLETED
    player.main_shift_completed_at = _as_houston(snapshot.get("shift_completed_at")) or now_houston
    player.main_shift_last_cash_xgp = final_salary_paid
    player.main_shift_last_xp_gained = int(snapshot.get("xp_gained") or 0)
    player.main_shift_last_stress_delta = int(snapshot.get("stress_change") or 0)
    player.main_shift_last_health_delta = int(snapshot.get("health_change") or 0)
    balance_after = _q4(getattr(player, "cash", 0))

    logger.info(
        "shift.salary_calculated",
        extra={
            "player_id": str(player.id),
            "shift_id": shift_id,
            "day_number": int(snapshot.get("current_day") or 1),
            "job_key": str(snapshot.get("job_key") or ""),
            "salary_amount": float(final_salary_paid),
            "cash_before": float(balance_before),
            "cash_after": float(balance_after),
            "trigger": str(trigger or ""),
        },
    )

    xgp_tx = XGPTransaction(
        player_id=player.id,
        transaction_type="job_income",
        direction="in",
        amount=final_salary_paid,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type="job_action",
        reference_id=shift_id,
        description=salary_label,
    )
    db.add(xgp_tx)
    db.flush()

    player_tx = record_player_transaction(
        db,
        player=player,
        day=int(snapshot.get("current_day") or 1),
        transaction_type="wage_income",
        category="work",
        quantity=int(snapshot.get("hours_worked") or 0),
        unit_price=_q4(snapshot.get("base_hourly_pay", 0)),
        gross_amount=final_salary_paid,
        fee_amount=0,
        net_cash_delta=final_salary_paid,
        resulting_cash_balance=balance_after,
        metadata={
            "job_name": str(snapshot.get("job_key") or ""),
            "job_type": "main",
            "shift_number": int(snapshot.get("shift_number") or 1),
            "productivity": float(_q4(snapshot.get("productivity_multiplier", 1))),
            "trigger": trigger,
            "main_shift_status": SHIFT_STATUS_COMPLETED,
            "houston_finalized_at": now_houston.isoformat(),
            "salary_audit_shift_token": str(snapshot.get("shift_token") or ""),
            "salary_label": salary_label,
            "overtime_applied": bool(snapshot.get("overtime_applied")),
            "overtime_multiplier_used": float(_q4(snapshot.get("overtime_multiplier_used", 1))),
        },
    )
    db.flush()

    gameplay_tx = record_gameplay_transaction(
        db,
        player=player,
        day=int(snapshot.get("current_day") or 1),
        transaction_type="income",
        category="salary",
        amount=final_salary_paid,
        description=salary_label,
    )
    db.flush()
    logger.info(
        "shift.salary_transaction_created",
        extra={
            "player_id": str(player.id),
            "shift_id": shift_id,
            "day_number": int(snapshot.get("current_day") or 1),
            "job_key": str(snapshot.get("job_key") or ""),
            "salary_amount": float(final_salary_paid),
            "transaction_id": str(gameplay_tx.id),
            "cash_before": float(balance_before),
            "cash_after": float(balance_after),
        },
    )

    contribution = ContributionEvent(
        player_id=player.id,
        event_type="job_work",
        xgp_value=final_salary_paid,
        event_units=float(int(snapshot.get("hours_worked") or 0)),
        metadata_json=json.dumps(
            {
                "job_id": str(snapshot.get("job_key") or ""),
                "job_type": "main",
                "day_number": int(snapshot.get("current_day") or 1),
                "shift_number": int(snapshot.get("shift_number") or 1),
                "productivity_multiplier": float(_q4(snapshot.get("productivity_multiplier", 1))),
                "base_hourly_pay": float(_q4(snapshot.get("base_hourly_pay", 0))),
                "overtime_penalty": bool(snapshot.get("overtime_penalty_applied")),
                "overtime_applied": bool(snapshot.get("overtime_applied")),
                "overtime_multiplier_used": float(_q4(snapshot.get("overtime_multiplier_used", 1))),
                "trigger": trigger,
                "houston_finalized_at": now_houston.isoformat(),
                "salary_audit_shift_token": str(snapshot.get("shift_token") or ""),
                "salary_label": salary_label,
            }
        ),
    )
    db.add(contribution)

    pds.worked_main_job = True
    pds.did_work = True
    pds.shift_start = _as_houston(snapshot.get("shift_started_at")) or now_houston
    pds.shift_end = now_houston
    pds.worked_hours = max(
        int(getattr(pds, "worked_hours", 0) or 0),
        int(snapshot.get("hours_worked") or 0),
    )
    pds.salary_earned = _q4(Decimal(str(getattr(pds, "salary_earned", 0) or 0)) + final_salary_paid)
    pds.salary_transaction_id = str(gameplay_tx.id)
    pds.salary_posted_at = now_houston
    pds.missed_penalty = Decimal("0")
    pds.gross_income_xgp = _q4(Decimal(str(getattr(pds, "gross_income_xgp", 0) or 0)) + final_salary_paid)
    pds.hours_available_end = int(player.hours_available or 0)
    pds.stress_end = int(player.stress or 0)
    pds.health_end = int(player.health or 0)
    pds.cash_end = balance_after

    try:
        player.lifetime_xgp_earned = round(float(player.lifetime_xgp_earned or 0.0) + float(final_salary_paid), 4)
    except AttributeError:
        pass

    logger.info(
        "shift.cash_updated_after_salary",
        extra={
            "player_id": str(player.id),
            "shift_id": shift_id,
            "day_number": int(snapshot.get("current_day") or 1),
            "job_key": str(snapshot.get("job_key") or ""),
            "salary_amount": float(final_salary_paid),
            "transaction_id": str(gameplay_tx.id),
            "cash_before": float(balance_before),
            "cash_after": float(balance_after),
        },
    )

    if _is_table_available(db, "player_employment_states") and _is_table_available(db, "stock_daily_prices"):
        upsert_employment_foundation(
            db,
            player=player,
            settled_day=max(1, _safe_int(getattr(player, "last_settled_day", None), 0) + 1),
            job_key=str(snapshot.get("job_key") or ""),
            shift_type=snapshot.get("shift_type"),
            grant_work_xp=int(snapshot.get("xp_gained") or 0),
        )
    try:
        award_completed_shift_xp(
            db,
            player_id=player.id,
            job_key=str(snapshot.get("job_key") or ""),
            xp_gain=SHIFT_COMPLETION_XP_GAIN,
            worked_at=now_houston,
        )
    except Exception:
        pass
    sync_shift_day_rules_if_needed(
        db,
        player=player,
        day_number=int(snapshot.get("current_day") or 1),
        now_houston=now_houston,
    )
    updated_audit = _upsert_shift_salary_audit_row(
        db,
        snapshot=snapshot,
        payment_status=SALARY_PAYMENT_STATUS_POSTED,
        shift_id=shift_id,
        salary_transaction_id=str(gameplay_tx.id),
        xgp_transaction_id=str(xgp_tx.id),
        player_transaction_log_id=str(player_tx.id),
        salary_posted_at=now_houston,
        cash_before=balance_before,
        cash_after=balance_after,
    )
    db.commit()
    db.refresh(player)
    return updated_audit or audit_row


def _mark_shift_salary_post_failed(
    db: Session,
    *,
    player_id: UUID,
    snapshot: dict[str, Any],
    reason: str,
) -> ShiftSalaryAuditLog | None:
    db.rollback()
    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None:
        return None
    player.main_shift_active_flag = False
    player.main_shift_status = SHIFT_STATUS_COMPLETED
    player.main_shift_completed_at = _as_houston(snapshot.get("shift_completed_at")) or get_houston_now()
    if str(snapshot.get("job_key") or "") and getattr(player, "main_job", None) != snapshot.get("job_key"):
        player.main_job = str(snapshot.get("job_key") or "")
    pds = _get_or_create_player_daily_state_in_txn(
        db,
        player,
        day_number=int(snapshot.get("current_day") or 1),
    )
    pds.shift_start = _as_houston(snapshot.get("shift_started_at")) or pds.shift_start
    pds.shift_end = _as_houston(snapshot.get("shift_completed_at")) or pds.shift_end
    audit_row = _upsert_shift_salary_audit_row(
        db,
        snapshot=snapshot,
        payment_status=SALARY_PAYMENT_STATUS_FAILED,
        failure_reason=reason,
        cash_before=_q4(getattr(player, "cash", 0)),
        cash_after=_q4(getattr(player, "cash", 0)),
    )
    db.commit()
    db.refresh(player)
    return audit_row


def _retry_pending_shift_salary_if_needed(
    db: Session,
    *,
    player: Player,
    day_number: int,
    now_houston: datetime,
) -> ShiftSalaryAuditLog | None:
    audit_row = _latest_shift_salary_audit_for_player(db, player_id=player.id, day_number=day_number)
    if audit_row is None:
        return None
    payment_status = str(getattr(audit_row, "payment_status", "") or "").strip().lower()
    if payment_status == SALARY_PAYMENT_STATUS_POSTED:
        return audit_row
    if bool(getattr(player, "main_shift_active_flag", False)):
        return audit_row
    if str(getattr(player, "main_shift_status", "") or "").strip().lower() != SHIFT_STATUS_COMPLETED:
        return audit_row
    try:
        repaired = _post_shift_salary_from_audit(
            db,
            player=player,
            audit_row=audit_row,
            trigger="salary_retry_sync",
            now_houston=now_houston,
        )
        logger.info(
            "shift.salary_retry_succeeded",
            extra={
                "player_id": str(player.id),
                "shift_id": str(getattr(repaired, "shift_id", "") or ""),
                "day_number": int(day_number),
                "job_key": str(getattr(repaired, "job_key", "") or ""),
                "salary_amount": float(_safe_float(getattr(repaired, "final_salary_paid", 0), 0.0)),
                "transaction_id": str(getattr(repaired, "salary_transaction_id", "") or ""),
            },
        )
        return repaired
    except Exception as exc:
        failed = _mark_shift_salary_post_failed(
            db,
            player_id=player.id,
            snapshot=_shift_salary_snapshot_from_audit(audit_row),
            reason=str(exc),
        )
        logger.warning(
            "shift.salary_retry_failed",
            extra={
                "player_id": str(player.id),
                "shift_id": str(getattr(audit_row, "shift_id", "") or ""),
                "day_number": int(day_number),
                "job_key": str(getattr(audit_row, "job_key", "") or ""),
                "failure_reason": str(exc),
            },
        )
        return failed


def _validate_main_shift_start(player: Player, *, job_name: str, hours_worked: int, shift_number: int) -> None:
    canonical_job_name = _canonical_main_job(job_name)
    canonical_player_job = _canonical_main_job(getattr(player, "main_job", None))
    testing_config = get_gameplay_testing_mode_config()
    max_daily_main_shifts = _max_daily_main_shifts_for_job(canonical_job_name, config=testing_config)
    max_main_hours_per_day = MAX_MAIN_HOURS_PER_DAY
    if bool(testing_config.get("testing_mode")) and max_daily_main_shifts > 1:
        max_main_hours_per_day = max(
            MAX_MAIN_HOURS_PER_DAY,
            int(hours_worked) * int(max_daily_main_shifts),
        )
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

    if int(player.work_actions_today or 0) >= max_daily_main_shifts:
        raise ValueError("Daily shift limit reached.")

    if int(player.health or 0) <= 15:
        raise ValueError(f"Health is too low to work ({player.health}/100). Minimum required: 16.")

    if shift_number == 2 and float(player.fatigue or 0) >= MAX_FATIGUE_FOR_SECOND_SHIFT:
        raise ValueError(
            f"Fatigue is too high for a second shift ({float(player.fatigue or 0):.1f}/100). "
            f"Must be below {MAX_FATIGUE_FOR_SECOND_SHIFT}."
        )

    if int(player.main_job_hours_today or 0) > 0 and max_daily_main_shifts <= 1:
        raise ValueError("You have already worked your main job shift today.")

    if shift_number > max_daily_main_shifts:
        raise ValueError("Daily shift limit reached.")

    if int(player.main_job_hours_today or 0) + hours_worked > max_main_hours_per_day:
        raise ValueError(
            f"Main job hour cap is {max_main_hours_per_day} hours/day. "
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


def _list_shift_salary_audits_for_player_day(
    db: Session,
    *,
    player_id: UUID,
    day_number: int,
) -> list[ShiftSalaryAuditLog]:
    if not _is_table_available(db, "shift_salary_audit_logs"):
        return []
    return (
        db.query(ShiftSalaryAuditLog)
        .filter(
            ShiftSalaryAuditLog.player_id == player_id,
            ShiftSalaryAuditLog.day_number == int(day_number),
        )
        .order_by(
            ShiftSalaryAuditLog.shift_number.asc(),
            ShiftSalaryAuditLog.shift_completed_at.asc(),
            ShiftSalaryAuditLog.created_at.asc(),
        )
        .all()
    )


def _build_testing_mode_work_payload(
    *,
    player: Player,
    is_weekend: bool,
    shifts_completed_today: int,
    shift_1_completed: bool,
    shift_2_completed: bool,
    active_shift: bool,
) -> dict[str, Any]:
    testing_config = get_gameplay_testing_mode_config()
    current_job_key = normalize_main_job_key(
        getattr(player, "main_shift_job_name", None) or getattr(player, "main_job", None),
        allow_aliases=True,
    )
    eligible_for_two_shifts = _testing_mode_job_eligible(current_job_key, config=testing_config)
    max_daily_main_shifts = _max_daily_main_shifts_for_job(current_job_key, config=testing_config)
    weekend_main_shift_enabled = bool(testing_config.get("weekend_main_shift_enabled"))
    weekend_rideshare_only = bool(
        testing_config.get("testing_mode") and is_weekend and not weekend_main_shift_enabled
    )
    overtime_shift_available = bool(
        testing_config.get("testing_mode")
        and eligible_for_two_shifts
        and not weekend_rideshare_only
        and shift_1_completed
        and not shift_2_completed
        and not active_shift
    )
    daily_shift_limit_reached = bool(
        shifts_completed_today >= max_daily_main_shifts or (weekend_rideshare_only and shifts_completed_today == 0)
    )
    next_shift_number_available = None
    if not active_shift and not daily_shift_limit_reached and not weekend_rideshare_only:
        next_shift_number_available = min(max_daily_main_shifts, shifts_completed_today + 1)

    return {
        "enabled": bool(testing_config.get("testing_mode")),
        "shift_minutes": int(testing_config.get("shift_minutes") or 15),
        "shift_length_label": _testing_shift_length_label(testing_config),
        "two_shift_jobs": list(testing_config.get("two_shift_jobs") or []),
        "eligible_for_two_shifts": eligible_for_two_shifts,
        "max_daily_main_shifts": max_daily_main_shifts,
        "shifts_completed_today": shifts_completed_today,
        "shift_1_completed": bool(shift_1_completed),
        "shift_2_completed": bool(shift_2_completed),
        "overtime_shift_available": overtime_shift_available,
        "overtime_used_today": bool(shift_2_completed),
        "next_shift_number_available": next_shift_number_available,
        "daily_shift_limit_reached": daily_shift_limit_reached,
        "weekend_rideshare_only": weekend_rideshare_only,
        "rideshare_cap_today": _rideshare_daily_cap(is_weekend=is_weekend, config=testing_config),
        "weekend_main_shift_enabled": weekend_main_shift_enabled,
        "second_shift_overtime_multiplier": float(
            testing_config.get("second_shift_overtime_multiplier") or Decimal("1.5")
        ),
    }


def build_work_state_payload(db: Session, player: Player, *, now_houston: datetime | None = None) -> dict[str, Any]:
    now = _as_houston(now_houston) or get_houston_now()
    current_day = _current_game_day_for_player(db, player)
    testing_config = get_gameplay_testing_mode_config()
    _maybe_reset_daily_counters(player, current_day)
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == current_day,
        )
        .first()
    )

    main_job_sync = inspect_and_repair_main_job_sync(
        db,
        player=player,
        trigger="build_work_state_payload",
        apply_repair=False,
    )
    canonical_main_job = _canonical_main_job(
        main_job_sync.get("authoritative_main_job_key") or getattr(player, "main_job", None)
    )
    canonical_shift_job_name = _canonical_main_job(getattr(player, "main_shift_job_name", None) or "")
    shift_started_at = _as_houston(getattr(player, "main_shift_started_at", None))
    shift_ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    shift_completed_at = _as_houston(getattr(player, "main_shift_completed_at", None))
    active_shift = bool(getattr(player, "main_shift_active_flag", False) and getattr(player, "main_shift_status", "") == SHIFT_STATUS_ACTIVE)
    current_day_shift_audits = _list_shift_salary_audits_for_player_day(
        db,
        player_id=player.id,
        day_number=current_day,
    )
    shifts_completed_today = len(current_day_shift_audits)
    shift_1_completed = any(int(getattr(row, "shift_number", 0) or 0) == 1 for row in current_day_shift_audits)
    shift_2_completed = any(int(getattr(row, "shift_number", 0) or 0) == 2 for row in current_day_shift_audits)
    shift_expired = bool(active_shift and shift_ends_at and now >= shift_ends_at)
    schedule = _scheduled_shift_context(player, day_number=current_day, now_houston=now)
    testing_mode_payload = _build_testing_mode_work_payload(
        player=player,
        is_weekend=bool(schedule["is_weekend"]),
        shifts_completed_today=shifts_completed_today,
        shift_1_completed=shift_1_completed,
        shift_2_completed=shift_2_completed,
        active_shift=active_shift,
    )
    resolved_shift_job_name = canonical_shift_job_name or _canonical_main_job(schedule["canonical_main_job"]) or canonical_main_job
    job_truth_context = _resolve_job_truth_context(
        db,
        player=player,
        scheduled_shift_job_id=_canonical_main_job(schedule["canonical_main_job"]),
        active_shift_job_id=canonical_shift_job_name if active_shift else None,
        main_job_sync=main_job_sync,
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
    job_market_payload["job_sync_status"] = str(main_job_sync.get("sync_status") or "")
    job_market_payload["job_sync_warning_message"] = str(main_job_sync.get("sync_warning_message") or "")
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
    salary_earned_today = _salary_total_for_day(
        db,
        player_id=player.id,
        day_number=current_day,
        fallback_amount=_safe_float(getattr(pds, "salary_earned", 0) if pds is not None else 0, 0.0),
    )
    salary_earned_yesterday = (
        _salary_total_for_day(
            db,
            player_id=player.id,
            day_number=max(1, current_day - 1),
            fallback_amount=_safe_float(
                (
                    db.query(PlayerDailyState.salary_earned)
                    .filter(
                        PlayerDailyState.player_id == player.id,
                        PlayerDailyState.day_number == max(1, current_day - 1),
                    )
                    .scalar()
                ),
                0.0,
            ),
        )
        if current_day > 1
        else 0.0
    )

    completed_shift_confirmed = _completed_main_shift_for_day(
        player,
        pds,
        current_day=current_day,
        active_shift=active_shift,
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
            or completed_shift_confirmed
            or bool(schedule["reached_shift_end"])
        )
    )
    rideshare_state = _build_rideshare_state(
        active_shift=active_shift,
        rideshare_unlocked=rideshare_unlocked,
        shift_completed_today=completed_shift_confirmed,
        day_settled=day_settled,
        is_weekend=bool(schedule["is_weekend"]),
        no_shift_scheduled=no_shift_scheduled,
        scheduled_shift_end_label=schedule["scheduled_shift_end_label"],
        side_income_hours_today=side_income_hours_today,
        hours_available=int(getattr(player, "hours_available", 0) or 0),
        health=_safe_int(getattr(player, "health", 100), 100),
        stress=_safe_int(getattr(player, "stress", 0), 0),
        current_location_key=current_location_key,
        now_houston=now,
        testing_config=testing_config,
    )
    rideshare_available = bool(rideshare_state.get("can_rideshare"))
    rideshare_block_reason = str(rideshare_state.get("block_reason") or "").strip() or None
    remaining_side_cap = max(0.0, float(rideshare_state.get("remaining_trips") or 0.0))
    work_status = (
        WORK_STATUS_ON_SHIFT
        if active_shift
        else WORK_STATUS_OFF_SHIFT_AFTER_WORK
        if completed_shift_confirmed
        else WORK_STATUS_OFF_SHIFT
    )
    shift_ended_at = shift_completed_at
    did_work_today = _did_work_for_day(player, pds, current_day=current_day, active_shift=active_shift)
    missed_shift_today = bool(getattr(pds, "missed_shift", False)) if pds is not None else False
    current_day_salary_audit = _serialize_shift_salary_audit(current_day_shift_audits[-1] if current_day_shift_audits else None)
    did_work_today = bool(did_work_today or current_day_salary_audit)
    last_salary_posted = _serialize_shift_salary_audit(
        _latest_posted_shift_salary_audit_for_player(db, player_id=player.id)
    )
    recent_salary_audits = _list_recent_shift_salary_audits_for_player(db, player_id=player.id, limit=3)
    salary_payment_status, salary_status_label, salary_status_message = _salary_status_from_audit(
        active_shift=active_shift,
        missed_shift_today=missed_shift_today,
        current_day_audit=current_day_salary_audit,
    )
    current_salary_transaction_id = str((current_day_salary_audit or {}).get("salary_transaction_id") or "").strip()
    current_salary_posted_at = (current_day_salary_audit or {}).get("salary_posted_at")
    salary_transaction_confirmed = bool(current_salary_transaction_id)
    last_completed_shift_payload = {
        "earned_cash_xgp": round(
            _safe_float(
                (current_day_salary_audit or {}).get("final_salary_paid"),
                _safe_float(getattr(player, "main_shift_last_cash_xgp", 0), 0.0),
            ),
            4,
        ),
        "xp_gained": int(
            (current_day_salary_audit or {}).get("xp_gained")
            or getattr(player, "main_shift_last_xp_gained", 0)
            or 0
        ),
        "stress_change": int(
            (current_day_salary_audit or {}).get("stress_change")
            or getattr(player, "main_shift_last_stress_delta", 0)
            or 0
        ),
        "health_change": int(
            (current_day_salary_audit or {}).get("health_change")
            or getattr(player, "main_shift_last_health_delta", 0)
            or 0
        ),
        "salary_payment_status": salary_payment_status,
        "salary_transaction_id": current_salary_transaction_id,
        "salary_posted_at": current_salary_posted_at,
        "transaction_confirmed": salary_transaction_confirmed,
        "job_key": str((current_day_salary_audit or {}).get("job_key") or resolved_shift_job_name or ""),
        "job_display_name": str(
            (current_day_salary_audit or {}).get("job_display_name")
            or _job_display_name(resolved_shift_job_name)
        ),
    }

    return {
        "player_id": str(player.id),
        "current_houston_time": now.isoformat(),
        "current_houston_time_label": _format_houston_datetime_label(now),
        "current_houston_date": str(schedule["houston_local_date"]),
        "current_houston_date_label": str(schedule["houston_local_date_label"] or ""),
        "current_game_day": current_day,
        "day_of_week": str(schedule["day_of_week"]),
        "is_weekend": bool(schedule["is_weekend"]),
        "phase_status_label": str(schedule["phase_status_label"]),
        "testing_mode": testing_mode_payload,
        "day_rollover_timezone": "America/Chicago",
        "day_rollover_time_label": HOUSTON_DAY_RESET_LABEL,
        "next_day_rollover_time": "00:00",
        "day_settled": day_settled,
        "main_job_key": canonical_main_job or "",
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
        "job_sync_status": str(job_truth_context.get("job_sync_status") or main_job_sync.get("sync_status") or ""),
        "job_sync_warning_message": str(
            job_truth_context.get("job_sync_warning_message") or main_job_sync.get("sync_warning_message") or ""
        ),
        "job_sync_repair_source": str(
            job_truth_context.get("job_sync_repair_source") or main_job_sync.get("repair_source") or ""
        ),
        "job_sync_auto_repaired": bool(main_job_sync.get("repair_applied")),
        "job_market": job_market_payload,
        "active_shift_id": (
            f"{player.id}:{current_day}:{int(getattr(player, 'main_shift_number', 0) or 0)}"
            if active_shift
            else None
        ),
        "shift_status": str(getattr(player, "main_shift_status", SHIFT_STATUS_IDLE) or SHIFT_STATUS_IDLE),
        "main_shift_active_flag": active_shift,
        "is_on_shift": active_shift,
        "work_status": work_status,
        "current_action_state": work_status,
        "shift_started_at": shift_started_at.isoformat() if shift_started_at else None,
        "shift_ends_at": shift_ends_at.isoformat() if shift_ends_at else None,
        "shift_completed_at": shift_completed_at.isoformat() if shift_completed_at else None,
        "shift_ended_at": shift_ended_at.isoformat() if shift_ended_at else None,
        "shift_start_time_label": _format_houston_datetime_label(shift_started_at),
        "shift_end_time_label": _format_houston_datetime_label(shift_ends_at),
        "shift_completed_time_label": _format_houston_datetime_label(shift_completed_at),
        "shift_job_name": resolved_shift_job_name or "",
        "shift_job_display_name": _job_display_name(resolved_shift_job_name),
        "shift_type": str(getattr(player, "main_shift_shift_type", None) or "standard_shift"),
        "shift_hours": int(getattr(player, "main_shift_hours", 0) or 0),
        "shift_number": int(getattr(player, "main_shift_number", 0) or 0),
        "shifts_completed_today": int(shifts_completed_today),
        "shift_1_completed": bool(shift_1_completed),
        "shift_2_completed": bool(shift_2_completed),
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
        "salary_payment_status": salary_payment_status,
        "salary_status_label": salary_status_label,
        "salary_status_message": salary_status_message,
        "salary_posting_pending": bool(
            not active_shift and salary_payment_status == SALARY_PAYMENT_STATUS_PENDING
        ),
        "salary_transaction_id": current_salary_transaction_id,
        "salary_posted_at": current_salary_posted_at,
        "salary_transaction_confirmed": salary_transaction_confirmed,
        "current_shift_salary_audit": current_day_salary_audit,
        "last_salary_posted": last_salary_posted,
        "recent_salary_audits": recent_salary_audits,
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
        "last_completed_shift": last_completed_shift_payload,
        "can_rideshare": rideshare_available,
        "rideshare_state": rideshare_state,
        "rideshare_block_reason": rideshare_block_reason,
        "rideshare_unlocked": rideshare_unlocked,
        "rideshare_available": rideshare_available,
        "rideshare_unlock_time_label": schedule["scheduled_shift_end_label"],
        "trips_today": int(rideshare_state.get("trips_today") or 0),
        "trips_remaining": int(rideshare_state.get("remaining_trips") or 0),
        "remaining_time_units": int(rideshare_state.get("hours_remaining_today") or int(getattr(player, "hours_available", 0) or 0)),
        "remaining_side_income_hours_today": round(remaining_side_cap, 4),
        "degraded_sections": [],
        "market_data_available": True,
        "market_data_message": None,
        "action_state_refreshed_at": now.isoformat(),
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
    testing_mode_payload = current_work_state.get("testing_mode") if isinstance(current_work_state, dict) else {}
    if str(current_work_state.get("job_sync_status") or "") == "repair_needed":
        raise ValueError(
            str(current_work_state.get("job_sync_warning_message") or "Your job data is syncing. Please retry in a moment.")
        )
    if bool((testing_mode_payload or {}).get("weekend_rideshare_only")):
        raise ValueError("Weekend testing rule active. No required main shift today - rideshare only.")
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
        "shift.shift_started",
        extra={
            "player_id": str(player.id),
            "shift_id": None,
            "day_number": int(current_day),
            "job_key": normalized_job,
            "salary_amount": 0.0,
            "cash_before": float(cash_before),
            "cash_after": float(_q4(getattr(player, "cash", 0))),
            "transaction_id": None,
            "shift_started_at": work_state.get("shift_started_at"),
            "shift_ends_at": work_state.get("shift_ends_at"),
        },
    )
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
    snapshot = _build_shift_salary_snapshot(
        player,
        current_day=current_day,
        now_houston=now,
        trigger=trigger,
    )
    try:
        audit_row = _record_completed_shift_pending_salary(
            db,
            player=player,
            snapshot=snapshot,
        )
        if audit_row is None:
            raise ValueError("Shift salary audit log could not be created.")
        logger.info(
            "shift.shift_completed",
            extra={
                "player_id": str(player.id),
                "shift_id": str(getattr(audit_row, "shift_id", "") or ""),
                "day_number": int(snapshot.get("current_day") or 1),
                "job_key": str(snapshot.get("job_key") or ""),
                "salary_amount": float(_safe_float(snapshot.get("final_salary_paid"), 0.0)),
                "cash_before": float(_safe_float(snapshot.get("cash_before"), 0.0)),
                "cash_after": float(_safe_float(snapshot.get("cash_before"), 0.0)),
                "transaction_id": None,
                "trigger": trigger,
            },
        )
        refreshed_player = db.query(Player).filter(Player.id == player.id).first() or player
        posted_audit = _post_shift_salary_from_audit(
            db,
            player=refreshed_player,
            audit_row=audit_row,
            trigger=trigger,
            now_houston=now,
        )
        player = refreshed_player
    except Exception as exc:
        failed_audit = _mark_shift_salary_post_failed(
            db,
            player_id=player.id,
            snapshot=snapshot,
            reason=str(exc),
        )
        logger.exception(
            "shift.salary_post_failed",
            extra={
                "player_id": str(player.id),
                "shift_id": str((failed_audit and getattr(failed_audit, "shift_id", "")) or ""),
                "day_number": int(snapshot.get("current_day") or 1),
                "job_key": str(snapshot.get("job_key") or ""),
                "salary_amount": float(_safe_float(snapshot.get("final_salary_paid"), 0.0)),
                "cash_before": float(_safe_float(snapshot.get("cash_before"), 0.0)),
                "cash_after": float(_safe_float(getattr(player, "cash", 0), 0.0)),
                "transaction_id": str((failed_audit and getattr(failed_audit, "salary_transaction_id", "")) or ""),
                "failure_reason": str(exc),
                "trigger": trigger,
            },
        )
        work_state = build_work_state_payload(db, player, now_houston=now)
        return work_state

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
            "authoritative_current_job_id": work_state.get("authoritative_current_job_id"),
            "scheduled_shift_job_id": work_state.get("scheduled_shift_job_id"),
            "active_shift_job_id": work_state.get("active_shift_job_id"),
            "pay_calculation_job_id": work_state.get("pay_calculation_job_id"),
            "ui_job_id": work_state.get("ui_job_id"),
            "job_truth_mismatch_detected": bool(work_state.get("job_truth_mismatch_detected")),
            "salary_transaction_id": str(getattr(posted_audit, "salary_transaction_id", "") or ""),
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
    main_job_sync = inspect_and_repair_main_job_sync(
        db,
        player=player,
        trigger="resolve_expired_shift_if_needed",
        apply_repair=True,
    )
    current_day = _current_game_day_for_player(db, player)
    reset_applied = _maybe_reset_daily_counters(player, current_day)
    started_at = _as_houston(getattr(player, "main_shift_started_at", None))
    ends_at = _as_houston(getattr(player, "main_shift_ends_at", None))
    active_shift = bool(getattr(player, "main_shift_active_flag", False) and getattr(player, "main_shift_status", "") == SHIFT_STATUS_ACTIVE)
    expired = bool(active_shift and ends_at and now >= ends_at)
    if (
        not active_shift
        and str(getattr(player, "main_shift_status", "") or "").strip().lower() == SHIFT_STATUS_COMPLETED
    ):
        _retry_pending_shift_salary_if_needed(
            db,
            player=player,
            day_number=current_day,
            now_houston=now,
        )
        db.refresh(player)

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
            "job_sync_status": str(main_job_sync.get("sync_status") or ""),
            "job_sync_repair_applied": bool(main_job_sync.get("repair_applied")),
        },
    )

    try:
        rollover_result = _run_houston_auto_rollover_if_needed(db, player=player, now_houston=now)
    except Exception as exc:
        db.rollback()
        db.refresh(player)
        logger.exception(
            "shift.resolve_expired_shift_if_needed auto_rollover_degraded",
            extra={
                "player_id": str(player.id),
                "current_houston_time": now.isoformat(),
                "reason": str(exc),
            },
        )
        rollover_result = _rollover_degraded_result(
            player=player,
            now_houston=now,
            reason=str(exc),
        )
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
        work_state = _apply_main_job_sync_result_to_work_state(work_state, main_job_sync)
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
        work_state = _apply_market_degradation_to_work_state(
            work_state,
            rollover_result=rollover_result,
        )
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
        finalized_state = _apply_main_job_sync_result_to_work_state(finalized_state, main_job_sync)
        finalized_state["offline_survival_catchup"] = catchup_result
        finalized_state["auto_day_rollover"] = rollover_result
        finalized_state["auto_finalized_previous_day"] = False
        finalized_state["auto_finalized_days_count"] = 0
        finalized_state["new_day_started_houston_time"] = False
        finalized_state["auto_rollover_recap_lines"] = []
        finalized_state = _apply_market_degradation_to_work_state(
            finalized_state,
            rollover_result=rollover_result,
        )
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
        or bool(main_job_sync.get("repair_applied"))
        or int(catchup_result.get("applied_days") or 0) > 0
        or bool(catchup_result.get("sync_date_updated"))
    ):
        db.commit()
        db.refresh(player)

    work_state = build_work_state_payload(db, player, now_houston=now)
    work_state = _apply_main_job_sync_result_to_work_state(work_state, main_job_sync)
    work_state["offline_survival_catchup"] = catchup_result
    work_state["auto_day_rollover"] = rollover_result
    work_state["auto_finalized_previous_day"] = False
    work_state["auto_finalized_days_count"] = 0
    work_state["new_day_started_houston_time"] = False
    work_state["auto_rollover_recap_lines"] = []
    work_state = _apply_market_degradation_to_work_state(
        work_state,
        rollover_result=rollover_result,
    )
    return work_state

