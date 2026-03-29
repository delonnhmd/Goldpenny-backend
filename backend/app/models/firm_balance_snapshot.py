"""app/models/firm_balance_snapshot.py — Step 14: Daily firm balance sheet.

One snapshot is created per firm per in-game day by the firm engine.
This is the firm equivalent of PlayerDailyState — a daily financial position
record used for trend analysis, distress detection, and future UI charting.

equity_estimate = cash + inventory_value + receivables - payables - debt

runway_days = floor(cash / avg_daily_overhead)
  Null if overhead = 0 or the firm has fewer than 2 ledger days of history.
  When runway_days < 5, distress_level escalation should be reviewed.

All monetary fields are Numeric(14,2) to support large NPC firm balances
without overflow or precision loss.

The unique constraint on (firm_id, day) ensures each firm gets exactly one
snapshot per game day regardless of how many times the engine is called.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class FirmBalanceSnapshot(Base):
    """Daily financial position snapshot for one firm."""

    __tablename__ = "firm_balance_snapshots"

    __table_args__ = (
        UniqueConstraint("firm_id", "day", name="uq_firm_balance_snapshot_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=False, index=True)

    # In-game day this snapshot covers.
    day = Column(Integer, nullable=False, index=True)

    # Liquid cash at end of day after all inflows and outflows.
    cash_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Market value of unsold inventory (MVP: always 0; tracked for future).
    inventory_value_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Outstanding receivables (future: payment-on-delivery contracts).
    receivables_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Outstanding payables (wages owed, invoices pending).
    payables_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Outstanding debt principal balance.
    debt_outstanding_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Simplified equity = cash + inventory + receivables - payables - debt.
    equity_estimate_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Estimated days until cash is exhausted at current burn rate.
    # Null if the firm has no ongoing overhead or insufficient history.
    runway_days = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
