"""Step 30 world memory endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.world_memory_service import (
    WorldMemoryError,
    WorldMemoryNotFoundError,
    WorldMemoryValidationError,
    build_local_pressure_summary,
    build_player_pattern_summary,
    build_region_memory_summary,
    build_world_memory_history,
    build_world_memory_summary,
    build_world_narrative,
    decay_world_memory,
    detect_recurring_patterns,
    get_world_memory_snapshot,
    update_world_memory,
)
from app.schemas.world_memory import (
    LocalPressureSummaryResponse,
    PlayerPatternSummaryResponse,
    RegionMemorySummaryResponse,
    WorldMemoryHistoryResponse,
    WorldMemorySnapshotResponse,
    WorldMemorySummaryResponse,
    WorldNarrativeResponse,
    WorldPatternsResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, WorldMemoryNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, WorldMemoryValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, WorldMemoryError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected world memory error.")


@router.get("/player/{player_id}/snapshot", response_model=WorldMemorySnapshotResponse)
def get_world_memory_snapshot_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorldMemorySnapshotResponse:
    """Return the latest world-memory snapshot, refreshing if stale."""
    try:
        payload = get_world_memory_snapshot(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return WorldMemorySnapshotResponse(**payload)


@router.get("/player/{player_id}/patterns", response_model=WorldPatternsResponse)
def get_world_memory_patterns_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorldPatternsResponse:
    """Return recurring pattern detections for the current rolling window."""
    try:
        payload = detect_recurring_patterns(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return WorldPatternsResponse(**payload)


@router.get("/player/{player_id}/narrative", response_model=WorldNarrativeResponse)
def get_world_memory_narrative_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorldNarrativeResponse:
    """Return compact world continuity narrative for the player."""
    try:
        payload = build_world_narrative(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return WorldNarrativeResponse(**payload)


@router.get("/player/{player_id}/local-pressure", response_model=LocalPressureSummaryResponse)
def get_world_memory_local_pressure_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> LocalPressureSummaryResponse:
    """Return local pressure summary around commute, cost, and opportunity."""
    try:
        payload = build_local_pressure_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return LocalPressureSummaryResponse(**payload)


@router.get("/player/{player_id}/player-patterns", response_model=PlayerPatternSummaryResponse)
def get_world_memory_player_patterns_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PlayerPatternSummaryResponse:
    """Return recent player behavior pattern summary."""
    try:
        payload = build_player_pattern_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return PlayerPatternSummaryResponse(**payload)


@router.get("/player/{player_id}/region-memory", response_model=RegionMemorySummaryResponse)
def get_world_memory_region_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RegionMemorySummaryResponse:
    """Return evolving region identity/tradeoff summary."""
    try:
        payload = build_region_memory_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return RegionMemorySummaryResponse(**payload)


@router.get("/player/{player_id}/history", response_model=WorldMemoryHistoryResponse)
def get_world_memory_history_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> WorldMemoryHistoryResponse:
    """Return recent pattern history lifecycle rows."""
    try:
        payload = build_world_memory_history(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
            limit=limit,
        )
    except Exception as exc:
        _raise_http_error(exc)
    return WorldMemoryHistoryResponse(**payload)


@router.post("/player/{player_id}/refresh", response_model=WorldMemorySnapshotResponse)
def refresh_world_memory_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorldMemorySnapshotResponse:
    """Force-refresh world memory snapshot and decay stale pattern rows."""
    try:
        payload = update_world_memory(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return WorldMemorySnapshotResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=WorldMemorySummaryResponse)
def get_world_memory_summary_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorldMemorySummaryResponse:
    """Return composed world-memory payload for frontend hydration."""
    try:
        payload = build_world_memory_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return WorldMemorySummaryResponse(**payload)


@router.post("/player/{player_id}/decay", response_model=dict)
def decay_world_memory_route(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Internal helper endpoint to force decay pass (debug/balancing use)."""
    try:
        payload = decay_world_memory(db=db, player_id=player_id, as_of_date=as_of_date)
        db.commit()
    except Exception as exc:
        db.rollback()
        _raise_http_error(exc)
    return payload

