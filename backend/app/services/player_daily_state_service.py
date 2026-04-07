"""Shared, race-safe helpers for per-player daily state rows."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState

logger = logging.getLogger(__name__)

Q4 = Decimal("0.0001")


def _q4(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q4, rounding=ROUND_HALF_UP)


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(default)


def _find_player_daily_state(db: Session, *, player_id: Any, day_number: int) -> PlayerDailyState | None:
    return (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player_id,
            PlayerDailyState.day_number == int(day_number),
        )
        .first()
    )


def _base_defaults(player: Player) -> dict[str, Any]:
    hours_now = _safe_int(getattr(player, "hours_available", 16), 16)
    stress_now = _safe_int(getattr(player, "stress", 0), 0)
    health_now = _safe_int(getattr(player, "health", 100), 100)
    cash_now = _q4(getattr(player, "cash", 0))
    return {
        "hours_available_start": hours_now,
        "hours_available_end": hours_now,
        "worked_main_job": False,
        "did_settlement": False,
        "stress_start": stress_now,
        "stress_end": stress_now,
        "health_start": health_now,
        "health_end": health_now,
        "cash_start": cash_now,
        "cash_end": cash_now,
    }


def ensure_player_daily_state(
    db: Session,
    *,
    player: Player,
    day_number: int,
    defaults: dict[str, Any] | None = None,
) -> PlayerDailyState:
    """Return one PlayerDailyState row for (player, day), creating it safely."""
    resolved_day = int(day_number)
    existing = _find_player_daily_state(db, player_id=player.id, day_number=resolved_day)
    if existing is not None:
        return existing

    payload = {
        "player_id": player.id,
        "day_number": resolved_day,
        **_base_defaults(player),
    }
    if defaults:
        payload.update(defaults)

    state = PlayerDailyState(**payload)
    savepoint = db.begin_nested()
    try:
        db.add(state)
        db.flush()
        savepoint.commit()
        return state
    except IntegrityError:
        savepoint.rollback()
        raced = _find_player_daily_state(db, player_id=player.id, day_number=resolved_day)
        if raced is not None:
            logger.warning(
                "player_daily_state ensure raced on unique row; returning existing state.",
                extra={
                    "player_id": str(player.id),
                    "day_number": resolved_day,
                },
            )
            return raced
        raise
