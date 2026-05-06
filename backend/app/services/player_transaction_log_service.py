"""Helpers for writing and reading unified player transaction history."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.player_transaction_log import PlayerTransactionLog

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


def player_transaction_logs_table_available(db: Session) -> bool:
    table_name = PlayerTransactionLog.__tablename__
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


def record_player_transaction(
    db: Session,
    *,
    player: Player | UUID | str,
    day: int | None,
    transaction_type: str,
    category: str,
    asset_symbol: str | None = None,
    quantity: Decimal | float | int | None = None,
    unit_price: Decimal | float | int | None = None,
    gross_amount: Decimal | float | int = 0,
    fee_amount: Decimal | float | int = 0,
    net_cash_delta: Decimal | float | int = 0,
    resulting_cash_balance: Decimal | float | int = 0,
    metadata: dict[str, Any] | None = None,
) -> PlayerTransactionLog:
    payload = json.dumps(metadata or {})
    row = PlayerTransactionLog(
        player_id=_resolve_player_id(player),
        day=int(day) if day is not None else None,
        transaction_type=str(transaction_type or "").strip().lower() or "unknown",
        category=str(category or "").strip().lower() or "general",
        asset_symbol=(str(asset_symbol or "").strip().upper() or None),
        quantity=_q4(_d(quantity)) if quantity is not None else None,
        unit_price=_q4(_d(unit_price)) if unit_price is not None else None,
        gross_amount=_q4(_d(gross_amount)),
        fee_amount=_q4(_d(fee_amount)),
        net_cash_delta=_q4(_d(net_cash_delta)),
        resulting_cash_balance=_q4(_d(resulting_cash_balance)),
        metadata_json=payload,
    )
    if not player_transaction_logs_table_available(db):
        return row
    db.add(row)
    return row


def list_recent_player_transactions(
    db: Session,
    *,
    player: Player | UUID | str,
    limit: int = 50,
) -> list[PlayerTransactionLog]:
    if not player_transaction_logs_table_available(db):
        return []
    safe_limit = max(1, min(int(limit), 200))
    return (
        db.query(PlayerTransactionLog)
        .filter(PlayerTransactionLog.player_id == _resolve_player_id(player))
        .order_by(PlayerTransactionLog.created_at.desc())
        .limit(safe_limit)
        .all()
    )
