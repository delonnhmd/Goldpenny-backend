"""Unified per-player transaction ledger for gameplay cash movements."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerTransactionLog(Base):
    """Immutable cash movement ledger used for audit, debugging, and UI history."""

    __tablename__ = "player_transaction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=True, index=True)
    transaction_type = Column(String(40), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True, default="general")
    asset_symbol = Column(String(40), nullable=True, index=True)
    quantity = Column(Numeric(14, 4), nullable=True)
    unit_price = Column(Numeric(14, 4), nullable=True)
    gross_amount = Column(Numeric(14, 4), nullable=False, default=0)
    fee_amount = Column(Numeric(14, 4), nullable=False, default=0)
    net_cash_delta = Column(Numeric(14, 4), nullable=False, default=0)
    resulting_cash_balance = Column(Numeric(14, 4), nullable=False, default=0)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    player = relationship("Player", foreign_keys=[player_id], back_populates="transaction_logs")
