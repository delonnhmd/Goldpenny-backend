"""Per-job progression state for each player (safe-mode career track)."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerJobProgression(Base):
    __tablename__ = "player_job_progressions"
    __table_args__ = (
        UniqueConstraint("player_id", "job_key", name="uq_player_job_progression_player_job"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_key = Column(String(60), nullable=False, index=True)

    # Per-job progression track (independent from global player skill_level).
    skill_level = Column(Integer, nullable=False, default=1)
    xp_total = Column(Integer, nullable=False, default=0)
    xp = Column(Integer, nullable=False, default=0)  # XP inside current level band.
    xp_to_next_level = Column(Integer, nullable=False, default=100)
    promotion_tier = Column(String(30), nullable=False, default="Junior")
    shifts_completed = Column(Integer, nullable=False, default=0)

    last_worked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id], back_populates="job_progressions")
