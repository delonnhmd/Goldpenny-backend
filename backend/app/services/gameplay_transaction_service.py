"""Helpers for writing and reading player-facing gameplay transactions."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.gameplay_transaction import GameplayTransaction
from app.models.player import Player

MONEY_Q = Decimal("0.0001")


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _resolve_player_id(player: Player | UUID | str) -> UUID:
    if isinstance(player, Player):
        return player.id
    if isinstance(player, UUID):
        return player
    return UUID(str(player))


def record_gameplay_transaction(
    db: Session,
    *,
    player: Player | UUID | str,
    day: int,
    transaction_type: str,
    category: str,
    amount: Decimal | float | int,
    description: str,
) -> GameplayTransaction:
    normalized_type = str(transaction_type or "").strip().lower() or "expense"
    normalized_amount = _q4(_d(amount))
    if normalized_type == "income":
        normalized_amount = abs(normalized_amount)
    else:
        normalized_type = "expense"
        normalized_amount = -abs(normalized_amount)

    row = GameplayTransaction(
        player_id=_resolve_player_id(player),
        day=max(1, int(day)),
        type=normalized_type,
        category=str(category or "").strip().lower() or "general",
        amount=normalized_amount,
        description=str(description or "").strip() or "Gameplay transaction",
    )
    db.add(row)
    return row


def list_gameplay_transactions_for_day(
    db: Session,
    *,
    player: Player | UUID | str,
    day: int,
) -> list[GameplayTransaction]:
    return (
        db.query(GameplayTransaction)
        .filter(
            GameplayTransaction.player_id == _resolve_player_id(player),
            GameplayTransaction.day == max(1, int(day)),
        )
        .order_by(GameplayTransaction.timestamp.asc(), GameplayTransaction.id.asc())
        .all()
    )
