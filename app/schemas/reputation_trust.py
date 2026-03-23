"""Step 40 reputation and trust response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReputationProfileResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    reputation_score: float
    trust_score: float
    financial_reliability_score: float
    work_reliability_score: float
    business_reliability_score: float
    opportunity_readiness_score: float
    overall_trust_label: str
    reputation_direction: str
    payment_signal_label: str
    borrowing_signal_label: str
    work_signal_label: str
    business_signal_label: str
    stability_signal_label: str
    opportunity_access_label: str
    top_reputation_driver: str
    top_reputation_drag: str
    practical_actions: list[str] = Field(default_factory=list)
    planning_insights: list[str] = Field(default_factory=list)


class PaymentSignalDetail(BaseModel):
    label: str
    score: float
    main_drag: str
    false_growth_active: bool


class BorrowingSignalDetail(BaseModel):
    label: str
    dependence_risk_score: float
    active_loan_count: int
    repeat_borrowing_30d: int


class WorkSignalDetail(BaseModel):
    label: str
    score: float
    main_drag: str
    skill_level: int


class BusinessSignalDetail(BaseModel):
    label: str
    score: float
    main_drag: str
    business_count: int


class StabilitySignalDetail(BaseModel):
    label: str
    stability_score: float
    buffer_days: float


class TrustSignalStateResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    payment_signal: PaymentSignalDetail
    borrowing_signal: BorrowingSignalDetail
    work_signal: WorkSignalDetail
    business_signal: BusinessSignalDetail
    stability_signal: StabilitySignalDetail


class JobReputationStateResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    work_reliability_score: float
    work_signal_label: str
    main_drag: str
    career_modifier_pct: float
    career_modifier_direction: str
    skill_level: int
    has_job: bool
    opportunity_access_penalty: float
    career_progress_penalty: float
    false_growth_active: bool
    stress_level: float
    recovery_boost_active: bool


class BusinessReputationStateResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    business_reliability_score: float
    business_signal_label: str
    main_drag: str
    business_modifier_pct: float
    business_modifier_direction: str
    business_count: int
    false_growth_active: bool
    business_risk_penalty: float
    financial_reliability_score: float


class OpportunityAccessStateResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    opportunity_access_label: str
    opportunity_readiness_score: float
    tier_description: str
    trust_score: float
    reputation_score: float
    reputation_direction: str
    overall_trust_label: str
    practical_actions: list[str] = Field(default_factory=list)


class ReputationEffectsDetail(BaseModel):
    job_quality_modifier_pct: float
    credit_rate_modifier_pct: float
    demand_modifier_pct: float
    trust_modifier_pct: float


class ReputationEffectsResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    trust_score: float
    overall_trust_label: str
    opportunity_access_label: str
    opportunity_readiness_score: float
    effects: ReputationEffectsDetail
    note: str


class Trend7dSummary(BaseModel):
    avg_reputation_score: float = 0.0
    avg_trust_score: float = 0.0
    samples: int = 0


class ReputationSummaryResponse(BaseModel):
    player_id: str
    day: int
    as_of_date: str
    profile: dict[str, Any] = Field(default_factory=dict)
    trust_signals: dict[str, Any] = Field(default_factory=dict)
    effects: ReputationEffectsDetail
    trend_7d: Trend7dSummary
    opportunity_access_label: str
    overall_trust_label: str
    reputation_direction: str
    practical_actions: list[str] = Field(default_factory=list)
    planning_insights: list[str] = Field(default_factory=list)
