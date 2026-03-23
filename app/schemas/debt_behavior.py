"""Step 38 debt behavior response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DebtBehaviorProfileResponse(BaseModel):
    player_id: str
    day_number: int
    as_of_date: str
    debt_dependency_score: float
    payment_stack_pressure_score: float
    borrowing_frequency_score: float
    financial_stability_score: float
    composite_risk_score: float
    trend_direction: str
    debt_state_label: str
    spiral_risk_label: str
    recovery_stage: str
    top_risk_driver: str
    top_recovery_driver: str
    planning_warnings: list[str] = Field(default_factory=list)


class DebtTrendStateResponse(BaseModel):
    player_id: str
    day_number: int
    has_history: bool
    trend_direction: str
    days_tracked: int
    average_composite_risk: float
    worst_spiral_label: str
    most_recent_spiral_label: str
    consecutive_stable_days: int
    trend_summary: str


class SpiralStateResponse(BaseModel):
    player_id: str
    day_number: int
    spiral_risk_label: str
    primary_driver: str
    time_to_instability_estimate: str
    composite_risk_score: float
    trend_direction: str
    short_summary: str


class RecoveryStateResponse(BaseModel):
    player_id: str
    day_number: int
    recovery_stage: str
    confidence_score: float
    consecutive_stable_days: int
    spiral_risk_label: str
    short_summary: str


class DebtBehaviorSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    debt_state_label: str
    recovery_state_label: str
    spiral_risk_label: str
    trend_direction: str
    top_risk_driver: str
    top_recovery_driver: str
    debt_dependency_score: float
    payment_stack_pressure_score: float
    borrowing_frequency_score: float
    financial_stability_score: float
    composite_risk_score: float
    consecutive_stable_days: int
    recovery_confidence_score: float
    stress_baseline_modifier: float
    shock_sensitivity_modifier: float
    borrowing_access_penalty: float
    business_expansion_penalty: float
    time_to_instability_estimate: str
    practical_actions: list[str] = Field(default_factory=list)
    planning_warnings: list[str] = Field(default_factory=list)
    trend_days_tracked: int
    short_summary: str
