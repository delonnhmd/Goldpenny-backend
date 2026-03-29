"""Side-income API (Step 8: ride share MVP)."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import ALGORITHM, SECRET_KEY, get_current_user
from app.db.database import get_db
from app.engine.daily_engine import get_or_create_game_state
from app.engine.rideshare_engine import (
    MAX_RIDESHARE_HOURS_PER_DAY,
    process_rideshare_action,
)
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.side_income_action import SideIncomeAction
from app.models.user import User

router = APIRouter(prefix="/side-income", tags=["Side Income"])
logger = logging.getLogger(__name__)
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class SideIncomeOption(BaseModel):
    side_income_type: str
    display_name: str
    max_hours_per_day: int
    uses_oil_index: bool
    notes: str


class SideIncomeOptionsResponse(BaseModel):
    options: list[SideIncomeOption]


class RideShareRequest(BaseModel):
    hours_worked: float = Field(..., gt=0, description="Ride-share hours to work.")
    player_id: str | None = Field(default=None, description="Gameplay player id or display_name alias.")


class RideShareResponse(BaseModel):
    message: str
    day_number: int
    hours_worked: float
    gross_income_xgp: float
    fuel_cost_xgp: float
    wear_cost_xgp: float = 0.0
    maintenance_cost_xgp: float = 0.0
    net_income_xgp: float
    oil_index_used: float
    demand_multiplier: float = 1.0
    gas_price_xgp: float = 0.0
    wear_cost_per_hour_xgp: float = 0.0
    maintenance_triggered: bool = False
    maintenance_probability: float = 0.0
    reliability_before: float = 1.0
    reliability_after: float = 1.0
    stress_change: int
    health_change: int
    hours_before: int
    hours_after: int
    balance_before: float
    balance_after: float


class SideIncomeHistoryItem(BaseModel):
    side_income_type: str
    day_number: int
    hours_worked: float
    gross_income_xgp: float
    fuel_cost_xgp: float
    wear_cost_xgp: float = 0.0
    maintenance_cost_xgp: float = 0.0
    demand_multiplier: float = 1.0
    reliability_before: float = 1.0
    reliability_after: float = 1.0
    net_income_xgp: float
    stress_change: int
    health_change: int
    created_at: Optional[str]


class SideIncomeDailySummaryResponse(BaseModel):
    day_number: int
    side_income_hours: float
    side_income_gross_xgp: float
    side_income_fuel_cost_xgp: float
    side_income_wear_cost_xgp: float
    side_income_maintenance_cost_xgp: float
    side_income_net_xgp: float


def _get_player_or_404(db: Session, user: User) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player profile not found.")
    return player


def _resolve_player_by_identifier(db: Session, player_id: str) -> Player | None:
    raw = str(player_id or "").strip()
    if not raw:
        return None

    try:
        pid = UUID(raw)
        player = db.query(Player).filter(Player.id == pid).first()
        if player is not None:
            return player
    except ValueError:
        pass

    return (
        db.query(Player)
        .filter(func.lower(Player.display_name) == raw.lower())
        .order_by(Player.created_at.asc())
        .first()
    )


def _resolve_user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_raw = payload.get("sub")
        if not user_id_raw:
            return None
        user_id = UUID(str(user_id_raw))
    except (JWTError, ValueError):
        return None
    return db.query(User).filter(User.id == user_id).first()


@router.get("/options", response_model=SideIncomeOptionsResponse)
def get_side_income_options() -> SideIncomeOptionsResponse:
    return SideIncomeOptionsResponse(
        options=[
            SideIncomeOption(
                side_income_type="ride_share",
                display_name="Ride Share",
                max_hours_per_day=MAX_RIDESHARE_HOURS_PER_DAY,
                uses_oil_index=True,
                notes=(
                    "Flexible emergency income: trades time, stress, and slight health risk "
                    "for extra XGP."
                ),
            )
        ]
    )


@router.post("/rideshare", response_model=RideShareResponse)
def run_rideshare_action(
    payload: RideShareRequest,
    db: Session = Depends(get_db),
    auth_token: str | None = Depends(_optional_oauth2),
    x_player_id: str | None = Header(default=None, alias="X-Player-Id"),
) -> RideShareResponse:
    identity_source = "none"
    player: Player | None = None

    requested_player_id = str(payload.player_id or x_player_id or "").strip()
    if requested_player_id:
        player = _resolve_player_by_identifier(db, requested_player_id)
        identity_source = "player_id"

    if player is None:
        user = _resolve_user_from_token(db, auth_token)
        if user is not None:
            player = _get_player_or_404(db, user)
            identity_source = "bearer_token"

    if player is None:
        logger.warning(
            "side_income.rideshare unauthorized request.",
            extra={
                "identity_source": identity_source,
                "payload_player_id": payload.player_id,
                "header_player_id": x_player_id,
                "has_bearer_token": bool(auth_token),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide player_id in body/header or a valid bearer token.",
        )

    game_state = get_or_create_game_state(db)
    logger.info(
        "side_income.rideshare request resolved.",
        extra={
            "player_id": str(player.id),
            "identity_source": identity_source,
            "hours_worked": payload.hours_worked,
            "current_day": int(game_state.current_day),
            "last_settled_day": int(getattr(player, "last_settled_day", 0) or 0),
            "hours_available": int(getattr(player, "hours_available", 0) or 0),
        },
    )

    try:
        result = process_rideshare_action(
            db=db,
            player=player,
            hours_worked=payload.hours_worked,
        )
    except ValueError as exc:
        logger.warning(
            "side_income.rideshare request rejected.",
            extra={
                "player_id": str(player.id),
                "identity_source": identity_source,
                "hours_worked": payload.hours_worked,
                "reason": str(exc),
            },
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception:
        logger.exception(
            "side_income.rideshare request failed unexpectedly.",
            extra={
                "player_id": str(player.id),
                "identity_source": identity_source,
                "hours_worked": payload.hours_worked,
            },
        )
        raise

    return RideShareResponse(message="Ride share completed", **result)


@router.get("/history", response_model=list[SideIncomeHistoryItem])
def get_side_income_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SideIncomeHistoryItem]:
    player = _get_player_or_404(db, current_user)

    rows = (
        db.query(SideIncomeAction)
        .filter(SideIncomeAction.player_id == player.id)
        .order_by(SideIncomeAction.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        SideIncomeHistoryItem(
            side_income_type=row.side_income_type,
            day_number=int(row.day_number),
            hours_worked=float(row.hours_worked),
            gross_income_xgp=float(row.gross_income_xgp),
            fuel_cost_xgp=float(row.fuel_cost_xgp),
            wear_cost_xgp=float(getattr(row, "wear_cost_xgp", 0) or 0),
            maintenance_cost_xgp=float(getattr(row, "maintenance_cost_xgp", 0) or 0),
            demand_multiplier=float(getattr(row, "demand_multiplier", 1) or 1),
            reliability_before=float(getattr(row, "reliability_before", 1) or 1),
            reliability_after=float(getattr(row, "reliability_after", 1) or 1),
            net_income_xgp=float(row.net_income_xgp),
            stress_change=int(row.stress_change),
            health_change=int(row.health_change),
            created_at=row.created_at.isoformat() if row.created_at else None,
        )
        for row in rows
    ]


@router.get("/daily-summary", response_model=SideIncomeDailySummaryResponse)
def get_side_income_daily_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SideIncomeDailySummaryResponse:
    player = _get_player_or_404(db, current_user)
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)

    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == current_day,
        )
        .first()
    )

    if pds is None:
        return SideIncomeDailySummaryResponse(
            day_number=current_day,
            side_income_hours=0.0,
            side_income_gross_xgp=0.0,
            side_income_fuel_cost_xgp=0.0,
            side_income_wear_cost_xgp=0.0,
            side_income_maintenance_cost_xgp=0.0,
            side_income_net_xgp=0.0,
        )

    return SideIncomeDailySummaryResponse(
        day_number=current_day,
        side_income_hours=float(getattr(pds, "side_income_hours", 0) or 0),
        side_income_gross_xgp=float(getattr(pds, "side_income_gross_xgp", 0) or 0),
        side_income_fuel_cost_xgp=float(getattr(pds, "side_income_fuel_cost_xgp", 0) or 0),
        side_income_wear_cost_xgp=float(getattr(pds, "side_income_wear_cost_xgp", 0) or 0),
        side_income_maintenance_cost_xgp=float(getattr(pds, "side_income_maintenance_cost_xgp", 0) or 0),
        side_income_net_xgp=float(getattr(pds, "side_income_net_xgp", 0) or 0),
    )
