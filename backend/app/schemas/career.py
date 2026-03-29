"""Step 18: Career progression Pydantic response schemas."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class PlayerCareerSnapshot(BaseModel):
    """Full career state for one player at current time."""

    player_id: str
    current_job_key: Optional[str]
    current_job_rank: str
    current_job_skill: float
    total_days_worked_in_job: int
    trailing_performance_score: float
    promotion_eligible: bool
    promotion_progress: float = Field(ge=0.0, le=1.0)
    certification_track_key: Optional[str]
    certification_progress_days: int
    certification_required_days: int
    certification_completed: bool
    effective_monthly_pay_xgp: Optional[float]
    last_promotion_day: Optional[int]
    debug_meta: Optional[dict[str, Any]] = None


class PlayerCareerDailyResponse(BaseModel):
    """Result of one day's career progression run."""

    player_id: str
    as_of_date: str
    current_job_key: Optional[str]
    current_job_rank: str
    skill_before: float
    skill_after: float
    skill_delta: float
    performance_score: float = Field(ge=0.0, le=1.0)
    trailing_performance_score: float = Field(ge=0.0, le=1.0)
    promotion_progress: float = Field(ge=0.0, le=1.0)
    promotion_eligible: bool
    promotion_unlocked_today: bool
    certification_track_key: Optional[str]
    certification_progress_days: int
    certification_required_days: int
    certification_estimated_days_remaining: int
    certification_completed: bool
    training_hours: float
    missed_training_hours: float
    debug_meta: Optional[dict[str, Any]] = None


class CertificationProgressResponse(BaseModel):
    """Targeted view of one player's active certification track."""

    player_id: str
    certification_track_key: Optional[str]
    certification_progress_days: int
    certification_required_days: int
    certification_completed: bool
    estimated_days_remaining: int
    debug_meta: Optional[dict[str, Any]] = None


class CareerHistoryEntry(BaseModel):
    """One day of career log history."""

    day_number: int
    job_key: Optional[str]
    job_rank: Optional[str]
    skill_before: float
    skill_after: float
    skill_delta: float
    performance_score: float
    trailing_performance_score: float
    promotion_progress: float
    promotion_unlocked: bool
    certification_progress_days: int
    certification_completed: bool
    training_hours: float


class PlayerCareerHistoryResponse(BaseModel):
    """Paginated career history with summary stats."""

    player_id: str
    entries: list[CareerHistoryEntry]
    trailing_7d_avg_skill_gain: float
    trailing_7d_avg_performance: float
    promotions_count: int
    certifications_completed_count: int


class JobSwitchRequest(BaseModel):
    new_job_key: str


class CertificationStartRequest(BaseModel):
    track_key: str


class TrainingLogRequest(BaseModel):
    training_hours: float = Field(gt=0.0, le=4.0)
    as_of_date: Optional[str] = None
