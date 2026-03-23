"""Step 29 commitment service: activate plans, track adherence, and guide follow-through."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.strategic_planning_service import (
    build_player_strategy_recommendation,
    build_short_horizon_plan_options,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_commitment_history import PlayerCommitmentHistory
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_daily_state import PlayerDailyState
from app.models.side_income_action import SideIncomeAction

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
MONEY_Q = Decimal("0.01")

ACTIVE_STATUS = "active"
INACTIVE_STATUS = "inactive"
FINAL_STATUSES = {"completed", "failed", "cancelled", "expired", "replaced"}

DEFAULT_DURATION_DAYS = 5
MIN_DURATION_DAYS = 3
MAX_DURATION_DAYS = 7

DEFAULT_ADHERENCE_SCORE = Decimal("55.0")
DEFAULT_MOMENTUM_SCORE = Decimal("50.0")

COMMITMENT_FOCUS_MAP: dict[str, list[str]] = {
    "stabilize_finances": [
        "Cover daily debt obligations on time",
        "Preserve cash buffer and avoid risky outflows",
        "Keep distress trend from worsening",
    ],
    "push_income": [
        "Complete productive work/business actions",
        "Protect burnout guardrails while pushing output",
        "Keep short-run net cash positive",
    ],
    "reduce_stress": [
        "Take recovery actions and protect sleep",
        "Avoid sustained overtime pressure",
        "Keep stress trend downward",
    ],
    "invest_career": [
        "Log training consistently",
        "Protect enough recovery for productivity",
        "Trade short-term cash for medium-term progression",
    ],
    "lean_into_business": [
        "Operate business consistently in favorable windows",
        "Watch margin pressure and avoid overbuying inventory",
        "Maintain positive business net over the plan horizon",
    ],
    "housing_optimization": [
        "Reduce commute burden where feasible",
        "Accept housing-cost tradeoff when moving closer",
        "Avoid letting commute stress silently compound",
    ],
}

COMMITMENT_PAYOFF_MAP: dict[str, tuple[str, str]] = {
    "stabilize_finances": (
        "Debt pressure and distress should ease if discipline holds.",
        "Missing payments can quickly erase progress and raise stress.",
    ),
    "push_income": (
        "Cash runway can improve fast in a productive 3-day push.",
        "Burnout and distress can spike if recovery is ignored.",
    ),
    "reduce_stress": (
        "Lower stress supports better productivity and fewer bad-day spirals.",
        "Income momentum may slow while prioritizing recovery.",
    ),
    "invest_career": (
        "Skill and promotion readiness improve medium-term earnings potential.",
        "Short-term liquidity can feel tighter during training focus.",
    ),
    "lean_into_business": (
        "Favorable demand windows can compound business momentum.",
        "Weak margin days can amplify losses without discipline.",
    ),
    "housing_optimization": (
        "Lower commute burden can free time and reduce daily stress load.",
        "Renting closer increases housing expense and cash pressure.",
    ),
}

COMMITMENT_CORRECTION_MAP: dict[str, str] = {
    "stabilize_finances": "Prioritize payment coverage first and pause optional spend for 1-2 days.",
    "push_income": "Keep productive actions, but add one recovery window to avoid burnout drag.",
    "reduce_stress": "Take one recovery action and skip one high-pressure grind action tomorrow.",
    "invest_career": "Log at least one training action before adding extra grind shifts.",
    "lean_into_business": "Run only the strongest business mode and avoid speculative inventory buys.",
    "housing_optimization": "If commute pressure stays high, consider move/rent-closer despite higher housing cost.",
}


class CommitmentError(Exception):
    """Base commitment exception."""


class CommitmentNotFoundError(CommitmentError):
    """Raised when player cannot be found."""


class CommitmentValidationError(CommitmentError):
    """Raised when request or commitment key is invalid."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _to_float(value: Decimal | int | float) -> float:
    return float(_q4(_d(value)))


def _day_to_date(day: int) -> date:
    return GAME_EPOCH + timedelta(days=max(0, int(day) - 1))


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise CommitmentValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise CommitmentNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise CommitmentNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, player: Player, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        return int(day), as_of_date
    latest_day = (
        db.query(func.max(DailySettlementLog.day_number))
        .filter(DailySettlementLog.player_id == player.id)
        .scalar()
    )
    if latest_day is None:
        latest_day = 1
    return int(latest_day), _day_to_date(int(latest_day))


def _parse_json(value: str | None, default):
    if not value:
        return default
    try:
        payload = json.loads(value)
    except Exception:
        return default
    return payload if isinstance(payload, type(default)) else default


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


def _alignment_label(score_0_to_1: Decimal) -> str:
    score = _clamp(score_0_to_1, Decimal("0.00"), Decimal("1.00"))
    if score >= Decimal("0.72"):
        return "aligned"
    if score >= Decimal("0.56"):
        return "mostly_aligned"
    if score >= Decimal("0.40"):
        return "drifting"
    return "off_track"


def _drift_level(score_0_to_1: Decimal, days_drifted: int) -> str:
    score = _clamp(score_0_to_1, Decimal("0.00"), Decimal("1.00"))
    if score < Decimal("0.30") or days_drifted >= 5:
        return "high"
    if score < Decimal("0.45") or days_drifted >= 3:
        return "moderate"
    if score < Decimal("0.58") or days_drifted >= 1:
        return "low"
    return "none"


def _risk_label(plan_key: str, confidence_label: str) -> str:
    key = str(plan_key or "").strip().lower()
    conf = str(confidence_label or "").strip().lower()
    if key in {"push_income", "lean_into_business"}:
        return "high" if conf in {"low", "moderate"} else "moderate"
    if key == "housing_optimization":
        return "moderate"
    if key == "reduce_stress":
        return "low"
    return "moderate" if conf == "low" else "low"


def _get_or_create_state(db: Session, player: Player) -> PlayerCommitmentState:
    state = (
        db.query(PlayerCommitmentState)
        .filter(PlayerCommitmentState.player_id == player.id)
        .first()
    )
    if state is not None:
        return state
    state = PlayerCommitmentState(
        player_id=player.id,
        status=INACTIVE_STATUS,
        adherence_score=Decimal("0"),
        momentum_score=Decimal("0"),
        days_followed=0,
        days_drifted=0,
    )
    db.add(state)
    db.flush()
    return state


def _state_is_active(state: PlayerCommitmentState | None) -> bool:
    if state is None:
        return False
    return str(state.status or "").lower() == ACTIVE_STATUS and bool(state.commitment_key)


def _collect_signals(db: Session, player: Player, day: int) -> dict:
    settlement = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number <= int(day),
        )
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    previous_settlement = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number <= max(1, int(day) - 1),
        )
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    daily_state = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number <= int(day),
        )
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .first()
    )
    distress = (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player.id,
            FinancialDistressLog.day <= int(day),
        )
        .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
        .first()
    )
    housing = (
        db.query(HousingDailyLog)
        .filter(
            HousingDailyLog.player_id == player.id,
            HousingDailyLog.day <= int(day),
        )
        .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
        .first()
    )
    business_rows_today = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day == int(day),
        )
        .all()
    )
    training_row = (
        db.query(CareerProgressLog)
        .filter(
            CareerProgressLog.player_id == player.id,
            CareerProgressLog.day_number == int(day),
        )
        .first()
    )

    job_actions_count = int(
        db.query(func.count(JobAction.id))
        .filter(
            JobAction.player_id == player.id,
            JobAction.day == int(day),
        )
        .scalar()
        or 0
    )
    side_income_hours = _d(
        db.query(func.coalesce(func.sum(SideIncomeAction.hours_worked), 0))
        .filter(
            SideIncomeAction.player_id == player.id,
            SideIncomeAction.day_number == int(day),
        )
        .scalar()
    )
    side_income_actions_count = int(
        db.query(func.count(SideIncomeAction.id))
        .filter(
            SideIncomeAction.player_id == player.id,
            SideIncomeAction.day_number == int(day),
        )
        .scalar()
        or 0
    )

    business_net_today = sum((_d(row.net_profit_xgp) for row in business_rows_today), Decimal("0"))
    business_runs_today = int(len(business_rows_today))

    stress_now = _d(player.stress)
    health_now = _d(player.health)
    productivity_now = _d(getattr(player, "productivity_modifier", 1))
    distress_score = _d(getattr(player, "distress_score", 0))
    distress_state = str(getattr(player, "distress_state", "stable") or "stable")

    if distress is not None:
        distress_score = _d(distress.distress_score_after)
        distress_state = str(distress.distress_state_after or distress_state)

    settlement_income = _d(getattr(settlement, "income_xgp", 0))
    settlement_expenses = _d(getattr(settlement, "expenses_xgp", 0))
    settlement_day = int(getattr(settlement, "day_number", 0) or 0)
    if settlement_day != int(day):
        settlement_income = Decimal("0")
        settlement_expenses = Decimal("0")
    net_today = settlement_income - settlement_expenses

    debt_due = _d(getattr(distress, "debt_payment_due_xgp", getattr(player, "required_daily_debt_payment_xgp", 0)))
    debt_paid = _d(getattr(distress, "debt_payment_paid_xgp", 0))
    debt_missed = bool(getattr(distress, "debt_payment_missed", False))
    if distress is None or int(getattr(distress, "day", 0) or 0) != int(day):
        debt_paid = Decimal("0")
        debt_missed = False

    recovery_hours = _d(getattr(daily_state, "recovery_hours", 0))
    overtime_hours = _d(getattr(daily_state, "overtime_hours", 0))
    sleep_hours = _d(getattr(daily_state, "sleep_hours", 7))
    commute_hours = _d(getattr(daily_state, "commute_hours", 0))
    if commute_hours <= Decimal("0") and housing is not None:
        commute_hours = _d(getattr(housing, "commute_hours", 0))

    housing_cost_daily = _d(getattr(settlement, "housing_cost_daily_xgp", 0))
    if housing_cost_daily <= Decimal("0") and housing is not None:
        housing_cost_daily = _d(getattr(housing, "housing_cost_xgp", 0))

    region_key = str(
        getattr(housing, "region", None)
        or getattr(settlement, "region_key", None)
        or player.region
        or "suburban"
    ).strip().lower()

    previous_stress = _d(getattr(previous_settlement, "stress_after", stress_now))
    previous_health = _d(getattr(previous_settlement, "health_after", health_now))

    return {
        "day": int(day),
        "stress": stress_now,
        "health": health_now,
        "productivity": productivity_now,
        "distress_score": distress_score,
        "distress_state": distress_state,
        "income_today": settlement_income,
        "expenses_today": settlement_expenses,
        "net_today": net_today,
        "debt_due": debt_due,
        "debt_paid": debt_paid,
        "debt_missed": debt_missed,
        "cash": _d(player.cash_xgp),
        "debt_total": _d(player.debt_xgp),
        "recovery_hours": recovery_hours,
        "overtime_hours": overtime_hours,
        "sleep_hours": sleep_hours,
        "commute_hours": commute_hours,
        "housing_cost_daily": housing_cost_daily,
        "region_key": region_key,
        "business_net_today": business_net_today,
        "business_runs_today": business_runs_today,
        "training_hours_today": _d(getattr(training_row, "training_hours", 0)),
        "job_actions_today": job_actions_count,
        "side_income_hours_today": side_income_hours,
        "side_income_actions_today": side_income_actions_count,
        "stress_trend_delta": stress_now - previous_stress,
        "health_trend_delta": health_now - previous_health,
    }


def _evaluate_key(
    commitment_key: str,
    signals: dict,
    action_key: str | None = None,
) -> dict:
    key = str(commitment_key or "").strip().lower()
    action = str(action_key or "").strip().lower()

    stress = _d(signals.get("stress"))
    health = _d(signals.get("health"))
    productivity = _d(signals.get("productivity"))
    distress_score = _d(signals.get("distress_score"))
    net_today = _d(signals.get("net_today"))
    debt_due = _d(signals.get("debt_due"))
    debt_paid = _d(signals.get("debt_paid"))
    debt_missed = bool(signals.get("debt_missed"))
    cash = _d(signals.get("cash"))
    recovery_hours = _d(signals.get("recovery_hours"))
    overtime_hours = _d(signals.get("overtime_hours"))
    sleep_hours = _d(signals.get("sleep_hours"))
    commute_hours = _d(signals.get("commute_hours"))
    housing_cost_daily = _d(signals.get("housing_cost_daily"))
    region_key = str(signals.get("region_key", "suburban"))
    business_net_today = _d(signals.get("business_net_today"))
    business_runs_today = int(signals.get("business_runs_today", 0) or 0)
    training_hours_today = _d(signals.get("training_hours_today"))
    job_actions_today = int(signals.get("job_actions_today", 0) or 0)
    side_income_actions_today = int(signals.get("side_income_actions_today", 0) or 0)

    stress_norm = _clamp((Decimal("100") - stress) / Decimal("100"), Decimal("0"), Decimal("1"))
    health_norm = _clamp(health / Decimal("100"), Decimal("0"), Decimal("1"))
    distress_norm = _clamp((Decimal("100") - distress_score) / Decimal("100"), Decimal("0"), Decimal("1"))

    alignment = Decimal("0.50")
    reasons: list[str] = []

    if key == "stabilize_finances":
        payment_ratio = Decimal("1.0")
        if debt_due > Decimal("0"):
            payment_ratio = _clamp(debt_paid / debt_due, Decimal("0"), Decimal("1"))
        cash_buffer = _clamp(cash / Decimal("350"), Decimal("0"), Decimal("1"))
        net_component = _clamp((net_today + Decimal("30")) / Decimal("120"), Decimal("0"), Decimal("1"))
        alignment = (
            payment_ratio * Decimal("0.42")
            + distress_norm * Decimal("0.24")
            + cash_buffer * Decimal("0.20")
            + net_component * Decimal("0.14")
        )
        if debt_missed:
            alignment -= Decimal("0.30")
            reasons.append("Debt payment was missed today.")
        if action in {"buy_inventory", "operate_business"} and distress_score >= Decimal("60"):
            alignment -= Decimal("0.08")
            reasons.append("Growth spending conflicted with debt-control focus.")
        if payment_ratio >= Decimal("0.95"):
            reasons.append("Debt obligations were covered on schedule.")

    elif key == "push_income":
        productive_actions = Decimal(str(job_actions_today + side_income_actions_today + business_runs_today))
        productive_score = _clamp(productive_actions / Decimal("3"), Decimal("0"), Decimal("1"))
        net_component = _clamp((net_today + Decimal("60")) / Decimal("180"), Decimal("0"), Decimal("1"))
        stamina = _clamp(stress_norm * Decimal("0.60") + health_norm * Decimal("0.40"), Decimal("0"), Decimal("1"))
        burnout_penalty = _clamp((stress - Decimal("78")) / Decimal("22"), Decimal("0"), Decimal("1")) + _clamp(
            overtime_hours / Decimal("5"),
            Decimal("0"),
            Decimal("1"),
        ) * Decimal("0.5")
        alignment = (
            productive_score * Decimal("0.45")
            + net_component * Decimal("0.30")
            + stamina * Decimal("0.25")
            - burnout_penalty * Decimal("0.20")
        )
        if action in {"rest", "recovery_action"}:
            alignment -= Decimal("0.05")
            reasons.append("Recovery action reduced income-push intensity for today.")
        if productive_actions >= Decimal("2"):
            reasons.append("Multiple productive actions supported the income push.")

    elif key == "reduce_stress":
        recovery_score = _clamp(recovery_hours / Decimal("2"), Decimal("0"), Decimal("1"))
        sleep_score = _clamp((sleep_hours - Decimal("4")) / Decimal("4"), Decimal("0"), Decimal("1"))
        stress_guard = _clamp((Decimal("82") - stress) / Decimal("42"), Decimal("0"), Decimal("1"))
        overwork_penalty = _clamp(overtime_hours / Decimal("4"), Decimal("0"), Decimal("1"))
        alignment = (
            recovery_score * Decimal("0.40")
            + sleep_score * Decimal("0.25")
            + stress_guard * Decimal("0.25")
            + health_norm * Decimal("0.10")
            - overwork_penalty * Decimal("0.22")
        )
        if action in {"work_shift", "side_income", "operate_business"}:
            alignment -= Decimal("0.08")
            reasons.append("High-pressure grind action conflicted with stress-reduction plan.")
        if action in {"rest", "recovery_action"}:
            alignment += Decimal("0.08")
            reasons.append("Recovery action aligned with the stress-reduction plan.")

    elif key == "invest_career":
        training_score = _clamp(training_hours_today / Decimal("2"), Decimal("0"), Decimal("1"))
        productivity_guard = _clamp((productivity - Decimal("0.70")) / Decimal("0.35"), Decimal("0"), Decimal("1"))
        stress_guard = _clamp((Decimal("86") - stress) / Decimal("46"), Decimal("0"), Decimal("1"))
        alignment = (
            training_score * Decimal("0.52")
            + productivity_guard * Decimal("0.24")
            + stress_guard * Decimal("0.24")
        )
        if action == "study":
            alignment += Decimal("0.10")
            reasons.append("Training action directly advanced this commitment.")
        if training_score <= Decimal("0.05"):
            reasons.append("No training logged today; career investment is drifting.")

    elif key == "lean_into_business":
        run_score = _clamp(Decimal(str(business_runs_today)), Decimal("0"), Decimal("1"))
        margin_score = _clamp((business_net_today + Decimal("35")) / Decimal("110"), Decimal("0"), Decimal("1"))
        liquidity_guard = _clamp((cash - Decimal("120")) / Decimal("420"), Decimal("0"), Decimal("1"))
        distress_penalty = _clamp((distress_score - Decimal("65")) / Decimal("35"), Decimal("0"), Decimal("1"))
        alignment = (
            run_score * Decimal("0.38")
            + margin_score * Decimal("0.36")
            + liquidity_guard * Decimal("0.26")
            - distress_penalty * Decimal("0.18")
        )
        if action == "operate_business":
            alignment += Decimal("0.10")
            reasons.append("Business operation aligned with this plan.")
        if business_runs_today == 0:
            reasons.append("No business run recorded today.")

    elif key == "housing_optimization":
        commute_relief = _clamp((Decimal("1.85") - commute_hours) / Decimal("1.55"), Decimal("0"), Decimal("1"))
        region_access = Decimal("0.90") if region_key == "downtown" else Decimal("0.45")
        stress_guard = _clamp((Decimal("80") - stress) / Decimal("40"), Decimal("0"), Decimal("1"))
        cost_penalty = Decimal("0")
        if housing_cost_daily >= Decimal("29") and cash < Decimal("220"):
            cost_penalty = Decimal("0.20")
        alignment = (
            commute_relief * Decimal("0.45")
            + region_access * Decimal("0.25")
            + stress_guard * Decimal("0.20")
            + distress_norm * Decimal("0.10")
            - cost_penalty
        )
        if action == "change_region":
            alignment += Decimal("0.10")
            reasons.append("Region/housing action supported commute optimization.")
        if commute_hours >= Decimal("1.45") and region_key == "suburban" and action != "change_region":
            alignment -= Decimal("0.10")
            reasons.append("Commute drag remains high; move/rent-closer option is still unaddressed.")

    else:
        alignment = _clamp(stress_norm * Decimal("0.40") + distress_norm * Decimal("0.60"), Decimal("0"), Decimal("1"))
        reasons.append("Fallback alignment used for unknown commitment key.")

    alignment = _clamp(alignment, Decimal("0"), Decimal("1"))
    alignment_label = _alignment_label(alignment)

    evaluation_summary = {
        "aligned": "You stayed aligned with today's commitment focus.",
        "mostly_aligned": "You are mostly on plan, but one driver needs attention.",
        "drifting": "Plan adherence is drifting; a corrective action is recommended.",
        "off_track": "You are off-plan today; course correction is needed.",
    }[alignment_label]

    return {
        "alignment_score": alignment,
        "alignment_label": alignment_label,
        "evaluation_summary": evaluation_summary,
        "reasons": reasons[:4],
        "debug_meta": {
            "commitment_key": key,
            "stress": _to_float(stress),
            "health": _to_float(health),
            "productivity": _to_float(productivity),
            "distress_score": _to_float(distress_score),
            "net_today_xgp": float(_money(net_today)),
            "overtime_hours": _to_float(overtime_hours),
            "recovery_hours": _to_float(recovery_hours),
            "sleep_hours": _to_float(sleep_hours),
            "commute_hours": _to_float(commute_hours),
            "housing_cost_daily_xgp": float(_money(housing_cost_daily)),
            "action_key": action or None,
        },
    }


def _serialize_active_commitment(
    player_id: UUID,
    as_of_date: date,
    state: PlayerCommitmentState | None,
    *,
    alignment_label: str = "none",
    drift_level: str = "none",
    suggested_correction: str | None = None,
    summary: str = "",
) -> dict:
    if not _state_is_active(state):
        return {
            "player_id": str(player_id),
            "as_of_date": as_of_date.isoformat(),
            "status": INACTIVE_STATUS,
            "commitment_key": "",
            "title": "No active commitment",
            "description": "Pick one short-horizon plan to start follow-through tracking.",
            "duration_days": 0,
            "start_date": None,
            "target_end_date": None,
            "days_remaining": 0,
            "adherence_score": 0.0,
            "momentum_score": 0.0,
            "alignment_label": "none",
            "drift_level": "none",
            "days_followed": 0,
            "days_drifted": 0,
            "likely_payoff": "Consistency signals unlock over multi-day discipline.",
            "likely_downside": "No commitment means less strategic momentum tracking.",
            "summary": "No active commitment selected.",
            "suggested_correction": "Choose a commitment to start multi-day follow-through.",
            "reward_summary": None,
            "debug_meta": {"state_status": getattr(state, "status", INACTIVE_STATUS)},
        }

    current_day = _date_to_day(as_of_date)
    days_remaining = max(0, int(state.target_end_day or current_day) - int(current_day) + 1)
    payoff, downside = COMMITMENT_PAYOFF_MAP.get(
        str(state.commitment_key),
        (
            "Maintaining alignment should improve short-horizon outcomes.",
            "Drift can reduce plan value over the horizon.",
        ),
    )
    return {
        "player_id": str(player_id),
        "as_of_date": as_of_date.isoformat(),
        "status": str(state.status),
        "commitment_key": str(state.commitment_key or ""),
        "title": str(state.title or ""),
        "description": str(state.description or ""),
        "duration_days": int(state.planned_duration_days or 0),
        "start_date": state.start_date.isoformat() if state.start_date else None,
        "target_end_date": state.target_end_date.isoformat() if state.target_end_date else None,
        "days_remaining": int(days_remaining),
        "adherence_score": _to_float(_d(state.adherence_score)),
        "momentum_score": _to_float(_d(state.momentum_score)),
        "alignment_label": alignment_label,
        "drift_level": drift_level,
        "days_followed": int(state.days_followed or 0),
        "days_drifted": int(state.days_drifted or 0),
        "likely_payoff": payoff,
        "likely_downside": downside,
        "summary": summary or str(state.completion_summary or ""),
        "suggested_correction": suggested_correction,
        "reward_summary": str(state.reward_summary or "") or None,
        "debug_meta": _parse_json(state.debug_json, {}) if state.debug_json else {},
    }


def _upsert_history_from_state(
    db: Session,
    *,
    player_id: UUID,
    state: PlayerCommitmentState,
    final_status: str,
    completed_on_day: int,
    completion_summary: str,
    reward_summary: str | None,
    main_driver: str,
    feedback_trace: list[dict] | None = None,
) -> PlayerCommitmentHistory:
    row = (
        db.query(PlayerCommitmentHistory)
        .filter(
            PlayerCommitmentHistory.player_id == player_id,
            PlayerCommitmentHistory.commitment_key == str(state.commitment_key or ""),
            PlayerCommitmentHistory.start_day == int(state.start_day or completed_on_day),
        )
        .first()
    )
    if row is None:
        row = PlayerCommitmentHistory(
            player_id=player_id,
            commitment_key=str(state.commitment_key or ""),
            title=str(state.title or ""),
            description=str(state.description or ""),
            start_day=int(state.start_day or completed_on_day),
            target_end_day=int(state.target_end_day or completed_on_day),
            planned_duration_days=int(state.planned_duration_days or 0),
            start_date=state.start_date,
            target_end_date=state.target_end_date,
        )
        db.add(row)

    row.status = str(final_status)
    row.adherence_score = _q4(_d(state.adherence_score))
    row.momentum_score = _q4(_d(state.momentum_score))
    row.days_followed = int(state.days_followed or 0)
    row.days_drifted = int(state.days_drifted or 0)
    row.completed_on_day = int(completed_on_day)
    row.completed_on_date = _day_to_date(int(completed_on_day))
    row.completion_summary = completion_summary
    row.reward_summary = reward_summary
    row.main_driver = main_driver
    row.feedback_trace_json = _dump_json(feedback_trace or [])
    row.debug_json = state.debug_json
    return row


def build_available_commitments(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build available commitment options from Step 28 short-horizon plans."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    plans = build_short_horizon_plan_options(db=db, player_id=player.id, as_of_date=resolved_date)

    items: list[dict] = []
    for option in plans.get("options", [])[:4]:
        key = str(option.get("plan_key", "")).strip()
        if not key:
            continue
        focus = COMMITMENT_FOCUS_MAP.get(key, ["Stay aligned with the plan's core tradeoff."])
        confidence = str(option.get("confidence_label", "moderate"))
        items.append(
            {
                "commitment_key": key,
                "title": str(option.get("title", key.replace("_", " ").title())),
                "description": str(option.get("short_description", "")),
                "suggested_duration_days": int(option.get("suggested_duration_days", DEFAULT_DURATION_DAYS)),
                "expected_upside": str(option.get("likely_upside", "")),
                "expected_downside": str(option.get("likely_downside", "")),
                "adherence_focus": focus,
                "current_fit_label": confidence,
                "risk_label": _risk_label(key, confidence),
                "debug_meta": {
                    "plan_debug_meta": option.get("debug_meta", {}),
                    "day": int(day),
                },
            }
        )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": items[:4],
        "debug_meta": {
            "source": "strategic_planning_service.build_short_horizon_plan_options",
            "option_count": len(items[:4]),
            "day": int(day),
        },
    }


def build_commitment_completion_or_failure(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    final_status_override: str | None = None,
    reason_override: str | None = None,
) -> dict:
    """Resolve active commitment into completed/failed/cancelled/replaced when required."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)
    if not _state_is_active(state):
        return {
            "final_status": INACTIVE_STATUS,
            "summary": "No active commitment to resolve.",
            "main_driver": "none",
            "next_recommended_commitment": None,
            "reward_summary": None,
            "debug_meta": {"day": int(day)},
        }

    adherence = _d(state.adherence_score)
    final_status = str(final_status_override or "").strip().lower()
    if final_status and final_status not in FINAL_STATUSES:
        raise CommitmentValidationError("Invalid final_status_override.")

    if not final_status:
        if int(day) < int(state.target_end_day or day) and adherence > Decimal("25"):
            return {
                "final_status": ACTIVE_STATUS,
                "summary": "Commitment remains active.",
                "main_driver": "horizon_incomplete",
                "next_recommended_commitment": None,
                "reward_summary": None,
                "debug_meta": {
                    "day": int(day),
                    "target_end_day": int(state.target_end_day or day),
                    "adherence_score": _to_float(adherence),
                },
            }
        if int(day) >= int(state.target_end_day or day):
            if adherence >= Decimal("68"):
                final_status = "completed"
            elif adherence >= Decimal("45"):
                final_status = "expired"
            else:
                final_status = "failed"
        elif adherence <= Decimal("25") and int(state.days_drifted or 0) >= 3:
            final_status = "failed"
        else:
            return {
                "final_status": ACTIVE_STATUS,
                "summary": "Commitment remains active.",
                "main_driver": "still_tracking",
                "next_recommended_commitment": None,
                "reward_summary": None,
                "debug_meta": {"day": int(day), "adherence_score": _to_float(adherence)},
            }

    reward_summary: str | None = None
    main_driver = str(reason_override or "")
    if not main_driver:
        main_driver = {
            "completed": "strong_adherence",
            "expired": "partial_follow_through",
            "failed": "sustained_drift",
            "cancelled": "player_cancelled",
            "replaced": "player_replaced",
        }.get(final_status, "manual_resolution")

    if final_status == "completed":
        player.stress = _clamp_int(int(player.stress or 0) - 1, 0, 100)
        reward_summary = "Consistency marker awarded. Stress relieved by 1."
    elif final_status == "expired":
        reward_summary = "Partial follow-through recorded."
    elif final_status == "failed":
        reward_summary = "No reward. Review drift warnings and reset focus."
    elif final_status in {"cancelled", "replaced"}:
        reward_summary = "Commitment closed before term."

    completion_summary = reason_override or {
        "completed": "Commitment completed with disciplined follow-through.",
        "expired": "Commitment window ended with partial adherence.",
        "failed": "Commitment failed due to repeated drift.",
        "cancelled": "Commitment cancelled by player choice.",
        "replaced": "Commitment replaced by a new plan.",
    }.get(final_status, "Commitment finalized.")

    _upsert_history_from_state(
        db,
        player_id=player.id,
        state=state,
        final_status=final_status,
        completed_on_day=int(day),
        completion_summary=completion_summary,
        reward_summary=reward_summary,
        main_driver=main_driver,
        feedback_trace=[
            {
                "day": int(day),
                "status": final_status,
                "adherence_score": _to_float(adherence),
                "momentum_score": _to_float(_d(state.momentum_score)),
            }
        ],
    )

    state.status = final_status
    state.completion_summary = completion_summary
    state.reward_summary = reward_summary
    state.last_evaluated_on = int(day)
    state.debug_json = _dump_json(
        {
            **(_parse_json(state.debug_json, {}) if state.debug_json else {}),
            "finalized_on_day": int(day),
            "final_status": final_status,
            "main_driver": main_driver,
            "reward_summary": reward_summary,
        }
    )
    db.flush()

    recommendation = build_player_strategy_recommendation(db=db, player_id=player.id, as_of_date=resolved_date)
    return {
        "final_status": final_status,
        "summary": completion_summary,
        "main_driver": main_driver,
        "next_recommended_commitment": recommendation.get("recommended_plan_key"),
        "reward_summary": reward_summary,
        "debug_meta": {
            "day": int(day),
            "adherence_score": _to_float(adherence),
            "momentum_score": _to_float(_d(state.momentum_score)),
        },
    }


def activate_player_commitment(
    db: Session,
    player_id: str | UUID,
    commitment_key: str,
    *,
    duration_days: int = DEFAULT_DURATION_DAYS,
    replace_active: bool = False,
    as_of_date: date | None = None,
) -> dict:
    """Activate one commitment for a player, optionally replacing an active one."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    duration = _clamp_int(int(duration_days), MIN_DURATION_DAYS, MAX_DURATION_DAYS)

    available_payload = build_available_commitments(db=db, player_id=player.id, as_of_date=resolved_date)
    available = {str(item["commitment_key"]): item for item in available_payload.get("items", [])}
    selected = available.get(str(commitment_key))
    if selected is None:
        raise CommitmentValidationError("Selected commitment_key is not currently available for this player.")

    state = _get_or_create_state(db, player)
    if _state_is_active(state):
        if not replace_active:
            raise CommitmentValidationError("Player already has an active commitment. Use replace endpoint.")
        build_commitment_completion_or_failure(
            db=db,
            player_id=player.id,
            as_of_date=resolved_date,
            final_status_override="replaced",
            reason_override="Active commitment replaced by player.",
        )

    target_end_day = int(day) + int(duration) - 1
    recommendation = build_player_strategy_recommendation(db=db, player_id=player.id, as_of_date=resolved_date)
    state.commitment_key = str(selected["commitment_key"])
    state.title = str(selected["title"])
    state.description = str(selected["description"])
    state.start_day = int(day)
    state.target_end_day = int(target_end_day)
    state.planned_duration_days = int(duration)
    state.start_date = resolved_date
    state.target_end_date = _day_to_date(target_end_day)
    state.status = ACTIVE_STATUS
    state.adherence_score = _q4(DEFAULT_ADHERENCE_SCORE)
    state.momentum_score = _q4(DEFAULT_MOMENTUM_SCORE)
    state.days_followed = 0
    state.days_drifted = 0
    state.last_evaluated_on = None
    state.completion_summary = None
    state.reward_summary = None
    state.initial_context_json = _dump_json(
        {
            "activated_on_day": int(day),
            "available_commitment_debug": selected.get("debug_meta", {}),
            "strategy_recommendation": recommendation,
        }
    )
    state.debug_json = _dump_json(
        {
            "activated_on_day": int(day),
            "replace_active": bool(replace_active),
            "duration_days": int(duration),
            "expected_upside": selected.get("expected_upside"),
            "expected_downside": selected.get("expected_downside"),
        }
    )
    db.flush()

    return _serialize_active_commitment(
        player.id,
        resolved_date,
        state,
        alignment_label="mostly_aligned",
        drift_level="none",
        suggested_correction=None,
        summary="Commitment activated. Follow-through tracking is now live.",
    )


def evaluate_commitment_adherence(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    action_key: str | None = None,
) -> dict:
    """Compute current adherence/momentum deltas for the active commitment."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)
    if not _state_is_active(state):
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "has_active_commitment": False,
            "adherence_delta": 0.0,
            "momentum_delta": 0.0,
            "evaluation_summary": "No active commitment selected.",
            "alignment_label": "none",
            "debug_meta": {"day": int(day)},
        }

    signals = _collect_signals(db, player, day)
    eval_payload = _evaluate_key(str(state.commitment_key), signals, action_key=action_key)
    alignment = _d(eval_payload["alignment_score"])
    target_adherence = _clamp(alignment * Decimal("100"), Decimal("0"), Decimal("100"))
    current_adherence = _d(state.adherence_score)

    if int(state.last_evaluated_on or 0) != int(day):
        adherence_delta = (target_adherence - current_adherence) * Decimal("0.35")
    elif action_key:
        adherence_delta = (target_adherence - current_adherence) * Decimal("0.12")
    else:
        adherence_delta = Decimal("0")
    adherence_delta = _clamp(adherence_delta, Decimal("-8.0"), Decimal("8.0"))

    momentum_base = (alignment - Decimal("0.50")) * Decimal("6.0")
    if action_key:
        if action_key in {"rest", "recovery_action", "study", "operate_business", "change_region", "debt_payment"}:
            momentum_base += Decimal("0.8")
        elif action_key in {"buy_inventory", "side_income", "work_shift"} and alignment < Decimal("0.45"):
            momentum_base -= Decimal("0.8")
    if int(state.last_evaluated_on or 0) == int(day) and not action_key:
        momentum_base = Decimal("0")
    momentum_delta = _clamp(momentum_base, Decimal("-4.0"), Decimal("4.0"))

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "has_active_commitment": True,
        "adherence_delta": _to_float(adherence_delta),
        "momentum_delta": _to_float(momentum_delta),
        "evaluation_summary": str(eval_payload["evaluation_summary"]),
        "alignment_label": str(eval_payload["alignment_label"]),
        "debug_meta": {
            "day": int(day),
            "target_adherence_score": _to_float(target_adherence),
            "current_adherence_score": _to_float(current_adherence),
            "alignment_score": _to_float(alignment),
            "signals": eval_payload["debug_meta"],
            "reasons": eval_payload.get("reasons", []),
        },
    }


def detect_commitment_drift(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Detect whether behavior is drifting from the active commitment."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)
    if not _state_is_active(state):
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "drift_level": "none",
            "drift_reasons": [],
            "corrective_suggestion": "Choose one commitment to enable drift tracking.",
            "should_warn_player": False,
            "debug_meta": {"day": int(day)},
        }

    signals = _collect_signals(db, player, day)
    eval_payload = _evaluate_key(str(state.commitment_key), signals, action_key=None)
    score = _d(eval_payload["alignment_score"])
    drift = _drift_level(score, int(state.days_drifted or 0))
    reasons = list(eval_payload.get("reasons", []))

    key = str(state.commitment_key or "")
    if key == "reduce_stress" and _d(signals.get("stress")) >= Decimal("76"):
        reasons.append("Stress is still elevated while on Reduce Stress commitment.")
    if key == "stabilize_finances" and bool(signals.get("debt_missed")):
        reasons.append("Debt payment miss directly conflicts with finance stabilization.")
    if key == "housing_optimization" and _d(signals.get("commute_hours")) >= Decimal("1.45"):
        reasons.append("Commute burden remains high; move/rent-closer tradeoff is unresolved.")

    correction = COMMITMENT_CORRECTION_MAP.get(
        key,
        "Take one action tomorrow that directly supports your chosen commitment.",
    )
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "drift_level": drift,
        "drift_reasons": reasons[:5],
        "corrective_suggestion": correction,
        "should_warn_player": drift in {"moderate", "high"},
        "debug_meta": {
            "day": int(day),
            "alignment_score": _to_float(score),
            "alignment_label": eval_payload.get("alignment_label"),
            "days_drifted": int(state.days_drifted or 0),
        },
    }


def evaluate_commitment_progress(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    action_key: str | None = None,
) -> dict:
    """Persist daily commitment adherence/momentum updates."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)
    if not _state_is_active(state):
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "has_active_commitment": False,
            "adherence_delta": 0.0,
            "momentum_delta": 0.0,
            "evaluation_summary": "No active commitment selected.",
            "alignment_label": "none",
            "debug_meta": {"day": int(day)},
        }

    adherence_eval = evaluate_commitment_adherence(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        action_key=action_key,
    )
    adherence_delta = _d(adherence_eval.get("adherence_delta", 0))
    momentum_delta = _d(adherence_eval.get("momentum_delta", 0))
    current_adherence = _d(state.adherence_score)
    current_momentum = _d(state.momentum_score)
    new_adherence = _clamp(current_adherence + adherence_delta, Decimal("0"), Decimal("100"))
    new_momentum = _clamp(current_momentum + momentum_delta, Decimal("0"), Decimal("100"))

    state.adherence_score = _q4(new_adherence)
    state.momentum_score = _q4(new_momentum)
    if int(state.last_evaluated_on or 0) != int(day):
        if new_adherence >= Decimal("55"):
            state.days_followed = int(state.days_followed or 0) + 1
        else:
            state.days_drifted = int(state.days_drifted or 0) + 1
        state.last_evaluated_on = int(day)

    drift_payload = detect_commitment_drift(db=db, player_id=player.id, as_of_date=resolved_date)
    state.debug_json = _dump_json(
        {
            **(_parse_json(state.debug_json, {}) if state.debug_json else {}),
            "last_progress_update_day": int(day),
            "last_action_key": action_key,
            "alignment_label": adherence_eval.get("alignment_label"),
            "drift_level": drift_payload.get("drift_level"),
            "adherence_delta": _to_float(adherence_delta),
            "momentum_delta": _to_float(momentum_delta),
        }
    )
    db.flush()

    completion_payload = build_commitment_completion_or_failure(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "has_active_commitment": _state_is_active(state),
        "adherence_delta": _to_float(adherence_delta),
        "momentum_delta": _to_float(momentum_delta),
        "evaluation_summary": adherence_eval.get("evaluation_summary", ""),
        "alignment_label": adherence_eval.get("alignment_label", "none"),
        "drift_level": drift_payload.get("drift_level", "none"),
        "drift_reasons": drift_payload.get("drift_reasons", []),
        "should_warn_player": bool(drift_payload.get("should_warn_player", False)),
        "suggested_correction": drift_payload.get("corrective_suggestion"),
        "completion": completion_payload,
        "debug_meta": {
            "day": int(day),
            "adherence_before": _to_float(current_adherence),
            "adherence_after": _to_float(new_adherence),
            "momentum_before": _to_float(current_momentum),
            "momentum_after": _to_float(new_momentum),
            "adherence_eval_debug": adherence_eval.get("debug_meta", {}),
            "drift_debug": drift_payload.get("debug_meta", {}),
        },
    }


def build_commitment_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    evaluate: bool = True,
) -> dict:
    """Build frontend-friendly active commitment summary."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)

    progress_payload: dict = {}
    if evaluate and _state_is_active(state):
        progress_payload = evaluate_commitment_progress(
            db=db,
            player_id=player.id,
            as_of_date=resolved_date,
            action_key=None,
        )
        state = _get_or_create_state(db, player)

    drift_payload = detect_commitment_drift(db=db, player_id=player.id, as_of_date=resolved_date)
    summary_text = (
        "No active commitment selected."
        if not _state_is_active(state)
        else (
            "Commitment on track."
            if drift_payload.get("drift_level") in {"none", "low"}
            else "Commitment drifting; corrective move is recommended."
        )
    )
    active_payload = _serialize_active_commitment(
        player.id,
        resolved_date,
        state,
        alignment_label=str(progress_payload.get("alignment_label") or drift_payload.get("debug_meta", {}).get("alignment_label") or "none"),
        drift_level=str(drift_payload.get("drift_level", "none")),
        suggested_correction=drift_payload.get("corrective_suggestion"),
        summary=summary_text,
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "active_commitment": active_payload,
        "debug_meta": {
            "progress_payload": progress_payload,
            "drift_payload": drift_payload,
        },
    }


def build_commitment_feedback(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build compact commitment feedback items (on-track vs drifting guidance)."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)
    if not _state_is_active(state):
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "items": [
                {
                    "severity": "info",
                    "title": "No active commitment",
                    "body": "Pick one 3-7 day commitment to start follow-through tracking.",
                    "commitment_key": "",
                    "feedback_type": "inactive",
                    "suggested_correction": "Choose one commitment from available options.",
                    "debug_meta": {"day": int(day)},
                }
            ],
            "debug_meta": {"day": int(day)},
        }

    drift = detect_commitment_drift(db=db, player_id=player.id, as_of_date=resolved_date)
    level = str(drift.get("drift_level", "none"))
    adherence = _d(state.adherence_score)
    momentum = _d(state.momentum_score)

    if level in {"none", "low"}:
        severity = "success"
        title = f"On track: {state.title}"
        body = (
            f"Adherence {float(_q4(adherence)):.1f}, momentum {float(_q4(momentum)):.1f}. "
            "Keep stacking aligned actions."
        )
        feedback_type = "on_track"
    elif level == "moderate":
        severity = "warning"
        title = f"Drift warning: {state.title}"
        body = "Your recent actions are drifting from the commitment tradeoff."
        feedback_type = "drifting"
    else:
        severity = "critical"
        title = f"Off plan: {state.title}"
        body = "Commitment alignment is weak. Correct course before momentum collapses."
        feedback_type = "off_track"

    items = [
        {
            "severity": severity,
            "title": title,
            "body": body,
            "commitment_key": str(state.commitment_key or ""),
            "feedback_type": feedback_type,
            "suggested_correction": drift.get("corrective_suggestion"),
            "debug_meta": {
                "day": int(day),
                "drift_level": level,
                "adherence_score": _to_float(adherence),
                "momentum_score": _to_float(momentum),
            },
        }
    ]

    for reason in drift.get("drift_reasons", [])[:2]:
        items.append(
            {
                "severity": "info",
                "title": "Driver",
                "body": str(reason),
                "commitment_key": str(state.commitment_key or ""),
                "feedback_type": "driver",
                "suggested_correction": None,
                "debug_meta": {"day": int(day)},
            }
        )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": items,
        "debug_meta": {"drift_payload": drift, "day": int(day)},
    }


def get_player_active_commitment(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return active commitment state without forcing an evaluation cycle."""
    summary = build_commitment_summary(db=db, player_id=player_id, as_of_date=as_of_date, evaluate=False)
    return summary["active_commitment"]


def get_player_commitment_history(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    limit: int = 20,
) -> dict:
    """Return recent commitment history rows."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    rows = (
        db.query(PlayerCommitmentHistory)
        .filter(PlayerCommitmentHistory.player_id == player.id)
        .order_by(
            PlayerCommitmentHistory.completed_on_day.desc().nullslast(),
            PlayerCommitmentHistory.updated_at.desc(),
        )
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    entries: list[dict] = []
    for row in rows:
        entries.append(
            {
                "commitment_key": str(row.commitment_key),
                "title": str(row.title),
                "status": str(row.status),
                "start_date": row.start_date.isoformat() if row.start_date else None,
                "target_end_date": row.target_end_date.isoformat() if row.target_end_date else None,
                "completed_on_date": row.completed_on_date.isoformat() if row.completed_on_date else None,
                "adherence_score": _to_float(_d(row.adherence_score)),
                "momentum_score": _to_float(_d(row.momentum_score)),
                "days_followed": int(row.days_followed or 0),
                "days_drifted": int(row.days_drifted or 0),
                "completion_summary": str(row.completion_summary or "") or None,
                "reward_summary": str(row.reward_summary or "") or None,
                "debug_meta": _parse_json(row.debug_json, {}) if row.debug_json else {},
            }
        )
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "entries": entries,
        "debug_meta": {
            "history_count": len(entries),
            "limit": int(max(1, min(int(limit), 100))),
        },
    }


def cancel_player_commitment(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Cancel the current active commitment."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player)
    if not _state_is_active(state):
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "status": INACTIVE_STATUS,
            "summary": "No active commitment to cancel.",
            "debug_meta": {},
        }
    completion = build_commitment_completion_or_failure(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        final_status_override="cancelled",
        reason_override="Commitment cancelled by player.",
    )
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "status": completion.get("final_status", "cancelled"),
        "summary": completion.get("summary", "Commitment cancelled."),
        "debug_meta": completion.get("debug_meta", {}),
    }
