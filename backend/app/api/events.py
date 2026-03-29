"""Step 19 / 19.5: Event engine API.

Route overview
--------------
GET   /events/daily/latest          — Latest daily event
GET   /events/daily/{day}           — Event for specific day
GET   /events/history               — Recent event history
GET   /events/catalog               — Full static event catalog
GET   /events/chains/active         — Active event chains (Step 19.5)
POST  /events/daily/force           — Force a specific event for a day (admin/debug)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.event_service import (
    force_daily_event,
    get_active_chains,
    get_catalog,
    get_event_history,
    get_event_snapshot,
    run_daily_event_engine,
)
from app.schemas.events import (
    ActiveChainsResponse,
    DailyEventHistoryResponse,
    DailyEventResponse,
    EventCatalogResponse,
    ForceEventRequest,
)

router = APIRouter()


@router.get("/daily/latest", response_model=DailyEventResponse)
def read_latest_event(db: Session = Depends(get_db)):
    """Return the most recent daily event."""
    history = get_event_history(db, limit=1)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No events yet.")
    return history[0]


@router.get("/daily/{day}", response_model=DailyEventResponse)
def read_event_for_day(day: int, db: Session = Depends(get_db)):
    """Return the event for a specific game day."""
    if day <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="day must be > 0")
    result = get_event_snapshot(db, day)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No event for day {day}.")
    return result


@router.get("/history", response_model=DailyEventHistoryResponse)
def read_event_history(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return recent event history."""
    events = get_event_history(db, limit=limit)
    return {"count": len(events), "events": events}


@router.get("/catalog", response_model=EventCatalogResponse)
def read_event_catalog():
    """Return the full static event catalog."""
    templates = get_catalog()
    return {"count": len(templates), "templates": templates}


@router.get("/chains/active", response_model=ActiveChainsResponse)
def read_active_chains(
    day: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    """Return active event chains as of the given day."""
    chains = get_active_chains(db, day)
    return {"count": len(chains), "chains": chains}


@router.post("/daily/force", response_model=DailyEventResponse)
def force_event(body: ForceEventRequest, db: Session = Depends(get_db)):
    """Force a specific event for a given day (admin/debug)."""
    result = force_daily_event(db, body.day, body.event_key)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result["error"])
    db.commit()
    return result
