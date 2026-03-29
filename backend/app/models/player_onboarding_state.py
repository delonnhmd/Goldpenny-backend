"""Step 31 onboarding state model for first-time user funnel progress."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerOnboardingState(Base):
    """Persistent onboarding state for progressive first-session reveal."""

    __tablename__ = "player_onboarding_states"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_player_onboarding_state_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    onboarding_status = Column(String(20), nullable=False, default="not_started")
    current_step_key = Column(String(80), nullable=True)
    current_step_index = Column(Integer, nullable=False, default=1)

    started_on = Column(Date, nullable=True)
    completed_on = Column(Date, nullable=True)
    skipped_on = Column(Date, nullable=True)
    last_guidance_shown_on = Column(Date, nullable=True)

    visible_modules_json = Column(Text, nullable=True)
    unlocked_modules_json = Column(Text, nullable=True)
    completed_step_keys_json = Column(Text, nullable=True)

    first_session_day_count = Column(Integer, nullable=False, default=0)
    debug_meta = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
