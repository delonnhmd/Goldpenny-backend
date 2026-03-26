"""Canonical gameplay endpoints used by the Expo gameplay loop shell.

Step 72 goals:
- provide stable /gameplay/player/{player_id}/... routes
- avoid frontend route probing + 404 storms
- keep first-session day-1 flow playable with meaningful starter actions
"""

from __future__ import annotations

import logging
import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.career_config import CAREER_CONFIG
from app.engine.career_service import (
    CareerError,
    CareerNotFoundError,
    CareerValidationError,
    apply_daily_career_progression,
    switch_player_job,
)
from app.engine.economy_presentation_service import build_economy_presentation_summary
from app.engine.rideshare_engine import process_rideshare_action
from app.engine.work_engine import WorkEngine
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.services.daily_brief_service import (
    DailyBriefError,
    DailyBriefNotFoundError,
    get_player_latest_daily_brief,
)
from app.services.daily_settlement_service import (
    DailySettlementError,
    SettlementNotFoundError,
    SettlementValidationError,
    get_latest_settlement_summary,
)
from app.services.day_progression_service import run_player_next_day
from app.services.job_market_service import (
    JobMarketError,
    JobMarketNotFoundError,
    JobMarketValidationError,
    get_player_job_summary,
)
from app.services.player_onboarding_service import (
    OnboardingError,
    OnboardingNotFoundError,
    get_playable_player_summary,
)
from app.services.player_transaction_log_service import list_recent_player_transactions

router = APIRouter()
logger = logging.getLogger(__name__)
_work_engine = WorkEngine()


class GameplayActionRequest(BaseModel):
    action_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class GameplayActionPreviewRequest(BaseModel):
    action_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class EndOfDaySummaryAckRequest(BaseModel):
    day_number: int | None = None


SHIFT_PROFILES: dict[str, dict[str, Any]] = {
    "morning_shift": {
        "label": "Morning Shift",
        "window": "5:00-13:00",
        "hours_worked": 4,
        "stress_modifier": 0.9,
        "health_modifier": 1.05,
    },
    "standard_shift": {
        "label": "Standard Shift",
        "window": "9:00-17:00",
        "hours_worked": 6,
        "stress_modifier": 1.0,
        "health_modifier": 1.0,
    },
    "long_shift": {
        "label": "Long Shift",
        "window": "9:00-21:00",
        "hours_worked": 8,
        "stress_modifier": 1.2,
        "health_modifier": 0.9,
    },
}

JOB_COMPANY_MAP: dict[str, dict[str, str]] = {
    "auto_mechanic": {"symbol": "GP_AUTO", "name": "GP Auto", "position": "Auto Mechanic"},
    "aircraft_mechanic": {"symbol": "GP_TRANSPORT", "name": "GP Transport", "position": "Aircraft Mechanic"},
    "banker": {"symbol": "GP_BANK", "name": "GP Bank", "position": "Junior Banker"},
    "chef": {"symbol": "GP_CONSUMER", "name": "GP Consumer", "position": "Kitchen Lead"},
    "retail_worker": {"symbol": "GP_RETAIL", "name": "GP Retail", "position": "Retail Associate"},
    "delivery_driver": {"symbol": "GP_TRANSPORT", "name": "GP Transport", "position": "Delivery Driver"},
    "rideshare": {"symbol": "GP_TRANSPORT", "name": "GP Transport", "position": "Ride Share Driver"},
}


def _normalize_shift_type(raw_shift: Any) -> str:
    key = str(raw_shift or "").strip().lower()
    if key in SHIFT_PROFILES:
        return key
    return "standard_shift"


def _upsert_employment_foundation(
    db: Session,
    *,
    player: Player,
    settled_day: int,
    job_key: str | None,
    shift_type: str | None,
) -> None:
    key = (job_key or "").strip().lower()
    if not key:
        return

    company = JOB_COMPANY_MAP.get(
        key,
        {"symbol": "GP_CONSUMER", "name": "Gold Penny Group", "position": key.replace("_", " ").title()},
    )
    normalized_shift = _normalize_shift_type(shift_type)

    row = (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player.id,
            PlayerEmploymentState.day == int(settled_day),
        )
        .first()
    )
    if row is None:
        row = PlayerEmploymentState(
            player_id=player.id,
            day=int(settled_day),
            current_job_code=key,
            monthly_pay_xgp=Decimal("0.00"),
            employed_flag=True,
            job_status="employed",
        )
        db.add(row)
        db.flush()

    row.current_job_code = key
    row.position_title = company["position"]
    row.employer_company_symbol = company["symbol"]
    row.employer_company_name = company["name"]
    row.shift_type = normalized_shift

def _resolve_player(db: Session, player_id: str) -> Player:
    raw_player_id = str(player_id or "").strip()
    if not raw_player_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found.")

    try:
        pid = UUID(raw_player_id)
    except ValueError:
        pid = None

    if pid is not None:
        player = db.query(Player).filter(Player.id == pid).first()
        if player is not None:
            return player

    # Day-1 dev usability guard: allow canonical gameplay routes to resolve by
    # external display name aliases (e.g. "player1") when UUID is not supplied.
    player = (
        db.query(Player)
        .filter(func.lower(Player.display_name) == raw_player_id.lower())
        .order_by(Player.created_at.asc())
        .first()
    )
    if player is not None:
        logger.info(
            "gameplay.player resolved by display_name alias.",
            extra={
                "requested_player_id": raw_player_id,
                "resolved_player_id": str(player.id),
            },
        )
        return player

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found.")


def _raise_gameplay_http_error(exc: Exception) -> None:
    if isinstance(exc, (OnboardingNotFoundError, SettlementNotFoundError, DailyBriefNotFoundError, JobMarketNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (SettlementValidationError, CareerValidationError, JobMarketValidationError)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, (DailySettlementError, OnboardingError, DailyBriefError, CareerError, JobMarketError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected gameplay service error.")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _is_new_player_first_session(player: Player) -> bool:
    return _safe_int(getattr(player, "last_settled_day", None), 0) <= 0


def _first_line(text_value: Any, fallback: str) -> str:
    raw = str(text_value or "").strip()
    if not raw:
        return fallback
    head = raw.splitlines()[0].strip()
    return head or fallback


def _job_options_payload() -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    # Keep six MVP options deterministic + stable for first-session UI.
    for cfg in sorted(CAREER_CONFIG.values(), key=lambda row: row.display_name)[:6]:
        company = JOB_COMPANY_MAP.get(
            cfg.job_key,
            {
                "symbol": "GP_CONSUMER",
                "name": "Gold Penny Group",
                "position": cfg.display_name,
            },
        )
        options.append(
            {
                "job_key": cfg.job_key,
                "title": cfg.display_name,
                "monthly_pay_xgp": _safe_float(cfg.base_pay_reference),
                "stability_weight": _safe_float(cfg.stability_weight),
                "performance_weight": _safe_float(cfg.performance_weight),
                "stress_sensitivity": _safe_float(cfg.stress_sensitivity),
                "employer_company_symbol": company["symbol"],
                "employer_company_name": company["name"],
                "position_title": company["position"],
                "default_shift_type": "standard_shift",
                "shift_options": [
                    {
                        "shift_type": shift_type,
                        "label": shift_meta["label"],
                        "window": shift_meta["window"],
                        "hours_worked": shift_meta["hours_worked"],
                    }
                    for shift_type, shift_meta in SHIFT_PROFILES.items()
                ],
            }
        )
    return options


def _starter_daily_brief(current_job: str | None) -> str:
    if current_job:
        return (
            f"Day 1 starter lane: run one {current_job.replace('_', ' ')} shift, "
            "then check pressure before ending the day."
        )
    return (
        "Day 1 starter lane: choose your first job, run one low-risk action, "
        "then review cash and stress before settlement."
    )


def _build_action_hub_payload(player: Player) -> dict[str, Any]:
    current_job = (player.main_job or "").strip()
    has_job = bool(current_job)
    is_first_session = _is_new_player_first_session(player)
    as_of_date = date.today().isoformat()
    job_options = _job_options_payload()

    recommended_actions: list[dict[str, Any]] = []
    available_actions: list[dict[str, Any]] = []
    blocked_actions: list[dict[str, Any]] = []
    top_tradeoffs: list[str] = []
    next_risk_warnings: list[str] = []

    if has_job:
        recommended_actions.append(
            {
                "action_key": "work_shift",
                "title": "Work Shift",
                "description": f"Use your current role ({current_job.replace('_', ' ')}) for stable day-1 cash.",
                "status": "recommended",
                "blockers": [],
                "tradeoffs": ["Consumes time units but improves short-term cash safety."],
                "warnings": [],
                "confidence_level": "high",
                "parameters": {
                    "job_name": current_job,
                    "shift_type": "standard_shift",
                    "hours_worked": SHIFT_PROFILES["standard_shift"]["hours_worked"],
                    "shift_options": [
                        {
                            "shift_type": shift_type,
                            "label": meta["label"],
                            "window": meta["window"],
                            "hours_worked": meta["hours_worked"],
                        }
                        for shift_type, meta in SHIFT_PROFILES.items()
                    ],
                },
            }
        )
        available_actions.append(
            {
                "action_key": "switch_job",
                "title": "Switch Job",
                "description": "Change role if your current lane does not fit your strategy.",
                "status": "available",
                "blockers": [],
                "tradeoffs": ["Role change can shift stress profile and promotion pace."],
                "warnings": [],
                "confidence_level": "medium",
                "parameters": {
                    "job_options": job_options,
                    "current_job_key": current_job,
                    "shift_type": "standard_shift",
                },
            }
        )
    else:
        recommended_actions.append(
            {
                "action_key": "switch_job",
                "title": "Choose Your First Job",
                "description": "Select one starter role to unlock reliable work-shift income.",
                "status": "recommended",
                "blockers": [],
                "tradeoffs": ["Higher pay roles can carry higher stress and tighter requirements."],
                "warnings": [],
                "confidence_level": "high",
                "parameters": {
                    "job_options": job_options,
                    "current_job_key": None,
                    "new_job_key": (job_options[0].get("job_key") if job_options else None),
                    "shift_type": "standard_shift",
                },
            }
        )
        blocked_actions.append(
            {
                "action_key": "work_shift",
                "title": "Work Shift",
                "description": "Complete job selection first to start earning from shifts.",
                "status": "blocked",
                "blockers": ["Choose your first job first."],
                "tradeoffs": [],
                "warnings": [],
                "confidence_level": "unknown",
                "parameters": {},
            }
        )

    available_actions.extend(
        [
            {
                "action_key": "study",
                "title": "Skill Training",
                "description": "Invest 2 hours in career growth for better long-term outcomes.",
                "status": "available",
                "blockers": [],
                "tradeoffs": ["No immediate cash today."],
                "warnings": [],
                "confidence_level": "medium",
                "parameters": {"training_hours": 2},
            },
            {
                "action_key": "side_income",
                "title": "Ride Share",
                "description": "Flexible emergency income with higher stress volatility.",
                "status": "available",
                "blockers": [],
                "tradeoffs": ["Variable payout and stress cost."],
                "warnings": ["Use short shifts to avoid stacking stress."],
                "confidence_level": "low",
                "parameters": {"hours_worked": 2},
            },
            {
                "action_key": "rest",
                "title": "Recovery Block",
                "description": "Lower stress and protect health before settlement.",
                "status": "available",
                "blockers": [],
                "tradeoffs": ["No direct income this action."],
                "warnings": [],
                "confidence_level": "high",
                "parameters": {},
            },
        ]
    )

    if has_job:
        top_tradeoffs.append("Use one cash-positive shift before optional upside actions.")
    else:
        top_tradeoffs.append("Pick a first job first so day-1 work actions unlock.")
    top_tradeoffs.append("Protect stress and health before ending the day.")

    if _safe_int(player.stress, 0) >= 65:
        next_risk_warnings.append("Stress is elevated. Mix recovery into your next move.")
    if _safe_float(player.debt_xgp, 0) > max(200.0, _safe_float(player.cash_xgp, 0)):
        next_risk_warnings.append("Debt pressure is high relative to cash buffer.")

    return {
        "player_id": str(player.id),
        "as_of_date": as_of_date,
        "recommended_actions": recommended_actions,
        "available_actions": available_actions,
        "blocked_actions": blocked_actions,
        "top_tradeoffs": top_tradeoffs,
        "next_risk_warnings": next_risk_warnings,
        "debug_meta": {
            "new_player_first_session": is_first_session,
            "has_starter_job_selected": has_job,
            "current_job_key": current_job or None,
            "job_options_count": len(job_options),
        },
    }


@router.get("/player/{player_id}/dashboard")
def get_gameplay_dashboard(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.dashboard request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/dashboard"},
    )
    try:
        player = _resolve_player(db, player_id)
        playable = get_playable_player_summary(db, player.id)
    except Exception as exc:
        _raise_gameplay_http_error(exc)

    brief_payload: dict[str, Any] | None = None
    economy_payload: dict[str, Any] | None = None
    job_payload: dict[str, Any] | None = None

    try:
        brief_payload = get_player_latest_daily_brief(db, player.id)
    except Exception:
        brief_payload = None

    try:
        economy_payload = build_economy_presentation_summary(db=db, player_id=str(player.id))
    except Exception:
        economy_payload = None

    try:
        job_payload = get_player_job_summary(db=db, player_id=str(player.id))
    except Exception:
        job_payload = None

    is_first_session = _is_new_player_first_session(player)
    current_job = (
        (job_payload or {}).get("current_job_code")
        or playable.get("latest_daily_brief", {}).get("current_job")
        or player.main_job
    )
    current_job = str(current_job).strip() if current_job else ""

    player_warnings = ((economy_payload or {}).get("player_warnings") or [])[:3]
    player_opportunities = ((economy_payload or {}).get("player_opportunities") or [])[:3]
    top_risks = [
        {"key": f"risk_{idx}", "title": str(item), "description": str(item), "severity": "warning"}
        for idx, item in enumerate(player_warnings)
    ]
    top_opportunities = [
        {"key": f"opportunity_{idx}", "title": str(item), "description": str(item), "severity": "positive"}
        for idx, item in enumerate(player_opportunities)
    ]

    if not top_risks:
        top_risks = [
            {
                "key": "risk_buffer",
                "title": "Protect cash buffer",
                "description": "Avoid high-volatility actions until baseline cash flow is stable.",
                "severity": "warning",
            }
        ]
    if not top_opportunities:
        top_opportunities = [
            {
                "key": "opportunity_shift",
                "title": "Run one cash-positive action",
                "description": "Take one low-risk income action before ending the day.",
                "severity": "info",
            }
        ]

    headline = _first_line(
        (brief_payload or {}).get("headline"),
        "Day 1 starter: stabilize income and protect downside.",
    )
    daily_brief = _first_line(
        (brief_payload or {}).get("summary"),
        _starter_daily_brief(current_job if current_job else None),
    )

    recommended_actions = [
        {
            "action_key": "work_shift" if current_job else "switch_job",
            "title": "Work Shift" if current_job else "Choose Your First Job",
            "reason": (
                f"Use {current_job.replace('_', ' ')} for immediate day-1 cash."
                if current_job
                else "Pick one starter role to unlock reliable day-1 work actions."
            ),
        }
    ]

    dashboard = {
        "player_id": str(player.id),
        "as_of_date": str((brief_payload or {}).get("day") or date.today().isoformat()),
        "headline": headline,
        "daily_brief": daily_brief,
        "stats": {
            "cash_xgp": _safe_float(playable.get("cash_xgp"), _safe_float(player.cash_xgp, 0.0)),
            "debt_xgp": _safe_float(playable.get("debt_xgp"), _safe_float(player.debt_xgp, 0.0)),
            "net_worth_xgp": _safe_float(playable.get("net_worth_xgp"), _safe_float(player.net_worth_xgp, 0.0)),
            "stress": _safe_int(playable.get("stress"), _safe_int(player.stress, 0)),
            "health": _safe_int(playable.get("health"), _safe_int(player.health, 100)),
            "credit_score": _safe_int(playable.get("credit_score"), _safe_int(player.credit_score, 650)),
            "current_job": current_job or None,
            "region_key": str(playable.get("region") or player.region or "suburban"),
        },
        "top_opportunities": top_opportunities,
        "top_risks": top_risks,
        "recommended_actions": recommended_actions,
        "debug_meta": {
            "new_player_first_session": is_first_session,
            "has_starter_job_selected": bool(current_job),
            "source_brief_available": brief_payload is not None,
            "source_economy_available": economy_payload is not None,
        },
    }
    logger.info(
        "gameplay.dashboard resolved.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "new_player_first_session": is_first_session,
            "has_starter_job_selected": bool(current_job),
        },
    )
    return dashboard


@router.get("/player/{player_id}/actions")
def get_gameplay_actions(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.actions request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/actions"},
    )
    try:
        player = _resolve_player(db, player_id)
        payload = _build_action_hub_payload(player)
        logger.info(
            "gameplay.actions resolved player action hub.",
            extra={
                "player_id": player_id,
                "resolved_player_id": str(player.id),
                "new_player_first_session": _is_new_player_first_session(player),
                "has_starter_job_selected": bool(player.main_job),
            },
        )
        return payload
    except Exception as exc:
        _raise_gameplay_http_error(exc)


@router.get("/player/{player_id}/action-hub")
def get_gameplay_action_hub_alias(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.action_hub alias route used.",
        extra={
            "player_id": player_id,
            "canonical_alias_route": "/gameplay/player/{player_id}/action-hub",
        },
    )
    return get_gameplay_actions(player_id=player_id, db=db)


@router.get("/player/{player_id}/end-of-day-summary")
def get_gameplay_end_of_day_summary(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.end_of_day_summary request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/end-of-day-summary"},
    )
    try:
        player = _resolve_player(db, player_id)
        payload = get_latest_settlement_summary(db, str(player.id))
        latest_completed_day = int(payload.get("day_number") or 0)
        summary_seen_day = int(getattr(player, "last_seen_settlement_day", 0) or 0)
        summary_seen_for_day = summary_seen_day >= latest_completed_day and latest_completed_day > 0
        should_auto_show = bool(latest_completed_day > 0 and not summary_seen_for_day)

        payload_debug_meta = dict(payload.get("debug_meta") or {})
        payload_debug_meta.update(
            {
                "latest_completed_day": latest_completed_day,
                "summary_seen_day": summary_seen_day,
                "summary_seen_for_day": summary_seen_for_day,
                "should_auto_show_summary": should_auto_show,
                "summary_gate_reason": (
                    "show_unseen_latest_settlement"
                    if should_auto_show
                    else "suppress_already_seen_or_missing"
                ),
            }
        )
        payload["debug_meta"] = payload_debug_meta

        logger.info(
            "gameplay.end_of_day_summary resolved settlement summary.",
            extra={
                "requested_player_id": player_id,
                "resolved_player_id": str(player.id),
                "summary_exists": True,
                "day_number": latest_completed_day,
                "summary_seen_day": summary_seen_day,
                "summary_seen_for_day": summary_seen_for_day,
                "should_auto_show_summary": should_auto_show,
            },
        )
        return payload
    except Exception as exc:
        logger.warning(
            "gameplay.end_of_day_summary unavailable for player.",
            extra={"requested_player_id": player_id, "summary_exists": False, "error": str(exc)},
        )
        _raise_gameplay_http_error(exc)


@router.post("/player/{player_id}/end-of-day-summary/ack")
def acknowledge_gameplay_end_of_day_summary(
    player_id: str,
    body: EndOfDaySummaryAckRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark latest settlement summary as acknowledged for one-time auto-show gating."""
    player = _resolve_player(db, player_id)
    latest = get_latest_settlement_summary(db, str(player.id))
    latest_completed_day = int(latest.get("day_number") or 0)
    target_day = int(body.day_number or latest_completed_day or 0)
    if target_day <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No completed day available to acknowledge.")
    if target_day > latest_completed_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot acknowledge day {target_day}; latest completed day is {latest_completed_day}.",
        )

    current_seen_day = int(getattr(player, "last_seen_settlement_day", 0) or 0)
    player.last_seen_settlement_day = max(current_seen_day, target_day)
    db.commit()
    logger.info(
        "gameplay.end_of_day_summary acknowledged.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "target_day": target_day,
            "latest_completed_day": latest_completed_day,
            "summary_seen_day": int(player.last_seen_settlement_day or 0),
        },
    )
    return {
        "player_id": str(player.id),
        "acknowledged_day": target_day,
        "latest_completed_day": latest_completed_day,
        "summary_seen_day": int(player.last_seen_settlement_day or 0),
    }


@router.get("/player/{player_id}/transactions")
def get_gameplay_transaction_history(
    player_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return recent cash movement history for gameplay auditing and UI display."""
    player = _resolve_player(db, player_id)
    rows = list_recent_player_transactions(db, player=player, limit=limit)
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row.metadata_json or "{}")
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        items.append(
            {
                "id": str(row.id),
                "player_id": str(player.id),
                "day": int(row.day) if row.day is not None else None,
                "type": row.transaction_type,
                "category": row.category,
                "symbol": row.asset_symbol,
                "quantity": float(row.quantity) if row.quantity is not None else None,
                "unit_price": float(row.unit_price) if row.unit_price is not None else None,
                "gross_amount": float(row.gross_amount),
                "fee_amount": float(row.fee_amount),
                "net_cash_delta": float(row.net_cash_delta),
                "resulting_cash_balance": float(row.resulting_cash_balance),
                "metadata_json": metadata,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"player_id": str(player.id), "count": len(items), "transactions": items}


@router.post("/player/{player_id}/end-day")
def post_gameplay_end_day(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.end_day request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/end-day"},
    )
    try:
        player = _resolve_player(db, player_id)
        logger.info(
            "gameplay.end_day resolved player.",
            extra={
                "requested_player_id": player_id,
                "resolved_player_id": str(player.id),
            },
        )
        return run_player_next_day(db, str(player.id))
    except Exception as exc:
        _raise_gameplay_http_error(exc)


@router.post("/player/{player_id}/actions/preview")
def preview_gameplay_action(
    player_id: str,
    body: GameplayActionPreviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    key = str(body.action_key or "").strip().lower()
    params = body.parameters or {}
    shift_type = _normalize_shift_type(params.get("shift_type"))
    shift_profile = SHIFT_PROFILES[shift_type]
    hours = max(1, _safe_int(params.get("hours_worked"), int(shift_profile["hours_worked"])))
    training = max(1, _safe_int(params.get("training_hours"), 2))

    base = {
        "player_id": str(player.id),
        "action_key": key,
        "summary": "Preview generated.",
        "expected_cash_impact": {"label": "Cash", "direction": "flat", "amount": 0, "text": "0"},
        "expected_stress_impact": {"label": "Stress", "direction": "flat", "amount": 0, "text": "0"},
        "expected_health_impact": {"label": "Health", "direction": "flat", "amount": 0, "text": "0"},
        "expected_time_impact": {"label": "Time", "direction": "down", "amount": -hours, "text": f"-{hours} units"},
        "expected_career_impact": {"label": "Career", "direction": "flat", "amount": 0, "text": "No material change"},
        "expected_distress_impact": {"label": "Distress", "direction": "flat", "amount": 0, "text": "No material change"},
        "blockers": [],
        "warnings": [],
        "confidence_level": "medium",
        "debug_meta": {"preview_route": "canonical"},
    }

    if key == "work_shift":
        base["summary"] = "Work shift should improve cash and add moderate stress."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "up", "amount": 65 * hours, "text": f"+~{65 * hours} xgp"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": max(1, hours), "text": f"+{max(1, hours)}"}
        base["expected_health_impact"] = {"label": "Health", "direction": "down", "amount": -max(0, hours // 4), "text": f"-{max(0, hours // 4)}"}
        base["debug_meta"] = {
            "preview_route": "canonical",
            "shift_type": shift_type,
            "shift_window": shift_profile["window"],
            "shift_label": shift_profile["label"],
        }
    elif key == "switch_job":
        base["summary"] = "Switching jobs changes pay trajectory and stress profile."
        base["expected_career_impact"] = {"label": "Career", "direction": "mixed", "text": "Role and progression path update"}
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
    elif key == "study":
        base["summary"] = "Training improves long-term growth with no immediate cash."
        base["expected_career_impact"] = {"label": "Career", "direction": "up", "amount": training, "text": f"+{training} training hours"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": 1, "text": "+1"}
    elif key == "side_income":
        base["summary"] = "Ride share adds variable cash with stress tradeoff."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "up", "amount": 20 * hours, "text": f"+~{20 * hours} xgp"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": max(1, hours), "text": f"+{max(1, hours)}"}
    elif key == "rest":
        base["summary"] = "Recovery lowers stress and improves health stability."
        base["expected_stress_impact"] = {"label": "Stress", "direction": "down", "amount": -6, "text": "-6"}
        base["expected_health_impact"] = {"label": "Health", "direction": "up", "amount": 3, "text": "+3"}
        base["expected_time_impact"] = {"label": "Time", "direction": "down", "amount": -1, "text": "-1 units"}
    elif key == "eat_meal":
        meal_type = str(params.get("meal_type") or "meal").strip().lower()
        base["summary"] = f"Eating {meal_type} costs 6 XGP and restores health and reduces stress."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "down", "amount": -6, "text": "-6 XGP"}
        base["expected_health_impact"] = {"label": "Health", "direction": "up", "amount": 5, "text": "+5"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "down", "amount": -3, "text": "-3"}
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
    elif key == "quick_loan":
        raw_amount = max(100, min(500, int(params.get("loan_amount") or 200)))
        due = round(raw_amount * 1.15, 2)
        base["summary"] = f"Borrow {raw_amount} XGP now and owe {due} XGP (15% interest)."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "up", "amount": raw_amount, "text": f"+{raw_amount} XGP"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": 5, "text": "+5"}
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
        base["warnings"] = [f"You will owe {due} XGP total. Pay before weekly settlement to avoid credit damage."]
    elif key == "select_housing":
        housing_type = str(params.get("housing_type") or "suburban").lower()
        HOUSING_INFO = {
            "suburban": "Weekly rent 80 XGP, gas 40 XGP, lower stress.",
            "downtown": "Weekly rent 140 XGP, gas 20 XGP, higher stress.",
        }
        base["summary"] = f"{housing_type.capitalize()} housing: {HOUSING_INFO.get(housing_type, '')}"
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}

    return base


@router.post("/player/{player_id}/actions/execute")
def execute_gameplay_action(
    player_id: str,
    body: GameplayActionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    action_key = str(body.action_key or "").strip().lower()
    params = body.parameters or {}
    logger.info(
        "gameplay.actions.execute request received.",
        extra={"player_id": player_id, "action_key": action_key},
    )

    if action_key == "switch_job":
        target = str(params.get("new_job_key") or params.get("job_key") or params.get("target_job") or "").strip()
        if not target:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="switch_job requires new_job_key.")
        shift_type = _normalize_shift_type(params.get("shift_type"))
        try:
            result = switch_player_job(db, player_id, target)
            _upsert_employment_foundation(
                db,
                player=player,
                settled_day=max(1, _safe_int(getattr(player, "last_settled_day", None), 0) + 1),
                job_key=target,
                shift_type=shift_type,
            )
            db.commit()
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": str(result.get("message") or "Job switched."),
                "result_summary": str(result.get("message") or f"Switched to {target}."),
                "time_cost_units": 1,
                "cash_delta_xgp": 0.0,
                "stress_delta": 0,
                "health_delta": 0,
                "raw_result": {
                    **result,
                    "employer_company_symbol": JOB_COMPANY_MAP.get(target, {}).get("symbol"),
                    "employer_company_name": JOB_COMPANY_MAP.get(target, {}).get("name"),
                    "position_title": JOB_COMPANY_MAP.get(target, {}).get("position"),
                    "shift_type": shift_type,
                },
            }
        except Exception as exc:
            db.rollback()
            _raise_gameplay_http_error(exc)

    if action_key == "work_shift":
        shift_type = _normalize_shift_type(params.get("shift_type"))
        shift_profile = SHIFT_PROFILES[shift_type]
        requested_hours = _safe_int(params.get("hours_worked"), int(shift_profile["hours_worked"]))
        hours_worked = max(1, min(8, requested_hours))
        job_name = str(params.get("job_name") or player.main_job or "").strip().lower()
        if not job_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose a job before running work_shift.")
        try:
            result = _work_engine.process_work_action(db=db, player=player, job_name=job_name, hours_worked=hours_worked)
            _upsert_employment_foundation(
                db,
                player=player,
                settled_day=max(1, _safe_int(getattr(player, "last_settled_day", None), 0) + 1),
                job_key=job_name,
                shift_type=shift_type,
            )
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": "Work shift completed.",
                "result_summary": f"Worked {result.hours_worked}h as {result.job_name.replace('_', ' ')}.",
                "time_cost_units": max(1, min(4, result.hours_worked // 2)),
                "cash_delta_xgp": _safe_float(result.earned_cash),
                "stress_delta": _safe_int(result.stress_change),
                "health_delta": _safe_int(result.health_change),
                "raw_result": {
                    "job_name": result.job_name,
                    "hours_worked": result.hours_worked,
                    "earned_cash": _safe_float(result.earned_cash),
                    "productivity": _safe_float(result.productivity),
                    "shift_type": shift_type,
                    "shift_window": shift_profile["window"],
                    "shift_label": shift_profile["label"],
                    "employer_company_symbol": JOB_COMPANY_MAP.get(job_name, {}).get("symbol"),
                    "employer_company_name": JOB_COMPANY_MAP.get(job_name, {}).get("name"),
                },
            }
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except Exception as exc:
            _raise_gameplay_http_error(exc)

    if action_key == "study":
        training_hours = Decimal(str(max(1, min(4, _safe_int(params.get("training_hours"), 2)))))
        try:
            result = apply_daily_career_progression(
                db=db,
                player_id=player_id,
                training_hours=training_hours,
                commit=True,
            )
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": "Training logged.",
                "result_summary": "Training completed. Career progression updated.",
                "time_cost_units": int(training_hours),
                "cash_delta_xgp": 0.0,
                "stress_delta": 1,
                "health_delta": 0,
                "raw_result": result,
            }
        except Exception as exc:
            db.rollback()
            _raise_gameplay_http_error(exc)

    if action_key == "side_income":
        hours_worked = max(1, min(6, _safe_int(params.get("hours_worked"), 2)))
        try:
            result = process_rideshare_action(db=db, player=player, hours_worked=float(hours_worked))
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": "Ride share completed.",
                "result_summary": "Side-income shift completed.",
                "time_cost_units": max(1, min(4, hours_worked // 2)),
                "cash_delta_xgp": _safe_float(result.get("net_income_xgp")),
                "stress_delta": _safe_int(result.get("stress_change")),
                "health_delta": _safe_int(result.get("health_change")),
                "raw_result": result,
            }
        except Exception as exc:
            _raise_gameplay_http_error(exc)

    if action_key == "rest":
        stress_before = _safe_int(player.stress, 0)
        health_before = _safe_int(player.health, 100)
        player.stress = max(0, stress_before - 6)
        player.health = min(100, health_before + 3)
        db.commit()
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": "Recovery complete.",
            "result_summary": "You took a recovery block and stabilized pressure.",
            "time_cost_units": 1,
            "cash_delta_xgp": 0.0,
            "stress_delta": player.stress - stress_before,
            "health_delta": player.health - health_before,
            "raw_result": {
                "stress_before": stress_before,
                "stress_after": _safe_int(player.stress, stress_before),
                "health_before": health_before,
                "health_after": _safe_int(player.health, health_before),
            },
        }

    # ── Step 74: eat_meal ─────────────────────────────────────────────────────
    if action_key == "eat_meal":
        meal_type = str(params.get("meal_type") or "meal").strip().lower()
        MEAL_COSTS: dict[str, int] = {"breakfast": 6, "lunch": 6, "dinner": 6}
        meal_cost = Decimal(str(MEAL_COSTS.get(meal_type, 6)))
        cash_before = Decimal(str(_safe_float(getattr(player, "cash", 0))))
        if cash_before < meal_cost:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Not enough XGP for a {meal_type}. Need {meal_cost} XGP.",
            )
        stress_before = _safe_int(player.stress, 0)
        health_before = _safe_int(player.health, 100)
        player.cash = cash_before - meal_cost  # type: ignore[assignment]
        player.health = min(100, health_before + 5)
        player.stress = max(0, stress_before - 3)
        db.commit()
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"{meal_type.capitalize()} eaten.",
            "result_summary": f"You ate {meal_type} (-{meal_cost} XGP, +5 health, -3 stress).",
            "time_cost_units": 0,
            "cash_delta_xgp": -float(meal_cost),
            "stress_delta": player.stress - stress_before,
            "health_delta": player.health - health_before,
            "raw_result": {
                "meal_type": meal_type,
                "meal_cost_xgp": float(meal_cost),
                "cash_after": float(player.cash),  # type: ignore[arg-type]
                "health_before": health_before,
                "health_after": _safe_int(player.health, health_before),
                "stress_before": stress_before,
                "stress_after": _safe_int(player.stress, stress_before),
            },
        }

    # ── Step 74: quick_loan ───────────────────────────────────────────────────
    if action_key == "quick_loan":
        raw_amount = _safe_int(params.get("loan_amount"), 200)
        loan_amount = Decimal(str(max(100, min(500, raw_amount))))
        interest_rate = Decimal("0.15")  # 15% flat
        due_amount = (loan_amount * (1 + interest_rate)).quantize(Decimal("0.01"))
        cash_before = Decimal(str(_safe_float(getattr(player, "cash", 0))))
        debt_before = Decimal(str(_safe_float(getattr(player, "debt_xgp", 0))))
        stress_before = _safe_int(player.stress, 0)
        player.cash = cash_before + loan_amount  # type: ignore[assignment]
        player.debt_xgp = debt_before + due_amount  # type: ignore[assignment]
        player.stress = min(100, stress_before + 5)
        db.commit()
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"Borrowed {loan_amount} XGP.",
            "result_summary": f"Quick loan of {loan_amount} XGP received. You owe {due_amount} XGP (15% interest).",
            "time_cost_units": 0,
            "cash_delta_xgp": float(loan_amount),
            "stress_delta": player.stress - stress_before,
            "health_delta": 0,
            "raw_result": {
                "loan_amount_xgp": float(loan_amount),
                "interest_rate": float(interest_rate),
                "due_amount_xgp": float(due_amount),
                "cash_after": float(player.cash),  # type: ignore[arg-type]
                "debt_after": float(player.debt_xgp),  # type: ignore[arg-type]
                "stress_after": _safe_int(player.stress, stress_before),
            },
        }

    # ── Step 74: select_housing ───────────────────────────────────────────────
    if action_key == "select_housing":
        housing_type = str(params.get("housing_type") or "suburban").strip().lower()
        if housing_type not in ("suburban", "downtown"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="housing_type must be 'suburban' or 'downtown'.",
            )
        player.region = housing_type  # type: ignore[assignment]
        player.housing_region_id = housing_type  # type: ignore[assignment]
        db.commit()
        HOUSING_INFO = {
            "suburban": {"rent_xgp": 80, "stress_modifier": -2, "gas_xgp": 40},
            "downtown": {"rent_xgp": 140, "stress_modifier": +5, "gas_xgp": 20},
        }
        info = HOUSING_INFO[housing_type]
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"Housing set to {housing_type}.",
            "result_summary": (
                f"You chose {housing_type.capitalize()} housing. "
                f"Weekly rent: {info['rent_xgp']} XGP. "
                f"Weekly gas: {info['gas_xgp']} XGP."
            ),
            "time_cost_units": 0,
            "cash_delta_xgp": 0.0,
            "stress_delta": info["stress_modifier"],
            "health_delta": 0,
            "raw_result": {
                "housing_type": housing_type,
                "weekly_rent_xgp": info["rent_xgp"],
                "weekly_gas_xgp": info["gas_xgp"],
                "stress_modifier": info["stress_modifier"],
            },
        }

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported action_key '{action_key}'.",
    )
