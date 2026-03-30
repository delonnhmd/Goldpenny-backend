"""Step 18: Career progression service — skill growth, promotion, certification management.

Public surface:
  - get_or_create_player_career(db, player_id) -> PlayerCareer
  - compute_daily_skill_growth(...) -> Decimal
  - compute_daily_performance_score(...) -> Decimal
  - compute_promotion_progress(...) -> Decimal
  - attempt_promotion(db, career, day) -> bool
  - start_certification_track(db, player_id, track_key) -> dict
  - update_certification_progress(db, career, training_hours_today) -> tuple[int, bool]
  - complete_certification_if_eligible(db, career) -> bool
  - switch_player_job(db, player_id, new_job_key, as_of_date=None) -> dict
  - get_player_career_snapshot(db, player_id) -> dict
  - get_player_career_history(db, player_id, limit=30) -> dict
  - apply_daily_career_progression(db, player_id, as_of_date=None) -> dict
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.engine.career_config import (
    CAREER_CONFIG,
    CERTIFICATION_CATALOG,
    RANK_ENTRY,
    RANK_ORDER,
    SKILL_DELTA_CEILING,
    SKILL_DELTA_FLOOR,
    SKILL_MAX,
    SKILL_MIN,
    PERF_MIN,
    PERF_MAX,
    STRESS_HIGH_THRESHOLD,
    HEALTH_LOW_THRESHOLD,
    TRAINING_HOURS_MAX,
    TRAINING_HOURS_MIN,
    VALID_JOB_KEYS,
    effective_monthly_pay,
    get_job_config,
    get_promotion_threshold,
    next_rank,
)
from app.models.career_progress_log import CareerProgressLog
from app.models.player import Player
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.services.job_key_service import normalize_main_job_key, require_canonical_main_job_key

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
logger = logging.getLogger(__name__)

GAME_EPOCH = date(2026, 1, 1)

# Trailing performance EMA alpha (7-day-ish smoothing)
# new_trailing = alpha * daily + (1 - alpha) * old_trailing
PERF_EMA_ALPHA = Decimal("0.20")

# Minimum training hours per day to advance certification
CERT_MIN_DAILY_TRAINING_HOURS = Decimal("1.00")

# Transfer skill bonus when switching to a related job (fraction of old skill applied)
RELATED_JOB_SKILL_TRANSFER = {
    ("auto_mechanic", "aircraft_mechanic"): Decimal("0.15"),
}

# Time cost of training (hours consumed from daily budget per training hour)
# 1 training hour = 1 hour from time budget (opportunity cost)
TRAINING_TIME_COST_RATIO = Decimal("1.00")

# Stress increase per training-hour when already stressed
TRAINING_STRESS_COST_RATE = Decimal("0.40")


# ── Custom exceptions ──────────────────────────────────────────────────────────

class CareerError(Exception):
    """Base exception for career service operations."""


class CareerNotFoundError(CareerError):
    """Raised when player or career state does not exist."""


class CareerValidationError(CareerError):
    """Raised when a career operation violates business rules."""


# ── Internal helpers ───────────────────────────────────────────────────────────

def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _day_to_date(day: int) -> date:
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(d: date) -> int:
    return int((d - GAME_EPOCH).days) + 1


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise CareerNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise CareerNotFoundError("Player not found.")
    return row


def _latest_employment_state(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _latest_daily_state(db: Session, player_id: UUID, day: int) -> PlayerDailyState | None:
    row = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player_id,
            PlayerDailyState.day_number == day,
        )
        .first()
    )
    if row is not None:
        return row
    # fall back to most-recent settled state
    return (
        db.query(PlayerDailyState)
        .filter(PlayerDailyState.player_id == player_id)
        .order_by(PlayerDailyState.day_number.desc())
        .first()
    )


def _parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


# ── Core public functions ──────────────────────────────────────────────────────

def get_or_create_player_career(db: Session, player_id: str | UUID) -> PlayerCareer:
    """Return existing career state row, or create a blank one seeded from player.main_job."""
    player = _resolve_player(db, player_id)
    career = (
        db.query(PlayerCareer)
        .filter(PlayerCareer.player_id == player.id)
        .first()
    )
    if career is not None:
        canonical_player_job = normalize_main_job_key(player.main_job, allow_aliases=True)
        canonical_career_job = normalize_main_job_key(career.current_job_key, allow_aliases=True)
        changed = False
        if canonical_player_job and player.main_job != canonical_player_job:
            player.main_job = canonical_player_job
            changed = True
        if canonical_career_job and career.current_job_key != canonical_career_job:
            career.current_job_key = canonical_career_job
            changed = True
        elif canonical_career_job is None and canonical_player_job and not career.current_job_key:
            career.current_job_key = canonical_player_job
            changed = True
        if changed:
            db.flush()
        return career

    # Seed from player.main_job if valid
    job_key = normalize_main_job_key(player.main_job, allow_aliases=True)
    if job_key not in VALID_JOB_KEYS:
        job_key = None  # type: ignore[assignment]

    career = PlayerCareer(
        player_id=player.id,
        current_job_key=job_key,
        current_job_rank=RANK_ENTRY,
        current_job_skill=Decimal("0.0"),
        total_days_worked_in_job=0,
        trailing_performance_score=Decimal("0.0"),
        promotion_eligible=False,
        certification_track_key=None,
        certification_progress_days=0,
        certification_required_days=0,
        certification_completed=False,
        last_promotion_day=None,
    )
    db.add(career)
    db.flush()
    return career


def compute_daily_skill_growth(
    *,
    job_key: str,
    worked_today: bool,
    productivity_modifier: Decimal,
    stress: int,
    health: int,
    training_hours: Decimal,
) -> Decimal:
    """Return the skill delta for one day of work/training.

    Breakdown:
      worked_today_component: base gain if player worked
      productivity_bonus / malus: from productivity_modifier
      training_component: extra gain from allocated training hours
      stress_penalty: applied when stress > threshold
      health_penalty: applied when health is low

    All deltas are clamped to [SKILL_DELTA_FLOOR, SKILL_DELTA_CEILING].
    """
    cfg = get_job_config(job_key)

    # Base component — only granted when player actually worked the job
    if worked_today:
        worked_component = cfg.skill_growth_rate
        # productivity bonus/malus
        prod = _d(productivity_modifier)
        if prod > Decimal("1.0"):
            prod_delta = (prod - Decimal("1.0")) * Decimal("0.15")
        else:
            prod_delta = (prod - Decimal("1.0")) * Decimal("0.40")
        worked_component = worked_component + prod_delta
    else:
        worked_component = Decimal("0.00")

    # Training component
    t_hours = _clamp(_d(training_hours), TRAINING_HOURS_MIN, TRAINING_HOURS_MAX)
    training_component = t_hours * cfg.training_skill_rate

    # Stress penalty — applies regardless of whether player worked
    s = Decimal(str(stress))
    if s > STRESS_HIGH_THRESHOLD:
        stress_penalty = (s - STRESS_HIGH_THRESHOLD) / Decimal("100") * cfg.stress_sensitivity * Decimal("0.60")
    else:
        stress_penalty = Decimal("0.00")

    # Health penalty
    h = Decimal(str(health))
    if h < HEALTH_LOW_THRESHOLD:
        health_penalty = (HEALTH_LOW_THRESHOLD - h) / Decimal("100") * Decimal("0.40")
    else:
        health_penalty = Decimal("0.00")

    raw = worked_component + training_component - stress_penalty - health_penalty
    return _q4(_clamp(raw, SKILL_DELTA_FLOOR, SKILL_DELTA_CEILING))


def compute_daily_performance_score(
    *,
    worked_today: bool,
    productivity_modifier: Decimal,
    employment_state: PlayerEmploymentState | None,
    daily_state: PlayerDailyState | None,
) -> Decimal:
    """Return the daily performance score in [0.00, 1.00].

    Formula:
      score = attendance_factor * productivity_factor * consistency_factor * job_condition_factor

    Factors:
      attendance_factor: 0.60 if skipped, 1.00 if worked
      productivity_factor: clamp(productivity_modifier, 0.60, 1.10) normalized to [0.60, 1.00]
      consistency_factor: light penalty for overtime / high burnout
      job_condition_factor: layoff_risk drag from employment state
    """
    # Attendance
    attendance_factor = Decimal("1.00") if worked_today else Decimal("0.60")

    # Productivity factor — normalize modifier range to [0, 1]
    prod = _clamp(_d(productivity_modifier), Decimal("0.60"), Decimal("1.10"))
    # normalize [0.60 → 1.10] to [0.60 → 1.00]
    prod_normalized = Decimal("0.60") + (prod - Decimal("0.60")) / Decimal("0.50") * Decimal("0.40")
    productivity_factor = _clamp(prod_normalized, Decimal("0.60"), Decimal("1.00"))

    # Consistency factor — penalize for overtime or burnout
    consistency_factor = Decimal("1.00")
    if daily_state is not None:
        overtime = _d(getattr(daily_state, "overtime_hours", 0))
        burnout = _d(getattr(daily_state, "burnout_risk", 0))
        if overtime > Decimal("2.0"):
            consistency_factor -= Decimal("0.06")
        if burnout > Decimal("0.20"):
            consistency_factor -= Decimal("0.06")
    consistency_factor = _clamp(consistency_factor, Decimal("0.80"), Decimal("1.00"))

    # Job condition — drag from layoff risk environment
    job_condition_factor = Decimal("1.00")
    if employment_state is not None:
        layoff_risk = _clamp(_d(employment_state.layoff_risk_pct) / Decimal("100"), Decimal("0"), Decimal("0.35"))
        job_condition_factor = Decimal("1.00") - layoff_risk * Decimal("0.20")

    raw = attendance_factor * productivity_factor * consistency_factor * job_condition_factor
    return _q4(_clamp(raw, PERF_MIN, PERF_MAX))


def _update_trailing_performance(old_trailing: Decimal, daily_score: Decimal) -> Decimal:
    """Exponential moving average with PERF_EMA_ALPHA weight on new data."""
    new = PERF_EMA_ALPHA * daily_score + (Decimal("1") - PERF_EMA_ALPHA) * old_trailing
    return _q4(_clamp(new, PERF_MIN, PERF_MAX))


def compute_promotion_progress(
    *,
    job_key: str,
    current_rank: str,
    days_worked: int,
    skill: Decimal,
    trailing_performance: Decimal,
) -> Decimal:
    """Return a [0.00, 1.00] score representing how close the player is to promotion.

    Each threshold criterion contributes a weight:
      - days_worked:  40%
      - skill:        35%
      - performance:  25%

    Returns 1.00 if ALL thresholds are met (promotion is eligible),
    or a fractional progress score otherwise.  Returns 0 if already at max rank.
    """
    threshold = get_promotion_threshold(job_key, current_rank)
    if threshold is None:
        return Decimal("0.00")  # already at advanced (or no threshold defined)

    days_pct = min(Decimal(str(days_worked)) / Decimal(str(threshold.min_days_worked)), Decimal("1.00"))
    skill_pct = _clamp(skill / threshold.min_skill, Decimal("0.00"), Decimal("1.00"))
    perf_pct = _clamp(trailing_performance / threshold.min_trailing_performance, Decimal("0.00"), Decimal("1.00"))

    raw = days_pct * Decimal("0.40") + skill_pct * Decimal("0.35") + perf_pct * Decimal("0.25")
    return _q4(_clamp(raw, Decimal("0.00"), Decimal("1.00")))


def attempt_promotion(db: Session, career: PlayerCareer, day: int) -> bool:
    """Try to promote the career one rank.

    Returns True if promoted, False if not eligible.
    At most one rank per day. Aircraft mechanic requires certification completed.
    """
    if career.current_job_key is None:
        return False

    cfg = get_job_config(career.current_job_key)
    current_rank = career.current_job_rank or RANK_ENTRY
    threshold = get_promotion_threshold(career.current_job_key, current_rank)

    if threshold is None:
        return False  # already at max rank

    # Guard: aircraft_mechanic requires certification
    if cfg.certification_required and not career.certification_completed:
        return False

    skill = _d(career.current_job_skill)
    trailing = _d(career.trailing_performance_score)
    days_worked = int(career.total_days_worked_in_job or 0)

    if days_worked < threshold.min_days_worked:
        return False
    if skill < threshold.min_skill:
        return False
    if trailing < threshold.min_trailing_performance:
        return False

    new_rank = next_rank(current_rank)
    if new_rank is None:
        return False

    career.current_job_rank = new_rank
    career.promotion_eligible = False
    career.last_promotion_day = day

    return True


def start_certification_track(db: Session, player_id: str | UUID, track_key: str) -> dict:
    """Enrol a player in a certification track.

    Rules:
    - track_key must exist in CERTIFICATION_CATALOG
    - player must not already be enrolled in the same track
    - player must not already have the certification completed
    """
    if track_key not in CERTIFICATION_CATALOG:
        raise CareerValidationError(
            f"Unknown certification track: {track_key!r}. "
            f"Valid: {sorted(CERTIFICATION_CATALOG.keys())}"
        )

    career = get_or_create_player_career(db, player_id)
    cat = CERTIFICATION_CATALOG[track_key]

    if career.certification_completed and career.certification_track_key == track_key:
        raise CareerValidationError(
            f"Certification {track_key!r} is already completed for this player."
        )
    if career.certification_track_key == track_key and not career.certification_completed:
        # Already enrolled — return current state
        return {
            "enrolled": False,
            "message": "Already enrolled in this certification track.",
            "certification_track_key": track_key,
            "certification_progress_days": int(career.certification_progress_days or 0),
            "certification_required_days": int(career.certification_required_days or cat["required_days"]),
            "certification_completed": False,
        }

    career.certification_track_key = track_key
    career.certification_progress_days = 0
    career.certification_required_days = cat["required_days"]
    career.certification_completed = False

    db.flush()

    return {
        "enrolled": True,
        "message": f"Enrolled in {cat['display_name']}.",
        "certification_track_key": track_key,
        "certification_progress_days": 0,
        "certification_required_days": cat["required_days"],
        "certification_completed": False,
    }


def update_certification_progress(
    career: PlayerCareer,
    training_hours_today: Decimal,
) -> tuple[int, bool]:
    """Advance certification progress for one day.

    Returns (new_progress_days, completed_flag).

    Certification advances only if:
    - player has an active track
    - training_hours_today >= CERT_MIN_DAILY_TRAINING_HOURS
    - not already completed

    A small consistency bonus applies when training_hours > 1.5h (up to +0.2 extra day).
    """
    if not career.certification_track_key:
        return int(career.certification_progress_days or 0), False

    if career.certification_completed:
        return int(career.certification_progress_days or 0), True

    t = _clamp(_d(training_hours_today), TRAINING_HOURS_MIN, TRAINING_HOURS_MAX)

    if t < CERT_MIN_DAILY_TRAINING_HOURS:
        # Insufficient training today — no progress
        return int(career.certification_progress_days or 0), False

    # Base: 1 day of progress per qualifying day
    # Consistency bonus: extra 0.20 days if > 1.5h invested
    advance = Decimal("1.00")
    if t > Decimal("1.50"):
        advance += Decimal("0.20")

    new_progress = _d(career.certification_progress_days or 0) + advance
    required = _d(career.certification_required_days or 1)

    completed = new_progress >= required
    final_progress = min(new_progress, required)
    # Store as integer (full days completed)
    career.certification_progress_days = int(final_progress.to_integral_value(rounding=ROUND_HALF_UP))

    return career.certification_progress_days, completed


def complete_certification_if_eligible(db: Session, career: PlayerCareer) -> bool:
    """Mark certification as completed if progress meets required days.

    Returns True if just completed, False if already done or not yet eligible.
    """
    if career.certification_completed:
        return False
    if not career.certification_track_key:
        return False

    progress = int(career.certification_progress_days or 0)
    required = int(career.certification_required_days or 1)

    if progress >= required:
        career.certification_completed = True
        db.flush()
        return True
    return False


def switch_player_job(
    db: Session,
    player_id: str | UUID,
    new_job_key: str,
    as_of_date: date | None = None,
) -> dict:
    """Switch the player to a new job, applying validation rules.

    Rules:
    - new_job_key must be a valid job key
    - aircraft_mechanic requires certification_completed == True
    - switching resets days_worked and rank to entry for the new job
    - a modest cross-job skill transfer may apply for related transitions
    - preserves global career history
    """
    raw_new_job_key = str(new_job_key or "").strip()
    logger.info(
        "career.switch_player_job request received.",
        extra={
            "player_id": str(player_id),
            "incoming_new_job_key": raw_new_job_key,
        },
    )

    try:
        canonical_new_job_key = require_canonical_main_job_key(raw_new_job_key)
    except ValueError as exc:
        raise CareerValidationError(
            str(exc)
        )

    player = _resolve_player(db, player_id)
    career = get_or_create_player_career(db, player.id)
    cfg = get_job_config(canonical_new_job_key)

    # Gate check for aircraft mechanic
    if cfg.certification_required and not career.certification_completed:
        raise CareerValidationError(
            f"Cannot switch to {canonical_new_job_key!r}: certification "
            f"{cfg.certification_track_key!r} must be completed first."
        )

    old_job = normalize_main_job_key(career.current_job_key, allow_aliases=True)
    previous_main_job = normalize_main_job_key(player.main_job, allow_aliases=True)
    old_skill = _d(career.current_job_skill)

    # Compute transfer skill bonus for related job transitions
    transfer_bonus = RELATED_JOB_SKILL_TRANSFER.get((old_job, canonical_new_job_key), Decimal("0.00"))
    transferred_skill = _q4(old_skill * transfer_bonus)

    # Starting skill in new job
    # For aircraft_mechanic after auto_mechanic cert: modest boost, never inflated
    new_skill = _clamp(transferred_skill, SKILL_MIN, Decimal("25.0"))

    career.current_job_key = canonical_new_job_key
    career.current_job_rank = RANK_ENTRY
    career.current_job_skill = new_skill
    career.total_days_worked_in_job = 0
    career.trailing_performance_score = Decimal("0.0")
    career.promotion_eligible = False

    # Update player.main_job to match
    player.main_job = canonical_new_job_key

    db.flush()
    logger.info(
        "career.switch_player_job persisted canonical main job.",
        extra={
            "player_id": str(player.id),
            "incoming_new_job_key": raw_new_job_key,
            "resolved_new_job_key": canonical_new_job_key,
            "previous_main_job": previous_main_job,
            "previous_career_job": old_job,
            "updated_main_job": player.main_job,
            "updated_career_job": career.current_job_key,
            "persistence_success": True,
        },
    )

    return {
        "success": True,
        "new_job_key": canonical_new_job_key,
        "previous_job_key": old_job,
        "new_rank": RANK_ENTRY,
        "transferred_skill": float(_q4(transferred_skill)),
        "starting_skill": float(new_skill),
        "message": (
            f"Switched from {old_job!r} to {canonical_new_job_key!r}. "
            f"Starting at entry rank with skill {float(new_skill):.2f}."
        ),
    }


def get_player_career_snapshot(db: Session, player_id: str | UUID) -> dict:
    """Return a complete career state snapshot for the player."""
    player = _resolve_player(db, player_id)
    career = get_or_create_player_career(db, player.id)
    cfg = CAREER_CONFIG.get(career.current_job_key or "")

    rank = career.current_job_rank or RANK_ENTRY
    skill = _d(career.current_job_skill)
    trailing = _d(career.trailing_performance_score)
    days_worked = int(career.total_days_worked_in_job or 0)
    cert_track = career.certification_track_key
    cert_progress = int(career.certification_progress_days or 0)
    cert_required = int(career.certification_required_days or 0)
    cert_completed = bool(career.certification_completed)

    # promotion progress
    promo_progress = Decimal("0.00")
    promo_eligible = False
    if career.current_job_key:
        promo_progress = compute_promotion_progress(
            job_key=career.current_job_key,
            current_rank=rank,
            days_worked=days_worked,
            skill=skill,
            trailing_performance=trailing,
        )
        threshold = get_promotion_threshold(career.current_job_key, rank)
        if threshold is not None:
            promo_eligible = (
                days_worked >= threshold.min_days_worked
                and skill >= threshold.min_skill
                and trailing >= threshold.min_trailing_performance
            )

    # effective pay
    eff_pay = None
    if career.current_job_key:
        try:
            eff_pay = float(effective_monthly_pay(career.current_job_key, rank, skill))
        except Exception:
            eff_pay = None

    # promotion blockers for debug
    blockers: list[str] = []
    if career.current_job_key and cfg:
        threshold = get_promotion_threshold(career.current_job_key, rank)
        if threshold is None:
            blockers.append("Already at maximum rank.")
        else:
            if days_worked < threshold.min_days_worked:
                blockers.append(
                    f"Need {threshold.min_days_worked - days_worked} more days in this job."
                )
            if skill < threshold.min_skill:
                blockers.append(
                    f"Need {float(threshold.min_skill - skill):.1f} more skill points."
                )
            if trailing < threshold.min_trailing_performance:
                blockers.append(
                    f"Need trailing performance >= {float(threshold.min_trailing_performance):.2f} "
                    f"(current: {float(trailing):.2f})."
                )
            if cfg.certification_required and not cert_completed:
                blockers.append("Certification required before promotion is available.")

    return {
        "player_id": str(player.id),
        "current_job_key": career.current_job_key,
        "current_job_rank": rank,
        "current_job_skill": float(_q4(skill)),
        "total_days_worked_in_job": days_worked,
        "trailing_performance_score": float(_q4(trailing)),
        "promotion_eligible": promo_eligible,
        "promotion_progress": float(_q4(promo_progress)),
        "certification_track_key": cert_track,
        "certification_progress_days": cert_progress,
        "certification_required_days": cert_required,
        "certification_completed": cert_completed,
        "effective_monthly_pay_xgp": eff_pay,
        "last_promotion_day": career.last_promotion_day,
        "debug_meta": {
            "promotion_blockers": blockers,
            "rank_wage_multiplier": float(
                (cfg.rank_wage_multipliers.get(rank, Decimal("1.00"))) if cfg else 1.00
            ),
            "career_debug": _parse_json(career.career_debug_json),
        },
    }


def get_player_career_history(
    db: Session,
    player_id: str | UUID,
    limit: int = 30,
) -> dict:
    """Return the last *limit* career progress log entries and summary statistics."""
    player = _resolve_player(db, player_id)

    logs = (
        db.query(CareerProgressLog)
        .filter(CareerProgressLog.player_id == player.id)
        .order_by(CareerProgressLog.day_number.desc())
        .limit(limit)
        .all()
    )

    entries = []
    for row in reversed(logs):
        entries.append({
            "day_number": int(row.day_number),
            "job_key": row.job_key,
            "job_rank": row.job_rank,
            "skill_before": float(_q4(_d(row.skill_before))),
            "skill_after": float(_q4(_d(row.skill_after))),
            "skill_delta": float(_q4(_d(row.skill_delta))),
            "performance_score": float(_q4(_d(row.performance_score))),
            "trailing_performance_score": float(_q4(_d(row.trailing_performance_score))),
            "promotion_progress": float(_q4(_d(row.promotion_progress))),
            "promotion_unlocked": bool(row.promotion_unlocked),
            "certification_progress_days": int(row.certification_progress_days or 0),
            "certification_completed": bool(row.certification_completed),
            "training_hours": float(_d(row.training_hours)),
        })

    # 7-day summary stats
    recent_7 = entries[-7:] if len(entries) >= 7 else entries
    avg_skill_7d = (
        sum(e["skill_delta"] for e in recent_7) / len(recent_7) if recent_7 else 0.0
    )
    avg_perf_7d = (
        sum(e["performance_score"] for e in recent_7) / len(recent_7) if recent_7 else 0.0
    )

    promotions = sum(1 for e in entries if e["promotion_unlocked"])
    certs_completed = sum(1 for e in entries if e["certification_completed"])

    return {
        "player_id": str(player.id),
        "entries": entries,
        "trailing_7d_avg_skill_gain": round(avg_skill_7d, 4),
        "trailing_7d_avg_performance": round(avg_perf_7d, 4),
        "promotions_count": promotions,
        "certifications_completed_count": certs_completed,
    }


def apply_daily_career_progression(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    training_hours: Decimal | None = None,
    commit: bool = False,
) -> dict:
    """Main daily orchestrator — run after work/life consequences are known.

    Steps:
    1. Load player, career state, employment + daily life state
    2. Determine if player worked today
    3. Compute performance score
    4. Compute skill growth
    5. Advance certification if training hours provided
    6. Update trailing performance EMA
    7. Evaluate promotion eligibility
    8. Attempt promotion if thresholds are met
    9. Persist career state + log row (upsert on player_id/day)
    10. Return structured PlayerCareerDailyResponse dict

    training_hours: hours the player spent on deliberate training/studying today.
    TRAINING_HOURS_MAX is enforced internally.
    """
    player = _resolve_player(db, player_id)

    # Determine game day
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        settled_date = as_of_date
    else:
        from app.services.daily_settlement_service import get_next_player_day
        day = int(get_next_player_day(db, player.id))
        # get_next_player_day returns the *next* unsettled day, so we use day - 1
        day = max(1, day - 1)
        settled_date = _day_to_date(day)

    career = get_or_create_player_career(db, player.id)

    # Gather context from settled employment + life state
    emp_state = _latest_employment_state(db, player.id)
    daily_state = _latest_daily_state(db, player.id, day)

    # Resolve training hours (clamped)
    t_hours = _clamp(
        _d(training_hours) if training_hours is not None else Decimal("0.00"),
        TRAINING_HOURS_MIN,
        TRAINING_HOURS_MAX,
    )

    # Check if player worked today (they have a job and worked in the job)
    worked_today = False
    if emp_state is not None and emp_state.employed_flag:
        worked_today = True

    # If career has no job set, seed from employment or player.main_job
    job_key = career.current_job_key
    if not job_key or job_key not in VALID_JOB_KEYS:
        employment_job_key = normalize_main_job_key(
            getattr(emp_state, "current_job_code", None) if emp_state is not None else None,
            allow_aliases=True,
        )
        player_job_key = normalize_main_job_key(player.main_job, allow_aliases=True)
        if employment_job_key in VALID_JOB_KEYS:
            job_key = employment_job_key
            career.current_job_key = job_key
        elif player_job_key in VALID_JOB_KEYS:
            job_key = player_job_key
            career.current_job_key = job_key

    # Vitals
    stress = int(
        daily_state.stress_end if daily_state and daily_state.stress_end is not None
        else player.stress or 0
    )
    health = int(
        daily_state.health_end if daily_state and daily_state.health_end is not None
        else player.health or 100
    )
    productivity = _d(
        daily_state.productivity_modifier if daily_state and daily_state.productivity_modifier is not None
        else player.productivity_modifier or 1.0
    )

    skill_before = _q4(_d(career.current_job_skill))
    skill_delta = Decimal("0.00")
    performance_score = Decimal("0.00")

    if job_key and job_key in VALID_JOB_KEYS:
        # Skill growth
        skill_delta = compute_daily_skill_growth(
            job_key=job_key,
            worked_today=worked_today,
            productivity_modifier=productivity,
            stress=stress,
            health=health,
            training_hours=t_hours,
        )

        # Performance score
        performance_score = compute_daily_performance_score(
            worked_today=worked_today,
            productivity_modifier=productivity,
            employment_state=emp_state,
            daily_state=daily_state,
        )

    # Update skill (bounded)
    new_skill = _clamp(skill_before + skill_delta, SKILL_MIN, SKILL_MAX)
    career.current_job_skill = new_skill

    # Increment days worked counter
    if worked_today:
        career.total_days_worked_in_job = int(career.total_days_worked_in_job or 0) + 1

    # Update trailing performance EMA
    old_trailing = _q4(_d(career.trailing_performance_score))
    new_trailing = _update_trailing_performance(old_trailing, performance_score)
    career.trailing_performance_score = new_trailing

    # Certification progress
    cert_progress_before = int(career.certification_progress_days or 0)
    cert_completed_today = False
    missed_training = Decimal("0.00")

    if career.certification_track_key and not career.certification_completed:
        _new_progress, advanced = update_certification_progress(career, t_hours)
        if advanced:
            just_completed = complete_certification_if_eligible(db, career)
            cert_completed_today = just_completed or career.certification_completed

        # Track missed training hours (if cert active but no training today)
        if t_hours < CERT_MIN_DAILY_TRAINING_HOURS:
            missed_training = CERT_MIN_DAILY_TRAINING_HOURS - t_hours

    # Evaluate promotion eligibility
    rank = career.current_job_rank or RANK_ENTRY
    days_worked = int(career.total_days_worked_in_job or 0)
    promo_eligible = False
    promo_progress = Decimal("0.00")

    if job_key and job_key in VALID_JOB_KEYS:
        promo_progress = compute_promotion_progress(
            job_key=job_key,
            current_rank=rank,
            days_worked=days_worked,
            skill=new_skill,
            trailing_performance=new_trailing,
        )
        threshold = get_promotion_threshold(job_key, rank)
        if threshold is not None:
            promo_eligible = (
                days_worked >= threshold.min_days_worked
                and new_skill >= threshold.min_skill
                and new_trailing >= threshold.min_trailing_performance
            )
    career.promotion_eligible = promo_eligible

    # Attempt promotion
    promotion_unlocked_today = False
    if promo_eligible:
        promotion_unlocked_today = attempt_promotion(db, career, day)
        if promotion_unlocked_today:
            rank = career.current_job_rank  # updated by attempt_promotion

    # Build debug metadata
    debug = {
        "day": day,
        "worked_today": worked_today,
        "stress": stress,
        "health": health,
        "productivity_modifier": float(_q4(productivity)),
        "skill_delta_components": {
            "skill_delta": float(_q4(skill_delta)),
            "training_hours": float(_q4(t_hours)),
        },
        "perf_components": {
            "daily_score": float(_q4(performance_score)),
            "trailing_update": float(_q4(new_trailing)),
        },
        "cert_progress_before": cert_progress_before,
        "cert_progress_after": int(career.certification_progress_days or 0),
        "missed_training_hours": float(_q4(missed_training)),
    }

    career.career_debug_json = json.dumps(debug)

    # Upsert daily progress log
    existing_log = (
        db.query(CareerProgressLog)
        .filter(
            CareerProgressLog.player_id == player.id,
            CareerProgressLog.day_number == day,
        )
        .first()
    )
    if existing_log is None:
        log_row = CareerProgressLog(
            player_id=player.id,
            day_number=day,
            job_key=job_key,
            job_rank=rank,
            skill_before=skill_before,
            skill_after=_q4(new_skill),
            skill_delta=_q4(skill_delta),
            performance_score=_q4(performance_score),
            trailing_performance_score=_q4(new_trailing),
            promotion_progress=_q4(promo_progress),
            promotion_unlocked=promotion_unlocked_today,
            certification_progress_days=int(career.certification_progress_days or 0),
            certification_completed=bool(career.certification_completed),
            training_hours=_q4(t_hours),
            missed_training_hours=_q4(missed_training),
            debug_json=json.dumps(debug),
        )
        db.add(log_row)
    else:
        # Update existing (idempotent re-run)
        existing_log.job_key = job_key
        existing_log.job_rank = rank
        existing_log.skill_before = skill_before
        existing_log.skill_after = _q4(new_skill)
        existing_log.skill_delta = _q4(skill_delta)
        existing_log.performance_score = _q4(performance_score)
        existing_log.trailing_performance_score = _q4(new_trailing)
        existing_log.promotion_progress = _q4(promo_progress)
        existing_log.promotion_unlocked = promotion_unlocked_today
        existing_log.certification_progress_days = int(career.certification_progress_days or 0)
        existing_log.certification_completed = bool(career.certification_completed)
        existing_log.training_hours = _q4(t_hours)
        existing_log.missed_training_hours = _q4(missed_training)
        existing_log.debug_json = json.dumps(debug)

    db.flush()

    if commit:
        db.commit()

    # Compute cert days remaining
    cert_required = int(career.certification_required_days or 0)
    cert_progress_final = int(career.certification_progress_days or 0)
    cert_remaining = max(0, cert_required - cert_progress_final)

    return {
        "player_id": str(player.id),
        "as_of_date": settled_date.isoformat(),
        "current_job_key": job_key,
        "current_job_rank": rank,
        "skill_before": float(_q4(skill_before)),
        "skill_after": float(_q4(new_skill)),
        "skill_delta": float(_q4(skill_delta)),
        "performance_score": float(_q4(performance_score)),
        "trailing_performance_score": float(_q4(new_trailing)),
        "promotion_progress": float(_q4(promo_progress)),
        "promotion_eligible": promo_eligible,
        "promotion_unlocked_today": promotion_unlocked_today,
        "certification_track_key": career.certification_track_key,
        "certification_progress_days": cert_progress_final,
        "certification_required_days": cert_required,
        "certification_estimated_days_remaining": cert_remaining,
        "certification_completed": bool(career.certification_completed),
        "training_hours": float(_q4(t_hours)),
        "missed_training_hours": float(_q4(missed_training)),
        "debug_meta": debug,
    }
