"""Step 30 world pattern history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerWorldPatternHistory(Base):
    """Rolling pattern lifecycle rows (active/fading/resolved)."""

    __tablename__ = "player_world_pattern_history"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "pattern_key",
            "first_seen_on_day",
            name="uq_player_world_pattern_hist_player_key_first_seen",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pattern_key = Column(String(90), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True)
    title = Column(String(180), nullable=False)

    first_seen_on_day = Column(Integer, nullable=False, index=True)
    first_seen_on_date = Column(Date, nullable=True, index=True)
    last_seen_on_day = Column(Integer, nullable=False, index=True)
    last_seen_on_date = Column(Date, nullable=True, index=True)

    consecutive_days = Column(Integer, nullable=False, default=1)
    persistence_score = Column(Numeric(8, 4), nullable=False, default=0)
    severity = Column(String(20), nullable=False, default="low")
    direction = Column(String(20), nullable=False, default="stable")
    status = Column(String(20), nullable=False, default="active")  # active | fading | resolved

    summary_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)
    last_updated_on = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
