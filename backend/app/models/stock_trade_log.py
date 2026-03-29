"""Core immutable stock trade ledger table."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base
from app.models.enums import TradeSide


class StockTradeLog(Base):
    __tablename__ = "stock_trade_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    side = Column(
        Enum(TradeSide, name="trade_side_enum", native_enum=False, length=10),
        nullable=False,
        index=True,
    )

    shares = Column(Integer, nullable=False)
    price_per_share = Column(Numeric(14, 4), nullable=False)
    gross_amount_xgp = Column(Numeric(14, 4), nullable=False)
    fee_amount_xgp = Column(Numeric(14, 4), nullable=False)
    net_amount_xgp = Column(Numeric(14, 4), nullable=False)
    realized_pnl_xgp = Column(Numeric(14, 4), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", back_populates="stock_trade_logs", foreign_keys=[player_id])

