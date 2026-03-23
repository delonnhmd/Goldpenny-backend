"""Step 18: Daily career progression log — one immutable row per player per day."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class CareerProgressLog(Base):
    """Immutable daily record of career growth, skill delta, and certification progress."""

    __tablename__ = "career_progress_logs"

    __table_args__ = (
        UniqueConstraint("player_id", "day_number", name="uq_career_progress_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    day_number = Column(Integer, nullable=False, index=True)

    # ── Job snapshot ──────────────────────────────────────────────────────────
    job_key = Column(String(60), nullable=True)
    job_rank = Column(String(20), nullable=True)  # entry | intermediate | advanced

    # ── Skill movement ────────────────────────────────────────────────────────
    skill_before = Column(Numeric(8, 4), nullable=False, default=0.0)
    skill_after = Column(Numeric(8, 4), nullable=False, default=0.0)
    skill_delta = Column(Numeric(8, 4), nullable=False, default=0.0)

    # ── Performance ──────────────────────────────────────────────────────────
    performance_score = Column(Numeric(8, 4), nullable=False, default=0.0)
    trailing_performance_score = Column(Numeric(8, 4), nullable=False, default=0.0)

    # ── Promotion progress ────────────────────────────────────────────────────
    promotion_progress = Column(Numeric(8, 4), nullable=False, default=0.0)
    promotion_unlocked = Column(Boolean, nullable=False, default=False)

    # ── Certification ─────────────────────────────────────────────────────────
    certification_progress_days = Column(Integer, nullable=False, default=0)
    certification_completed = Column(Boolean, nullable=False, default=False)

    # ── Training ─────────────────────────────────────────────────────────────
    training_hours = Column(Numeric(6, 2), nullable=False, default=0.0)
    missed_training_hours = Column(Numeric(6, 2), nullable=False, default=0.0)

    # ── Debug ─────────────────────────────────────────────────────────────────
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
