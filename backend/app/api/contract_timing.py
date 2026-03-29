"""Step 41 contract timing API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.contract_timing_service import (
    ContractTimingError,
    ContractTimingNotFoundError,
    ContractTimingValidationError,
    apply_contract_cycle_progression,
    build_cash_timing_pressure_state,
    build_contract_pressure_summary,
    build_due_soon_summary,
    build_player_contract_schedule,
    build_upcoming_obligation_window,
    generate_recurring_contracts,
)
from app.schemas.contract_timing import (
    CashTimingPressureStateResponse,
    ContractPressureSummaryResponse,
    DueSoonSummaryResponse,
    PlayerContractScheduleResponse,
    UpcomingObligationWindowResponse,
)

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ContractTimingNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ContractTimingValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ContractTimingError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected contract timing error.",
    )


def _resolve_day_arg(day: int | None) -> int | None:
    return day


@router.get(
    "/player/{player_id}/schedule",
    response_model=PlayerContractScheduleResponse,
    summary="Build and persist player contract schedule",
)
def get_contract_schedule(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> PlayerContractScheduleResponse:
    try:
        result = build_player_contract_schedule(db, player_id, day=day)
        db.commit()
    except (ContractTimingError, Exception) as exc:
        db.rollback()
        _raise_http(exc)
    return PlayerContractScheduleResponse(**result)


@router.get(
    "/player/{player_id}/upcoming-window",
    response_model=UpcomingObligationWindowResponse,
    summary="Get upcoming obligation window (1d / 3d / 7d)",
)
def get_upcoming_window(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> UpcomingObligationWindowResponse:
    try:
        result = build_upcoming_obligation_window(db, player_id, day=day)
    except (ContractTimingError, Exception) as exc:
        _raise_http(exc)
    return UpcomingObligationWindowResponse(**result)


@router.get(
    "/player/{player_id}/cash-timing-pressure",
    response_model=CashTimingPressureStateResponse,
    summary="Get cash flow timing pressure state",
)
def get_cash_timing_pressure(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> CashTimingPressureStateResponse:
    try:
        result = build_cash_timing_pressure_state(db, player_id, day=day)
    except (ContractTimingError, Exception) as exc:
        _raise_http(exc)
    return CashTimingPressureStateResponse(**result)


@router.get(
    "/player/{player_id}/due-soon-summary",
    response_model=DueSoonSummaryResponse,
    summary="Get concise due-soon summary for the next 7 days",
)
def get_due_soon_summary(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> DueSoonSummaryResponse:
    try:
        result = build_due_soon_summary(db, player_id, day=day)
    except (ContractTimingError, Exception) as exc:
        _raise_http(exc)
    return DueSoonSummaryResponse(**result)


@router.get(
    "/player/{player_id}/pressure-summary",
    response_model=ContractPressureSummaryResponse,
    summary="Full contract pressure summary — all timing signals",
)
def get_pressure_summary(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> ContractPressureSummaryResponse:
    try:
        result = build_contract_pressure_summary(db, player_id, day=day)
    except (ContractTimingError, Exception) as exc:
        _raise_http(exc)
    return ContractPressureSummaryResponse(**result)


@router.post(
    "/player/{player_id}/generate-contracts",
    summary="Generate or refresh recurring contract events",
)
def post_generate_contracts(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = generate_recurring_contracts(db, player_id, day=day)
        db.commit()
    except (ContractTimingError, Exception) as exc:
        db.rollback()
        _raise_http(exc)
    return result


@router.post(
    "/player/{player_id}/advance-events",
    summary="Advance contract event statuses for the current day",
)
def post_advance_events(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = apply_contract_cycle_progression(db, player_id, day=day)
        db.commit()
    except (ContractTimingError, Exception) as exc:
        db.rollback()
        _raise_http(exc)
    return result
