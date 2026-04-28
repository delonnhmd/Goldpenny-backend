"""Operator endpoints for the Real-World Event Pipeline (Phase 3-B-1, task 4).

Mounted under ``/admin/realworld/*``. Auth reuses the same X-Internal-Key
pattern as :mod:`app.api.internal` — fail-closed if INTERNAL_API_KEY is
not configured.

Currently exposes only the manual override:

  POST /admin/realworld/regenerate?date=YYYY-MM-DD

The Task 6 read-only "today" view (GET /admin/realworld/today) lands in
the next commit.
"""

from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.realworld.daily_generation_job import run_daily_generation

router = APIRouter()


def _require_internal_key(x_internal_key: str = Header(default="")) -> None:
    """Same fail-closed pattern as app.api.internal._require_internal_key."""
    expected = os.getenv("INTERNAL_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is disabled (INTERNAL_API_KEY not configured).",
        )
    if x_internal_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key.",
        )


@router.post("/realworld/regenerate", dependencies=[Depends(_require_internal_key)])
def regenerate(
    date_str: str | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
) -> dict:
    """Manually trigger the daily generation pipeline for ``date``.

    Idempotent: if a row already exists for the resulting game day, the
    job short-circuits and returns ``source: "skipped_idempotent"``.
    """
    target: date | None = None
    if date_str is not None:
        try:
            target = date.fromisoformat(date_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date {date_str!r}; expected YYYY-MM-DD.",
            ) from exc
    return run_daily_generation(target_date=target, db=db)
