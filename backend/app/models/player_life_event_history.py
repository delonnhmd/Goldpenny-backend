"""Step 35 personal life-event history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerLifeEventHistory(Base):
    """One personal life event resolution row per player/day."""

    __tablename__ = "player_life_event_history"
    __table_args__ = (
        UniqueConstraint("player_id", "day_number", name="uq_player_life_event_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_number = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True, index=True)

    event_key = Column(String(80), nullable=False, index=True)
    event_family = Column(String(40), nullable=False, index=True)
    headline = Column(String(220), nullable=False)
    severity_band = Column(String(20), nullable=False, index=True)

    cash_impact_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    stress_impact_delta = Column(Numeric(8, 4), nullable=False, default=0)
    health_impact_delta = Column(Numeric(8, 4), nullable=False, default=0)
    time_impact_hours = Column(Numeric(8, 4), nullable=False, default=0)
    work_income_impact = Column(Numeric(8, 4), nullable=False, default=0)
    business_impact = Column(Numeric(8, 4), nullable=False, default=0)
    side_income_impact = Column(Numeric(8, 4), nullable=False, default=0)
    duration_days = Column(Integer, nullable=False, default=0)
    recovery_hint = Column(Text, nullable=True)

    trigger_tags_json = Column(Text, nullable=True)
    impact_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])

