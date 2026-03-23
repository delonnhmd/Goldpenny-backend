"""Step 37 rolling consumer borrowing state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerBorrowingState(Base):
    """Rolling per-player borrowing access and dependence metrics."""

    __tablename__ = "player_borrowing_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_borrowing_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    borrowing_access_score = Column(Numeric(8, 4), nullable=False, default=0)
    credit_access_tier = Column(String(24), nullable=False, default="locked")
    emergency_liquidity_label = Column(String(24), nullable=False, default="stable")
    max_safe_borrow_amount_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    estimated_risk_pricing_band = Column(String(24), nullable=False, default="unavailable")
    recent_distress_penalty = Column(Numeric(8, 4), nullable=False, default=0)

    active_loan_count = Column(Integer, nullable=False, default=0)
    repeat_borrowing_count_30d = Column(Integer, nullable=False, default=0)
    dependence_risk_score = Column(Numeric(8, 4), nullable=False, default=0)

    debug_json = Column(Text, nullable=True)
    last_updated_on = Column(Integer, nullable=True, index=True)
    last_updated_date = Column(Date, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
