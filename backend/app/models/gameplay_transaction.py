"""Dedicated day-level ledger for player-facing gameplay cash activity."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class GameplayTransaction(Base):
    """Immutable player-facing ledger row for one gameplay income or expense."""

    __tablename__ = "gameplay_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True)
    amount = Column(Numeric(14, 4), nullable=False, default=0)
    description = Column(Text, nullable=False, default="")
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    player = relationship("Player", foreign_keys=[player_id], back_populates="gameplay_transactions")
