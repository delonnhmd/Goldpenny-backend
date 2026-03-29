"""Step 35 personal shock response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PersonalShockProfileResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    shock_risk_score: float
    financial_fragility_score: float
    health_fragility_score: float
    work_disruption_risk_score: float
    recovery_capacity_score: float
    recent_pressure_direction: str
    recent_negative_streak: int = 0
    recent_recovery_support: int = 0
    last_updated_on: int
    last_updated_date: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PersonalRiskStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    day_number: int
    shock_risk_label: str
    event_roll_chance: float
    severity_weights: dict[str, float] = Field(default_factory=dict)
    major_event_probability: float
    repeat_shock_protection_active: bool = False
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PersonalLifeEventResponse(BaseModel):
    event_triggered: bool = False
    event_key: str | None = None
    event_family: str | None = None
    headline: str
    severity_band: str
    as_of_date: str | None = None
    day_number: int | None = None
    cash_impact_xgp: float = 0.0
    stress_impact_delta: float = 0.0
    health_impact_delta: float = 0.0
    time_impact_hours: float = 0.0
    work_income_impact: float = 0.0
    business_impact: float = 0.0
    side_income_impact: float = 0.0
    duration_days: int = 0
    recovery_hint: str = ""
    trigger_tags: list[str] = Field(default_factory=list)
    impact: dict[str, Any] = Field(default_factory=dict)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class RecoveryStateResponse(BaseModel):
    player_id: str | None = None
    recovery_days_remaining: int = 0
    temporary_stress_modifier: float = 0.0
    temporary_health_modifier: float = 0.0
    temporary_income_modifier: float = 0.0
    temporary_business_modifier: float = 0.0
    temporary_time_modifier: float = 0.0
    recovery_status_label: str = "stable"
    source_event_key: str | None = None
    source_event_severity: str | None = None
    last_applied_day: int | None = None
    next_expire_day: int | None = None
    short_summary: str = ""
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PlayerResilienceSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    resilience_label: str
    cash_buffer_label: str
    stress_load_label: str
    recovery_capacity_label: str
    top_risk_driver: str
    top_stabilizer: str
    short_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PersonalShockSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    current_shock_risk_label: str
    recent_event_summary: str
    active_recovery_summary: str
    practical_current_actions: list[str] = Field(default_factory=list)
    short_recommendation: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class PersonalShockSystemSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    shock_profile: PersonalShockProfileResponse
    risk_state: PersonalRiskStateResponse
    recent_event: PersonalLifeEventResponse
    recovery_state: RecoveryStateResponse
    resilience_summary: PlayerResilienceSummaryResponse
    shock_summary: PersonalShockSummaryResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)

