"""Step 29 commitment endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.commitment_service import (
    CommitmentError,
    CommitmentNotFoundError,
    CommitmentValidationError,
    activate_player_commitment,
    build_available_commitments,
    build_commitment_feedback,
    build_commitment_summary,
    cancel_player_commitment,
    evaluate_commitment_progress,
    get_player_active_commitment,
    get_player_commitment_history,
)
from app.schemas.commitment import (
    ActiveCommitmentResponse,
    AvailableCommitmentsResponse,
    CommitmentActivationRequest,
    CommitmentFeedbackResponse,
    CommitmentHistoryResponse,
    CommitmentSummaryResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, CommitmentNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CommitmentValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, CommitmentError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected commitment service error.")


@router.get("/player/{player_id}/available", response_model=AvailableCommitmentsResponse)
def get_available_commitments_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AvailableCommitmentsResponse:
    """Return up to 3-4 commitment options derived from Step 28 plans."""
    try:
        payload = build_available_commitments(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return AvailableCommitmentsResponse(**payload)


@router.get("/player/{player_id}/active", response_model=ActiveCommitmentResponse)
def get_active_commitment_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ActiveCommitmentResponse:
    """Return active commitment state (or inactive placeholder)."""
    try:
        payload = get_player_active_commitment(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return ActiveCommitmentResponse(**payload)


@router.post("/player/{player_id}/activate", response_model=ActiveCommitmentResponse)
def activate_commitment_route(
    player_id: str,
    request: CommitmentActivationRequest = Body(...),
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ActiveCommitmentResponse:
    """Activate a commitment; fails if one is already active unless replace_active=true."""
    try:
        payload = activate_player_commitment(
            db=db,
            player_id=player_id,
            commitment_key=request.commitment_key,
            duration_days=request.duration_days,
            replace_active=bool(request.replace_active),
            as_of_date=as_of_date,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return ActiveCommitmentResponse(**payload)


@router.post("/player/{player_id}/cancel", response_model=CommitmentSummaryResponse)
def cancel_commitment_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CommitmentSummaryResponse:
    """Cancel active commitment with history trace; returns current summary."""
    try:
        cancel_player_commitment(db=db, player_id=player_id, as_of_date=as_of_date)
        payload = build_commitment_summary(db=db, player_id=player_id, as_of_date=as_of_date, evaluate=False)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return CommitmentSummaryResponse(**payload)


@router.post("/player/{player_id}/replace", response_model=ActiveCommitmentResponse)
def replace_commitment_route(
    player_id: str,
    request: CommitmentActivationRequest = Body(...),
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ActiveCommitmentResponse:
    """Replace active commitment with a new one in a tracked, non-silent way."""
    try:
        payload = activate_player_commitment(
            db=db,
            player_id=player_id,
            commitment_key=request.commitment_key,
            duration_days=request.duration_days,
            replace_active=True,
            as_of_date=as_of_date,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return ActiveCommitmentResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=CommitmentSummaryResponse)
def get_commitment_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CommitmentSummaryResponse:
    """Return composed active commitment summary with adherence and drift context."""
    try:
        payload = build_commitment_summary(db=db, player_id=player_id, as_of_date=as_of_date, evaluate=True)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return CommitmentSummaryResponse(**payload)


@router.get("/player/{player_id}/feedback", response_model=CommitmentFeedbackResponse)
def get_commitment_feedback_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CommitmentFeedbackResponse:
    """Return compact on-track/drift feedback cards for UI surfaces."""
    try:
        payload = build_commitment_feedback(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return CommitmentFeedbackResponse(**payload)


@router.get("/player/{player_id}/history", response_model=CommitmentHistoryResponse)
def get_commitment_history_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CommitmentHistoryResponse:
    """Return recent commitment outcomes (completed/cancelled/replaced/failed)."""
    try:
        payload = get_player_commitment_history(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            limit=limit,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return CommitmentHistoryResponse(**payload)


@router.post("/player/{player_id}/refresh", response_model=CommitmentSummaryResponse)
def refresh_commitment_route(
    player_id: str,
    action_key: str | None = Query(default=None),
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CommitmentSummaryResponse:
    """Force commitment progress evaluation, typically after action execution."""
    try:
        evaluate_commitment_progress(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            action_key=action_key,
        )
        payload = build_commitment_summary(db=db, player_id=player_id, as_of_date=as_of_date, evaluate=False)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return CommitmentSummaryResponse(**payload)

