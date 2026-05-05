"""Step 27 economy presentation response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.supply_chain import SupplyChainStoryResponse, SupplyChainSummaryResponse


class MarketOverviewResponse(BaseModel):
    player_id: str
    as_of_date: str
    current_market_mood: str
    headline_drivers: list[str] = Field(default_factory=list)
    top_winners: list[str] = Field(default_factory=list)
    top_losers: list[str] = Field(default_factory=list)
    macro_trend_labels: dict[str, str] = Field(default_factory=dict)
    basket_pressure_labels: dict[str, str] = Field(default_factory=dict)
    short_explainer: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PriceTrendItem(BaseModel):
    basket_key: str
    current_level: float
    short_term_trend: str
    volatility_label: str
    primary_driver: str
    player_impact_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PriceTrendsResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[PriceTrendItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BusinessMarginItem(BaseModel):
    business_key: str
    margin_outlook: str
    demand_outlook: str
    cost_pressure: str
    risk_factors: list[str] = Field(default_factory=list)
    opportunity_factors: list[str] = Field(default_factory=list)
    short_explainer: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class BusinessMarginsResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[BusinessMarginItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommutePressureResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    commute_pressure_level: str
    estimated_commute_burden: str
    stress_impact_label: str
    time_impact_label: str
    housing_tradeoff_summary: str
    suggested_current_responses: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PlayerEconomyExplainerResponse(BaseModel):
    player_id: str
    as_of_date: str
    why_costs_changed: str
    why_business_changed: str
    why_commute_changed: str
    why_stress_changed: str
    this_week_focus: str
    suggested_defensive_move: str
    suggested_growth_move: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DailyEconomyBriefResponse(BaseModel):
    as_of_date: str
    day: int
    headline: str
    summary_lines: list[str] = Field(default_factory=list)
    top_bottlenecks: list[str] = Field(default_factory=list)
    top_basket_movers: list[str] = Field(default_factory=list)
    top_job_changes: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DailySettlementDigestResponse(BaseModel):
    day_number: int
    income_xgp: float
    expenses_xgp: float
    net_change_xgp: float
    cash_after_xgp: float
    stress_change: int
    health_change: int
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class EconomyPresentationSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    current_day: int
    market_overview: MarketOverviewResponse
    price_trends: PriceTrendsResponse
    business_margins: BusinessMarginsResponse
    commute_pressure: CommutePressureResponse
    explainer: PlayerEconomyExplainerResponse
    daily_brief: DailyEconomyBriefResponse
    supply_chain_summary: SupplyChainSummaryResponse
    supply_chain_story: SupplyChainStoryResponse
    settlement_summary: DailySettlementDigestResponse | None = None
    player_warnings: list[str] = Field(default_factory=list)
    player_opportunities: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)
