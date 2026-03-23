"""Step 36 player payment outcome history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerPaymentHistory(Base):
    """One deterministic payment-outcome row per player/day."""

    __tablename__ = "player_payment_history"
    __table_args__ = (
        UniqueConstraint("player_id", "day_number", name="uq_player_payment_history_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_number = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True, index=True)

    required_monthly_obligation_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    required_daily_burden_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_minimum_obligation_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    housing_obligation_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_overhead_obligation_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    insurance_basic_obligation_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    obligation_load_ratio = Column(Numeric(8, 4), nullable=False, default=0)
    liquidity_buffer_days = Column(Numeric(8, 4), nullable=False, default=0)
    payment_pressure_label = Column(String(20), nullable=False, default="manageable")

    full_pay_feasible = Column(Boolean, nullable=False, default=False)
    partial_pay_feasible = Column(Boolean, nullable=False, default=False)
    payment_outcome = Column(String(20), nullable=False, default="paid_full", index=True)
    total_due_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    total_paid_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    unpaid_amount_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    late_fee_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    stress_impact_delta = Column(Numeric(8, 4), nullable=False, default=0)

    delinquency_stage_before = Column(String(20), nullable=False, default="current")
    delinquency_stage_after = Column(String(20), nullable=False, default="current")
    credit_score_before = Column(Integer, nullable=False, default=650)
    credit_score_after = Column(Integer, nullable=False, default=650)
    credit_score_delta = Column(Integer, nullable=False, default=0)
    survival_status_label = Column(String(20), nullable=False, default="current")

    due_obligations_json = Column(Text, nullable=True)
    practical_actions_json = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])

