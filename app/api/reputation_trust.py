"""Step 40 reputation and trust API endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.reputation_trust_service import (
    ReputationTrustError,
    ReputationTrustNotFoundError,
    ReputationTrustValidationError,
    apply_reputation_effects,
    build_business_reputation_state,
    build_job_reputation_state,
    build_opportunity_access_state,
    build_player_reputation_profile,
    build_reputation_summary,
    build_trust_signal_state,
)
from app.schemas.reputation_trust import (
    BusinessReputationStateResponse,
    JobReputationStateResponse,
    OpportunityAccessStateResponse,
    ReputationEffectsDetail,
    ReputationEffectsResponse,
    ReputationProfileResponse,
    ReputationSummaryResponse,
    Trend7dSummary,
    TrustSignalStateResponse,
)

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ReputationTrustNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ReputationTrustValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ReputationTrustError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected reputation trust error.",
    )


@router.get(
    "/player/{player_id}/profile",
    response_model=ReputationProfileResponse,
    summary="Build and persist player reputation profile",
)
def get_reputation_profile(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> ReputationProfileResponse:
    try:
        result = build_player_reputation_profile(db, player_id, day=day, as_of_date=as_of_date)
        db.commit()
    except (ReputationTrustError, Exception) as exc:
        db.rollback()
        _raise_http(exc)
    return ReputationProfileResponse(**result)


@router.get(
    "/player/{player_id}/trust-signals",
    response_model=TrustSignalStateResponse,
    summary="Get granular trust signal breakdown",
)
def get_trust_signals(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> TrustSignalStateResponse:
    try:
        result = build_trust_signal_state(db, player_id, day=day, as_of_date=as_of_date)
    except (ReputationTrustError, Exception) as exc:
        _raise_http(exc)
    from app.schemas.reputation_trust import (
        BorrowingSignalDetail,
        BusinessSignalDetail,
        PaymentSignalDetail,
        StabilitySignalDetail,
        WorkSignalDetail,
    )
    return TrustSignalStateResponse(
        player_id=result["player_id"],
        day=result["day"],
        as_of_date=result["as_of_date"],
        payment_signal=PaymentSignalDetail(**result["payment_signal"]),
        borrowing_signal=BorrowingSignalDetail(**result["borrowing_signal"]),
        work_signal=WorkSignalDetail(**result["work_signal"]),
        business_signal=BusinessSignalDetail(**result["business_signal"]),
        stability_signal=StabilitySignalDetail(**result["stability_signal"]),
    )


@router.get(
    "/player/{player_id}/job-state",
    response_model=JobReputationStateResponse,
    summary="Career-facing reputation modifiers",
)
def get_job_reputation_state(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> JobReputationStateResponse:
    try:
        result = build_job_reputation_state(db, player_id, day=day, as_of_date=as_of_date)
    except (ReputationTrustError, Exception) as exc:
        _raise_http(exc)
    return JobReputationStateResponse(**result)


@router.get(
    "/player/{player_id}/business-state",
    response_model=BusinessReputationStateResponse,
    summary="Business-facing reputation modifiers",
)
def get_business_reputation_state(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> BusinessReputationStateResponse:
    try:
        result = build_business_reputation_state(db, player_id, day=day, as_of_date=as_of_date)
    except (ReputationTrustError, Exception) as exc:
        _raise_http(exc)
    return BusinessReputationStateResponse(**result)


@router.get(
    "/player/{player_id}/opportunity-access",
    response_model=OpportunityAccessStateResponse,
    summary="Opportunity access tier and readiness score",
)
def get_opportunity_access_state(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> OpportunityAccessStateResponse:
    try:
        result = build_opportunity_access_state(db, player_id, day=day, as_of_date=as_of_date)
        db.commit()
    except (ReputationTrustError, Exception) as exc:
        db.rollback()
        _raise_http(exc)
    return OpportunityAccessStateResponse(**result)


@router.get(
    "/player/{player_id}/effects",
    response_model=ReputationEffectsResponse,
    summary="Read-only projection of reputation effects on jobs, credit, business",
)
def get_reputation_effects(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> ReputationEffectsResponse:
    try:
        result = apply_reputation_effects(db, player_id, day=day, as_of_date=as_of_date)
    except (ReputationTrustError, Exception) as exc:
        _raise_http(exc)
    return ReputationEffectsResponse(
        player_id=result["player_id"],
        day=result["day"],
        as_of_date=result["as_of_date"],
        trust_score=result["trust_score"],
        overall_trust_label=result["overall_trust_label"],
        opportunity_access_label=result["opportunity_access_label"],
        opportunity_readiness_score=result["opportunity_readiness_score"],
        effects=ReputationEffectsDetail(**result["effects"]),
        note=result["note"],
    )


@router.get(
    "/player/{player_id}/summary",
    response_model=ReputationSummaryResponse,
    summary="Full reputation summary — persists profile and returns synthesis",
)
def get_reputation_summary(
    player_id: str,
    day: int | None = Query(default=None, description="Game day number"),
    as_of_date: date | None = Query(default=None, description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> ReputationSummaryResponse:
    try:
        result = build_reputation_summary(db, player_id, day=day, as_of_date=as_of_date)
        db.commit()
    except (ReputationTrustError, Exception) as exc:
        db.rollback()
        _raise_http(exc)
    trend_raw = result.get("trend_7d", {})
    return ReputationSummaryResponse(
        player_id=result["player_id"],
        day=result["day"],
        as_of_date=result["as_of_date"],
        profile=result["profile"],
        trust_signals=result["trust_signals"],
        effects=ReputationEffectsDetail(**result["effects"]),
        trend_7d=Trend7dSummary(**trend_raw) if trend_raw else Trend7dSummary(),
        opportunity_access_label=result["opportunity_access_label"],
        overall_trust_label=result["overall_trust_label"],
        reputation_direction=result["reputation_direction"],
        practical_actions=result["practical_actions"],
        planning_insights=result["planning_insights"],
    )
