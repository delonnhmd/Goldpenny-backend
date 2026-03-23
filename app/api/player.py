from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

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
from app.models.user import User

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
    profile = db.query(Player).filter(Player.user_id == current_user.id).first()
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
        "created_at": profile.created_at,
    }


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
