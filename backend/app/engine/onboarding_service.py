"""Step 31 onboarding service: first-time funnel + progressive reveal controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_onboarding_state import PlayerOnboardingState
from app.models.side_income_action import SideIncomeAction

GAME_EPOCH = date(2026, 1, 1)

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"

ALL_STATUSES = {
    STATUS_NOT_STARTED,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_SKIPPED,
}

GUIDED_DAY_LIMIT = 3

SECTION_KEYS = [
    "day_controls",
    "daily_brief",
    "player_stats",
    "player_state",
    "risk_opportunity",
    "quick_actions",
    "action_hub",
    "action_history",
    "end_of_day_summary",
    "commute_pressure",
    "housing_tradeoff",
    "notifications",
    "progression",
    "weekly_summary",
    "weekly_missions",
    "strategic_planning",
    "debt_growth",
    "recovery_vs_push",
    "commitment",
    "world_memory",
    "market_overview",
    "price_trends",
    "business_margins",
    "business_plan",
    "economy_explainer",
    "future_teasers",
    "future_preparation",
]

MODULE_TO_SECTIONS = {
    "core_basics": [
        "day_controls",
        "daily_brief",
        "player_stats",
        "action_hub",
        "end_of_day_summary",
    ],
    "commute_tradeoff": [
        "commute_pressure",
        "housing_tradeoff",
    ],
    "progression_notifications": [
        "notifications",
        "progression",
        "weekly_summary",
        "weekly_missions",
    ],
    "planning": [
        "strategic_planning",
        "debt_growth",
        "recovery_vs_push",
    ],
    "commitment": ["commitment"],
    "world_memory": ["world_memory"],
    "economy_deep": [
        "market_overview",
        "price_trends",
        "business_margins",
        "business_plan",
        "economy_explainer",
        "future_teasers",
        "future_preparation",
    ],
}

ALL_MODULE_KEYS = list(MODULE_TO_SECTIONS.keys())

ALWAYS_ALLOWED_ACTIONS = ["work_shift", "side_income", "end_day"]
MODULE_ACTIONS = {
    "commute_tradeoff": ["change_region"],
    "progression_notifications": ["study", "recovery_action", "debt_payment", "rest"],
    "economy_deep": ["operate_business", "buy_inventory"],
}

STEP_DEFINITIONS = [
    {
        "step_key": "welcome_core_premise",
        "title": "Welcome to Gold Penny",
        "body": "Each day is your life loop. Make choices to survive and grow your money.",
        "highlight_target": "daily_brief",
        "required_action_key": "continue_onboarding",
        "optional_action_key": None,
        "completion_condition": "welcome_acknowledged",
    },
    {
        "step_key": "read_todays_brief",
        "title": "Read Today's Brief",
        "body": "This tells you what is happening in the economy today.",
        "highlight_target": "daily_brief",
        "required_action_key": "review_daily_brief",
        "optional_action_key": "open_action_hub",
        "completion_condition": "brief_reviewed",
    },
    {
        "step_key": "first_income_action",
        "title": "Take One Action",
        "body": "Choose one simple action to earn or manage your money today.",
        "highlight_target": "action_hub",
        "required_action_key": "work_shift",
        "optional_action_key": "side_income",
        "completion_condition": "first_income_action_done",
    },
    {
        "step_key": "end_first_day",
        "title": "End Your First Day",
        "body": "Finish your day to see the real results and move forward.",
        "highlight_target": "day_controls",
        "required_action_key": "end_day",
        "optional_action_key": None,
        "completion_condition": "first_day_settled",
    },
]

STEP_ORDER = {row["step_key"]: index + 1 for index, row in enumerate(STEP_DEFINITIONS)}
STEP_LOOKUP = {row["step_key"]: row for row in STEP_DEFINITIONS}


class OnboardingFlowError(Exception):
    """Base onboarding funnel exception."""


class OnboardingFlowNotFoundError(OnboardingFlowError):
    """Raised when player cannot be found."""


class OnboardingFlowValidationError(OnboardingFlowError):
    """Raised when onboarding input is invalid."""


@dataclass
class _OnboardingSignals:
    day_number: int
    as_of_date: date
    settlements_count: int
    daily_brief_count: int
    job_actions_count: int
    side_income_actions_count: int
    business_operation_count: int
    recovery_actions_count: int
    commute_exposure_count: int
    housing_switch_count: int
    latest_stress: int
    latest_recovery_hours: float

    @property
    def first_income_action_done(self) -> bool:
        return (self.job_actions_count + self.side_income_actions_count + self.business_operation_count) > 0

    @property
    def first_day_settled(self) -> bool:
        return self.settlements_count > 0

    @property
    def commute_tradeoff_exposed(self) -> bool:
        return self.commute_exposure_count > 0

    @property
    def first_recovery_action_done(self) -> bool:
        return self.recovery_actions_count > 0 or self.latest_recovery_hours >= 1.5

    @property
    def total_income_actions(self) -> int:
        return self.job_actions_count + self.side_income_actions_count + self.business_operation_count

    @property
    def current_day_income_action_taken(self) -> bool:
        return self.total_income_actions > self.settlements_count

    @property
    def current_day_recovery_action_taken(self) -> bool:
        return self.recovery_actions_count > self.settlements_count


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise OnboardingFlowValidationError("as_of_date must be on or after game epoch.")
    return day


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise OnboardingFlowValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if str(item).strip()]


def _dump_json(payload: list[str] | dict) -> str:
    return json.dumps(payload, sort_keys=True)


def _normalize_action_key(action_key: str | None) -> str:
    raw = str(action_key or "").strip().lower()
    if not raw:
        return ""
    if "brief" in raw:
        return "review_daily_brief"
    if "end" in raw and "day" in raw:
        return "end_day"
    if "work" in raw or "shift" in raw or "job" in raw:
        return "work_shift"
    if "side" in raw or "ride" in raw or "delivery" in raw:
        return "side_income"
    if "recovery" in raw:
        return "recovery_action"
    if "rest" in raw or "sleep" in raw:
        return "rest"
    if "study" in raw or "train" in raw or "cert" in raw:
        return "study"
    if "region" in raw or "housing" in raw or "move" in raw or "rent" in raw:
        return "change_region"
    if "commute" in raw:
        return "review_commute_tradeoff"
    return raw


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise OnboardingFlowNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise OnboardingFlowNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, player: Player, as_of_date: date | None) -> tuple[int, date]:
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date

    latest_settlement_day = _safe_scalar(
        db,
        lambda: (
            db.query(func.max(DailySettlementLog.day_number))
            .filter(DailySettlementLog.player_id == player.id)
            .scalar()
        ),
        default=None,
        table_name=DailySettlementLog.__tablename__,
    )
    if latest_settlement_day is not None:
        return int(latest_settlement_day), _day_to_date(int(latest_settlement_day))

    latest_daily_state_day = _safe_scalar(
        db,
        lambda: (
            db.query(func.max(PlayerDailyState.day_number))
            .filter(PlayerDailyState.player_id == player.id)
            .scalar()
        ),
        default=None,
        table_name=PlayerDailyState.__tablename__,
    )
    if latest_daily_state_day is not None:
        return int(latest_daily_state_day), _day_to_date(int(latest_daily_state_day))

    return 1, _day_to_date(1)


def _get_or_create_state(db: Session, player: Player, as_of_date: date) -> PlayerOnboardingState:
    state = (
        db.query(PlayerOnboardingState)
        .filter(PlayerOnboardingState.player_id == player.id)
        .first()
    )
    if state is not None:
        return state

    state = PlayerOnboardingState(
        player_id=player.id,
        onboarding_status=STATUS_NOT_STARTED,
        current_step_key=STEP_DEFINITIONS[0]["step_key"],
        current_step_index=1,
        visible_modules_json=_dump_json(["core_basics"]),
        unlocked_modules_json=_dump_json(["core_basics"]),
        completed_step_keys_json=_dump_json([]),
        first_session_day_count=0,
        debug_meta=_dump_json({"created_by": "step31_onboarding_service"}),
    )
    db.add(state)
    db.flush()
    return state


def _is_missing_relation_error(exc: Exception) -> bool:
    """Detect missing table/column errors for optional onboarding integrations."""
    message = str(exc).lower()
    return (
        "no such table" in message
        or "no such column" in message
        or "undefined table" in message
        or "undefined column" in message
    )


def _has_table(db: Session, table_name: str) -> bool:
    connection = db.connection()
    return bool(inspect(connection).has_table(table_name))


def _safe_scalar(db: Session, producer, default, *, table_name: str | None = None):
    """Run query producer and return default when optional relation is unavailable."""
    if table_name and not _has_table(db, table_name):
        return default
    try:
        return producer()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_relation_error(exc):
            return default
        raise


def _safe_count(db: Session, producer, *, table_name: str | None = None) -> int:
    value = _safe_scalar(db, producer, default=0, table_name=table_name)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_first(db: Session, producer, *, table_name: str | None = None):
    return _safe_scalar(db, producer, default=None, table_name=table_name)


def _safe_all(db: Session, producer, *, table_name: str | None = None) -> list:
    value = _safe_scalar(db, producer, default=[], table_name=table_name)
    if isinstance(value, list):
        return value
    return []


def _collect_signals(db: Session, player: Player, day_number: int, as_of_date: date) -> _OnboardingSignals:
    settlements_count = _safe_count(
        db,
        lambda: (
            db.query(DailySettlementLog.id)
            .filter(
                DailySettlementLog.player_id == player.id,
                DailySettlementLog.day_number <= int(day_number),
            )
            .count()
        ),
        table_name=DailySettlementLog.__tablename__,
    )
    daily_brief_count = _safe_count(
        db,
        lambda: (
            db.query(DailyBriefLog.id)
            .filter(
                DailyBriefLog.player_id == player.id,
                DailyBriefLog.day <= int(day_number),
            )
            .count()
        ),
        table_name=DailyBriefLog.__tablename__,
    )
    job_actions_count = _safe_count(
        db,
        lambda: (
            db.query(JobAction.id)
            .filter(
                JobAction.player_id == player.id,
                JobAction.day <= int(day_number),
            )
            .count()
        ),
        table_name=JobAction.__tablename__,
    )
    side_income_actions_count = _safe_count(
        db,
        lambda: (
            db.query(SideIncomeAction.id)
            .filter(
                SideIncomeAction.player_id == player.id,
                SideIncomeAction.day_number <= int(day_number),
            )
            .count()
        ),
        table_name=SideIncomeAction.__tablename__,
    )
    business_operation_count = _safe_count(
        db,
        lambda: (
            db.query(BusinessDailyLog.id)
            .filter(
                BusinessDailyLog.player_id == player.id,
                BusinessDailyLog.day <= int(day_number),
            )
            .count()
        ),
        table_name=BusinessDailyLog.__tablename__,
    )
    commute_exposure_count = _safe_count(
        db,
        lambda: (
            db.query(HousingDailyLog.id)
            .filter(
                HousingDailyLog.player_id == player.id,
                HousingDailyLog.day <= int(day_number),
            )
            .count()
        ),
        table_name=HousingDailyLog.__tablename__,
    )
    housing_switch_count = _safe_count(
        db,
        lambda: (
            db.query(HousingDailyLog.id)
            .filter(
                HousingDailyLog.player_id == player.id,
                HousingDailyLog.day <= int(day_number),
                HousingDailyLog.region != player.region,
            )
            .count()
        ),
        table_name=HousingDailyLog.__tablename__,
    )
    latest_daily_state = _safe_first(
        db,
        lambda: (
            db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == player.id,
                PlayerDailyState.day_number <= int(day_number),
            )
            .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
            .first()
        ),
        table_name=PlayerDailyState.__tablename__,
    )
    latest_stress = int(
        getattr(latest_daily_state, "stress_end", None)
        or getattr(player, "stress", 0)
        or 0
    )
    latest_recovery_hours = float(
        getattr(latest_daily_state, "recovery_hours", 0) or 0
    )

    recovery_actions_count = 0
    try:
        queued = _parse_json_list(getattr(player, "recovery_actions_json", None))
        recovery_actions_count += len(queued)
    except Exception:
        pass

    distress_rows = _safe_all(
        db,
        lambda: (
            db.query(FinancialDistressLog.recovery_actions_json)
            .filter(
                FinancialDistressLog.player_id == player.id,
                FinancialDistressLog.day <= int(day_number),
            )
            .all()
        ),
        table_name=FinancialDistressLog.__tablename__,
    )
    for (raw_json,) in distress_rows:
        try:
            payload = json.loads(raw_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        actions = payload.get("actions_applied") or []
        if isinstance(actions, list):
            recovery_actions_count += len(actions)

    return _OnboardingSignals(
        day_number=int(day_number),
        as_of_date=as_of_date,
        settlements_count=settlements_count,
        daily_brief_count=daily_brief_count,
        job_actions_count=job_actions_count,
        side_income_actions_count=side_income_actions_count,
        business_operation_count=business_operation_count,
        recovery_actions_count=int(recovery_actions_count),
        commute_exposure_count=commute_exposure_count,
        housing_switch_count=housing_switch_count,
        latest_stress=latest_stress,
        latest_recovery_hours=latest_recovery_hours,
    )


def _step_condition_met(
    step_key: str,
    signals: _OnboardingSignals,
    manual_action_key: str,
    completed_keys: list[str],
) -> bool:
    if step_key == "welcome_core_premise":
        return manual_action_key == "continue_onboarding"
    if step_key == "read_todays_brief":
        return (
            manual_action_key in {"review_daily_brief", "open_action_hub"}
            or signals.first_income_action_done
        )
    if step_key == "first_income_action":
        return signals.first_income_action_done
    if step_key == "end_first_day":
        return signals.first_day_settled or manual_action_key == "end_day"
    return False


def _progress_label(completed_count: int) -> str:
    total = len(STEP_DEFINITIONS)
    return f"{max(0, min(total, completed_count))}/{total} steps"


def _guided_day_number(day_number: int, onboarding_status: str, onboarding_active: bool) -> int:
    status = str(onboarding_status or "").lower()
    if status == STATUS_SKIPPED:
        return 0
    if onboarding_active and int(day_number) == 1:
        return 1
    if 2 <= int(day_number) <= GUIDED_DAY_LIMIT:
        return int(day_number)
    return 0


def _guided_phase(guided_day_number: int) -> str | None:
    if guided_day_number == 1:
        return "day_1_loop"
    if guided_day_number == 2:
        return "day_2_pressure"
    if guided_day_number == 3:
        return "day_3_opportunity"
    return None


def _guided_label(guided_day_number: int) -> str | None:
    if guided_day_number <= 0:
        return None
    return f"Day {guided_day_number} of {GUIDED_DAY_LIMIT}"


def _guided_visible_modules(
    guided_day_number: int,
    onboarding_status: str,
    unlocked_modules: list[str],
) -> list[str]:
    status = str(onboarding_status or "").lower()
    if status == STATUS_SKIPPED:
        return ALL_MODULE_KEYS[:]
    if guided_day_number == 1:
        return ["core_basics"]
    if guided_day_number == 2:
        return ["core_basics", "planning", "progression_notifications"]
    if guided_day_number == 3:
        return ["core_basics", "planning", "progression_notifications", "economy_deep"]
    if status == STATUS_COMPLETED:
        return ALL_MODULE_KEYS[:]
    return unlocked_modules[:]


def _guided_focus(signals: _OnboardingSignals, guided_day_number: int) -> dict[str, str | None]:
    if guided_day_number == 2:
        if not signals.current_day_income_action_taken:
            return {
                "highlighted_section": "action_hub",
                "highlighted_action_key": "work_shift",
            }
        if signals.latest_stress >= 45 and not signals.current_day_recovery_action_taken:
            return {
                "highlighted_section": "action_hub",
                "highlighted_action_key": "recovery_action",
            }
        return {
            "highlighted_section": "day_controls",
            "highlighted_action_key": "end_day",
        }

    if guided_day_number == 3:
        if not signals.current_day_income_action_taken:
            return {
                "highlighted_section": "action_hub",
                "highlighted_action_key": "explore_opportunity",
            }
        return {
            "highlighted_section": "day_controls",
            "highlighted_action_key": "end_day",
        }

    return {
        "highlighted_section": None,
        "highlighted_action_key": None,
    }


def _current_step_for_completed(completed_keys: list[str]) -> dict:
    completed_set = set(completed_keys)
    for step in STEP_DEFINITIONS:
        if step["step_key"] not in completed_set:
            return step
    return STEP_DEFINITIONS[-1]


def _compute_unlock_items(
    completed_keys: list[str],
    signals: _OnboardingSignals,
) -> list[dict]:
    completed_set = set(completed_keys)
    day_two_ready = signals.day_number >= 2 or signals.settlements_count >= 1
    day_three_ready = signals.day_number >= 3 or signals.settlements_count >= 2
    guided_intro_complete = signals.day_number >= 4 or signals.settlements_count >= GUIDED_DAY_LIMIT
    rules = [
        (
            "core_basics",
            "Always available for onboarding",
            True,
            "Core daily loop is always visible.",
        ),
        (
            "progression_notifications",
            "Reach Day 2",
            day_two_ready,
            "Warnings and progression cues appear on Day 2 once daily costs start to matter.",
        ),
        (
            "planning",
            "Reach Day 2",
            day_two_ready,
            "Debt and recovery planning unlock on Day 2 so pressure stays understandable.",
        ),
        (
            "commute_tradeoff",
            "Finish the guided first 3 days",
            guided_intro_complete,
            "Commute and housing tradeoffs unlock after the guided intro days are complete.",
        ),
        (
            "commitment",
            "Finish the guided first 3 days",
            guided_intro_complete,
            "Commitment systems unlock after the guided intro days keep the opening loop focused.",
        ),
        (
            "world_memory",
            "Finish the guided first 3 days",
            guided_intro_complete,
            "World continuity insights unlock after the guided intro days are complete.",
        ),
        (
            "economy_deep",
            "Reach Day 3",
            day_three_ready,
            "Business and stock signals unlock on Day 3 once the player has seen pressure first.",
        ),
    ]
    return [
        {
            "module_key": module_key,
            "unlock_condition": unlock_condition,
            "unlock_status": bool(unlock_status),
            "unlock_reason": unlock_reason,
            "debug_meta": {
                "settlements_count": int(signals.settlements_count),
                "completed_keys": completed_keys,
            },
        }
        for (module_key, unlock_condition, unlock_status, unlock_reason) in rules
    ]


def _sections_for_modules(module_keys: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for module_key in module_keys:
        for section in MODULE_TO_SECTIONS.get(module_key, []):
            if section in seen:
                continue
            seen.add(section)
            ordered.append(section)
    return ordered


def _blocked_actions_for_modules(unlocked_modules: list[str]) -> list[dict]:
    allowed_actions = set(ALWAYS_ALLOWED_ACTIONS)
    for module_key in unlocked_modules:
        for action in MODULE_ACTIONS.get(module_key, []):
            allowed_actions.add(action)

    canonical_candidates = sorted({action for values in MODULE_ACTIONS.values() for action in values})
    blocked = []
    for action in canonical_candidates:
        if action in allowed_actions:
            continue
        if action in {"change_region"}:
            reason = "Commute/housing lesson unlocks region moves after your first day."
        elif action in {"operate_business", "buy_inventory"}:
            reason = "Business depth unlocks after core onboarding milestones."
        else:
            reason = "This action unlocks after early onboarding milestones."
        blocked.append({"action_key": action, "reason": reason})
    return blocked


def _state_to_payload(
    state: PlayerOnboardingState,
    *,
    player_id: UUID,
    as_of_date: date,
    signals: _OnboardingSignals | None = None,
    onboarding_active: bool = False,
) -> dict:
    completed_keys = _parse_json_list(getattr(state, "completed_step_keys_json", None))
    current = _current_step_for_completed(completed_keys)
    onboarding_status = str(state.onboarding_status or STATUS_NOT_STARTED)
    guided_day_number = _guided_day_number(
        signals.day_number if signals is not None else 0,
        onboarding_status,
        onboarding_active,
    )
    return {
        "player_id": str(player_id),
        "as_of_date": as_of_date.isoformat(),
        "onboarding_status": onboarding_status,
        "current_step_key": str(state.current_step_key or current["step_key"]),
        "current_step_index": int(state.current_step_index or STEP_ORDER[current["step_key"]]),
        "current_step_title": str(current["title"]),
        "current_step_body": str(current["body"]),
        "progress_label": _progress_label(len(completed_keys)),
        "first_session_day_count": int(state.first_session_day_count or 0),
        "guided_experience_active": guided_day_number > 0,
        "guided_day_number": int(guided_day_number),
        "guided_phase": _guided_phase(guided_day_number),
        "guided_label": _guided_label(guided_day_number),
        "visible_modules": _parse_json_list(getattr(state, "visible_modules_json", None)),
        "unlocked_modules": _parse_json_list(getattr(state, "unlocked_modules_json", None)),
        "completed_step_keys": completed_keys,
        "debug_meta": {
            "current_step_completion_condition": current["completion_condition"],
            "last_guidance_shown_on": state.last_guidance_shown_on.isoformat() if state.last_guidance_shown_on else None,
        },
    }


def evaluate_onboarding_completion(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    *,
    action_key: str | None = None,
) -> dict:
    """Evaluate and persist onboarding step completion deterministically."""
    player = _resolve_player(db, player_id)
    day_number, resolved_date = _resolve_day(db, player, as_of_date)
    signals = _collect_signals(db, player, day_number, resolved_date)
    state = _get_or_create_state(db, player, resolved_date)
    manual_action_key = _normalize_action_key(action_key)

    if str(state.onboarding_status or STATUS_NOT_STARTED) == STATUS_NOT_STARTED:
        state.onboarding_status = STATUS_IN_PROGRESS
        state.started_on = resolved_date

    completed_keys = _parse_json_list(getattr(state, "completed_step_keys_json", None))
    completed_set = set(completed_keys)

    if str(state.onboarding_status or "") in {STATUS_COMPLETED, STATUS_SKIPPED}:
        if str(state.onboarding_status) == STATUS_COMPLETED and not state.completed_on:
            state.completed_on = resolved_date
    else:
        for step in STEP_DEFINITIONS:
            key = step["step_key"]
            if key in completed_set:
                continue
            if _step_condition_met(key, signals, manual_action_key, list(completed_set)):
                completed_set.add(key)
                continue
            break

        completed_keys = [row["step_key"] for row in STEP_DEFINITIONS if row["step_key"] in completed_set]
        all_done = len(completed_keys) == len(STEP_DEFINITIONS)
        if all_done:
            state.onboarding_status = STATUS_COMPLETED
            if not state.completed_on:
                state.completed_on = resolved_date
        else:
            state.onboarding_status = STATUS_IN_PROGRESS
            state.completed_on = None

    completed_keys = [row["step_key"] for row in STEP_DEFINITIONS if row["step_key"] in completed_set]
    current_step = _current_step_for_completed(completed_keys)
    state.current_step_key = current_step["step_key"]
    state.current_step_index = STEP_ORDER[current_step["step_key"]]
    state.first_session_day_count = int(signals.settlements_count)
    state.completed_step_keys_json = _dump_json(completed_keys)

    unlock_items = _compute_unlock_items(completed_keys, signals)
    unlocked_modules = [item["module_key"] for item in unlock_items if bool(item["unlock_status"])]

    onboarding_active = str(state.onboarding_status or "") in {STATUS_NOT_STARTED, STATUS_IN_PROGRESS}
    guided_day_number = _guided_day_number(signals.day_number, str(state.onboarding_status or ""), onboarding_active)
    if str(state.onboarding_status or "") == STATUS_SKIPPED:
        unlocked_modules = ALL_MODULE_KEYS[:]
        visible_modules = ALL_MODULE_KEYS[:]
    else:
        visible_modules = _guided_visible_modules(guided_day_number, str(state.onboarding_status or ""), unlocked_modules)
        if str(state.onboarding_status or "") == STATUS_COMPLETED and guided_day_number == 0:
            unlocked_modules = ALL_MODULE_KEYS[:]
            visible_modules = ALL_MODULE_KEYS[:]

    state.unlocked_modules_json = _dump_json(unlocked_modules)
    state.visible_modules_json = _dump_json(visible_modules)
    state.debug_meta = _dump_json(
        {
            "day_number": int(day_number),
            "manual_action_key": manual_action_key,
            "signals": {
                "settlements_count": int(signals.settlements_count),
                "daily_brief_count": int(signals.daily_brief_count),
                "income_actions_total": int(
                    signals.job_actions_count
                    + signals.side_income_actions_count
                    + signals.business_operation_count
                ),
                "recovery_actions_count": int(signals.recovery_actions_count),
                "commute_exposure_count": int(signals.commute_exposure_count),
                "latest_stress": int(signals.latest_stress),
                "latest_recovery_hours": float(signals.latest_recovery_hours),
            },
        }
    )

    db.flush()
    return _state_to_payload(
        state,
        player_id=player.id,
        as_of_date=resolved_date,
        signals=signals,
        onboarding_active=onboarding_active,
    )


def build_unlock_schedule(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return module unlock schedule used for progressive reveal UI."""
    player = _resolve_player(db, player_id)
    day_number, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player, resolved_date)
    evaluate_onboarding_completion(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        action_key=None,
    )
    state = _get_or_create_state(db, player, resolved_date)
    signals = _collect_signals(db, player, day_number, resolved_date)
    completed_keys = _parse_json_list(getattr(state, "completed_step_keys_json", None))
    items = _compute_unlock_items(completed_keys, signals)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "onboarding_status": str(state.onboarding_status or STATUS_NOT_STARTED),
        "items": items,
        "debug_meta": {
            "day_number": int(day_number),
            "completed_step_keys": completed_keys,
        },
    }


def build_first_session_dashboard_config(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return onboarding-driven section visibility and action gating config."""
    # Core logic freeze: backend owns onboarding/guided-day reveal so mobile UI does not become
    # a second rules engine. Keep payload shape and reveal semantics stable.
    player = _resolve_player(db, player_id)
    day_number, resolved_date = _resolve_day(db, player, as_of_date)
    state_payload = evaluate_onboarding_completion(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        action_key=None,
    )
    schedule = build_unlock_schedule(db=db, player_id=player.id, as_of_date=resolved_date)
    state = _get_or_create_state(db, player, resolved_date)
    signals = _collect_signals(db, player, day_number, resolved_date)

    onboarding_status = str(state.onboarding_status or STATUS_NOT_STARTED)
    onboarding_active = onboarding_status in {STATUS_NOT_STARTED, STATUS_IN_PROGRESS}
    guided_day_number = _guided_day_number(day_number, onboarding_status, onboarding_active)
    unlocked_modules = [
        item["module_key"]
        for item in schedule["items"]
        if bool(item.get("unlock_status"))
    ]
    fully_unlocked = onboarding_status == STATUS_SKIPPED or (onboarding_status == STATUS_COMPLETED and guided_day_number == 0)
    if fully_unlocked:
        unlocked_modules = ALL_MODULE_KEYS[:]

    visible_modules = ALL_MODULE_KEYS[:] if fully_unlocked else _guided_visible_modules(guided_day_number, onboarding_status, unlocked_modules)
    visible_sections = SECTION_KEYS[:] if fully_unlocked else _sections_for_modules(visible_modules)
    hidden_sections = [] if fully_unlocked else [section for section in SECTION_KEYS if section not in set(visible_sections)]
    collapsed_sections = [
        section
        for section in visible_sections
        if section in {
            "market_overview",
            "price_trends",
            "business_margins",
            "business_plan",
            "economy_explainer",
            "future_teasers",
            "future_preparation",
            "world_memory",
            "commitment",
        }
    ]

    highlighted_section = None
    highlighted_action_key = None
    if not fully_unlocked:
        if onboarding_active:
            current_step = STEP_LOOKUP.get(state_payload["current_step_key"], STEP_DEFINITIONS[0])
            highlighted_section = str(current_step.get("highlight_target") or "")
            highlighted_action_key = str(current_step.get("required_action_key") or "") or None
            if highlighted_section not in SECTION_KEYS:
                highlighted_section = None
        elif guided_day_number in {2, 3}:
            guided_focus = _guided_focus(signals, guided_day_number)
            highlighted_section = guided_focus.get("highlighted_section")
            highlighted_action_key = guided_focus.get("highlighted_action_key")

    allowed_actions = set(ALWAYS_ALLOWED_ACTIONS)
    for module_key in visible_modules:
        for action in MODULE_ACTIONS.get(module_key, []):
            allowed_actions.add(action)

    blocked_actions = _blocked_actions_for_modules(visible_modules)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "onboarding_status": onboarding_status,
        "guided_experience_active": guided_day_number > 0,
        "guided_day_number": int(guided_day_number),
        "guided_phase": _guided_phase(guided_day_number),
        "guided_label": _guided_label(guided_day_number),
        "visible_sections": visible_sections,
        "collapsed_sections": collapsed_sections,
        "hidden_sections": hidden_sections,
        "highlighted_section": highlighted_section,
        "highlighted_action_key": highlighted_action_key,
        "allowed_actions": sorted(allowed_actions),
        "blocked_actions_for_onboarding": blocked_actions,
        "debug_meta": {
            "day_number": int(day_number),
            "unlocked_modules": unlocked_modules,
            "visible_modules": visible_modules,
            "current_step_key": state_payload["current_step_key"],
        },
    }


def build_onboarding_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build composed onboarding state payload for frontend hydration."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    state_payload = evaluate_onboarding_completion(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        action_key=None,
    )
    return state_payload


def get_onboarding_step(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return current step metadata for the player onboarding flow."""
    state = build_onboarding_state(db=db, player_id=player_id, as_of_date=as_of_date)
    step = STEP_LOOKUP.get(state["current_step_key"], STEP_DEFINITIONS[0])
    return {
        "player_id": state["player_id"],
        "as_of_date": state["as_of_date"],
        "onboarding_status": state["onboarding_status"],
        "step_key": step["step_key"],
        "title": step["title"],
        "body": step["body"],
        "highlight_target": step["highlight_target"],
        "required_action_key": step["required_action_key"],
        "optional_action_key": step["optional_action_key"],
        "completion_condition": step["completion_condition"],
        "can_skip": state["onboarding_status"] in {STATUS_IN_PROGRESS, STATUS_NOT_STARTED},
        "debug_meta": state.get("debug_meta", {}),
    }


def build_onboarding_guidance(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build concise, action-oriented onboarding guidance for current step."""
    player = _resolve_player(db, player_id)
    day_number, resolved_date = _resolve_day(db, player, as_of_date)
    state_payload = build_onboarding_state(db=db, player_id=player.id, as_of_date=resolved_date)
    state = _get_or_create_state(db, player, resolved_date)
    state.last_guidance_shown_on = resolved_date
    db.flush()
    step = STEP_LOOKUP.get(state_payload["current_step_key"], STEP_DEFINITIONS[0])
    signals = _collect_signals(db, player, day_number, resolved_date)
    onboarding_active = str(state_payload["onboarding_status"] or "") in {STATUS_NOT_STARTED, STATUS_IN_PROGRESS}
    guided_day_number = _guided_day_number(day_number, str(state_payload["onboarding_status"] or ""), onboarding_active)

    if not onboarding_active and guided_day_number in {2, 3}:
        if guided_day_number == 2:
            next_action_key = "work_shift"
            blocker_reason = "Your bills are starting to matter. Keep cash ahead of pressure, then end the day and compare the result."
            if signals.latest_stress >= 45 and not signals.current_day_recovery_action_taken:
                next_action_key = "recovery_action"
                blocker_reason = "Pressure is rising. A simple recovery action can protect tomorrow before you push harder."
            elif signals.current_day_income_action_taken:
                next_action_key = "end_day"
                blocker_reason = "You have already acted today. End the day and read how costs and pressure changed the result."

            return {
                "player_id": state_payload["player_id"],
                "as_of_date": state_payload["as_of_date"],
                "onboarding_status": state_payload["onboarding_status"],
                "guided_experience_active": True,
                "guided_day_number": 2,
                "guided_phase": "day_2_pressure",
                "guided_label": "Day 2 of 3",
                "step_key": "guided_day_2_pressure",
                "title": "Pressure Is Part of the Loop",
                "body": "Day 2 teaches that expenses, debt, and recovery are real parts of the economy. Keep the loop understandable: read the brief, make one move, then study the result.",
                "highlight_target": "action_hub" if next_action_key != "end_day" else "day_controls",
                "required_action_key": next_action_key,
                "optional_action_key": None,
                "completion_condition": "complete_day_two_loop",
                "blocker_reason": blocker_reason,
                "can_skip": False,
                "debug_meta": {
                    "day_number": int(day_number),
                    "latest_stress": int(signals.latest_stress),
                    "income_actions_total": int(signals.total_income_actions),
                    "recovery_actions_count": int(signals.recovery_actions_count),
                },
            }

        next_action_key = "explore_opportunity"
        blocker_reason = "The economy now creates simple upside and risk. Explore one opportunity only if your cash buffer still feels safe."
        if signals.current_day_income_action_taken:
            next_action_key = "end_day"
            blocker_reason = "You have already made a move today. End the day and compare whether the safer or riskier path paid off."
        elif float(player.cash_xgp or 0) < 120:
            next_action_key = "work_shift"
            blocker_reason = "Opportunity matters now, but cash safety still comes first. Build a little room before pushing into higher variance choices."

        return {
            "player_id": state_payload["player_id"],
            "as_of_date": state_payload["as_of_date"],
            "onboarding_status": state_payload["onboarding_status"],
            "guided_experience_active": True,
            "guided_day_number": 3,
            "guided_phase": "day_3_opportunity",
            "guided_label": "Day 3 of 3",
            "step_key": "guided_day_3_opportunity",
            "title": "Adapt, Don’t Just Tap",
            "body": "Day 3 introduces light opportunity. Work is still valid, but now the lesson is adaptation: compare safer income with one small opportunity signal from the economy.",
            "highlight_target": "action_hub" if next_action_key != "end_day" else "day_controls",
            "required_action_key": next_action_key,
            "optional_action_key": None,
            "completion_condition": "complete_day_three_loop",
            "blocker_reason": blocker_reason,
            "can_skip": False,
            "debug_meta": {
                "day_number": int(day_number),
                    "cash_xgp": float(player.cash_xgp or 0),
                "income_actions_total": int(signals.total_income_actions),
                "recovery_actions_count": int(signals.recovery_actions_count),
            },
        }

    blocker_reason = None
    if step["step_key"] == "welcome_core_premise":
        blocker_reason = "Start with the short guide, then read the Daily Brief."
    elif step["step_key"] == "read_todays_brief":
        blocker_reason = "Read the Daily Brief first so you know what kind of day it is."
    elif step["step_key"] == "first_income_action" and not signals.first_income_action_done:
        blocker_reason = "Take one income action to continue."
    elif step["step_key"] == "end_first_day" and not signals.first_day_settled:
        blocker_reason = "Use End Day after your action to lock your first results."

    body = step["body"]
    if step["step_key"] == "first_income_action":
        body = "Choose one simple action now. Work is the fastest way to feel the loop."
    elif step["step_key"] == "end_first_day":
        body = "End the day to see what changed and start the next one with real results."

    return {
        "player_id": state_payload["player_id"],
        "as_of_date": state_payload["as_of_date"],
        "onboarding_status": state_payload["onboarding_status"],
        "guided_experience_active": guided_day_number > 0,
        "guided_day_number": int(guided_day_number),
        "guided_phase": _guided_phase(guided_day_number),
        "guided_label": _guided_label(guided_day_number),
        "step_key": step["step_key"],
        "title": step["title"],
        "body": body,
        "highlight_target": step["highlight_target"],
        "required_action_key": step["required_action_key"],
        "optional_action_key": step["optional_action_key"],
        "completion_condition": step["completion_condition"],
        "blocker_reason": blocker_reason,
        "can_skip": state_payload["onboarding_status"] in {STATUS_IN_PROGRESS, STATUS_NOT_STARTED},
        "debug_meta": {
            "day_number": int(day_number),
            "signals": {
                "settlements_count": signals.settlements_count,
                "income_actions_total": (
                    signals.job_actions_count
                    + signals.side_income_actions_count
                    + signals.business_operation_count
                ),
                "recovery_actions_count": signals.recovery_actions_count,
                "commute_exposure_count": signals.commute_exposure_count,
            },
        },
    }


def advance_onboarding_step(
    db: Session,
    player_id: str | UUID,
    *,
    action_key: str | None = None,
    step_key: str | None = None,
    force: bool = False,
    as_of_date: date | None = None,
) -> dict:
    """Advance onboarding state explicitly and then evaluate deterministic conditions."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player, resolved_date)

    if str(state.onboarding_status or "") == STATUS_SKIPPED and not force:
        raise OnboardingFlowValidationError("Onboarding was skipped. Use force=true to re-open.")

    if str(state.onboarding_status or "") == STATUS_COMPLETED and not force:
        return build_onboarding_state(db=db, player_id=player.id, as_of_date=resolved_date)

    manual_action = _normalize_action_key(action_key)
    payload = evaluate_onboarding_completion(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        action_key=manual_action,
    )

    if step_key:
        requested = str(step_key).strip()
        if requested and requested in STEP_LOOKUP:
            completed = set(_parse_json_list(state.completed_step_keys_json))
            completed.add(requested)
            state.completed_step_keys_json = _dump_json(
                [row["step_key"] for row in STEP_DEFINITIONS if row["step_key"] in completed]
            )
            payload = evaluate_onboarding_completion(
                db=db,
                player_id=player.id,
                as_of_date=resolved_date,
                action_key=manual_action,
            )

    return payload


def skip_onboarding(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Skip onboarding and reveal the full mature dashboard immediately."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player, resolved_date)

    state.onboarding_status = STATUS_SKIPPED
    state.skipped_on = resolved_date
    state.current_step_key = STEP_DEFINITIONS[-1]["step_key"]
    state.current_step_index = len(STEP_DEFINITIONS)
    state.completed_step_keys_json = _dump_json([row["step_key"] for row in STEP_DEFINITIONS])
    state.visible_modules_json = _dump_json(ALL_MODULE_KEYS)
    state.unlocked_modules_json = _dump_json(ALL_MODULE_KEYS)
    state.first_session_day_count = max(int(state.first_session_day_count or 0), 1)
    db.flush()
    return _state_to_payload(state, player_id=player.id, as_of_date=resolved_date)


def complete_onboarding(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Mark onboarding as completed and unlock all mature gameplay sections."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, player, as_of_date)
    state = _get_or_create_state(db, player, resolved_date)

    state.onboarding_status = STATUS_COMPLETED
    state.completed_on = resolved_date
    state.current_step_key = STEP_DEFINITIONS[-1]["step_key"]
    state.current_step_index = len(STEP_DEFINITIONS)
    state.completed_step_keys_json = _dump_json([row["step_key"] for row in STEP_DEFINITIONS])
    state.visible_modules_json = _dump_json(ALL_MODULE_KEYS)
    state.unlocked_modules_json = _dump_json(ALL_MODULE_KEYS)
    state.first_session_day_count = max(int(state.first_session_day_count or 0), 1)
    db.flush()
    return _state_to_payload(state, player_id=player.id, as_of_date=resolved_date)
