"""Schemas for Step 14 economic transmission outputs."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class BasketPriceDriverSnapshot(BaseModel):
    basket_key: str
    old_price_index: float
    new_price_index: float
    daily_change: float
    supply_multiplier: float
    dominant_nodes: list[str] = Field(default_factory=list)
    drivers: dict[str, float] = Field(default_factory=dict)


class BasketPricingDailyResponse(BaseModel):
    as_of_date: date
    macro_state_id: int | None
    day: int
    already_processed: bool = False
    basket_updates: list[BasketPriceDriverSnapshot] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class JobMarketModifierSnapshot(BaseModel):
    job_key: str
    pressure: float
    direction: str
    opportunity_modifier: float
    wage_drift_modifier: float
    layoff_risk_modifier: float


class JobMarketDailyResponse(BaseModel):
    as_of_date: date
    macro_state_id: int | None
    day: int
    job_updates: list[JobMarketModifierSnapshot] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DailyEconomyBriefResponse(BaseModel):
    as_of_date: date
    day: int
    headline: str
    summary_lines: list[str] = Field(default_factory=list)
    top_bottlenecks: list[str] = Field(default_factory=list)
    top_basket_movers: list[str] = Field(default_factory=list)
    top_job_changes: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)
