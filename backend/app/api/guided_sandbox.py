"""Guided sandbox API — Day 1-5 nudges for early-game direction.

Thin read-only surface around `app.services.guided_sandbox_service`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.services.guided_sandbox_service import (
    GUIDED_SANDBOX_DAY_WINDOW,
    is_active,
    list_all_nudges,
    resolve_day_nudge,
)

router = APIRouter()


@router.get("/nudge", summary="Get the guided-sandbox nudge for a given day")
def get_nudge_route(day: int = Query(..., ge=1)) -> dict:
    if day < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="day must be >= 1",
        )
    payload = resolve_day_nudge(day)
    return {
        "day": int(day),
        "is_active": is_active(day),
        "window_size": GUIDED_SANDBOX_DAY_WINDOW,
        "nudge": payload,
    }


@router.get("/nudges", summary="List all guided-sandbox nudges (days 1-5)")
def list_nudges_route() -> dict:
    return {
        "window_size": GUIDED_SANDBOX_DAY_WINDOW,
        "nudges": list_all_nudges(),
    }
