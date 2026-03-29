"""app/models/xgp_transaction.py — Immutable XGP ledger entry.

Every XGP inflow or outflow MUST produce a row in this table before the
player's balance is updated.  This gives:
  - A complete, auditable history of every XGP movement.
  - A foundation for fraud detection (compare balance_before/after chain).
  - A future source for contribution scoring and dispute resolution.

No balance may be updated without a corresponding ledger entry.

Economic note:
  XGP is the off-chain gameplay currency.  It is NOT minted on-chain and
  has no direct conversion to PFT (the on-chain reward token).  PFT
  allocation is calculated separately via the monthly contribution pool.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class XGPTransaction(Base):
    """One debit or credit event against a player's XGP balance."""

    __tablename__ = "xgp_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Who ───────────────────────────────────────────────────────────────────
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── What kind of transaction ──────────────────────────────────────────────
    # Examples: job_income, business_income, market_purchase, repair_cost,
    #           healthcare_cost, listing_fee, debt_payment, tax_payment
    transaction_type = Column(String(40), nullable=False, index=True)

    # ── Direction ─────────────────────────────────────────────────────────────
    # "in"  — player receives XGP (income, refund, award)
    # "out" — player spends XGP (purchase, fee, penalty)
    direction = Column(String(3), nullable=False, index=True)

    # ── Amounts ───────────────────────────────────────────────────────────────
    # Stored as Numeric for precision; always positive regardless of direction.
    amount = Column(Numeric(14, 4), nullable=False)
    balance_before = Column(Numeric(14, 4), nullable=False)
    balance_after = Column(Numeric(14, 4), nullable=False)

    # ── Source reference (optional) ───────────────────────────────────────────
    # Allows tracing back to the originating record (JobAction, MarketListing…)
    reference_type = Column(String(40), nullable=True)    # e.g. "job_action"
    reference_id = Column(String(60), nullable=True)       # UUID or int as string

    # ── Human-readable note ───────────────────────────────────────────────────
    description = Column(String(200), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────────────────────────────────
    player = relationship("Player", foreign_keys=[player_id])
