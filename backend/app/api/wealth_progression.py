"""Step 39 wealth progression API endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.wealth_progression_service import (
    WealthProgressionError,
    WealthProgressionNotFoundError,
    WealthProgressionValidationError,
    apply_wealth_growth_outcomes,
    build_asset_progression_state,
    build_net_worth_summary,
    build_savings_capacity_state,
    build_wealth_momentum_summary,
    build_wealth_profile,
    evaluate_wealth_actions,
)
from app.schemas.wealth_progression import (
    AssetProgressionStateResponse,
    NetWorthSummaryResponse,
    SavingsCapacityStateResponse,
    WealthActionsEvaluationResponse,
    WealthMomentumSummaryResponse,
    WealthProfileResponse,
)

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, WealthProgressionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, WealthProgressionValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, WealthProgressionError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected wealth progression error.",
    )


def _resolve_day_arg(
    db: Session,
    player_id: str,
    as_of_date: date | None,
    day_number: int | None,
) -> int:
    """Resolve game day integer from query params, defaulting to next player day."""
    if day_number is not None:
        return int(day_number)
    if as_of_date is not None:
        from app.engine.wealth_progression_service import GAME_EPOCH

        return int((as_of_date - GAME_EPOCH).days) + 1
    from uuid import UUID

    from app.models.player import Player

    try:
        pid = UUID(str(player_id))
    except ValueError:
        return 1
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        return 1
    from app.services.daily_settlement_service import get_next_player_day

    return int(get_next_player_day(db, player.id))


@router.get("/player/{player_id}/profile", response_model=WealthProfileResponse)
def get_wealth_profile(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> WealthProfileResponse:
    """Return the rolling wealth profile including all asset, debt, and score components."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        payload = build_wealth_profile(db=db, player_id=player_id, day=day)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return WealthProfileResponse(**payload)


@router.get("/player/{player_id}/savings-capacity", response_model=SavingsCapacityStateResponse)
def get_savings_capacity(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> SavingsCapacityStateResponse:
    """Return savings and investment readiness labels plus recommended buffer thresholds."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        aod = as_of_date
        payload = build_savings_capacity_state(db=db, player_id=player_id, day=day, as_of_date=aod)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return SavingsCapacityStateResponse(**payload)


@router.get("/player/{player_id}/asset-progression", response_model=AssetProgressionStateResponse)
def get_asset_progression(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> AssetProgressionStateResponse:
    """Return asset breakdown: liquid, market (stocks), business equity, diversification."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        aod = as_of_date
        payload = build_asset_progression_state(db=db, player_id=player_id, day=day, as_of_date=aod)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return AssetProgressionStateResponse(**payload)


@router.get("/player/{player_id}/action-evaluation", response_model=WealthActionsEvaluationResponse)
def get_action_evaluation(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> WealthActionsEvaluationResponse:
    """Evaluate all wealth actions (save, invest, pay_debt, etc.) and return readiness labels."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        aod = as_of_date
        payload = evaluate_wealth_actions(db=db, player_id=player_id, day=day, as_of_date=aod)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return WealthActionsEvaluationResponse(**payload)


@router.get("/player/{player_id}/net-worth-summary", response_model=NetWorthSummaryResponse)
def get_net_worth_summary(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> NetWorthSummaryResponse:
    """Return net worth direction, growth quality, false-growth detection, and recommendations."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        aod = as_of_date
        payload = build_net_worth_summary(db=db, player_id=player_id, day=day, as_of_date=aod)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return NetWorthSummaryResponse(**payload)


@router.get("/player/{player_id}/momentum-summary", response_model=WealthMomentumSummaryResponse)
def get_wealth_momentum_summary(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> WealthMomentumSummaryResponse:
    """Return full wealth momentum synthesis: phase advisory, softening, planning insights."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        aod = as_of_date
        payload = build_wealth_momentum_summary(db=db, player_id=player_id, day=day, as_of_date=aod)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return WealthMomentumSummaryResponse(**payload)
