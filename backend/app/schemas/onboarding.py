"""Step 31 onboarding response/request schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OnboardingUnlockItem(BaseModel):
    module_key: str
    unlock_condition: str
    unlock_status: bool
    unlock_reason: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class OnboardingStateResponse(BaseModel):
    player_id: str
    as_of_date: str
    onboarding_status: str
    current_step_key: str
    current_step_index: int
    current_step_title: str
    current_step_body: str
    progress_label: str
    first_session_day_count: int
    guided_experience_active: bool = False
    guided_day_number: int = 0
    guided_phase: str | None = None
    guided_label: str | None = None
    visible_modules: list[str] = Field(default_factory=list)
    unlocked_modules: list[str] = Field(default_factory=list)
    completed_step_keys: list[str] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class OnboardingGuidanceResponse(BaseModel):
    player_id: str
    as_of_date: str
    onboarding_status: str
    guided_experience_active: bool = False
    guided_day_number: int = 0
    guided_phase: str | None = None
    guided_label: str | None = None
    step_key: str
    title: str
    body: str
    highlight_target: str
    required_action_key: str | None = None
    optional_action_key: str | None = None
    completion_condition: str
    blocker_reason: str | None = None
    can_skip: bool = True
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class OnboardingDashboardConfigResponse(BaseModel):
    player_id: str
    as_of_date: str
    onboarding_status: str
    guided_experience_active: bool = False
    guided_day_number: int = 0
    guided_phase: str | None = None
    guided_label: str | None = None
    visible_sections: list[str] = Field(default_factory=list)
    collapsed_sections: list[str] = Field(default_factory=list)
    hidden_sections: list[str] = Field(default_factory=list)
    highlighted_section: str | None = None
    highlighted_action_key: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions_for_onboarding: list[dict[str, Any]] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class OnboardingUnlockScheduleResponse(BaseModel):
    player_id: str
    as_of_date: str
    onboarding_status: str
    items: list[OnboardingUnlockItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class OnboardingAdvanceRequest(BaseModel):
    action_key: str | None = None
    step_key: str | None = None
    force: bool = False


class OnboardingActionResultResponse(BaseModel):
    player_id: str
    as_of_date: str
    message: str
    state: OnboardingStateResponse
    guidance: OnboardingGuidanceResponse
    dashboard_config: OnboardingDashboardConfigResponse
    unlock_schedule: OnboardingUnlockScheduleResponse
    debug_meta: dict[str, Any] = Field(default_factory=dict)
