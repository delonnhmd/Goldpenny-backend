"""Step 42: Player forecast snapshot — lightweight rolling projection state."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerForecastSnapshot(Base):
    """Lightweight per-player forecast snapshot — one row per player (upsert).

    Stores the most recent forward-projection summary so that the UI can display
    a concise danger-radar and outlook without re-computing the full forecast
    on every request.
    """

    __tablename__ = "player_forecast_snapshots"
    __table_args__ = (UniqueConstraint("player_id", name="uq_pfs_player"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- forecast horizon ---
    forecast_horizon_days = Column(Integer, nullable=False, default=14)
    generated_on_day = Column(Integer, nullable=True, index=True)
    generated_on_date = Column(Date, nullable=True)

    # --- summary labels ---
    overall_outlook_label = Column(String(20), nullable=False, default="stable")
    # stable / tight / risky / critical
    near_term_risk_label = Column(String(20), nullable=False, default="low")
    # low / moderate / high / critical
    delinquency_risk_label = Column(String(20), nullable=False, default="low")
    # low / moderate / high / critical
    cash_gap_risk_label = Column(String(20), nullable=False, default="none")
    # none / minor / moderate / urgent
    debt_spiral_risk_label = Column(String(20), nullable=False, default="low")
    # low / building / high / spiral

    # --- key metrics ---
    liquidity_low_point_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    projected_delinquency_risk_day = Column(Integer, nullable=True)
    days_until_next_problem = Column(Integer, nullable=True)
    confidence_level = Column(String(20), nullable=False, default="medium")
    # low / medium / high

    # --- advisory labels ---
    guidance_label = Column(String(30), nullable=False, default="monitor")
    top_recommendation = Column(String(120), nullable=True)
    avoid_action = Column(String(120), nullable=True)
    next_major_risk_event = Column(String(80), nullable=True)
    best_stabilizing_action = Column(String(120), nullable=True)

    # --- JSON payloads ---
    projected_cash_curve_json = Column(Text, nullable=True)   # list of {day, cash}
    risk_signals_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    last_updated_on = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
