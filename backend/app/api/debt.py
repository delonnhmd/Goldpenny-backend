from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.daily_settlement_service import SettlementNotFoundError, get_next_player_day
from app.services.debt_credit_service import (
    DebtCreditError,
    DebtCreditNotFoundError,
    DebtCreditValidationError,
    apply_daily_debt_and_credit,
    get_player_debt_credit_logs,
    get_player_debt_credit_summary,
)

router = APIRouter()


class DebtProcessResponse(BaseModel):
    player_id: str
    day: int
    opening_debt_xgp: float
    payment_due_xgp: float
    payment_made_xgp: float
    interest_added_xgp: float
    ending_debt_xgp: float
    payment_status: str
    opening_credit_score: int
    credit_score_change: int
    ending_credit_score: int
    delinquency_flag: bool
    already_processed: bool = False


class DebtSummaryResponse(BaseModel):
    player_id: str
    current_debt_xgp: float
    current_credit_score: int
    latest_day: int | None = None
    opening_debt_xgp: float | None = None
    payment_due_xgp: float | None = None
    payment_made_xgp: float | None = None
    interest_added_xgp: float | None = None
    ending_debt_xgp: float | None = None
    payment_status: str | None = None
    opening_credit_score: int | None = None
    credit_score_change: int | None = None
    ending_credit_score: int | None = None
    delinquency_flag: bool | None = None


class DebtCreditLogItem(BaseModel):
    id: str
    player_id: str
    day: int
    opening_debt_xgp: float
    payment_due_xgp: float
    payment_made_xgp: float
    interest_added_xgp: float
    ending_debt_xgp: float
    payment_status: str
    opening_credit_score: int
    credit_score_change: int
    ending_credit_score: int
    delinquency_flag: bool
    notes_json: str | None = None
    created_at: str | None = None


class DebtLogsResponse(BaseModel):
    player_id: str
    count: int
    logs: list[DebtCreditLogItem]


def _raise_debt_service_http_error(exc: Exception) -> None:
    if isinstance(exc, SettlementNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, DebtCreditNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, DebtCreditValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, DebtCreditError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected debt-credit service error.")


@router.post("/player/{player_id}/process", response_model=DebtProcessResponse, summary="Process one debt-credit day")
def process_player_debt_credit(
    player_id: str,
    day: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> DebtProcessResponse:
    try:
        target_day = int(day) if day is not None else int(get_next_player_day(db, player_id))
        result = apply_daily_debt_and_credit(
            db=db,
            player_id=player_id,
            day=target_day,
            commit=True,
            mutate_player=True,
        )
    except Exception as exc:
        _raise_debt_service_http_error(exc)
    return DebtProcessResponse(**result)


@router.get("/player/{player_id}/summary", response_model=DebtSummaryResponse, summary="Get debt-credit summary")
def get_player_debt_summary(player_id: str, db: Session = Depends(get_db)) -> DebtSummaryResponse:
    try:
        result = get_player_debt_credit_summary(db=db, player_id=player_id)
    except Exception as exc:
        _raise_debt_service_http_error(exc)
    return DebtSummaryResponse(**result)


@router.get("/player/{player_id}/logs", response_model=DebtLogsResponse, summary="Get debt-credit logs")
def get_player_debt_logs(
    player_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> DebtLogsResponse:
    try:
        result = get_player_debt_credit_logs(db=db, player_id=player_id, limit=limit)
    except Exception as exc:
        _raise_debt_service_http_error(exc)
    return DebtLogsResponse(**result)
