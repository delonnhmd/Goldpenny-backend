"""Step 40: Reputation, Trust, and Opportunity Access Layer.

This service synthesises a player's reputation profile from:
  - delinquency state     (Steps 36)
  - borrowing state       (Step 37)
  - debt behaviour state  (Step 38)
  - wealth state          (Step 39)
  - shock / fragility     (Step 35)
  - recovery state        (Step 35)
  - commitment state      (Step 34)
  - business performance  (Steps 10/15)

Reputation represents a SECOND progression path alongside money:
  - Reliability matters independently of raw cash balance
  - Discipline and consistency improve future opportunity quality
  - False growth does NOT produce strong trust
  - Bad reputation is NOT instantly fatal — recovery is always possible
  - All effects are bounded, explainable, and testable

Write tables:
  - player_reputation_states       (rolling per-player snapshot, upsert)
  - player_reputation_history      (append-only daily rows, upsert by player+day)
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.database import Base  # noqa: F401 – ensure mapper is ready
from app.models.business_daily_log import BusinessDailyLog
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_reputation_history import PlayerReputationHistory
from app.models.player_reputation_state import PlayerReputationState
from app.models.player_shock_state import PlayerShockState
from app.models.player_wealth_state import PlayerWealthState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")

# Score bounds
SCORE_MIN = Decimal("0")
SCORE_MAX = Decimal("100")

# Delinquency stage → index (higher = worse)
DELINQUENCY_STAGE_INDEX: dict[str, int] = {
    "current": 0,
    "stretched": 1,
    "late": 2,
    "delinquent": 3,
    "critical": 4,
}

# Trust label thresholds (score → label)
# score ≥ 80 → highly_trusted
# score ≥ 65 → trusted
# score ≥ 45 → solid
# score ≥ 30 → mixed
# score <  30 → weak
TRUST_THRESHOLDS = (
    (Decimal("80"), "highly_trusted"),
    (Decimal("65"), "trusted"),
    (Decimal("45"), "solid"),
    (Decimal("30"), "mixed"),
)

# Opportunity access label thresholds (opportunity_readiness_score → label)
OPPORTUNITY_THRESHOLDS = (
    (Decimal("80"), "preferred"),
    (Decimal("65"), "elevated"),
    (Decimal("45"), "standard"),
    (Decimal("30"), "limited"),
)

# Recovery stage weight (recovery boosts trust rebuild)
RECOVERY_STAGE_BOOST: dict[str, Decimal] = {
    "strong": Decimal("8"),
    "rebuilding": Decimal("5"),
    "early": Decimal("2"),
    "none": Decimal("0"),
    "stable": Decimal("1"),
}

# debt_state_label modifiers
DEBT_STATE_MODIFIER: dict[str, Decimal] = {
    "stable_surplus": Decimal("8"),
    "stable": Decimal("4"),
    "stretched": Decimal("-5"),
    "distressed": Decimal("-10"),
    "critical": Decimal("-16"),
    "default": Decimal("0"),
}

# Spiral risk modifier
SPIRAL_MODIFIER: dict[str, Decimal] = {
    "low": Decimal("0"),
    "rising": Decimal("-6"),
    "high": Decimal("-12"),
    "critical": Decimal("-20"),
}

# Maximum opportunity modifier bounds
MAX_OPPORTUNITY_BONUS = Decimal("20")   # +20 points max for high trust
MAX_OPPORTUNITY_PENALTY = Decimal("30")  # -30 points max for low trust

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReputationTrustError(Exception):
    """Base Step 40 error."""


class ReputationTrustNotFoundError(ReputationTrustError):
    """Raised when player or required state rows are missing."""


class ReputationTrustValidationError(ReputationTrustError):
    """Raised for invalid inputs."""


# ---------------------------------------------------------------------------
# Precision helpers
# ---------------------------------------------------------------------------


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal = SCORE_MIN, hi: Decimal = SCORE_MAX) -> Decimal:
    return max(lo, min(hi, value))


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


# ---------------------------------------------------------------------------
# Day / date helpers
# ---------------------------------------------------------------------------


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise ReputationTrustValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise ReputationTrustValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_day(
    db: Session,
    player: Player,
    as_of_date: date | None,
    day_number: int | None,
) -> tuple[int, date]:
    if day_number is not None:
        return int(day_number), _day_to_date(int(day_number))
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date
    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


# ---------------------------------------------------------------------------
# DB fetch helpers
# ---------------------------------------------------------------------------


def _get_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ReputationTrustNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise ReputationTrustNotFoundError("Player not found.")
    return row


def _get_delinquency(db: Session, player_id: UUID) -> PlayerDelinquencyState | None:
    return db.query(PlayerDelinquencyState).filter(PlayerDelinquencyState.player_id == player_id).first()


def _get_borrowing(db: Session, player_id: UUID) -> PlayerBorrowingState | None:
    return db.query(PlayerBorrowingState).filter(PlayerBorrowingState.player_id == player_id).first()


def _get_debt_behavior(db: Session, player_id: UUID) -> PlayerDebtBehaviorState | None:
    return db.query(PlayerDebtBehaviorState).filter(PlayerDebtBehaviorState.player_id == player_id).first()


def _get_wealth_state(db: Session, player_id: UUID) -> PlayerWealthState | None:
    return db.query(PlayerWealthState).filter(PlayerWealthState.player_id == player_id).first()


def _get_shock_state(db: Session, player_id: UUID) -> PlayerShockState | None:
    return db.query(PlayerShockState).filter(PlayerShockState.player_id == player_id).first()


def _get_recovery_state(db: Session, player_id: UUID) -> PlayerRecoveryState | None:
    return db.query(PlayerRecoveryState).filter(PlayerRecoveryState.player_id == player_id).first()


def _get_commitment_state(db: Session, player_id: UUID) -> list[PlayerCommitmentState]:
    try:
        return db.query(PlayerCommitmentState).filter(PlayerCommitmentState.player_id == player_id).all()
    except Exception:
        return []


def _get_businesses(db: Session, player_id: UUID) -> list[PlayerBusiness]:
    try:
        return db.query(PlayerBusiness).filter(PlayerBusiness.player_id == player_id).all()
    except Exception:
        return []


def _recent_biz_logs(db: Session, player_id: UUID, day: int, window: int = 30) -> list[BusinessDailyLog]:
    start = max(1, int(day) - window + 1)
    try:
        return (
            db.query(BusinessDailyLog)
            .filter(
                BusinessDailyLog.player_id == player_id,
                BusinessDailyLog.day >= start,
                BusinessDailyLog.day <= int(day),
            )
            .order_by(BusinessDailyLog.day.desc())
            .all()
        )
    except Exception:
        return []


def _recent_reputation_history(
    db: Session, player_id: UUID, day: int, n: int = 14,
) -> list[PlayerReputationHistory]:
    try:
        return (
            db.query(PlayerReputationHistory)
            .filter(
                PlayerReputationHistory.player_id == player_id,
                PlayerReputationHistory.day < int(day),
            )
            .order_by(PlayerReputationHistory.day.desc())
            .limit(n)
            .all()
        )
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Label resolvers
# ---------------------------------------------------------------------------


def _resolve_trust_label(score: Decimal) -> str:
    for threshold, label in TRUST_THRESHOLDS:
        if score >= threshold:
            return label
    return "weak"


def _resolve_opportunity_label(score: Decimal) -> str:
    for threshold, label in OPPORTUNITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "restricted"


def _resolve_signal_label(score: Decimal) -> str:
    """Map a 0–100 score to weak/mixed/solid/trusted/highly_trusted."""
    return _resolve_trust_label(score)


def _resolve_reputation_direction(
    current_score: Decimal,
    history: list[PlayerReputationHistory],
    recovery_stage: str,
) -> str:
    if recovery_stage in ("rebuilding", "early"):
        if current_score >= Decimal("40"):
            return "recovering"
    if len(history) < 3:
        return "stable"
    recent_avg = sum(_d(h.reputation_score) for h in history[:3]) / 3
    delta = current_score - recent_avg
    if delta >= Decimal("3"):
        return "improving"
    if delta <= Decimal("-3"):
        return "weakening"
    return "stable"


# ---------------------------------------------------------------------------
# Score computers
# ---------------------------------------------------------------------------


def _compute_financial_reliability_score(
    player: Player,
    delinq: PlayerDelinquencyState | None,
    borrowing: PlayerBorrowingState | None,
    debt_behavior: PlayerDebtBehaviorState | None,
    wealth: PlayerWealthState | None,
) -> tuple[Decimal, str, str]:
    """Return (score, signal_label, main_drag)."""
    score = Decimal("50")
    drag = ""

    # --- delinquency penalty ---
    if delinq is not None:
        stage = getattr(delinq, "current_delinquency_stage", "current") or "current"
        stage_idx = DELINQUENCY_STAGE_INDEX.get(stage, 0)
        delinq_pen = Decimal(str(stage_idx * 10))
        score -= delinq_pen

        missed_30d = _d(getattr(delinq, "missed_payment_count_30d", 0))
        late_30d = _d(getattr(delinq, "late_payment_count_30d", 0))
        score -= missed_30d * Decimal("3")
        score -= late_30d * Decimal("1.5")

        credit_pressure = _d(getattr(delinq, "credit_pressure_score", 0))
        score -= credit_pressure * Decimal("0.1")

        if stage_idx >= 3:
            drag = "delinquent payment history"
        elif missed_30d >= 3:
            drag = "repeated missed payments"
        elif late_30d >= 5:
            drag = "frequent late payments"

    # --- borrowing penalty ---
    if borrowing is not None:
        repeat_borr = _d(getattr(borrowing, "repeat_borrowing_count_30d", 0))
        depend_risk = _d(getattr(borrowing, "dependence_risk_score", 0))
        score -= repeat_borr * Decimal("2")
        score -= depend_risk * Decimal("0.15")
        active_loans = int(getattr(borrowing, "active_loan_count", 0) or 0)
        if active_loans >= 3:
            score -= Decimal("8")
            if not drag:
                drag = "high active loan count"

    # --- debt behaviour modifier ---
    if debt_behavior is not None:
        debt_label = getattr(debt_behavior, "debt_state_label", None) or "default"
        score += DEBT_STATE_MODIFIER.get(debt_label, Decimal("0"))

        spiral = getattr(debt_behavior, "spiral_risk_label", None) or "low"
        score += SPIRAL_MODIFIER.get(spiral, Decimal("0"))

        fin_stab = _d(getattr(debt_behavior, "financial_stability_score", 50))
        score += (fin_stab - Decimal("50")) * Decimal("0.2")

    # --- missed payment streak on player ---
    streak = int(getattr(player, "missed_payment_streak", 0) or 0)
    if streak >= 5:
        score -= Decimal("15")
        if not drag:
            drag = "prolonged payment streak"
    elif streak >= 2:
        score -= Decimal("8")

    # --- false growth suppression ---
    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False
    if false_growth:
        # Positive wealth does not yield positive financial reliability if growth is fake
        score = _clamp(score, SCORE_MIN, Decimal("55"))
        if not drag:
            drag = "false growth pattern suppressing trust"

    # Bonus for credit score on player
    cs = int(getattr(player, "credit_score", 650) or 650)
    if cs >= 750:
        score += Decimal("8")
    elif cs >= 700:
        score += Decimal("4")
    elif cs <= 550:
        score -= Decimal("8")
    elif cs <= 600:
        score -= Decimal("4")

    score = _clamp(_q4(score), SCORE_MIN, SCORE_MAX)
    label = _resolve_signal_label(score)
    return score, label, drag or "none"


def _compute_work_reliability_score(
    player: Player,
    shock: PlayerShockState | None,
    recovery: PlayerRecoveryState | None,
    debt_behavior: PlayerDebtBehaviorState | None,
) -> tuple[Decimal, str, str]:
    """Return (score, signal_label, main_drag)."""
    score = Decimal("50")
    drag = ""

    # --- skill level bonus ---
    skill = int(getattr(player, "skill_level", 1) or 1)
    if skill >= 5:
        score += Decimal("12")
    elif skill >= 4:
        score += Decimal("8")
    elif skill >= 3:
        score += Decimal("4")
    elif skill <= 1:
        score -= Decimal("5")

    # --- employment stability ---
    has_job = bool(getattr(player, "main_job", None))
    if not has_job:
        score -= Decimal("10")
        drag = "no active employment"

    # --- work disruption risk from shock state ---
    if shock is not None:
        work_risk = _d(getattr(shock, "work_disruption_risk_score", 0))
        fragility = _d(getattr(shock, "financial_fragility_score", 0))
        neg_streak = int(getattr(shock, "recent_negative_streak", 0) or 0)

        score -= work_risk * Decimal("0.25")
        score -= fragility * Decimal("0.1")
        if neg_streak >= 5:
            score -= Decimal("10")
            if not drag:
                drag = "sustained negative shock streak"
        elif neg_streak >= 3:
            score -= Decimal("5")

    # --- stress penalty ---
    stress = _d(getattr(player, "stress", 0))
    if stress >= 80:
        score -= Decimal("12")
        if not drag:
            drag = "extreme stress level"
    elif stress >= 60:
        score -= Decimal("6")
    elif stress >= 40:
        score -= Decimal("2")

    # --- recovery boost ---
    if recovery is not None:
        rec_label = getattr(recovery, "recovery_status_label", None) or "none"
        score += RECOVERY_STAGE_BOOST.get(rec_label, Decimal("0"))

    # --- debt behaviour recovery stage ---
    if debt_behavior is not None:
        rec_stage = getattr(debt_behavior, "recovery_stage", None) or "none"
        score += RECOVERY_STAGE_BOOST.get(rec_stage, Decimal("0"))

    score = _clamp(_q4(score), SCORE_MIN, SCORE_MAX)
    label = _resolve_signal_label(score)
    return score, label, drag or "none"


def _compute_business_reliability_score(
    player: Player,
    businesses: list[PlayerBusiness],
    biz_logs: list[BusinessDailyLog],
    wealth: PlayerWealthState | None,
) -> tuple[Decimal, str, str]:
    """Return (score, signal_label, main_drag)."""
    if not businesses:
        # No business → neutral, not a drag (player might only have job income)
        return Decimal("50"), "mixed", "none"

    score = Decimal("50")
    drag = ""

    total_logs = len(biz_logs)
    if total_logs == 0:
        return _q4(score), "mixed", "insufficient business data"

    profitable_days = sum(1 for lg in biz_logs if _d(lg.net_profit_xgp) > 0)
    profitability_rate = Decimal(str(profitable_days)) / Decimal(str(total_logs))

    if profitability_rate >= Decimal("0.8"):
        score += Decimal("20")
    elif profitability_rate >= Decimal("0.6"):
        score += Decimal("10")
    elif profitability_rate >= Decimal("0.4"):
        score += Decimal("2")
    elif profitability_rate < Decimal("0.2"):
        score -= Decimal("15")
        drag = "chronically unprofitable business"
    else:
        score -= Decimal("6")

    # Demand score consistency
    demand_scores = [_d(getattr(lg, "demand_score", 50) or 50) for lg in biz_logs]
    if demand_scores:
        avg_demand = sum(demand_scores) / len(demand_scores)
        if avg_demand >= Decimal("65"):
            score += Decimal("8")
        elif avg_demand < Decimal("35"):
            score -= Decimal("8")
            if not drag:
                drag = "low business demand"

    # Player business reputation
    biz_reps = [_d(getattr(b, "reputation", 50) or 50) for b in businesses]
    if biz_reps:
        avg_biz_rep = sum(biz_reps) / len(biz_reps)
        score += (avg_biz_rep - Decimal("50")) * Decimal("0.3")

    # False growth cap
    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False
    if false_growth:
        score = _clamp(score, SCORE_MIN, Decimal("60"))
        if not drag:
            drag = "false growth suppressing business trust"

    score = _clamp(_q4(score), SCORE_MIN, SCORE_MAX)
    label = _resolve_signal_label(score)
    return score, label, drag or "none"


def _compute_composite_reputation_score(
    fin_reliability: Decimal,
    work_reliability: Decimal,
    biz_reliability: Decimal,
    businesses: list,
) -> Decimal:
    """Weighted composite (50/30/20 or 50/50 if no business)."""
    if not businesses:
        # Job income player — weight evenly between financial and work
        composite = (fin_reliability * Decimal("0.55")) + (work_reliability * Decimal("0.45"))
    else:
        composite = (
            fin_reliability * Decimal("0.50")
            + work_reliability * Decimal("0.30")
            + biz_reliability * Decimal("0.20")
        )
    return _clamp(_q4(composite), SCORE_MIN, SCORE_MAX)


def _compute_trust_score(
    reputation_score: Decimal,
    history: list[PlayerReputationHistory],
    false_growth: bool,
    debt_behavior: PlayerDebtBehaviorState | None,
    wealth: PlayerWealthState | None,
) -> Decimal:
    """Trust is slower-moving than reputation — blends current with recent history."""
    if not history:
        raw_trust = reputation_score
    else:
        # Blend: 60% current reputation, 40% average of last 7 days history
        recent = history[:7]
        hist_avg = sum(_d(h.reputation_score) for h in recent) / len(recent)
        raw_trust = (reputation_score * Decimal("0.60")) + (hist_avg * Decimal("0.40"))

    trust = _q4(raw_trust)

    # False growth hard cap on trust
    if false_growth:
        trust = _clamp(trust, SCORE_MIN, Decimal("60"))

    # Recovery stage can provide a modest trust rebuild boost even if current rep is low
    if debt_behavior is not None:
        rec_stage = getattr(debt_behavior, "recovery_stage", None) or "none"
        boost = RECOVERY_STAGE_BOOST.get(rec_stage, Decimal("0"))
        trust = _clamp(trust + (boost * Decimal("0.5")), SCORE_MIN, SCORE_MAX)

    return _clamp(_q4(trust), SCORE_MIN, SCORE_MAX)


def _compute_opportunity_readiness_score(
    trust_score: Decimal,
    fin_reliability: Decimal,
    work_reliability: Decimal,
    biz_reliability: Decimal,
    wealth: PlayerWealthState | None,
    shock: PlayerShockState | None,
    player: Player,
    businesses: list,
) -> Decimal:
    """Forward-looking synthesis for opportunity quality access. 0–100."""
    # Base from trust
    score = trust_score * Decimal("0.60")

    # Stability bonus from wealth
    if wealth is not None:
        stability = _d(getattr(wealth, "stability_before_growth_score", 50))
        score += stability * Decimal("0.12")
        buffer = _d(getattr(wealth, "buffer_days", 0))
        if buffer >= Decimal("14"):
            score += Decimal("6")
        elif buffer >= Decimal("7"):
            score += Decimal("3")

    # Shock fragility penalty
    if shock is not None:
        fragility = _d(getattr(shock, "financial_fragility_score", 0))
        score -= fragility * Decimal("0.08")

    # Skill level contribution
    skill = int(getattr(player, "skill_level", 1) or 1)
    score += Decimal(str(min(skill * 2, 10)))

    # Business contribution
    if businesses:
        score += biz_reliability * Decimal("0.08")

    # Apply opportunity modifier bounds to final score
    base = Decimal("50")
    delta = score - base
    if delta > MAX_OPPORTUNITY_BONUS:
        delta = MAX_OPPORTUNITY_BONUS
    elif delta < -MAX_OPPORTUNITY_PENALTY:
        delta = -MAX_OPPORTUNITY_PENALTY
    score = base + delta

    return _clamp(_q4(score), SCORE_MIN, SCORE_MAX)


def _build_practical_actions(
    opportunity_label: str,
    fin_drag: str,
    work_drag: str,
    biz_drag: str,
    player: Player,
    delinq: PlayerDelinquencyState | None,
    wealth: PlayerWealthState | None,
) -> list[str]:
    actions: list[str] = []
    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False

    if opportunity_label in ("restricted", "limited"):
        actions.append("Focus on clearing missed payments before seeking new credit or jobs.")
    if fin_drag not in ("none", ""):
        actions.append(f"Address financial drag: {fin_drag}.")
    if work_drag not in ("none", "") and work_drag != "none":
        actions.append(f"Improve work stability: {work_drag}.")
    if biz_drag not in ("none", "") and biz_drag != "none":
        actions.append(f"Business improvement needed: {biz_drag}.")
    if false_growth:
        actions.append("Build real cash reserves — wealth growth appears inflated and is suppressing trust.")
    if opportunity_label in ("elevated", "preferred"):
        actions.append("Strong reputation: use elevated access to pursue higher-tier jobs or lower-rate credit.")
    if not actions:
        actions.append("Maintain current payment consistency to hold reputation steady.")
    return actions


def _build_planning_insights(
    reputation_score: Decimal,
    trust_score: Decimal,
    opportunity_label: str,
    direction: str,
    fin_reliability: Decimal,
    wealth: PlayerWealthState | None,
) -> list[str]:
    insights: list[str] = []
    phase = getattr(wealth, "wealth_phase_label", None) if wealth else None

    if trust_score >= Decimal("70") and opportunity_label in ("elevated", "preferred"):
        insights.append("High trust is unlocking better opportunity quality — protect this by staying current on payments.")
    if direction == "improving":
        insights.append("Reputation is trending upward — consistency over the next 7 days will consolidate this gain.")
    elif direction == "weakening":
        insights.append("Reputation is declining — address payment or work disruptions before they compound.")
    elif direction == "recovering":
        insights.append("Healthy recovery trajectory — continued adherence will restore full opportunity access.")
    if fin_reliability < Decimal("40"):
        insights.append("Financial reliability is the most impactful lever for improving overall reputation.")
    if phase in ("fragile", "survival") if phase else False:
        insights.append("Surviving in fragile wealth phase — trust will improve naturally once cash buffer grows.")
    if not insights:
        insights.append("Reputation is in maintenance mode — small consistent wins build durable trust over time.")
    return insights


# ---------------------------------------------------------------------------
# Core state builders
# ---------------------------------------------------------------------------


def _load_all_signals(
    db: Session,
    player: Player,
    day: int,
) -> dict:
    """Load all signal rows in one pass."""
    pid = player.id
    return {
        "delinq": _get_delinquency(db, pid),
        "borrowing": _get_borrowing(db, pid),
        "debt_behavior": _get_debt_behavior(db, pid),
        "wealth": _get_wealth_state(db, pid),
        "shock": _get_shock_state(db, pid),
        "recovery": _get_recovery_state(db, pid),
        "commitments": _get_commitment_state(db, pid),
        "businesses": _get_businesses(db, pid),
        "biz_logs": _recent_biz_logs(db, pid, day, 30),
        "history": _recent_reputation_history(db, pid, day, 14),
    }


def _compute_all_scores(player: Player, day: int, signals: dict) -> dict:
    """Compute all scores from pre-loaded signals. Returns a dict ready for persistence."""
    delinq = signals["delinq"]
    borrowing = signals["borrowing"]
    debt_behavior = signals["debt_behavior"]
    wealth = signals["wealth"]
    shock = signals["shock"]
    recovery = signals["recovery"]
    businesses = signals["businesses"]
    biz_logs = signals["biz_logs"]
    history = signals["history"]

    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False

    fin_score, fin_signal, fin_drag = _compute_financial_reliability_score(
        player, delinq, borrowing, debt_behavior, wealth
    )
    work_score, work_signal, work_drag = _compute_work_reliability_score(
        player, shock, recovery, debt_behavior
    )
    biz_score, biz_signal, biz_drag = _compute_business_reliability_score(
        player, businesses, biz_logs, wealth
    )

    rep_score = _compute_composite_reputation_score(fin_score, work_score, biz_score, businesses)
    trust_score = _compute_trust_score(rep_score, history, false_growth, debt_behavior, wealth)
    opp_score = _compute_opportunity_readiness_score(
        trust_score, fin_score, work_score, biz_score, wealth, shock, player, businesses
    )

    overall_trust_label = _resolve_trust_label(trust_score)
    opportunity_access_label = _resolve_opportunity_label(opp_score)
    stability_signal_label = _resolve_signal_label(
        _d(getattr(wealth, "stability_before_growth_score", 50)) if wealth else Decimal("50")
    )

    # Direction
    rec_stage = getattr(debt_behavior, "recovery_stage", None) or "none"
    direction = _resolve_reputation_direction(rep_score, history, rec_stage)

    # Top driver: highest subscores to highlight
    score_map = {
        "financial reliability": fin_score,
        "work reliability": work_score,
        "business reliability": biz_score,
    }
    top_driver_key = max(score_map, key=lambda k: score_map[k])
    top_driver = f"{top_driver_key} ({_q4(score_map[top_driver_key])})"

    # Top drag: worst label contributors
    drag_candidates = [d for d in [fin_drag, work_drag, biz_drag] if d and d != "none"]
    top_drag = drag_candidates[0] if drag_candidates else "none"

    practical_actions = _build_practical_actions(
        opportunity_access_label, fin_drag, work_drag, biz_drag, player, delinq, wealth
    )
    planning_insights = _build_planning_insights(
        rep_score, trust_score, opportunity_access_label, direction, fin_score, wealth
    )

    # Flags for history row
    delinquency_drag_active = bool(delinq and DELINQUENCY_STAGE_INDEX.get(
        getattr(delinq, "current_delinquency_stage", "current") or "current", 0
    ) >= 2)
    recovery_boost_active = rec_stage in ("rebuilding", "strong", "early")

    debug = {
        "day": day,
        "false_growth": false_growth,
        "fin_score": float(_q4(fin_score)),
        "work_score": float(_q4(work_score)),
        "biz_score": float(_q4(biz_score)),
        "rep_score": float(_q4(rep_score)),
        "trust_score": float(_q4(trust_score)),
        "opp_score": float(_q4(opp_score)),
        "rec_stage": rec_stage,
        "direction": direction,
        "delinquency_drag_active": delinquency_drag_active,
        "recovery_boost_active": recovery_boost_active,
    }

    return {
        "reputation_score": rep_score,
        "trust_score": trust_score,
        "financial_reliability_score": fin_score,
        "work_reliability_score": work_score,
        "business_reliability_score": biz_score,
        "opportunity_readiness_score": opp_score,
        "overall_trust_label": overall_trust_label,
        "reputation_direction": direction,
        "payment_signal_label": fin_signal,
        "borrowing_signal_label": _resolve_signal_label(
            Decimal("50") if borrowing is None else _clamp(
                Decimal("100") - _d(getattr(borrowing, "dependence_risk_score", 0)),
                SCORE_MIN, SCORE_MAX,
            )
        ),
        "work_signal_label": work_signal,
        "business_signal_label": biz_signal,
        "stability_signal_label": stability_signal_label,
        "opportunity_access_label": opportunity_access_label,
        "top_reputation_driver": top_driver,
        "top_reputation_drag": top_drag,
        "practical_actions_json": _dump_json(practical_actions),
        "planning_insights_json": _dump_json(planning_insights),
        "debug_json": _dump_json(debug),
        # history-row-specific
        "_false_growth_suppressed": false_growth,
        "_delinquency_drag_active": delinquency_drag_active,
        "_recovery_boost_active": recovery_boost_active,
    }


def _upsert_reputation_state(
    db: Session,
    player_id: UUID,
    day: int,
    as_of_date: date,
    scores: dict,
) -> PlayerReputationState:
    row = db.query(PlayerReputationState).filter(PlayerReputationState.player_id == player_id).first()
    if row is None:
        import uuid as _uuid
        row = PlayerReputationState(id=_uuid.uuid4(), player_id=player_id)
        db.add(row)

    row.reputation_score = scores["reputation_score"]
    row.trust_score = scores["trust_score"]
    row.financial_reliability_score = scores["financial_reliability_score"]
    row.work_reliability_score = scores["work_reliability_score"]
    row.business_reliability_score = scores["business_reliability_score"]
    row.opportunity_readiness_score = scores["opportunity_readiness_score"]
    row.overall_trust_label = scores["overall_trust_label"]
    row.reputation_direction = scores["reputation_direction"]
    row.payment_signal_label = scores["payment_signal_label"]
    row.borrowing_signal_label = scores["borrowing_signal_label"]
    row.work_signal_label = scores["work_signal_label"]
    row.business_signal_label = scores["business_signal_label"]
    row.stability_signal_label = scores["stability_signal_label"]
    row.opportunity_access_label = scores["opportunity_access_label"]
    row.top_reputation_driver = scores["top_reputation_driver"]
    row.top_reputation_drag = scores["top_reputation_drag"]
    row.practical_actions_json = scores["practical_actions_json"]
    row.planning_insights_json = scores["planning_insights_json"]
    row.debug_json = scores["debug_json"]
    row.last_updated_on = day
    row.last_updated_date = as_of_date
    return row


def _upsert_reputation_history(
    db: Session,
    player_id: UUID,
    day: int,
    as_of_date: date,
    scores: dict,
) -> PlayerReputationHistory:
    hist = (
        db.query(PlayerReputationHistory)
        .filter(
            PlayerReputationHistory.player_id == player_id,
            PlayerReputationHistory.day == day,
        )
        .first()
    )
    if hist is None:
        import uuid as _uuid
        hist = PlayerReputationHistory(id=_uuid.uuid4(), player_id=player_id, day=day)
        db.add(hist)

    hist.as_of_date = as_of_date
    hist.reputation_score = scores["reputation_score"]
    hist.trust_score = scores["trust_score"]
    hist.financial_reliability_score = scores["financial_reliability_score"]
    hist.work_reliability_score = scores["work_reliability_score"]
    hist.business_reliability_score = scores["business_reliability_score"]
    hist.opportunity_readiness_score = scores["opportunity_readiness_score"]
    hist.overall_trust_label = scores["overall_trust_label"]
    hist.opportunity_access_label = scores["opportunity_access_label"]
    hist.reputation_direction = scores["reputation_direction"]
    hist.false_growth_suppressed = scores["_false_growth_suppressed"]
    hist.delinquency_drag_active = scores["_delinquency_drag_active"]
    hist.recovery_boost_active = scores["_recovery_boost_active"]
    return hist


# ===========================================================================
# PUBLIC API
# ===========================================================================


def build_player_reputation_profile(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Compute and persist the player's full reputation profile.

    Returns a dict representation of the persisted PlayerReputationState.
    """
    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    signals = _load_all_signals(db, player, resolved_day)
    scores = _compute_all_scores(player, resolved_day, signals)

    state = _upsert_reputation_state(db, player.id, resolved_day, resolved_date, scores)
    _upsert_reputation_history(db, player.id, resolved_day, resolved_date, scores)
    db.flush()

    return {
        "player_id": str(player.id),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "reputation_score": float(scores["reputation_score"]),
        "trust_score": float(scores["trust_score"]),
        "financial_reliability_score": float(scores["financial_reliability_score"]),
        "work_reliability_score": float(scores["work_reliability_score"]),
        "business_reliability_score": float(scores["business_reliability_score"]),
        "opportunity_readiness_score": float(scores["opportunity_readiness_score"]),
        "overall_trust_label": scores["overall_trust_label"],
        "reputation_direction": scores["reputation_direction"],
        "payment_signal_label": scores["payment_signal_label"],
        "borrowing_signal_label": scores["borrowing_signal_label"],
        "work_signal_label": scores["work_signal_label"],
        "business_signal_label": scores["business_signal_label"],
        "stability_signal_label": scores["stability_signal_label"],
        "opportunity_access_label": scores["opportunity_access_label"],
        "top_reputation_driver": scores["top_reputation_driver"],
        "top_reputation_drag": scores["top_reputation_drag"],
        "practical_actions": json.loads(scores["practical_actions_json"]),
        "planning_insights": json.loads(scores["planning_insights_json"]),
    }


def build_trust_signal_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Return granular trust signal breakdown without persisting."""
    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    pid = player.id

    delinq = _get_delinquency(db, pid)
    borrowing = _get_borrowing(db, pid)
    debt_behavior = _get_debt_behavior(db, pid)
    wealth = _get_wealth_state(db, pid)
    shock = _get_shock_state(db, pid)
    recovery = _get_recovery_state(db, pid)
    businesses = _get_businesses(db, pid)
    biz_logs = _recent_biz_logs(db, pid, resolved_day, 30)

    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False

    fin_score, fin_signal, fin_drag = _compute_financial_reliability_score(
        player, delinq, borrowing, debt_behavior, wealth
    )
    work_score, work_signal, work_drag = _compute_work_reliability_score(
        player, shock, recovery, debt_behavior
    )
    biz_score, biz_signal, biz_drag = _compute_business_reliability_score(
        player, businesses, biz_logs, wealth
    )

    stability_score = _d(getattr(wealth, "stability_before_growth_score", 50)) if wealth else Decimal("50")

    return {
        "player_id": str(pid),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "payment_signal": {
            "label": fin_signal,
            "score": float(_q4(fin_score)),
            "main_drag": fin_drag,
            "false_growth_active": false_growth,
        },
        "borrowing_signal": {
            "label": _resolve_signal_label(
                _clamp(Decimal("100") - _d(getattr(borrowing, "dependence_risk_score", 0)), SCORE_MIN, SCORE_MAX)
                if borrowing else Decimal("50")
            ),
            "dependence_risk_score": float(_d(getattr(borrowing, "dependence_risk_score", 0))),
            "active_loan_count": int(getattr(borrowing, "active_loan_count", 0) or 0),
            "repeat_borrowing_30d": int(getattr(borrowing, "repeat_borrowing_count_30d", 0) or 0),
        },
        "work_signal": {
            "label": work_signal,
            "score": float(_q4(work_score)),
            "main_drag": work_drag,
            "skill_level": int(getattr(player, "skill_level", 1) or 1),
        },
        "business_signal": {
            "label": biz_signal,
            "score": float(_q4(biz_score)),
            "main_drag": biz_drag,
            "business_count": len(businesses),
        },
        "stability_signal": {
            "label": _resolve_signal_label(stability_score),
            "stability_score": float(_q4(stability_score)),
            "buffer_days": float(_d(getattr(wealth, "buffer_days", 0))) if wealth else 0.0,
        },
    }


def build_job_reputation_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Career-facing reputation modifiers — influences job quality, raises, and contracts."""
    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    pid = player.id

    shock = _get_shock_state(db, pid)
    recovery = _get_recovery_state(db, pid)
    debt_behavior = _get_debt_behavior(db, pid)
    wealth = _get_wealth_state(db, pid)
    delinq = _get_delinquency(db, pid)
    borrowing = _get_borrowing(db, pid)

    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False
    work_score, work_signal, work_drag = _compute_work_reliability_score(
        player, shock, recovery, debt_behavior
    )
    fin_score, fin_signal, _ = _compute_financial_reliability_score(
        player, delinq, borrowing, debt_behavior, wealth
    )

    # Career modifier: blend work and financial reliability
    career_modifier = _clamp(
        (work_score - Decimal("50")) * Decimal("0.015")
        + (fin_score - Decimal("50")) * Decimal("0.008"),
        Decimal("-0.30"),
        Decimal("0.20"),
    )

    # opportunity_access_penalty from player model
    opp_pen = float(_d(getattr(player, "opportunity_access_penalty", 0)))
    career_progress_pen = float(_d(getattr(player, "career_progress_penalty", 0)))

    return {
        "player_id": str(pid),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "work_reliability_score": float(_q4(work_score)),
        "work_signal_label": work_signal,
        "main_drag": work_drag,
        "career_modifier_pct": float(_q4(career_modifier)),
        "career_modifier_direction": "positive" if career_modifier > 0 else ("negative" if career_modifier < 0 else "neutral"),
        "skill_level": int(getattr(player, "skill_level", 1) or 1),
        "has_job": bool(getattr(player, "main_job", None)),
        "opportunity_access_penalty": opp_pen,
        "career_progress_penalty": career_progress_pen,
        "false_growth_active": false_growth,
        "stress_level": float(_d(getattr(player, "stress", 0))),
        "recovery_boost_active": bool(
            debt_behavior and getattr(debt_behavior, "recovery_stage", "none") in ("rebuilding", "strong", "early")
        ),
    }


def build_business_reputation_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Business-facing reputation modifiers — influences customer trust, vendor terms, and demand."""
    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    pid = player.id

    businesses = _get_businesses(db, pid)
    biz_logs = _recent_biz_logs(db, pid, resolved_day, 30)
    wealth = _get_wealth_state(db, pid)
    debt_behavior = _get_debt_behavior(db, pid)
    delinq = _get_delinquency(db, pid)
    borrowing = _get_borrowing(db, pid)

    biz_score, biz_signal, biz_drag = _compute_business_reliability_score(
        player, businesses, biz_logs, wealth
    )
    fin_score, _, _ = _compute_financial_reliability_score(player, delinq, borrowing, debt_behavior, wealth)

    # Business modifier: +/- demand multiplier applied to future business cycles
    biz_modifier = _clamp(
        (biz_score - Decimal("50")) * Decimal("0.012")
        + (fin_score - Decimal("50")) * Decimal("0.006"),
        Decimal("-0.25"),
        Decimal("0.20"),
    )

    false_growth = bool(getattr(wealth, "false_growth_detected", False)) if wealth else False
    biz_pen = float(_d(getattr(player, "business_risk_penalty", 0)))

    return {
        "player_id": str(pid),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "business_reliability_score": float(_q4(biz_score)),
        "business_signal_label": biz_signal,
        "main_drag": biz_drag,
        "business_modifier_pct": float(_q4(biz_modifier)),
        "business_modifier_direction": "positive" if biz_modifier > 0 else ("negative" if biz_modifier < 0 else "neutral"),
        "business_count": len(businesses),
        "false_growth_active": false_growth,
        "business_risk_penalty": biz_pen,
        "financial_reliability_score": float(_q4(fin_score)),
    }


def build_opportunity_access_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Opportunity quality modifiers — what tier of jobs, credit, and deals are accessible."""
    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    pid = player.id

    signals = _load_all_signals(db, player, resolved_day)
    scores = _compute_all_scores(player, resolved_day, signals)

    opp_label = scores["opportunity_access_label"]
    opp_score = float(scores["opportunity_readiness_score"])

    # Human-readable descriptions per access tier
    tier_desc = {
        "restricted": "Very limited opportunities — clearing payment arrears is the priority path.",
        "limited": "Below standard access — address delinquency and reduce borrowing dependence.",
        "standard": "Normal opportunity access — consistent payments will gradually improve quality.",
        "elevated": "Above average access — eligible for better-rate credit and mid-tier job contracts.",
        "preferred": "Top-tier access — preferred partner rates and high-quality job opportunities available.",
    }

    return {
        "player_id": str(pid),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "opportunity_access_label": opp_label,
        "opportunity_readiness_score": opp_score,
        "tier_description": tier_desc.get(opp_label, ""),
        "trust_score": float(scores["trust_score"]),
        "reputation_score": float(scores["reputation_score"]),
        "reputation_direction": scores["reputation_direction"],
        "overall_trust_label": scores["overall_trust_label"],
        "practical_actions": json.loads(scores["practical_actions_json"]),
    }


def apply_reputation_effects(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Read-only projection of reputation effects.

    Returns the modifiers reputation would apply to jobs, credit, and business
    WITHOUT writing anything. Suitable for UI preview and planning screens.
    """
    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    pid = player.id

    # Load existing reputation state if persisted, else compute fresh
    state = db.query(PlayerReputationState).filter(PlayerReputationState.player_id == pid).first()
    if state is None:
        signals = _load_all_signals(db, player, resolved_day)
        scores = _compute_all_scores(player, resolved_day, signals)
        trust_score = scores["trust_score"]
        opp_label = scores["opportunity_access_label"]
        rep_score = scores["reputation_score"]
        opp_score = scores["opportunity_readiness_score"]
    else:
        trust_score = _d(state.trust_score)
        opp_label = state.opportunity_access_label
        rep_score = _d(state.reputation_score)
        opp_score = _d(state.opportunity_readiness_score)

    # Compute bounded modifier values (for display only — no writes)
    trust_modifier = _clamp(
        (trust_score - Decimal("50")) * Decimal("0.004"),
        Decimal("-0.2"),
        Decimal("0.2"),
    )
    job_quality_modifier = float(_clamp(
        (trust_score - Decimal("50")) * Decimal("0.003"),
        Decimal("-0.15"),
        Decimal("0.15"),
    ))
    credit_rate_modifier = float(_clamp(
        (trust_score - Decimal("50")) * Decimal("-0.002"),
        Decimal("-0.10"),
        Decimal("0.10"),
    ))
    demand_modifier = float(_clamp(
        (rep_score - Decimal("50")) * Decimal("0.003"),
        Decimal("-0.12"),
        Decimal("0.12"),
    ))

    return {
        "player_id": str(pid),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "trust_score": float(_q4(trust_score)),
        "overall_trust_label": _resolve_trust_label(trust_score),
        "opportunity_access_label": opp_label,
        "opportunity_readiness_score": float(_q4(opp_score)),
        "effects": {
            "job_quality_modifier_pct": round(job_quality_modifier, 4),
            "credit_rate_modifier_pct": round(credit_rate_modifier, 4),
            "demand_modifier_pct": round(demand_modifier, 4),
            "trust_modifier_pct": float(_q4(trust_modifier)),
        },
        "note": "Modifiers are projections only — no changes applied.",
    }


def build_reputation_summary(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Full synthesis: persists the profile and returns a comprehensive summary."""
    profile = build_player_reputation_profile(db, player_id, day=day, as_of_date=as_of_date)

    player = _get_player(db, player_id)
    resolved_day, resolved_date = _resolve_day(db, player, as_of_date, day)
    pid = player.id

    signals = _load_all_signals(db, player, resolved_day)
    effects = apply_reputation_effects(db, player_id, day=day, as_of_date=as_of_date)
    trust_signals = build_trust_signal_state(db, player_id, day=day, as_of_date=as_of_date)

    # History trend summary
    history = signals["history"]
    trend_7d: dict = {}
    if history:
        recent_7 = history[:7]
        trend_7d = {
            "avg_reputation_score": float(
                _q4(sum(_d(h.reputation_score) for h in recent_7) / len(recent_7))
            ),
            "avg_trust_score": float(
                _q4(sum(_d(h.trust_score) for h in recent_7) / len(recent_7))
            ),
            "samples": len(recent_7),
        }

    return {
        "player_id": str(pid),
        "day": resolved_day,
        "as_of_date": str(resolved_date),
        "profile": profile,
        "trust_signals": trust_signals,
        "effects": effects["effects"],
        "trend_7d": trend_7d,
        "opportunity_access_label": profile["opportunity_access_label"],
        "overall_trust_label": profile["overall_trust_label"],
        "reputation_direction": profile["reputation_direction"],
        "practical_actions": profile["practical_actions"],
        "planning_insights": profile["planning_insights"],
    }
