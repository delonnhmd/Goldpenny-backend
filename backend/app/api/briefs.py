from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db
from app.models.daily_settlement_log import DailySettlementLog
from app.services.daily_brief_service import (
    DailyBriefError,
    DailyBriefNotFoundError,
    DailyBriefValidationError,
    generate_player_daily_brief,
    get_player_daily_brief_history,
    get_player_latest_daily_brief,
)
from app.services.daily_settlement_service import SettlementNotFoundError, get_next_player_day
from app.services.strategic_brief_service import build_strategic_brief

router = APIRouter()


class BriefGenerateResponse(BaseModel):
    player_id: str | None
    day: int
    headline: str
    summary: str
    macro_tags_json: list
    player_impact_json: dict
    action_hints_json: list
    already_processed: bool = False


class BriefHistoryResponse(BaseModel):
    player_id: str
    count: int
    briefs: list[BriefGenerateResponse]


def _raise_brief_http_error(exc: Exception) -> None:
    if isinstance(exc, (DailyBriefNotFoundError, SettlementNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, DailyBriefValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, DailyBriefError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected brief service error.")


def _default_brief_day(db: Session, player_id: str) -> int:
    try:
        pid = UUID(str(player_id))
    except ValueError as exc:
        raise SettlementNotFoundError("Player not found.") from exc
    latest_settlement = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == pid)
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    if latest_settlement is not None:
        return int(latest_settlement.day_number)
    return int(get_next_player_day(db, player_id))


@router.post("/generate/{player_id}", response_model=BriefGenerateResponse, summary="Generate player daily brief")
def generate_player_brief_route(
    player_id: str,
    day: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> BriefGenerateResponse:
    try:
        target_day = int(day) if day is not None else _default_brief_day(db, player_id)
        result = generate_player_daily_brief(db=db, player_id=player_id, day=target_day, commit=True)
    except Exception as exc:
        _raise_brief_http_error(exc)
    return BriefGenerateResponse(**result)


@router.get("/player/{player_id}/latest", response_model=BriefGenerateResponse, summary="Latest daily brief for player")
def get_latest_player_brief_route(player_id: str, db: Session = Depends(get_db)) -> BriefGenerateResponse:
    try:
        result = get_player_latest_daily_brief(db=db, player_id=player_id)
    except Exception as exc:
        _raise_brief_http_error(exc)
    return BriefGenerateResponse(**result)


@router.get("/player/{player_id}/strategic", summary="Strategic daily brief for player")
def get_player_strategic_brief_route(
    player_id: str,
    day: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> dict:
    try:
        target_day = int(day) if day is not None else _default_brief_day(db, player_id)
    except SettlementNotFoundError:
        target_day = 1
    except Exception:
        target_day = 1
    return build_strategic_brief(db=db, player_id=player_id, day=target_day)


@router.get("/player/{player_id}/history", response_model=BriefHistoryResponse, summary="Daily brief history for player")
def get_player_brief_history_route(
    player_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> BriefHistoryResponse:
    try:
        result = get_player_daily_brief_history(db=db, player_id=player_id, limit=limit)
    except Exception as exc:
        _raise_brief_http_error(exc)
    return BriefHistoryResponse(**result)
