"""Step 42: Forecasting, Planning Intelligence, and Forward Projection Layer — API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.forecasting_planning_service import (
    ForecastingError,
    ForecastingNotFoundError,
    ForecastingValidationError,
    build_and_persist_forecast,
    build_decision_guidance,
    build_forecast_summary,
    build_risk_projection_state,
    build_scenario_comparison,
    build_short_term_forecast,
    simulate_player_path,
)
from app.schemas.forecasting import (
    DecisionGuidanceResponse,
    ForecastSnapshotResponse,
    ForecastSummaryResponse,
    RiskProjectionResponse,
    ScenarioComparisonRequest,
    ScenarioComparisonResponse,
    ShortTermForecastResponse,
    SimulationRequest,
    SimulationResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ForecastingNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ForecastingValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ForecastingError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected forecasting error.",
    )


# ---------------------------------------------------------------------------
# 1. Short-term cash-flow forecast
# ---------------------------------------------------------------------------


@router.get(
    "/player/{player_id}/short-term",
    response_model=ShortTermForecastResponse,
    summary="Build short-term deterministic cash-flow forecast (7–14 days)",
)
def get_short_term_forecast(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    horizon_days: int = Query(default=14, ge=1, le=60, description="Forecast horizon in days"),
    db: Session = Depends(get_db),
) -> ShortTermForecastResponse:
    try:
        result = build_short_term_forecast(db, player_id, day=day, horizon_days=horizon_days)
    except Exception as exc:
        _raise_http(exc)
    return ShortTermForecastResponse(**result)


# ---------------------------------------------------------------------------
# 2. Risk projection / danger radar
# ---------------------------------------------------------------------------


@router.get(
    "/player/{player_id}/risk",
    response_model=RiskProjectionResponse,
    summary="Get danger-radar: near-term risk, delinquency risk, cash gap, debt spiral",
)
def get_risk_projection(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    horizon_days: int = Query(default=14, ge=1, le=60, description="Forecast horizon in days"),
    db: Session = Depends(get_db),
) -> RiskProjectionResponse:
    try:
        result = build_risk_projection_state(db, player_id, day=day, horizon_days=horizon_days)
    except Exception as exc:
        _raise_http(exc)
    return RiskProjectionResponse(**result)


# ---------------------------------------------------------------------------
# 3. Forecast summary
# ---------------------------------------------------------------------------


@router.get(
    "/player/{player_id}/summary",
    response_model=ForecastSummaryResponse,
    summary="Get overall forecast summary: outlook, next risk event, best/worst actions",
)
def get_forecast_summary(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    horizon_days: int = Query(default=14, ge=1, le=60, description="Forecast horizon in days"),
    db: Session = Depends(get_db),
) -> ForecastSummaryResponse:
    try:
        result = build_forecast_summary(db, player_id, day=day, horizon_days=horizon_days)
    except Exception as exc:
        _raise_http(exc)
    return ForecastSummaryResponse(**result)


# ---------------------------------------------------------------------------
# 4. Simulate a hypothetical action
# ---------------------------------------------------------------------------


@router.post(
    "/player/{player_id}/simulate",
    response_model=SimulationResponse,
    summary="Simulate a hypothetical action (borrow, invest, expand, skip payment) vs. baseline",
)
def post_simulate_action(
    player_id: str,
    body: SimulationRequest,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> SimulationResponse:
    try:
        result = simulate_player_path(
            db, player_id, body.action, day=day, horizon_days=body.horizon_days
        )
    except Exception as exc:
        _raise_http(exc)
    return SimulationResponse(**result)


# ---------------------------------------------------------------------------
# 5. Scenario comparison
# ---------------------------------------------------------------------------


@router.post(
    "/player/{player_id}/compare",
    response_model=ScenarioComparisonResponse,
    summary="Compare 2–5 action scenarios side-by-side",
)
def post_scenario_comparison(
    player_id: str,
    body: ScenarioComparisonRequest,
    day: int | None = Query(default=None, description="Game day number"),
    db: Session = Depends(get_db),
) -> ScenarioComparisonResponse:
    try:
        result = build_scenario_comparison(
            db, player_id, day=day, horizon_days=body.horizon_days, actions=body.actions
        )
    except Exception as exc:
        _raise_http(exc)
    return ScenarioComparisonResponse(**result)


# ---------------------------------------------------------------------------
# 6. Decision guidance
# ---------------------------------------------------------------------------


@router.get(
    "/player/{player_id}/guidance",
    response_model=DecisionGuidanceResponse,
    summary="Get smart decision guidance: what should I do right now?",
)
def get_decision_guidance(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    horizon_days: int = Query(default=14, ge=1, le=60, description="Forecast horizon in days"),
    db: Session = Depends(get_db),
) -> DecisionGuidanceResponse:
    try:
        result = build_decision_guidance(db, player_id, day=day, horizon_days=horizon_days)
    except Exception as exc:
        _raise_http(exc)
    return DecisionGuidanceResponse(**result)


# ---------------------------------------------------------------------------
# 7. Build and persist full snapshot (POST — writes to DB)
# ---------------------------------------------------------------------------


@router.post(
    "/player/{player_id}/snapshot",
    response_model=ForecastSnapshotResponse,
    summary="Build, persist, and return full forecast snapshot for the player",
)
def post_build_snapshot(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    horizon_days: int = Query(default=14, ge=1, le=60, description="Forecast horizon in days"),
    db: Session = Depends(get_db),
) -> ForecastSnapshotResponse:
    try:
        result = build_and_persist_forecast(db, player_id, day=day, horizon_days=horizon_days)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return ForecastSnapshotResponse(**result)
