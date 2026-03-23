"""Step 39 wealth progression response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WealthProfileResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    cash_reserve_xgp: float
    savings_reserve_xgp: float
    investable_surplus_xgp: float
    debt_drag_xgp: float
    net_worth_xgp: float
    liquid_asset_value_xgp: float
    market_asset_value_xgp: float
    business_equity_xgp: float
    total_asset_value_xgp: float
    total_debt_xgp: float
    wealth_momentum_score: float
    stability_before_growth_score: float
    buffer_days: float
    wealth_phase_label: str
    asset_growth_trend: str
    safe_to_save_label: str
    safe_to_invest_label: str
    experience_phase: str
    days_in_phase: int
    softening_active: bool
    top_growth_driver: str
    top_drag_driver: str
    false_growth_detected: bool
    false_growth_warnings: list[str] = Field(default_factory=list)
    planning_insights: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class SavingsCapacityStateResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    safe_to_save_label: str
    safe_to_invest_label: str
    recommended_buffer_days: float
    current_buffer_days: float
    daily_obligations_xgp: float
    investable_surplus_xgp: float
    excess_cash_label: str
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class AssetProgressionStateResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    liquid_asset_value_xgp: float
    market_asset_value_xgp: float
    business_equity_xgp: float
    total_asset_value_xgp: float
    total_debt_xgp: float
    asset_growth_trend: str
    asset_quality_label: str
    diversification_label: str
    asset_to_debt_ratio: float
    strong_business_trend: bool
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WealthActionEvaluationItem(BaseModel):
    action_key: str
    evaluation_label: str
    reasoning: str


class WealthActionsEvaluationResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    evaluations: list[WealthActionEvaluationItem] = Field(default_factory=list)
    buffer_days: float
    delinquency_stage: str
    spiral_label: str
    investable_surplus_xgp: float
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class NetWorthSummaryResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    net_worth_xgp: float
    net_worth_direction: str
    net_worth_delta_xgp: float
    wealth_phase_label: str
    growth_quality_label: str
    false_growth_detected: bool
    false_growth_warnings: list[str] = Field(default_factory=list)
    top_growth_driver: str
    top_drag_driver: str
    debt_drag_xgp: float
    debt_drag_ratio: float
    total_asset_value_xgp: float
    practical_current_actions: list[str] = Field(default_factory=list)
    short_recommendation: str
    planning_insights: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WealthMomentumSummaryResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    wealth_phase_label: str
    wealth_momentum_score: float
    momentum_direction: str
    stability_before_growth_score: float
    net_worth_xgp: float
    buffer_days: float
    safe_to_save_label: str
    safe_to_invest_label: str
    experience_phase: str
    days_in_phase: int
    softening_active: bool
    softening_modifiers: dict[str, Any] = Field(default_factory=dict)
    false_growth_detected: bool
    false_growth_warnings: list[str] = Field(default_factory=list)
    asset_growth_trend: str
    market_asset_value_xgp: float
    business_equity_xgp: float
    liquid_asset_value_xgp: float
    debt_drag_xgp: float
    top_growth_driver: str
    top_drag_driver: str
    phase_advisory: list[str] = Field(default_factory=list)
    planning_insights: list[str] = Field(default_factory=list)
    savings_capacity_summary: str
    asset_quality_label: str
    diversification_label: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)
