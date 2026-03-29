"""Immutable debt and credit pressure log written once per player/day."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class DebtCreditLog(Base):
    """Daily debt servicing and credit score movement audit row."""

    __tablename__ = "debt_credit_logs"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_debt_credit_log_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)

    opening_debt_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    payment_due_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    payment_made_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    interest_added_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    ending_debt_xgp = Column(Numeric(14, 2), nullable=False, default=0)

    payment_status = Column(String(20), nullable=False, default="no_debt")

    opening_credit_score = Column(Integer, nullable=False)
    credit_score_change = Column(Integer, nullable=False, default=0)
    ending_credit_score = Column(Integer, nullable=False)

    delinquency_flag = Column(Boolean, nullable=False, default=False)
    notes_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
