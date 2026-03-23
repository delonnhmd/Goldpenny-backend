"""Step 28 strategic planning endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.strategic_planning_service import (
    StrategicPlanningError,
    StrategicPlanningNotFoundError,
    StrategicPlanningValidationError,
    build_business_mode_plan_analysis,
    build_debt_vs_growth_analysis,
    build_housing_tradeoff_analysis,
    build_locked_future_path_preparation,
    build_player_strategy_recommendation,
    build_recovery_vs_push_analysis,
    build_short_horizon_plan_options,
    build_strategic_planning_summary,
)
from app.schemas.strategic_planning import (
    BusinessPlanResponse,
    DebtVsGrowthResponse,
    FuturePreparationResponse,
    HousingTradeoffResponse,
    RecoveryVsPushResponse,
    ShortHorizonPlansResponse,
    StrategicPlanningSummaryResponse,
    StrategyRecommendationResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, StrategicPlanningNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, StrategicPlanningValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, StrategicPlanningError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected strategic planning error.")


@router.get("/player/{player_id}/plans", response_model=ShortHorizonPlansResponse)
def get_short_horizon_plans(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ShortHorizonPlansResponse:
    """Return top 3-4 short-horizon plan options for the player."""
    try:
        payload = build_short_horizon_plan_options(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return ShortHorizonPlansResponse(**payload)


@router.get("/player/{player_id}/housing-tradeoff", response_model=HousingTradeoffResponse)
def get_housing_tradeoff(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HousingTradeoffResponse:
    """Compare stay versus move/rent-closer commute and cost tradeoffs."""
    try:
        payload = build_housing_tradeoff_analysis(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return HousingTradeoffResponse(**payload)


@router.get("/player/{player_id}/debt-vs-growth", response_model=DebtVsGrowthResponse)
def get_debt_vs_growth(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DebtVsGrowthResponse:
    """Compare defensive debt choices versus growth spending choices."""
    try:
        payload = build_debt_vs_growth_analysis(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return DebtVsGrowthResponse(**payload)


@router.get("/player/{player_id}/business-plan", response_model=BusinessPlanResponse)
def get_business_plan(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BusinessPlanResponse:
    """Return short-horizon business mode advice for Fruit Shop and Food Truck."""
    try:
        payload = build_business_mode_plan_analysis(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return BusinessPlanResponse(**payload)


@router.get("/player/{player_id}/recovery-vs-push", response_model=RecoveryVsPushResponse)
def get_recovery_vs_push(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RecoveryVsPushResponse:
    """Compare push-harder and recover-first short-horizon strategies."""
    try:
        payload = build_recovery_vs_push_analysis(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return RecoveryVsPushResponse(**payload)


@router.get("/player/{player_id}/recommendation", response_model=StrategyRecommendationResponse)
def get_strategy_recommendation(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StrategyRecommendationResponse:
    """Return one composed recommendation with risk/opportunity framing."""
    try:
        payload = build_player_strategy_recommendation(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return StrategyRecommendationResponse(**payload)


@router.get("/player/{player_id}/future-preparation", response_model=FuturePreparationResponse)
def get_future_preparation(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> FuturePreparationResponse:
    """Return future locked preparation signals (non-actionable)."""
    try:
        payload = build_locked_future_path_preparation(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return FuturePreparationResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=StrategicPlanningSummaryResponse)
def get_strategic_planning_summary(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StrategicPlanningSummaryResponse:
    """Return composed Step 28 strategic planning payload for frontend hydration."""
    try:
        payload = build_strategic_planning_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return StrategicPlanningSummaryResponse(**payload)
