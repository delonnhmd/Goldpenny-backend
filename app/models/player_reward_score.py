"""PlayerRewardScore — granular per-activity reward point accumulation.

Step 9: Monthly Reward Pool and Token Claim Accounting System.

One row per (player_id, month_index). Points are accumulated incrementally
as the player performs in-game actions during the month.

Point sources:
    work_points         — hours × productivity × 0.5
    business_points     — positive daily profit × 0.02
    investment_points   — realized stock gain × 0.01
    marketplace_points  — trade value × 0.005
    stability_points    — +5 per week for financially responsible behavior

total_points is the authoritative sum used for pool allocation.
Points can never go negative — floor is always 0.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerRewardScore(Base):
    """Monthly reward point accumulation per player.

    Unique constraint enforces exactly one active score row per player per month.
    """

    __tablename__ = "player_reward_scores"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "month_index", name="uq_player_reward_score_player_month"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Plain UUID column — no FK constraint for lightweight migrations.
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    month_index = Column(Integer, nullable=False, index=True)

    # ── Point sub-categories ──────────────────────────────────────────────────
    work_points = Column(Float, nullable=False, default=0.0)
    business_points = Column(Float, nullable=False, default=0.0)
    investment_points = Column(Float, nullable=False, default=0.0)
    marketplace_points = Column(Float, nullable=False, default=0.0)
    stability_points = Column(Float, nullable=False, default=0.0)

    # Authoritative total — always equals sum of sub-categories.
    total_points = Column(Float, nullable=False, default=0.0)

    # In-game day of the most recent point accumulation event.
    last_updated_day = Column(Integer, nullable=True)

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
