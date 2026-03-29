"""app/api/soft_launch.py — Step 70: Soft Launch Harness.

Player-facing routes for the soft launch cohort:

  POST /soft-launch/join       — Validate invite code, create membership
  GET  /soft-launch/status     — Check if the current user is a member
  POST /soft-launch/feedback   — Submit in-game feedback (rating + 3 questions)
  POST /soft-launch/issue      — Submit an issue / friction / bug report

All routes require a valid Bearer JWT (the same auth used everywhere else).
The join endpoint also atomically increments use_count on the invite code and
rejects codes that are inactive or at capacity.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.issue_report import IssueReport
from app.models.player import Player
from app.models.player_feedback import PlayerFeedback
from app.models.soft_launch_access import SoftLaunchAccess
from app.models.soft_launch_member import SoftLaunchMember
from app.models.user import User

router = APIRouter()

# ── Request / response schemas ────────────────────────────────────────────────


class JoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=1, max_length=64, description="Invite code")


class JoinResponse(BaseModel):
    cohort_tag: str
    is_approved: bool
    message: str


class SoftLaunchStatusResponse(BaseModel):
    is_member: bool
    cohort_tag: Optional[str] = None
    joined_at: Optional[str] = None


class FeedbackRequest(BaseModel):
    session_id: Optional[str] = None
    game_day: int = Field(1, ge=1, le=365)
    rating: int = Field(..., ge=1, le=5)
    response_confusing: Optional[str] = Field(None, max_length=400)
    response_hard: Optional[str] = Field(None, max_length=400)
    response_interesting: Optional[str] = Field(None, max_length=400)


class FeedbackResponse(BaseModel):
    ok: bool
    feedback_id: str


class IssueRequest(BaseModel):
    session_id: Optional[str] = None
    game_day: Optional[int] = Field(None, ge=1, le=365)
    description: str = Field(..., min_length=1, max_length=2000)
    category: Optional[str] = Field(None, pattern=r"^(bug|friction|ui|balance|other)$")
    severity: Optional[str] = Field(None, pattern=r"^(low|medium|high|blocker)$")
    extra_context_json: Optional[str] = None


class IssueResponse(BaseModel):
    ok: bool
    issue_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_player(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found for this account.",
        )
    return player


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "/join",
    response_model=JoinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join the soft launch cohort via invite code",
)
def join_soft_launch(
    payload: JoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JoinResponse:
    # Idempotent — return existing membership if already joined.
    existing = (
        db.query(SoftLaunchMember)
        .filter(SoftLaunchMember.user_id == current_user.id)
        .first()
    )
    if existing:
        return JoinResponse(
            cohort_tag=existing.cohort_tag,
            is_approved=existing.is_approved,
            message="Already a member of the soft launch.",
        )

    code_row = (
        db.query(SoftLaunchAccess)
        .filter(SoftLaunchAccess.invite_code == payload.invite_code)
        .first()
    )
    if not code_row or not code_row.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or inactive invite code.",
        )
    if code_row.use_count >= code_row.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite code has reached its usage limit.",
        )

    member = SoftLaunchMember(
        user_id=current_user.id,
        invite_code_used=payload.invite_code,
        cohort_tag=code_row.cohort_tag,
        is_approved=True,
    )
    code_row.use_count += 1
    db.add(member)
    db.commit()
    db.refresh(member)

    return JoinResponse(
        cohort_tag=member.cohort_tag,
        is_approved=member.is_approved,
        message="Welcome to the soft launch!",
    )


@router.get(
    "/status",
    response_model=SoftLaunchStatusResponse,
    summary="Check soft launch membership for the current user",
)
def get_soft_launch_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SoftLaunchStatusResponse:
    member = (
        db.query(SoftLaunchMember)
        .filter(SoftLaunchMember.user_id == current_user.id)
        .first()
    )
    if not member:
        return SoftLaunchStatusResponse(is_member=False)
    return SoftLaunchStatusResponse(
        is_member=True,
        cohort_tag=member.cohort_tag,
        joined_at=member.joined_at.isoformat() if member.joined_at else None,
    )


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit in-game feedback (rating + 3-question survey)",
)
def submit_feedback(
    payload: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    player = _get_player(current_user, db)

    member = (
        db.query(SoftLaunchMember)
        .filter(SoftLaunchMember.user_id == current_user.id)
        .first()
    )
    cohort_tag = member.cohort_tag if member else None

    feedback = PlayerFeedback(
        player_id=player.id,
        session_id=payload.session_id,
        game_day=payload.game_day,
        rating=payload.rating,
        response_confusing=payload.response_confusing,
        response_hard=payload.response_hard,
        response_interesting=payload.response_interesting,
        cohort_tag=cohort_tag,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return FeedbackResponse(ok=True, feedback_id=str(feedback.id))


@router.post(
    "/issue",
    response_model=IssueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an issue, friction point, or bug report",
)
def submit_issue(
    payload: IssueRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IssueResponse:
    player = _get_player(current_user, db)

    report = IssueReport(
        player_id=player.id,
        session_id=payload.session_id,
        game_day=payload.game_day,
        description=payload.description,
        category=payload.category,
        severity=payload.severity,
        extra_context_json=payload.extra_context_json,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return IssueResponse(ok=True, issue_id=str(report.id))
