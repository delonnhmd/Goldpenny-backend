"""Step 30 world memory response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorldPatternItem(BaseModel):
    pattern_key: str
    category: str
    title: str
    short_description: str
    direction: str
    consecutive_days: int
    persistence_score: float
    severity: str
    confidence: str
    affected_systems: list[str] = Field(default_factory=list)
    current_status: str
    recommended_response: str
    future_locked_response: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WorldPatternsResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[WorldPatternItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WorldNarrativeResponse(BaseModel):
    player_id: str
    as_of_date: str
    headline: str
    body: str
    key_active_patterns: list[str] = Field(default_factory=list)
    what_is_persisting: list[str] = Field(default_factory=list)
    what_is_fading: list[str] = Field(default_factory=list)
    what_to_watch_next: list[str] = Field(default_factory=list)
    recommended_short_response: str
    future_locked_long_response: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class LocalPressureSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    local_pressure_level: str
    congestion_label: str
    opportunity_label: str
    cost_pressure_label: str
    business_climate_label: str
    short_summary: str
    practical_response_options: list[str] = Field(default_factory=list)
    future_locked_solution_teasers: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PlayerPatternSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    dominant_player_pattern: str
    supporting_patterns: list[str] = Field(default_factory=list)
    risk_patterns: list[str] = Field(default_factory=list)
    improving_patterns: list[str] = Field(default_factory=list)
    summary: str
    suggested_correction: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class RegionMemorySummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    region_key: str
    region_identity_trend: str
    dominant_region_pressures: list[str] = Field(default_factory=list)
    dominant_region_opportunities: list[str] = Field(default_factory=list)
    recent_change_summary: str
    current_tradeoff_identity: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WorldMemorySnapshotResponse(BaseModel):
    player_id: str
    as_of_date: str | None = None
    region_key: str
    memory_window_start: str | None = None
    memory_window_end: str | None = None
    macro_pressure_score: float
    commute_pressure_score: float
    business_pressure_score: float
    life_pressure_score: float
    opportunity_score: float
    dominant_patterns: list[WorldPatternItem] = Field(default_factory=list)
    narrative_state: dict[str, Any] = Field(default_factory=dict)
    local_pressure_summary: dict[str, Any] = Field(default_factory=dict)
    player_pattern_summary: dict[str, Any] = Field(default_factory=dict)
    region_memory_summary: dict[str, Any] = Field(default_factory=dict)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WorldMemoryHistoryItem(BaseModel):
    pattern_key: str
    category: str
    title: str
    first_seen_on: str | None = None
    last_seen_on: str | None = None
    consecutive_days: int
    persistence_score: float
    severity: str
    direction: str
    status: str
    summary: str
    recommended_response: str | None = None
    future_locked_response: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WorldMemoryHistoryResponse(BaseModel):
    player_id: str
    as_of_date: str
    entries: list[WorldMemoryHistoryItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WorldMemorySummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    snapshot: WorldMemorySnapshotResponse
    patterns: WorldPatternsResponse
    narrative: WorldNarrativeResponse
    local_pressure: LocalPressureSummaryResponse
    player_patterns: PlayerPatternSummaryResponse
    region_memory: RegionMemorySummaryResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)

