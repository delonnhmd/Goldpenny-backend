"""Step 39 rolling per-player wealth profile state."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerWealthState(Base):
    """Rolling snapshot of a player's wealth profile (one row per player)."""

    __tablename__ = "player_wealth_states"
    __table_args__ = (UniqueConstraint("player_id", name="uq_player_wealth_state_player"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- wealth snapshot (all in XGP) ---
    cash_reserve_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    savings_reserve_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    investable_surplus_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_drag_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    net_worth_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # --- asset breakdown ---
    liquid_asset_value_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    market_asset_value_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_equity_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    total_asset_value_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    total_debt_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # --- scores (0–100) ---
    wealth_momentum_score = Column(Numeric(8, 4), nullable=False, default=0)
    stability_before_growth_score = Column(Numeric(8, 4), nullable=False, default=0)
    buffer_days = Column(Numeric(8, 2), nullable=False, default=0)

    # --- phase labels ---
    wealth_phase_label = Column(String(20), nullable=False, default="fragile")
    asset_growth_trend = Column(String(20), nullable=False, default="stable")
    safe_to_save_label = Column(String(30), nullable=False, default="not_safe")
    safe_to_invest_label = Column(String(30), nullable=False, default="not_safe")

    # --- early-game softening ---
    experience_phase = Column(String(20), nullable=False, default="onboarding")
    days_in_phase = Column(Integer, nullable=False, default=0)
    softening_active = Column(Boolean, nullable=False, default=True)

    # --- advisory ---
    top_growth_driver = Column(String(80), nullable=True)
    top_drag_driver = Column(String(80), nullable=True)
    false_growth_detected = Column(Boolean, nullable=False, default=False)
    false_growth_warnings_json = Column(Text, nullable=True)
    planning_insights_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    last_updated_on = Column(Integer, nullable=True)
    last_updated_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
