"""Step 20 financial distress, debt trap, and recovery arc service."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.financial_distress_config import (
    BASE_LATE_FEE_XGP,
    BORROWING_COST_MAX,
    BORROWING_COST_MIN,
    BUSINESS_RISK_PENALTY_MAX,
    CAREER_PROGRESS_PENALTY_MAX,
    CREDIT_SCORE_MAX,
    CREDIT_SCORE_MIN,
    DISTRESS_STATES,
    DISTRESS_THRESHOLDS,
    MAX_DAILY_DISTRESS_PAIN,
    MAX_DAILY_DISTRESS_RELIEF,
    OPPORTUNITY_ACCESS_PENALTY_MAX,
    PAYMENT_PLAN_CREDIT_DRAG,
    PAYMENT_PLAN_DISTRESS_RELIEF,
    RECOVERY_ACTIONS,
    UNDERPAID_LATE_FEE_FACTOR,
    MAX_LATE_FEE_XGP,
)
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.services.debt_credit_service import apply_daily_debt_and_credit

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

GAME_EPOCH = date(2026, 1, 1)


class FinancialDistressError(Exception):
    """Base error for financial distress operations."""


class FinancialDistressNotFoundError(FinancialDistressError):
    """Raised when player/resources are missing."""


class FinancialDistressValidationError(FinancialDistressError):
    """Raised for invalid distress payloads."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _parse_action_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
    except Exception:
        return []
    return []


def _date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise FinancialDistressValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise FinancialDistressNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise FinancialDistressNotFoundError("Player not found.")
    return player


def _resolve_day(player: Player, db: Session, as_of_date: date | None, day_number: int | None = None) -> tuple[int, date]:
    if day_number is not None:
        return int(day_number), _day_to_date(int(day_number))
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        if day <= 0:
            raise FinancialDistressValidationError("as_of_date must be on or after game epoch.")
        return day, as_of_date

    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


def _get_or_create_daily_state(db: Session, player: Player, day: int) -> PlayerDailyState:
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == int(day),
        )
        .first()
    )
    if pds is not None:
        return pds

    cash_now = _money(_d(player.cash_xgp))
    pds = PlayerDailyState(
        player_id=player.id,
        day_number=int(day),
        hours_available_start=int(player.hours_available or 24),
        hours_available_end=int(player.hours_available or 24),
        worked_main_job=False,
        did_settlement=False,
        stress_start=int(player.stress or 0),
        stress_end=int(player.stress or 0),
        health_start=int(player.health or 100),
        health_end=int(player.health or 100),
        cash_start=cash_now,
        cash_end=cash_now,
    )
    db.add(pds)
    db.flush()
    return pds


def _latest_monthly_income(db: Session, player_id: UUID, day: int) -> Decimal:
    row = (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player_id,
            PlayerEmploymentState.day <= int(day),
        )
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )
    return _money(_d(getattr(row, "monthly_pay_xgp", 0)))


def _existing_log_for_day(db: Session, player_id: UUID, day: int) -> FinancialDistressLog | None:
    return (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player_id,
            FinancialDistressLog.day == int(day),
        )
        .order_by(FinancialDistressLog.created_at.desc())
        .first()
    )


def compute_daily_debt_obligations(
    *,
    total_debt_xgp: Decimal,
    credit_score: int,
    monthly_income_xgp: Decimal,
    debt_payment_due_xgp: Decimal | None = None,
    on_payment_plan: bool = False,
) -> dict:
    """Compute daily debt burden, utilization, and minimum due for distress scoring."""
    debt = _money(max(Decimal("0.00"), _d(total_debt_xgp)))
    score = _clamp_int(int(credit_score or 650), CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)
    monthly_income = _money(max(Decimal("0.00"), _d(monthly_income_xgp)))

    if debt <= Decimal("0.00"):
        due = Decimal("0.00")
    elif debt_payment_due_xgp is not None and _d(debt_payment_due_xgp) > Decimal("0"):
        due = _money(_d(debt_payment_due_xgp))
    else:
        due = _money(
            min(
                debt,
                max(Decimal("6.00"), min(Decimal("120.00"), debt * Decimal("0.0125"))),
            )
        )

    if bool(on_payment_plan) and due > Decimal("0.00"):
        due = _money(_clamp(due * Decimal("0.72"), Decimal("3.00"), due))

    credit_cap_proxy = _clamp(
        Decimal("1000.00") + (Decimal(score - 300) * Decimal("11.50")),
        Decimal("1000.00"),
        Decimal("7500.00"),
    )
    income_anchor = max(Decimal("800.00"), monthly_income * Decimal("4.00"))
    utilization_anchor = max(Decimal("500.00"), (credit_cap_proxy * Decimal("0.60")) + (income_anchor * Decimal("0.40")))
    utilization_ratio = _q4(_clamp(debt / utilization_anchor, Decimal("0.00"), Decimal("3.00")))

    daily_income_proxy = _money(max(Decimal("1.00"), monthly_income / Decimal("30.00")))
    payment_burden_ratio = _q4(_clamp(due / daily_income_proxy, Decimal("0.00"), Decimal("8.00")))

    return {
        "total_debt_xgp": _money(debt),
        "required_daily_debt_payment_xgp": _money(due),
        "debt_utilization_ratio": _q4(utilization_ratio),
        "daily_income_proxy_xgp": _money(daily_income_proxy),
        "payment_burden_ratio": _q4(payment_burden_ratio),
    }


def apply_daily_debt_payment(
    *,
    debt_payment_due_xgp: Decimal,
    debt_payment_paid_xgp: Decimal,
    payment_status: str | None,
    missed_payment_streak_before: int,
    accrued_interest_xgp: Decimal,
) -> dict:
    """Resolve payment outcome and compute bounded late fee/interest pressure."""
    due = _money(max(Decimal("0.00"), _d(debt_payment_due_xgp)))
    paid = _money(_clamp(_d(debt_payment_paid_xgp), Decimal("0.00"), due))
    status = (payment_status or "").strip().lower()

    is_underpaid = bool(due > Decimal("0.00") and paid > Decimal("0.00") and paid < due)
    is_missed = bool(due > Decimal("0.00") and paid <= Decimal("0.00"))
    if status == "missed":
        is_missed = True
        is_underpaid = False
    elif status == "paid_partial":
        is_underpaid = True
        is_missed = False
    elif status == "paid_full":
        is_underpaid = False
        is_missed = False
    elif status == "no_debt":
        is_underpaid = False
        is_missed = False

    payment_missed_flag = bool(is_missed or is_underpaid)
    missed_streak_after = (int(max(0, missed_payment_streak_before)) + 1) if payment_missed_flag else 0

    late_fee = Decimal("0.00")
    if is_missed:
        late_fee = _money(
            _clamp(
                BASE_LATE_FEE_XGP
                + (due * Decimal("0.065"))
                + (Decimal(str(max(0, missed_payment_streak_before))) * Decimal("1.35")),
                Decimal("2.00"),
                MAX_LATE_FEE_XGP,
            )
        )
    elif is_underpaid:
        unpaid_gap = max(Decimal("0.00"), due - paid)
        late_fee = _money(
            _clamp(
                (BASE_LATE_FEE_XGP * UNDERPAID_LATE_FEE_FACTOR)
                + (unpaid_gap * Decimal("0.045"))
                + (Decimal(str(max(0, missed_payment_streak_before))) * Decimal("0.65")),
                Decimal("1.00"),
                MAX_LATE_FEE_XGP * Decimal("0.75"),
            )
        )

    accrued_interest = _money(max(Decimal("0.00"), _d(accrued_interest_xgp)))

    return {
        "debt_payment_due_xgp": _money(due),
        "debt_payment_paid_xgp": _money(paid),
        "debt_payment_missed": bool(payment_missed_flag),
        "payment_status": status or ("missed" if is_missed else ("paid_partial" if is_underpaid else "paid_full")),
        "late_fee_xgp": _money(late_fee),
        "accrued_interest_xgp": _money(accrued_interest),
        "missed_payment_streak_after": int(missed_streak_after),
        "underpaid_flag": bool(is_underpaid),
        "full_miss_flag": bool(is_missed),
    }


def compute_credit_score_update(
    *,
    credit_score_before: int,
    debt_utilization_ratio: Decimal,
    debt_payment_missed: bool,
    underpaid_flag: bool,
    distress_score_before: Decimal,
    missed_payment_streak_before: int,
    on_payment_plan: bool,
) -> int:
    """Compute bounded daily credit score delta from payment + utilization + distress."""
    score_before = _clamp_int(int(credit_score_before or 650), CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)
    util = _clamp(_d(debt_utilization_ratio), Decimal("0.00"), Decimal("3.00"))
    distress = _clamp(_d(distress_score_before), Decimal("0.00"), Decimal("100.00"))
    streak = int(max(0, missed_payment_streak_before))

    if bool(debt_payment_missed):
        penalty = 8 if not bool(underpaid_flag) else 4
        penalty += min(8, streak * 2)
        delta = -penalty
    else:
        delta = 1
        if util <= Decimal("0.35"):
            delta += 1

    if util >= Decimal("1.35"):
        delta -= 4
    elif util >= Decimal("1.00"):
        delta -= 3
    elif util >= Decimal("0.75"):
        delta -= 2
    elif util >= Decimal("0.55"):
        delta -= 1

    if distress >= Decimal("80"):
        delta -= 2
    elif distress >= Decimal("60"):
        delta -= 1

    if bool(on_payment_plan) and not bool(debt_payment_missed):
        delta += PAYMENT_PLAN_CREDIT_DRAG

    delta = _clamp_int(int(delta), -18, 4)
    if score_before <= CREDIT_SCORE_MIN and delta < 0:
        return 0
    if score_before >= CREDIT_SCORE_MAX and delta > 0:
        return 0
    return int(delta)


def compute_distress_score(
    *,
    distress_score_before: Decimal,
    debt_payment_due_xgp: Decimal,
    daily_income_proxy_xgp: Decimal,
    available_cash_xgp: Decimal,
    debt_utilization_ratio: Decimal,
    missed_payment_streak: int,
    credit_score_after: int,
    business_net_profit_xgp: Decimal,
    stress_value: Decimal,
    on_payment_plan: bool,
) -> dict:
    """Compute continuous distress score and per-driver breakdown."""
    prev = _clamp(_d(distress_score_before), Decimal("0.00"), Decimal("100.00"))
    due = _money(max(Decimal("0.00"), _d(debt_payment_due_xgp)))
    daily_income = _money(max(Decimal("1.00"), _d(daily_income_proxy_xgp)))
    available_cash = _money(max(Decimal("0.00"), _d(available_cash_xgp)))
    util = _clamp(_d(debt_utilization_ratio), Decimal("0.00"), Decimal("3.00"))
    streak = int(max(0, missed_payment_streak))
    credit_after = _clamp_int(int(credit_score_after or 650), CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)
    business_net = _money(_d(business_net_profit_xgp))
    stress = _clamp(_d(stress_value), Decimal("0.00"), Decimal("100.00"))

    burden_ratio = _clamp(due / daily_income, Decimal("0.00"), Decimal("8.00"))
    debt_burden_component = _clamp(burden_ratio * Decimal("4.40"), Decimal("0.00"), Decimal("30.00"))

    cushion_anchor = max(Decimal("40.00"), (due * Decimal("5.00")) + Decimal("40.00"))
    cushion_ratio = _clamp(available_cash / cushion_anchor, Decimal("0.00"), Decimal("1.20"))
    cash_cushion_component = _clamp(
        (Decimal("1.00") - _clamp(cushion_ratio, Decimal("0.00"), Decimal("1.00"))) * Decimal("22.00"),
        Decimal("0.00"),
        Decimal("22.00"),
    )

    utilization_component = _clamp(util * Decimal("8.00"), Decimal("0.00"), Decimal("14.00"))
    missed_payment_component = _clamp(Decimal(str(streak)) * Decimal("6.50"), Decimal("0.00"), Decimal("30.00"))
    credit_deterioration_component = _clamp(
        (Decimal("620.00") - Decimal(str(credit_after))) / Decimal("7.00"),
        Decimal("0.00"),
        Decimal("16.00"),
    )
    business_loss_component = (
        _clamp(abs(business_net) / Decimal("90.00"), Decimal("0.00"), Decimal("9.00"))
        if business_net < 0
        else Decimal("0.00")
    )
    stress_synergy_component = _clamp(
        max(Decimal("0.00"), stress - Decimal("55.00")) / Decimal("6.50"),
        Decimal("0.00"),
        Decimal("10.00"),
    )
    inertia_component = _clamp(prev * Decimal("0.25"), Decimal("0.00"), Decimal("18.00"))
    payment_plan_relief_component = PAYMENT_PLAN_DISTRESS_RELIEF if bool(on_payment_plan) else Decimal("0.00")

    raw_score = (
        debt_burden_component
        + cash_cushion_component
        + utilization_component
        + missed_payment_component
        + credit_deterioration_component
        + business_loss_component
        + stress_synergy_component
        + inertia_component
        - payment_plan_relief_component
    )
    raw_score = _clamp(raw_score, Decimal("0.00"), Decimal("100.00"))
    blended_score = _clamp((prev * Decimal("0.55")) + (raw_score * Decimal("0.45")), Decimal("0.00"), Decimal("100.00"))

    return {
        "distress_score_before": _q4(prev),
        "distress_score_after_raw": _q4(raw_score),
        "distress_score_after": _q4(blended_score),
        "drivers": {
            "debt_burden_component": float(_q4(debt_burden_component)),
            "cash_cushion_component": float(_q4(cash_cushion_component)),
            "utilization_component": float(_q4(utilization_component)),
            "missed_payment_component": float(_q4(missed_payment_component)),
            "credit_deterioration_component": float(_q4(credit_deterioration_component)),
            "business_loss_component": float(_q4(business_loss_component)),
            "stress_synergy_component": float(_q4(stress_synergy_component)),
            "inertia_component": float(_q4(inertia_component)),
            "payment_plan_relief_component": float(_q4(payment_plan_relief_component)),
            "raw_score": float(_q4(raw_score)),
            "blended_score": float(_q4(blended_score)),
        },
    }


def compute_distress_state(distress_score: Decimal) -> str:
    """Map continuous distress score to deterministic threshold state."""
    score = _clamp(_d(distress_score), Decimal("0.00"), Decimal("100.00"))
    if score <= DISTRESS_THRESHOLDS["stable"]:
        return "stable"
    if score <= DISTRESS_THRESHOLDS["stretched"]:
        return "stretched"
    if score <= DISTRESS_THRESHOLDS["distressed"]:
        return "distressed"
    return "critical"


def compute_borrowing_penalty_signals(
    *,
    credit_score: int,
    distress_score: Decimal,
    distress_state: str,
    on_payment_plan: bool,
) -> dict:
    """Compute bounded finance penalty signals consumable by other systems."""
    score = _clamp_int(int(credit_score or 650), CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)
    distress = _clamp(_d(distress_score), Decimal("0.00"), Decimal("100.00"))
    state = (distress_state or "stable").strip().lower()
    if state not in DISTRESS_STATES:
        state = "stable"

    state_lift = {"stable": Decimal("0.00"), "stretched": Decimal("0.04"), "distressed": Decimal("0.10"), "critical": Decimal("0.18")}[state]
    state_opportunity = {"stable": Decimal("0.00"), "stretched": Decimal("0.03"), "distressed": Decimal("0.08"), "critical": Decimal("0.13")}[state]
    state_business = {"stable": Decimal("0.00"), "stretched": Decimal("0.04"), "distressed": Decimal("0.10"), "critical": Decimal("0.16")}[state]
    state_career = {"stable": Decimal("0.00"), "stretched": Decimal("0.02"), "distressed": Decimal("0.06"), "critical": Decimal("0.10")}[state]

    credit_drag = _clamp((Decimal("680.00") - Decimal(str(score))) / Decimal("420.00"), Decimal("0.00"), Decimal("0.55"))
    borrowing_cost_modifier = _clamp(
        Decimal("1.00") + credit_drag + state_lift + _clamp(distress / Decimal("900.00"), Decimal("0.00"), Decimal("0.14")),
        BORROWING_COST_MIN,
        BORROWING_COST_MAX,
    )
    opportunity_access_penalty = _clamp(
        state_opportunity
        + _clamp((distress - Decimal("35.00")) / Decimal("300.00"), Decimal("0.00"), Decimal("0.18"))
        + _clamp((Decimal("620.00") - Decimal(str(score))) / Decimal("5200.00"), Decimal("0.00"), Decimal("0.07")),
        Decimal("0.00"),
        OPPORTUNITY_ACCESS_PENALTY_MAX,
    )
    business_risk_penalty = _clamp(
        state_business
        + _clamp((distress - Decimal("40.00")) / Decimal("250.00"), Decimal("0.00"), Decimal("0.20"))
        + _clamp((Decimal("650.00") - Decimal(str(score))) / Decimal("4200.00"), Decimal("0.00"), Decimal("0.08")),
        Decimal("0.00"),
        BUSINESS_RISK_PENALTY_MAX,
    )
    career_progress_penalty = _clamp(
        state_career + _clamp((distress - Decimal("45.00")) / Decimal("320.00"), Decimal("0.00"), Decimal("0.15")),
        Decimal("0.00"),
        CAREER_PROGRESS_PENALTY_MAX,
    )

    if bool(on_payment_plan):
        opportunity_access_penalty = _clamp(opportunity_access_penalty - Decimal("0.0100"), Decimal("0.00"), OPPORTUNITY_ACCESS_PENALTY_MAX)
        business_risk_penalty = _clamp(business_risk_penalty - Decimal("0.0150"), Decimal("0.00"), BUSINESS_RISK_PENALTY_MAX)

    return {
        "borrowing_cost_modifier": _q4(borrowing_cost_modifier),
        "opportunity_access_penalty": _q4(opportunity_access_penalty),
        "business_risk_penalty": _q4(business_risk_penalty),
        "career_progress_penalty": _q4(career_progress_penalty),
    }


def apply_recovery_actions(
    *,
    player: Player,
    distress_state: str,
    distress_score: Decimal,
    queued_actions: list[str] | None = None,
) -> dict:
    """Apply queued/system recovery actions and return deterministic tradeoffs."""
    state = (distress_state or "stable").strip().lower()
    if state not in DISTRESS_STATES:
        state = "stable"
    score = _clamp(_d(distress_score), Decimal("0.00"), Decimal("100.00"))

    input_actions = list(queued_actions or [])
    normalized_actions = [str(action).strip().lower() for action in input_actions if str(action).strip()]
    invalid_actions = sorted({action for action in normalized_actions if action not in RECOVERY_ACTIONS})
    actions = [action for action in normalized_actions if action in RECOVERY_ACTIONS]

    suggestions: list[str] = []
    if state in {"distressed", "critical"} and (player.region or "").strip().lower() == "downtown":
        suggestions.append("housing_downshift_recommendation")
    if state == "critical" and not bool(getattr(player, "on_payment_plan", False)):
        suggestions.append("payment_plan_enroll")
    if score >= Decimal("70"):
        suggestions.append("business_spending_cut")
        suggestions.append("emergency_savings_mode")

    applied_actions: list[str] = []
    distress_relief = Decimal("0.00")
    credit_delta_adjustment = 0
    opportunity_adjustment = Decimal("0.00")
    business_adjustment = Decimal("0.00")
    career_adjustment = Decimal("0.00")
    notes: list[str] = []

    def _apply_action(action: str) -> None:
        nonlocal distress_relief, credit_delta_adjustment, opportunity_adjustment, business_adjustment, career_adjustment
        if action == "payment_plan_enroll":
            player.on_payment_plan = True
            distress_relief += Decimal("4.50")
            credit_delta_adjustment += PAYMENT_PLAN_CREDIT_DRAG
            notes.append("Payment plan eases immediate burden but slows score recovery.")
        elif action == "business_spending_cut":
            distress_relief += Decimal("2.00")
            business_adjustment -= Decimal("0.0300")
            notes.append("Business spending cut lowers risk appetite.")
        elif action == "housing_downshift_recommendation":
            notes.append("Housing downshift is recommended while under heavy pressure.")
        elif action == "inventory_freeze":
            distress_relief += Decimal("2.00")
            business_adjustment -= Decimal("0.0500")
            notes.append("Inventory freeze reduces expansion risk but limits growth.")
        elif action == "extra_work_push":
            distress_relief += Decimal("1.50")
            career_adjustment += Decimal("0.0200")
            notes.append("Extra work push helps cashflow but raises life strain.")
        elif action == "defer_training":
            distress_relief += Decimal("1.00")
            career_adjustment += Decimal("0.0500")
            notes.append("Training deferment frees resources at career growth cost.")
        elif action == "emergency_savings_mode":
            distress_relief += Decimal("2.00")
            opportunity_adjustment += Decimal("0.0200")
            business_adjustment += Decimal("0.0200")
            notes.append("Emergency savings mode improves resilience but narrows optional moves.")

    seen: set[str] = set()
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        _apply_action(action)
        applied_actions.append(action)

    if state == "critical" and not bool(getattr(player, "on_payment_plan", False)) and "payment_plan_enroll" not in seen:
        _apply_action("payment_plan_enroll")
        applied_actions.append("payment_plan_enroll_auto")

    distress_relief = _clamp(distress_relief, Decimal("0.00"), MAX_DAILY_DISTRESS_RELIEF)

    return {
        "actions_applied": applied_actions,
        "invalid_actions": invalid_actions,
        "suggested_actions": sorted(set(suggestions)),
        "distress_relief": _q4(distress_relief),
        "credit_delta_adjustment": int(credit_delta_adjustment),
        "opportunity_adjustment": _q4(opportunity_adjustment),
        "business_adjustment": _q4(business_adjustment),
        "career_adjustment": _q4(career_adjustment),
        "notes": notes,
    }


def _serialize_financial_distress_log(row: FinancialDistressLog) -> dict:
    try:
        distress_driver_json = json.loads(row.distress_driver_json or "{}")
    except Exception:
        distress_driver_json = {}
    try:
        recovery_actions_json = json.loads(row.recovery_actions_json or "{}")
    except Exception:
        recovery_actions_json = {}

    return {
        "id": str(row.id),
        "player_id": str(row.player_id),
        "day": int(row.day),
        "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
        "debt_payment_due_xgp": float(_money(_d(row.debt_payment_due_xgp))),
        "debt_payment_paid_xgp": float(_money(_d(row.debt_payment_paid_xgp))),
        "debt_payment_missed": bool(row.debt_payment_missed),
        "late_fee_xgp": float(_money(_d(row.late_fee_xgp))),
        "accrued_interest_xgp": float(_money(_d(row.accrued_interest_xgp))),
        "credit_score_before": int(row.credit_score_before),
        "credit_score_after": int(row.credit_score_after),
        "credit_score_delta": int(row.credit_score_delta),
        "distress_state_before": str(row.distress_state_before),
        "distress_state_after": str(row.distress_state_after),
        "distress_score_before": float(_q4(_d(row.distress_score_before))),
        "distress_score_after": float(_q4(_d(row.distress_score_after))),
        "borrowing_cost_modifier": float(_q4(_d(row.borrowing_cost_modifier))),
        "opportunity_access_penalty": float(_q4(_d(row.opportunity_access_penalty))),
        "business_risk_penalty": float(_q4(_d(row.business_risk_penalty))),
        "career_progress_penalty": float(_q4(_d(row.career_progress_penalty))),
        "distress_driver_json": distress_driver_json,
        "recovery_actions_applied": recovery_actions_json.get("actions_applied", []),
        "recovery_actions_json": recovery_actions_json,
        "debug_meta": {
            "distress_driver_json": distress_driver_json,
            "recovery_actions_json": recovery_actions_json,
        },
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _persist_financial_to_daily_state(
    pds: PlayerDailyState,
    *,
    debt_payment_due_xgp: Decimal,
    debt_payment_paid_xgp: Decimal,
    debt_payment_missed: bool,
    late_fee_xgp: Decimal,
    accrued_interest_xgp: Decimal,
    credit_score_before: int,
    credit_score_after: int,
    credit_score_delta: int,
    distress_state_before: str,
    distress_state_after: str,
    distress_score_before: Decimal,
    distress_score_after: Decimal,
    penalty_signals: dict,
    distress_driver_json: dict,
    recovery_actions_json: dict,
) -> None:
    pds.debt_payment_due_xgp = _money(debt_payment_due_xgp)
    pds.debt_payment_paid_xgp = _money(debt_payment_paid_xgp)
    pds.debt_payment_missed = bool(debt_payment_missed)
    pds.late_fee_xgp = _money(late_fee_xgp)
    pds.accrued_interest_xgp = _money(accrued_interest_xgp)
    pds.credit_score_before = int(credit_score_before)
    pds.credit_score_after = int(credit_score_after)
    pds.credit_score_delta = int(credit_score_delta)
    pds.distress_state_before = str(distress_state_before)
    pds.distress_state_after = str(distress_state_after)
    pds.distress_score_before = _q4(distress_score_before)
    pds.distress_score_after = _q4(distress_score_after)
    pds.borrowing_cost_modifier = _q4(_d(penalty_signals.get("borrowing_cost_modifier", 1.0)))
    pds.opportunity_access_penalty = _q4(_d(penalty_signals.get("opportunity_access_penalty", 0.0)))
    pds.business_risk_penalty = _q4(_d(penalty_signals.get("business_risk_penalty", 0.0)))
    pds.career_progress_penalty = _q4(_d(penalty_signals.get("career_progress_penalty", 0.0)))
    pds.distress_driver_json = json.dumps(distress_driver_json, sort_keys=True)
    pds.recovery_actions_json = json.dumps(recovery_actions_json, sort_keys=True)


def apply_daily_financial_distress(
    db: Session,
    player_id: int | str | UUID,
    as_of_date: date | None = None,
    *,
    day_number: int | None = None,
    debt_context: dict | None = None,
    monthly_income_xgp: Decimal | float | int | None = None,
    business_net_profit_xgp: Decimal | float | int | None = None,
    available_cash_xgp: Decimal | float | int | None = None,
) -> dict:
    """Apply one deterministic day of debt/distress/recovery state for a player."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=day_number)
    pds = _get_or_create_daily_state(db, player, day)

    existing = _existing_log_for_day(db, player.id, day)
    if existing is not None:
        payload = _serialize_financial_distress_log(existing)
        payload["already_processed"] = True
        return payload

    monthly_income = _money(_d(monthly_income_xgp)) if monthly_income_xgp is not None else _latest_monthly_income(db, player.id, day)
    if debt_context is None:
        debt_context = apply_daily_debt_and_credit(
            db=db,
            player_id=player.id,
            day=day,
            commit=False,
            mutate_player=False,
            available_cash_xgp=_d(available_cash_xgp) if available_cash_xgp is not None else _d(player.cash_xgp),
        )

    obligation = compute_daily_debt_obligations(
        total_debt_xgp=_d(player.debt_xgp),
        credit_score=int(debt_context.get("opening_credit_score", player.credit_score or 650)),
        monthly_income_xgp=monthly_income,
        debt_payment_due_xgp=_d(debt_context.get("payment_due_xgp", 0)),
        on_payment_plan=bool(getattr(player, "on_payment_plan", False)),
    )

    missed_streak_before = int(getattr(player, "missed_payment_streak", 0) or 0)
    payment_result = apply_daily_debt_payment(
        debt_payment_due_xgp=_d(obligation["required_daily_debt_payment_xgp"]),
        debt_payment_paid_xgp=_d(debt_context.get("payment_made_xgp", debt_context.get("payment_paid_xgp", 0))),
        payment_status=str(debt_context.get("payment_status", "")),
        missed_payment_streak_before=missed_streak_before,
        accrued_interest_xgp=_d(debt_context.get("interest_added_xgp", debt_context.get("accrued_interest_xgp", 0))),
    )

    credit_before = _clamp_int(int(debt_context.get("opening_credit_score", player.credit_score or 650)), CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)
    distress_state_before = (str(getattr(player, "distress_state", "stable") or "stable")).strip().lower()
    if distress_state_before not in DISTRESS_STATES:
        distress_state_before = "stable"
    distress_score_before = _clamp(_d(getattr(player, "distress_score", 0)), Decimal("0.00"), Decimal("100.00"))

    candidate_credit_delta = compute_credit_score_update(
        credit_score_before=credit_before,
        debt_utilization_ratio=_d(obligation["debt_utilization_ratio"]),
        debt_payment_missed=bool(payment_result["debt_payment_missed"]),
        underpaid_flag=bool(payment_result["underpaid_flag"]),
        distress_score_before=distress_score_before,
        missed_payment_streak_before=missed_streak_before,
        on_payment_plan=bool(getattr(player, "on_payment_plan", False)),
    )
    base_credit_delta = int(_d(debt_context.get("credit_score_change", 0)))
    blended_credit_delta = _clamp_int(
        base_credit_delta + _clamp_int(candidate_credit_delta - base_credit_delta, -6, 2),
        -20,
        4,
    )
    credit_after = _clamp_int(credit_before + blended_credit_delta, CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)

    distress_update = compute_distress_score(
        distress_score_before=distress_score_before,
        debt_payment_due_xgp=_d(payment_result["debt_payment_due_xgp"]),
        daily_income_proxy_xgp=_d(obligation["daily_income_proxy_xgp"]),
        available_cash_xgp=_d(available_cash_xgp) if available_cash_xgp is not None else _d(player.cash_xgp),
        debt_utilization_ratio=_d(obligation["debt_utilization_ratio"]),
        missed_payment_streak=int(payment_result["missed_payment_streak_after"]),
        credit_score_after=credit_after,
        business_net_profit_xgp=_d(business_net_profit_xgp if business_net_profit_xgp is not None else 0),
        stress_value=_d(getattr(player, "stress", 0)),
        on_payment_plan=bool(getattr(player, "on_payment_plan", False)),
    )
    distress_score_after = _clamp(_d(distress_update["distress_score_after"]), Decimal("0.00"), Decimal("100.00"))
    distress_state_after = compute_distress_state(distress_score_after)

    queued_actions = _parse_action_list(getattr(player, "recovery_actions_json", None))
    recovery_update = apply_recovery_actions(
        player=player,
        distress_state=distress_state_after,
        distress_score=distress_score_after,
        queued_actions=queued_actions,
    )
    relief = _clamp(_d(recovery_update["distress_relief"]), Decimal("0.00"), MAX_DAILY_DISTRESS_RELIEF)
    if bool(payment_result["debt_payment_missed"]):
        distress_score_after = _clamp(
            distress_score_after + _clamp(Decimal("2.25"), Decimal("0.00"), MAX_DAILY_DISTRESS_PAIN),
            Decimal("0.00"),
            Decimal("100.00"),
        )
    distress_score_after = _clamp(distress_score_after - relief, Decimal("0.00"), Decimal("100.00"))
    distress_state_after = compute_distress_state(distress_score_after)

    blended_credit_delta = _clamp_int(
        blended_credit_delta + int(recovery_update.get("credit_delta_adjustment", 0) or 0),
        -20,
        4,
    )
    credit_after = _clamp_int(credit_before + blended_credit_delta, CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)

    penalty_signals = compute_borrowing_penalty_signals(
        credit_score=credit_after,
        distress_score=distress_score_after,
        distress_state=distress_state_after,
        on_payment_plan=bool(getattr(player, "on_payment_plan", False)),
    )
    penalty_signals["opportunity_access_penalty"] = _q4(
        _clamp(
            _d(penalty_signals["opportunity_access_penalty"]) + _d(recovery_update.get("opportunity_adjustment", 0)),
            Decimal("0.00"),
            OPPORTUNITY_ACCESS_PENALTY_MAX,
        )
    )
    penalty_signals["business_risk_penalty"] = _q4(
        _clamp(
            _d(penalty_signals["business_risk_penalty"]) + _d(recovery_update.get("business_adjustment", 0)),
            Decimal("0.00"),
            BUSINESS_RISK_PENALTY_MAX,
        )
    )
    penalty_signals["career_progress_penalty"] = _q4(
        _clamp(
            _d(penalty_signals["career_progress_penalty"]) + _d(recovery_update.get("career_adjustment", 0)),
            Decimal("0.00"),
            CAREER_PROGRESS_PENALTY_MAX,
        )
    )

    late_fee_xgp = _money(_d(payment_result["late_fee_xgp"]))
    if bool(getattr(player, "on_payment_plan", False)) and late_fee_xgp > Decimal("0.00"):
        late_fee_xgp = _money(_clamp(late_fee_xgp * Decimal("0.55"), Decimal("0.00"), late_fee_xgp))
    accrued_interest_xgp = _money(_d(payment_result["accrued_interest_xgp"]))

    if bool(payment_result["debt_payment_missed"]):
        player.last_missed_payment_date = resolved_date

    player.required_daily_debt_payment_xgp = _money(_d(obligation["required_daily_debt_payment_xgp"]))
    player.debt_utilization_ratio = _q4(_d(obligation["debt_utilization_ratio"]))
    player.missed_payment_streak = int(payment_result["missed_payment_streak_after"])
    player.credit_score = int(credit_after)
    player.distress_state = distress_state_after
    player.distress_score = _q4(distress_score_after)
    player.borrowing_cost_modifier = _q4(_d(penalty_signals["borrowing_cost_modifier"]))
    player.opportunity_access_penalty = _q4(_d(penalty_signals["opportunity_access_penalty"]))
    player.business_risk_penalty = _q4(_d(penalty_signals["business_risk_penalty"]))
    player.career_progress_penalty = _q4(_d(penalty_signals["career_progress_penalty"]))
    player.recovery_actions_json = json.dumps([], sort_keys=True)

    distress_driver_json = {
        "obligation": {
            "required_daily_debt_payment_xgp": float(_money(_d(obligation["required_daily_debt_payment_xgp"]))),
            "debt_utilization_ratio": float(_q4(_d(obligation["debt_utilization_ratio"]))),
            "daily_income_proxy_xgp": float(_money(_d(obligation["daily_income_proxy_xgp"]))),
            "payment_burden_ratio": float(_q4(_d(obligation["payment_burden_ratio"]))),
        },
        "payment_resolution": {
            "payment_status": payment_result["payment_status"],
            "debt_payment_missed": bool(payment_result["debt_payment_missed"]),
            "underpaid_flag": bool(payment_result["underpaid_flag"]),
            "full_miss_flag": bool(payment_result["full_miss_flag"]),
            "late_fee_xgp": float(late_fee_xgp),
            "accrued_interest_xgp": float(accrued_interest_xgp),
            "missed_payment_streak_before": int(missed_streak_before),
            "missed_payment_streak_after": int(payment_result["missed_payment_streak_after"]),
        },
        "credit_drivers": {
            "base_credit_delta": int(base_credit_delta),
            "candidate_credit_delta": int(candidate_credit_delta),
            "final_credit_delta": int(blended_credit_delta),
            "credit_score_before": int(credit_before),
            "credit_score_after": int(credit_after),
        },
        "distress_drivers": distress_update["drivers"],
        "penalty_signals": {
            "borrowing_cost_modifier": float(_q4(_d(penalty_signals["borrowing_cost_modifier"]))),
            "opportunity_access_penalty": float(_q4(_d(penalty_signals["opportunity_access_penalty"]))),
            "business_risk_penalty": float(_q4(_d(penalty_signals["business_risk_penalty"]))),
            "career_progress_penalty": float(_q4(_d(penalty_signals["career_progress_penalty"]))),
        },
    }

    recovery_actions_json = {
        "actions_applied": list(recovery_update.get("actions_applied", [])),
        "invalid_actions": list(recovery_update.get("invalid_actions", [])),
        "suggested_actions": list(recovery_update.get("suggested_actions", [])),
        "notes": list(recovery_update.get("notes", [])),
    }

    player.credit_debug_json = json.dumps(
        {
            "day": int(day),
            "as_of_date": resolved_date.isoformat(),
            "distress_state_before": distress_state_before,
            "distress_state_after": distress_state_after,
            "distress_score_before": float(_q4(distress_score_before)),
            "distress_score_after": float(_q4(distress_score_after)),
            "distress_driver_json": distress_driver_json,
            "recovery_actions_json": recovery_actions_json,
        },
        sort_keys=True,
    )

    _persist_financial_to_daily_state(
        pds,
        debt_payment_due_xgp=_d(payment_result["debt_payment_due_xgp"]),
        debt_payment_paid_xgp=_d(payment_result["debt_payment_paid_xgp"]),
        debt_payment_missed=bool(payment_result["debt_payment_missed"]),
        late_fee_xgp=late_fee_xgp,
        accrued_interest_xgp=accrued_interest_xgp,
        credit_score_before=credit_before,
        credit_score_after=credit_after,
        credit_score_delta=blended_credit_delta,
        distress_state_before=distress_state_before,
        distress_state_after=distress_state_after,
        distress_score_before=distress_score_before,
        distress_score_after=distress_score_after,
        penalty_signals=penalty_signals,
        distress_driver_json=distress_driver_json,
        recovery_actions_json=recovery_actions_json,
    )

    row = FinancialDistressLog(
        player_id=player.id,
        day=int(day),
        as_of_date=resolved_date,
        debt_payment_due_xgp=_money(_d(payment_result["debt_payment_due_xgp"])),
        debt_payment_paid_xgp=_money(_d(payment_result["debt_payment_paid_xgp"])),
        debt_payment_missed=bool(payment_result["debt_payment_missed"]),
        late_fee_xgp=_money(late_fee_xgp),
        accrued_interest_xgp=_money(accrued_interest_xgp),
        credit_score_before=int(credit_before),
        credit_score_after=int(credit_after),
        credit_score_delta=int(blended_credit_delta),
        distress_state_before=distress_state_before,
        distress_state_after=distress_state_after,
        distress_score_before=_q4(distress_score_before),
        distress_score_after=_q4(distress_score_after),
        borrowing_cost_modifier=_q4(_d(penalty_signals["borrowing_cost_modifier"])),
        opportunity_access_penalty=_q4(_d(penalty_signals["opportunity_access_penalty"])),
        business_risk_penalty=_q4(_d(penalty_signals["business_risk_penalty"])),
        career_progress_penalty=_q4(_d(penalty_signals["career_progress_penalty"])),
        distress_driver_json=json.dumps(distress_driver_json, sort_keys=True),
        recovery_actions_json=json.dumps(recovery_actions_json, sort_keys=True),
    )
    db.add(row)
    db.flush()

    payload = _serialize_financial_distress_log(row)
    payload["already_processed"] = False
    return payload


def get_player_credit_snapshot(db: Session, player_id: str | UUID) -> dict:
    """Return current credit/debt/distress state and active penalty signals."""
    player = _resolve_player(db, player_id)
    latest = (
        db.query(FinancialDistressLog)
        .filter(FinancialDistressLog.player_id == player.id)
        .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
        .first()
    )
    latest_payload = _serialize_financial_distress_log(latest) if latest is not None else None

    return {
        "player_id": str(player.id),
        "credit_score": int(_clamp_int(int(player.credit_score or 650), CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)),
        "total_debt_xgp": float(_money(_d(player.debt_xgp))),
        "required_daily_debt_payment_xgp": float(_money(_d(getattr(player, "required_daily_debt_payment_xgp", 0)))),
        "debt_utilization_ratio": float(_q4(_d(getattr(player, "debt_utilization_ratio", 0)))),
        "missed_payment_streak": int(getattr(player, "missed_payment_streak", 0) or 0),
        "on_payment_plan": bool(getattr(player, "on_payment_plan", False)),
        "distress_state": str(getattr(player, "distress_state", "stable") or "stable"),
        "distress_score": float(_q4(_d(getattr(player, "distress_score", 0)))),
        "borrowing_cost_modifier": float(_q4(_d(getattr(player, "borrowing_cost_modifier", 1)))),
        "opportunity_access_penalty": float(_q4(_d(getattr(player, "opportunity_access_penalty", 0)))),
        "business_risk_penalty": float(_q4(_d(getattr(player, "business_risk_penalty", 0)))),
        "career_progress_penalty": float(_q4(_d(getattr(player, "career_progress_penalty", 0)))),
        "debug_meta": {
            "last_missed_payment_date": (
                player.last_missed_payment_date.isoformat() if getattr(player, "last_missed_payment_date", None) else None
            ),
            "credit_debug_json": _parse_json(getattr(player, "credit_debug_json", None)),
            "latest_daily": latest_payload,
            "queued_recovery_actions": _parse_action_list(getattr(player, "recovery_actions_json", None)),
        },
    }


def get_player_distress_history(db: Session, player_id: str | UUID, *, limit: int = 30) -> dict:
    """Return distress history rows with trailing metrics for balancing/debug."""
    if int(limit) <= 0:
        raise FinancialDistressValidationError("limit must be greater than 0.")

    player = _resolve_player(db, player_id)
    rows = (
        db.query(FinancialDistressLog)
        .filter(FinancialDistressLog.player_id == player.id)
        .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
        .limit(int(limit))
        .all()
    )

    entries = [_serialize_financial_distress_log(row) for row in rows]
    recent = entries[:7]
    n = Decimal(str(max(1, len(recent))))
    avg_distress = sum((Decimal(str(item["distress_score_after"])) for item in recent), Decimal("0")) / n
    missed_count = sum((1 for item in recent if bool(item["debt_payment_missed"])))
    credit_change = sum((int(item["credit_score_delta"]) for item in recent))

    recovery_streak = 0
    for item in entries:
        if int(item["credit_score_delta"]) >= 0 and not bool(item["debt_payment_missed"]):
            recovery_streak += 1
        else:
            break

    return {
        "player_id": str(player.id),
        "entries": entries,
        "trailing_7d_avg_distress_score": float(_q4(avg_distress)),
        "trailing_7d_missed_payments": int(missed_count),
        "trailing_7d_credit_change": int(credit_change),
        "recovery_streak_days": int(recovery_streak),
    }


def queue_player_recovery_action(db: Session, player_id: str | UUID, action_key: str) -> dict:
    """Queue one recovery action to be consumed on the next distress resolution."""
    action = (action_key or "").strip().lower()
    if action not in RECOVERY_ACTIONS:
        raise FinancialDistressValidationError(
            f"Unsupported recovery action. Use one of: {sorted(RECOVERY_ACTIONS)}"
        )
    player = _resolve_player(db, player_id)
    queue = _parse_action_list(getattr(player, "recovery_actions_json", None))
    if action not in queue:
        queue.append(action)
        queue.sort()
    player.recovery_actions_json = json.dumps(queue)
    db.flush()
    return {
        "player_id": str(player.id),
        "action_queued": action,
        "queued_actions": queue,
        "on_payment_plan": bool(getattr(player, "on_payment_plan", False)),
    }


def get_player_debt_snapshot(db: Session, player_id: str | UUID) -> dict:
    """Return compact debt snapshot with latest payment performance context."""
    player = _resolve_player(db, player_id)
    latest = (
        db.query(FinancialDistressLog)
        .filter(FinancialDistressLog.player_id == player.id)
        .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
        .first()
    )
    latest_payload = _serialize_financial_distress_log(latest) if latest is not None else None
    return {
        "player_id": str(player.id),
        "total_debt_xgp": float(_money(_d(player.debt_xgp))),
        "debt_payment_due_xgp": float(_money(_d(getattr(player, "required_daily_debt_payment_xgp", 0)))),
        "accrued_interest_xgp": float(_money(_d((latest_payload or {}).get("accrued_interest_xgp", 0)))),
        "late_fee_xgp": float(_money(_d((latest_payload or {}).get("late_fee_xgp", 0)))),
        "debt_utilization_ratio": float(_q4(_d(getattr(player, "debt_utilization_ratio", 0)))),
        "recovery_actions_available": sorted(RECOVERY_ACTIONS),
        "debug_meta": {
            "latest_daily": latest_payload,
            "queued_recovery_actions": _parse_action_list(getattr(player, "recovery_actions_json", None)),
        },
    }
