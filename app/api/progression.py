"""Step 26 progression endpoints: daily goals, weekly missions, streaks, summary."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.progression_service import (
    ProgressionError,
    ProgressionNotFoundError,
    ProgressionValidationError,
    build_progression_summary,
    evaluate_action_progress,
    get_player_daily_goals,
    get_player_streaks,
    get_player_weekly_missions,
)
from app.schemas.progression import (
    DailyGoalsResponse,
    ProgressionSummaryResponse,
    StreaksResponse,
    WeeklyMissionsResponse,
)

router = APIRouter()


def _raise_progression_http_error(exc: Exception) -> None:
    if isinstance(exc, ProgressionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ProgressionValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ProgressionError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected progression service error.")


@router.get("/player/{player_id}/daily-goals", response_model=DailyGoalsResponse)
def get_daily_goals_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DailyGoalsResponse:
    """Return deterministic daily goals relevant to the current player state."""
    try:
        payload = get_player_daily_goals(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_progression_http_error(exc)
    return DailyGoalsResponse(**payload)


@router.get("/player/{player_id}/weekly-missions", response_model=WeeklyMissionsResponse)
def get_weekly_missions_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WeeklyMissionsResponse:
    """Return deterministic weekly missions derived from player strategy and pressure."""
    try:
        payload = get_player_weekly_missions(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_progression_http_error(exc)
    return WeeklyMissionsResponse(**payload)


@router.get("/player/{player_id}/streaks", response_model=StreaksResponse)
def get_streaks_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StreaksResponse:
    """Return current streak counters and reset risk signals."""
    try:
        payload = get_player_streaks(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_progression_http_error(exc)
    return StreaksResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=ProgressionSummaryResponse)
def get_progression_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ProgressionSummaryResponse:
    """Return composed progression payload for frontend dashboard usage."""
    try:
        payload = build_progression_summary(db=db, player_id=player_id, as_of_date=as_of_date, persist=True)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_progression_http_error(exc)
    return ProgressionSummaryResponse(**payload)


@router.post("/player/{player_id}/refresh", response_model=ProgressionSummaryResponse)
def refresh_progression_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ProgressionSummaryResponse:
    """Force progression re-evaluation after one or more player actions."""
    try:
        payload = evaluate_action_progress(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_progression_http_error(exc)
    return ProgressionSummaryResponse(**payload)
