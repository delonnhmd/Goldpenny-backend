from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.daily_settlement_log import DailySettlementLog
from app.models.player import Player
from app.services.net_worth_service import (
    NetWorthError,
    NetWorthNotFoundError,
    NetWorthValidationError,
    compute_player_net_worth_snapshot,
    get_latest_player_net_worth_snapshot,
    get_player_asset_allocation,
    get_player_net_worth_history,
)

router = APIRouter()


class NetWorthSnapshotResponse(BaseModel):
    id: str
    player_id: str
    day: int
    cash_xgp: float
    bank_savings_xgp: float
    stock_market_value_xgp: float
    business_value_xgp: float
    inventory_value_xgp: float
    total_assets_xgp: float
    debt_xgp: float
    net_worth_xgp: float
    allocation_json: dict
    created_at: str | None = None
    already_processed: bool | None = None


class NetWorthHistoryResponse(BaseModel):
    player_id: str
    count: int
    snapshots: list[NetWorthSnapshotResponse]


class AllocationResponse(BaseModel):
    player_id: str
    day: int
    cash_xgp: float
    bank_savings_xgp: float
    stock_market_value_xgp: float
    business_value_xgp: float
    inventory_value_xgp: float
    debt_xgp: float
    total_assets_xgp: float
    net_worth_xgp: float
    allocation_json: dict


def _raise_net_worth_http_error(exc: Exception) -> None:
    if isinstance(exc, NetWorthNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, NetWorthValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, NetWorthError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected net-worth service error.")


def _resolve_player_or_404(db: Session, player_id: str) -> Player:
    try:
        pid = UUID(str(player_id))
    except ValueError as exc:
        raise NetWorthNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise NetWorthNotFoundError("Player not found.")
    return player


def _default_compute_day(db: Session, player_id: str) -> int:
    player = _resolve_player_or_404(db, player_id)
    if player.last_settled_day is not None and int(player.last_settled_day) > 0:
        return int(player.last_settled_day)

    latest_settlement_day = (
        db.query(func.max(DailySettlementLog.day_number))
        .filter(DailySettlementLog.player_id == player.id)
        .scalar()
    )
    if latest_settlement_day is not None and int(latest_settlement_day) > 0:
        return int(latest_settlement_day)

    return 1


@router.post(
    "/player/{player_id}/snapshot/compute",
    response_model=NetWorthSnapshotResponse,
    summary="Compute and persist one player net-worth snapshot",
)
def compute_player_snapshot_route(
    player_id: str,
    day: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> NetWorthSnapshotResponse:
    try:
        target_day = int(day) if day is not None else _default_compute_day(db, player_id)
        payload = compute_player_net_worth_snapshot(
            db=db,
            player_id=player_id,
            day=target_day,
            commit=True,
        )
        return NetWorthSnapshotResponse(**payload)
    except Exception as exc:
        _raise_net_worth_http_error(exc)


@router.get(
    "/player/{player_id}/snapshot/latest",
    response_model=NetWorthSnapshotResponse,
    summary="Get latest net-worth snapshot for player",
)
def get_latest_player_snapshot_route(player_id: str, db: Session = Depends(get_db)) -> NetWorthSnapshotResponse:
    try:
        payload = get_latest_player_net_worth_snapshot(db=db, player_id=player_id)
        return NetWorthSnapshotResponse(**payload)
    except Exception as exc:
        _raise_net_worth_http_error(exc)


@router.get(
    "/player/{player_id}/history",
    response_model=NetWorthHistoryResponse,
    summary="Get recent net-worth snapshot history for player",
)
def get_player_snapshot_history_route(
    player_id: str,
    limit: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> NetWorthHistoryResponse:
    try:
        payload = get_player_net_worth_history(db=db, player_id=player_id, limit=limit)
        return NetWorthHistoryResponse(**payload)
    except Exception as exc:
        _raise_net_worth_http_error(exc)


@router.get(
    "/player/{player_id}/allocation",
    response_model=AllocationResponse,
    summary="Get latest asset allocation summary for player",
)
def get_player_allocation_route(player_id: str, db: Session = Depends(get_db)) -> AllocationResponse:
    try:
        payload = get_player_asset_allocation(db=db, player_id=player_id)
        return AllocationResponse(**payload)
    except Exception as exc:
        _raise_net_worth_http_error(exc)
