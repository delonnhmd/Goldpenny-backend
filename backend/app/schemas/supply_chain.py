"""Pydantic response models for supply-chain daily compute snapshots.

Step 13 models: SupplyChainNodeSnapshot, BasketSupplySnapshot,
                BottleneckSnapshot, JobPressureSnapshot,
                SupplyChainDailyResponse

Step 43 models: SupplyChainNodeStateResponse, SupplyChainBottleneckResponse,
                BasketSupplyMultiplierResponse, JobPressureResponse,
                SupplyChainSummaryResponse, SupplyChainStoryResponse
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


# ── Step 13 models ────────────────────────────────────────────────────────────


class SupplyChainNodeSnapshot(BaseModel):
    node_key: str
    display_name: str
    availability: float
    severity: float
    drivers: dict[str, float] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class BasketSupplySnapshot(BaseModel):
    basket_key: str
    supply_multiplier: float
    dominant_nodes: list[str] = Field(default_factory=list)


class BottleneckSnapshot(BaseModel):
    node_key: str
    display_name: str
    availability: float
    severity: float


class JobPressureSnapshot(BaseModel):
    job_key: str
    pressure: float
    direction: str


class SupplyChainDailyResponse(BaseModel):
    as_of_date: date
    macro_state_id: int | None
    node_snapshots: list[SupplyChainNodeSnapshot] = Field(default_factory=list)
    basket_supply: list[BasketSupplySnapshot] = Field(default_factory=list)
    bottlenecks: list[BottleneckSnapshot] = Field(default_factory=list)
    job_pressure: list[JobPressureSnapshot] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


# ── Step 43 models ────────────────────────────────────────────────────────────


class SupplyChainNodeStateResponse(BaseModel):
    """Physical node availability state for one game day."""

    node_id: str
    abstract_node: str
    availability: float
    region: str | None = None
    region_modifier: float
    region_adjusted_availability: float
    reliability_scale: float
    source: str  # "macro" | "db_override"


class SupplyChainBottleneckResponse(BaseModel):
    """Detected supply chain bottleneck with severity context."""

    node_id: str
    availability: float
    severity_label: str
    affected_baskets: list[str] = Field(default_factory=list)
    affected_jobs: list[str] = Field(default_factory=list)
    reason_summary: str
    rank: int = 0


class BasketSupplyMultiplierResponse(BaseModel):
    """Supply availability multiplier for one basket type."""

    basket_type: str
    supply_multiplier: float
    cost_pressure_label: str
    primary_bottleneck_node: str | None = None
    short_summary: str


class JobPressureResponse(BaseModel):
    """Job opportunity pressure derived from supply chain bottlenecks."""

    job_key: str
    job_pressure_multiplier: float
    source_bottleneck_nodes: list[str] = Field(default_factory=list)
    opportunity_label: str
    short_summary: str


class SupplyChainSummaryResponse(BaseModel):
    """Full daily supply chain summary for a game day."""

    day: int
    top_bottleneck_node: str | None = None
    top_bottleneck_severity: str
    most_affected_basket: str | None = None
    most_affected_basket_multiplier: float
    best_job_opportunity: str | None = None
    best_job_pressure_multiplier: float
    overall_stress_score: float
    short_summary: str
    node_states: list[SupplyChainNodeStateResponse] = Field(default_factory=list)
    bottlenecks: list[SupplyChainBottleneckResponse] = Field(default_factory=list)
    basket_multipliers: list[BasketSupplyMultiplierResponse] = Field(default_factory=list)
    job_pressure: list[JobPressureResponse] = Field(default_factory=list)


class SupplyChainStoryResponse(BaseModel):
    """Human-readable supply chain story / explainer for a game day."""

    day: int
    shortage_story: str
    bottleneck_highlights: list[str] = Field(default_factory=list)
    basket_impact_notes: list[str] = Field(default_factory=list)
    job_opportunity_hints: list[str] = Field(default_factory=list)
    practical_current_actions: list[str] = Field(default_factory=list)
