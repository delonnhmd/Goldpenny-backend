"""Step 40 append-only per-player reputation trend history."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerReputationHistory(Base):
    """One row per player per game-day — append-only reputation trend log."""

    __tablename__ = "player_reputation_history"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_prh_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True)

    # --- scores snapshot ---
    reputation_score = Column(Numeric(8, 4), nullable=False, default=50)
    trust_score = Column(Numeric(8, 4), nullable=False, default=50)
    financial_reliability_score = Column(Numeric(8, 4), nullable=False, default=50)
    work_reliability_score = Column(Numeric(8, 4), nullable=False, default=50)
    business_reliability_score = Column(Numeric(8, 4), nullable=False, default=50)
    opportunity_readiness_score = Column(Numeric(8, 4), nullable=False, default=50)

    # --- phase labels ---
    overall_trust_label = Column(String(20), nullable=False, default="mixed")
    opportunity_access_label = Column(String(20), nullable=False, default="standard")
    reputation_direction = Column(String(20), nullable=False, default="stable")

    # --- flags ---
    false_growth_suppressed = Column(Boolean, nullable=False, default=False)
    delinquency_drag_active = Column(Boolean, nullable=False, default=False)
    recovery_boost_active = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
