"""Immutable daily player net worth snapshot."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerNetWorthSnapshot(Base):
    """One snapshot per player/day for wealth trend and allocation analysis."""

    __tablename__ = "player_net_worth_snapshots"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_player_net_worth_snapshot_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)

    cash_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    bank_savings_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    stock_market_value_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    business_value_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    inventory_value_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    total_assets_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    debt_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    net_worth_xgp = Column(Numeric(14, 2), nullable=False, default=0)

    allocation_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
