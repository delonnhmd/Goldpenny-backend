"""Shared helpers for job progression metadata and employment snapshots."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.career_config import CAREER_CONFIG
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.services.job_key_service import job_key_lookup_variants, normalize_main_job_key

SHIFT_PROFILES: dict[str, dict[str, Any]] = {
    "morning_shift": {
        "label": "Morning Shift",
        "window": "5:00-13:00",
        "hours_worked": 4,
        "stress_modifier": 0.9,
        "health_modifier": 1.05,
    },
    "standard_shift": {
        "label": "Standard Shift",
        "window": "9:00-17:00",
        "hours_worked": 6,
        "stress_modifier": 1.0,
        "health_modifier": 1.0,
    },
    "long_shift": {
        "label": "Long Shift",
        "window": "9:00-21:00",
        "hours_worked": 8,
        "stress_modifier": 1.2,
        "health_modifier": 0.9,
    },
}

JOB_COMPANY_MAP: dict[str, dict[str, str]] = {
    "auto_mechanic": {"symbol": "GP_AUTO", "name": "GP Auto", "position": "Auto Mechanic"},
    "aircraft_mechanic": {"symbol": "GP_TRANSPORT", "name": "GP Transport", "position": "Aircraft Mechanic"},
    "banker": {"symbol": "GP_BANK", "name": "GP Bank", "position": "Junior Banker"},
    "chef": {"symbol": "GP_CONSUMER", "name": "GP Consumer", "position": "Kitchen Lead"},
    "cleaner": {"symbol": "GP_SERVICES", "name": "GP Services", "position": "Cleaner"},
    "warehouse_operator": {"symbol": "GP_LOGISTICS", "name": "GP Logistics", "position": "Warehouse Manager"},
    "real_estate_agent": {"symbol": "GP_REALTY", "name": "GP Realty", "position": "Real Estate Agent"},
    "retail": {"symbol": "GP_RETAIL", "name": "GP Retail", "position": "Retail Seller"},
    "delivery": {"symbol": "GP_TRANSPORT", "name": "GP Transport", "position": "Delivery Driver"},
    "rideshare": {"symbol": "GP_TRANSPORT", "name": "GP Transport", "position": "Ride Share Driver"},
}

JOB_LEVEL_MAX = 40
JOB_LEVEL_XP_BASE = 100
JOB_LEVEL_XP_STEP = 20
JOB_XP_PER_WORK_HOUR = 25
JOB_SALARY_GROWTH_PER_LEVEL = Decimal("0.025")


def _money_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def xp_required_for_next_level(level: int) -> int:
    safe_level = max(1, min(level, JOB_LEVEL_MAX))
    return int(JOB_LEVEL_XP_BASE + ((safe_level - 1) * JOB_LEVEL_XP_STEP))


def latest_employment_state(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def latest_employment_state_for_job(
    db: Session,
    *,
    player_id: UUID,
    job_key: str,
) -> PlayerEmploymentState | None:
    variants = job_key_lookup_variants(job_key, allow_side_jobs=False)
    if not variants:
        return None
    return (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player_id,
            func.lower(PlayerEmploymentState.current_job_code).in_(variants),
        )
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def base_monthly_pay_for_job(job_key: str) -> Decimal:
    normalized_job_key = normalize_main_job_key(job_key, allow_aliases=True) or str(job_key or "").strip().lower()
    cfg = CAREER_CONFIG.get(normalized_job_key)
    if cfg is not None:
        return _money_decimal(cfg.base_pay_reference)
    return _money_decimal(3200)


def build_job_progress_payload(
    row: PlayerEmploymentState | None,
    *,
    fallback_job_key: str | None = None,
    fallback_shift_type: str | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    level = max(1, min(_safe_int(getattr(row, "skill_level", 1), 1), JOB_LEVEL_MAX))
    xp = max(0, _safe_int(getattr(row, "job_level_xp", 0), 0))
    xp_to_next = max(0, _safe_int(getattr(row, "job_level_xp_to_next", xp_required_for_next_level(level)), 0))
    if level >= JOB_LEVEL_MAX:
        xp = 0
        xp_to_next = 0
    resolved_job_key = normalize_main_job_key(
        getattr(row, "current_job_code", None) or fallback_job_key or "",
        allow_aliases=True,
    ) or str(getattr(row, "current_job_code", None) or fallback_job_key or "")

    return {
        "job_key": resolved_job_key,
        "job_level": level,
        "skill_level": level,
        "job_xp": xp,
        "job_xp_to_next_level": xp_to_next,
        "max_job_level": JOB_LEVEL_MAX,
        "monthly_pay_xgp": _safe_float(getattr(row, "monthly_pay_xgp", 0), 0.0),
        "employer_company_symbol": getattr(row, "employer_company_symbol", None),
        "employer_company_name": getattr(row, "employer_company_name", None),
        "position_title": getattr(row, "position_title", None),
        "shift_type": str(getattr(row, "shift_type", None) or fallback_shift_type or "standard_shift"),
    }


def normalize_shift_type(raw_shift: Any) -> str:
    key = str(raw_shift or "").strip().lower()
    if key in SHIFT_PROFILES:
        return key
    return "standard_shift"


def work_xp_for_hours(hours_worked: int) -> int:
    return max(5, int(max(1, hours_worked) * JOB_XP_PER_WORK_HOUR))


def upsert_employment_foundation(
    db: Session,
    *,
    player: Player,
    settled_day: int,
    job_key: str | None,
    shift_type: str | None,
    grant_work_xp: int = 0,
) -> dict[str, Any] | None:
    key = normalize_main_job_key(job_key, allow_aliases=True)
    if not key:
        return None

    company = JOB_COMPANY_MAP.get(
        key,
        {"symbol": "GP_CONSUMER", "name": "Gold Penny Group", "position": key.replace("_", " ").title()},
    )
    normalized_shift = normalize_shift_type(shift_type)
    previous_for_job = latest_employment_state_for_job(db, player_id=player.id, job_key=key)

    row = (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player.id,
            PlayerEmploymentState.day == int(settled_day),
        )
        .first()
    )
    if row is None:
        row = PlayerEmploymentState(
            player_id=player.id,
            day=int(settled_day),
            current_job_code=key,
            monthly_pay_xgp=base_monthly_pay_for_job(key),
            employed_flag=True,
            job_status="employed",
        )
        db.add(row)
        db.flush()

    base_level = max(
        1,
        min(
            _safe_int(
                getattr(previous_for_job, "skill_level", None),
                _safe_int(getattr(player, "skill_level", None), 1),
            ),
            JOB_LEVEL_MAX,
        ),
    )
    row.skill_level = base_level
    row.job_level_xp = max(0, _safe_int(getattr(previous_for_job, "job_level_xp", None), 0))
    row.job_level_xp_to_next = max(
        0,
        _safe_int(
            getattr(previous_for_job, "job_level_xp_to_next", None),
            xp_required_for_next_level(base_level),
        ),
    )

    row.current_job_code = key
    row.position_title = company["position"]
    row.employer_company_symbol = company["symbol"]
    row.employer_company_name = company["name"]
    row.shift_type = normalized_shift
    row.employed_flag = True
    row.job_status = "employed"

    earned_xp = max(0, int(grant_work_xp))
    level = max(1, min(_safe_int(getattr(row, "skill_level", 1), 1), JOB_LEVEL_MAX))
    xp = max(0, _safe_int(getattr(row, "job_level_xp", 0), 0))
    xp_to_next = max(1, _safe_int(getattr(row, "job_level_xp_to_next", xp_required_for_next_level(level)), 1))
    leveled_up = False

    while earned_xp > 0 and level < JOB_LEVEL_MAX:
        needed = max(1, xp_to_next - xp)
        if earned_xp >= needed:
            earned_xp -= needed
            level += 1
            xp = 0
            xp_to_next = xp_required_for_next_level(level) if level < JOB_LEVEL_MAX else 0
            leveled_up = True
        else:
            xp += earned_xp
            earned_xp = 0

    if level >= JOB_LEVEL_MAX:
        level = JOB_LEVEL_MAX
        xp = 0
        xp_to_next = 0

    row.skill_level = level
    row.job_level_xp = xp
    row.job_level_xp_to_next = xp_to_next
    player.skill_level = max(_safe_int(getattr(player, "skill_level", 1), 1), level)

    base_monthly_pay = base_monthly_pay_for_job(key)
    salary_multiplier = Decimal("1.00") + (Decimal(level - 1) * JOB_SALARY_GROWTH_PER_LEVEL)
    row.monthly_pay_xgp = _money_decimal(base_monthly_pay * salary_multiplier)
    if leveled_up:
        row.last_employment_event = "level_up"
    elif getattr(row, "last_employment_event", None) in (None, "", "none"):
        row.last_employment_event = "work_progress"

    return build_job_progress_payload(row)
