"""Side-income API (Step 8: ride share MVP)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
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
    current_user: User = Depends(get_current_user),
) -> RideShareResponse:
    player = _get_player_or_404(db, current_user)

    try:
        result = process_rideshare_action(
            db=db,
            player=player,
            hours_worked=payload.hours_worked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
