"""Step 26 goal/mission history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerGoalHistory(Base):
    """Daily/weekly progression entry with deterministic upsert keys."""

    __tablename__ = "player_goal_history"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "goal_scope",
            "goal_key",
            "day_number",
            name="uq_player_goal_history_scope_goal_day",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    as_of_date = Column(Date, nullable=True, index=True)
    day_number = Column(Integer, nullable=False, index=True)
    week_start_day = Column(Integer, nullable=True, index=True)
    week_end_day = Column(Integer, nullable=True)

    goal_scope = Column(String(20), nullable=False, index=True)  # daily | weekly | streak
    goal_key = Column(String(80), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="not_started")
    progress_current = Column(Numeric(14, 4), nullable=False, default=0)
    progress_target = Column(Numeric(14, 4), nullable=False, default=1)
    reward_summary = Column(Text, nullable=True)
    urgency = Column(String(20), nullable=True)
    expires_on = Column(Date, nullable=True)
    category = Column(String(40), nullable=True)

    debug_json = Column(Text, nullable=True)
    reward_applied_json = Column(Text, nullable=True)
    recovery_actions_json = Column(Text, nullable=True)

    credited_flag = Column(Boolean, nullable=False, default=False)
    credited_on_day = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
