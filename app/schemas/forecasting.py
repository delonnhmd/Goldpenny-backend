"""Step 42: Forecasting, Planning Intelligence, and Forward Projection Layer — Pydantic schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared sub-objects
# ---------------------------------------------------------------------------


class ProjectedCashEntry(BaseModel):
    day: int
    cash_xgp: float
    daily_net_xgp: float


class ProjectedObligationHit(BaseModel):
    obligation_key: str
    family: str
    type: str
    amount_xgp: float
    due_on_day: int
    days_away: int
    status: str


class ProjectedIncomeEvent(BaseModel):
    income_key: str
    type: str
    amount_xgp: float
    due_on_day: int
    days_away: int
    status: str


# ---------------------------------------------------------------------------
# 1. ShortTermForecastResponse
# ---------------------------------------------------------------------------


class ShortTermForecastResponse(BaseModel):
    player_id: str
    day: int
    forecast_horizon_days: int
    projected_cash_curve: list[ProjectedCashEntry]
    projected_obligation_hits: list[ProjectedObligationHit]
    projected_income_events: list[ProjectedIncomeEvent]
    projected_liquidity_low_point: float
    projected_liquidity_low_day: int
    projected_delinquency_risk_day: Optional[int] = None
    projected_stress_trend: str
    projected_debt_trend: str
    confidence_level: str
    short_summary: str
    debug_meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 2. RiskProjectionResponse
# ---------------------------------------------------------------------------


class RiskProjectionResponse(BaseModel):
    player_id: str
    day: int
    near_term_risk_label: str
    delinquency_risk_label: str
    cash_gap_risk_label: str
    debt_spiral_risk_projection: str
    timing_collision_risk: str
    composite_risk_score: float
    projected_liquidity_low_point_xgp: float
    projected_delinquency_risk_day: Optional[int] = None
    short_summary: str
    debug_meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 3. ForecastSummaryResponse
# ---------------------------------------------------------------------------


class ForecastSummaryResponse(BaseModel):
    player_id: str
    day: int
    overall_outlook_label: str
    next_major_risk_event: str
    days_until_next_problem: Optional[int] = None
    best_stabilizing_action: str
    worst_action_to_take: str
    projected_liquidity_low_point_xgp: float
    confidence_level: str
    short_summary: str
    debug_meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 4. SimulationRequest
# ---------------------------------------------------------------------------


class SimulationRequest(BaseModel):
    action: str = Field(
        ...,
        description=(
            "Hypothetical action to simulate. One of: do_nothing, borrow_small, "
            "borrow_large, invest_small, invest_large, expand_business, skip_payment"
        ),
    )
    horizon_days: int = Field(
        default=14,
        ge=1,
        le=60,
        description="Forecast horizon in game days",
    )


# ---------------------------------------------------------------------------
# 5. SimulationResponse
# ---------------------------------------------------------------------------


class SimulationBaseline(BaseModel):
    projected_liquidity_low_point: float
    liquidity_low_day: int
    delinquency_risk_day: Optional[int] = None
    end_cash_xgp: float
    outcome_label: str


class SimulationSimulated(BaseModel):
    projected_cash_curve: list[ProjectedCashEntry]
    projected_liquidity_low_point: float
    liquidity_low_day: int
    delinquency_risk_day: Optional[int] = None
    end_cash_xgp: float
    outcome_label: str
    risk_label: str
    stability_label: str


class SimulationNetEffect(BaseModel):
    cash_change_end_xgp: float
    delinquency_risk_change: str
    stability_change: str


class SimulationResponse(BaseModel):
    player_id: str
    day: int
    action: str
    action_note: str
    baseline: SimulationBaseline
    simulated: SimulationSimulated
    net_effect: SimulationNetEffect
    projected_obligations: list[ProjectedObligationHit]
    projected_income: list[ProjectedIncomeEvent]
    debug_meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 6. ScenarioComparisonRequest
# ---------------------------------------------------------------------------


class ScenarioComparisonRequest(BaseModel):
    actions: list[str] = Field(
        default=["do_nothing", "borrow_small", "invest_small"],
        description="List of 2–5 action keys to compare side-by-side",
        min_length=2,
        max_length=5,
    )
    horizon_days: int = Field(default=14, ge=1, le=60)


# ---------------------------------------------------------------------------
# 7. ScenarioComparisonResponse
# ---------------------------------------------------------------------------


class ScenarioOption(BaseModel):
    option_key: str
    action_note: str
    short_term_outcome_label: str
    medium_term_outcome_label: str
    risk_label: str
    stability_label: str
    net_effect_summary: str
    projected_end_cash_xgp: float
    liquidity_low_point_xgp: float
    delinquency_risk_day: Optional[int] = None


class ScenarioComparisonResponse(BaseModel):
    player_id: str
    day: int
    horizon_days: int
    options: list[ScenarioOption]
    recommended_option_key: str
    recommendation_reason: str
    debug_meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 8. DecisionGuidanceResponse
# ---------------------------------------------------------------------------


class DecisionGuidanceResponse(BaseModel):
    player_id: str
    day: int
    guidance_label: str
    top_recommendation: str
    avoid_action: str
    confidence_label: str
    reasoning_summary: str
    debug_meta: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 9. ForecastSnapshotResponse (persisted summary)
# ---------------------------------------------------------------------------


class ForecastSnapshotResponse(BaseModel):
    player_id: str
    snapshot_id: str
    day: int
    overall_outlook_label: str
    composite_risk_score: float
    projected_liquidity_low_point_xgp: float
    projected_delinquency_risk_day: Optional[int] = None
    days_until_next_problem: Optional[int] = None
    near_term_risk_label: str
    delinquency_risk_label: str
    cash_gap_risk_label: str
    debt_spiral_risk_label: str
    guidance_label: str
    top_recommendation: str
    avoid_action: str
    confidence_level: str
    debug_meta: Optional[dict[str, Any]] = None
