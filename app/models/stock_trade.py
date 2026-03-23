"""app/models/stock_trade.py — Step 9: Immutable trade audit log.

One row is appended for every completed buy or sell.  Rows are never updated or
deleted — this is a strict append-only ledger.

Fee accounting:
  BUY:  gross_amount = shares * price_per_share
        net_amount   = gross_amount + transaction_fee   (player pays gross + fee)
  SELL: gross_amount = shares * price_per_share
        net_amount   = gross_amount - transaction_fee   (player receives gross - fee)

balance_before / balance_after refer to player.cash (XGP) before and after.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class StockTrade(Base):
    """Append-only record of a completed stock trade."""

    __tablename__ = "stock_trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    player_id  = Column(UUID(as_uuid=True), nullable=False, index=True)
    stock_id   = Column(String(40), nullable=False, index=True)
    day_number = Column(Integer, nullable=False, index=True)

    # "buy" or "sell"
    trade_type = Column(String(10), nullable=False, index=True)

    shares          = Column(Integer, nullable=False)
    price_per_share = Column(Numeric(12, 4), nullable=False)
    gross_amount    = Column(Numeric(12, 4), nullable=False)
    transaction_fee = Column(Numeric(12, 4), nullable=False)
    net_amount      = Column(Numeric(12, 4), nullable=False)

    balance_before = Column(Numeric(12, 4), nullable=False)
    balance_after  = Column(Numeric(12, 4), nullable=False)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
