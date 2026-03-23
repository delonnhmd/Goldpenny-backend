"""Immutable daily business operations log."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class BusinessDailyLog(Base):
    """One immutable row per business per day describing operating outcome."""

    __tablename__ = "business_daily_logs"
    __table_args__ = (
        UniqueConstraint("business_id", "day", name="uq_business_daily_logs_business_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("player_businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True, index=True)
    business_type = Column(String(40), nullable=True, index=True)
    region_key = Column(String(40), nullable=True)

    gross_revenue_xgp = Column(Numeric(14, 4), nullable=False)
    input_cost_xgp = Column(Numeric(14, 4), nullable=False)
    fuel_cost_xgp = Column(Numeric(14, 4), nullable=True)
    maintenance_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    spoilage_cost_xgp = Column(Numeric(14, 4), nullable=True)
    overhead_cost_xgp = Column(Numeric(14, 4), nullable=False)
    net_profit_xgp = Column(Numeric(14, 4), nullable=False)

    units_sold = Column(Integer, nullable=False, default=0)
    inventory_start_units = Column(Numeric(14, 4), nullable=False, default=0)
    inventory_end_units = Column(Numeric(14, 4), nullable=False, default=0)
    demand_signal = Column(Numeric(8, 4), nullable=False, default=0)

    demand_score = Column(Numeric(8, 4), nullable=False)
    utilization_pct = Column(Numeric(8, 4), nullable=False)
    reputation_before = Column(Integer, nullable=True)
    reputation_after = Column(Integer, nullable=True)

    debug_json = Column(Text, nullable=True)
    notes_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    revenue_xgp = synonym("gross_revenue_xgp")
    cogs_xgp = synonym("input_cost_xgp")
    overhead_xgp = synonym("overhead_cost_xgp")
    spoilage_loss_xgp = synonym("spoilage_cost_xgp")

    business = relationship("PlayerBusiness", back_populates="daily_logs", foreign_keys=[business_id])
