"""Step 34 population pressure endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.population_pressure_service import (
    PopulationPressureError,
    PopulationPressureNotFoundError,
    PopulationPressureValidationError,
    build_local_competition_state,
    build_local_opportunity_pressure,
    build_population_pressure_summary,
    build_population_response_summary,
    build_region_heat_summary,
    build_region_population_state,
    update_population_pressure,
)
from app.schemas.population_pressure import (
    LocalCompetitionStateResponse,
    LocalOpportunityPressureResponse,
    PopulationPressureSummaryResponse,
    PopulationResponseSummaryResponse,
    RegionHeatSummaryResponse,
    RegionPopulationStateResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, PopulationPressureNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PopulationPressureValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, PopulationPressureError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected population pressure error.")


@router.get("/player/{player_id}/region-state", response_model=RegionPopulationStateResponse)
def get_region_state_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RegionPopulationStateResponse:
    """Return current region population/pressure state for a player."""
    try:
        payload = build_region_population_state(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return RegionPopulationStateResponse(**payload)


@router.get("/player/{player_id}/opportunity-pressure", response_model=LocalOpportunityPressureResponse)
def get_opportunity_pressure_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> LocalOpportunityPressureResponse:
    """Return local opportunity pressure summary (upside + friction)."""
    try:
        payload = build_local_opportunity_pressure(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return LocalOpportunityPressureResponse(**payload)


@router.get("/player/{player_id}/competition-state", response_model=LocalCompetitionStateResponse)
def get_competition_state_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> LocalCompetitionStateResponse:
    """Return local competition state for the player's region."""
    try:
        payload = build_local_competition_state(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return LocalCompetitionStateResponse(**payload)


@router.get("/player/{player_id}/region-heat", response_model=RegionHeatSummaryResponse)
def get_region_heat_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RegionHeatSummaryResponse:
    """Return region heat and tradeoff summary."""
    try:
        payload = build_region_heat_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return RegionHeatSummaryResponse(**payload)


@router.get("/player/{player_id}/response-summary", response_model=PopulationResponseSummaryResponse)
def get_response_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PopulationResponseSummaryResponse:
    """Return current practical responses and locked future response framing."""
    try:
        payload = build_population_response_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return PopulationResponseSummaryResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=PopulationPressureSummaryResponse)
def get_population_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PopulationPressureSummaryResponse:
    """Return composed Step 34 population pressure payload."""
    try:
        payload = build_population_pressure_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return PopulationPressureSummaryResponse(**payload)


@router.post("/player/{player_id}/refresh", response_model=RegionPopulationStateResponse)
def refresh_population_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RegionPopulationStateResponse:
    """Force-refresh region population pressure for the day."""
    try:
        update_population_pressure(db=db, player_id=player_id, as_of_date=as_of_date)
        payload = build_region_population_state(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return RegionPopulationStateResponse(**payload)
