"""Step 18: Player career state — per-player (not per-day) progression record."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerCareer(Base):
    """Mutable career state for a player. One row per player, upserted on each career event."""

    __tablename__ = "player_career_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Job identity ──────────────────────────────────────────────────────────
    current_job_key = Column(String(60), nullable=True)
    current_job_rank = Column(String(20), nullable=False, default="entry")  # entry | intermediate | advanced
    current_job_skill = Column(Numeric(8, 4), nullable=False, default=0.0)

    # ── Days-in-job counter (reset on job switch) ─────────────────────────────
    total_days_worked_in_job = Column(Integer, nullable=False, default=0)

    # ── Performance tracking ──────────────────────────────────────────────────
    trailing_performance_score = Column(Numeric(8, 4), nullable=False, default=0.0)
    promotion_eligible = Column(Boolean, nullable=False, default=False)

    # ── Certification ─────────────────────────────────────────────────────────
    certification_track_key = Column(String(60), nullable=True)
    certification_progress_days = Column(Integer, nullable=False, default=0)
    certification_required_days = Column(Integer, nullable=False, default=0)
    certification_completed = Column(Boolean, nullable=False, default=False)

    # ── Promotion history ─────────────────────────────────────────────────────
    last_promotion_day = Column(Integer, nullable=True)  # in-game day number

    # ── Debug ─────────────────────────────────────────────────────────────────
    career_debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
