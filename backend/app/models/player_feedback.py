"""Step 70 — Player feedback submitted from in-game feedback sheet.

Captured after Day 1 / Day 2 settlement.  rating is 1–5.
response_* fields hold short free-text answers to the three
fixed UX questions (confusing, hard, interesting).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerFeedback(Base):
    __tablename__ = "player_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(64), nullable=True)
    game_day = Column(Integer, nullable=False, default=1)
    rating = Column(Integer, nullable=False)  # 1–5
    response_confusing = Column(Text, nullable=True)
    response_hard = Column(Text, nullable=True)
    response_interesting = Column(Text, nullable=True)
    cohort_tag = Column(String(40), nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
