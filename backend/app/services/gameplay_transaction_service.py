"""Helpers for writing and reading player-facing gameplay transactions."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import inspect
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


def gameplay_transactions_table_available(db: Session) -> bool:
    table_name = GameplayTransaction.__tablename__
    table_cache = db.info.setdefault("_table_exists_cache", {})
    cached = table_cache.get(table_name)
    if cached is not None:
        return bool(cached)
    try:
        available = bool(inspect(db.connection()).has_table(table_name))
    except Exception:
        available = True
    table_cache[table_name] = available
    return available


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
    if not gameplay_transactions_table_available(db):
        return row
    db.add(row)
    return row


def list_gameplay_transactions_for_day(
    db: Session,
    *,
    player: Player | UUID | str,
    day: int,
) -> list[GameplayTransaction]:
    if not gameplay_transactions_table_available(db):
        return []
    return (
        db.query(GameplayTransaction)
        .filter(
            GameplayTransaction.player_id == _resolve_player_id(player),
            GameplayTransaction.day == max(1, int(day)),
        )
        .order_by(GameplayTransaction.timestamp.asc(), GameplayTransaction.id.asc())
        .all()
    )
