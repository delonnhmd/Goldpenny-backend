"""Player-facing black swan event log.

Rows in this table are presentation-layer moments promoted from existing
economy/event data. They do not mutate the economy, businesses, or map state.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerBlackSwanEvent(Base):
    __tablename__ = "player_black_swan_event"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_player_black_swan_event_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(Integer, nullable=False, index=True)
    event_type = Column(String(60), nullable=False, index=True)
    title = Column(String(220), nullable=False)
    description = Column(Text, nullable=False)
    severity_score = Column(Numeric(10, 4), nullable=False)
    source_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("daily_economy_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payload_json = Column(Text, nullable=True)
    seen_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
