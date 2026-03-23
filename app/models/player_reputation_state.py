"""Step 40 rolling per-player reputation and trust profile state."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerReputationState(Base):
    """Rolling per-player reputation profile — one row per player (upsert on update)."""

    __tablename__ = "player_reputation_states"
    __table_args__ = (UniqueConstraint("player_id", name="uq_prs_player"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- composite scores (0–100) ---
    reputation_score = Column(Numeric(8, 4), nullable=False, default=50)
    trust_score = Column(Numeric(8, 4), nullable=False, default=50)
    financial_reliability_score = Column(Numeric(8, 4), nullable=False, default=50)
    work_reliability_score = Column(Numeric(8, 4), nullable=False, default=50)
    business_reliability_score = Column(Numeric(8, 4), nullable=False, default=50)
    opportunity_readiness_score = Column(Numeric(8, 4), nullable=False, default=50)

    # --- labels ---
    overall_trust_label = Column(String(20), nullable=False, default="mixed")
    reputation_direction = Column(String(20), nullable=False, default="stable")
    # improving / stable / weakening / recovering

    # --- trust signals ---
    payment_signal_label = Column(String(20), nullable=False, default="mixed")
    borrowing_signal_label = Column(String(20), nullable=False, default="mixed")
    work_signal_label = Column(String(20), nullable=False, default="mixed")
    business_signal_label = Column(String(20), nullable=False, default="mixed")
    stability_signal_label = Column(String(20), nullable=False, default="mixed")

    # --- opportunity access ---
    opportunity_access_label = Column(String(20), nullable=False, default="standard")
    # restricted / limited / standard / elevated / preferred

    # --- advisory ---
    top_reputation_driver = Column(String(100), nullable=True)
    top_reputation_drag = Column(String(100), nullable=True)
    practical_actions_json = Column(Text, nullable=True)
    planning_insights_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    # --- time tracking ---
    last_updated_on = Column(Integer, nullable=True)
    last_updated_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
