"""Step 35 personal recovery window state."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerRecoveryState(Base):
    """Active personal recovery modifiers that persist across days."""

    __tablename__ = "player_recovery_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_recovery_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recovery_days_remaining = Column(Integer, nullable=False, default=0)
    temporary_stress_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    temporary_health_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    temporary_income_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    temporary_business_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    temporary_time_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    recovery_status_label = Column(String(20), nullable=False, default="stable")

    source_event_key = Column(String(80), nullable=True)
    source_event_severity = Column(String(20), nullable=True)
    last_applied_day = Column(Integer, nullable=True, index=True)
    next_expire_day = Column(Integer, nullable=True, index=True)
    recovery_debug_json = Column(Text, nullable=True)

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

