"""Run lifecycle service for bankruptcy and retirement endings."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.game_state import GameState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_progression_state import PlayerProgressionState
from app.services.game_time_service import get_server_now

MONEY_Q = Decimal("0.01")

RUN_STATUS_ACTIVE = "active"
RUN_STATUS_BANKRUPT = "bankrupt"
RUN_STATUS_RETIRED = "retired"
ENDED_RUN_STATUSES = {RUN_STATUS_BANKRUPT, RUN_STATUS_RETIRED}

BANKRUPTCY_WARNING = "Bankruptcy risk: another missed payment may end your run."
BANKRUPTCY_DEBT_THRESHOLD = Decimal("2500")
BANKRUPTCY_CREDIT_SCORE_MAX = 520
BANKRUPTCY_MISSED_PAYMENT_STREAK_MIN = 3

RETIREMENT_MIN_DAY = 30
RETIREMENT_MIN_NET_WORTH = Decimal("10000")
RETIREMENT_INELIGIBLE_REASON = "You need at least Day 30 and $10,000 net worth to retire."


class RunEndError(Exception):
    """Base exception for run lifecycle failures."""


class RunEndNotFoundError(RunEndError):
    """Raised when the player cannot be found."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _safe_float_money(value: object) -> float:
    return float(_money(_d(value)))


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise RunEndNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise RunEndNotFoundError("Player not found.")
    return player


def normalize_run_status(player: Player | None) -> str:
    status = str(getattr(player, "run_status", RUN_STATUS_ACTIVE) or RUN_STATUS_ACTIVE).strip().lower()
    if status in {RUN_STATUS_ACTIVE, RUN_STATUS_BANKRUPT, RUN_STATUS_RETIRED}:
        return status
    return RUN_STATUS_ACTIVE


def assert_run_can_continue(player: Player) -> None:
    status = normalize_run_status(player)
    if status != RUN_STATUS_ACTIVE:
        raise RunEndError(f"Player run has ended with status '{status}'.")


def retirement_title_for_net_worth(net_worth: object) -> str:
    value = _money(_d(net_worth))
    if value >= Decimal("100000"):
        return "Financially Free"
    if value >= Decimal("50000"):
        return "Independent Operator"
    return "Stable Owner"


def get_current_game_day(db: Session, player: Player | None = None) -> int:
    try:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        if state is not None:
            return max(1, int(getattr(state, "current_day", 1) or 1))
    except Exception:
        pass
    if player is not None:
        return max(1, int(getattr(player, "last_settled_day", 0) or 1))
    return 1


def _active_business_count(db: Session, player: Player) -> int:
    try:
        return int(
            db.query(func.count(PlayerBusiness.id))
            .filter(
                PlayerBusiness.player_id == player.id,
                PlayerBusiness.is_active.is_(True),
            )
            .scalar()
            or 0
        )
    except Exception:
        return 0


def _land_owned_count(_db: Session, _player: Player) -> int:
    # Sandbox land is still frontend-local in the current implementation; no
    # backend persistent land table exists yet.
    return 0


def _best_streak(db: Session, player: Player) -> int:
    try:
        row = (
            db.query(PlayerProgressionState)
            .filter(PlayerProgressionState.player_id == player.id)
            .first()
        )
    except Exception:
        return 0
    if row is None:
        return 0
    return max(
        int(getattr(row, "login_streak_best", 0) or 0),
        int(getattr(row, "productive_day_streak_best", 0) or 0),
        int(getattr(row, "positive_cash_flow_streak_best", 0) or 0),
        int(getattr(row, "training_streak_best", 0) or 0),
        int(getattr(row, "business_consistency_streak_best", 0) or 0),
        int(getattr(row, "low_distress_streak_best", 0) or 0),
    )


def _parse_run_end_summary(player: Player) -> dict:
    raw = getattr(player, "run_end_summary_json", None)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_run_end_summary(
    db: Session,
    player: Player,
    *,
    day_number: int,
    cash_basis: object | None = None,
    retirement_title: str | None = None,
) -> dict:
    summary = {
        "cash": _safe_float_money(cash_basis if cash_basis is not None else getattr(player, "cash_xgp", 0)),
        "debt": _safe_float_money(getattr(player, "debt_xgp", 0)),
        "credit_score": int(getattr(player, "credit_score", 650) or 650),
        "net_worth": _safe_float_money(getattr(player, "net_worth_xgp", getattr(player, "net_worth", 0))),
        "days_survived": int(day_number),
        "businesses_owned": _active_business_count(db, player),
        "land_owned": _land_owned_count(db, player),
        "best_streak": _best_streak(db, player),
    }
    if cash_basis is not None:
        summary["actual_cash"] = _safe_float_money(getattr(player, "cash_xgp", 0))
    if retirement_title:
        summary["retirement_title"] = retirement_title
    return summary


def build_end_state_payload(player: Player, *, triggered: bool = False) -> dict:
    status = normalize_run_status(player)
    summary = _parse_run_end_summary(player)
    return {
        "triggered": bool(triggered),
        "run_status": status,
        "reason": getattr(player, "run_end_reason", None),
        "summary": summary,
    }


def evaluate_bankruptcy_for_player(
    db: Session,
    player: Player,
    *,
    day_number: int,
    cash_basis: object | None = None,
    commit: bool = False,
) -> dict:
    if normalize_run_status(player) != RUN_STATUS_ACTIVE:
        return {
            "triggered": False,
            "risk_warnings": [],
            "end_state": build_end_state_payload(player, triggered=False),
        }

    cash_value = _money(_d(cash_basis if cash_basis is not None else getattr(player, "cash_xgp", 0)))
    debt_value = _money(_d(getattr(player, "debt_xgp", 0)))
    credit_score = int(getattr(player, "credit_score", 650) or 650)
    missed_streak = int(getattr(player, "missed_payment_streak", 0) or 0)

    bankruptcy_triggered = (
        cash_value < Decimal("0")
        and debt_value >= BANKRUPTCY_DEBT_THRESHOLD
        and credit_score <= BANKRUPTCY_CREDIT_SCORE_MAX
        and missed_streak >= BANKRUPTCY_MISSED_PAYMENT_STREAK_MIN
    )
    if not bankruptcy_triggered:
        risk_warnings = [BANKRUPTCY_WARNING] if cash_value < Decimal("0") and missed_streak >= 2 else []
        return {
            "triggered": False,
            "risk_warnings": risk_warnings,
            "end_state": None,
        }

    summary = build_run_end_summary(
        db,
        player,
        day_number=day_number,
        cash_basis=cash_value,
    )
    player.run_status = RUN_STATUS_BANKRUPT
    player.run_ended_at = get_server_now()
    player.run_end_day = int(day_number)
    player.run_end_reason = "bankruptcy"
    player.run_end_summary_json = json.dumps(summary, sort_keys=True)

    if commit:
        db.commit()
        db.refresh(player)

    return {
        "triggered": True,
        "risk_warnings": [],
        "end_state": build_end_state_payload(player, triggered=True),
    }


def _retirement_requirement_payload(db: Session, player: Player) -> dict:
    current_day = get_current_game_day(db, player)
    current_net_worth = _money(_d(getattr(player, "net_worth_xgp", getattr(player, "net_worth", 0))))
    return {
        "min_day": RETIREMENT_MIN_DAY,
        "min_net_worth": float(RETIREMENT_MIN_NET_WORTH),
        "current_day": int(current_day),
        "current_net_worth": float(current_net_worth),
    }


def _can_retire_from_requirement(player: Player, requirement: dict) -> bool:
    return (
        normalize_run_status(player) == RUN_STATUS_ACTIVE
        and int(requirement["current_day"]) >= RETIREMENT_MIN_DAY
        and _d(requirement["current_net_worth"]) >= RETIREMENT_MIN_NET_WORTH
    )


def get_player_run_status(db: Session, player_id: str | UUID) -> dict:
    player = _resolve_player(db, player_id)
    status = normalize_run_status(player)
    requirement = _retirement_requirement_payload(db, player)
    can_retire = _can_retire_from_requirement(player, requirement)
    return {
        "run_status": status,
        "run_ended_at": player.run_ended_at.isoformat() if getattr(player, "run_ended_at", None) else None,
        "run_end_day": int(player.run_end_day) if getattr(player, "run_end_day", None) is not None else None,
        "run_end_reason": getattr(player, "run_end_reason", None),
        "run_end_summary": _parse_run_end_summary(player),
        "can_continue": status == RUN_STATUS_ACTIVE,
        "can_retire": bool(can_retire),
        "retirement_requirement": requirement,
    }


def retire_player_run(db: Session, player_id: str | UUID) -> dict:
    player = _resolve_player(db, player_id)
    status = normalize_run_status(player)
    requirement = _retirement_requirement_payload(db, player)

    if status != RUN_STATUS_ACTIVE:
        return {
            "eligible": False,
            "reason": "This run has already ended.",
            **get_player_run_status(db, player.id),
        }

    if not _can_retire_from_requirement(player, requirement):
        return {
            "eligible": False,
            "reason": RETIREMENT_INELIGIBLE_REASON,
            **get_player_run_status(db, player.id),
        }

    title = retirement_title_for_net_worth(requirement["current_net_worth"])
    summary = build_run_end_summary(
        db,
        player,
        day_number=int(requirement["current_day"]),
        retirement_title=title,
    )
    player.run_status = RUN_STATUS_RETIRED
    player.run_ended_at = get_server_now()
    player.run_end_day = int(requirement["current_day"])
    player.run_end_reason = "voluntary_retirement"
    player.run_end_summary_json = json.dumps(summary, sort_keys=True)
    db.commit()
    db.refresh(player)

    return {
        "eligible": True,
        "reason": None,
        **get_player_run_status(db, player.id),
    }
