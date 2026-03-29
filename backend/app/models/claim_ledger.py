"""app/models/claim_ledger.py — Future PFT on-chain claim record.

One row per claim intent.  Created when a player requests to withdraw their
allocated PFT to an external wallet.

Claiming is DISABLED in Step 1.  This table is provisioned now so the
claim flow can be activated in a later step (smart-contract integration)
without any schema migration.  The status field defaults to "disabled"
to make this explicit.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class ClaimLedger(Base):
    """Pending / historical PFT on-chain claim record.

    Lifecycle:
        disabled  → (Step 1 placeholder, claiming not enabled)
        pending   → player requested claim, awaiting on-chain confirmation
        confirmed → tx_hash confirmed on-chain
        failed    → on-chain transaction reverted or timed out
    """

    __tablename__ = "claim_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Foreign keys ──────────────────────────────────────────────────────────
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    epoch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reward_epochs.id", ondelete="SET NULL"),
        nullable=True,   # nullable so records survive epoch deletion
        index=True,
    )

    # ── Claim details ─────────────────────────────────────────────────────────
    # Destination wallet address provided by the player at claim time.
    wallet_address = Column(String(100), nullable=True)

    # PFT amount being claimed (from contribution_snapshot.pft_allocated).
    amount = Column(Float, nullable=False)

    # On-chain transaction hash once submitted.  Null until broadcast.
    tx_hash = Column(String(100), nullable=True)

    # Current lifecycle state.  Defaults to "disabled" during Step 1.
    status = Column(String(20), nullable=False, default="disabled")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    epoch = relationship("RewardEpoch", foreign_keys=[epoch_id])
    player = relationship("Player", foreign_keys=[player_id])
