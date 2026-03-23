"""Step 38 debt behavior API endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.debt_behavior_service import (
    DebtBehaviorError,
    DebtBehaviorNotFoundError,
    DebtBehaviorValidationError,
    build_debt_behavior_profile,
    build_debt_behavior_summary,
    build_debt_pressure_effects,
    build_debt_trend_state,
    detect_debt_spiral_state,
    detect_recovery_state,
)
from app.schemas.debt_behavior import (
    DebtBehaviorProfileResponse,
    DebtBehaviorSummaryResponse,
    DebtTrendStateResponse,
    RecoveryStateResponse,
    SpiralStateResponse,
)

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, DebtBehaviorNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, DebtBehaviorValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, DebtBehaviorError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected debt behavior error.")


def _resolve_day_arg(
    db: Session,
    player_id: str,
    as_of_date: date | None,
    day_number: int | None,
) -> int:
    """Resolve day integer from query params, defaulting to next player day."""
    if day_number is not None:
        return int(day_number)
    if as_of_date is not None:
        from datetime import date as _date
        from app.engine.debt_behavior_service import GAME_EPOCH

        return int((as_of_date - GAME_EPOCH).days) + 1
    from app.db.database import SessionLocal
    from app.models.player import Player
    from uuid import UUID

    try:
        pid = UUID(str(player_id))
    except ValueError:
        return 1
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        return 1
    from app.services.daily_settlement_service import get_next_player_day

    return int(get_next_player_day(db, player.id))


@router.get("/player/{player_id}/behavior-profile", response_model=DebtBehaviorProfileResponse)
def get_debt_behavior_profile(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> DebtBehaviorProfileResponse:
    """Return rolling debt behavior scores and labels for a player."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        payload = build_debt_behavior_profile(db=db, player_id=player_id, day=day)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return DebtBehaviorProfileResponse(**payload)


@router.get("/player/{player_id}/trend", response_model=DebtTrendStateResponse)
def get_debt_trend(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> DebtTrendStateResponse:
    """Return trend analysis over the last 14 days of debt behavior history."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        payload = build_debt_trend_state(db=db, player_id=player_id, day=day)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return DebtTrendStateResponse(**payload)


@router.get("/player/{player_id}/spiral-state", response_model=SpiralStateResponse)
def get_spiral_state(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> SpiralStateResponse:
    """Return current spiral risk assessment, primary driver, and estimated instability horizon."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        payload = detect_debt_spiral_state(db=db, player_id=player_id, day=day)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return SpiralStateResponse(**payload)


@router.get("/player/{player_id}/recovery-state", response_model=RecoveryStateResponse)
def get_recovery_state(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> RecoveryStateResponse:
    """Return recovery stage and confidence score derived from historical stable streaks."""
    try:
        day = _resolve_day_arg(db, player_id, as_of_date, day_number)
        payload = detect_recovery_state(db=db, player_id=player_id, day=day)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return RecoveryStateResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=DebtBehaviorSummaryResponse)
def get_debt_behavior_summary(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    day_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> DebtBehaviorSummaryResponse:
    """Return a comprehensive debt behavior summary combining all sub-components."""
    try:
        payload = build_debt_behavior_summary(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            day_number=day_number,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http(exc)
    return DebtBehaviorSummaryResponse(**payload)
