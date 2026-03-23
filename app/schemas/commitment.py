"""Step 29 commitment response/request schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AvailableCommitmentItem(BaseModel):
    commitment_key: str
    title: str
    description: str
    suggested_duration_days: int
    expected_upside: str
    expected_downside: str
    adherence_focus: list[str] = Field(default_factory=list)
    current_fit_label: str
    risk_label: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class AvailableCommitmentsResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[AvailableCommitmentItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommitmentActivationRequest(BaseModel):
    commitment_key: str
    duration_days: int = Field(default=5, ge=3, le=7)
    replace_active: bool = False


class ActiveCommitmentResponse(BaseModel):
    player_id: str
    as_of_date: str
    status: str
    commitment_key: str
    title: str
    description: str
    duration_days: int
    start_date: str | None = None
    target_end_date: str | None = None
    days_remaining: int
    adherence_score: float
    momentum_score: float
    alignment_label: str
    drift_level: str
    days_followed: int
    days_drifted: int
    likely_payoff: str
    likely_downside: str
    summary: str
    suggested_correction: str | None = None
    reward_summary: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommitmentSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    active_commitment: ActiveCommitmentResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommitmentFeedbackItem(BaseModel):
    severity: str
    title: str
    body: str
    commitment_key: str
    feedback_type: str
    suggested_correction: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommitmentFeedbackResponse(BaseModel):
    player_id: str
    as_of_date: str
    items: list[CommitmentFeedbackItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommitmentHistoryItem(BaseModel):
    commitment_key: str
    title: str
    status: str
    start_date: str | None = None
    target_end_date: str | None = None
    completed_on_date: str | None = None
    adherence_score: float
    momentum_score: float
    days_followed: int
    days_drifted: int
    completion_summary: str | None = None
    reward_summary: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class CommitmentHistoryResponse(BaseModel):
    player_id: str
    as_of_date: str
    entries: list[CommitmentHistoryItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)

