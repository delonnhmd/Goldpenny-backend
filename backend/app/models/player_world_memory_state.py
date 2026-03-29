"""Step 30 world memory state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerWorldMemoryState(Base):
    """Rolling player-specific world memory snapshot."""

    __tablename__ = "player_world_memory_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_world_memory_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    region_key = Column(String(40), nullable=False, default="suburban", index=True)
    memory_window_start_day = Column(Integer, nullable=False, default=1, index=True)
    memory_window_end_day = Column(Integer, nullable=False, default=1, index=True)
    memory_window_start = Column(Date, nullable=True)
    memory_window_end = Column(Date, nullable=True)

    macro_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    commute_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    business_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    life_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    opportunity_score = Column(Numeric(8, 4), nullable=False, default=0)

    dominant_patterns_json = Column(Text, nullable=True)
    narrative_state_json = Column(Text, nullable=True)
    local_pressure_json = Column(Text, nullable=True)
    player_pattern_json = Column(Text, nullable=True)
    region_memory_json = Column(Text, nullable=True)

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
