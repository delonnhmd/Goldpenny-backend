"""Player housing region state for settlement pressure integration."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerHousingState(Base):
    """Current/previous housing assignment rows for a player."""

    __tablename__ = "player_housing_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region = Column(String(40), nullable=False, index=True)  # suburban | downtown
    housing_type = Column(String(40), nullable=False, default="starter_rent")
    monthly_housing_cost_xgp = Column(Numeric(14, 4), nullable=False, default=540)
    monthly_utilities_cost_xgp = Column(Numeric(14, 4), nullable=False, default=105)
    monthly_transport_base_xgp = Column(Numeric(14, 4), nullable=False, default=165)
    daily_housing_cost_xgp = Column(Numeric(14, 2), nullable=False, default=18)
    commute_mode = Column(String(20), nullable=False, default="car")
    commute_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    stress_modifier = Column(Integer, nullable=False, default=0)
    opportunity_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    business_demand_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    side_income_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    networking_modifier = Column(Numeric(8, 4), nullable=False, default=0.0)
    active_flag = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
