"""Step 35 personal shock endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.personal_shock_service import (
    PersonalShockError,
    PersonalShockNotFoundError,
    PersonalShockValidationError,
    build_personal_shock_profile,
    build_personal_shock_summary,
    build_personal_shock_system_summary,
    build_player_resilience_summary,
    build_shock_risk_state,
    get_player_recovery_state,
    get_recent_personal_life_event,
)
from app.schemas.personal_shocks import (
    PersonalLifeEventResponse,
    PersonalRiskStateResponse,
    PersonalShockProfileResponse,
    PersonalShockSummaryResponse,
    PersonalShockSystemSummaryResponse,
    PlayerResilienceSummaryResponse,
    RecoveryStateResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, PersonalShockNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PersonalShockValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, PersonalShockError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected personal shock error.")


@router.get("/player/{player_id}/shock-profile", response_model=PersonalShockProfileResponse)
def get_shock_profile_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PersonalShockProfileResponse:
    """Return rolling personal shock profile."""
    try:
        payload = build_personal_shock_profile(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PersonalShockProfileResponse(**payload)


@router.get("/player/{player_id}/risk-state", response_model=PersonalRiskStateResponse)
def get_risk_state_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PersonalRiskStateResponse:
    """Return event chance + severity risk state."""
    try:
        payload = build_shock_risk_state(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PersonalRiskStateResponse(**payload)


@router.get("/player/{player_id}/recent-event", response_model=PersonalLifeEventResponse)
def get_recent_event_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PersonalLifeEventResponse:
    """Return most recent personal life event payload."""
    try:
        payload = get_recent_personal_life_event(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PersonalLifeEventResponse(**payload)


@router.get("/player/{player_id}/recovery-state", response_model=RecoveryStateResponse)
def get_recovery_state_route(
    player_id: str,
    db: Session = Depends(get_db),
) -> RecoveryStateResponse:
    """Return active recovery modifiers."""
    try:
        payload = get_player_recovery_state(db=db, player_id=player_id)
    except Exception as exc:
        _raise_http_error(exc)
    return RecoveryStateResponse(**payload)


@router.get("/player/{player_id}/resilience-summary", response_model=PlayerResilienceSummaryResponse)
def get_resilience_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PlayerResilienceSummaryResponse:
    """Return resilience/fragility summary labels."""
    try:
        payload = build_player_resilience_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PlayerResilienceSummaryResponse(**payload)


@router.get("/player/{player_id}/shock-summary", response_model=PersonalShockSummaryResponse)
def get_shock_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PersonalShockSummaryResponse:
    """Return compact player-facing personal shock explanation."""
    try:
        payload = build_personal_shock_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PersonalShockSummaryResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=PersonalShockSystemSummaryResponse)
def get_shock_system_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> PersonalShockSystemSummaryResponse:
    """Return full composed Step 35 personal-shock payload."""
    try:
        payload = build_personal_shock_system_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return PersonalShockSystemSummaryResponse(**payload)

