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
# Phase 1: Junior 0→100 XP (Level 1).  At 100 XP: +10% salary, XP display
#   resets to 0/2000 but tier stays Junior.
# Phase 2: Junior 100→2100 total XP. Every 100 XP beyond the first 100 earns
#   +0.3% salary.  Tier still shows Junior.
# Phase 3: Senior at 2100 total XP (100 + 2000). Additional +20% base salary
#   bonus on top of accumulated increases.
PHASE1_XP_CAP = 100          # XP needed to complete phase 1
PHASE2_XP_CAP = 2000         # Additional XP in phase 2 (total = 2100)
TOTAL_XP_FOR_SENIOR = PHASE1_XP_CAP + PHASE2_XP_CAP  # 2100
SENIOR_CAP_XP = TOTAL_XP_FOR_SENIOR

SHIFT_COMPLETION_XP_GAIN = 10          # Regular OR Overtime shift completion
TRAINING_SESSION_XP_GAIN = 25          # Per 1-hour certification training session
MAX_LEVEL = 1                          # Display level is always 1 (Junior) until Senior

# Salary growth constants
PHASE1_COMPLETION_SALARY_BONUS = Decimal("0.10")    # +10% at 100 XP
PHASE2_PER_100_XP_SALARY_BONUS = Decimal("0.003")   # +0.3% per 100 XP after phase 1
SENIOR_PROMOTION_SALARY_BONUS = Decimal("0.20")      # +20% base at Senior


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
    """Always returns 1 (Junior) until Senior threshold is reached."""
    xp = max(0, int(total_xp))
    if xp >= TOTAL_XP_FOR_SENIOR:
        return 2  # Senior
    return 1  # Junior


def promotion_tier_for_level(level: int) -> str:
    lvl = max(1, int(level))
    if lvl >= 2:
        return "Senior"
    return "Junior"


def _xp_phase(total_xp: int) -> tuple[int, int, int]:
    """Return (phase, xp_in_phase, xp_cap_of_phase).

    Phase 1: total_xp < 100  →  (1, total_xp, 100)
    Phase 2: 100 <= total_xp < 2100  →  (2, total_xp - 100, 2000)
    Phase 3: total_xp >= 2100  →  (3, 0, 0)  — Senior, capped
    """
    xp = max(0, int(total_xp))
    if xp < PHASE1_XP_CAP:
        return 1, xp, PHASE1_XP_CAP
    if xp < TOTAL_XP_FOR_SENIOR:
        return 2, xp - PHASE1_XP_CAP, PHASE2_XP_CAP
    return 3, 0, 0


def base_monthly_salary_for_job(job_key: str | None) -> float:
    key = _canonical_job_key(job_key)
    cfg = CAREER_CONFIG.get(key)
    if cfg is not None:
        return float(_money_decimal(cfg.base_pay_reference))
    static = JOB_CATALOG.get(key)
    if static is not None:
        return float(_money_decimal(static.monthly_salary))
    return 0.0


def salary_multiplier_for_total_xp(total_xp: int) -> Decimal:
    """Compute the cumulative salary multiplier based on total XP.

    - At 100 XP: +10% (multiplier = 1.10)
    - Every 100 XP after 100: +0.3% each (e.g. at 200 total → 1.103, at 300 → 1.106)
    - At 2100 XP (Senior): additional +20% of base on top
      (so 20 intervals × 0.3% = 6% + 10% + 20% = 36% → multiplier = 1.36)
    """
    xp = max(0, int(total_xp))
    mult = Decimal("1.00")
    if xp >= PHASE1_XP_CAP:
        mult += PHASE1_COMPLETION_SALARY_BONUS  # +10%
        xp_in_phase2 = min(xp - PHASE1_XP_CAP, PHASE2_XP_CAP)
        increments = xp_in_phase2 // 100
        mult += Decimal(increments) * PHASE2_PER_100_XP_SALARY_BONUS
    if xp >= TOTAL_XP_FOR_SENIOR:
        mult += SENIOR_PROMOTION_SALARY_BONUS  # +20%
    return mult


def estimated_salary_for_xp(*, base_monthly_salary: float, total_xp: int) -> float:
    base = _money_decimal(base_monthly_salary)
    multiplier = salary_multiplier_for_total_xp(total_xp)
    return float(_money_decimal(base * multiplier))


def _apply_level_fields(row: PlayerJobProgression) -> None:
    total_xp = max(0, _safe_int(getattr(row, "xp_total", 0), 0))
    level = resolve_level_from_total_xp(total_xp)
    phase, xp_in_phase, xp_cap = _xp_phase(total_xp)
    row.skill_level = level
    row.promotion_tier = promotion_tier_for_level(level)
    if phase == 3:
        # Senior — fully capped
        row.xp = 0
        row.xp_to_next_level = 0
    else:
        row.xp = xp_in_phase
        row.xp_to_next_level = xp_cap


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
        xp_to_next_level=PHASE1_XP_CAP,
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
    total_xp = max(0, _safe_int(getattr(row, "xp_total", 0), 0))
    base_salary = base_monthly_salary_for_job(job_key)
    current_salary_estimate = estimated_salary_for_xp(
        base_monthly_salary=base_salary,
        total_xp=total_xp,
    )
    # Preview: what salary would be at the next 100 XP milestone
    phase, xp_in_phase, xp_cap = _xp_phase(total_xp)
    if phase == 1:
        next_milestone_xp = PHASE1_XP_CAP
        next_increase_pct = float(PHASE1_COMPLETION_SALARY_BONUS * Decimal("100"))  # 10%
    elif phase == 2:
        next_100 = ((xp_in_phase // 100) + 1) * 100
        next_milestone_xp = PHASE1_XP_CAP + min(next_100, PHASE2_XP_CAP)
        if next_100 >= PHASE2_XP_CAP:
            # Next milestone is Senior promotion
            next_increase_pct = float(
                (PHASE2_PER_100_XP_SALARY_BONUS + SENIOR_PROMOTION_SALARY_BONUS) * Decimal("100")
            )
        else:
            next_increase_pct = float(PHASE2_PER_100_XP_SALARY_BONUS * Decimal("100"))  # 0.3%
    else:
        next_milestone_xp = TOTAL_XP_FOR_SENIOR
        next_increase_pct = 0.0
    next_salary_estimate = estimated_salary_for_xp(
        base_monthly_salary=base_salary,
        total_xp=next_milestone_xp,
    )
    return {
        "job_key": job_key,
        "job_level": level,
        "skill_level": level,
        "xp_total": total_xp,
        "job_xp": max(0, _safe_int(getattr(row, "xp", 0), 0)),
        "job_xp_to_next_level": max(0, _safe_int(getattr(row, "xp_to_next_level", 0), 0)),
        "max_job_level": 2,  # Senior is the visual max
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
        "next_level_salary_increase_pct": round(next_increase_pct, 1),
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
            f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} promoted to Senior!"
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
            f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} promoted to Senior!"
            if leveled_up
            else f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} training XP +{gained}"
        ),
    }


def award_job_bonus_xp(
    db: Session,
    *,
    player_id: UUID | str,
    job_key: str | None,
    xp_gain: int,
    worked_at: datetime | None = None,
    reason_label: str = "Shift task",
) -> dict[str, Any] | None:
    """Award bonus XP without incrementing shift-completion counts."""
    row = get_or_create_player_job_progression(db, player_id=player_id, job_key=job_key)
    if row is None:
        return None

    _apply_level_fields(row)
    before_level = max(1, _safe_int(getattr(row, "skill_level", 1), 1))
    before_tier = str(getattr(row, "promotion_tier", "") or promotion_tier_for_level(before_level))
    gained = max(0, int(xp_gain))
    if gained <= 0:
        return None

    row.xp_total = min(
        SENIOR_CAP_XP,
        max(0, _safe_int(getattr(row, "xp_total", 0), 0) + gained),
    )
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
            f"{str((snapshot or {}).get('job_key') or job_key or 'Job').replace('_', ' ').title()} promoted to Senior!"
            if leveled_up
            else f"{reason_label} XP +{gained}"
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
        "job_xp_to_next_level": PHASE1_XP_CAP,
        "max_job_level": 2,
        "promotion_tier": promotion_tier_for_level(level),
        "shifts_completed": 0,
        "last_worked_at": None,
        "base_salary_xgp": round(base_salary, 2),
        "estimated_current_monthly_salary_xgp": round(
            estimated_salary_for_xp(base_monthly_salary=base_salary, total_xp=0), 2
        ),
        "estimated_next_level_monthly_salary_xgp": round(
            estimated_salary_for_xp(base_monthly_salary=base_salary, total_xp=PHASE1_XP_CAP), 2
        ),
        "next_level_salary_increase_pct": float(PHASE1_COMPLETION_SALARY_BONUS * Decimal("100")),
        "salary_preview_note": "Estimated only - live payroll remains unchanged.",
    }
