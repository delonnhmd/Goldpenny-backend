"""Finance API - Step 20 distress, debt trap, and recovery arc endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.financial_distress_service import (
    FinancialDistressError,
    FinancialDistressNotFoundError,
    FinancialDistressValidationError,
    get_player_credit_snapshot,
    get_player_debt_snapshot,
    get_player_distress_history,
    queue_player_recovery_action,
)

router = APIRouter()


class PlayerCreditSnapshot(BaseModel):
    player_id: str
    credit_score: int
    total_debt_xgp: float
    required_daily_debt_payment_xgp: float
    debt_utilization_ratio: float
    missed_payment_streak: int
    on_payment_plan: bool
    distress_state: str
    distress_score: float
    borrowing_cost_modifier: float
    opportunity_access_penalty: float
    business_risk_penalty: float
    career_progress_penalty: float
    debug_meta: dict = Field(default_factory=dict)


class PlayerDebtSnapshot(BaseModel):
    player_id: str
    total_debt_xgp: float
    debt_payment_due_xgp: float
    accrued_interest_xgp: float
    late_fee_xgp: float
    debt_utilization_ratio: float
    recovery_actions_available: list[str] = Field(default_factory=list)
    debug_meta: dict = Field(default_factory=dict)


class FinancialDistressHistoryResponse(BaseModel):
    player_id: str
    entries: list[dict] = Field(default_factory=list)
    trailing_7d_avg_distress_score: float = 0.0
    trailing_7d_missed_payments: int = 0
    trailing_7d_credit_change: int = 0
    recovery_streak_days: int = 0


class RecoveryActionRequest(BaseModel):
    action_key: str


class RecoveryActionResponse(BaseModel):
    player_id: str
    action_queued: str
    queued_actions: list[str] = Field(default_factory=list)
    on_payment_plan: bool
    credit_snapshot: PlayerCreditSnapshot


def _raise_finance_http_error(exc: Exception) -> None:
    if isinstance(exc, FinancialDistressNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, FinancialDistressValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, FinancialDistressError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected finance service error.")


@router.get("/player/{player_id}/credit", response_model=PlayerCreditSnapshot)
def get_player_credit_snapshot_route(player_id: str, db: Session = Depends(get_db)) -> PlayerCreditSnapshot:
    try:
        payload = get_player_credit_snapshot(db=db, player_id=player_id)
    except Exception as exc:
        _raise_finance_http_error(exc)
    return PlayerCreditSnapshot(**payload)


@router.get("/player/{player_id}/distress/history", response_model=FinancialDistressHistoryResponse)
def get_player_distress_history_route(
    player_id: str,
    limit: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
) -> FinancialDistressHistoryResponse:
    try:
        payload = get_player_distress_history(db=db, player_id=player_id, limit=limit)
    except Exception as exc:
        _raise_finance_http_error(exc)
    return FinancialDistressHistoryResponse(**payload)


@router.post("/player/{player_id}/recovery-action", response_model=RecoveryActionResponse)
def queue_recovery_action_route(
    player_id: str,
    body: RecoveryActionRequest,
    db: Session = Depends(get_db),
) -> RecoveryActionResponse:
    try:
        queued = queue_player_recovery_action(db=db, player_id=player_id, action_key=body.action_key)
        snapshot = get_player_credit_snapshot(db=db, player_id=player_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_finance_http_error(exc)
    return RecoveryActionResponse(**queued, credit_snapshot=PlayerCreditSnapshot(**snapshot))


@router.get("/player/{player_id}/debt", response_model=PlayerDebtSnapshot)
def get_player_debt_snapshot_route(player_id: str, db: Session = Depends(get_db)) -> PlayerDebtSnapshot:
    try:
        payload = get_player_debt_snapshot(db=db, player_id=player_id)
    except Exception as exc:
        _raise_finance_http_error(exc)
    return PlayerDebtSnapshot(**payload)
