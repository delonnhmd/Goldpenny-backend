"""Step 35 personal shock profile state."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerShockState(Base):
    """Rolling per-player shock-risk profile and latest event memory."""

    __tablename__ = "player_shock_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_shock_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    shock_risk_score = Column(Numeric(8, 4), nullable=False, default=0)
    financial_fragility_score = Column(Numeric(8, 4), nullable=False, default=0)
    health_fragility_score = Column(Numeric(8, 4), nullable=False, default=0)
    work_disruption_risk_score = Column(Numeric(8, 4), nullable=False, default=0)
    recovery_capacity_score = Column(Numeric(8, 4), nullable=False, default=0)

    recent_pressure_direction = Column(String(20), nullable=False, default="stable")
    recent_negative_streak = Column(Integer, nullable=False, default=0)
    recent_recovery_support = Column(Integer, nullable=False, default=0)

    last_event_key = Column(String(80), nullable=True)
    last_event_family = Column(String(40), nullable=True)
    last_event_severity = Column(String(20), nullable=True)
    last_event_day = Column(Integer, nullable=True, index=True)
    last_event_date = Column(Date, nullable=True, index=True)

    profile_debug_json = Column(Text, nullable=True)

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

