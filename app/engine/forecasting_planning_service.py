"""Step 42: Forecasting, Planning Intelligence, and Forward Projection Layer.

Projects a player's financial state forward using all prior systems as inputs.
This is NOT a new economy — it is a read-only projection layer on top of:
  - Step 35: shocks / fragility
  - Step 36: delinquency / survival
  - Step 37: borrowing / consumer credit
  - Step 38: debt behavior
  - Step 39: wealth
  - Step 40: reputation
  - Step 41: contracts / timing (primary driver)

Key design rules:
  - Deterministic baseline (no random chaos)
  - All scores bounded 0–100
  - Outputs are readable labels, not raw spreadsheets
  - Confidence level reflects data completeness
  - Simulation compares hypothetical actions vs. do-nothing baseline

Public functions:
  build_short_term_forecast(db, player_id, day=None, horizon_days=14)
  simulate_player_path(db, player_id, action, day=None)
  build_scenario_comparison(db, player_id, day=None)
  build_risk_projection_state(db, player_id, day=None)
  build_forecast_summary(db, player_id, day=None)
  build_decision_guidance(db, player_id, day=None)
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.database import Base  # noqa: F401 – ensure mapper is ready
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_contract_event import PlayerContractEvent
from app.models.player_contract_schedule import PlayerContractSchedule
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_forecast_snapshot import PlayerForecastSnapshot
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_reputation_state import PlayerReputationState
from app.models.player_shock_state import PlayerShockState
from app.models.player_wealth_state import PlayerWealthState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")

DEFAULT_HORIZON = 14          # forecast horizon in game days
SHORT_HORIZON = 7
LONG_HORIZON = 30

# Daily survival cost floor (XGP) — minimum cash consumption even with no obligations
DAILY_SURVIVAL_FLOOR_XGP = Decimal("20")

# Cash-gap warning thresholds
CASH_GAP_MINOR_XGP = Decimal("50")
CASH_GAP_MODERATE_XGP = Decimal("200")
CASH_GAP_URGENT_XGP = Decimal("500")

# Delinquency stage severity mapping
DELINQUENCY_SEVERITY: dict[str, int] = {
    "current": 0,
    "stretched": 1,
    "late": 2,
    "delinquent": 3,
    "critical": 4,
}

# Outlook thresholds (composite score 0–100: 100 = worst risk)
OUTLOOK_RISKY_THRESHOLD = Decimal("60")
OUTLOOK_TIGHT_THRESHOLD = Decimal("35")
OUTLOOK_STABLE_THRESHOLD = Decimal("20")

# Hypothetical action keys
ACTION_DO_NOTHING = "do_nothing"
ACTION_BORROW_SMALL = "borrow_small"
ACTION_BORROW_LARGE = "borrow_large"
ACTION_INVEST_SMALL = "invest_small"
ACTION_INVEST_LARGE = "invest_large"
ACTION_EXPAND_BUSINESS = "expand_business"
ACTION_SKIP_PAYMENT = "skip_payment"

VALID_ACTIONS = {
    ACTION_DO_NOTHING,
    ACTION_BORROW_SMALL,
    ACTION_BORROW_LARGE,
    ACTION_INVEST_SMALL,
    ACTION_INVEST_LARGE,
    ACTION_EXPAND_BUSINESS,
    ACTION_SKIP_PAYMENT,
}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ForecastingError(Exception):
    """Base Step 42 error."""


class ForecastingNotFoundError(ForecastingError):
    """Raised when required player or state rows are missing."""


class ForecastingValidationError(ForecastingError):
    """Raised for invalid inputs."""


# ---------------------------------------------------------------------------
# Precision helpers
# ---------------------------------------------------------------------------


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Q2, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal = Decimal("0"), hi: Decimal = Decimal("100")) -> Decimal:
    return max(lo, min(hi, value))


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Day / date helpers
# ---------------------------------------------------------------------------


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise ForecastingValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise ForecastingValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_day(day_number: int | None) -> tuple[int, date]:
    if day_number is not None:
        d = int(day_number)
        return d, _day_to_date(d)
    today = date.today()
    return _date_to_day(today), today


# ---------------------------------------------------------------------------
# DB fetch helpers
# ---------------------------------------------------------------------------


def _get_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise ForecastingNotFoundError(f"Player {player_id} not found.")
    return player


def _get_contract_schedule(db: Session, player_id: UUID) -> PlayerContractSchedule | None:
    return (
        db.query(PlayerContractSchedule)
        .filter(PlayerContractSchedule.player_id == player_id)
        .first()
    )


def _get_delinquency_state(db: Session, player_id: UUID) -> PlayerDelinquencyState | None:
    return (
        db.query(PlayerDelinquencyState)
        .filter(PlayerDelinquencyState.player_id == player_id)
        .first()
    )


def _get_borrowing_state(db: Session, player_id: UUID) -> PlayerBorrowingState | None:
    return (
        db.query(PlayerBorrowingState)
        .filter(PlayerBorrowingState.player_id == player_id)
        .first()
    )


def _get_debt_behavior_state(db: Session, player_id: UUID) -> PlayerDebtBehaviorState | None:
    return (
        db.query(PlayerDebtBehaviorState)
        .filter(PlayerDebtBehaviorState.player_id == player_id)
        .first()
    )


def _get_wealth_state(db: Session, player_id: UUID) -> PlayerWealthState | None:
    return (
        db.query(PlayerWealthState)
        .filter(PlayerWealthState.player_id == player_id)
        .first()
    )


def _get_reputation_state(db: Session, player_id: UUID) -> PlayerReputationState | None:
    return (
        db.query(PlayerReputationState)
        .filter(PlayerReputationState.player_id == player_id)
        .first()
    )


def _get_shock_state(db: Session, player_id: UUID) -> PlayerShockState | None:
    return (
        db.query(PlayerShockState)
        .filter(PlayerShockState.player_id == player_id)
        .first()
    )


def _get_active_loans(db: Session, player_id: UUID) -> list[PlayerLoanAccount]:
    return (
        db.query(PlayerLoanAccount)
        .filter(
            PlayerLoanAccount.player_id == player_id,
            PlayerLoanAccount.status == "active",
        )
        .all()
    )


def _get_upcoming_events(db: Session, player_id: UUID, from_day: int, to_day: int) -> list[PlayerContractEvent]:
    return (
        db.query(PlayerContractEvent)
        .filter(
            PlayerContractEvent.player_id == player_id,
            PlayerContractEvent.due_on_day >= from_day,
            PlayerContractEvent.due_on_day <= to_day,
        )
        .order_by(PlayerContractEvent.due_on_day)
        .all()
    )


def _get_housing_state(db: Session, player_id: UUID) -> PlayerHousingState | None:
    return (
        db.query(PlayerHousingState)
        .filter(PlayerHousingState.player_id == player_id, PlayerHousingState.active_flag == True)  # noqa: E712
        .first()
    )


def _get_employment_state(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Forecast state container
# ---------------------------------------------------------------------------


class _ForecastState:
    """Aggregated state from all prior systems for one player at one day."""

    def __init__(
        self,
        player: Player,
        day: int,
        contract_schedule: PlayerContractSchedule | None,
        delinquency: PlayerDelinquencyState | None,
        borrowing: PlayerBorrowingState | None,
        debt_behavior: PlayerDebtBehaviorState | None,
        wealth: PlayerWealthState | None,
        reputation: PlayerReputationState | None,
        shock: PlayerShockState | None,
        loans: list[PlayerLoanAccount],
        upcoming_events: list[PlayerContractEvent],
        housing: PlayerHousingState | None,
        employment: PlayerEmploymentState | None,
    ) -> None:
        self.player = player
        self.day = day
        self.contract_schedule = contract_schedule
        self.delinquency = delinquency
        self.borrowing = borrowing
        self.debt_behavior = debt_behavior
        self.wealth = wealth
        self.reputation = reputation
        self.shock = shock
        self.loans = loans
        self.upcoming_events = upcoming_events
        self.housing = housing
        self.employment = employment

    # --- convenience properties ---

    @property
    def cash(self) -> Decimal:
        return _d(self.player.cash)

    @property
    def monthly_income_xgp(self) -> Decimal:
        if self.employment and self.employment.employed_flag:
            return _d(self.employment.monthly_pay_xgp)
        return Decimal("0")

    @property
    def daily_income_xgp(self) -> Decimal:
        return _q4(self.monthly_income_xgp / Decimal("30"))

    @property
    def total_daily_debt_payment_xgp(self) -> Decimal:
        total = Decimal("0")
        for loan in self.loans:
            total += _d(loan.scheduled_daily_payment_xgp)
        return _q4(total)

    @property
    def delinquency_stage(self) -> str:
        if self.delinquency:
            return str(self.delinquency.current_delinquency_stage or "current")
        return "current"

    @property
    def cash_gap_before_income(self) -> Decimal:
        if self.contract_schedule:
            return _d(self.contract_schedule.cash_gap_before_next_income_xgp)
        return Decimal("0")

    @property
    def timing_pressure_label(self) -> str:
        if self.contract_schedule:
            return str(self.contract_schedule.timing_pressure_label or "low")
        return "low"

    @property
    def debt_spiral_risk(self) -> str:
        if self.debt_behavior:
            return str(self.debt_behavior.spiral_risk_label or "low")
        return "low"

    @property
    def wealth_phase(self) -> str:
        if self.wealth:
            return str(self.wealth.wealth_phase_label or "fragile")
        return "fragile"

    @property
    def safe_to_invest(self) -> bool:
        if self.wealth:
            return self.wealth.safe_to_invest_label in ("safe_small", "safe_medium", "safe_large")
        return False

    @property
    def shock_fragility_score(self) -> Decimal:
        if self.shock:
            return _d(self.shock.financial_fragility_score)
        return Decimal("50")

    @property
    def data_completeness_score(self) -> int:
        """Count how many optional state rows exist (0–8)."""
        present = 0
        for row in [self.contract_schedule, self.delinquency, self.borrowing,
                    self.debt_behavior, self.wealth, self.reputation, self.shock,
                    self.employment]:
            if row is not None:
                present += 1
        return present


# ---------------------------------------------------------------------------
# Internal scoring helpers
# ---------------------------------------------------------------------------


def _load_forecast_state(db: Session, player_id: UUID, day: int, horizon: int) -> _ForecastState:
    player = _get_player(db, player_id)
    return _ForecastState(
        player=player,
        day=day,
        contract_schedule=_get_contract_schedule(db, player_id),
        delinquency=_get_delinquency_state(db, player_id),
        borrowing=_get_borrowing_state(db, player_id),
        debt_behavior=_get_debt_behavior_state(db, player_id),
        wealth=_get_wealth_state(db, player_id),
        reputation=_get_reputation_state(db, player_id),
        shock=_get_shock_state(db, player_id),
        loans=_get_active_loans(db, player_id),
        upcoming_events=_get_upcoming_events(db, player_id, day, day + horizon),
        housing=_get_housing_state(db, player_id),
        employment=_get_employment_state(db, player_id),
    )


def _compute_daily_net_flow(state: _ForecastState, day_offset: int) -> Decimal:
    """Estimate daily net cash flow for a given offset day (0 = today)."""
    target_day = state.day + day_offset
    income = Decimal("0")
    outflow = DAILY_SURVIVAL_FLOOR_XGP + state.total_daily_debt_payment_xgp

    # Income events on this day
    for ev in state.upcoming_events:
        if ev.due_on_day == target_day and ev.income_flag:
            income += _d(ev.amount_xgp)

    # Obligation outflows on this day
    for ev in state.upcoming_events:
        if ev.due_on_day == target_day and not ev.income_flag and ev.status in ("upcoming", "due"):
            outflow += _d(ev.amount_xgp)

    return _q4(income - outflow)


def _project_cash_curve(state: _ForecastState, horizon: int) -> list[dict]:
    """Build day-by-day projected cash balance list."""
    curve: list[dict] = []
    running_cash = state.cash
    for offset in range(horizon + 1):
        net = _compute_daily_net_flow(state, offset)
        running_cash = _q4(running_cash + net)
        curve.append({
            "day": state.day + offset,
            "cash_xgp": float(running_cash),
            "daily_net_xgp": float(net),
        })
    return curve


def _find_liquidity_low_point(curve: list[dict]) -> tuple[float, int]:
    """Return (min_cash_xgp, day_of_low_point) from the projected curve."""
    if not curve:
        return 0.0, 0
    min_entry = min(curve, key=lambda c: c["cash_xgp"])
    return min_entry["cash_xgp"], min_entry["day"]


def _find_delinquency_risk_day(state: _ForecastState, curve: list[dict]) -> int | None:
    """Return the first day cash drops below zero (delinquency risk)."""
    for entry in curve:
        if entry["cash_xgp"] < 0:
            return entry["day"]
    return None


def _compute_composite_risk_score(state: _ForecastState, curve: list[dict]) -> Decimal:
    """Compute a composite 0–100 risk score. Higher = worse."""
    score = Decimal("0")

    # 1. Delinquency stage (0–40 pts)
    stage_idx = DELINQUENCY_SEVERITY.get(state.delinquency_stage, 0)
    score += _clamp(Decimal(stage_idx * 10), Decimal("0"), Decimal("40"))

    # 2. Cash gap risk (0–25 pts)
    gap = state.cash_gap_before_income
    if gap >= CASH_GAP_URGENT_XGP:
        score += Decimal("25")
    elif gap >= CASH_GAP_MODERATE_XGP:
        score += Decimal("15")
    elif gap >= CASH_GAP_MINOR_XGP:
        score += Decimal("8")

    # 3. Timing pressure (0–15 pts)
    tp = state.timing_pressure_label
    tp_scores = {"low": 0, "manageable": 4, "elevated": 10, "severe": 15}
    score += Decimal(tp_scores.get(tp, 5))

    # 4. Debt spiral risk (0–15 pts)
    ds = state.debt_spiral_risk
    ds_scores = {"low": 0, "rising": 5, "high": 10, "critical": 15}
    score += Decimal(ds_scores.get(ds, 0))

    # 5. Liquidity low point (0–5 pts)
    low_cash, _ = _find_liquidity_low_point(curve)
    if low_cash < 0:
        score += Decimal("5")

    return _clamp(_q4(score))


def _outlook_label(risk_score: Decimal) -> str:
    if risk_score >= OUTLOOK_RISKY_THRESHOLD:
        return "critical"
    if risk_score >= OUTLOOK_RISKY_THRESHOLD - Decimal("20"):
        return "risky"
    if risk_score >= OUTLOOK_TIGHT_THRESHOLD:
        return "tight"
    return "stable"


def _near_term_risk_label(risk_score: Decimal) -> str:
    if risk_score >= Decimal("65"):
        return "critical"
    if risk_score >= Decimal("45"):
        return "high"
    if risk_score >= Decimal("25"):
        return "moderate"
    return "low"


def _delinquency_risk_label(state: _ForecastState, delinquency_risk_day: int | None) -> str:
    stage_idx = DELINQUENCY_SEVERITY.get(state.delinquency_stage, 0)
    if stage_idx >= 3 or (delinquency_risk_day is not None and delinquency_risk_day - state.day <= 3):
        return "critical"
    if stage_idx >= 2 or (delinquency_risk_day is not None and delinquency_risk_day - state.day <= 7):
        return "high"
    if stage_idx >= 1 or (delinquency_risk_day is not None and delinquency_risk_day - state.day <= 14):
        return "moderate"
    return "low"


def _cash_gap_risk_label(state: _ForecastState) -> str:
    gap = state.cash_gap_before_income
    if gap >= CASH_GAP_URGENT_XGP:
        return "urgent"
    if gap >= CASH_GAP_MODERATE_XGP:
        return "moderate"
    if gap >= CASH_GAP_MINOR_XGP:
        return "minor"
    return "none"


def _debt_spiral_risk_label(state: _ForecastState) -> str:
    return state.debt_spiral_risk


def _confidence_label(state: _ForecastState) -> str:
    score = state.data_completeness_score
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _build_projected_obligation_hits(state: _ForecastState) -> list[dict]:
    """Return list of upcoming obligation events within the horizon."""
    result = []
    for ev in state.upcoming_events:
        if not ev.income_flag:
            result.append({
                "obligation_key": ev.obligation_key,
                "family": ev.obligation_family,
                "type": ev.obligation_type,
                "amount_xgp": float(_d(ev.amount_xgp)),
                "due_on_day": ev.due_on_day,
                "days_away": ev.due_on_day - state.day,
                "status": ev.status,
            })
    return result


def _build_projected_income_events(state: _ForecastState) -> list[dict]:
    """Return list of upcoming income events within the horizon."""
    result = []
    for ev in state.upcoming_events:
        if ev.income_flag:
            result.append({
                "income_key": ev.obligation_key,
                "type": ev.obligation_type,
                "amount_xgp": float(_d(ev.amount_xgp)),
                "due_on_day": ev.due_on_day,
                "days_away": ev.due_on_day - state.day,
                "status": ev.status,
            })
    return result


def _stress_trend_label(state: _ForecastState) -> str:
    """Project stress trend from current signals."""
    tp = state.timing_pressure_label
    ds = state.delinquency_stage
    stage_idx = DELINQUENCY_SEVERITY.get(ds, 0)
    if stage_idx >= 2 or tp == "severe":
        return "rising"
    if stage_idx == 1 or tp == "elevated":
        return "elevated"
    return "stable"


def _debt_trend_label(state: _ForecastState) -> str:
    """Project debt trend from behavior state."""
    if state.debt_behavior:
        return str(state.debt_behavior.trend_direction or "stable")
    return "stable"


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------


def _apply_action_to_state(state: _ForecastState, action: str) -> dict:
    """
    Apply a hypothetical action and return modified cash + obligation projections.
    Returns a dict with modified_cash_start and extra_daily_debt_payment.
    """
    base_cash = state.cash
    extra_daily_debt = Decimal("0")
    extra_immediate_cost = Decimal("0")
    extra_note = ""

    if action == ACTION_BORROW_SMALL:
        # Small bridge: +200 XGP now, +7 XGP/day repayment for 30 days
        base_cash += Decimal("200")
        extra_daily_debt = Decimal("7")
        extra_note = "Small bridge borrow: +200 XGP now, +7 XGP/day for 30 days"
    elif action == ACTION_BORROW_LARGE:
        # Large loan: +800 XGP now, +30 XGP/day repayment for 30 days
        base_cash += Decimal("800")
        extra_daily_debt = Decimal("30")
        extra_note = "Large loan: +800 XGP now, +30 XGP/day for 30 days"
    elif action == ACTION_INVEST_SMALL:
        # Small invest: -100 XGP now, no new obligations, upside not modeled
        extra_immediate_cost = Decimal("100")
        base_cash -= extra_immediate_cost
        extra_note = "Small investment: -100 XGP now (upside not guaranteed)"
    elif action == ACTION_INVEST_LARGE:
        # Large invest: -400 XGP now
        extra_immediate_cost = Decimal("400")
        base_cash -= extra_immediate_cost
        extra_note = "Large investment: -400 XGP now (upside not guaranteed)"
    elif action == ACTION_EXPAND_BUSINESS:
        # Business expansion: -200 XGP overhead, +15 XGP/day ongoing overhead for 60 days
        extra_immediate_cost = Decimal("200")
        base_cash -= extra_immediate_cost
        extra_daily_debt = Decimal("15")
        extra_note = "Business expansion: -200 XGP + increased operating overhead"
    elif action == ACTION_SKIP_PAYMENT:
        # Skip a payment: retain cash this cycle, but delinquency risk rises
        # We model the "saved" cash as the daily debt payment
        base_cash += state.total_daily_debt_payment_xgp
        extra_note = "Skip payment: short-term cash relief, delinquency risk rises"
    else:
        extra_note = "No change (do nothing)"

    return {
        "modified_cash_start": base_cash,
        "extra_daily_debt_payment": extra_daily_debt,
        "extra_note": extra_note,
    }


def _project_cash_curve_with_overrides(
    state: _ForecastState,
    horizon: int,
    modified_cash_start: Decimal,
    extra_daily_debt: Decimal,
) -> list[dict]:
    """Project curve using modified initial cash and extra daily debt."""
    curve: list[dict] = []
    running_cash = modified_cash_start
    for offset in range(horizon + 1):
        target_day = state.day + offset
        income = Decimal("0")
        outflow = DAILY_SURVIVAL_FLOOR_XGP + state.total_daily_debt_payment_xgp + extra_daily_debt

        for ev in state.upcoming_events:
            if ev.due_on_day == target_day and ev.income_flag:
                income += _d(ev.amount_xgp)
            if ev.due_on_day == target_day and not ev.income_flag and ev.status in ("upcoming", "due"):
                outflow += _d(ev.amount_xgp)

        net = _q4(income - outflow)
        running_cash = _q4(running_cash + net)
        curve.append({
            "day": target_day,
            "cash_xgp": float(running_cash),
            "daily_net_xgp": float(net),
        })
    return curve


def _outcome_label_from_curve(curve: list[dict], horizon: int, delinquency_stage: str) -> str:
    """Derive short/medium-term outcome label from a projected curve."""
    low_cash, low_day = _find_liquidity_low_point(curve)
    stage_idx = DELINQUENCY_SEVERITY.get(delinquency_stage, 0)
    short_entries = curve[:min(7, len(curve))]
    short_low = min((e["cash_xgp"] for e in short_entries), default=0.0)

    if low_cash < 0 or stage_idx >= 3:
        return "critical"
    if short_low < 30 or stage_idx >= 2:
        return "risky"
    if short_low < 100 or stage_idx >= 1:
        return "tight"
    return "stable"


def _risk_label_from_curve(curve: list[dict]) -> str:
    low_cash, _ = _find_liquidity_low_point(curve)
    if low_cash < 0:
        return "high"
    if low_cash < 50:
        return "moderate"
    return "low"


def _stability_label_from_curve(curve: list[dict]) -> str:
    """Assess how stable (flat/growing) the curve is."""
    if len(curve) < 2:
        return "unknown"
    start = curve[0]["cash_xgp"]
    end = curve[-1]["cash_xgp"]
    variance = max(abs(e["cash_xgp"] - start) for e in curve)
    if end < 0:
        return "deteriorating"
    if end >= start * 1.1 and variance < start * 0.3:
        return "improving"
    if variance > start * 0.5:
        return "volatile"
    if abs(end - start) < start * 0.05:
        return "flat"
    return "stable"


# ---------------------------------------------------------------------------
# Days-to-problem helper
# ---------------------------------------------------------------------------


def _days_to_next_problem(
    state: _ForecastState,
    curve: list[dict],
    delinquency_risk_day: int | None,
) -> int | None:
    """Return number of days until the nearest projected problem."""
    candidates = []
    if delinquency_risk_day is not None:
        candidates.append(delinquency_risk_day - state.day)
    # Cash drops below 50 XGP
    for entry in curve:
        if entry["cash_xgp"] < 50:
            candidates.append(entry["day"] - state.day)
            break
    if not candidates:
        return None
    return max(0, min(candidates))


def _next_major_risk_event_label(state: _ForecastState, delinquency_risk_day: int | None) -> str:
    """Describe the nearest projected risk event."""
    if delinquency_risk_day is not None:
        days_away = delinquency_risk_day - state.day
        return f"Cash depletion risk in {days_away} day(s)"
    tp = state.timing_pressure_label
    if tp == "severe":
        return "Severe obligation cluster approaching"
    if tp == "elevated":
        return "Elevated timing pressure in current window"
    stage_idx = DELINQUENCY_SEVERITY.get(state.delinquency_stage, 0)
    if stage_idx >= 2:
        return "Active delinquency — payment catch-up critical"
    return "No near-term risk event detected"


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------


def _upsert_forecast_snapshot(
    db: Session,
    player_id: UUID,
    day: int,
    horizon: int,
    outlook: str,
    near_term_risk: str,
    delinquency_risk: str,
    cash_gap_risk: str,
    debt_spiral_risk: str,
    liquidity_low_point: float,
    delinquency_risk_day: int | None,
    days_to_problem: int | None,
    confidence: str,
    guidance_label: str,
    top_recommendation: str,
    avoid_action: str,
    next_major_risk: str,
    best_action: str,
    curve: list[dict],
    risk_signals: dict,
    debug: dict,
) -> PlayerForecastSnapshot:
    snap = (
        db.query(PlayerForecastSnapshot)
        .filter(PlayerForecastSnapshot.player_id == player_id)
        .first()
    )
    if snap is None:
        snap = PlayerForecastSnapshot(id=uuid.uuid4(), player_id=player_id)
        db.add(snap)

    snap.forecast_horizon_days = horizon
    snap.generated_on_day = day
    snap.generated_on_date = _day_to_date(day)
    snap.overall_outlook_label = outlook
    snap.near_term_risk_label = near_term_risk
    snap.delinquency_risk_label = delinquency_risk
    snap.cash_gap_risk_label = cash_gap_risk
    snap.debt_spiral_risk_label = debt_spiral_risk
    snap.liquidity_low_point_xgp = _q4(Decimal(str(liquidity_low_point)))
    snap.projected_delinquency_risk_day = delinquency_risk_day
    snap.days_until_next_problem = days_to_problem
    snap.confidence_level = confidence
    snap.guidance_label = guidance_label
    snap.top_recommendation = top_recommendation
    snap.avoid_action = avoid_action
    snap.next_major_risk_event = next_major_risk
    snap.best_stabilizing_action = best_action
    snap.projected_cash_curve_json = _dump_json(curve)
    snap.risk_signals_json = _dump_json(risk_signals)
    snap.debug_json = _dump_json(debug)
    snap.last_updated_on = day
    db.flush()
    return snap


# ---------------------------------------------------------------------------
# Guidance logic
# ---------------------------------------------------------------------------


def _compute_guidance(state: _ForecastState, risk_score: Decimal, delinquency_risk_day: int | None) -> dict:
    """Derive human-readable guidance from composite state."""
    tp = state.timing_pressure_label
    stage_idx = DELINQUENCY_SEVERITY.get(state.delinquency_stage, 0)
    days_to_risk = (delinquency_risk_day - state.day) if delinquency_risk_day else 99
    cash = state.cash
    debt_spiral = state.debt_spiral_risk
    safe_invest = state.safe_to_invest

    # Guidance label
    if risk_score >= Decimal("65") or stage_idx >= 3:
        guidance_label = "urgent_caution"
    elif risk_score >= Decimal("45") or stage_idx >= 2:
        guidance_label = "reduce_risk"
    elif risk_score >= Decimal("25") or tp in ("elevated", "severe"):
        guidance_label = "monitor"
    else:
        guidance_label = "opportunity_ready"

    # Top recommendation
    if stage_idx >= 3 or days_to_risk <= 3:
        top_rec = "Prioritise catching up on missed payments before any other action."
    elif stage_idx >= 2 or days_to_risk <= 7:
        top_rec = "Avoid new debt. Focus on clearing current-cycle obligations."
    elif tp == "severe":
        top_rec = "Address obligation cluster — consider a targeted bridge if cash gap is confirmed."
    elif tp == "elevated" and cash < Decimal("150"):
        top_rec = "Hold cash reserves until high-density obligation window passes."
    elif debt_spiral in ("high", "critical"):
        top_rec = "Stop adding debt. Current trajectory leads to a spiral."
    elif safe_invest and risk_score < Decimal("25"):
        top_rec = "You are stable enough to invest small this cycle."
    else:
        top_rec = "Maintain current behaviour — no urgent action needed."

    # Avoid action
    if stage_idx >= 2 or days_to_risk <= 5:
        avoid = "Investing or expanding while payment risk is active."
    elif debt_spiral in ("high", "critical"):
        avoid = "Taking on additional loans — debt spiral risk is elevated."
    elif tp in ("elevated", "severe"):
        avoid = "Large one-off expenditures during high-pressure obligation window."
    elif not safe_invest and cash < Decimal("300"):
        avoid = "Investing before cash buffer is rebuilt."
    else:
        avoid = "Aggressive risk-taking without first building a 14-day cash buffer."

    # Confidence label for guidance
    confidence_label = _confidence_label(state)

    # Reasoning summary
    parts = []
    if stage_idx >= 1:
        parts.append(f"Delinquency stage: {state.delinquency_stage}")
    if tp != "low":
        parts.append(f"Timing pressure: {tp}")
    if state.cash_gap_before_income > CASH_GAP_MINOR_XGP:
        parts.append(f"Cash gap before next income: {float(state.cash_gap_before_income):.0f} XGP")
    if debt_spiral != "low":
        parts.append(f"Debt spiral risk: {debt_spiral}")
    if not parts:
        parts.append("All systems stable")
    reasoning = ". ".join(parts) + "."

    return {
        "guidance_label": guidance_label,
        "top_recommendation": top_rec,
        "avoid_action": avoid,
        "confidence_label": confidence_label,
        "reasoning_summary": reasoning,
        "debug_meta": {
            "risk_score": float(risk_score),
            "stage_idx": stage_idx,
            "days_to_delinquency_risk": days_to_risk if days_to_risk < 99 else None,
            "cash_on_hand": float(cash),
            "safe_to_invest": safe_invest,
        },
    }


# ---------------------------------------------------------------------------
# 1. build_short_term_forecast
# ---------------------------------------------------------------------------


def build_short_term_forecast(
    db: Session,
    player_id: str | UUID,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
) -> dict:
    """Build 7–14 day deterministic cash-flow forecast for a player.

    Returns:
        dict with keys: player_id, forecast_horizon_days, projected_cash_curve,
        projected_obligation_hits, projected_income_events, projected_liquidity_low_point,
        projected_delinquency_risk_day, projected_stress_trend, projected_debt_trend,
        confidence_level, short_summary, debug_meta.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    if horizon_days < 1 or horizon_days > 60:
        raise ForecastingValidationError("horizon_days must be between 1 and 60.")

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    curve = _project_cash_curve(state, horizon_days)
    low_cash, low_day = _find_liquidity_low_point(curve)
    delinquency_risk_day = _find_delinquency_risk_day(state, curve)

    confidence = _confidence_label(state)
    short_summary_parts = []
    if delinquency_risk_day:
        short_summary_parts.append(f"Cash runs out by day {delinquency_risk_day}")
    elif low_cash < 50:
        short_summary_parts.append(f"Liquidity low point: {low_cash:.0f} XGP on day {low_day}")
    else:
        short_summary_parts.append("Cash flow stable across horizon")
    stage_idx = DELINQUENCY_SEVERITY.get(state.delinquency_stage, 0)
    if stage_idx >= 2:
        short_summary_parts.append(f"Active delinquency ({state.delinquency_stage})")
    if state.timing_pressure_label in ("elevated", "severe"):
        short_summary_parts.append(f"Timing pressure: {state.timing_pressure_label}")

    return {
        "player_id": str(pid),
        "day": d,
        "forecast_horizon_days": horizon_days,
        "projected_cash_curve": curve,
        "projected_obligation_hits": _build_projected_obligation_hits(state),
        "projected_income_events": _build_projected_income_events(state),
        "projected_liquidity_low_point": low_cash,
        "projected_liquidity_low_day": low_day,
        "projected_delinquency_risk_day": delinquency_risk_day,
        "projected_stress_trend": _stress_trend_label(state),
        "projected_debt_trend": _debt_trend_label(state),
        "confidence_level": confidence,
        "short_summary": "; ".join(short_summary_parts),
        "debug_meta": {
            "cash_on_hand": float(state.cash),
            "daily_income_xgp": float(state.daily_income_xgp),
            "daily_debt_payment_xgp": float(state.total_daily_debt_payment_xgp),
            "event_count_in_window": len(state.upcoming_events),
            "data_completeness": state.data_completeness_score,
        },
    }


# ---------------------------------------------------------------------------
# 2. simulate_player_path
# ---------------------------------------------------------------------------


def simulate_player_path(
    db: Session,
    player_id: str | UUID,
    action: str,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
) -> dict:
    """Simulate a hypothetical player action and project its cash outcome.

    Supported actions: do_nothing, borrow_small, borrow_large,
    invest_small, invest_large, expand_business, skip_payment.

    Returns:
        dict with action, projected results, and comparison vs baseline.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    action = str(action).strip().lower()
    if action not in VALID_ACTIONS:
        raise ForecastingValidationError(
            f"Unknown action '{action}'. Valid: {sorted(VALID_ACTIONS)}"
        )

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    # Baseline (do nothing)
    baseline_curve = _project_cash_curve(state, horizon_days)
    baseline_low, baseline_low_day = _find_liquidity_low_point(baseline_curve)
    baseline_delinquency_day = _find_delinquency_risk_day(state, baseline_curve)

    # Simulated action
    overrides = _apply_action_to_state(state, action)
    sim_curve = _project_cash_curve_with_overrides(
        state,
        horizon_days,
        overrides["modified_cash_start"],
        overrides["extra_daily_debt_payment"],
    )
    sim_low, sim_low_day = _find_liquidity_low_point(sim_curve)
    sim_delinquency_day = _find_delinquency_risk_day(state, sim_curve)

    # Net effect
    net_cash_effect = sim_curve[-1]["cash_xgp"] - baseline_curve[-1]["cash_xgp"] if sim_curve and baseline_curve else 0.0
    delinquency_risk_change = "none"
    if baseline_delinquency_day and not sim_delinquency_day:
        delinquency_risk_change = "reduced"
    elif not baseline_delinquency_day and sim_delinquency_day:
        delinquency_risk_change = "increased"
    elif baseline_delinquency_day and sim_delinquency_day:
        days_diff = sim_delinquency_day - baseline_delinquency_day
        delinquency_risk_change = "delayed" if days_diff > 0 else "accelerated"

    return {
        "player_id": str(pid),
        "day": d,
        "action": action,
        "action_note": overrides["extra_note"],
        "baseline": {
            "projected_liquidity_low_point": baseline_low,
            "liquidity_low_day": baseline_low_day,
            "delinquency_risk_day": baseline_delinquency_day,
            "end_cash_xgp": baseline_curve[-1]["cash_xgp"] if baseline_curve else float(state.cash),
            "outcome_label": _outcome_label_from_curve(baseline_curve, horizon_days, state.delinquency_stage),
        },
        "simulated": {
            "projected_cash_curve": sim_curve,
            "projected_liquidity_low_point": sim_low,
            "liquidity_low_day": sim_low_day,
            "delinquency_risk_day": sim_delinquency_day,
            "end_cash_xgp": sim_curve[-1]["cash_xgp"] if sim_curve else float(state.cash),
            "outcome_label": _outcome_label_from_curve(sim_curve, horizon_days, state.delinquency_stage),
            "risk_label": _risk_label_from_curve(sim_curve),
            "stability_label": _stability_label_from_curve(sim_curve),
        },
        "net_effect": {
            "cash_change_end_xgp": net_cash_effect,
            "delinquency_risk_change": delinquency_risk_change,
            "stability_change": _stability_label_from_curve(sim_curve),
        },
        "projected_obligations": _build_projected_obligation_hits(state),
        "projected_income": _build_projected_income_events(state),
        "debug_meta": {
            "extra_daily_debt_xgp": float(overrides["extra_daily_debt_payment"]),
            "modified_cash_start": float(overrides["modified_cash_start"]),
        },
    }


# ---------------------------------------------------------------------------
# 3. build_scenario_comparison
# ---------------------------------------------------------------------------


def build_scenario_comparison(
    db: Session,
    player_id: str | UUID,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
    actions: list[str] | None = None,
) -> dict:
    """Compare 2–3 scenarios side-by-side.

    Default scenarios: do_nothing, borrow_small, invest_small.
    Each option shows short-term and medium-term tradeoffs.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    if actions is None:
        actions = [ACTION_DO_NOTHING, ACTION_BORROW_SMALL, ACTION_INVEST_SMALL]
    if len(actions) > 5:
        raise ForecastingValidationError("Maximum 5 scenario actions per comparison.")
    for a in actions:
        if a not in VALID_ACTIONS:
            raise ForecastingValidationError(f"Unknown action '{a}'.")

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    options = []
    for action in actions:
        overrides = _apply_action_to_state(state, action)
        curve = _project_cash_curve_with_overrides(
            state,
            horizon_days,
            overrides["modified_cash_start"],
            overrides["extra_daily_debt_payment"],
        )
        short_curve = curve[:min(7, len(curve))]
        med_curve = curve[7:] if len(curve) > 7 else curve

        short_low = min((e["cash_xgp"] for e in short_curve), default=float(state.cash))
        delinquency_day = _find_delinquency_risk_day(state, curve)

        options.append({
            "option_key": action,
            "action_note": overrides["extra_note"],
            "short_term_outcome_label": _outcome_label_from_curve(short_curve, 7, state.delinquency_stage),
            "medium_term_outcome_label": _outcome_label_from_curve(med_curve or curve, horizon_days, state.delinquency_stage),
            "risk_label": _risk_label_from_curve(curve),
            "stability_label": _stability_label_from_curve(curve),
            "net_effect_summary": overrides["extra_note"],
            "projected_end_cash_xgp": curve[-1]["cash_xgp"] if curve else float(state.cash),
            "liquidity_low_point_xgp": short_low,
            "delinquency_risk_day": delinquency_day,
        })

    # Rank by end cash (best option)
    best_by_stability = max(options, key=lambda o: o["projected_end_cash_xgp"])

    return {
        "player_id": str(pid),
        "day": d,
        "horizon_days": horizon_days,
        "options": options,
        "recommended_option_key": best_by_stability["option_key"],
        "recommendation_reason": (
            f"'{best_by_stability['option_key']}' projects the best end cash balance "
            f"and {best_by_stability['stability_label']} stability."
        ),
        "debug_meta": {
            "cash_on_hand": float(state.cash),
            "data_completeness": state.data_completeness_score,
        },
    }


# ---------------------------------------------------------------------------
# 4. build_risk_projection_state
# ---------------------------------------------------------------------------


def build_risk_projection_state(
    db: Session,
    player_id: str | UUID,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
) -> dict:
    """Build the danger-radar: translate raw forecast into warning labels.

    Returns:
        dict with near_term_risk_label, delinquency_risk_label, cash_gap_risk_label,
        debt_spiral_risk_projection, timing_collision_risk, short_summary, debug_meta.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    curve = _project_cash_curve(state, horizon_days)
    risk_score = _compute_composite_risk_score(state, curve)
    delinquency_risk_day = _find_delinquency_risk_day(state, curve)
    low_cash, low_day = _find_liquidity_low_point(curve)

    near_term = _near_term_risk_label(risk_score)
    delinquency_risk = _delinquency_risk_label(state, delinquency_risk_day)
    cash_gap_risk = _cash_gap_risk_label(state)
    debt_spiral = _debt_spiral_risk_label(state)
    timing_collision = str(getattr(state.contract_schedule, "obligation_collision_label", "none") or "none")

    summary_parts = []
    if near_term in ("high", "critical"):
        summary_parts.append(f"Near-term risk: {near_term}")
    if delinquency_risk in ("high", "critical"):
        summary_parts.append(f"Delinquency risk: {delinquency_risk}")
    if cash_gap_risk in ("moderate", "urgent"):
        summary_parts.append(f"Cash gap risk: {cash_gap_risk}")
    if debt_spiral in ("high", "critical"):
        summary_parts.append(f"Debt spiral projection: {debt_spiral}")
    if timing_collision in ("collision", "compound"):
        summary_parts.append(f"Timing collision: {timing_collision}")
    if not summary_parts:
        summary_parts.append("No active risk signals")

    return {
        "player_id": str(pid),
        "day": d,
        "near_term_risk_label": near_term,
        "delinquency_risk_label": delinquency_risk,
        "cash_gap_risk_label": cash_gap_risk,
        "debt_spiral_risk_projection": debt_spiral,
        "timing_collision_risk": timing_collision,
        "composite_risk_score": float(risk_score),
        "projected_liquidity_low_point_xgp": low_cash,
        "projected_delinquency_risk_day": delinquency_risk_day,
        "short_summary": "; ".join(summary_parts),
        "debug_meta": {
            "risk_score": float(risk_score),
            "delinquency_stage": state.delinquency_stage,
            "timing_pressure": state.timing_pressure_label,
            "cash_gap_xgp": float(state.cash_gap_before_income),
            "shock_fragility_score": float(state.shock_fragility_score),
        },
    }


# ---------------------------------------------------------------------------
# 5. build_forecast_summary
# ---------------------------------------------------------------------------


def build_forecast_summary(
    db: Session,
    player_id: str | UUID,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
) -> dict:
    """Build a concise, player-readable forecast summary.

    Returns:
        dict with overall_outlook_label, next_major_risk_event,
        days_until_next_problem, best_stabilizing_action, worst_action_to_take,
        short_summary, debug_meta.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    curve = _project_cash_curve(state, horizon_days)
    risk_score = _compute_composite_risk_score(state, curve)
    delinquency_risk_day = _find_delinquency_risk_day(state, curve)
    low_cash, _ = _find_liquidity_low_point(curve)
    outlook = _outlook_label(risk_score)
    days_to_problem = _days_to_next_problem(state, curve, delinquency_risk_day)
    next_risk_event = _next_major_risk_event_label(state, delinquency_risk_day)
    guidance = _compute_guidance(state, risk_score, delinquency_risk_day)

    # Best stabilising action
    if outlook in ("critical", "risky"):
        best_action = "Focus on clearing current obligations before any investment."
    elif outlook == "tight":
        best_action = "Hold cash reserves, avoid discretionary spending."
    else:
        best_action = guidance["top_recommendation"]

    # Worst action to take
    if outlook in ("critical", "risky"):
        worst_action = "Taking on new debt or making discretionary investments."
    elif outlook == "tight":
        worst_action = "Expanding business overhead or large purchases."
    else:
        worst_action = guidance["avoid_action"]

    summary_parts = [f"Outlook: {outlook}"]
    if days_to_problem is not None:
        summary_parts.append(f"Next problem: ~{days_to_problem} day(s)")
    summary_parts.append(next_risk_event)

    return {
        "player_id": str(pid),
        "day": d,
        "overall_outlook_label": outlook,
        "next_major_risk_event": next_risk_event,
        "days_until_next_problem": days_to_problem,
        "best_stabilizing_action": best_action,
        "worst_action_to_take": worst_action,
        "short_summary": " | ".join(summary_parts),
        "projected_liquidity_low_point_xgp": low_cash,
        "confidence_level": _confidence_label(state),
        "debug_meta": {
            "risk_score": float(risk_score),
            "cash_on_hand": float(state.cash),
            "delinquency_stage": state.delinquency_stage,
            "timing_pressure": state.timing_pressure_label,
        },
    }


# ---------------------------------------------------------------------------
# 6. build_decision_guidance
# ---------------------------------------------------------------------------


def build_decision_guidance(
    db: Session,
    player_id: str | UUID,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
) -> dict:
    """Build smart decision guidance for the player.

    This is the 'what should I do right now?' layer.

    Returns:
        dict with guidance_label, top_recommendation, avoid_action,
        confidence_label, reasoning_summary, debug_meta.
    """
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    curve = _project_cash_curve(state, horizon_days)
    risk_score = _compute_composite_risk_score(state, curve)
    delinquency_risk_day = _find_delinquency_risk_day(state, curve)

    return {
        "player_id": str(pid),
        "day": d,
        **_compute_guidance(state, risk_score, delinquency_risk_day),
    }


# ---------------------------------------------------------------------------
# 7. Convenience: build and persist full snapshot
# ---------------------------------------------------------------------------


def build_and_persist_forecast(
    db: Session,
    player_id: str | UUID,
    *,
    day: int | None = None,
    horizon_days: int = DEFAULT_HORIZON,
) -> dict:
    """Build forecast summary + risk state, persist snapshot, return combined dict."""
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ForecastingValidationError(f"Invalid player_id: {player_id}") from exc

    d, _ = _resolve_day(day)
    state = _load_forecast_state(db, pid, d, horizon_days)

    curve = _project_cash_curve(state, horizon_days)
    risk_score = _compute_composite_risk_score(state, curve)
    delinquency_risk_day = _find_delinquency_risk_day(state, curve)
    low_cash, _ = _find_liquidity_low_point(curve)
    outlook = _outlook_label(risk_score)
    days_to_problem = _days_to_next_problem(state, curve, delinquency_risk_day)
    guidance = _compute_guidance(state, risk_score, delinquency_risk_day)

    risk_signals = {
        "near_term_risk_label": _near_term_risk_label(risk_score),
        "delinquency_risk_label": _delinquency_risk_label(state, delinquency_risk_day),
        "cash_gap_risk_label": _cash_gap_risk_label(state),
        "debt_spiral_risk_label": _debt_spiral_risk_label(state),
        "timing_collision_risk": str(getattr(state.contract_schedule, "obligation_collision_label", "none") or "none"),
    }

    snap = _upsert_forecast_snapshot(
        db,
        pid,
        d,
        horizon_days,
        outlook,
        risk_signals["near_term_risk_label"],
        risk_signals["delinquency_risk_label"],
        risk_signals["cash_gap_risk_label"],
        risk_signals["debt_spiral_risk_label"],
        low_cash,
        delinquency_risk_day,
        days_to_problem,
        _confidence_label(state),
        guidance["guidance_label"],
        guidance["top_recommendation"],
        guidance["avoid_action"],
        _next_major_risk_event_label(state, delinquency_risk_day),
        guidance["top_recommendation"],
        curve,
        risk_signals,
        guidance["debug_meta"],
    )

    return {
        "player_id": str(pid),
        "day": d,
        "snapshot_id": str(snap.id),
        "overall_outlook_label": outlook,
        "composite_risk_score": float(risk_score),
        "projected_liquidity_low_point_xgp": low_cash,
        "projected_delinquency_risk_day": delinquency_risk_day,
        "days_until_next_problem": days_to_problem,
        "confidence_level": _confidence_label(state),
        **risk_signals,
        **guidance,
    }
