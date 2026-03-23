"""RewardPool — monthly token reward supply for Gold Penny.

Step 9: Monthly Reward Pool and Token Claim Accounting System.

One row per game month. The pool defines how many tokens are distributed
proportionally among active players at month end.

game month_index is an integer derived from in-game days:
    month_index = (current_day - 1) // 30 + 1

Month 1 = in-game days 1–30, Month 2 = days 31–60, etc.

The pool is NEVER refilled once closed. Token supply is enforced by the
monthly emission schedule in the reward engine.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RewardPool(Base):
    """Monthly token reward pool — supply-side accounting.

    status lifecycle:
        "open"   → pool is accepting point accumulation (current month)
        "closed" → month ended; token_claim_allowances have been calculated
    """

    __tablename__ = "reward_pools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Integer game month index (1-based, derived from in-game days).
    month_index = Column(Integer, nullable=False, unique=True, index=True)

    # Total tokens available for this month (from emission schedule).
    total_tokens_allocated = Column(Float, nullable=False, default=100_000.0)
    # Decremented as allowances are calculated. Remainder is burned/carried.
    tokens_remaining = Column(Float, nullable=False, default=100_000.0)

    # Sum of all player total_points at time of pool close.
    # Used as the denominator for proportional allocation.
    points_total = Column(Float, nullable=False, default=0.0)

    # "open" | "closed"
    status = Column(String(20), nullable=False, default="open", index=True)

    # In-game day this pool was created (first day of the month).
    created_day = Column(Integer, nullable=False)
    # In-game day pool was closed (last day of the month). Null while open.
    closed_day = Column(Integer, nullable=True)

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
