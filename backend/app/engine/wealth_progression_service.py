"""Step 39: Wealth Building + Asset Progression Layer.

This service synthesises a player's full wealth picture from:
  - cash and savings (player model)
  - stock holdings (Step 9)
  - business equity (Step 10/15)
  - debt state (Steps 36/37/38)
  - shock/fragility state (Step 35)
  - progression state (Step 26)

It introduces:
  - wealth_profile: survival vs growth vs compounding phase tracking
  - savings_capacity: tells the truth about safe-to-save vs safe-to-invest
  - asset_progression: bounded, explainable asset value tracking
  - wealth_action evaluation: labels wealth moves as premature/cautious/reasonable/aggressive/reckless
  - net_worth_summary: false-growth detection and durable-vs-fragile growth distinction
  - wealth_momentum_summary: full synthesis with planning insights
  - experience_phase: controlled early-game softening curve (taper-out, no exploit loops)

Write tables:
  - player_wealth_states           (rolling per-player snapshot, upsert)
  - player_wealth_trend_history    (append-only daily rows, upsert by player+day)
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
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_shock_state import PlayerShockState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_wealth_state import PlayerWealthState
from app.models.player_wealth_trend_history import PlayerWealthTrendHistory
from app.models.sector_stock import SectorStock

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAME_EPOCH = date(2026, 1, 1)
MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

# Minimum emergency reserve that should never be invested (XGP)
MINIMUM_EMERGENCY_RESERVE = Decimal("500")

# Recommended buffer days before safe-to-invest threshold
BUFFER_DAYS_SAVE_THRESHOLD = Decimal("7")   # >= 7 days → safe_to_save
BUFFER_DAYS_INVEST_THRESHOLD = Decimal("14")  # >= 14 days + stable → cautious invest

# Experience phase boundaries (days elapsed since account_created_day)
EXPERIENCE_PHASE_TRANSITIONS = {
    "onboarding": (1, 7),
    "early_growth": (8, 30),
    "stabilization": (31, 90),
    "pressure": (91, 180),
    "full_sim": (181, 99999),
}

# Softening modifiers per phase: (shock_severity_mult, credit_penalty_mult,
#   borrowing_harshness_mult, competition_friction_mult, business_downside_mult,
#   small_win_boost_add)
SOFTENING_MODIFIERS: dict[str, dict[str, float]] = {
    "onboarding": {
        "shock_severity_mult": 0.55,
        "credit_penalty_mult": 0.60,
        "borrowing_harshness_mult": 0.70,
        "competition_friction_mult": 0.65,
        "business_downside_mult": 0.70,
        "small_win_boost_add": 0.08,
    },
    "early_growth": {
        "shock_severity_mult": 0.75,
        "credit_penalty_mult": 0.80,
        "borrowing_harshness_mult": 0.85,
        "competition_friction_mult": 0.80,
        "business_downside_mult": 0.82,
        "small_win_boost_add": 0.04,
    },
    "stabilization": {
        "shock_severity_mult": 0.90,
        "credit_penalty_mult": 0.92,
        "borrowing_harshness_mult": 0.95,
        "competition_friction_mult": 0.92,
        "business_downside_mult": 0.95,
        "small_win_boost_add": 0.01,
    },
    "pressure": {
        "shock_severity_mult": 1.00,
        "credit_penalty_mult": 1.00,
        "borrowing_harshness_mult": 1.00,
        "competition_friction_mult": 1.00,
        "business_downside_mult": 1.00,
        "small_win_boost_add": 0.00,
    },
    "full_sim": {
        "shock_severity_mult": 1.00,
        "credit_penalty_mult": 1.00,
        "borrowing_harshness_mult": 1.00,
        "competition_friction_mult": 1.00,
        "business_downside_mult": 1.00,
        "small_win_boost_add": 0.00,
    },
}

# Wealth phase thresholds
DELINQUENCY_STAGES = ("current", "stretched", "late", "delinquent", "critical")
STAGE_INDEX: dict[str, int] = {s: i for i, s in enumerate(DELINQUENCY_STAGES)}

SPIRAL_SEVERITY: dict[str, int] = {
    "low": 0,
    "rising": 1,
    "high": 2,
    "critical": 3,
}

# All valid wealth action keys
WEALTH_ACTIONS = (
    "hold_cash",
    "save_cash",
    "buy_stocks",
    "reinvest_business",
    "pay_debt",
    "delay_wealth_move",
)

# Action evaluation labels
ACTION_LABELS = ("premature", "cautious", "reasonable", "aggressive", "reckless")

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WealthProgressionError(Exception):
    """Base Step 39 error."""


class WealthProgressionNotFoundError(WealthProgressionError):
    """Raised when player or required state is missing."""


class WealthProgressionValidationError(WealthProgressionError):
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
        raise WealthProgressionNotFoundError("Player not found.") from exc

    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise WealthProgressionNotFoundError("Player not found.")
    return row


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise WealthProgressionValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise WealthProgressionValidationError("as_of_date must be on or after game epoch.")
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


def _get_delinquency_state(db: Session, player_id: UUID) -> PlayerDelinquencyState | None:
    return db.query(PlayerDelinquencyState).filter(PlayerDelinquencyState.player_id == player_id).first()


def _get_borrowing_state(db: Session, player_id: UUID) -> PlayerBorrowingState | None:
    return db.query(PlayerBorrowingState).filter(PlayerBorrowingState.player_id == player_id).first()


def _get_shock_state(db: Session, player_id: UUID) -> PlayerShockState | None:
    return db.query(PlayerShockState).filter(PlayerShockState.player_id == player_id).first()


def _get_debt_behavior_state(db: Session, player_id: UUID) -> PlayerDebtBehaviorState | None:
    return db.query(PlayerDebtBehaviorState).filter(PlayerDebtBehaviorState.player_id == player_id).first()


def _active_loans(db: Session, player_id: UUID) -> list[PlayerLoanAccount]:
    try:
        return (
            db.query(PlayerLoanAccount)
            .filter(
                PlayerLoanAccount.player_id == player_id,
                PlayerLoanAccount.status.in_(["active", "delinquent"]),
            )
            .all()
        )
    except Exception:
        return []


def _active_holdings(db: Session, player_id: UUID) -> list[PlayerStockHolding]:
    try:
        return (
            db.query(PlayerStockHolding)
            .filter(
                PlayerStockHolding.player_id == player_id,
                PlayerStockHolding.shares_owned > 0,
            )
            .all()
        )
    except Exception:
        return []


def _stock_price(db: Session, stock_id: str) -> Decimal:
    row = db.query(SectorStock).filter(SectorStock.stock_id == stock_id).first()
    if row is None:
        return Decimal("0")
    return _d(row.current_price)


def _active_businesses(db: Session, player_id: UUID) -> list[PlayerBusiness]:
    try:
        return (
            db.query(PlayerBusiness)
            .filter(PlayerBusiness.player_id == player_id)
            .all()
        )
    except Exception:
        return []


def _recent_business_logs(db: Session, player_id: UUID, day: int, window: int = 30) -> list[BusinessDailyLog]:
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


def _recent_wealth_history(db: Session, player_id: UUID, day: int, n: int = 14) -> list[PlayerWealthTrendHistory]:
    """Return up to n recent history rows BEFORE current day (excludes current eval day)."""
    try:
        return (
            db.query(PlayerWealthTrendHistory)
            .filter(
                PlayerWealthTrendHistory.player_id == player_id,
                PlayerWealthTrendHistory.day < int(day),
            )
            .order_by(PlayerWealthTrendHistory.day.desc())
            .limit(n)
            .all()
        )
    except Exception:
        return []


def _compute_experience_phase(player: Player, current_day: int) -> tuple[str, int, bool]:
    """Return (phase_name, days_in_phase, softening_active)."""
    created = player.account_created_day
    if created is None:
        created = 1
    days_elapsed = max(1, int(current_day) - int(created) + 1)

    phase = "full_sim"
    for p, (lo, hi) in EXPERIENCE_PHASE_TRANSITIONS.items():
        if lo <= days_elapsed <= hi:
            phase = p
            days_in_phase = days_elapsed - lo + 1
            softening = phase in ("onboarding", "early_growth", "stabilization")
            return phase, days_in_phase, softening

    # full_sim
    days_in_phase = days_elapsed - 181 + 1
    return "full_sim", max(1, days_in_phase), False


def _compute_market_asset_value(db: Session, player_id: UUID) -> Decimal:
    holdings = _active_holdings(db, player_id)
    total = Decimal("0")
    for h in holdings:
        price = _stock_price(db, h.stock_id)
        total += _d(h.shares_owned) * price
    return _q4(total)


def _compute_business_equity(db: Session, player_id: UUID, day: int) -> tuple[Decimal, bool]:
    """Return (business_equity_xgp, has_strong_business_trend)."""
    businesses = _active_businesses(db, player_id)
    if not businesses:
        return Decimal("0"), False

    logs = _recent_business_logs(db, player_id, day, 14)
    profitable_count = sum(1 for lg in logs if _d(lg.net_profit_xgp) > 0)
    strong_trend = len(logs) >= 7 and profitable_count >= int(len(logs) * 0.7)

    total_equity = Decimal("0")
    for biz in businesses:
        invested = _d(biz.cash_invested_xgp)
        reserve = _d(biz.cash_reserve_xgp or 0)
        # Profit multiplier from recent logs (simple 30-day proxy)
        biz_logs = [lg for lg in logs if lg.business_id == biz.id]
        if biz_logs:
            avg_daily_profit = sum(_d(lg.net_profit_xgp) for lg in biz_logs) / len(biz_logs)
            # Only count positive profit contribution to equity
            profit_value = _clamp(avg_daily_profit * 30, Decimal("0"), Decimal("10000"))
        else:
            profit_value = Decimal("0")
        # Equity = invested capital + cash reserve + modest profit proxy
        equity = invested + reserve + (profit_value * Decimal("0.5"))
        total_equity += _clamp(equity, Decimal("0"), Decimal("99999"))

    return _q4(total_equity), strong_trend


def _compute_daily_obligations(player: Player, loans: list[PlayerLoanAccount]) -> Decimal:
    """Estimate total daily financial obligations (debt payments + baseline survival)."""
    loan_daily = _d(player.required_daily_debt_payment_xgp)
    # Add any missed delinquency overhang
    for loan in loans:
        if hasattr(loan, "current_due_xgp") and _d(loan.current_due_xgp) > _d(loan.scheduled_daily_payment_xgp):
            overhang = _d(loan.current_due_xgp) - _d(loan.scheduled_daily_payment_xgp)
            loan_daily += overhang / Decimal("7")  # spread over a week
    # Minimum daily survival estimate (food + essentials)
    survival_floor = Decimal("15")
    return _q4(max(loan_daily, survival_floor))


def _compute_debt_drag(player: Player, loans: list[PlayerLoanAccount]) -> Decimal:
    """Compute 30-day debt servicing drag from active loans."""
    drag = Decimal("0")
    for loan in loans:
        outstanding = _d(loan.principal_outstanding_xgp)
        daily_payment = _d(loan.scheduled_daily_payment_xgp)
        drag += daily_payment * 30
    # Also include player-level debt
    drag += _d(player.required_daily_debt_payment_xgp) * 30
    return _q4(_clamp(drag, Decimal("0"), Decimal("999999")))


def _compute_total_debt(player: Player, loans: list[PlayerLoanAccount]) -> Decimal:
    """Total outstanding principal across all active loans + player debt."""
    loan_total = sum((_d(ln.principal_outstanding_xgp) for ln in loans), Decimal("0"))
    player_debt = _d(player.debt_xgp)
    return _q4(max(loan_total, player_debt))


def _compute_investable_surplus(
    liquid: Decimal,
    daily_obligations: Decimal,
    buffer_days: Decimal,
    delinquency_stage: str,
) -> Decimal:
    """Compute investable surplus: what the player could safely move to growth."""
    # Buffer target = recommended buffer days × daily obligations
    recommended_buffer = BUFFER_DAYS_INVEST_THRESHOLD * daily_obligations
    # Minimum emergency reserve is always protected
    protected = recommended_buffer + MINIMUM_EMERGENCY_RESERVE
    surplus = liquid - protected
    if surplus <= Decimal("0"):
        return Decimal("0")
    # Distressed players get a tighter limit
    stage_idx = STAGE_INDEX.get(delinquency_stage, 0)
    if stage_idx >= STAGE_INDEX.get("late", 2):
        return Decimal("0")
    if stage_idx >= STAGE_INDEX.get("stretched", 1):
        surplus = surplus * Decimal("0.3")
    else:
        surplus = surplus * Decimal("0.5")  # never invest all surplus
    return _q4(_clamp(surplus, Decimal("0"), liquid * Decimal("0.6")))


def _compute_stability_score(
    buffer_days: Decimal,
    delinquency_stage: str,
    spiral_label: str,
    shock_risk: Decimal,
) -> Decimal:
    """Compute stability-before-growth score (0–100)."""
    score = Decimal("50")

    # buffer_days contribution
    if buffer_days >= 21:
        score += Decimal("20")
    elif buffer_days >= 14:
        score += Decimal("12")
    elif buffer_days >= 7:
        score += Decimal("4")
    elif buffer_days < 3:
        score -= Decimal("20")
    else:
        score -= Decimal("10")

    # delinquency stage penalty
    stage_idx = STAGE_INDEX.get(delinquency_stage, 0)
    score -= Decimal(str(stage_idx * 10))

    # spiral penalty
    spiral_sev = SPIRAL_SEVERITY.get(spiral_label, 0)
    score -= Decimal(str(spiral_sev * 8))

    # shock risk penalty
    score -= shock_risk * Decimal("0.2")

    return _clamp(_q4(score), Decimal("0"), Decimal("100"))


def _compute_wealth_momentum(
    net_worth: Decimal,
    buffer_days: Decimal,
    spiral_label: str,
    recovery_stage: str,
    debt_drag: Decimal,
    total_assets: Decimal,
    strong_business_trend: bool,
    market_value: Decimal,
) -> Decimal:
    """Compute wealth momentum score (0–100)."""
    score = Decimal("40")

    # Net worth positive contribution
    if net_worth > Decimal("5000"):
        score += Decimal("15")
    elif net_worth > Decimal("2000"):
        score += Decimal("10")
    elif net_worth > Decimal("0"):
        score += Decimal("5")
    elif net_worth < Decimal("-1000"):
        score -= Decimal("20")
    else:
        score -= Decimal("10")

    # Buffer health
    if buffer_days >= 21:
        score += Decimal("15")
    elif buffer_days >= 14:
        score += Decimal("8")
    elif buffer_days >= 7:
        score += Decimal("3")
    else:
        score -= Decimal("8")

    # Spiral label effect
    sev = SPIRAL_SEVERITY.get(spiral_label, 0)
    if sev == 0:  # low
        score += Decimal("8")
    elif sev == 1:  # rising
        score += Decimal("0")
    elif sev == 2:  # high
        score -= Decimal("12")
    else:           # critical
        score -= Decimal("25")

    # Recovery stage boost
    recovery_boosts = {"none": 0, "early": 3, "stabilizing": 7, "rebuilding": 12, "strong": 18}
    score += Decimal(str(recovery_boosts.get(recovery_stage, 0)))

    # Business trend boost
    if strong_business_trend:
        score += Decimal("5")

    # Market investment contribution
    if market_value > Decimal("2000"):
        score += Decimal("5")
    elif market_value > Decimal("500"):
        score += Decimal("2")

    # Debt drag penalty
    if total_assets > Decimal("0"):
        drag_ratio = _clamp(debt_drag / total_assets, Decimal("0"), Decimal("1"))
        score -= drag_ratio * Decimal("15")

    return _clamp(_q4(score), Decimal("0"), Decimal("100"))


def _determine_wealth_phase(
    stability_score: Decimal,
    momentum_score: Decimal,
    spiral_label: str,
    delinquency_stage: str,
    business_equity: Decimal,
    market_value: Decimal,
    investable_surplus: Decimal,
    total_debt: Decimal,
    liquid: Decimal,
) -> str:
    """Return wealth_phase_label: fragile | stabilizing | growing | compounding | overextended."""
    stage_idx = STAGE_INDEX.get(delinquency_stage, 0)
    sev = SPIRAL_SEVERITY.get(spiral_label, 0)

    # Overextended: technically positive NW but liquidity hollowed out by debt
    if investable_surplus < Decimal("0") and total_debt > liquid * Decimal("0.8"):
        return "overextended"

    # Fragile: severe delinquency or critical spiral or very low stability
    if stage_idx >= STAGE_INDEX.get("delinquent", 3) or sev >= 3 or stability_score < 25:
        return "fragile"

    # Stabilizing: escaping fragile, building buffer, not yet growing
    if stability_score < 55 or momentum_score < 50:
        return "stabilizing"

    # Compounding: strong stability + momentum + meaningful assets
    if (
        stability_score >= 75
        and momentum_score >= 70
        and (business_equity > Decimal("1000") or market_value > Decimal("500"))
    ):
        return "compounding"

    # Growing: stable enough, positive momentum
    if stability_score >= 55 and momentum_score >= 50:
        return "growing"

    return "stabilizing"


def _compute_safe_labels(
    buffer_days: Decimal,
    spiral_label: str,
    delinquency_stage: str,
    investable_surplus: Decimal,
) -> tuple[str, str]:
    """Return (safe_to_save_label, safe_to_invest_label)."""
    stage_idx = STAGE_INDEX.get(delinquency_stage, 0)
    sev = SPIRAL_SEVERITY.get(spiral_label, 0)

    # safe_to_save
    if stage_idx >= STAGE_INDEX.get("late", 2) or sev >= 3:
        safe_to_save = "not_safe"
    elif buffer_days >= BUFFER_DAYS_SAVE_THRESHOLD and stage_idx <= 1:
        if buffer_days >= 14:
            safe_to_save = "strongly_recommended"
        else:
            safe_to_save = "safe"
    elif buffer_days >= 3:
        safe_to_save = "cautious"
    else:
        safe_to_save = "not_safe"

    # safe_to_invest
    if stage_idx >= STAGE_INDEX.get("stretched", 1) or sev >= 2:
        safe_to_invest = "not_safe"
    elif investable_surplus <= Decimal("0"):
        safe_to_invest = "premature"
    elif investable_surplus > Decimal("0") and buffer_days >= BUFFER_DAYS_INVEST_THRESHOLD:
        if sev == 0 and stage_idx == 0 and buffer_days >= 21:
            safe_to_invest = "reasonable"
        else:
            safe_to_invest = "cautious"
    else:
        safe_to_invest = "premature"

    return safe_to_save, safe_to_invest


def _compute_asset_growth_trend(history: list[PlayerWealthTrendHistory]) -> str:
    """Compare recent vs older total_asset_value to determine trend direction."""
    if len(history) < 3:
        return "stable"
    recent = history[:3]
    older = history[3:] if len(history) > 3 else history[:1]
    if not older:
        return "stable"
    avg_recent = sum(_d(r.total_asset_value_xgp) for r in recent) / len(recent)
    avg_older = sum(_d(r.total_asset_value_xgp) for r in older) / len(older)
    delta = avg_recent - avg_older
    if delta > Decimal("100"):
        return "improving"
    if delta < Decimal("-100"):
        return "deteriorating"
    return "stable"


def _detect_false_growth(
    net_worth: Decimal,
    debt_drag: Decimal,
    investable_surplus: Decimal,
    spiral_label: str,
    borrowing_state: PlayerBorrowingState | None,
    business_logs: list[BusinessDailyLog],
    history: list[PlayerWealthTrendHistory],
) -> tuple[bool, list[str]]:
    """Detect false-growth patterns. Returns (is_false_growth, warning_list)."""
    warnings: list[str] = []
    sev = SPIRAL_SEVERITY.get(spiral_label, 0)

    # Pattern 1: borrowing masking growth
    if borrowing_state is not None:
        repeat_borrow = int(borrowing_state.repeat_borrowing_count_30d or 0)
        if repeat_borrow >= 3 and net_worth > Decimal("0"):
            warnings.append(
                "Growth appears to be financed by repeated borrowing, not durable wealth accumulation."
            )

    # Pattern 2: strong business revenue but spiral risk is elevated
    if business_logs:
        recent_profit = sum(_d(lg.net_profit_xgp) for lg in business_logs[:7])
        if recent_profit > Decimal("200") and sev >= 2:
            warnings.append(
                "Business revenue looks strong, but debt spiral risk is elevated — do not confuse revenue with wealth."
            )

    # Pattern 3: net worth rising but investable surplus gone
    if net_worth > Decimal("500") and investable_surplus <= Decimal("0"):
        warnings.append(
            "Net worth appears positive, but no investable surplus remains — growth may be fragile."
        )

    # Pattern 4: trend history shows debt drag growing faster than net worth
    if len(history) >= 3:
        old_nw = _d(history[-1].net_worth_xgp)
        old_drag = _d(history[-1].debt_drag_xgp)
        nw_growth = net_worth - old_nw
        drag_growth = debt_drag - old_drag
        if drag_growth > nw_growth and drag_growth > Decimal("50"):
            warnings.append(
                "Your net worth may be improving, but your debt burden is growing faster — growth is being financed by rising fragility."
            )

    # Pattern 5: asset value rising but liquidity deteriorating
    if len(history) >= 3:
        old_surplus = _d(history[-1].investable_surplus_xgp)
        if old_surplus > investable_surplus and net_worth > old_nw if history else False:
            warnings.append(
                "Asset value is rising, but available liquidity is weakening — expansion may be creating false progress."
            )

    return len(warnings) > 0, warnings


def _generate_planning_insights(
    wealth_phase: str,
    safe_to_save: str,
    safe_to_invest: str,
    spiral_label: str,
    recovery_stage: str,
    buffer_days: Decimal,
    false_growth: bool,
    strong_business_trend: bool,
    market_value: Decimal,
) -> list[str]:
    insights: list[str] = []

    if wealth_phase == "fragile":
        insights.append("Focus on stabilizing obligations before considering any growth moves.")
    elif wealth_phase == "stabilizing":
        insights.append("You are stabilizing, but not ready for aggressive growth.")
    elif wealth_phase == "growing":
        insights.append("You are building momentum — prioritise durable assets over speculative moves.")
    elif wealth_phase == "compounding":
        insights.append("Your wealth is compounding — protect the foundation that got you here.")
    elif wealth_phase == "overextended":
        insights.append("You are overextended — reduce debt obligations before expanding assets.")

    if false_growth:
        insights.append("Your current growth is mostly revenue, not durable wealth.")

    if safe_to_invest == "not_safe" or safe_to_invest == "premature":
        if buffer_days < BUFFER_DAYS_INVEST_THRESHOLD:
            insights.append(
                "A larger emergency buffer may improve long-term wealth more than a risky investment right now."
            )

    if spiral_label in ("high", "critical"):
        insights.append("Your debt burden is weakening the quality of your progress.")

    if recovery_stage in ("rebuilding", "strong"):
        insights.append("Financial stabilization is unlocking stronger wealth-building capacity.")

    if strong_business_trend and safe_to_invest in ("cautious", "reasonable"):
        insights.append("Strong business performance is improving wealth momentum — protect this trend.")

    if market_value > Decimal("500"):
        insights.append("Stock holdings are contributing to your asset progression — monitor sector trends.")

    return insights


def _upsert_wealth_trend_row(
    db: Session,
    player_id: UUID,
    day: int,
    as_of_date: date,
    data: dict,
) -> None:
    """Upsert a PlayerWealthTrendHistory row for player×day."""
    existing = (
        db.query(PlayerWealthTrendHistory)
        .filter(
            PlayerWealthTrendHistory.player_id == player_id,
            PlayerWealthTrendHistory.day == int(day),
        )
        .first()
    )
    if existing is None:
        row = PlayerWealthTrendHistory(
            player_id=player_id,
            day=int(day),
            as_of_date=as_of_date,
            **data,
        )
        db.add(row)
    else:
        for k, v in data.items():
            setattr(existing, k, v)


def _upsert_wealth_state(
    db: Session,
    player_id: UUID,
    day: int,
    as_of_date: date,
    data: dict,
) -> PlayerWealthState:
    """Upsert rolling PlayerWealthState for player."""
    existing = (
        db.query(PlayerWealthState)
        .filter(PlayerWealthState.player_id == player_id)
        .first()
    )
    if existing is None:
        existing = PlayerWealthState(player_id=player_id, **data)
        db.add(existing)
    else:
        for k, v in data.items():
            setattr(existing, k, v)
        existing.last_updated_on = int(day)
        existing.last_updated_date = as_of_date
    return existing


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------


def build_wealth_profile(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Compute and persist the player's full wealth profile.

    Reads: Player, loans, holdings, businesses, delinquency, borrowing,
           debt behavior, shock state.
    Writes: PlayerWealthState (upsert), PlayerWealthTrendHistory (upsert).
    Returns: dict with all profile fields.
    """
    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    # --- Load supporting state ---
    loans = _active_loans(db, pid)
    delin = _get_delinquency_state(db, pid)
    borrow = _get_borrowing_state(db, pid)
    shock = _get_shock_state(db, pid)
    debt_beh = _get_debt_behavior_state(db, pid)
    history = _recent_wealth_history(db, pid, day, 14)
    biz_logs = _recent_business_logs(db, pid, day, 30)

    delinquency_stage = delin.current_delinquency_stage if delin else "current"
    spiral_label = debt_beh.spiral_risk_label if debt_beh else "low"
    recovery_stage = debt_beh.recovery_stage if debt_beh else "none"
    shock_risk = _d(shock.shock_risk_score if shock else 0)

    # --- Core values ---
    cash = _d(player.cash)
    savings = _d(player.bank_savings_xgp)
    liquid = _q4(cash + savings)
    total_debt = _compute_total_debt(player, loans)
    daily_obligations = _compute_daily_obligations(player, loans)

    # buffer days: how many days current liquid covers obligations
    if daily_obligations > Decimal("0"):
        buffer_days_val = _clamp(_q4(liquid / daily_obligations), Decimal("0"), Decimal("999"))
    else:
        buffer_days_val = Decimal("30")  # no obligations → ample buffer

    market_value = _compute_market_asset_value(db, pid)
    business_equity, strong_business = _compute_business_equity(db, pid, day)
    total_assets = _q4(liquid + market_value + business_equity)
    debt_drag = _compute_debt_drag(player, loans)
    net_worth = _q4(total_assets - total_debt)
    investable = _compute_investable_surplus(liquid, daily_obligations, buffer_days_val, delinquency_stage)

    # --- Computed scores ---
    stability_score = _compute_stability_score(buffer_days_val, delinquency_stage, spiral_label, shock_risk)
    momentum_score = _compute_wealth_momentum(
        net_worth, buffer_days_val, spiral_label, recovery_stage,
        debt_drag, total_assets, strong_business, market_value,
    )

    # Experience phase
    phase, days_in_phase, softening = _compute_experience_phase(player, day)

    # Apply softening to stability/momentum in early phases
    if softening and phase in ("onboarding", "early_growth"):
        mods = SOFTENING_MODIFIERS[phase]
        # In early phase, boost momentum slightly (small wins feel real)
        momentum_score = _clamp(
            momentum_score + Decimal(str(mods["small_win_boost_add"])) * 100,
            Decimal("0"), Decimal("100"),
        )

    # --- Phase and labels ---
    wealth_phase = _determine_wealth_phase(
        stability_score, momentum_score, spiral_label, delinquency_stage,
        business_equity, market_value, investable, total_debt, liquid,
    )
    safe_to_save, safe_to_invest = _compute_safe_labels(
        buffer_days_val, spiral_label, delinquency_stage, investable,
    )
    asset_trend = _compute_asset_growth_trend(history)

    # --- Drivers ---
    growth_drivers = []
    drag_drivers = []
    if market_value > Decimal("500"):
        growth_drivers.append("stock holdings")
    if strong_business:
        growth_drivers.append("business performance")
    if savings > Decimal("500"):
        growth_drivers.append("savings reserve")
    if debt_drag > Decimal("200"):
        drag_drivers.append("loan payment obligations")
    if spiral_label in ("high", "critical"):
        drag_drivers.append("debt spiral risk")
    if STAGE_INDEX.get(delinquency_stage, 0) >= 2:
        drag_drivers.append("delinquency stage")
    top_growth = ", ".join(growth_drivers[:2]) if growth_drivers else "none identified"
    top_drag = ", ".join(drag_drivers[:2]) if drag_drivers else "none identified"

    # --- False-growth detection ---
    false_growth, fg_warnings = _detect_false_growth(
        net_worth, debt_drag, investable, spiral_label, borrow, biz_logs, history,
    )

    # --- Planning insights ---
    insights = _generate_planning_insights(
        wealth_phase, safe_to_save, safe_to_invest, spiral_label, recovery_stage,
        buffer_days_val, false_growth, strong_business, market_value,
    )

    # --- Build state payload ---
    state_data = dict(
        cash_reserve_xgp=_q4(cash),
        savings_reserve_xgp=_q4(savings),
        investable_surplus_xgp=investable,
        debt_drag_xgp=debt_drag,
        net_worth_xgp=net_worth,
        liquid_asset_value_xgp=liquid,
        market_asset_value_xgp=market_value,
        business_equity_xgp=business_equity,
        total_asset_value_xgp=total_assets,
        total_debt_xgp=total_debt,
        wealth_momentum_score=momentum_score,
        stability_before_growth_score=stability_score,
        buffer_days=buffer_days_val,
        wealth_phase_label=wealth_phase,
        asset_growth_trend=asset_trend,
        safe_to_save_label=safe_to_save,
        safe_to_invest_label=safe_to_invest,
        experience_phase=phase,
        days_in_phase=int(days_in_phase),
        softening_active=softening,
        top_growth_driver=top_growth,
        top_drag_driver=top_drag,
        false_growth_detected=false_growth,
        false_growth_warnings_json=_dump_json(fg_warnings) if fg_warnings else None,
        planning_insights_json=_dump_json(insights) if insights else None,
        debug_json=_dump_json({
            "daily_obligations": _to_float(daily_obligations),
            "buffer_days": _to_float(buffer_days_val),
            "delinquency_stage": delinquency_stage,
            "spiral_label": spiral_label,
            "recovery_stage": recovery_stage,
            "shock_risk": _to_float(shock_risk),
            "loan_count": len(loans),
            "strong_business_trend": strong_business,
            "phase": phase,
        }),
        last_updated_on=day,
        last_updated_date=as_of_date,
    )

    # --- Persist ---
    _upsert_wealth_state(db, pid, day, as_of_date, state_data)
    _upsert_wealth_trend_row(db, pid, day, as_of_date, {
        "net_worth_xgp": net_worth,
        "total_asset_value_xgp": total_assets,
        "total_debt_xgp": total_debt,
        "debt_drag_xgp": debt_drag,
        "investable_surplus_xgp": investable,
        "market_asset_value_xgp": market_value,
        "business_equity_xgp": business_equity,
        "wealth_momentum_score": momentum_score,
        "stability_before_growth_score": stability_score,
        "buffer_days": buffer_days_val,
        "wealth_phase_label": wealth_phase,
        "asset_growth_trend": asset_trend,
        "experience_phase": phase,
        "false_growth_flag": false_growth,
    })
    db.flush()

    return dict(
        player_id=str(pid),
        day_number=day,
        as_of_date=str(as_of_date),
        cash_reserve_xgp=_to_float(cash),
        savings_reserve_xgp=_to_float(savings),
        investable_surplus_xgp=_to_float(investable),
        debt_drag_xgp=_to_float(debt_drag),
        net_worth_xgp=_to_float(net_worth),
        liquid_asset_value_xgp=_to_float(liquid),
        market_asset_value_xgp=_to_float(market_value),
        business_equity_xgp=_to_float(business_equity),
        total_asset_value_xgp=_to_float(total_assets),
        total_debt_xgp=_to_float(total_debt),
        wealth_momentum_score=_to_float(momentum_score),
        stability_before_growth_score=_to_float(stability_score),
        buffer_days=_to_float(buffer_days_val),
        wealth_phase_label=wealth_phase,
        asset_growth_trend=asset_trend,
        safe_to_save_label=safe_to_save,
        safe_to_invest_label=safe_to_invest,
        experience_phase=phase,
        days_in_phase=int(days_in_phase),
        softening_active=softening,
        top_growth_driver=top_growth,
        top_drag_driver=top_drag,
        false_growth_detected=false_growth,
        false_growth_warnings=fg_warnings,
        planning_insights=insights,
        debug_meta={
            "daily_obligations": _to_float(daily_obligations),
            "delinquency_stage": delinquency_stage,
            "spiral_label": spiral_label,
            "recovery_stage": recovery_stage,
            "loan_count": len(loans),
        },
    )


def build_savings_capacity_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Determine whether the player should save, invest cautiously, or stabilise first.

    This function tells the truth: some players should save first,
    some can invest, some should stabilise before chasing growth.
    """
    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    loans = _active_loans(db, pid)
    delin = _get_delinquency_state(db, pid)
    debt_beh = _get_debt_behavior_state(db, pid)

    cash = _d(player.cash)
    savings = _d(player.bank_savings_xgp)
    liquid = cash + savings
    delinquency_stage = delin.current_delinquency_stage if delin else "current"
    spiral_label = debt_beh.spiral_risk_label if debt_beh else "low"
    daily_obligations = _compute_daily_obligations(player, loans)

    if daily_obligations > Decimal("0"):
        current_buf = _clamp(_q4(liquid / daily_obligations), Decimal("0"), Decimal("999"))
    else:
        current_buf = Decimal("30")

    # Recommended buffer based on risk level
    stage_idx = STAGE_INDEX.get(delinquency_stage, 0)
    if stage_idx >= 2 or SPIRAL_SEVERITY.get(spiral_label, 0) >= 2:
        recommended = Decimal("21")
    elif stage_idx == 1:
        recommended = Decimal("14")
    else:
        recommended = Decimal("7")

    investable = _compute_investable_surplus(liquid, daily_obligations, current_buf, delinquency_stage)
    safe_to_save, safe_to_invest = _compute_safe_labels(current_buf, spiral_label, delinquency_stage, investable)

    # Excess cash label
    if current_buf >= 30:
        excess_label = "flush"
    elif current_buf >= 21:
        excess_label = "comfortable"
    elif current_buf >= 14:
        excess_label = "adequate"
    elif current_buf >= 7:
        excess_label = "tight"
    else:
        excess_label = "stressed"

    # Short summary
    if safe_to_save == "not_safe":
        summary = "Stabilise obligations before directing cash to savings."
    elif safe_to_invest in ("not_safe", "premature"):
        summary = "Building savings is appropriate now; invest only after buffer is secure."
    elif safe_to_invest == "cautious":
        summary = "Buffer is adequate for cautious first-investment steps."
    else:
        summary = "Buffer and stability support measured growth moves."

    return dict(
        player_id=str(pid),
        day_number=day,
        as_of_date=str(as_of_date),
        safe_to_save_label=safe_to_save,
        safe_to_invest_label=safe_to_invest,
        recommended_buffer_days=_to_float(recommended),
        current_buffer_days=_to_float(current_buf),
        daily_obligations_xgp=_to_float(daily_obligations),
        investable_surplus_xgp=_to_float(investable),
        excess_cash_label=excess_label,
        short_summary=summary,
        debug_meta={
            "delinquency_stage": delinquency_stage,
            "spiral_label": spiral_label,
            "liquid_xgp": _to_float(liquid),
        },
    )


def build_asset_progression_state(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Track player asset growth in a bounded, explainable way.

    Includes: liquid assets, market assets, business equity, total assets,
    growth trend, and asset quality label.
    """
    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    loans = _active_loans(db, pid)
    history = _recent_wealth_history(db, pid, day, 14)

    cash = _d(player.cash)
    savings = _d(player.bank_savings_xgp)
    liquid = _q4(cash + savings)
    market_value = _compute_market_asset_value(db, pid)
    business_equity, strong_business = _compute_business_equity(db, pid, day)
    total_assets = _q4(liquid + market_value + business_equity)
    total_debt = _compute_total_debt(player, loans)

    asset_trend = _compute_asset_growth_trend(history)

    # Asset quality label: how much of total assets is liquid vs locked
    if total_assets <= Decimal("0"):
        quality_label = "no_assets"
    else:
        liquid_ratio = liquid / total_assets
        market_ratio = market_value / total_assets
        if liquid_ratio >= Decimal("0.7"):
            quality_label = "liquid_heavy"  # very accessible but low growth
        elif market_ratio >= Decimal("0.5"):
            quality_label = "market_weighted"  # good growth potential
        elif business_equity > total_assets * Decimal("0.5"):
            quality_label = "business_weighted"  # tied to business performance
        else:
            quality_label = "balanced"

    # Diversification score (simple)
    asset_types = sum([
        1 if liquid > Decimal("200") else 0,
        1 if market_value > Decimal("100") else 0,
        1 if business_equity > Decimal("100") else 0,
    ])
    diversification = {0: "none", 1: "minimal", 2: "moderate", 3: "diversified"}[asset_types]

    # Asset-to-debt ratio
    if total_debt > Decimal("0"):
        adr = _to_float(_clamp(_q4(total_assets / total_debt), Decimal("0"), Decimal("100")))
    else:
        adr = 99.0

    return dict(
        player_id=str(pid),
        day_number=day,
        as_of_date=str(as_of_date),
        liquid_asset_value_xgp=_to_float(liquid),
        market_asset_value_xgp=_to_float(market_value),
        business_equity_xgp=_to_float(business_equity),
        total_asset_value_xgp=_to_float(total_assets),
        total_debt_xgp=_to_float(total_debt),
        asset_growth_trend=asset_trend,
        asset_quality_label=quality_label,
        diversification_label=diversification,
        asset_to_debt_ratio=adr,
        strong_business_trend=strong_business,
        debug_meta={
            "liquid_ratio": _to_float(liquid / total_assets) if total_assets > 0 else 0.0,
        },
    )


def evaluate_wealth_actions(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Evaluate each possible wealth action for the current player state.

    Returns a dict mapping action_key → evaluation_label + reasoning.
    """
    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    loans = _active_loans(db, pid)
    delin = _get_delinquency_state(db, pid)
    debt_beh = _get_debt_behavior_state(db, pid)

    cash = _d(player.cash)
    savings = _d(player.bank_savings_xgp)
    liquid = cash + savings
    delinquency_stage = delin.current_delinquency_stage if delin else "current"
    spiral_label = debt_beh.spiral_risk_label if debt_beh else "low"
    stage_idx = STAGE_INDEX.get(delinquency_stage, 0)
    sev = SPIRAL_SEVERITY.get(spiral_label, 0)
    daily_obligations = _compute_daily_obligations(player, loans)
    buf = _clamp(liquid / daily_obligations, Decimal("0"), Decimal("999")) if daily_obligations > 0 else Decimal("30")
    investable = _compute_investable_surplus(liquid, daily_obligations, buf, delinquency_stage)
    total_debt = _compute_total_debt(player, loans)

    evaluations = []

    def _eval(action: str, label: str, reason: str) -> dict:
        return {"action_key": action, "evaluation_label": label, "reasoning": reason}

    # hold_cash
    if stage_idx >= 2 or sev >= 2:
        evaluations.append(_eval("hold_cash", "reasonable", "Holding cash is the safest move while obligations are under pressure."))
    elif buf < 7:
        evaluations.append(_eval("hold_cash", "reasonable", "Buffer is thin — holding cash improves resilience."))
    else:
        evaluations.append(_eval("hold_cash", "cautious", "Cash holding is safe but foregoes growth opportunity."))

    # save_cash
    if stage_idx >= 3:
        evaluations.append(_eval("save_cash", "premature", "Delinquency stage is too severe to redirect cash to savings."))
    elif buf >= 7 and stage_idx <= 1:
        evaluations.append(_eval("save_cash", "reasonable", "Building savings is appropriate at current stability level."))
    else:
        evaluations.append(_eval("save_cash", "cautious", "Savings is possible but keep obligations covered first."))

    # buy_stocks
    if sev >= 3 or stage_idx >= 2:
        evaluations.append(_eval("buy_stocks", "reckless", "Investing in stocks while in a debt spiral or severe delinquency is reckless."))
    elif investable <= Decimal("0"):
        evaluations.append(_eval("buy_stocks", "premature", "No investable surplus available — stabilise buffer before stock purchases."))
    elif buf >= 14 and sev == 0 and stage_idx == 0:
        evaluations.append(_eval("buy_stocks", "reasonable", "Buffer and stability support cautious stock investment."))
    elif buf >= 10:
        evaluations.append(_eval("buy_stocks", "cautious", "Stock purchase is possible but keep position sizes modest."))
    else:
        evaluations.append(_eval("buy_stocks", "premature", "Buffer needs to be larger before stock investment is advisable."))

    # reinvest_business
    businesses = _active_businesses(db, pid)
    if not businesses:
        evaluations.append(_eval("reinvest_business", "premature", "No active businesses to reinvest in."))
    elif sev >= 2 or stage_idx >= 2:
        evaluations.append(_eval("reinvest_business", "aggressive", "Reinvesting in business while debt pressure is high increases financial exposure."))
    elif investable > Decimal("200"):
        evaluations.append(_eval("reinvest_business", "reasonable", "Business reinvestment is reasonable with available surplus."))
    else:
        evaluations.append(_eval("reinvest_business", "cautious", "Modest reinvestment is possible but protect your cash buffer."))

    # pay_debt
    if total_debt <= Decimal("0"):
        evaluations.append(_eval("pay_debt", "premature", "No outstanding debt to pay."))
    elif sev >= 1 or stage_idx >= 1:
        evaluations.append(_eval("pay_debt", "reasonable", "Paying down debt reduces spiral risk and improves future wealth quality."))
    else:
        evaluations.append(_eval("pay_debt", "cautious", "Debt payoff is a solid stability move even when risk is low."))

    # delay_wealth_move
    if sev >= 2 or stage_idx >= 2 or buf < 7:
        evaluations.append(_eval("delay_wealth_move", "reasonable", "Survival risk is too high — delaying wealth moves is the prudent choice."))
    else:
        evaluations.append(_eval("delay_wealth_move", "cautious", "Delaying is safe but may slow wealth momentum in a stable environment."))

    return dict(
        player_id=str(pid),
        day_number=day,
        as_of_date=str(as_of_date),
        evaluations=evaluations,
        buffer_days=_to_float(buf),
        delinquency_stage=delinquency_stage,
        spiral_label=spiral_label,
        investable_surplus_xgp=_to_float(investable),
        debug_meta={
            "stage_idx": stage_idx,
            "spiral_sev": sev,
            "business_count": len(businesses),
        },
    )


def apply_wealth_growth_outcomes(
    db: Session,
    player_id: str | UUID,
    action_key: str,
    day: int | None = None,
    as_of_date: date | None = None,
    amount_xgp: float | None = None,
) -> dict:
    """Return projected wealth outcomes for a proposed action WITHOUT mutating player state.

    This is a read-only projection function — it does NOT transfer money.
    It tells the player what the wealth profile would look like AFTER the action.
    """
    if action_key not in WEALTH_ACTIONS:
        raise WealthProgressionValidationError(
            f"Invalid action_key '{action_key}'. Must be one of: {', '.join(WEALTH_ACTIONS)}."
        )

    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    loans = _active_loans(db, pid)
    delin = _get_delinquency_state(db, pid)
    debt_beh = _get_debt_behavior_state(db, pid)

    cash = _d(player.cash)
    savings = _d(player.bank_savings_xgp)
    liquid = cash + savings
    amount = _d(amount_xgp or 0)
    daily_obligations = _compute_daily_obligations(player, loans)
    delinquency_stage = delin.current_delinquency_stage if delin else "current"
    spiral_label = debt_beh.spiral_risk_label if debt_beh else "low"

    # Projected changes based on action
    projected_cash = cash
    projected_savings = savings
    projected_market = _compute_market_asset_value(db, pid)
    projected_debt = _compute_total_debt(player, loans)

    notes: list[str] = []

    if action_key == "hold_cash":
        notes.append("No change to wealth structure. Cash preserved for obligations.")

    elif action_key == "save_cash":
        move = min(amount if amount > 0 else cash * Decimal("0.2"), cash - daily_obligations * 7)
        move = _clamp(move, Decimal("0"), cash)
        if move > 0:
            projected_cash -= move
            projected_savings += move
            notes.append(f"Moving {_to_float(move):.2f} XGP to savings improves buffer quality.")
        else:
            notes.append("Insufficient cash above buffer minimum to move to savings safely.")

    elif action_key == "buy_stocks":
        invest = min(amount if amount > 0 else liquid * Decimal("0.1"), liquid * Decimal("0.3"))
        invest = _clamp(invest, Decimal("0"), liquid - daily_obligations * 14)
        if invest > 0:
            projected_cash -= invest
            projected_market += invest  # simplified projection
            notes.append(f"Allocating {_to_float(invest):.2f} XGP to stocks would improve market asset exposure.")
        else:
            notes.append("No investable surplus available for stock purchase at this time.")

    elif action_key == "reinvest_business":
        reinvest = min(amount if amount > 0 else liquid * Decimal("0.15"), liquid * Decimal("0.3"))
        reinvest = _clamp(reinvest, Decimal("0"), liquid - daily_obligations * 14)
        if reinvest > 0:
            projected_cash -= reinvest
            notes.append(f"Reinvesting {_to_float(reinvest):.2f} XGP into business increases equity but ties up capital.")
        else:
            notes.append("Buffer too thin for business reinvestment at this time.")

    elif action_key == "pay_debt":
        pay = min(amount if amount > 0 else liquid * Decimal("0.2"), projected_debt)
        pay = _clamp(pay, Decimal("0"), liquid - daily_obligations * 7)
        if pay > 0:
            projected_cash -= pay
            projected_debt -= pay
            notes.append(f"Paying {_to_float(pay):.2f} XGP toward debt would reduce drag and improve momentum score.")
        else:
            notes.append("No safe amount available for extra debt payment right now.")

    elif action_key == "delay_wealth_move":
        notes.append("Delaying preserves current liquidity and avoids commitment risk.")

    projected_liquid = projected_cash + projected_savings
    projected_total_assets = projected_liquid + projected_market + _compute_business_equity(db, pid, day)[0]
    projected_nw = projected_total_assets - projected_debt

    return dict(
        player_id=str(pid),
        action_key=action_key,
        day_number=day,
        as_of_date=str(as_of_date),
        projected_cash_xgp=_to_float(projected_cash),
        projected_savings_xgp=_to_float(projected_savings),
        projected_liquid_xgp=_to_float(projected_liquid),
        projected_market_asset_xgp=_to_float(projected_market),
        projected_total_assets_xgp=_to_float(projected_total_assets),
        projected_net_worth_xgp=_to_float(projected_nw),
        projected_debt_xgp=_to_float(projected_debt),
        notes=notes,
        delinquency_stage=delinquency_stage,
        spiral_label=spiral_label,
    )


def build_net_worth_summary(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Build net worth summary with false-growth detection and wealth direction analysis.

    Distinguishes: real progress, fragile growth, false growth driven by debt or
    unstable business performance.
    """
    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    profile = build_wealth_profile(db, pid, day, as_of_date)
    history = _recent_wealth_history(db, pid, day, 14)

    net_worth = _d(profile["net_worth_xgp"])
    prev_nw = _d(history[0].net_worth_xgp) if history else Decimal("0")
    nw_delta = net_worth - prev_nw

    if len(history) >= 7:
        old_nw = _d(history[-1].net_worth_xgp)
        trend_delta = net_worth - old_nw
        if trend_delta > Decimal("200"):
            nw_direction = "improving"
        elif trend_delta < Decimal("-200"):
            nw_direction = "declining"
        else:
            nw_direction = "stable"
    else:
        nw_direction = "stable"

    false_growth = profile["false_growth_detected"]
    fg_warnings = profile["false_growth_warnings"]

    # Growth quality assessment
    if false_growth:
        growth_quality = "fragile"
    elif profile["wealth_phase_label"] in ("growing", "compounding"):
        growth_quality = "durable"
    elif profile["wealth_phase_label"] == "stabilizing":
        growth_quality = "building"
    else:
        growth_quality = "fragile"

    # Practical current actions
    practical = []
    if profile["safe_to_invest_label"] in ("not_safe", "premature"):
        practical.append("Focus on meeting obligations and building your buffer before growth moves.")
    if False in [False] and profile["debt_drag_xgp"] > profile["liquid_asset_value_xgp"] * 0.3:
        practical.append("Reduce debt drag as a priority — it is limiting wealth quality.")
    if profile["wealth_phase_label"] == "overextended":
        practical.append("You are overextended — avoid additional borrowing or expansion until debt reduces.")

    if not practical:
        if profile["wealth_phase_label"] in ("growing", "compounding"):
            practical.append("Maintain asset diversification and protect your savings buffer.")
        else:
            practical.append("Continue stabilising before pursuing additional growth.")

    # Debt drag vs assets
    drag = _d(profile["debt_drag_xgp"])
    total_assets = _d(profile["total_asset_value_xgp"])
    drag_ratio = _to_float(drag / total_assets) if total_assets > 0 else 0.0

    short_recommendation = (
        "Prioritise debt reduction to improve long-term net worth quality."
        if drag_ratio > 0.3 else
        "Maintain savings buffer and consider measured asset diversification."
        if profile["wealth_phase_label"] in ("stabilizing", "growing") else
        "Stabilise cash flow before committing to aggressive asset growth."
    )

    return dict(
        player_id=str(pid),
        day_number=day,
        as_of_date=str(as_of_date),
        net_worth_xgp=profile["net_worth_xgp"],
        net_worth_direction=nw_direction,
        net_worth_delta_xgp=_to_float(nw_delta),
        wealth_phase_label=profile["wealth_phase_label"],
        growth_quality_label=growth_quality,
        false_growth_detected=false_growth,
        false_growth_warnings=fg_warnings,
        top_growth_driver=profile["top_growth_driver"],
        top_drag_driver=profile["top_drag_driver"],
        debt_drag_xgp=profile["debt_drag_xgp"],
        debt_drag_ratio=drag_ratio,
        total_asset_value_xgp=profile["total_asset_value_xgp"],
        practical_current_actions=practical,
        short_recommendation=short_recommendation,
        planning_insights=profile["planning_insights"],
        debug_meta={
            "nw_delta": _to_float(nw_delta),
            "trend_days": len(history),
            "drag_ratio": drag_ratio,
        },
    )


def build_wealth_momentum_summary(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
    as_of_date: date | None = None,
) -> dict:
    """Build the full wealth momentum synthesis: all sub-components in one summary.

    This is the top-level summary endpoint that composes all sub-systems.
    """
    player = _resolve_player(db, player_id)
    pid: UUID = player.id

    if day is None and as_of_date is not None:
        day = _date_to_day(as_of_date)
    elif day is None:
        day, as_of_date = _resolve_day(db, player)
    else:
        as_of_date = _day_to_date(int(day))

    day = int(day)

    # Build all sub-components
    profile = build_wealth_profile(db, pid, day, as_of_date)
    savings_state = build_savings_capacity_state(db, pid, day, as_of_date)
    assets = build_asset_progression_state(db, pid, day, as_of_date)

    phase = profile["experience_phase"]
    mods = SOFTENING_MODIFIERS.get(phase, SOFTENING_MODIFIERS["full_sim"])

    # Experience phase advisory
    phase_advisory: list[str] = []
    if phase == "onboarding":
        phase_advisory.append("Early-game protections are active — financial consequences are softened while you learn.")
    elif phase == "early_growth":
        phase_advisory.append("You are in the early growth phase — most penalties are still moderated.")
    elif phase == "stabilization":
        phase_advisory.append("Stabilization phase — penalties are nearly full strength; build habits now.")
    elif phase in ("pressure", "full_sim"):
        phase_advisory.append("Full simulation rules apply — all mechanics are at standard strength.")

    history = _recent_wealth_history(db, pid, day, 14)

    # 7-day momentum direction
    if len(history) >= 7:
        recent_score = _d(history[0].wealth_momentum_score)
        older_score = _d(history[6].wealth_momentum_score)
        delta = recent_score - older_score
        if delta > Decimal("5"):
            momentum_direction = "accelerating"
        elif delta < Decimal("-5"):
            momentum_direction = "decelerating"
        else:
            momentum_direction = "steady"
    else:
        momentum_direction = "steady"

    return dict(
        player_id=str(pid),
        day_number=day,
        as_of_date=str(as_of_date),
        wealth_phase_label=profile["wealth_phase_label"],
        wealth_momentum_score=profile["wealth_momentum_score"],
        momentum_direction=momentum_direction,
        stability_before_growth_score=profile["stability_before_growth_score"],
        net_worth_xgp=profile["net_worth_xgp"],
        buffer_days=profile["buffer_days"],
        safe_to_save_label=profile["safe_to_save_label"],
        safe_to_invest_label=profile["safe_to_invest_label"],
        experience_phase=phase,
        days_in_phase=profile["days_in_phase"],
        softening_active=profile["softening_active"],
        softening_modifiers=mods,
        false_growth_detected=profile["false_growth_detected"],
        false_growth_warnings=profile["false_growth_warnings"],
        asset_growth_trend=profile["asset_growth_trend"],
        market_asset_value_xgp=profile["market_asset_value_xgp"],
        business_equity_xgp=profile["business_equity_xgp"],
        liquid_asset_value_xgp=profile["liquid_asset_value_xgp"],
        debt_drag_xgp=profile["debt_drag_xgp"],
        top_growth_driver=profile["top_growth_driver"],
        top_drag_driver=profile["top_drag_driver"],
        phase_advisory=phase_advisory,
        planning_insights=profile["planning_insights"],
        savings_capacity_summary=savings_state.get("short_summary", ""),
        asset_quality_label=assets.get("asset_quality_label", "balanced"),
        diversification_label=assets.get("diversification_label", "none"),
        debug_meta={
            "momentum_direction": momentum_direction,
            "history_days": len(history),
            "phase": phase,
            "softening_mods": mods,
        },
    )
