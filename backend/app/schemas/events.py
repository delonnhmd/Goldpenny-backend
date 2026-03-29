"""Step 19 / 19.5: Event engine Pydantic response schemas."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class DailyEventResponse(BaseModel):
    """Single daily event payload."""

    id: str
    day: int
    event_key: str
    headline: str
    summary: Optional[str] = None
    event_category: str
    sentiment: str
    severity: float = Field(ge=0.0)
    impact_tags: Any = None
    source_type: str = "generated"
    created_at: Optional[str] = None
    already_processed: bool = False

    macro_before: Optional[dict[str, float]] = None
    macro_after: Optional[dict[str, float]] = None
    pre_cap_deltas: Optional[dict[str, float]] = None
    post_cap_deltas: Optional[dict[str, float]] = None

    # Step 19.5 chain fields
    chain_id: Optional[str] = None
    chain_position: int = 0
    chain_stage: Optional[str] = None
    chain_length_expected: Optional[int] = None
    parent_event_key: Optional[str] = None
    is_chain_continuation: bool = False
    continuation_probability: float = 0.0
    decay_factor: float = 1.0


class DailyEventHistoryResponse(BaseModel):
    """List of recent daily events."""

    count: int
    events: list[DailyEventResponse]


class EventCatalogEntry(BaseModel):
    """One entry from the static event catalog."""

    event_key: str
    headline: str
    category: str
    sentiment: str
    severity_weight: float
    impact_tags: dict[str, float]
    preconditions: dict[str, float]
    can_chain: bool = False
    chain_group_key: Optional[str] = None


class EventCatalogResponse(BaseModel):
    """Full event catalog."""

    count: int
    templates: list[EventCatalogEntry]


class ForceEventRequest(BaseModel):
    """Body for POST /events/daily/force."""

    day: int = Field(gt=0)
    event_key: str = Field(min_length=1, max_length=80)


class ActiveChainSummary(BaseModel):
    """Summary of one active event chain."""

    chain_id: str
    latest_day: int
    latest_event_key: str
    chain_position: int
    chain_stage: Optional[str] = None
    chain_length_expected: int = 0
    decay_factor: float = 1.0
    continuation_probability: float = 0.0
    is_active: bool = True


class ActiveChainsResponse(BaseModel):
    """Active event chains."""

    count: int
    chains: list[ActiveChainSummary]
