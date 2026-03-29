"""Monthly reward accounting record per player per month."""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RewardLedger(Base):
    __tablename__ = "reward_ledgers"
    __table_args__ = (
        UniqueConstraint("player_id", "month_key", name="uq_reward_ledger_player_month"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    month_key = Column(String(7), nullable=False, index=True)  # "YYYY-MM"

    # ── Monthly activity metrics ──────────────────────────────────────────────
    days_active = Column(Integer, nullable=False, default=0)
    total_work_actions = Column(Integer, nullable=False, default=0)
    total_main_job_hours = Column(Integer, nullable=False, default=0)
    total_side_job_hours = Column(Integer, nullable=False, default=0)
    total_income_earned = Column(Numeric(14, 2), nullable=False, default=0)
    total_food_purchased = Column(Integer, nullable=False, default=0)
    total_food_consumed = Column(Integer, nullable=False, default=0)

    # ── Vitals averages ───────────────────────────────────────────────────────
    average_health = Column(Float, nullable=False, default=0.0)
    average_stress = Column(Float, nullable=False, default=0.0)
    average_fatigue = Column(Float, nullable=False, default=0.0)

    # ── Sub-scores (each 0–100) ───────────────────────────────────────────────
    consistency_score = Column(Float, nullable=False, default=0.0)
    survival_score = Column(Float, nullable=False, default=0.0)
    productivity_score = Column(Float, nullable=False, default=0.0)
    anti_exploit_score = Column(Float, nullable=False, default=100.0)

    # ── Reward points ─────────────────────────────────────────────────────────
    raw_reward_points = Column(Float, nullable=False, default=0.0)
    approved_reward_points = Column(Float, nullable=False, default=0.0)

    # ── Token conversion ──────────────────────────────────────────────────────
    token_conversion_rate = Column(Float, nullable=False, default=0.10)
    estimated_token_amount = Column(Float, nullable=False, default=0.0)
    monthly_cap_applied = Column(Boolean, nullable=False, default=False)

    # ── Status ────────────────────────────────────────────────────────────────
    eligibility_status = Column(String(20), nullable=False, default="pending")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
