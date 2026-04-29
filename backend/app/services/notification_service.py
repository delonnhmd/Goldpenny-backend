from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.player_push_token import PlayerPushToken


logger = logging.getLogger("goldpenny.notifications")

EXPO_PUSH_SEND_URL = "https://exp.host/--/api/v2/push/send"


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
