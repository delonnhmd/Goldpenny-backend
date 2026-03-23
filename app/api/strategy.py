"""Step 22 strategy and weekly summary endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.player_strategy_service import (
    PlayerStrategyError,
    PlayerStrategyNotFoundError,
    PlayerStrategyValidationError,
    classify_player_strategy,
)
from app.engine.weekly_strategy_service import (
    WeeklyStrategyError,
    WeeklyStrategyNotFoundError,
    WeeklyStrategyValidationError,
    build_player_weekly_strategy_summary,
)

router = APIRouter()


class PlayerWeeklyStrategySummary(BaseModel):
    player_id: str
    week_start: str
    week_end: str
    dominant_income_source: str
    largest_cost_pressure: str
    distress_trend: str
    stress_trend: str
    health_trend: str
    career_trend: str
    strategy_classification: str
    suggested_next_moves: list[str]
    debug_meta: dict


class PlayerStrategyClassificationResponse(BaseModel):
    player_id: str
    as_of_date: str
    strategy_classification: str
    classification_drivers: dict
    debug_meta: dict


def _raise_strategy_http_error(exc: Exception) -> None:
    if isinstance(exc, (PlayerStrategyNotFoundError, WeeklyStrategyNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (PlayerStrategyValidationError, WeeklyStrategyValidationError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, (PlayerStrategyError, WeeklyStrategyError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected strategy service error.")


@router.get("/player/{player_id}/weekly", response_model=PlayerWeeklyStrategySummary)
def get_player_weekly_strategy_summary(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Return a deterministic weekly strategy summary for one player."""
    try:
        return build_player_weekly_strategy_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_strategy_http_error(exc)


@router.get("/player/{player_id}/classification", response_model=PlayerStrategyClassificationResponse)
def get_player_strategy_classification(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    lookback_days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
) -> dict:
    """Return current strategy classification derived from recent real gameplay."""
    try:
        return classify_player_strategy(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
        )
    except Exception as exc:
        _raise_strategy_http_error(exc)
