"""app/models/coop_deal_payout.py — Step 13: Co-op Deals System.

CoopDealPayout is an immutable append-only audit record of one participant's
payout when a co-op deal completes.

Rows are NEVER updated or deleted.  They accumulate as a full economic audit
trail that can be used for:
  - Player payout history display
  - Economy-wide income analysis
  - Anti-exploit review (cross-referencing with XGPTransaction rows)

Each completed deal produces one CoopDealPayout row per participant.

Economic context:
  The payout rows + XGPTransaction rows are the authoritative source of truth
  for how co-op collaboration income enters the economy.  Together they let
  the economy team trace every XGP unit that flows from deal completion.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class CoopDealPayout(Base):
    """Immutable payout record for one participant in a completed co-op deal."""

    __tablename__ = "coop_deal_payouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    deal_id = Column(Integer, ForeignKey("coop_deals.id"), nullable=False, index=True)

    # Which player received this payout.
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # The participant's split share for this deal (e.g. 50.0 for 50%).
    split_percent = Column(Float, nullable=False)

    # XGP credited to this player's cash balance.
    amount_xgp = Column(Numeric(12, 2), nullable=False)

    # Player XGP balance immediately before and after the credit.
    # Captured at completion time for full auditability.
    balance_before = Column(Numeric(12, 2), nullable=False)
    balance_after = Column(Numeric(12, 2), nullable=False)

    # In-game day on which this payout was issued.
    day_number = Column(Integer, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
