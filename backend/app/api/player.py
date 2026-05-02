import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.life_balance_service import (
    LifeBalanceError,
    LifeBalanceNotFoundError,
    LifeBalanceValidationError,
    get_player_life_history,
    get_player_life_snapshot,
)
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.services.annual_recap_service import (
    AnnualRecapError,
    AnnualRecapNotFoundError,
    AnnualRecapUnavailableError,
    AnnualRecapValidationError,
    build_player_annual_recap,
)
from app.services.black_swan_service import (
    BlackSwanError,
    BlackSwanNotFoundError,
    get_pending_black_swan_event,
    mark_black_swan_seen,
)
from app.models.user import User
from app.services.player_onboarding_service import create_survival_player_profile
from app.services.run_end_service import (
    RunEndError,
    RunEndNotFoundError,
    get_player_run_status,
    retire_player_run,
)
from app.services.timeline_service import (
    TimelineError,
    TimelineNotFoundError,
    build_player_timeline,
)

router = APIRouter()


class TimeBudgetSnapshot(BaseModel):
    as_of_date: str
    total_hours_used: float
    job_hours: float
    business_hours: float
    side_income_hours: float
    commute_hours: float
    sleep_hours: float
    recovery_hours: float
    overtime_hours: float


class PlayerLifeSnapshot(BaseModel):
    player_id: str
    as_of_date: str
    stress_before: int
    stress_after: int
    health_before: int
    health_after: int
    stress_delta: int
    health_delta: int
    productivity_modifier: float
    burnout_risk: float
    medical_event_risk: float
    medical_cost_xgp: float
    missed_work_penalty_xgp: float
    time_budget: TimeBudgetSnapshot
    debug_meta: dict = Field(default_factory=dict)


class PlayerLifeDailyResponse(BaseModel):
    player_id: str
    as_of_date: str
    life_summary: str
    time_budget_summary: str
    stress: int
    health: int
    productivity_modifier: float
    burnout_risk: float
    medical_event_risk: float
    medical_cost_xgp: float
    missed_work_penalty_xgp: float
    debug_meta: dict = Field(default_factory=dict)


class PlayerLifeHistoryResponse(BaseModel):
    player_id: str
    entries: list[dict] = Field(default_factory=list)
    trailing_7d_avg_stress: float = 0.0
    trailing_7d_avg_health: float = 0.0
    trailing_7d_avg_sleep: float = 0.0
    trailing_7d_avg_productivity: float = 0.0


class AnnualRecapResponse(BaseModel):
    year: int
    days_survived: int
    starting_net_worth: float
    ending_net_worth: float
    net_worth_change: float
    cash: float
    debt: float
    credit_score: int
    businesses_owned: int
    land_owned: int
    best_streak: int
    total_income: float
    total_expenses: float
    biggest_win: str
    biggest_loss: str
    top_event: str
    title: str


class TimelineEventResponse(BaseModel):
    day: int
    type: str
    title: str
    description: str
    impact_level: str
    icon: str


class BlackSwanEventResponse(BaseModel):
    id: str
    player_id: str
    day: int
    event_type: str
    title: str
    description: str
    severity_score: float
    source_event_id: str | None = None
    payload: dict = Field(default_factory=dict)
    push_payload: dict = Field(default_factory=dict)
    seen_at: str | None = None
    created_at: str | None = None


def _raise_life_http_error(exc: Exception) -> None:
    if isinstance(exc, LifeBalanceNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LifeBalanceValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, LifeBalanceError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected life service error.")


@router.get("/profile")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    profile = db.query(Player).filter(Player.user_id == str(current_user.id)).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "cash": float(profile.cash),
        "gender": profile.gender,
        "health": profile.health,
        "stress": profile.stress,
        "fatigue": profile.fatigue,
        "productivity_modifier": float(getattr(profile, "productivity_modifier", 1.0) or 1.0),
        "base_productivity_modifier": float(getattr(profile, "base_productivity_modifier", 1.0) or 1.0),
        "burnout_risk": float(getattr(profile, "burnout_risk", 0.0) or 0.0),
        "medical_event_risk": float(getattr(profile, "medical_event_risk", 0.0) or 0.0),
        "skill_level": profile.skill_level,
        "main_job": profile.main_job,
        "side_job": profile.side_job,
        "credit_score": profile.credit_score,
        "required_daily_debt_payment_xgp": float(getattr(profile, "required_daily_debt_payment_xgp", 0.0) or 0.0),
        "debt_utilization_ratio": float(getattr(profile, "debt_utilization_ratio", 0.0) or 0.0),
        "missed_payment_streak": int(getattr(profile, "missed_payment_streak", 0) or 0),
        "on_payment_plan": bool(getattr(profile, "on_payment_plan", False)),
        "distress_state": str(getattr(profile, "distress_state", "stable") or "stable"),
        "distress_score": float(getattr(profile, "distress_score", 0.0) or 0.0),
        "borrowing_cost_modifier": float(getattr(profile, "borrowing_cost_modifier", 1.0) or 1.0),
        "opportunity_access_penalty": float(getattr(profile, "opportunity_access_penalty", 0.0) or 0.0),
        "business_risk_penalty": float(getattr(profile, "business_risk_penalty", 0.0) or 0.0),
        "career_progress_penalty": float(getattr(profile, "career_progress_penalty", 0.0) or 0.0),
        "reputation": profile.reputation,
        "hours_available": profile.hours_available,
        "total_hours_worked_today": profile.total_hours_worked_today,
        "work_actions_today": profile.work_actions_today,
        "run_status": getattr(profile, "run_status", "active") or "active",
        "created_at": profile.created_at,
    }


def _raise_annual_recap_http_error(exc: Exception) -> None:
    if isinstance(exc, AnnualRecapNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AnnualRecapUnavailableError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, AnnualRecapValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, AnnualRecapError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected annual recap error.")


def _raise_timeline_http_error(exc: Exception) -> None:
    if isinstance(exc, TimelineNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, TimelineError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected timeline error.")


def _raise_black_swan_http_error(exc: Exception) -> None:
    if isinstance(exc, BlackSwanNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BlackSwanError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected black swan error.")


@router.get("/{player_id}/annual-recap", response_model=AnnualRecapResponse)
def get_player_annual_recap_route(
    player_id: str,
    year: int = Query(default=1, ge=1, le=1),
    debug: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> AnnualRecapResponse:
    try:
        payload = build_player_annual_recap(db, player_id, year=year, debug=debug)
    except Exception as exc:
        _raise_annual_recap_http_error(exc)
    return AnnualRecapResponse(**payload)


@router.get("/{player_id}/black-swan/pending", response_model=BlackSwanEventResponse | None)
def get_pending_black_swan_event_route(
    player_id: str,
    db: Session = Depends(get_db),
) -> BlackSwanEventResponse | None:
    try:
        payload = get_pending_black_swan_event(db, player_id)
    except Exception as exc:
        _raise_black_swan_http_error(exc)
    return BlackSwanEventResponse(**payload) if payload is not None else None


@router.post("/{player_id}/black-swan/{event_id}/seen", response_model=BlackSwanEventResponse)
def mark_black_swan_seen_route(
    player_id: str,
    event_id: str,
    db: Session = Depends(get_db),
) -> BlackSwanEventResponse:
    try:
        payload = mark_black_swan_seen(db, player_id, event_id)
    except Exception as exc:
        _raise_black_swan_http_error(exc)
    return BlackSwanEventResponse(**payload)


@router.get("/{player_id}/timeline", response_model=list[TimelineEventResponse])
def get_player_timeline_route(
    player_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[TimelineEventResponse]:
    try:
        payload = build_player_timeline(db, player_id, limit=limit)
    except Exception as exc:
        _raise_timeline_http_error(exc)
    return [TimelineEventResponse(**event) for event in payload]


@router.get("/{player_id}/life", response_model=PlayerLifeSnapshot)
def get_player_life_snapshot_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PlayerLifeSnapshot:
    try:
        payload = get_player_life_snapshot(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_life_http_error(exc)
    return PlayerLifeSnapshot(**payload)


@router.get("/{player_id}/life/history", response_model=PlayerLifeHistoryResponse)
def get_player_life_history_route(
    player_id: str,
    limit: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
) -> PlayerLifeHistoryResponse:
    try:
        payload = get_player_life_history(db=db, player_id=player_id, limit=limit)
    except Exception as exc:
        _raise_life_http_error(exc)
    return PlayerLifeHistoryResponse(**payload)


STARTER_REGION = "suburban"


class CreateLinkedPlayerByUserIdRequest(BaseModel):
    display_name: str | None = None
    signup_answers: dict[str, str] | None = None


def _serialize_player(player: Player) -> dict:
    return {
        "id": str(player.id),
        "user_id": player.user_id,
        "display_name": player.display_name,
        "gender": player.gender,
        "region": player.region,
        "cash_xgp": float(player.cash or 0),
        "bank_savings_xgp": float(player.bank_savings_xgp or 0),
        "debt_xgp": float(player.debt_xgp or 0),
        "credit_score": int(player.credit_score or 0),
        "net_worth_xgp": float(player.net_worth or 0),
        "health": int(player.health or 0),
        "stress": int(player.stress or 0),
        "skill_level": int(player.skill_level or 1),
        "main_job": player.main_job,
        "side_job": player.side_job,
        "hours_available": int(player.hours_available or 0),
        "account_created_day": int(player.account_created_day or 1),
        "main_shift_active_flag": bool(player.main_shift_active_flag or False),
        "main_shift_status": str(player.main_shift_status or "idle"),
        "run_status": str(getattr(player, "run_status", "active") or "active"),
        "created_at": player.created_at.isoformat() if player.created_at else None,
    }


def _raise_run_end_http_error(exc: Exception) -> None:
    if isinstance(exc, RunEndNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, RunEndError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected run lifecycle error.")


@router.get("/{player_id}/run-status")
def get_player_run_status_route(
    player_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_player_run_status(db, player_id)
    except Exception as exc:
        _raise_run_end_http_error(exc)


@router.post("/{player_id}/retire")
def retire_player_run_route(
    player_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return retire_player_run(db, player_id)
    except Exception as exc:
        db.rollback()
        _raise_run_end_http_error(exc)


@router.get("/by-user-id/{user_id}")
def get_player_by_user_id(
    user_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Return the canonical player linked to a Supabase Auth user id."""
    cleaned = (user_id or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="user_id is required.")

    existing = db.query(Player).filter(Player.user_id == cleaned).first()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    return _serialize_player(existing)


@router.post("/by-user-id/{user_id}", status_code=status.HTTP_200_OK)
def create_player_by_user_id(
    user_id: str,
    body: CreateLinkedPlayerByUserIdRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create the canonical player linked to a Supabase Auth user id if missing."""
    cleaned = (user_id or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="user_id is required.")

    existing = db.query(Player).filter(Player.user_id == cleaned).first()
    if existing is not None:
        return _serialize_player(existing)

    try:
        player = create_survival_player_profile(
            db,
            user_id=cleaned,
            display_name=body.display_name,
            fallback_email=None,
            region=STARTER_REGION,
            questionnaire_answers=body.signup_answers,
            daily_state_note="supabase_linked_player_created",
        )
        player.main_shift_active_flag = False
        player.main_shift_status = "idle"
        db.commit()
        db.refresh(player)
    except IntegrityError:
        db.rollback()
        player = db.query(Player).filter(Player.user_id == cleaned).first()
        if player is None:
            logger.exception(
                "player_by_user_id_integrity_error_no_existing_row",
                extra={"user_id": cleaned},
            )
            raise HTTPException(
                status_code=500,
                detail="Could not create your player profile right now. Please try again.",
            )
    except Exception:
        db.rollback()
        logger.exception(
            "player_by_user_id_create_failed",
            extra={"user_id": cleaned},
        )
        raise HTTPException(
            status_code=500,
            detail="Could not create your player profile right now. Please try again.",
        )

    return _serialize_player(player)


@router.get("/{player_id}/time-budget/latest", response_model=TimeBudgetSnapshot)
def get_player_time_budget_latest_route(
    player_id: str,
    db: Session = Depends(get_db),
) -> TimeBudgetSnapshot:
    try:
        snapshot = get_player_life_snapshot(db=db, player_id=player_id)
    except Exception as exc:
        _raise_life_http_error(exc)
    return TimeBudgetSnapshot(**snapshot["time_budget"])
