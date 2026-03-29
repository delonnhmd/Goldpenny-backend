"""Step 26 progression service: goals, missions, streaks, and retention rewards."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_goal_history import PlayerGoalHistory
from app.models.player_progression_state import PlayerProgressionState
from app.models.side_income_action import SideIncomeAction

GAME_EPOCH = date(2026, 1, 1)
MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

DAILY_SCOPE = "daily"
WEEKLY_SCOPE = "weekly"
STREAK_SCOPE = "streak"

DAILY_REWARD_RULES: dict[str, dict] = {
    "productive_actions_2": {"stress_relief": 1, "reward_summary": "Momentum badge + small morale relief"},
    "stress_below_70": {"stress_relief": 2, "reward_summary": "Calm-day badge + moderate stress relief"},
    "positive_net_cash_today": {"reputation_bump": 1, "reward_summary": "Discipline marker + confidence bump"},
    "business_progress_today": {"reputation_bump": 1, "reward_summary": "Operator consistency marker"},
    "training_session_today": {"stress_relief": 1, "reward_summary": "Learning momentum marker"},
    "avoid_elevated_distress_today": {"stress_relief": 1, "reward_summary": "Stability marker"},
    "recovery_action_today": {"stress_relief": 2, "reward_summary": "Recovery marker + stress relief"},
}

WEEKLY_REWARD_RULES: dict[str, dict] = {
    "weekly_income_target": {"stress_relief": 2, "reputation_bump": 1, "reward_summary": "Weekly earnings milestone"},
    "weekly_debt_reduction": {"stress_relief": 2, "reward_summary": "Debt-control milestone"},
    "weekly_training_sessions": {"reputation_bump": 1, "productivity_base_bump": Decimal("0.0020"), "reward_summary": "Skill discipline milestone"},
    "weekly_profitable_business_days": {"reputation_bump": 2, "reward_summary": "Business consistency milestone"},
    "weekly_work_shifts": {"stress_relief": 1, "reward_summary": "Work consistency milestone"},
    "weekly_low_stress_days": {"stress_relief": 2, "reward_summary": "Balance milestone"},
}

STREAK_ORDER = [
    ("login_play_streak", "login_streak"),
    ("productive_day_streak", "productive_day_streak"),
    ("positive_cash_flow_streak", "positive_cash_flow_streak"),
    ("training_streak", "training_streak"),
    ("business_consistency_streak", "business_consistency_streak"),
    ("low_distress_streak", "low_distress_streak"),
]


class ProgressionError(Exception):
    """Base progression exception."""


class ProgressionNotFoundError(ProgressionError):
    """Raised when player is missing."""


class ProgressionValidationError(ProgressionError):
    """Raised for invalid progression inputs."""


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


def _day_to_date(day: int) -> date:
    return GAME_EPOCH + timedelta(days=max(0, int(day) - 1))


def _date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _week_bounds(day: int) -> tuple[int, int]:
    week_start = ((int(day) - 1) // 7) * 7 + 1
    return week_start, week_start + 6


def _parse_json(value: str | None, default):
    if not value:
        return default
    try:
        payload = json.loads(value)
    except Exception:
        return default
    return payload if isinstance(payload, type(default)) else default


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ProgressionNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise ProgressionNotFoundError("Player not found.")
    return player


def _resolve_day(player: Player, db: Session, as_of_date: date | None, day_number: int | None = None) -> tuple[int, date]:
    if day_number is not None:
        day = int(day_number)
        if day <= 0:
            raise ProgressionValidationError("day_number must be greater than 0.")
        return day, _day_to_date(day)
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        if day <= 0:
            raise ProgressionValidationError("as_of_date must be on or after game epoch.")
        return day, as_of_date

    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


def _is_day_settled(db: Session, player_id: UUID, day: int) -> bool:
    row = (
        db.query(DailySettlementLog.id)
        .filter(
            DailySettlementLog.player_id == player_id,
            DailySettlementLog.day_number == int(day),
        )
        .first()
    )
    return row is not None


def _get_or_create_progression_state(db: Session, player: Player, day: int) -> PlayerProgressionState:
    state = db.query(PlayerProgressionState).filter(PlayerProgressionState.player_id == player.id).first()
    if state is not None:
        return state

    week_start, week_end = _week_bounds(day)
    state = PlayerProgressionState(
        player_id=player.id,
        current_day=int(day),
        current_week_start_day=int(week_start),
        current_week_end_day=int(week_end),
        week_start_debt_xgp=_money(_d(getattr(player, "debt_xgp", 0))),
        week_start_cash_xgp=_money(_d(getattr(player, "cash_xgp", 0))),
        recently_completed_json="[]",
        reward_trace_json="[]",
        last_action_digest_json="{}",
    )
    db.add(state)
    db.flush()
    return state


def _sync_week_window(state: PlayerProgressionState, player: Player, day: int) -> bool:
    week_start, week_end = _week_bounds(day)
    if int(state.current_week_start_day or 0) == week_start:
        return False
    state.current_week_start_day = int(week_start)
    state.current_week_end_day = int(week_end)
    state.week_start_debt_xgp = _money(_d(getattr(player, "debt_xgp", 0)))
    state.week_start_cash_xgp = _money(_d(getattr(player, "cash_xgp", 0)))
    return True


def _append_recent_completion(state: PlayerProgressionState, item: dict) -> None:
    entries = _parse_json(getattr(state, "recently_completed_json", None), [])
    if not isinstance(entries, list):
        entries = []
    dedupe_key = f"{item.get('scope')}::{item.get('key')}::{item.get('day')}"
    existing_keys = {f"{e.get('scope')}::{e.get('key')}::{e.get('day')}" for e in entries if isinstance(e, dict)}
    if dedupe_key in existing_keys:
        return
    entries.insert(0, item)
    state.recently_completed_json = json.dumps(entries[:20], sort_keys=True)


def _append_reward_trace(state: PlayerProgressionState, trace: dict) -> None:
    entries = _parse_json(getattr(state, "reward_trace_json", None), [])
    if not isinstance(entries, list):
        entries = []
    entries.insert(0, trace)
    state.reward_trace_json = json.dumps(entries[:25], sort_keys=True)


def _get_daily_state(db: Session, player_id: UUID, day: int) -> PlayerDailyState | None:
    return (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player_id,
            PlayerDailyState.day_number == int(day),
        )
        .order_by(PlayerDailyState.created_at.desc())
        .first()
    )


def _collect_day_signals(db: Session, player: Player, day: int) -> dict:
    pds = _get_daily_state(db, player.id, day)
    has_business = (
        db.query(PlayerBusiness.id)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.is_active.is_(True),
        )
        .first()
        is not None
    )
    business_runs = int(
        db.query(BusinessDailyLog.id)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day == int(day),
        )
        .count()
        or 0
    )
    profitable_business_runs = int(
        db.query(BusinessDailyLog.id)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day == int(day),
            BusinessDailyLog.net_profit_xgp > Decimal("0"),
        )
        .count()
        or 0
    )
    job_actions = int(
        db.query(JobAction.id)
        .filter(
            JobAction.player_id == player.id,
            JobAction.day == int(day),
        )
        .count()
        or 0
    )
    side_income_actions = int(
        db.query(SideIncomeAction.id)
        .filter(
            SideIncomeAction.player_id == player.id,
            SideIncomeAction.day_number == int(day),
        )
        .count()
        or 0
    )
    training_log = (
        db.query(CareerProgressLog)
        .filter(
            CareerProgressLog.player_id == player.id,
            CareerProgressLog.day_number == int(day),
        )
        .order_by(CareerProgressLog.created_at.desc())
        .first()
    )
    training_hours = _q4(_d(getattr(training_log, "training_hours", 0)))
    recovery_queue = _parse_json(getattr(player, "recovery_actions_json", None), [])
    recovery_actions_count = len(recovery_queue) if isinstance(recovery_queue, list) else 0
    productive_actions_count = int(job_actions + side_income_actions + business_runs)
    if training_hours > Decimal("0"):
        productive_actions_count += 1
    if recovery_actions_count > 0:
        productive_actions_count += 1

    cash_now = _money(_d(getattr(player, "cash_xgp", 0)))
    cash_start = _money(_d(getattr(pds, "cash_start", cash_now)))
    cash_delta_today = _money(cash_now - cash_start)

    settlement = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number == int(day),
        )
        .order_by(DailySettlementLog.created_at.desc())
        .first()
    )

    return {
        "day": int(day),
        "pds": pds,
        "settlement": settlement,
        "has_active_business": bool(has_business),
        "business_runs_today": int(business_runs),
        "profitable_business_runs_today": int(profitable_business_runs),
        "job_actions_today": int(job_actions),
        "side_income_actions_today": int(side_income_actions),
        "training_hours_today": training_hours,
        "recovery_actions_count": int(recovery_actions_count),
        "productive_actions_today": int(productive_actions_count),
        "cash_delta_today_xgp": cash_delta_today,
        "stress_now": int(getattr(player, "stress", 0) or 0),
        "health_now": int(getattr(player, "health", 100) or 100),
        "burnout_risk": _q4(_d(getattr(player, "burnout_risk", 0))),
        "distress_state": str(getattr(player, "distress_state", "stable") or "stable"),
        "distress_score": _q4(_d(getattr(player, "distress_score", 0))),
        "on_payment_plan": bool(getattr(player, "on_payment_plan", False)),
    }


def _daily_goal_templates(day_signals: dict) -> list[dict]:
    templates: list[dict] = []
    templates.append(
        {
            "goal_key": "productive_actions_2",
            "title": "Complete 2 productive actions",
            "description": "Chain two meaningful actions today to keep momentum.",
            "progress_current": Decimal(day_signals["productive_actions_today"]),
            "progress_target": Decimal("2"),
            "urgency": "medium",
            "category": "discipline",
        }
    )

    high_pressure = int(day_signals["stress_now"]) >= 65 or _d(day_signals["burnout_risk"]) >= Decimal("0.25")
    if high_pressure:
        templates.append(
            {
                "goal_key": "stress_below_70",
                "title": "Finish with stress below 70",
                "description": "Stabilize pressure so tomorrow's productivity does not slip.",
                "progress_current": Decimal("1") if int(day_signals["stress_now"]) < 70 else Decimal("0"),
                "progress_target": Decimal("1"),
                "urgency": "high",
                "category": "life_balance",
            }
        )
    else:
        templates.append(
            {
                "goal_key": "positive_net_cash_today",
                "title": "End today with positive cash flow",
                "description": "Keep today's actions net positive to sustain runway.",
                "progress_current": Decimal("1") if _d(day_signals["cash_delta_today_xgp"]) > Decimal("0") else Decimal("0"),
                "progress_target": Decimal("1"),
                "urgency": "medium",
                "category": "finance",
            }
        )

    if bool(day_signals["has_active_business"]):
        templates.append(
            {
                "goal_key": "business_progress_today",
                "title": "Operate business once today",
                "description": "Maintain operating consistency and keep customer rhythm.",
                "progress_current": Decimal(day_signals["business_runs_today"]),
                "progress_target": Decimal("1"),
                "urgency": "medium",
                "category": "business",
            }
        )
    elif int(day_signals.get("stress_now", 0)) >= 75:
        templates.append(
            {
                "goal_key": "recovery_action_today",
                "title": "Queue a recovery action",
                "description": "High pressure detected; schedule one recovery action today.",
                "progress_current": Decimal("1") if int(day_signals["recovery_actions_count"]) > 0 else Decimal("0"),
                "progress_target": Decimal("1"),
                "urgency": "high",
                "category": "recovery",
            }
        )
    else:
        templates.append(
            {
                "goal_key": "training_session_today",
                "title": "Log one training session",
                "description": "Small daily training keeps career growth compounding.",
                "progress_current": Decimal("1") if _d(day_signals["training_hours_today"]) > Decimal("0") else Decimal("0"),
                "progress_target": Decimal("1"),
                "urgency": "low",
                "category": "career",
            }
        )

    return templates[:3]


def _collect_week_signals(db: Session, player: Player, week_start: int, week_end: int) -> dict:
    settlements = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number >= int(week_start),
            DailySettlementLog.day_number <= int(week_end),
        )
        .order_by(DailySettlementLog.day_number.asc(), DailySettlementLog.created_at.asc())
        .all()
    )
    income_total = sum((_d(getattr(row, "income_xgp", 0)) for row in settlements), Decimal("0"))
    low_stress_days = sum(
        1
        for row in settlements
        if int(getattr(row, "stress_after", 0) or 0) <= 70
    )

    distress_logs = (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player.id,
            FinancialDistressLog.day >= int(week_start),
            FinancialDistressLog.day <= int(week_end),
        )
        .order_by(FinancialDistressLog.day.asc(), FinancialDistressLog.created_at.asc())
        .all()
    )
    missed_finance_days = sum(1 for row in distress_logs if bool(getattr(row, "debt_payment_missed", False)))

    training_sessions = int(
        db.query(CareerProgressLog.id)
        .filter(
            CareerProgressLog.player_id == player.id,
            CareerProgressLog.day_number >= int(week_start),
            CareerProgressLog.day_number <= int(week_end),
            CareerProgressLog.training_hours > Decimal("0"),
        )
        .count()
        or 0
    )
    work_shifts = int(
        db.query(JobAction.id)
        .filter(
            JobAction.player_id == player.id,
            JobAction.day >= int(week_start),
            JobAction.day <= int(week_end),
        )
        .count()
        or 0
    )
    profitable_business_days = int(
        db.query(BusinessDailyLog.day)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day >= int(week_start),
            BusinessDailyLog.day <= int(week_end),
            BusinessDailyLog.net_profit_xgp > Decimal("0"),
        )
        .distinct()
        .count()
        or 0
    )
    trailing_settlements = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == player.id)
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .limit(14)
        .all()
    )
    trailing_income_avg = Decimal("0")
    if trailing_settlements:
        trailing_income_avg = sum((_d(getattr(row, "income_xgp", 0)) for row in trailing_settlements), Decimal("0")) / Decimal(
            str(max(1, len(trailing_settlements)))
        )

    has_business = (
        db.query(PlayerBusiness.id)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.is_active.is_(True),
        )
        .first()
        is not None
    )
    career_state = db.query(PlayerCareer).filter(PlayerCareer.player_id == player.id).first()

    return {
        "income_total_xgp": _money(income_total),
        "low_stress_days": int(low_stress_days),
        "missed_finance_days": int(missed_finance_days),
        "training_sessions": int(training_sessions),
        "work_shifts": int(work_shifts),
        "profitable_business_days": int(profitable_business_days),
        "trailing_income_avg_xgp": _money(trailing_income_avg),
        "has_active_business": bool(has_business),
        "career_state": career_state,
        "settlement_rows": len(settlements),
    }


def _status_from_progress(progress_current: Decimal, progress_target: Decimal, *, settled: bool) -> str:
    if progress_current >= progress_target:
        return "completed"
    if settled:
        return "failed"
    if progress_current > Decimal("0"):
        return "in_progress"
    return "not_started"


def _apply_reward(player: Player, reward_payload: dict, *, scope: str) -> dict:
    stress_relief = int(reward_payload.get("stress_relief", 0) or 0)
    reputation_bump = int(reward_payload.get("reputation_bump", 0) or 0)
    productivity_base_bump = _q4(_d(reward_payload.get("productivity_base_bump", 0)))

    before_stress = int(getattr(player, "stress", 0) or 0)
    before_rep = int(getattr(player, "reputation", 0) or 0)
    before_base_prod = _q4(_d(getattr(player, "base_productivity_modifier", 1)))

    if stress_relief > 0:
        player.stress = _clamp_int(before_stress - stress_relief, 0, 100)
    if reputation_bump > 0:
        player.reputation = _clamp_int(before_rep + reputation_bump, 0, 100)
    if productivity_base_bump > Decimal("0"):
        player.base_productivity_modifier = _q4(
            _clamp(before_base_prod + productivity_base_bump, Decimal("0.70"), Decimal("1.08"))
        )
        player.productivity_modifier = _q4(
            _clamp(_d(getattr(player, "productivity_modifier", 1)), Decimal("0.70"), _d(player.base_productivity_modifier))
        )

    return {
        "scope": scope,
        "stress_before": before_stress,
        "stress_after": int(getattr(player, "stress", before_stress) or before_stress),
        "reputation_before": before_rep,
        "reputation_after": int(getattr(player, "reputation", before_rep) or before_rep),
        "base_productivity_before": float(before_base_prod),
        "base_productivity_after": float(_q4(_d(getattr(player, "base_productivity_modifier", before_base_prod)))),
        "reward_summary": str(reward_payload.get("reward_summary", "")),
    }


def _update_goal_history_row(
    db: Session,
    state: PlayerProgressionState,
    player: Player,
    *,
    scope: str,
    key: str,
    title: str,
    description: str,
    status: str,
    progress_current: Decimal,
    progress_target: Decimal,
    reward_summary: str,
    urgency: str | None,
    category: str | None,
    as_of_date: date,
    day_number: int,
    week_start_day: int | None,
    week_end_day: int | None,
    debug_meta: dict,
    credit_day: int,
    reward_payload: dict | None,
) -> tuple[PlayerGoalHistory, dict | None]:
    row = (
        db.query(PlayerGoalHistory)
        .filter(
            PlayerGoalHistory.player_id == player.id,
            PlayerGoalHistory.goal_scope == scope,
            PlayerGoalHistory.goal_key == key,
            PlayerGoalHistory.day_number == int(day_number),
        )
        .first()
    )
    if row is None:
        row = PlayerGoalHistory(
            player_id=player.id,
            goal_scope=scope,
            goal_key=key,
            day_number=int(day_number),
        )
        db.add(row)

    row.as_of_date = as_of_date
    row.week_start_day = week_start_day
    row.week_end_day = week_end_day
    row.title = title
    row.description = description
    row.status = status
    row.progress_current = _q4(progress_current)
    row.progress_target = _q4(progress_target)
    row.reward_summary = reward_summary
    row.urgency = urgency
    row.expires_on = as_of_date if scope == DAILY_SCOPE else _day_to_date(week_end_day or day_number)
    row.category = category
    row.debug_json = json.dumps(debug_meta, sort_keys=True)

    reward_result = None
    if status == "completed" and not bool(row.credited_flag):
        reward_result = _apply_reward(player, reward_payload or {}, scope=scope)
        row.credited_flag = True
        row.credited_on_day = int(credit_day)
        row.reward_applied_json = json.dumps(reward_result, sort_keys=True)
        _append_recent_completion(
            state,
            {
                "scope": scope,
                "key": key,
                "title": title,
                "day": int(credit_day),
                "reward_summary": reward_summary,
            },
        )
        _append_reward_trace(
            state,
            {
                "scope": scope,
                "key": key,
                "day": int(credit_day),
                "applied": reward_result,
            },
        )

    db.flush()
    return row, reward_result


def _weekly_mission_templates(player: Player, state: PlayerProgressionState, week_signals: dict) -> list[dict]:
    trailing_avg = _d(week_signals.get("trailing_income_avg_xgp", 0))
    income_target = _money(
        _clamp(
            trailing_avg * Decimal("7.0") * Decimal("0.95"),
            Decimal("350.00"),
            Decimal("6000.00"),
        )
    )
    if income_target <= Decimal("0"):
        income_target = Decimal("500.00")

    templates: list[dict] = [
        {
            "mission_key": "weekly_income_target",
            "title": "Hit weekly income target",
            "description": "Keep total weekly earnings above your baseline target.",
            "progress_current": _money(_d(week_signals["income_total_xgp"])),
            "progress_target": income_target,
            "category": "income",
        }
    ]

    week_start_debt = _money(_d(getattr(state, "week_start_debt_xgp", _d(getattr(player, "debt_xgp", 0)))))
    current_debt = _money(_d(getattr(player, "debt_xgp", 0)))
    if current_debt > Decimal("100") or week_start_debt > Decimal("100"):
        reduction_target = _money(
            _clamp(week_start_debt * Decimal("0.04"), Decimal("20.00"), Decimal("400.00"))
        )
        debt_reduced = _money(max(Decimal("0"), week_start_debt - current_debt))
        templates.append(
            {
                "mission_key": "weekly_debt_reduction",
                "title": "Reduce debt this week",
                "description": "Push principal down with consistent debt-control actions.",
                "progress_current": debt_reduced,
                "progress_target": reduction_target,
                "category": "debt",
            }
        )

    career_state = week_signals.get("career_state")
    if career_state is not None or bool(getattr(player, "main_job", None)):
        templates.append(
            {
                "mission_key": "weekly_training_sessions",
                "title": "Complete 3 training sessions",
                "description": "Build skill momentum with steady learning blocks.",
                "progress_current": Decimal(int(week_signals["training_sessions"])),
                "progress_target": Decimal("3"),
                "category": "career",
            }
        )

    if bool(week_signals["has_active_business"]):
        templates.append(
            {
                "mission_key": "weekly_profitable_business_days",
                "title": "Run business profitably 4 days",
                "description": "Operate with consistency and protect weekly margin.",
                "progress_current": Decimal(int(week_signals["profitable_business_days"])),
                "progress_target": Decimal("4"),
                "category": "business",
            }
        )
    else:
        templates.append(
            {
                "mission_key": "weekly_work_shifts",
                "title": "Complete 4 work shifts",
                "description": "Keep dependable work output through the week.",
                "progress_current": Decimal(int(week_signals["work_shifts"])),
                "progress_target": Decimal("4"),
                "category": "work",
            }
        )

    if int(week_signals["settlement_rows"]) >= 2:
        templates.append(
            {
                "mission_key": "weekly_low_stress_days",
                "title": "Keep low-stress days above 5",
                "description": "Maintain healthy pressure levels across the week.",
                "progress_current": Decimal(int(week_signals["low_stress_days"])),
                "progress_target": Decimal("5"),
                "category": "life_balance",
            }
        )

    return templates[:5]


def build_daily_goals(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    day_number: int | None = None,
    persist: bool = True,
) -> dict:
    """Build deterministic daily goals from current player state and day signals."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=day_number)
    state = _get_or_create_progression_state(db, player, day)
    state.current_day = int(day)
    _sync_week_window(state, player, day)

    signals = _collect_day_signals(db, player, day)
    templates = _daily_goal_templates(signals)
    day_settled = _is_day_settled(db, player.id, day)

    items: list[dict] = []
    reward_events: list[dict] = []
    for template in templates:
        goal_key = str(template["goal_key"])
        progress_current = _q4(_d(template["progress_current"]))
        progress_target = _q4(_d(template["progress_target"]))
        status = _status_from_progress(progress_current, progress_target, settled=day_settled)
        reward_payload = DAILY_REWARD_RULES.get(goal_key, {"reward_summary": "Progress badge"})
        reward_summary = str(reward_payload.get("reward_summary", "Progress badge"))
        debug_meta = {
            "signals": {
                "productive_actions_today": int(signals["productive_actions_today"]),
                "business_runs_today": int(signals["business_runs_today"]),
                "training_hours_today": float(_q4(_d(signals["training_hours_today"]))),
                "recovery_actions_count": int(signals["recovery_actions_count"]),
                "cash_delta_today_xgp": float(_money(_d(signals["cash_delta_today_xgp"]))),
                "stress_now": int(signals["stress_now"]),
                "day_settled": bool(day_settled),
            },
            "target_formula": str(progress_target),
        }

        if persist:
            _, reward_result = _update_goal_history_row(
                db=db,
                state=state,
                player=player,
                scope=DAILY_SCOPE,
                key=goal_key,
                title=str(template["title"]),
                description=str(template["description"]),
                status=status,
                progress_current=progress_current,
                progress_target=progress_target,
                reward_summary=reward_summary,
                urgency=str(template.get("urgency", "medium")),
                category=str(template.get("category", "discipline")),
                as_of_date=resolved_date,
                day_number=day,
                week_start_day=None,
                week_end_day=None,
                debug_meta=debug_meta,
                credit_day=day,
                reward_payload=reward_payload,
            )
            if reward_result is not None:
                reward_events.append({"goal_key": goal_key, "title": str(template["title"]), "reward_applied": reward_result})

        items.append(
            {
                "goal_key": goal_key,
                "title": str(template["title"]),
                "description": str(template["description"]),
                "status": status,
                "progress_current": float(progress_current),
                "progress_target": float(progress_target),
                "reward_summary": reward_summary,
                "urgency": str(template.get("urgency", "medium")),
                "expires_on": resolved_date.isoformat(),
                "debug_meta": debug_meta,
            }
        )

    state.last_goal_refresh_day = int(day)
    state.last_action_digest_json = json.dumps(
        {
            "day": int(day),
            "productive_actions_today": int(signals["productive_actions_today"]),
            "business_runs_today": int(signals["business_runs_today"]),
            "training_hours_today": float(_q4(_d(signals["training_hours_today"]))),
            "cash_delta_today_xgp": float(_money(_d(signals["cash_delta_today_xgp"]))),
            "stress_now": int(signals["stress_now"]),
        },
        sort_keys=True,
    )
    db.flush()

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "daily_goals": items,
        "reward_events": reward_events,
        "debug_meta": {
            "generation_driver": {
                "day_settled": bool(day_settled),
                "has_active_business": bool(signals["has_active_business"]),
                "stress_now": int(signals["stress_now"]),
                "distress_state": str(signals["distress_state"]),
                "burnout_risk": float(_q4(_d(signals["burnout_risk"]))),
            }
        },
    }


def build_weekly_missions(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    day_number: int | None = None,
    persist: bool = True,
) -> dict:
    """Build deterministic weekly missions from strategy and pressure context."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=day_number)
    state = _get_or_create_progression_state(db, player, day)
    state.current_day = int(day)
    week_reset = _sync_week_window(state, player, day)
    week_start, week_end = int(state.current_week_start_day), int(state.current_week_end_day)

    week_signals = _collect_week_signals(db, player, week_start, week_end)
    templates = _weekly_mission_templates(player, state, week_signals)
    week_closed = int(day) >= int(week_end)

    items: list[dict] = []
    reward_events: list[dict] = []
    for template in templates:
        mission_key = str(template["mission_key"])
        progress_current = _q4(_d(template["progress_current"]))
        progress_target = _q4(_d(template["progress_target"]))
        status = _status_from_progress(progress_current, progress_target, settled=week_closed)
        reward_payload = WEEKLY_REWARD_RULES.get(mission_key, {"reward_summary": "Weekly milestone"})
        reward_summary = str(reward_payload.get("reward_summary", "Weekly milestone"))
        debug_meta = {
            "signals": {
                "income_total_xgp": float(_money(_d(week_signals["income_total_xgp"]))),
                "training_sessions": int(week_signals["training_sessions"]),
                "work_shifts": int(week_signals["work_shifts"]),
                "profitable_business_days": int(week_signals["profitable_business_days"]),
                "low_stress_days": int(week_signals["low_stress_days"]),
                "week_closed": bool(week_closed),
            },
            "week_bounds": {"week_start": int(week_start), "week_end": int(week_end)},
        }

        if persist:
            _, reward_result = _update_goal_history_row(
                db=db,
                state=state,
                player=player,
                scope=WEEKLY_SCOPE,
                key=mission_key,
                title=str(template["title"]),
                description=str(template["description"]),
                status=status,
                progress_current=progress_current,
                progress_target=progress_target,
                reward_summary=reward_summary,
                urgency="medium",
                category=str(template.get("category", "weekly")),
                as_of_date=resolved_date,
                day_number=int(week_start),
                week_start_day=int(week_start),
                week_end_day=int(week_end),
                debug_meta=debug_meta,
                credit_day=min(int(day), int(week_end)),
                reward_payload=reward_payload,
            )
            if reward_result is not None:
                reward_events.append({"mission_key": mission_key, "title": str(template["title"]), "reward_applied": reward_result})

        items.append(
            {
                "mission_key": mission_key,
                "title": str(template["title"]),
                "description": str(template["description"]),
                "status": status,
                "progress_current": float(progress_current),
                "progress_target": float(progress_target),
                "reward_summary": reward_summary,
                "week_start": _day_to_date(week_start).isoformat(),
                "week_end": _day_to_date(week_end).isoformat(),
                "category": str(template.get("category", "weekly")),
                "debug_meta": debug_meta,
            }
        )

    state.last_mission_refresh_week_start_day = int(week_start)
    db.flush()

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "week_start_day": int(week_start),
        "week_end_day": int(week_end),
        "weekly_missions": items[:5],
        "reward_events": reward_events,
        "debug_meta": {
            "week_reset": bool(week_reset),
            "week_signals": {
                "income_total_xgp": float(_money(_d(week_signals["income_total_xgp"]))),
                "training_sessions": int(week_signals["training_sessions"]),
                "work_shifts": int(week_signals["work_shifts"]),
                "profitable_business_days": int(week_signals["profitable_business_days"]),
                "low_stress_days": int(week_signals["low_stress_days"]),
                "missed_finance_days": int(week_signals["missed_finance_days"]),
            },
        },
    }


def _update_named_streak(
    state: PlayerProgressionState,
    *,
    name: str,
    day: int,
    condition_met: bool,
    credit_day: bool,
) -> tuple[int, int, int | None]:
    current_field = f"{name}_current"
    best_field = f"{name}_best"
    last_day_field = f"{name}_last_day"

    current = int(getattr(state, current_field, 0) or 0)
    best = int(getattr(state, best_field, 0) or 0)
    last_day = getattr(state, last_day_field, None)
    last_day_int = int(last_day) if last_day is not None else None

    if credit_day:
        if last_day_int == int(day):
            return current, best, last_day_int
        if condition_met:
            if last_day_int == int(day) - 1:
                current = int(current) + 1
            else:
                current = 1
            best = max(best, current)
            last_day_int = int(day)
        else:
            current = 0
        setattr(state, current_field, int(current))
        setattr(state, best_field, int(best))
        setattr(state, last_day_field, int(last_day_int) if last_day_int is not None else None)

    return int(current), int(best), (int(last_day_int) if last_day_int is not None else None)


def build_player_streaks(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    day_number: int | None = None,
    persist: bool = True,
    credit_day: bool = False,
) -> dict:
    """Build deterministic streak objects; optional day crediting after settlement."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=day_number)
    state = _get_or_create_progression_state(db, player, day)
    state.current_day = int(day)
    _sync_week_window(state, player, day)
    day_signals = _collect_day_signals(db, player, day)
    settled = _is_day_settled(db, player.id, day)

    conditions = {
        "login_streak": bool(settled) or int(day_signals["productive_actions_today"]) > 0,
        "productive_day_streak": bool(settled) and int(day_signals["productive_actions_today"]) >= 2,
        "positive_cash_flow_streak": bool(settled)
        and (
            _d(getattr(day_signals.get("settlement"), "cash_after", 0))
            - _d(getattr(day_signals.get("settlement"), "cash_before", 0))
            > Decimal("0")
        ),
        "training_streak": bool(settled) and _d(day_signals["training_hours_today"]) > Decimal("0"),
        "business_consistency_streak": bool(settled) and int(day_signals["business_runs_today"]) > 0,
        "low_distress_streak": bool(settled)
        and str(day_signals["distress_state"]) in {"stable", "stretched"}
        and _d(day_signals["distress_score"]) < Decimal("50"),
    }

    streak_items: list[dict] = []
    streak_map = {
        "login_streak": ("login_play_streak", "Login / Play Streak", "Settle or complete productive actions today."),
        "productive_day_streak": ("productive_day_streak", "Productive-Day Streak", "Complete 2+ productive actions and settle the day."),
        "positive_cash_flow_streak": ("positive_cash_flow_streak", "Positive Cash-Flow Streak", "Finish settled day with positive cash delta."),
        "training_streak": ("training_streak", "Training Streak", "Log training hours before settlement."),
        "business_consistency_streak": ("business_consistency_streak", "Business Consistency Streak", "Operate business at least once before settlement."),
        "low_distress_streak": ("low_distress_streak", "Low-Distress Streak", "Keep distress stable/stretched under score 50."),
    }

    for state_name, (streak_key, title, next_credit_condition) in streak_map.items():
        current, best, last_day = _update_named_streak(
            state,
            name=state_name,
            day=day,
            condition_met=bool(conditions[state_name]),
            credit_day=bool(credit_day and settled and persist),
        )
        if current >= 5:
            reset_risk = "low"
            status = "active"
        elif current >= 2:
            reset_risk = "medium"
            status = "active"
        elif current == 1:
            reset_risk = "medium"
            status = "at_risk" if not conditions[state_name] else "active"
        else:
            reset_risk = "high"
            status = "idle" if not settled else "broken"

        streak_items.append(
            {
                "streak_key": streak_key,
                "title": title,
                "current_count": int(current),
                "best_count": int(best),
                "status": status,
                "last_credited_on": _day_to_date(last_day).isoformat() if last_day is not None else None,
                "reset_risk": reset_risk,
                "next_credit_condition": next_credit_condition,
                "debug_meta": {
                    "day": int(day),
                    "settled": bool(settled),
                    "condition_met": bool(conditions[state_name]),
                },
            }
        )

    if persist:
        db.flush()

    order_index = {item[0]: idx for idx, item in enumerate(STREAK_ORDER)}
    streak_items.sort(key=lambda row: order_index.get(str(row["streak_key"]), 99))

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "streaks": streak_items,
        "debug_meta": {
            "credit_day": bool(credit_day and settled),
            "settled": bool(settled),
        },
    }


def _build_recently_completed(db: Session, player_id: UUID, day: int) -> list[dict]:
    rows = (
        db.query(PlayerGoalHistory)
        .filter(
            PlayerGoalHistory.player_id == player_id,
            PlayerGoalHistory.credited_flag.is_(True),
            PlayerGoalHistory.credited_on_day >= max(1, int(day) - 6),
        )
        .order_by(PlayerGoalHistory.credited_on_day.desc(), PlayerGoalHistory.updated_at.desc())
        .limit(12)
        .all()
    )
    items: list[dict] = []
    for row in rows:
        items.append(
            {
                "scope": row.goal_scope,
                "key": row.goal_key,
                "title": row.title,
                "credited_on": _day_to_date(int(row.credited_on_day or day)).isoformat(),
                "reward_summary": row.reward_summary,
            }
        )
    return items


def _build_suggested_focus(player: Player, daily_goals: list[dict], weekly_missions: list[dict]) -> list[str]:
    focus: list[str] = []
    stress = int(getattr(player, "stress", 0) or 0)
    distress_state = str(getattr(player, "distress_state", "stable") or "stable")
    if stress >= 72:
        focus.append("Protect recovery: prioritize lower-stress actions and sleep quality today.")
    if distress_state in {"distressed", "critical"}:
        focus.append("Debt stability first: avoid optional spending and queue recovery actions.")

    pending_daily = [g for g in daily_goals if g.get("status") in {"not_started", "in_progress"}]
    pending_weekly = [m for m in weekly_missions if m.get("status") in {"not_started", "in_progress"}]
    if pending_daily:
        focus.append(f"Finish daily goal: {pending_daily[0].get('title')}.")
    if pending_weekly:
        focus.append(f"Advance weekly mission: {pending_weekly[0].get('title')}.")

    if not focus:
        focus.append("Keep compounding: complete one productive action and preserve positive cash flow.")
    return focus[:4]


def _build_motivational_summary(recently_completed: list[dict], daily_goals: list[dict], streaks: list[dict]) -> str:
    if recently_completed:
        return f"You are building momentum: {len(recently_completed)} completions recorded recently."
    completed_daily = sum(1 for item in daily_goals if item.get("status") == "completed")
    if completed_daily >= 2:
        return "Strong day rhythm. Keep the discipline streak alive."
    best_streak = max((int(s.get("current_count", 0) or 0) for s in streaks), default=0)
    if best_streak >= 3:
        return f"Consistency is compounding with a {best_streak}-day streak."
    return "Small disciplined actions today create easier weeks later."


def build_progression_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    day_number: int | None = None,
    persist: bool = True,
) -> dict:
    """Build a composed progression summary for frontend use."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=day_number)
    state = _get_or_create_progression_state(db, player, day)
    state.current_day = int(day)
    _sync_week_window(state, player, day)

    daily_payload = build_daily_goals(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        persist=persist,
    )
    weekly_payload = build_weekly_missions(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        persist=persist,
    )
    streak_payload = build_player_streaks(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        persist=persist,
        credit_day=False,
    )

    recently_completed = _build_recently_completed(db, player.id, day)
    suggested_focus = _build_suggested_focus(player, daily_payload["daily_goals"], weekly_payload["weekly_missions"])
    motivational_summary = _build_motivational_summary(
        recently_completed,
        daily_payload["daily_goals"],
        streak_payload["streaks"],
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "daily_goals": daily_payload["daily_goals"][:3],
        "weekly_missions": weekly_payload["weekly_missions"][:5],
        "streaks": streak_payload["streaks"],
        "recently_completed": recently_completed,
        "suggested_focus": suggested_focus,
        "motivational_summary": motivational_summary,
        "debug_meta": {
            "day_number": int(day),
            "week_start_day": int(state.current_week_start_day or _week_bounds(day)[0]),
            "week_end_day": int(state.current_week_end_day or _week_bounds(day)[1]),
            "goal_generation_driver": daily_payload.get("debug_meta", {}),
            "weekly_generation_driver": weekly_payload.get("debug_meta", {}),
            "streak_crediting_reasons": streak_payload.get("debug_meta", {}),
            "reward_events": {
                "daily": daily_payload.get("reward_events", []),
                "weekly": weekly_payload.get("reward_events", []),
            },
        },
    }


def evaluate_action_progress(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Evaluate progression after a successful action in the day loop."""
    summary = build_progression_summary(db=db, player_id=player_id, as_of_date=as_of_date, persist=True)
    try:
        from app.engine.commitment_service import evaluate_commitment_progress

        evaluate_commitment_progress(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            action_key=None,
        )
    except Exception:
        pass  # commitment tracking errors must not break progression refresh
    db.flush()
    return summary


def evaluate_end_of_day_progress(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Finalize daily goals and streak crediting once settlement is available."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=None)

    latest_settlement = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == player.id)
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    if latest_settlement is not None:
        day = int(latest_settlement.day_number)
        resolved_date = _day_to_date(day)

    state = _get_or_create_progression_state(db, player, day)
    state.current_day = int(day)
    _sync_week_window(state, player, day)

    build_daily_goals(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day, persist=True)
    build_player_streaks(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        persist=True,
        credit_day=True,
    )
    build_weekly_missions(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day, persist=True)
    try:
        from app.engine.commitment_service import evaluate_commitment_progress

        evaluate_commitment_progress(
            db=db,
            player_id=player.id,
            as_of_date=resolved_date,
            action_key=None,
        )
    except Exception:
        pass  # commitment errors must not break progression end-of-day
    if int(day) % 7 == 0:
        evaluate_end_of_week_progress(db=db, player_id=player.id, as_of_date=resolved_date)

    state.last_progress_evaluated_day = int(day)
    db.flush()
    return build_progression_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day, persist=True)


def evaluate_end_of_week_progress(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Finalize weekly mission state on/after week boundary."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(player, db, as_of_date, day_number=None)
    state = _get_or_create_progression_state(db, player, day)
    state.current_day = int(day)
    _sync_week_window(state, player, day)
    payload = build_weekly_missions(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        persist=True,
    )
    db.flush()
    return payload


def get_player_streaks(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Convenience reader for streak payload."""
    return build_player_streaks(db=db, player_id=player_id, as_of_date=as_of_date, persist=True, credit_day=False)


def get_player_daily_goals(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Convenience reader for daily-goal payload."""
    payload = build_daily_goals(db=db, player_id=player_id, as_of_date=as_of_date, persist=True)
    return {
        "player_id": payload["player_id"],
        "as_of_date": payload["as_of_date"],
        "daily_goals": payload["daily_goals"][:3],
        "debug_meta": payload.get("debug_meta", {}),
    }


def get_player_weekly_missions(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Convenience reader for weekly-mission payload."""
    payload = build_weekly_missions(db=db, player_id=player_id, as_of_date=as_of_date, persist=True)
    return {
        "player_id": payload["player_id"],
        "as_of_date": payload["as_of_date"],
        "weekly_missions": payload["weekly_missions"][:5],
        "debug_meta": payload.get("debug_meta", {}),
    }
