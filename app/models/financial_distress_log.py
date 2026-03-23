"""Daily player financial distress audit log (Step 20)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class FinancialDistressLog(Base):
    """One idempotent distress-resolution row per player/day."""

    __tablename__ = "financial_distress_logs"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_financial_distress_log_player_day"),
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

    debt_payment_due_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_payment_paid_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_payment_missed = Column(Boolean, nullable=False, default=False)
    late_fee_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    accrued_interest_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    credit_score_before = Column(Integer, nullable=False, default=650)
    credit_score_after = Column(Integer, nullable=False, default=650)
    credit_score_delta = Column(Integer, nullable=False, default=0)

    distress_state_before = Column(String(20), nullable=False, default="stable")
    distress_state_after = Column(String(20), nullable=False, default="stable")
    distress_score_before = Column(Numeric(8, 4), nullable=False, default=0)
    distress_score_after = Column(Numeric(8, 4), nullable=False, default=0)

    borrowing_cost_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    opportunity_access_penalty = Column(Numeric(8, 4), nullable=False, default=0.0)
    business_risk_penalty = Column(Numeric(8, 4), nullable=False, default=0.0)
    career_progress_penalty = Column(Numeric(8, 4), nullable=False, default=0.0)

    distress_driver_json = Column(Text, nullable=True)
    recovery_actions_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
