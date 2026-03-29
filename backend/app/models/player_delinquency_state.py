"""Step 36 player delinquency rolling state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerDelinquencyState(Base):
    """Rolling per-player delinquency stage and payment-pressure counters."""

    __tablename__ = "player_delinquency_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_delinquency_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    current_delinquency_stage = Column(String(20), nullable=False, default="current", index=True)
    missed_payment_count_30d = Column(Integer, nullable=False, default=0)
    late_payment_count_30d = Column(Integer, nullable=False, default=0)
    days_under_payment_stress = Column(Integer, nullable=False, default=0)
    last_missed_obligation_type = Column(String(40), nullable=True)

    credit_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    financial_distress_score = Column(Numeric(8, 4), nullable=False, default=0)

    stage_debug_json = Column(Text, nullable=True)
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

