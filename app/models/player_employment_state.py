"""Per-player employment snapshot table."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerEmploymentState(Base):
    __tablename__ = "player_employment_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)
    current_job_code = Column(
        String(60),
        ForeignKey("job_definitions.job_code", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    skill_level = Column(Integer, nullable=False, default=1)
    monthly_pay_xgp = Column(Numeric(14, 2), nullable=False, default=0)
    employed_flag = Column(Boolean, nullable=False, default=True)
    layoff_risk_pct = Column(Numeric(6, 2), nullable=False, default=0)
    productivity_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    # Step 16: job-market pressure + event tracking
    job_status = Column(String(20), nullable=False, default="employed")  # employed | laid_off | seeking
    promotion_eligible_flag = Column(Boolean, nullable=False, default=False)
    promotion_count = Column(Integer, nullable=False, default=0)
    last_raise_pct = Column(Numeric(6, 2), nullable=False, default=0)
    last_employment_event = Column(String(40), nullable=True)
    opportunity_score = Column(Numeric(8, 4), nullable=False, default=1.0)
    layoff_event_flag = Column(Boolean, nullable=False, default=False)
    promotion_chance_pct = Column(Numeric(6, 2), nullable=False, default=0)
    wage_adjustment_pct = Column(Numeric(6, 2), nullable=False, default=0)
    employment_evaluated_flag = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", back_populates="employment_states", foreign_keys=[player_id])
    job_definition = relationship("JobDefinition", foreign_keys=[current_job_code])
