"""Step 29 commitment history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerCommitmentHistory(Base):
    """Immutable-ish commitment lifecycle row for audit and player history."""

    __tablename__ = "player_commitment_history"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "commitment_key",
            "start_day",
            name="uq_player_commitment_history_player_key_start_day",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    commitment_key = Column(String(80), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    description = Column(Text, nullable=False, default="")

    start_day = Column(Integer, nullable=False, index=True)
    target_end_day = Column(Integer, nullable=False)
    planned_duration_days = Column(Integer, nullable=False, default=0)
    start_date = Column(Date, nullable=True)
    target_end_date = Column(Date, nullable=True)

    status = Column(String(20), nullable=False, default="active")
    adherence_score = Column(Numeric(8, 4), nullable=False, default=0)
    momentum_score = Column(Numeric(8, 4), nullable=False, default=0)
    days_followed = Column(Integer, nullable=False, default=0)
    days_drifted = Column(Integer, nullable=False, default=0)

    completed_on_day = Column(Integer, nullable=True, index=True)
    completed_on_date = Column(Date, nullable=True)
    completion_summary = Column(Text, nullable=True)
    reward_summary = Column(Text, nullable=True)
    main_driver = Column(Text, nullable=True)

    feedback_trace_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])

