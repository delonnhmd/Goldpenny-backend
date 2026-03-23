"""Immutable daily economy brief row for player-facing narrative."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class DailyBriefLog(Base):
    """Per-player daily brief with deterministic narrative fields."""

    __tablename__ = "daily_brief_logs"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_daily_brief_log_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)

    headline = Column(String(220), nullable=False)
    summary = Column(Text, nullable=False)

    macro_tags_json = Column(Text, nullable=True)
    player_impact_json = Column(Text, nullable=True)
    action_hints_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
