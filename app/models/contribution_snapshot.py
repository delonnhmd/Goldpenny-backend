"""app/models/contribution_snapshot.py — Per-player, per-epoch reward snapshot.

One row is created for each player at epoch finalisation.  It captures the
player's raw activity metrics, computed contribution score, eligibility
decision, and final PFT allocation for that epoch.

This is the immutable audit record for every PFT distribution event.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class ContributionSnapshot(Base):
    """Reward snapshot for one player in one epoch."""

    __tablename__ = "contribution_snapshots"

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
        ForeignKey("reward_epochs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Activity metrics captured at snapshot time ────────────────────────────
    # Total XGP earned through all income sources during this epoch.
    xgp_earned = Column(Float, nullable=False, default=0.0)

    # Weighted contribution score computed by the reward engine.
    contribution_score = Column(Float, nullable=False, default=0.0)

    # Reputation at the moment the snapshot was taken (point-in-time).
    reputation_at_snapshot = Column(Integer, nullable=False, default=0)

    # ── Eligibility & allocation ──────────────────────────────────────────────
    # True if the player met all eligibility gates (age, reputation, score).
    qualified = Column(Boolean, nullable=False, default=False)

    # PFT units allocated to this player for this epoch.
    # 0 for non-qualified players.  Computed by allocate_monthly_pft().
    pft_allocated = Column(Float, nullable=False, default=0.0)

    # ── Claim tracking (disabled during Step 1) ───────────────────────────────
    # Will be True once the player submits an on-chain claim in a later step.
    claimed = Column(Boolean, nullable=False, default=False)
    claimed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    epoch = relationship("RewardEpoch", foreign_keys=[epoch_id])
    player = relationship("Player", foreign_keys=[player_id])
