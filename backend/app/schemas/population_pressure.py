"""Step 34 population pressure response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RegionPopulationStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    heat_level: str
    active_population_score: float
    opportunity_density_score: float
    congestion_score: float
    housing_pressure_score: float
    business_competition_score: float
    consumer_flow_score: float
    recent_growth_direction: str
    last_updated_on: int
    last_updated_date: str | None = None
    memory_window_start: str | None = None
    memory_window_end: str | None = None
    short_summary: str | None = None
    practical_current_responses: list[str] = Field(default_factory=list)
    future_locked_response_options: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class LocalOpportunityPressureResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    opportunity_density_label: str
    job_access_label: str
    business_demand_label: str
    local_advantage_summary: str
    local_friction_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class LocalCompetitionStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    competition_level: str
    business_competition_label: str
    demand_share_pressure: float
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class RegionHeatSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    heat_level: str
    dominant_upside: str
    dominant_friction: str
    housing_tradeoff_summary: str
    business_climate_summary: str
    commute_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PopulationResponseSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    current_pressure_summary: str
    practical_current_responses: list[str] = Field(default_factory=list)
    short_recommendation: str
    future_locked_response_options: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PopulationPressureSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_state: RegionPopulationStateResponse
    opportunity_pressure: LocalOpportunityPressureResponse
    competition_state: LocalCompetitionStateResponse
    region_heat: RegionHeatSummaryResponse
    response_summary: PopulationResponseSummaryResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)
