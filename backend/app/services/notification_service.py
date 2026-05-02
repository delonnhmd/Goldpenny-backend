from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.player_notification_log import PlayerNotificationLog
from app.models.player_push_token import PlayerPushToken


logger = logging.getLogger("goldpenny.notifications")

EXPO_PUSH_SEND_URL = "https://exp.host/--/api/v2/push/send"

# Phase 3-C Push Scheduling: daily-loop notification types.
NOTIF_MORNING_BRIEF_READY = "MORNING_BRIEF_READY"
NOTIF_SETTLEMENT_REMINDER = "SETTLEMENT_REMINDER"

DAILY_LOOP_NOTIFICATION_TYPES = {NOTIF_MORNING_BRIEF_READY, NOTIF_SETTLEMENT_REMINDER}

DAILY_LOOP_NOTIFICATION_DEFAULTS: dict[str, dict[str, Any]] = {
    NOTIF_MORNING_BRIEF_READY: {
        "title": "New Day Ready",
        "body": "Your Daily Brief is ready. Check today's economy and plan your moves.",
        "data": {"screen": "Life", "type": "daily_brief"},
    },
    NOTIF_SETTLEMENT_REMINDER: {
        "title": "Day Ending Soon",
        "body": "Finish your actions before settlement.",
        "data": {"screen": "Summary", "type": "settlement_reminder"},
    },
}


def send_push_notification(
    player_id: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Send a basic Expo push notification to every token registered for a player."""

    owns_session = db is None
    session = db or SessionLocal()
    try:
        try:
            player_uuid = UUID(str(player_id))
        except ValueError:
            logger.warning("push_send_invalid_player_id", extra={"player_id": str(player_id)})
            return {
                "ok": False,
                "tokens": 0,
                "sent": 0,
                "failed": 0,
                "tickets": [],
                "errors": ["Invalid player_id."],
            }

        tokens = (
            session.query(PlayerPushToken)
            .filter(PlayerPushToken.player_id == player_uuid)
            .order_by(PlayerPushToken.updated_at.desc())
            .all()
        )
        if not tokens:
            logger.info("push_send_no_tokens", extra={"player_id": str(player_id)})
            return {
                "ok": False,
                "tokens": 0,
                "sent": 0,
                "failed": 0,
                "tickets": [],
                "errors": [],
                "message": "No push tokens registered for this player.",
            }

        messages = [
            {
                "to": row.push_token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {},
            }
            for row in tokens
        ]

        try:
            response = httpx.post(EXPO_PUSH_SEND_URL, json=messages, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning(
                "push_send_failed",
                extra={"player_id": str(player_id), "token_count": len(tokens), "error": str(exc)},
            )
            return {
                "ok": False,
                "tokens": len(tokens),
                "sent": 0,
                "failed": len(tokens),
                "tickets": [],
                "errors": [str(exc)],
            }

        tickets = payload.get("data", []) if isinstance(payload, dict) else []
        if isinstance(tickets, dict):
            tickets = [tickets]
        if not isinstance(tickets, list):
            tickets = []

        failed = 0
        errors: list[str] = []
        for ticket in tickets:
            if isinstance(ticket, dict) and ticket.get("status") == "ok":
                continue
            failed += 1
            if isinstance(ticket, dict):
                message = str(ticket.get("message") or ticket.get("details") or "Expo push ticket failed.")
            else:
                message = "Expo push ticket failed."
            errors.append(message)

        sent = max(0, len(tokens) - failed)
        logger.info(
            "push_send_completed",
            extra={"player_id": str(player_id), "token_count": len(tokens), "sent": sent, "failed": failed},
        )
        return {
            "ok": failed == 0,
            "tokens": len(tokens),
            "sent": sent,
            "failed": failed,
            "tickets": tickets,
            "errors": errors,
        }
    finally:
        if owns_session:
            session.close()


def _has_existing_log(
    session: Session,
    player_uuid: UUID,
    notification_type: str,
    scheduled_for: datetime,
) -> bool:
    return (
        session.query(PlayerNotificationLog.id)
        .filter(
            PlayerNotificationLog.player_id == player_uuid,
            PlayerNotificationLog.notification_type == notification_type,
            PlayerNotificationLog.scheduled_for == scheduled_for,
        )
        .first()
        is not None
    )


def send_daily_loop_notification(
    player_id: str,
    notification_type: str,
    title: str,
    body: str,
    data: dict[str, Any],
    scheduled_for: datetime,
    db: Session | None = None,
) -> dict[str, Any]:
    """Send a daily-loop push and write a `player_notification_log` row.

    Idempotent on (player_id, notification_type, scheduled_for): if a row
    already exists, the push is skipped. Failures never raise — the result
    dict carries `ok=False` and an error message instead, so the scheduler
    cannot crash on a single bad player.
    """

    owns_session = db is None
    session = db or SessionLocal()
    try:
        try:
            player_uuid = UUID(str(player_id))
        except ValueError:
            logger.warning(
                "daily_loop_push_invalid_player_id",
                extra={"player_id": str(player_id)},
            )
            return {
                "ok": False,
                "skipped": True,
                "reason": "invalid_player_id",
                "tokens": 0,
                "log_id": None,
                "payload": None,
            }

        if _has_existing_log(session, player_uuid, notification_type, scheduled_for):
            logger.info(
                "daily_loop_push_duplicate_skip",
                extra={
                    "player_id": str(player_id),
                    "notification_type": notification_type,
                    "scheduled_for": scheduled_for.isoformat(),
                },
            )
            return {
                "ok": True,
                "skipped": True,
                "reason": "duplicate",
                "tokens": 0,
                "log_id": None,
                "payload": None,
            }

        payload = {"title": title, "body": body, "data": dict(data or {})}

        try:
            send_result = send_push_notification(
                str(player_uuid),
                title,
                body,
                data=payload["data"],
                db=session,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "daily_loop_push_unexpected_error",
                extra={"player_id": str(player_id), "notification_type": notification_type},
            )
            send_result = {
                "ok": False,
                "tokens": 0,
                "sent": 0,
                "failed": 0,
                "errors": [str(exc)],
            }

        tokens = int(send_result.get("tokens") or 0)
        sent = int(send_result.get("sent") or 0)
        failed = int(send_result.get("failed") or 0)
        errors = send_result.get("errors") or []

        if tokens == 0:
            status = "no_token"
        elif sent > 0 and failed == 0:
            status = "sent"
        elif sent > 0:
            status = "partial"
        else:
            status = "failed"

        log_row = PlayerNotificationLog(
            player_id=player_uuid,
            notification_type=notification_type,
            scheduled_for=scheduled_for,
            status=status,
            error_message="; ".join(str(e) for e in errors)[:1000] if errors else None,
        )
        session.add(log_row)
        try:
            session.commit()
            session.refresh(log_row)
        except Exception:
            session.rollback()
            logger.exception(
                "daily_loop_push_log_write_failed",
                extra={"player_id": str(player_id), "notification_type": notification_type},
            )
            return {
                "ok": False,
                "skipped": False,
                "reason": "log_write_failed",
                "tokens": tokens,
                "sent": sent,
                "failed": failed,
                "log_id": None,
                "payload": payload,
            }

        return {
            "ok": status in {"sent", "partial"},
            "skipped": False,
            "reason": status,
            "tokens": tokens,
            "sent": sent,
            "failed": failed,
            "log_id": str(log_row.id),
            "payload": payload,
            "status": status,
        }
    finally:
        if owns_session:
            session.close()
