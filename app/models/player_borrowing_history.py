"""Step 37 borrowing history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerBorrowingHistory(Base):
    """Immutable borrowing-related history rows for auditability and memory."""

    __tablename__ = "player_borrowing_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_number = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True, index=True)
    event_type = Column(String(40), nullable=False, index=True)

    offer_key = Column(String(80), nullable=True)
    offer_family = Column(String(40), nullable=True)
    loan_account_id = Column(UUID(as_uuid=True), ForeignKey("player_loan_accounts.id", ondelete="SET NULL"), nullable=True, index=True)

    principal_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    fee_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    apr_pct = Column(Numeric(8, 4), nullable=False, default=0)
    term_days = Column(Integer, nullable=False, default=0)
    estimated_total_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    cash_delta_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_delta_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    obligation_delta_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    status_after = Column(String(20), nullable=False, default="active")

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
    loan_account = relationship("PlayerLoanAccount", foreign_keys=[loan_account_id])
