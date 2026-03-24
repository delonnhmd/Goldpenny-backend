from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.onboarding_service import (
    OnboardingFlowError,
    OnboardingFlowNotFoundError,
    OnboardingFlowValidationError,
    advance_onboarding_step,
    build_first_session_dashboard_config,
    build_onboarding_guidance,
    build_onboarding_state,
    build_unlock_schedule,
    complete_onboarding,
    skip_onboarding,
)
from app.schemas.onboarding import (
    OnboardingActionResultResponse,
    OnboardingAdvanceRequest,
    OnboardingDashboardConfigResponse,
    OnboardingGuidanceResponse,
    OnboardingStateResponse,
    OnboardingUnlockScheduleResponse,
)
from app.services.player_onboarding_service import (
    OnboardingError as PlayerOnboardingError,
    OnboardingNotFoundError as PlayerOnboardingNotFoundError,
    OnboardingValidationError as PlayerOnboardingValidationError,
    build_minimal_playable_player_summary,
    create_new_player_profile,
    get_playable_player_summary,
    initialize_starter_player_state,
    load_existing_player_state,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class NewPlayerOnboardingRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)
    gender: str
    region: str
    starter_job_code: str


class PlayablePlayerSummaryResponse(BaseModel):
    player_id: str
    display_name: str | None = None
    gender: str | None = None
    region: str
    cash_xgp: float
    bank_savings_xgp: float
    debt_xgp: float
    credit_score: int
    net_worth_xgp: float
    health: int
    stress: int
    available_hours: int
    active_housing_summary: dict | None = None
    active_employment_summary: dict | None = None
    latest_settlement_summary: dict | None = None
    latest_daily_brief: dict | None = None
    latest_portfolio_summary: dict
    load_ready: bool | None = None


def _raise_onboarding_http_error(exc: Exception) -> None:
    if isinstance(exc, (PlayerOnboardingNotFoundError, OnboardingFlowNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (PlayerOnboardingValidationError, OnboardingFlowValidationError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, (PlayerOnboardingError, OnboardingFlowError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    detail = str(exc).strip()
    if detail:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Onboarding setup failed: {detail}",
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Onboarding setup failed due to a server error. Please retry.",
    )


def _compose_action_result(
    db: Session,
    *,
    player_id: str,
    as_of_date: date | None,
    message: str,
) -> OnboardingActionResultResponse:
    state_payload = build_onboarding_state(db=db, player_id=player_id, as_of_date=as_of_date)
    guidance_payload = build_onboarding_guidance(db=db, player_id=player_id, as_of_date=as_of_date)
    config_payload = build_first_session_dashboard_config(db=db, player_id=player_id, as_of_date=as_of_date)
    unlock_payload = build_unlock_schedule(db=db, player_id=player_id, as_of_date=as_of_date)
    return OnboardingActionResultResponse(
        player_id=state_payload["player_id"],
        as_of_date=state_payload["as_of_date"],
        message=message,
        state=OnboardingStateResponse(**state_payload),
        guidance=OnboardingGuidanceResponse(**guidance_payload),
        dashboard_config=OnboardingDashboardConfigResponse(**config_payload),
        unlock_schedule=OnboardingUnlockScheduleResponse(**unlock_payload),
        debug_meta={
            "action_message": message,
        },
    )


@router.post("/new-player", response_model=PlayablePlayerSummaryResponse, summary="Create a new playable player")
def create_new_player_onboarding(
    body: NewPlayerOnboardingRequest,
    db: Session = Depends(get_db),
) -> PlayablePlayerSummaryResponse:
    created_player_id: str | None = None
    try:
        created = create_new_player_profile(
            db=db,
            display_name=body.display_name,
            gender=body.gender,
            region=body.region,
            starter_job_code=body.starter_job_code,
        )
        player = created["player"]
        created_player_id = str(player.id)

        try:
            initialize_starter_player_state(
                db=db,
                player_id=player.id,
                region=body.region,
                starter_job_code=body.starter_job_code,
            )
        except Exception as init_exc:
            logger.exception(
                "onboarding.new_player starter initialization failed; returning minimal profile fallback.",
                extra={
                    "player_id": str(player.id),
                    "display_name": body.display_name,
                    "region": body.region,
                    "starter_job_code": body.starter_job_code,
                },
            )
            db.rollback()

            # Fallback path: create a minimal profile without starter state wiring.
            created = create_new_player_profile(
                db=db,
                display_name=body.display_name,
                gender=body.gender,
                region=body.region,
                starter_job_code=body.starter_job_code,
            )
            player = created["player"]
            created_player_id = str(player.id)
            logger.warning(
                "onboarding.new_player created minimal player profile fallback after starter init failure.",
                extra={
                    "player_id": created_player_id,
                    "display_name": body.display_name,
                    "region": body.region,
                    "starter_job_code": body.starter_job_code,
                    "starter_init_error": str(init_exc),
                },
            )

        # Initialize Step 31 onboarding state immediately so first dashboard load
        # can apply progressive reveal logic without an extra bootstrap call.
        try:
            build_onboarding_state(db=db, player_id=player.id)
        except Exception:
            # Backward-compatible fallback for test harnesses/schemas that may
            # not include onboarding persistence tables yet.
            logger.exception(
                "onboarding.new_player could not initialize onboarding state; continuing with fallback-safe response.",
                extra={
                    "player_id": str(player.id),
                },
            )

        db.commit()
        try:
            summary = get_playable_player_summary(db, player.id)
            summary["load_ready"] = True
            return PlayablePlayerSummaryResponse(**summary)
        except Exception:
            logger.exception(
                "onboarding.new_player summary hydration failed; returning minimal playable summary.",
                extra={
                    "player_id": str(player.id),
                },
            )
            fallback = build_minimal_playable_player_summary(player, load_ready=False)
            return PlayablePlayerSummaryResponse(**fallback)
    except Exception as exc:
        db.rollback()
        logger.exception(
            "onboarding.new_player failed.",
            extra={
                "display_name": body.display_name,
                "gender": body.gender,
                "region": body.region,
                "starter_job_code": body.starter_job_code,
                "created_player_id": created_player_id,
                "error_type": type(exc).__name__,
            },
        )
        _raise_onboarding_http_error(exc)


@router.get("/player/{player_id}", response_model=PlayablePlayerSummaryResponse, summary="Get playable player summary")
def get_onboarding_player_summary(player_id: str, db: Session = Depends(get_db)) -> PlayablePlayerSummaryResponse:
    try:
        summary = get_playable_player_summary(db, player_id)
        return PlayablePlayerSummaryResponse(**summary)
    except Exception as exc:
        _raise_onboarding_http_error(exc)


@router.get(
    "/player/{player_id}/load",
    response_model=PlayablePlayerSummaryResponse,
    summary="Load existing player session state",
)
def load_onboarding_player_state(player_id: str, db: Session = Depends(get_db)) -> PlayablePlayerSummaryResponse:
    try:
        summary = load_existing_player_state(db, player_id)
        return PlayablePlayerSummaryResponse(**summary)
    except Exception as exc:
        _raise_onboarding_http_error(exc)


@router.get("/player/{player_id}/state", response_model=OnboardingStateResponse)
def get_onboarding_state_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingStateResponse:
    """Return persistent onboarding step/state snapshot for the player."""
    try:
        payload = build_onboarding_state(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return OnboardingStateResponse(**payload)


@router.get("/player/{player_id}/guidance", response_model=OnboardingGuidanceResponse)
def get_onboarding_guidance_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingGuidanceResponse:
    """Return concise action-based guidance for the current onboarding step."""
    try:
        payload = build_onboarding_guidance(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return OnboardingGuidanceResponse(**payload)


@router.get("/player/{player_id}/dashboard-config", response_model=OnboardingDashboardConfigResponse)
def get_onboarding_dashboard_config_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingDashboardConfigResponse:
    """Return section visibility config to reduce first-session dashboard overload."""
    try:
        payload = build_first_session_dashboard_config(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return OnboardingDashboardConfigResponse(**payload)


@router.get("/player/{player_id}/unlock-schedule", response_model=OnboardingUnlockScheduleResponse)
def get_onboarding_unlock_schedule_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingUnlockScheduleResponse:
    """Return progressive unlock schedule derived from completed onboarding milestones."""
    try:
        payload = build_unlock_schedule(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return OnboardingUnlockScheduleResponse(**payload)


@router.post("/player/{player_id}/advance", response_model=OnboardingActionResultResponse)
def advance_onboarding_route(
    player_id: str,
    request: OnboardingAdvanceRequest = Body(default=OnboardingAdvanceRequest()),
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingActionResultResponse:
    """Advance onboarding step state after a tracked action or explicit prompt flow."""
    try:
        advance_onboarding_step(
            db=db,
            player_id=player_id,
            action_key=request.action_key,
            step_key=request.step_key,
            force=bool(request.force),
            as_of_date=as_of_date,
        )
        payload = _compose_action_result(
            db,
            player_id=player_id,
            as_of_date=as_of_date,
            message="Onboarding step updated.",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return payload


@router.post("/player/{player_id}/skip", response_model=OnboardingActionResultResponse)
def skip_onboarding_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingActionResultResponse:
    """Skip onboarding and reveal the full dashboard while preserving an audit trail."""
    try:
        skip_onboarding(db=db, player_id=player_id, as_of_date=as_of_date)
        payload = _compose_action_result(
            db,
            player_id=player_id,
            as_of_date=as_of_date,
            message="Onboarding skipped.",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return payload


@router.post("/player/{player_id}/complete", response_model=OnboardingActionResultResponse)
def complete_onboarding_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingActionResultResponse:
    """Mark onboarding complete and unlock all advanced dashboard modules."""
    try:
        complete_onboarding(db=db, player_id=player_id, as_of_date=as_of_date)
        payload = _compose_action_result(
            db,
            player_id=player_id,
            as_of_date=as_of_date,
            message="Onboarding completed.",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return payload


@router.post("/player/{player_id}/refresh", response_model=OnboardingActionResultResponse)
def refresh_onboarding_route(
    player_id: str,
    request: OnboardingAdvanceRequest = Body(default=OnboardingAdvanceRequest()),
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OnboardingActionResultResponse:
    """Refresh onboarding state from persisted activity and optional action hint."""
    try:
        advance_onboarding_step(
            db=db,
            player_id=player_id,
            action_key=request.action_key,
            step_key=request.step_key,
            force=bool(request.force),
            as_of_date=as_of_date,
        )
        payload = _compose_action_result(
            db,
            player_id=player_id,
            as_of_date=as_of_date,
            message="Onboarding refreshed.",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_onboarding_http_error(exc)
    return payload
