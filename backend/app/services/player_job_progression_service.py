"""Per-job skill/XP/promotion progression service (Step 92 safe mode)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.career_config import CAREER_CONFIG
from app.models.job_definition import JOB_CATALOG
from app.models.player_job_progression import PlayerJobProgression
from app.services.job_key_service import normalize_main_job_key

# STEP 93G — simplified 2-tier career progression.
# Level 1 = Junior (0 -> 100 XP), Level 2 = Senior (100 -> 2000 XP cap).
# Future tiers (Professional, Expert) are intentionally not implemented yet.
JOB_LEVEL_THRESHOLDS_TOTAL_XP: dict[int, int] = {
    1: 0,     # Junior
    2: 100,   # Senior
}

# Senior tier caps at this total XP value. Any further XP is clamped.
SENIOR_CAP_XP = 2000

SHIFT_COMPLETION_XP_GAIN = 10          # Regular OR Overtime shift completion
TRAINING_SESSION_XP_GAIN = 25          # Per 1-hour certification training session
MAX_LEVEL = max(JOB_LEVEL_THRESHOLDS_TOTAL_XP.keys())  # 2
SALARY_PREVIEW_GROWTH_PER_LEVEL = Decimal("0.03")


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


def _money_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _canonical_job_key(job_key: str | None) -> str:
    return normalize_main_job_key(job_key, allow_aliases=True) or str(job_key or "").strip().lower()


def resolve_level_from_total_xp(total_xp: int) -> int:
    xp = max(0, int(total_xp))
    resolved = 1
    for level, threshold in sorted(JOB_LEVEL_THRESHOLDS_TOTAL_XP.items()):
        if xp >= threshold:
            resolved = level
    return min(MAX_LEVEL, max(1, resolved))


def promotion_tier_for_level(level: int) -> str:
    lvl = max(1, int(level))
    if lvl <= 1:
        return "Junior"
    return "Senior"


def _level_bounds(level: int) -> tuple[int, int | None]:
    safe_level = min(MAX_LEVEL, max(1, int(level)))
    current_floor = JOB_LEVEL_THRESHOLDS_TOTAL_XP.get(safe_level, 0)
    if safe_level >= MAX_LEVEL:
        # Senior (top tier) still has an in-tier XP cap for progress UI.
        return current_floor, SENIOR_CAP_XP
    next_level = safe_level + 1
    return current_floor, JOB_LEVEL_THRESHOLDS_TOTAL_XP.get(next_level)


def base_monthly_salary_for_job(job_key: str | None) -> float:
    key = _canonical_job_key(job_key)
    cfg = CAREER_CONFIG.get(key)
    if cfg is not None:
        return float(_money_decimal(cfg.base_pay_reference))
    static = JOB_CATALOG.get(key)
    if static is not None:
        return float(_money_decimal(static.monthly_salary))
    return 0.0


def estimated_salary_for_level(*, base_monthly_salary: float, level: int) -> float:
    base = _money_decimal(base_monthly_salary)
    growth_steps = max(0, min(MAX_LEVEL, int(level)) - 1)
    multiplier = Decimal("1.00") + (Decimal(growth_steps) * SALARY_PREVIEW_GROWTH_PER_LEVEL)
    return float(_money_decimal(base * multiplier))


def _apply_level_fields(row: PlayerJobProgression) -> None:
    total_xp = max(0, _safe_int(getattr(row, "xp_total", 0), 0))
    level = resolve_level_from_total_xp(total_xp)
    floor_xp, next_floor_xp = _level_bounds(level)
    row.skill_level = level
    row.promotion_tier = promotion_tier_for_level(level)
    if next_floor_xp is None:
        row.xp = 0
        row.xp_to_next_level = 0
    else:
        row.xp = max(0, total_xp - floor_xp)
        row.xp_to_next_level = max(0, next_floor_xp - floor_xp)


def get_player_job_progression(
    db: Session,
    *,
    player_id: UUID | str,
    job_key: str | None,
) -> PlayerJobProgression | None:
    key = _canonical_job_key(job_key)
    if not key:
        return None
    return (
        db.query(PlayerJobProgression)
        .filter(
            PlayerJobProgression.player_id == UUID(str(player_id)),
            PlayerJobProgression.job_key == key,
        )
        .first()
    )


def get_or_create_player_job_progression(
    db: Session,
    *,
    player_id: UUID | str,
    job_key: str | None,
) -> PlayerJobProgression | None:
    key = _canonical_job_key(job_key)
    if not key:
        return None
    row = get_player_job_progression(db, player_id=player_id, job_key=key)
    if row is not None:
        _apply_level_fields(row)
        return row

    row = PlayerJobProgression(
        player_id=UUID(str(player_id)),
        job_key=key,
        skill_level=1,
        xp_total=0,
        xp=0,
        xp_to_next_level=max(0, JOB_LEVEL_THRESHOLDS_TOTAL_XP.get(2, 100)),
        promotion_tier=promotion_tier_for_level(1),
        shifts_completed=0,
    )
    db.add(row)
    db.flush()
    return row


def build_job_progression_snapshot(
    row: PlayerJobProgression | None,
    *,
    fallback_job_key: str | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    _apply_level_fields(row)
    job_key = _canonical_job_key(getattr(row, "job_key", None) or fallback_job_key)
    level = max(1, _safe_int(getattr(row, "skill_level", 1), 1))
    base_salary = base_monthly_salary_for_job(job_key)
    current_salary_estimate = estimated_salary_for_level(
        base_monthly_salary=base_salary,
        level=level,
    )
    next_level = min(MAX_LEVEL, level + 1)
    next_salary_estimate = estimated_salary_for_level(
        base_monthly_salary=base_salary,
        level=next_level,
    )
    return {
        "job_key": job_key,
        "job_level": level,
        "skill_level": level,
        "xp_total": max(0, _safe_int(getattr(row, "xp_total", 0), 0)),
        "job_xp": max(0, _safe_int(getattr(row, "xp", 0), 0)),
        "job_xp_to_next_level": max(0, _safe_int(getattr(row, "xp_to_next_level", 0), 0)),
        "max_job_level": MAX_LEVEL,
        "promotion_tier": str(getattr(row, "promotion_tier", "") or promotion_tier_for_level(level)),
        "shifts_completed": max(0, _safe_int(getattr(row, "shifts_completed", 0), 0)),
        "last_worked_at": (
            getattr(row, "last_worked_at", None).isoformat()
            if getattr(row, "last_worked_at", None) is not None
            else None
        ),
        "base_salary_xgp": round(base_salary, 2),
        "estimated_current_monthly_salary_xgp": round(current_salary_estimate, 2),
        "estimated_next_level_monthly_salary_xgp": round(next_salary_estimate, 2),
        "next_level_salary_increase_pct": float(SALARY_PREVIEW_GROWTH_PER_LEVEL * Decimal("100")),
        "salary_preview_note": "Estimated only - live payroll remains unchanged.",
    }


def award_completed_shift_xp(
    db: Session,
    *,
    player_id: UUID | str,
    job_key: str | None,
    xp_gain: int = SHIFT_COMPLETION_XP_GAIN,
    worked_at: datetime | None = None,
) -> dict[str, Any] | None:
    row = get_or_create_player_job_progression(db, player_id=player_id, job_key=job_key)
    if row is None:
        return None

    _apply_level_fields(row)
    before_level = max(1, _safe_int(getattr(row, "skill_level", 1), 1))
    before_tier = str(getattr(row, "promotion_tier", "") or promotion_tier_for_level(before_level))
    gained = max(0, int(xp_gain))

    row.xp_total = min(
        SENIOR_CAP_XP,
        max(0, _safe_int(getattr(row, "xp_total", 0), 0) + gained),
    )
    row.shifts_completed = max(0, _safe_int(getattr(row, "shifts_completed", 0), 0) + 1)
    row.last_worked_at = worked_at or datetime.now(timezone.utc)
    _apply_level_fields(row)
    db.flush()

    after_level = max(1, _safe_int(getattr(row, "skill_level", 1), 1))
    after_tier = str(getattr(row, "promotion_tier", "") or promotion_tier_for_level(after_level))
    snapshot = build_job_progression_snapshot(row)
    leveled_up = after_level > before_level

    return {
        "job_key": _canonical_job_key(job_key),
        "xp_gained": gained,
        "level_before": before_level,
        "level_after": after_level,
        "promotion_tier_before": before_tier,
        "promotion_tier_after": after_tier,
        "leveled_up": leveled_up,
        "tier_changed": after_tier != before_tier,
        "progression": snapshot,
        "feedback_message": (
            f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} reached Level {after_level}"
            if leveled_up
            else f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} XP +{gained}"
        ),
    }


def award_training_session_xp(
    db: Session,
    *,
    player_id: UUID | str,
    job_key: str | None,
    xp_gain: int = TRAINING_SESSION_XP_GAIN,
) -> dict[str, Any] | None:
    """STEP 93G — award +25 XP for a completed certification training session.

    Unlike shift completion this does NOT increment shifts_completed and does
    not update last_worked_at. Only certification-track jobs should call this.
    """
    row = get_or_create_player_job_progression(db, player_id=player_id, job_key=job_key)
    if row is None:
        return None

    _apply_level_fields(row)
    before_level = max(1, _safe_int(getattr(row, "skill_level", 1), 1))
    before_tier = str(getattr(row, "promotion_tier", "") or promotion_tier_for_level(before_level))
    gained = max(0, int(xp_gain))

    row.xp_total = min(
        SENIOR_CAP_XP,
        max(0, _safe_int(getattr(row, "xp_total", 0), 0) + gained),
    )
    _apply_level_fields(row)
    db.flush()

    after_level = max(1, _safe_int(getattr(row, "skill_level", 1), 1))
    after_tier = str(getattr(row, "promotion_tier", "") or promotion_tier_for_level(after_level))
    snapshot = build_job_progression_snapshot(row)
    leveled_up = after_level > before_level

    return {
        "job_key": _canonical_job_key(job_key),
        "xp_gained": gained,
        "level_before": before_level,
        "level_after": after_level,
        "promotion_tier_before": before_tier,
        "promotion_tier_after": after_tier,
        "leveled_up": leveled_up,
        "tier_changed": after_tier != before_tier,
        "progression": snapshot,
        "feedback_message": (
            f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} reached Level {after_level}"
            if leveled_up
            else f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} training XP +{gained}"
        ),
    }


def list_player_job_progressions(
    db: Session,
    *,
    player_id: UUID | str,
) -> list[PlayerJobProgression]:
    rows = (
        db.query(PlayerJobProgression)
        .filter(PlayerJobProgression.player_id == UUID(str(player_id)))
        .order_by(PlayerJobProgression.updated_at.desc(), PlayerJobProgression.created_at.desc())
        .all()
    )
    for row in rows:
        _apply_level_fields(row)
    return rows


def progression_lookup_map(
    db: Session,
    *,
    player_id: UUID | str,
) -> dict[str, dict[str, Any]]:
    rows = list_player_job_progressions(db, player_id=player_id)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _canonical_job_key(getattr(row, "job_key", None))
        if not key:
            continue
        snap = build_job_progression_snapshot(row, fallback_job_key=key)
        if snap:
            result[key] = snap
    return result


def safe_default_progression_for_job(job_key: str | None) -> dict[str, Any]:
    key = _canonical_job_key(job_key)
    level = 1
    base_salary = base_monthly_salary_for_job(key)
    return {
        "job_key": key,
        "job_level": level,
        "skill_level": level,
        "xp_total": 0,
        "job_xp": 0,
        "job_xp_to_next_level": max(0, JOB_LEVEL_THRESHOLDS_TOTAL_XP.get(2, 100)),
        "max_job_level": MAX_LEVEL,
        "promotion_tier": promotion_tier_for_level(level),
        "shifts_completed": 0,
        "last_worked_at": None,
        "base_salary_xgp": round(base_salary, 2),
        "estimated_current_monthly_salary_xgp": round(
            estimated_salary_for_level(base_monthly_salary=base_salary, level=level), 2
        ),
        "estimated_next_level_monthly_salary_xgp": round(
            estimated_salary_for_level(base_monthly_salary=base_salary, level=min(MAX_LEVEL, level + 1)),
            2,
        ),
        "next_level_salary_increase_pct": float(SALARY_PREVIEW_GROWTH_PER_LEVEL * Decimal("100")),
        "salary_preview_note": "Estimated only - live payroll remains unchanged.",
    }
