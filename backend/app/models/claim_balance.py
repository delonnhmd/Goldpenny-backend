"""Accumulated pending off-chain reward balance per player (one row per player)."""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class ClaimBalance(Base):
    __tablename__ = "claim_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Current accumulated off-chain balances
    pending_reward_points = Column(Float, nullable=False, default=0.0)
    pending_token_amount = Column(Float, nullable=False, default=0.0)
    # Lifetime accounting
    lifetime_approved_token_amount = Column(Float, nullable=False, default=0.0)
    lifetime_claimed_token_amount = Column(Float, nullable=False, default=0.0)
    # Track last processed month for idempotency
    last_processed_month_key = Column(String(7), nullable=True)  # "YYYY-MM"
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
