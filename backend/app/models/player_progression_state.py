"""Step 26 progression state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerProgressionState(Base):
    """Mutable progression state for one player."""

    __tablename__ = "player_progression_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_progression_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    current_day = Column(Integer, nullable=False, default=1)
    current_week_start_day = Column(Integer, nullable=False, default=1)
    current_week_end_day = Column(Integer, nullable=False, default=7)
    week_start_debt_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    week_start_cash_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    last_goal_refresh_day = Column(Integer, nullable=True)
    last_mission_refresh_week_start_day = Column(Integer, nullable=True)
    last_progress_evaluated_day = Column(Integer, nullable=True)

    login_streak_current = Column(Integer, nullable=False, default=0)
    login_streak_best = Column(Integer, nullable=False, default=0)
    login_streak_last_day = Column(Integer, nullable=True)

    productive_day_streak_current = Column(Integer, nullable=False, default=0)
    productive_day_streak_best = Column(Integer, nullable=False, default=0)
    productive_day_streak_last_day = Column(Integer, nullable=True)

    positive_cash_flow_streak_current = Column(Integer, nullable=False, default=0)
    positive_cash_flow_streak_best = Column(Integer, nullable=False, default=0)
    positive_cash_flow_streak_last_day = Column(Integer, nullable=True)

    training_streak_current = Column(Integer, nullable=False, default=0)
    training_streak_best = Column(Integer, nullable=False, default=0)
    training_streak_last_day = Column(Integer, nullable=True)

    business_consistency_streak_current = Column(Integer, nullable=False, default=0)
    business_consistency_streak_best = Column(Integer, nullable=False, default=0)
    business_consistency_streak_last_day = Column(Integer, nullable=True)

    low_distress_streak_current = Column(Integer, nullable=False, default=0)
    low_distress_streak_best = Column(Integer, nullable=False, default=0)
    low_distress_streak_last_day = Column(Integer, nullable=True)

    recently_completed_json = Column(Text, nullable=True)
    reward_trace_json = Column(Text, nullable=True)
    last_action_digest_json = Column(Text, nullable=True)
    reward_guard_flag = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
