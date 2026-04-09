"""Auditable salary posting record for completed main-job shifts."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class ShiftSalaryAuditLog(Base):
    __tablename__ = "shift_salary_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_number = Column(Integer, nullable=False, index=True)
    shift_token = Column(String(200), nullable=False, unique=True, index=True)
    shift_id = Column(String(80), nullable=True, index=True)
    job_key = Column(String(120), nullable=False, index=True)
    job_display_name = Column(String(120), nullable=False, default="")
    shift_started_at = Column(DateTime(timezone=True), nullable=True)
    shift_ends_at = Column(DateTime(timezone=True), nullable=True)
    shift_completed_at = Column(DateTime(timezone=True), nullable=True)
    shift_type = Column(String(40), nullable=True)
    shift_number = Column(Integer, nullable=False, default=1)
    hours_worked = Column(Integer, nullable=False, default=0)
    trigger = Column(String(80), nullable=True)
    payment_status = Column(String(20), nullable=False, default="pending", index=True)
    failure_reason = Column(Text, nullable=True)

    base_monthly_salary = Column(Numeric(14, 4), nullable=False, default=0)
    pay_snapshot_used = Column(Numeric(14, 4), nullable=False, default=0)
    base_hourly_pay = Column(Numeric(14, 4), nullable=False, default=0)
    productivity_multiplier = Column(Numeric(8, 4), nullable=False, default=1)
    income_multiplier = Column(Numeric(8, 4), nullable=False, default=1)
    job_level_multiplier = Column(Numeric(8, 4), nullable=False, default=1)
    gross_shift_pay = Column(Numeric(14, 4), nullable=False, default=0)
    final_salary_paid = Column(Numeric(14, 4), nullable=False, default=0)

    xp_gained = Column(Integer, nullable=False, default=0)
    stress_change = Column(Integer, nullable=False, default=0)
    health_change = Column(Integer, nullable=False, default=0)
    fatigue_change = Column(Numeric(8, 4), nullable=False, default=0)
    overtime_penalty_applied = Column(Boolean, nullable=False, default=False)

    salary_transaction_id = Column(String(80), nullable=True, index=True)
    xgp_transaction_id = Column(String(80), nullable=True, index=True)
    player_transaction_log_id = Column(String(80), nullable=True, index=True)
    salary_posted_at = Column(DateTime(timezone=True), nullable=True)

    cash_before = Column(Numeric(14, 4), nullable=False, default=0)
    cash_after = Column(Numeric(14, 4), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
