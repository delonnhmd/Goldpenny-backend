"""Immutable housing pressure log written once per player per day."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import synonym
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class HousingDailyLog(Base):
    """Daily housing cost and pressure outcomes for explainability and analytics."""

    __tablename__ = "housing_daily_logs"
    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_housing_daily_log_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True, index=True)
    region = Column(String(40), nullable=False)
    housing_cost_xgp = Column(Numeric(14, 2), nullable=False)
    utilities_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    commute_hours = Column(Numeric(12, 4), nullable=False, default=0)
    commute_fuel_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    commute_pressure = Column(Numeric(8, 4), nullable=False, default=0)
    stress_delta = Column(Integer, nullable=False, default=0)
    opportunity_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    region_stress_delta = Column(Numeric(8, 4), nullable=False, default=0)
    region_opportunity_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    region_business_demand_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    region_side_income_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    networking_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    opportunity_quality_signal = Column(Numeric(8, 4), nullable=False, default=1)
    housing_debug_json = Column(Text, nullable=True)
    notes_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    region_key = synonym("region")
    housing_cost_daily_xgp = synonym("housing_cost_xgp")

    player = relationship("Player", foreign_keys=[player_id])
