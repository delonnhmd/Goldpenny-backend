"""Immutable business accounting ledger entries."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class BusinessLedgerEntry(Base):
    """Detailed inflow/outflow ledger for each business day operation."""

    __tablename__ = "business_ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("player_businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)

    category = Column(String(40), nullable=False)
    amount_xgp = Column(Numeric(14, 4), nullable=False)
    direction = Column(String(10), nullable=False)
    memo = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    business = relationship("PlayerBusiness", foreign_keys=[business_id])
