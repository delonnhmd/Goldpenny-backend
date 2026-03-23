"""Step 26 progression response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DailyGoalItem(BaseModel):
    goal_key: str
    title: str
    description: str
    status: str
    progress_current: float
    progress_target: float
    reward_summary: str
    urgency: str
    expires_on: str | None = None
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WeeklyMissionItem(BaseModel):
    mission_key: str
    title: str
    description: str
    status: str
    progress_current: float
    progress_target: float
    reward_summary: str
    week_start: str
    week_end: str
    category: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class StreakItem(BaseModel):
    streak_key: str
    title: str
    current_count: int
    best_count: int
    status: str
    last_credited_on: str | None = None
    reset_risk: str
    next_credit_condition: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class ProgressionSummaryResponse(BaseModel):
    player_id: str
    as_of_date: str
    daily_goals: list[DailyGoalItem] = Field(default_factory=list)
    weekly_missions: list[WeeklyMissionItem] = Field(default_factory=list)
    streaks: list[StreakItem] = Field(default_factory=list)
    recently_completed: list[dict[str, Any]] = Field(default_factory=list)
    suggested_focus: list[str] = Field(default_factory=list)
    motivational_summary: str
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class DailyGoalsResponse(BaseModel):
    player_id: str
    as_of_date: str
    daily_goals: list[DailyGoalItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class WeeklyMissionsResponse(BaseModel):
    player_id: str
    as_of_date: str
    weekly_missions: list[WeeklyMissionItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)


class StreaksResponse(BaseModel):
    player_id: str
    as_of_date: str
    streaks: list[StreakItem] = Field(default_factory=list)
    debug_meta: dict[str, Any] = Field(default_factory=dict)
