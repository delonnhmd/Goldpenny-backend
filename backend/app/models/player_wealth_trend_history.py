"""Step 39 daily wealth snapshot history (append-only rows)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerWealthTrendHistory(Base):
    """One row per evaluation day capturing the player's wealth snapshot."""

    __tablename__ = "player_wealth_trend_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True)

    # wealth snapshot at this point in time
    net_worth_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    total_asset_value_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    total_debt_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_drag_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    investable_surplus_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    market_asset_value_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_equity_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # scores
    wealth_momentum_score = Column(Numeric(8, 4), nullable=False, default=0)
    stability_before_growth_score = Column(Numeric(8, 4), nullable=False, default=0)
    buffer_days = Column(Numeric(8, 2), nullable=False, default=0)

    # labels
    wealth_phase_label = Column(String(20), nullable=False, default="fragile")
    asset_growth_trend = Column(String(20), nullable=False, default="stable")
    experience_phase = Column(String(20), nullable=False, default="onboarding")

    # false-growth flag
    false_growth_flag = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
