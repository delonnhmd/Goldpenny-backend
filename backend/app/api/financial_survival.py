"""Step 36 financial survival endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.financial_survival_service import (
    FinancialSurvivalError,
    FinancialSurvivalNotFoundError,
    FinancialSurvivalValidationError,
    build_credit_impact_summary,
    build_delinquency_state,
    build_financial_survival_summary,
    build_financial_survival_system_summary,
    build_payment_risk_state,
    build_player_obligation_profile,
    get_player_payment_history,
)
from app.schemas.financial_survival import (
    CreditImpactSummaryResponse,
    DelinquencyStateResponse,
    FinancialSurvivalPaymentHistoryResponse,
    FinancialSurvivalSummaryResponse,
    FinancialSurvivalSystemSummaryResponse,
    PaymentRiskStateResponse,
    PlayerObligationProfileResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, FinancialSurvivalNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, FinancialSurvivalValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, FinancialSurvivalError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected financial survival error.")


@router.get("/player/{player_id}/obligation-profile", response_model=PlayerObligationProfileResponse)
def get_obligation_profile_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PlayerObligationProfileResponse:
    """Return current required-obligation profile and liquidity burden."""
    try:
        payload = build_player_obligation_profile(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PlayerObligationProfileResponse(**payload)


@router.get("/player/{player_id}/payment-risk", response_model=PaymentRiskStateResponse)
def get_payment_risk_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PaymentRiskStateResponse:
    """Return payment feasibility and delinquency exposure for the player/day."""
    try:
        payload = build_payment_risk_state(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PaymentRiskStateResponse(**payload)


@router.get("/player/{player_id}/delinquency-state", response_model=DelinquencyStateResponse)
def get_delinquency_state_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> DelinquencyStateResponse:
    """Return rolling delinquency counters and current stage."""
    try:
        payload = build_delinquency_state(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return DelinquencyStateResponse(**payload)


@router.get("/player/{player_id}/credit-impact", response_model=CreditImpactSummaryResponse)
def get_credit_impact_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> CreditImpactSummaryResponse:
    """Return the latest credit impact summary from payment outcomes."""
    try:
        history = get_player_payment_history(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
            limit=1,
        )
        latest = (history.get("entries") or [{}])[0] if history.get("entries") else {}
        payload = build_credit_impact_summary(
            credit_score_before=int(latest.get("credit_score_before", 650)),
            credit_score_after=int(latest.get("credit_score_after", 650)),
            credit_delta=int(latest.get("credit_score_delta", 0)),
            payment_outcome=str(latest.get("payment_outcome", "paid_full")),
            delinquency_stage_after=str(latest.get("delinquency_stage_after", "current")),
        )
    except Exception as exc:
        _raise_http_error(exc)
    return CreditImpactSummaryResponse(**payload)


@router.get("/player/{player_id}/survival-summary", response_model=FinancialSurvivalSummaryResponse)
def get_survival_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> FinancialSurvivalSummaryResponse:
    """Return compact player-facing financial survival status and actions."""
    try:
        payload = build_financial_survival_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return FinancialSurvivalSummaryResponse(**payload)


@router.get("/player/{player_id}/payment-history", response_model=FinancialSurvivalPaymentHistoryResponse)
def get_payment_history_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
) -> FinancialSurvivalPaymentHistoryResponse:
    """Return recent payment history with trailing diagnostics."""
    try:
        payload = get_player_payment_history(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
            limit=limit,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return FinancialSurvivalPaymentHistoryResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=FinancialSurvivalSystemSummaryResponse)
def get_financial_survival_system_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> FinancialSurvivalSystemSummaryResponse:
    """Return composed Step 36 financial survival payload."""
    try:
        payload = build_financial_survival_system_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return FinancialSurvivalSystemSummaryResponse(**payload)

