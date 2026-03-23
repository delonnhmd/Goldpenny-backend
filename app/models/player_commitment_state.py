"""Step 29 commitment state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerCommitmentState(Base):
    """Mutable commitment state for one player (single active slot)."""

    __tablename__ = "player_commitment_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_commitment_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    commitment_key = Column(String(80), nullable=True, index=True)
    title = Column(String(180), nullable=True)
    description = Column(Text, nullable=True)

    start_day = Column(Integer, nullable=True, index=True)
    target_end_day = Column(Integer, nullable=True, index=True)
    planned_duration_days = Column(Integer, nullable=False, default=0)
    start_date = Column(Date, nullable=True)
    target_end_date = Column(Date, nullable=True)

    status = Column(String(20), nullable=False, default="inactive")  # inactive | active | completed | failed | cancelled | expired | replaced
    adherence_score = Column(Numeric(8, 4), nullable=False, default=0)
    momentum_score = Column(Numeric(8, 4), nullable=False, default=0)
    days_followed = Column(Integer, nullable=False, default=0)
    days_drifted = Column(Integer, nullable=False, default=0)
    last_evaluated_on = Column(Integer, nullable=True)

    completion_summary = Column(Text, nullable=True)
    reward_summary = Column(Text, nullable=True)
    initial_context_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])

