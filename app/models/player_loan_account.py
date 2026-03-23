"""Step 37 player consumer loan account model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerLoanAccount(Base):
    """Tracks one accepted borrowing offer and its rolling repayment state."""

    __tablename__ = "player_loan_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    offer_key = Column(String(80), nullable=False, index=True)
    offer_family = Column(String(40), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)

    principal_original_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    principal_outstanding_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    apr_pct = Column(Numeric(8, 4), nullable=False, default=0)
    fee_amount_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    term_days = Column(Integer, nullable=False, default=30)
    days_elapsed = Column(Integer, nullable=False, default=0)
    days_remaining = Column(Integer, nullable=False, default=30)
    scheduled_daily_payment_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    current_due_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    missed_payment_count = Column(Integer, nullable=False, default=0)
    delinquency_stage = Column(String(20), nullable=False, default="current")
    rollover_allowed = Column(Boolean, nullable=False, default=False)

    accepted_on_day = Column(Integer, nullable=False, index=True)
    accepted_on_date = Column(Date, nullable=True, index=True)
    last_payment_day = Column(Integer, nullable=True, index=True)
    last_payment_amount_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    closed_on_day = Column(Integer, nullable=True, index=True)
    closed_on_date = Column(Date, nullable=True, index=True)

    account_meta_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
