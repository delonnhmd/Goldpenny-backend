"""Step 38: Debt Behavior, Spiral Detection, and Recovery Layer.

This service is a *meta-layer* that reads from Steps 35/36/37
(personal shocks, financial survival/delinquency, consumer borrowing)
and synthesises a richer, multi-period picture of how a player's debt
behaviour is evolving.  It does NOT mutate data owned by those steps;
it only writes to its own two tables:
  - player_debt_behavior_states  (rolling per-player snapshot)
  - player_debt_trend_history    (append-only daily rows)
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.database import Base  # noqa: F401 – ensure mapper is ready
from app.models.player import Player
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_debt_trend_history import PlayerDebtTrendHistory
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState

# ---------------------------------------------------------------------------
# Constants – shared with Steps 35/36/37 for semantic alignment
# ---------------------------------------------------------------------------

GAME_EPOCH = date(2026, 1, 1)
MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

DELINQUENCY_STAGES = ("current", "stretched", "late", "delinquent", "critical")
STAGE_INDEX: dict[str, int] = {s: i for i, s in enumerate(DELINQUENCY_STAGES)}

# Minimum consecutive stable history rows required to reach each recovery stage.
RECOVERY_STAGE_THRESHOLDS: dict[str, int] = {
    "early": 1,
    "stabilizing": 3,
    "rebuilding": 7,
    "strong": 14,
}

# Score thresholds for composite spiral risk.
SPIRAL_RISK_THRESHOLDS: dict[str, Decimal] = {
    "low": Decimal("25"),
    "rising": Decimal("50"),
    "high": Decimal("75"),
}

# Planning-warning messages.
_WARN_DEPENDENCY = "Borrowing frequency is high — each new loan raises future payment pressure."
_WARN_STACK = "Payment stack is under pressure — missing a single payment can trigger late fees and delinquency escalation."
_WARN_SPIRAL_HIGH = "Debt spiral risk is elevated — prioritise paying down active loans before taking on new obligations."
_WARN_SPIRAL_CRITICAL = "Critical spiral risk — avoid any new borrowing and focus entirely on meeting current payment obligations."
_WARN_STAGE = "Your delinquency stage is severe — missed payments at this stage carry cascading credit and fee penalties."
_WARN_SHOCK = "High fragility score — an unexpected shock event could tip finances from stressed to critical."
_WARN_DETERIORATING = "Your debt trajectory is worsening — act early to reverse the trend before it becomes a spiral."


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DebtBehaviorError(Exception):
    """Base Step 38 error."""


class DebtBehaviorNotFoundError(DebtBehaviorError):
    """Raised when player or required state is missing."""


class DebtBehaviorValidationError(DebtBehaviorError):
    """Raised for invalid inputs."""


# ---------------------------------------------------------------------------
# Precision helpers
# ---------------------------------------------------------------------------


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _to_float(value: Decimal | int | float) -> float:
    return float(_q4(_d(value)))


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


def _safe_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        payload = json.loads(raw)
    except Exception:
        return fallback
    return payload if isinstance(payload, type(fallback)) else fallback


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtBehaviorNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise DebtBehaviorNotFoundError("Player not found.")
    return row


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise DebtBehaviorValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise DebtBehaviorValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_day(
    db: Session,
    player: Player,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> tuple[int, date]:
    if day_number is not None:
        return int(day_number), _day_to_date(int(day_number))
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date
    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


def _get_borrowing_state(db: Session, player_id: UUID) -> PlayerBorrowingState | None:
    return db.query(PlayerBorrowingState).filter(PlayerBorrowingState.player_id == player_id).first()


def _get_delinquency_state(db: Session, player_id: UUID) -> PlayerDelinquencyState | None:
    return db.query(PlayerDelinquencyState).filter(PlayerDelinquencyState.player_id == player_id).first()


def _get_shock_state(db: Session, player_id: UUID) -> PlayerShockState | None:
    return db.query(PlayerShockState).filter(PlayerShockState.player_id == player_id).first()


def _active_loans(db: Session, player_id: UUID) -> list[PlayerLoanAccount]:
    try:
        return (
            db.query(PlayerLoanAccount)
            .filter(
                PlayerLoanAccount.player_id == player_id,
                PlayerLoanAccount.status.in_(["active", "delinquent"]),
            )
            .order_by(PlayerLoanAccount.accepted_on_day.asc())
            .all()
        )
    except Exception:
        return []


def _recent_payments(db: Session, player_id: UUID, day: int, window_days: int = 30) -> list[PlayerPaymentHistory]:
    start = max(1, int(day) - max(1, int(window_days)) + 1)
    try:
        return (
            db.query(PlayerPaymentHistory)
            .filter(
                PlayerPaymentHistory.player_id == player_id,
                PlayerPaymentHistory.day_number >= start,
                PlayerPaymentHistory.day_number <= int(day),
            )
            .order_by(PlayerPaymentHistory.day_number.asc())
            .all()
        )
    except Exception:
        return []


def _recent_borrowing_history(db: Session, player_id: UUID, day: int, window_days: int = 30) -> list[PlayerBorrowingHistory]:
    start = max(1, int(day) - max(1, int(window_days)) + 1)
    try:
        return (
            db.query(PlayerBorrowingHistory)
            .filter(
                PlayerBorrowingHistory.player_id == player_id,
                PlayerBorrowingHistory.day_number >= start,
                PlayerBorrowingHistory.day_number <= int(day),
            )
            .order_by(PlayerBorrowingHistory.day_number.asc())
            .all()
        )
    except Exception:
        return []


def _recent_trend_history(db: Session, player_id: UUID, day: int, window_days: int = 14) -> list[PlayerDebtTrendHistory]:
    start = max(1, int(day) - max(1, int(window_days)))
    return (
        db.query(PlayerDebtTrendHistory)
        .filter(
            PlayerDebtTrendHistory.player_id == player_id,
            PlayerDebtTrendHistory.day >= start,
            PlayerDebtTrendHistory.day < int(day),
        )
        .order_by(PlayerDebtTrendHistory.day.asc())
        .all()
    )


def _get_or_create_behavior_state(db: Session, player_id: UUID) -> PlayerDebtBehaviorState:
    row = db.query(PlayerDebtBehaviorState).filter(PlayerDebtBehaviorState.player_id == player_id).first()
    if row is not None:
        return row
    row = PlayerDebtBehaviorState(player_id=player_id)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Score computation helpers
# ---------------------------------------------------------------------------


def _compute_debt_dependency(
    borrowing_state: PlayerBorrowingState | None,
    active_loan_count: int,
) -> Decimal:
    """0–100 score; higher = more dependent on borrowing."""
    base = _d(getattr(borrowing_state, "dependence_risk_score", 0))
    freq_add = _clamp(_d(getattr(borrowing_state, "repeat_borrowing_count_30d", 0)) * Decimal("8"), Decimal("0"), Decimal("40"))
    loan_add = _clamp(_d(active_loan_count) * Decimal("15"), Decimal("0"), Decimal("45"))
    return _q4(_clamp(base + freq_add + loan_add, Decimal("0"), Decimal("100")))


def _compute_payment_stack_pressure(
    delinquency_state: PlayerDelinquencyState | None,
) -> Decimal:
    """0–100 score; higher = payment stack is under more stress."""
    if delinquency_state is None:
        return Decimal("0")
    base = _d(getattr(delinquency_state, "credit_pressure_score", 0))
    missed = _d(getattr(delinquency_state, "missed_payment_count_30d", 0))
    late = _d(getattr(delinquency_state, "late_payment_count_30d", 0))
    stress_days = _d(getattr(delinquency_state, "days_under_payment_stress", 0))
    stage = str(getattr(delinquency_state, "current_delinquency_stage", "current")).strip().lower()
    stage_add = _d(STAGE_INDEX.get(stage, 0)) * Decimal("12")
    return _q4(
        _clamp(
            base + missed * Decimal("8") + late * Decimal("3") + stress_days * Decimal("0.5") + stage_add,
            Decimal("0"),
            Decimal("100"),
        )
    )


def _compute_borrowing_frequency(
    borrowing_state: PlayerBorrowingState | None,
    active_loan_count: int,
) -> Decimal:
    """0–100 score; higher = borrowing more frequently relative to capacity."""
    repeat_30d = _d(getattr(borrowing_state, "repeat_borrowing_count_30d", 0))
    loan_add = _d(active_loan_count) * Decimal("20")
    freq_add = repeat_30d * Decimal("18")
    return _q4(_clamp(freq_add + loan_add, Decimal("0"), Decimal("100")))


def _compute_financial_stability(
    dependency: Decimal,
    payment_pressure: Decimal,
    shock_state: PlayerShockState | None,
) -> Decimal:
    """0–100 score; higher = more stable (inverse of combined risk)."""
    shock_risk = _d(getattr(shock_state, "shock_risk_score", 0))
    fragility = _d(getattr(shock_state, "financial_fragility_score", 0))
    instability = (
        payment_pressure * Decimal("0.45")
        + dependency * Decimal("0.30")
        + shock_risk * Decimal("0.15")
        + fragility * Decimal("0.10")
    )
    return _q4(_clamp(Decimal("100") - instability, Decimal("0"), Decimal("100")))


def _composite_risk(dependency: Decimal, payment_pressure: Decimal, borrowing_freq: Decimal) -> Decimal:
    return _q4((dependency + payment_pressure + borrowing_freq) / Decimal("3"))


def _spiral_risk_label(composite: Decimal) -> str:
    if composite >= SPIRAL_RISK_THRESHOLDS["high"]:
        return "critical"
    if composite >= SPIRAL_RISK_THRESHOLDS["rising"]:
        return "high"
    if composite >= SPIRAL_RISK_THRESHOLDS["low"]:
        return "rising"
    return "low"


def _debt_state_label(spiral_label: str, trend_dir: str) -> str:
    if spiral_label == "critical":
        return "spiral"
    if spiral_label == "high":
        return "unstable"
    if spiral_label == "rising" or (spiral_label == "low" and trend_dir == "deteriorating"):
        return "building pressure"
    return "controlled"


def _trend_direction(current_composite: Decimal, history_rows: list[PlayerDebtTrendHistory]) -> str:
    if len(history_rows) < 2:
        return "stable"
    recent_window = history_rows[-min(7, len(history_rows)):]
    older_window = history_rows[: max(1, len(history_rows) - len(recent_window))]

    recent_avg = sum(_d(r.composite_risk_score) for r in recent_window) / _d(len(recent_window))
    older_avg = sum(_d(r.composite_risk_score) for r in older_window) / _d(len(older_window))

    delta = current_composite - recent_avg
    if delta >= Decimal("4"):
        return "deteriorating"
    if delta <= Decimal("-4"):
        return "improving"
    return "stable"


def _consecutive_stable_days(history_rows: list[PlayerDebtTrendHistory]) -> int:
    """Count consecutive tail rows where spiral_risk_label is 'low' or 'rising'."""
    count = 0
    for row in reversed(history_rows):
        label = str(getattr(row, "spiral_risk_label", "low")).strip().lower()
        if label in {"low", "rising"}:
            count += 1
        else:
            break
    return count


def _recovery_stage_from_streak(consecutive_stable: int, spiral_label: str) -> str:
    """Derive recovery stage label from streak length; no recovery if spiral is high/critical."""
    if spiral_label in {"high", "critical"}:
        return "none"
    if consecutive_stable >= RECOVERY_STAGE_THRESHOLDS["strong"]:
        return "strong"
    if consecutive_stable >= RECOVERY_STAGE_THRESHOLDS["rebuilding"]:
        return "rebuilding"
    if consecutive_stable >= RECOVERY_STAGE_THRESHOLDS["stabilizing"]:
        return "stabilizing"
    if consecutive_stable >= RECOVERY_STAGE_THRESHOLDS["early"]:
        return "early"
    return "none"


def _recovery_confidence(stage: str, consecutive_stable: int) -> Decimal:
    target = RECOVERY_STAGE_THRESHOLDS.get(stage, 1) if stage != "none" else 1
    return _q4(_clamp(_d(consecutive_stable) / _d(target), Decimal("0"), Decimal("1")))


def _top_risk_driver(
    dependency: Decimal,
    payment_pressure: Decimal,
    borrowing_freq: Decimal,
    shock_state: PlayerShockState | None,
    delinquency_state: PlayerDelinquencyState | None,
) -> str:
    candidates = {
        "high_dependency_score": dependency,
        "payment_stack_pressure": payment_pressure,
        "frequent_borrowing": borrowing_freq,
        "elevated_shock_risk": _d(getattr(shock_state, "shock_risk_score", 0)),
        "financial_fragility": _d(getattr(shock_state, "financial_fragility_score", 0)),
        "delinquency_stage": _d(STAGE_INDEX.get(str(getattr(delinquency_state, "current_delinquency_stage", "current")).lower(), 0)) * Decimal("25"),
    }
    return max(candidates, key=lambda k: float(candidates[k]))  # type: ignore[return-value]


def _top_recovery_driver(
    stability: Decimal,
    delinquency_state: PlayerDelinquencyState | None,
    shock_state: PlayerShockState | None,
    trend_dir: str,
) -> str:
    stage = str(getattr(delinquency_state, "current_delinquency_stage", "current")).strip().lower()
    if stage == "current" and stability >= Decimal("65"):
        return "stable_payment_history"
    if trend_dir == "improving":
        return "improving_trend"
    recovery_capacity = _d(getattr(shock_state, "recovery_capacity_score", 0))
    if recovery_capacity >= Decimal("65"):
        return "high_recovery_capacity"
    recent_recovery = _d(getattr(shock_state, "recent_recovery_support", 0))
    if recent_recovery >= Decimal("2"):
        return "recent_recovery_support_events"
    return "gradual_stabilization"


def _build_planning_warnings(
    spiral_label: str,
    trend_dir: str,
    dependency: Decimal,
    payment_pressure: Decimal,
    shock_state: PlayerShockState | None,
    delinquency_state: PlayerDelinquencyState | None,
) -> list[str]:
    warnings: list[str] = []
    stage = str(getattr(delinquency_state, "current_delinquency_stage", "current")).strip().lower()
    fragility = _d(getattr(shock_state, "financial_fragility_score", 0))

    if spiral_label == "critical":
        warnings.append(_WARN_SPIRAL_CRITICAL)
    elif spiral_label == "high":
        warnings.append(_WARN_SPIRAL_HIGH)

    if dependency >= Decimal("55"):
        warnings.append(_WARN_DEPENDENCY)

    if payment_pressure >= Decimal("50"):
        warnings.append(_WARN_STACK)

    if stage in {"delinquent", "critical"}:
        warnings.append(_WARN_STAGE)

    if fragility >= Decimal("60"):
        warnings.append(_WARN_SHOCK)

    if trend_dir == "deteriorating" and spiral_label not in {"high", "critical"}:
        warnings.append(_WARN_DETERIORATING)

    return warnings


def _time_to_instability(spiral_label: str, trend_dir: str) -> str:
    if spiral_label == "critical" and trend_dir == "deteriorating":
        return "1–3 days"
    if spiral_label == "critical":
        return "3–5 days"
    if spiral_label == "high" and trend_dir == "deteriorating":
        return "4–7 days"
    if spiral_label == "high":
        return "7–10 days"
    if spiral_label == "rising":
        return "10–14 days"
    return "30+ days"


# ---------------------------------------------------------------------------
# Public API – 6 exported functions
# ---------------------------------------------------------------------------


def build_debt_behavior_profile(
    db: Session,
    player_id: str | UUID,
    day: int,
) -> dict:
    """Compute and persist rolling debt behavior scores for the player.

    Returns a dict with 5 scores, trend_direction, and all label fields.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtBehaviorNotFoundError("Player not found.") from exc
    if db.query(Player).filter(Player.id == pid).first() is None:
        raise DebtBehaviorNotFoundError("Player not found.")

    borrowing = _get_borrowing_state(db, pid)
    delinquency = _get_delinquency_state(db, pid)
    shock = _get_shock_state(db, pid)
    loans = _active_loans(db, pid)
    active_loan_count = len(loans)

    dependency = _compute_debt_dependency(borrowing, active_loan_count)
    payment_pressure = _compute_payment_stack_pressure(delinquency)
    borrow_freq = _compute_borrowing_frequency(borrowing, active_loan_count)
    stability = _compute_financial_stability(dependency, payment_pressure, shock)
    composite = _composite_risk(dependency, payment_pressure, borrow_freq)

    history_rows = _recent_trend_history(db, pid, day, 14)
    trend_dir = _trend_direction(composite, history_rows)
    spiral_label = _spiral_risk_label(composite)
    state_label = _debt_state_label(spiral_label, trend_dir)
    consecutive_stable = _consecutive_stable_days(history_rows)
    recovery = _recovery_stage_from_streak(consecutive_stable, spiral_label)

    top_risk = _top_risk_driver(dependency, payment_pressure, borrow_freq, shock, delinquency)
    top_rec = _top_recovery_driver(stability, delinquency, shock, trend_dir)
    warnings = _build_planning_warnings(spiral_label, trend_dir, dependency, payment_pressure, shock, delinquency)

    resolved_date = _day_to_date(day)

    # ── persist rolling state ──────────────────────────────────────────────
    state = _get_or_create_behavior_state(db, pid)
    state.debt_dependency_score = dependency
    state.payment_stack_pressure_score = payment_pressure
    state.borrowing_frequency_score = borrow_freq
    state.financial_stability_score = stability
    state.trend_direction = trend_dir
    state.debt_state_label = state_label
    state.spiral_risk_label = spiral_label
    state.recovery_stage = recovery
    state.top_risk_driver = top_risk
    state.top_recovery_driver = top_rec
    state.planning_warnings_json = _dump_json(warnings)
    state.last_updated_on = int(day)
    state.last_updated_date = resolved_date
    state.debug_json = _dump_json(
        {
            "active_loan_count": active_loan_count,
            "composite_risk_score": _to_float(composite),
            "consecutive_stable_days": consecutive_stable,
            "delinquency_stage": str(getattr(delinquency, "current_delinquency_stage", "current")),
        }
    )
    db.flush()

    # ── append trend history row ───────────────────────────────────────────
    _upsert_trend_row(
        db=db,
        player_id=pid,
        day=day,
        resolved_date=resolved_date,
        dependency=dependency,
        payment_pressure=payment_pressure,
        borrow_freq=borrow_freq,
        stability=stability,
        composite=composite,
        trend_dir=trend_dir,
        state_label=state_label,
        spiral_label=spiral_label,
        recovery=recovery,
        trigger_signals=warnings,
    )

    return {
        "player_id": str(pid),
        "day_number": int(day),
        "as_of_date": resolved_date.isoformat(),
        "debt_dependency_score": _to_float(dependency),
        "payment_stack_pressure_score": _to_float(payment_pressure),
        "borrowing_frequency_score": _to_float(borrow_freq),
        "financial_stability_score": _to_float(stability),
        "composite_risk_score": _to_float(composite),
        "trend_direction": trend_dir,
        "debt_state_label": state_label,
        "spiral_risk_label": spiral_label,
        "recovery_stage": recovery,
        "top_risk_driver": top_risk,
        "top_recovery_driver": top_rec,
        "planning_warnings": warnings,
    }


def _upsert_trend_row(
    db: Session,
    player_id: UUID,
    day: int,
    resolved_date: date,
    dependency: Decimal,
    payment_pressure: Decimal,
    borrow_freq: Decimal,
    stability: Decimal,
    composite: Decimal,
    trend_dir: str,
    state_label: str,
    spiral_label: str,
    recovery: str,
    trigger_signals: list[str],
) -> None:
    """Insert or update a trend history row for this player×day."""
    existing = (
        db.query(PlayerDebtTrendHistory)
        .filter(
            PlayerDebtTrendHistory.player_id == player_id,
            PlayerDebtTrendHistory.day == int(day),
        )
        .first()
    )
    if existing is not None:
        existing.debt_dependency_score = dependency
        existing.payment_stack_pressure_score = payment_pressure
        existing.borrowing_frequency_score = borrow_freq
        existing.financial_stability_score = stability
        existing.composite_risk_score = composite
        existing.trend_direction = trend_dir
        existing.debt_state_label = state_label
        existing.spiral_risk_label = spiral_label
        existing.recovery_stage = recovery
        existing.trigger_signals_json = _dump_json(trigger_signals)
    else:
        row = PlayerDebtTrendHistory(
            player_id=player_id,
            day=int(day),
            as_of_date=resolved_date,
            debt_dependency_score=dependency,
            payment_stack_pressure_score=payment_pressure,
            borrowing_frequency_score=borrow_freq,
            financial_stability_score=stability,
            composite_risk_score=composite,
            trend_direction=trend_dir,
            debt_state_label=state_label,
            spiral_risk_label=spiral_label,
            recovery_stage=recovery,
            trigger_signals_json=_dump_json(trigger_signals),
        )
        db.add(row)
    db.flush()


# ---------------------------------------------------------------------------


def build_debt_trend_state(
    db: Session,
    player_id: str | UUID,
    day: int,
) -> dict:
    """Return a rolling trend analysis over the last 14 days of history."""
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtBehaviorNotFoundError("Player not found.") from exc

    history_rows = _recent_trend_history(db, pid, day + 1, 14)

    if not history_rows:
        return {
            "player_id": str(pid),
            "day_number": int(day),
            "has_history": False,
            "trend_direction": "stable",
            "days_tracked": 0,
            "average_composite_risk": 0.0,
            "worst_spiral_label": "low",
            "most_recent_spiral_label": "low",
            "consecutive_stable_days": 0,
            "trend_summary": "Insufficient history to assess trend.",
        }

    composites = [_d(r.composite_risk_score) for r in history_rows]
    avg_composite = _q4(sum(composites) / _d(len(composites)))
    worst_label = max(
        (_spiral_risk_label(_d(r.composite_risk_score)) for r in history_rows),
        key=lambda l: ["low", "rising", "high", "critical"].index(l),
    )
    most_recent_label = str(history_rows[-1].spiral_risk_label)
    consecutive_stable = _consecutive_stable_days(history_rows)

    # Simple direction calculation from stored composite scores.
    half = max(1, len(history_rows) // 2)
    older_avg = sum(composites[:half]) / _d(half)
    recent_avg = sum(composites[half:]) / _d(max(1, len(composites) - half))
    delta = recent_avg - older_avg
    if delta >= Decimal("4"):
        trend_dir = "deteriorating"
    elif delta <= Decimal("-4"):
        trend_dir = "improving"
    else:
        trend_dir = "stable"

    if trend_dir == "improving":
        summary = "Your debt risk scores are improving over the tracked period."
    elif trend_dir == "deteriorating":
        summary = "Your debt risk scores are worsening — consider reducing loan activity."
    else:
        summary = "Debt scores are broadly stable over the tracked period."

    return {
        "player_id": str(pid),
        "day_number": int(day),
        "has_history": True,
        "trend_direction": trend_dir,
        "days_tracked": len(history_rows),
        "average_composite_risk": _to_float(avg_composite),
        "worst_spiral_label": worst_label,
        "most_recent_spiral_label": most_recent_label,
        "consecutive_stable_days": consecutive_stable,
        "trend_summary": summary,
    }


# ---------------------------------------------------------------------------


def detect_debt_spiral_state(
    db: Session,
    player_id: str | UUID,
    day: int,
    profile: dict | None = None,
) -> dict:
    """Assess current spiral risk level, primary driver, and estimated instability horizon.

    ``profile`` may be passed in to avoid a double-compute when called from
    build_debt_behavior_summary.  If absent it is computed on the fly.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtBehaviorNotFoundError("Player not found.") from exc

    if profile is None:
        profile = build_debt_behavior_profile(db, pid, day)

    spiral_label = str(profile.get("spiral_risk_label", "low"))
    trend_dir = str(profile.get("trend_direction", "stable"))
    primary_driver = str(profile.get("top_risk_driver", "unknown"))
    time_est = _time_to_instability(spiral_label, trend_dir)

    if spiral_label == "critical":
        summary = (
            "Critical debt spiral risk. Payment obligations are likely to exceed available resources "
            "within days. Immediate debt reduction is essential."
        )
    elif spiral_label == "high":
        summary = (
            "High spiral risk detected. Multiple debt pressure signals are compounding. "
            "Borrowing access will narrow and recovery will become more difficult."
        )
    elif spiral_label == "rising":
        summary = (
            "Spiral risk is rising. Early warning signals have appeared — "
            "taking corrective action now is significantly easier than later."
        )
    else:
        summary = "Debt spiral risk is currently low. Maintain payment discipline to keep it that way."

    return {
        "player_id": str(pid),
        "day_number": int(day),
        "spiral_risk_label": spiral_label,
        "primary_driver": primary_driver,
        "time_to_instability_estimate": time_est,
        "composite_risk_score": profile.get("composite_risk_score", 0.0),
        "trend_direction": trend_dir,
        "short_summary": summary,
    }


# ---------------------------------------------------------------------------


def detect_recovery_state(
    db: Session,
    player_id: str | UUID,
    day: int,
    profile: dict | None = None,
) -> dict:
    """Assess the player's recovery trajectory from historical stability streaks.

    Recovery is deliberately *slower* to accumulate than damage — the streak
    thresholds (1/3/7/14 days) enforce this asymmetry.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtBehaviorNotFoundError("Player not found.") from exc

    if profile is None:
        profile = build_debt_behavior_profile(db, pid, day)

    # Use history for days *before* the current evaluation day so the row just
    # inserted by build_debt_behavior_profile is not counted in the streak.
    history_rows = _recent_trend_history(db, pid, day, 28)
    consecutive_stable = _consecutive_stable_days(history_rows)
    spiral_label = str(profile.get("spiral_risk_label", "low"))
    recovery = _recovery_stage_from_streak(consecutive_stable, spiral_label)
    confidence = _recovery_confidence(recovery, consecutive_stable)

    stage_messages = {
        "none": "No recovery momentum yet. Focus on avoiding missed payments and reducing open loans.",
        "early": "Early recovery signs detected. One more stable week will move you into the stabilizing stage.",
        "stabilizing": "Your debt trajectory is stabilizing. Continue avoiding new loans to consolidate progress.",
        "rebuilding": "You are actively rebuilding. Borrowing access is beginning to recover.",
        "strong": "Strong recovery established. Financial resilience has been restored.",
    }

    return {
        "player_id": str(pid),
        "day_number": int(day),
        "recovery_stage": recovery,
        "confidence_score": _to_float(confidence),
        "consecutive_stable_days": consecutive_stable,
        "spiral_risk_label": spiral_label,
        "short_summary": stage_messages.get(recovery, "Unknown recovery state."),
    }


# ---------------------------------------------------------------------------


def build_debt_pressure_effects(
    db: Session,
    player_id: str | UUID,
    day: int,
    profile: dict | None = None,
) -> dict:
    """Compute debt-driven modifier values for Steps 35/36/37 consumers.

    Returns a dict of modifiers — callers apply them to their own systems.
    This function does NOT mutate any table; it only reads and derives.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtBehaviorNotFoundError("Player not found.") from exc

    if profile is None:
        profile = build_debt_behavior_profile(db, pid, day)

    spiral_label = str(profile.get("spiral_risk_label", "low"))
    dependency = _d(profile.get("debt_dependency_score", 0))
    payment_pressure = _d(profile.get("payment_stack_pressure_score", 0))
    composite = _d(profile.get("composite_risk_score", 0))
    trend_dir = str(profile.get("trend_direction", "stable"))

    # Stress baseline modifier (+0 to +25 stress points)
    stress_modifier = _q4(
        _clamp(
            composite * Decimal("0.25")
            + (_d(3) if trend_dir == "deteriorating" else Decimal("0")),
            Decimal("0"),
            Decimal("25"),
        )
    )

    # Shock sensitivity multiplier (1.0 to 1.5)
    shock_sensitivity = _q4(
        _clamp(
            Decimal("1.0") + (composite / Decimal("100")) * Decimal("0.5"),
            Decimal("1.0"),
            Decimal("1.5"),
        )
    )

    # Borrowing access penalty (0 to 35 score points)
    borrowing_penalty = _q4(
        _clamp(
            payment_pressure * Decimal("0.22")
            + dependency * Decimal("0.13"),
            Decimal("0"),
            Decimal("35"),
        )
    )

    # Business expansion penalty (0.0 to 0.40 multiplier penalty)
    business_penalty = _q4(
        _clamp(
            (composite / Decimal("100")) * Decimal("0.40"),
            Decimal("0"),
            Decimal("0.40"),
        )
    )

    warnings = _safe_json(
        (db.query(PlayerDebtBehaviorState).filter(PlayerDebtBehaviorState.player_id == pid).first() or object).__dict__.get("planning_warnings_json"),  # type: ignore[union-attr]
        [],
    )
    # Ensure we have the latest
    if not warnings:
        warnings = list(profile.get("planning_warnings", []))

    return {
        "player_id": str(pid),
        "day_number": int(day),
        "spiral_risk_label": spiral_label,
        "stress_baseline_modifier": _to_float(stress_modifier),
        "shock_sensitivity_modifier": _to_float(shock_sensitivity),
        "borrowing_access_penalty": _to_float(borrowing_penalty),
        "business_expansion_penalty": _to_float(business_penalty),
        "planning_warnings": warnings,
        "composite_risk_score": _to_float(composite),
    }


# ---------------------------------------------------------------------------


def build_debt_behavior_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Full synthesised debt behaviour summary combining all sub-components.

    This is the primary entrypoint for API consumers who want a single
    comprehensive view without calling each sub-function separately.
    """
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    pid = player.id

    profile = build_debt_behavior_profile(db, pid, day)
    spiral = detect_debt_spiral_state(db, pid, day, profile)
    recovery = detect_recovery_state(db, pid, day, profile)
    effects = build_debt_pressure_effects(db, pid, day, profile)
    trend = build_debt_trend_state(db, pid, day)

    state_label = str(profile.get("debt_state_label", "controlled"))
    recovery_label = str(recovery.get("recovery_stage", "none"))
    top_risk = str(profile.get("top_risk_driver", "unknown"))
    top_rec = str(profile.get("top_recovery_driver", "unknown"))
    warnings = list(profile.get("planning_warnings", []))

    # Practical actions
    practical_actions: list[str] = []
    spiral_label = str(profile.get("spiral_risk_label", "low"))
    if spiral_label in {"critical", "high"}:
        practical_actions.append("Pause all new borrowing until at least one active loan is fully paid off.")
    if str(profile.get("payment_stack_pressure_score", 0)) != "0":
        pressure = _d(profile.get("payment_stack_pressure_score", 0))
        if pressure >= Decimal("50"):
            practical_actions.append("Prioritise making all scheduled loan and obligation payments on time this cycle.")
    if _d(profile.get("debt_dependency_score", 0)) >= Decimal("55"):
        practical_actions.append("Consider replacing rolling short-term loans with a single longer-term consolidation product.")
    trend_dir = str(profile.get("trend_direction", "stable"))
    if trend_dir == "deteriorating":
        practical_actions.append("Your trajectory is worsening — review your spending commitments and defer non-essential expenses.")
    if recovery_label in {"rebuilding", "strong"}:
        practical_actions.append("Recovery is progressing — continue current payment behaviour for 7 more days to lock in gains.")

    if not practical_actions:
        practical_actions.append("Maintain current payment discipline and avoid unnecessary borrowing.")

    short_summary = (
        f"Debt state: {state_label}. Spiral risk: {spiral_label}. "
        f"Recovery: {recovery_label}. Trend: {trend_dir}."
    )

    return {
        "player_id": str(pid),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "debt_state_label": state_label,
        "recovery_state_label": recovery_label,
        "spiral_risk_label": spiral_label,
        "trend_direction": trend_dir,
        "top_risk_driver": top_risk,
        "top_recovery_driver": top_rec,
        "debt_dependency_score": profile.get("debt_dependency_score", 0.0),
        "payment_stack_pressure_score": profile.get("payment_stack_pressure_score", 0.0),
        "borrowing_frequency_score": profile.get("borrowing_frequency_score", 0.0),
        "financial_stability_score": profile.get("financial_stability_score", 0.0),
        "composite_risk_score": profile.get("composite_risk_score", 0.0),
        "consecutive_stable_days": int(recovery.get("consecutive_stable_days", 0)),
        "recovery_confidence_score": recovery.get("confidence_score", 0.0),
        "stress_baseline_modifier": effects.get("stress_baseline_modifier", 0.0),
        "shock_sensitivity_modifier": effects.get("shock_sensitivity_modifier", 1.0),
        "borrowing_access_penalty": effects.get("borrowing_access_penalty", 0.0),
        "business_expansion_penalty": effects.get("business_expansion_penalty", 0.0),
        "time_to_instability_estimate": spiral.get("time_to_instability_estimate", "30+ days"),
        "practical_actions": practical_actions,
        "planning_warnings": warnings,
        "trend_days_tracked": int(trend.get("days_tracked", 0)),
        "short_summary": short_summary,
    }
