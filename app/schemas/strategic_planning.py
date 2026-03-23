"""Step 28 strategic planning response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanOptionItem(BaseModel):
    plan_key: str
    title: str
    short_description: str
    likely_upside: str
    likely_downside: str
    primary_tradeoff: str
    suggested_duration_days: int
    confidence_label: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class ShortHorizonPlansResponse(BaseModel):
    player_id: str
    as_of_date: str
    options: list[PlanOptionItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class HousingTradeoffResponse(BaseModel):
    player_id: str
    as_of_date: str
    current_region: str
    current_commute_burden: str
    closer_housing_cost_pressure: str
    expected_stress_delta_label: str
    expected_time_delta_label: str
    opportunity_access_label: str
    short_recommendation: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DebtVsGrowthItem(BaseModel):
    option_key: str
    option_label: str
    defensive_score: float
    growth_score: float
    liquidity_risk: str
    distress_impact_label: str
    recommendation_note: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DebtVsGrowthResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[DebtVsGrowthItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BusinessPlanItem(BaseModel):
    business_key: str
    business_present: bool
    current_mode: str
    demand_outlook: str
    input_cost_outlook: str
    margin_stability: str
    recommendation_over_horizon: str
    key_watch_item: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BusinessPlanResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[BusinessPlanItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class RecoveryVsPushResponse(BaseModel):
    player_id: str
    as_of_date: str
    current_pressure_level: str
    push_case: str
    recovery_case: str
    likely_near_term_cost: str
    likely_near_term_benefit: str
    recommendation_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class StrategyRecommendationResponse(BaseModel):
    player_id: str
    as_of_date: str
    recommended_plan_key: str
    recommended_plan_title: str
    biggest_risk: str
    biggest_opportunity: str
    defensive_move: str
    growth_move: str
    avoid_warning: str
    recommendation_reason: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class FuturePreparationItem(BaseModel):
    path_key: str
    title: str
    why_it_matters_now: str
    current_preparation_signal: str
    unlock_status: str
    category: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class FuturePreparationResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[FuturePreparationItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class StrategicPlanningSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    plans: ShortHorizonPlansResponse
    housing_tradeoff: HousingTradeoffResponse
    debt_vs_growth: DebtVsGrowthResponse
    business_plan: BusinessPlanResponse
    recovery_vs_push: RecoveryVsPushResponse
    recommendation: StrategyRecommendationResponse
    future_preparation: FuturePreparationResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)
