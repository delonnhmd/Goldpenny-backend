"""Operator endpoints for the Real-World Event Pipeline (Phase 3-B-1).

Mounted under ``/admin/realworld/*``. Auth reuses the same X-Internal-Key
pattern as :mod:`app.api.internal` — fail-closed if INTERNAL_API_KEY is
not configured.

Currently exposes:

  POST /admin/realworld/regenerate?date=YYYY-MM-DD
  GET  /admin/realworld/today
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.game_state import GameState
from app.services.realworld.cost_breaker import (
    HARD_BREAKER_THRESHOLD,
    OPERATIONAL_TARGET,
    CostBreaker,
)
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


@router.get("/realworld/today", dependencies=[Depends(_require_internal_key)])
def today(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return read-only operator visibility into today's real-world pipeline state."""
    game_state = db.query(GameState).order_by(GameState.id.asc()).first()
    current_day = int(game_state.current_day) if game_state is not None else None

    today_row = _event_for_day(db, current_day) if current_day is not None else None
    yesterday_row = _event_for_day(db, current_day - 1) if current_day is not None else None
    breaker = CostBreaker(db)
    monthly_cost = breaker.monthly_cost_per_mau()

    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "current_day": current_day,
        "today_event": _serialize_event(today_row),
        "yesterday_event": _serialize_event(yesterday_row),
        "breaker": {
            "monthly_cost_per_mau": monthly_cost,
            "is_tripped": monthly_cost > HARD_BREAKER_THRESHOLD,
            "operational_target": OPERATIONAL_TARGET,
            "hard_breaker_threshold": HARD_BREAKER_THRESHOLD,
        },
        "recent_generation_logs": [
            _serialize_generation_log(row)
            for row in (
                db.query(DailyEconomyEvent)
                .order_by(DailyEconomyEvent.created_at.desc(), DailyEconomyEvent.day.desc())
                .limit(7)
                .all()
            )
        ],
    }


def _event_for_day(db: Session, day: int) -> DailyEconomyEvent | None:
    return db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == day).first()


def _serialize_event(row: DailyEconomyEvent | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "day": row.day,
        "event_key": row.event_key,
        "headline": row.headline,
        "summary": row.summary,
        "event_category": row.event_category,
        "sentiment": row.sentiment,
        "severity": _json_value(row.severity),
        "impact_tags_json": row.impact_tags_json,
        "impact_tags": _json_loads(row.impact_tags_json),
        "source_type": row.source_type,
        "chain_id": row.chain_id,
        "chain_position": row.chain_position,
        "chain_length_expected": row.chain_length_expected,
        "chain_stage": row.chain_stage,
        "parent_event_key": row.parent_event_key,
        "continuation_probability": _json_value(row.continuation_probability),
        "decay_factor": _json_value(row.decay_factor),
        "chain_debug_json": row.chain_debug_json,
        "chain_debug": _json_loads(row.chain_debug_json),
        "is_realworld_anchored": row.is_realworld_anchored,
        "source_summary": row.source_summary,
        "source_urls": row.source_urls or [],
        "generated_at": _json_value(row.generated_at),
        "affected_sectors": row.affected_sectors or [],
        "duration_days": row.duration_days,
        "magnitude": row.magnitude,
        "debug_json": row.debug_json,
        "debug": _json_loads(row.debug_json),
        "created_at": _json_value(row.created_at),
    }


def _serialize_generation_log(row: DailyEconomyEvent) -> dict[str, Any]:
    return {
        "day": row.day,
        "event_id": row.event_key,
        "headline": row.headline,
        "source": _generation_source(row),
        "source_type": row.source_type,
        "is_realworld_anchored": row.is_realworld_anchored,
        "created_at": _json_value(row.created_at),
    }


def _generation_source(row: DailyEconomyEvent) -> str:
    if not row.is_realworld_anchored:
        return "static_fallback"
    if row.event_key.endswith("-quiet") or row.headline.startswith("Quiet Day"):
        return "yesterday_fallback"
    return "rule"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
