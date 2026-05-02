"""Phase 3-C Push Scheduling: daily-loop notification dispatcher.

Selects active players inside the morning-brief or settlement-reminder
windows and sends a single push per player per window. The Celery beat
task runs every 5 minutes; each window is also 5 minutes wide so a
player is hit at most once per day per type, even with retry timing.

This module deliberately:
- skips ended runs (bankrupt / retired) and any non-active run_status
- skips players without a push token
- swallows per-player errors so one failure cannot abort the batch
- never recomputes economy / business logic — it only reads game time
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.player import Player
from app.models.player_push_token import PlayerPushToken
from app.services.game_time_service import (
    get_game_time_payload,
    get_next_morning_brief_at,
    get_next_settlement_at,
    get_server_now,
)
from app.services.notification_service import (
    DAILY_LOOP_NOTIFICATION_DEFAULTS,
    NOTIF_MORNING_BRIEF_READY,
    NOTIF_SETTLEMENT_REMINDER,
    send_daily_loop_notification,
)


logger = logging.getLogger("goldpenny.notifications.daily_loop")

ACTIVE_RUN_STATUS = "active"
MORNING_BRIEF_WINDOW = timedelta(minutes=5)
SETTLEMENT_REMINDER_LEAD = timedelta(minutes=30)
SETTLEMENT_REMINDER_WINDOW = timedelta(minutes=5)


def _player_has_token(session: Session, player_id: UUID) -> bool:
    return (
        session.query(PlayerPushToken.id)
        .filter(PlayerPushToken.player_id == player_id)
        .first()
        is not None
    )


def _in_morning_brief_window(server_now: datetime, next_brief: datetime) -> bool:
    return next_brief <= server_now < next_brief + MORNING_BRIEF_WINDOW


def _in_settlement_reminder_window(server_now: datetime, next_settlement: datetime) -> bool:
    start = next_settlement - SETTLEMENT_REMINDER_LEAD
    end = start + SETTLEMENT_REMINDER_WINDOW
    return start <= server_now < end


def _due_notifications_for(
    server_now: datetime,
    next_brief: datetime,
    next_settlement: datetime,
) -> list[tuple[str, datetime]]:
    """Return list of (notification_type, scheduled_for) due now."""
    due: list[tuple[str, datetime]] = []
    if _in_morning_brief_window(server_now, next_brief):
        due.append((NOTIF_MORNING_BRIEF_READY, next_brief))
    if _in_settlement_reminder_window(server_now, next_settlement):
        due.append((NOTIF_SETTLEMENT_REMINDER, next_settlement))
    return due


def _dispatch_for_player(
    session: Session,
    player: Player,
    due: list[tuple[str, datetime]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for notif_type, scheduled_for in due:
        defaults = DAILY_LOOP_NOTIFICATION_DEFAULTS[notif_type]
        try:
            result = send_daily_loop_notification(
                player_id=str(player.id),
                notification_type=notif_type,
                title=defaults["title"],
                body=defaults["body"],
                data=defaults["data"],
                scheduled_for=scheduled_for,
                db=session,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "daily_loop_dispatch_failed",
                extra={"player_id": str(player.id), "notification_type": notif_type},
            )
            result = {
                "ok": False,
                "skipped": False,
                "reason": "exception",
                "error": str(exc),
            }
        results.append(
            {
                "player_id": str(player.id),
                "notification_type": notif_type,
                **result,
            }
        )
    return results


def run_daily_loop_notifications(db: Session | None = None) -> dict[str, Any]:
    """Scheduler entry point: send all due daily-loop pushes.

    Designed for a 5-minute cron. Returns a summary suitable for logging
    or manual inspection. Per-player exceptions are caught so one bad
    player cannot stop the batch.
    """

    owns_session = db is None
    session = db or SessionLocal()
    try:
        payload = get_game_time_payload()
        server_now = get_server_now()
        next_brief = get_next_morning_brief_at(server_now)
        next_settlement = get_next_settlement_at(server_now)

        due = _due_notifications_for(server_now, next_brief, next_settlement)
        if not due:
            return {
                "server_now": payload["server_now"],
                "due_types": [],
                "players_considered": 0,
                "results": [],
            }

        active_players = (
            session.query(Player)
            .filter(Player.run_status == ACTIVE_RUN_STATUS)
            .all()
        )

        all_results: list[dict[str, Any]] = []
        considered = 0
        for player in active_players:
            considered += 1
            try:
                if not _player_has_token(session, player.id):
                    continue
                all_results.extend(_dispatch_for_player(session, player, due))
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "daily_loop_player_loop_error",
                    extra={"player_id": str(player.id)},
                )
                continue

        sent_count = sum(1 for r in all_results if r.get("ok") and not r.get("skipped"))
        skipped_count = sum(1 for r in all_results if r.get("skipped"))
        failed_count = sum(1 for r in all_results if not r.get("ok") and not r.get("skipped"))

        summary = {
            "server_now": payload["server_now"],
            "due_types": [t for t, _ in due],
            "players_considered": considered,
            "results_count": len(all_results),
            "sent": sent_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }
        logger.info("daily_loop_run_summary", extra=summary)
        return {**summary, "results": all_results}
    finally:
        if owns_session:
            session.close()
