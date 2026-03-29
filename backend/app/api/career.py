"""Step 18: Career progression API.

Route overview
--------------
GET  /career/player/{player_id}                  — Current career snapshot
GET  /career/player/{player_id}/history          — Career progress log history
POST /career/player/{player_id}/job/switch       — Switch jobs (with validation)
POST /career/player/{player_id}/certification/start  — Enrol in certification track
POST /career/player/{player_id}/training/log     — Allocate training hours for a day
GET  /career/player/{player_id}/certification    — Certification progress view
POST /career/player/{player_id}/progression/run  — Run career progression for a day (debug/manual)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.career_config import CAREER_CONFIG, CERTIFICATION_CATALOG, VALID_JOB_KEYS
from app.engine.career_service import (
    CareerError,
    CareerNotFoundError,
    CareerValidationError,
    apply_daily_career_progression,
    get_or_create_player_career,
    get_player_career_history,
    get_player_career_snapshot,
    start_certification_track,
    switch_player_job,
)
from app.schemas.career import (
    CertificationProgressResponse,
    CertificationStartRequest,
    JobSwitchRequest,
    PlayerCareerDailyResponse,
    PlayerCareerHistoryResponse,
    PlayerCareerSnapshot,
    TrainingLogRequest,
)

router = APIRouter()


def _career_404(exc: CareerNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _career_422(exc: CareerValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _career_500(exc: CareerError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def _map_career_error(exc: CareerError) -> HTTPException:
    if isinstance(exc, CareerNotFoundError):
        return _career_404(exc)
    if isinstance(exc, CareerValidationError):
        return _career_422(exc)
    return _career_500(exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/player/{player_id}",
    response_model=PlayerCareerSnapshot,
    summary="Get current career snapshot for a player",
)
def get_career_snapshot(
    player_id: str,
    db: Session = Depends(get_db),
) -> PlayerCareerSnapshot:
    """Return the current career state for *player_id*."""
    try:
        snapshot = get_player_career_snapshot(db, player_id)
    except CareerError as exc:
        raise _map_career_error(exc)
    return PlayerCareerSnapshot(**snapshot)


@router.get(
    "/player/{player_id}/history",
    response_model=PlayerCareerHistoryResponse,
    summary="Get career progress log history",
)
def get_career_history(
    player_id: str,
    limit: int = Query(default=30, ge=1, le=120),
    db: Session = Depends(get_db),
) -> PlayerCareerHistoryResponse:
    """Return up to *limit* daily career progress log entries with summary statistics."""
    try:
        history = get_player_career_history(db, player_id, limit=limit)
    except CareerError as exc:
        raise _map_career_error(exc)
    return PlayerCareerHistoryResponse(**history)


@router.post(
    "/player/{player_id}/job/switch",
    response_model=dict,
    summary="Switch player to a new job",
)
def switch_job(
    player_id: str,
    body: JobSwitchRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Switch the player to *new_job_key*.

    - Aircraft Mechanic requires completed certification.
    - Switching resets rank to entry and days_worked to 0.
    - A modest skill transfer applies for related job transitions.
    """
    try:
        result = switch_player_job(db, player_id, body.new_job_key)
        db.commit()
    except CareerError as exc:
        db.rollback()
        raise _map_career_error(exc)
    return result


@router.post(
    "/player/{player_id}/certification/start",
    response_model=dict,
    summary="Enrol player in a certification track",
)
def start_cert(
    player_id: str,
    body: CertificationStartRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Enrol the player in *track_key* certification.

    Available tracks:
    - ``aircraft_mechanic_cert`` — 180 in-game days to become an Aircraft Mechanic
    """
    try:
        result = start_certification_track(db, player_id, body.track_key)
        db.commit()
    except CareerError as exc:
        db.rollback()
        raise _map_career_error(exc)
    return result


@router.post(
    "/player/{player_id}/training/log",
    response_model=PlayerCareerDailyResponse,
    summary="Allocate training hours and advance career for the day",
)
def log_training(
    player_id: str,
    body: TrainingLogRequest,
    db: Session = Depends(get_db),
) -> PlayerCareerDailyResponse:
    """Allocate *training_hours* for the day and run career progression.

    Training hours consume the daily time budget and advance any active
    certification. Over-training raises stress. Maximum 4h per day.
    """
    as_of = None
    if body.as_of_date:
        try:
            as_of = date.fromisoformat(body.as_of_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="as_of_date must be ISO format (YYYY-MM-DD).",
            )
    try:
        result = apply_daily_career_progression(
            db=db,
            player_id=player_id,
            as_of_date=as_of,
            training_hours=Decimal(str(body.training_hours)),
            commit=True,
        )
    except CareerError as exc:
        db.rollback()
        raise _map_career_error(exc)
    return PlayerCareerDailyResponse(**result)


@router.get(
    "/player/{player_id}/certification",
    response_model=CertificationProgressResponse,
    summary="Get certification progress for a player",
)
def get_certification(
    player_id: str,
    db: Session = Depends(get_db),
) -> CertificationProgressResponse:
    """Return the active certification track state for *player_id*."""
    try:
        career = get_or_create_player_career(db, player_id)
    except CareerError as exc:
        raise _map_career_error(exc)

    cert_progress = int(career.certification_progress_days or 0)
    cert_required = int(career.certification_required_days or 0)
    remaining = max(0, cert_required - cert_progress)

    return CertificationProgressResponse(
        player_id=str(career.player_id),
        certification_track_key=career.certification_track_key,
        certification_progress_days=cert_progress,
        certification_required_days=cert_required,
        certification_completed=bool(career.certification_completed),
        estimated_days_remaining=remaining,
        debug_meta={
            "track_catalog": CERTIFICATION_CATALOG.get(career.certification_track_key or "", {}),
        },
    )


@router.post(
    "/player/{player_id}/progression/run",
    response_model=PlayerCareerDailyResponse,
    summary="Manually run daily career progression (admin/debug)",
)
def run_career_progression(
    player_id: str,
    as_of_date: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
    training_hours: float = Query(default=0.0, ge=0.0, le=4.0),
    db: Session = Depends(get_db),
) -> PlayerCareerDailyResponse:
    """Run career progression for *player_id* on *as_of_date* (defaults to current game day).

    Useful for re-running or debugging day outcomes without waiting for full settlement.
    """
    parsed_date = None
    if as_of_date:
        try:
            parsed_date = date.fromisoformat(as_of_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="as_of_date must be ISO format (YYYY-MM-DD).",
            )
    try:
        result = apply_daily_career_progression(
            db=db,
            player_id=player_id,
            as_of_date=parsed_date,
            training_hours=Decimal(str(training_hours)),
            commit=True,
        )
    except CareerError as exc:
        db.rollback()
        raise _map_career_error(exc)
    return PlayerCareerDailyResponse(**result)


@router.get(
    "/config/jobs",
    response_model=dict,
    summary="List all job career configurations (admin view)",
)
def get_job_configs() -> dict:
    """Return static career config for all six supported jobs."""
    result = {}
    for key, cfg in CAREER_CONFIG.items():
        result[key] = {
            "job_key": cfg.job_key,
            "display_name": cfg.display_name,
            "base_pay_reference": float(cfg.base_pay_reference),
            "skill_growth_rate": float(cfg.skill_growth_rate),
            "stress_sensitivity": float(cfg.stress_sensitivity),
            "performance_weight": float(cfg.performance_weight),
            "stability_weight": float(cfg.stability_weight),
            "certification_required": cfg.certification_required,
            "certification_track_key": cfg.certification_track_key or None,
            "certification_days_required": cfg.certification_days_required,
            "rank_wage_multipliers": {
                rank: float(mult) for rank, mult in cfg.rank_wage_multipliers.items()
            },
            "promotion_thresholds": [
                {
                    "from_rank": t.from_rank,
                    "to_rank": t.to_rank,
                    "min_days_worked": t.min_days_worked,
                    "min_skill": float(t.min_skill),
                    "min_trailing_performance": float(t.min_trailing_performance),
                }
                for t in cfg.promotion_thresholds
            ],
        }
    return {"jobs": result, "valid_job_keys": sorted(VALID_JOB_KEYS)}
