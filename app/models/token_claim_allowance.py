"""TokenClaimAllowance — per-player proportional token allowance after pool closes.

Step 9: Monthly Reward Pool and Token Claim Accounting System.

Created by close_reward_pool() for each player who earned > 0 points.

allowance_status lifecycle:
    "pending"   — pool not yet closed; allowance not yet calculated
    "claimable" — pool closed; player may claim their token_allocation
    "claimed"   — player has marked their tokens as claimed
    "expired"   — claim window passed without the player claiming

token_allocation = reward_pool.total_tokens_allocated × (player_points / pool_points_total)
claimable_tokens = token_allocation − tokens_claimed

Actual on-chain minting happens in a future step. This record feeds the
blockchain claim process.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class TokenClaimAllowance(Base):
    """Calculated proportional token allowance for a player for one game month.

    Unique constraint prevents duplicate allowances for the same player month.
    """

    __tablename__ = "token_claim_allowances"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "month_index", name="uq_token_claim_allowance_player_month"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Plain UUID column — no FK constraint for lightweight migrations.
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    month_index = Column(Integer, nullable=False, index=True)

    # Player's total reward points for this month (snapshot at pool close).
    total_points = Column(Float, nullable=False, default=0.0)

    # Proportional token allocation from the pool.
    token_allocation = Column(Float, nullable=False, default=0.0)
    # Tokens actually marked as claimed (0 until claim_tokens is called).
    tokens_claimed = Column(Float, nullable=False, default=0.0)
    # Remaining claimable = token_allocation − tokens_claimed.
    claimable_tokens = Column(Float, nullable=False, default=0.0)

    # "pending" | "claimable" | "claimed" | "expired"
    allowance_status = Column(String(20), nullable=False, default="pending", index=True)

    # In-game day when this allowance was calculated (pool close day).
    calculated_day = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
