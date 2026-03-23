"""Step 37 consumer borrowing endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.consumer_borrowing_service import (
    ConsumerBorrowingError,
    ConsumerBorrowingNotFoundError,
    ConsumerBorrowingValidationError,
    apply_borrowing_decision,
    build_borrowing_eligibility_profile,
    build_borrowing_pressure_summary,
    build_borrowing_risk_summary,
    build_consumer_borrowing_system_summary,
    build_emergency_liquidity_state,
    generate_borrowing_options,
    get_player_borrowing_history,
    get_player_loan_accounts,
)
from app.schemas.consumer_borrowing import (
    BorrowingDecisionRequest,
    BorrowingDecisionResponse,
    BorrowingEligibilityProfileResponse,
    BorrowingOptionsResponse,
    BorrowingPressureSummaryResponse,
    BorrowingRiskSummaryResponse,
    ConsumerBorrowingSystemSummaryResponse,
    EmergencyLiquidityStateResponse,
    PlayerBorrowingHistoryResponse,
    PlayerLoanAccountsResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ConsumerBorrowingNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConsumerBorrowingValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ConsumerBorrowingError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected consumer borrowing error.")


@router.get("/player/{player_id}/eligibility-profile", response_model=BorrowingEligibilityProfileResponse)
def get_eligibility_profile_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> BorrowingEligibilityProfileResponse:
    """Return rolling borrowing-access profile."""
    try:
        payload = build_borrowing_eligibility_profile(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return BorrowingEligibilityProfileResponse(**payload)


@router.get("/player/{player_id}/liquidity-state", response_model=EmergencyLiquidityStateResponse)
def get_liquidity_state_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> EmergencyLiquidityStateResponse:
    """Return emergency liquidity and bridge-need summary."""
    try:
        payload = build_emergency_liquidity_state(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return EmergencyLiquidityStateResponse(**payload)


@router.get("/player/{player_id}/options", response_model=BorrowingOptionsResponse)
def get_borrowing_options_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    include_locked: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> BorrowingOptionsResponse:
    """Return dynamic borrowing options for the current player/day."""
    try:
        payload = generate_borrowing_options(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
            include_locked=bool(include_locked),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return BorrowingOptionsResponse(**payload)


@router.get("/player/{player_id}/risk-summary", response_model=BorrowingRiskSummaryResponse)
def get_borrowing_risk_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> BorrowingRiskSummaryResponse:
    """Return borrowing risk classification and trap/stabilization guidance."""
    try:
        payload = build_borrowing_risk_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return BorrowingRiskSummaryResponse(**payload)


@router.get("/player/{player_id}/pressure-summary", response_model=BorrowingPressureSummaryResponse)
def get_borrowing_pressure_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> BorrowingPressureSummaryResponse:
    """Return compact emergency borrowing pressure + practical actions."""
    try:
        payload = build_borrowing_pressure_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return BorrowingPressureSummaryResponse(**payload)


@router.post("/player/{player_id}/accept-offer", response_model=BorrowingDecisionResponse)
def accept_borrowing_offer_route(
    player_id: str,
    request: BorrowingDecisionRequest = Body(...),
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> BorrowingDecisionResponse:
    """Accept one borrowing offer and persist loan + history state."""
    try:
        payload = apply_borrowing_decision(
            db=db,
            player_id=player_id,
            offer_key=request.offer_key,
            principal_requested_xgp=request.principal_requested_xgp,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return BorrowingDecisionResponse(**payload)


@router.get("/player/{player_id}/loan-accounts", response_model=PlayerLoanAccountsResponse)
def get_loan_accounts_route(
    player_id: str,
    include_closed: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> PlayerLoanAccountsResponse:
    """Return player loan account snapshots."""
    try:
        payload = get_player_loan_accounts(
            db=db,
            player_id=player_id,
            include_closed=bool(include_closed),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return PlayerLoanAccountsResponse(**payload)


@router.get("/player/{player_id}/history", response_model=PlayerBorrowingHistoryResponse)
def get_borrowing_history_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
) -> PlayerBorrowingHistoryResponse:
    """Return recent borrowing history rows for auditability."""
    try:
        payload = get_player_borrowing_history(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
            limit=limit,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return PlayerBorrowingHistoryResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=ConsumerBorrowingSystemSummaryResponse)
def get_borrowing_system_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> ConsumerBorrowingSystemSummaryResponse:
    """Return composed Step 37 consumer borrowing payload."""
    try:
        payload = build_consumer_borrowing_system_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return ConsumerBorrowingSystemSummaryResponse(**payload)
