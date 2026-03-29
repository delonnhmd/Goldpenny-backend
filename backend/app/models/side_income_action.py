"""Immutable side-income action audit record.

Step 8 introduces ride share as the first flexible emergency-income mechanic:
players can trade remaining daily time and wellbeing for extra XGP when needed.
Each action is write-once for full economic traceability.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class SideIncomeAction(Base):
    """One immutable side-income action (Step 8: ride share MVP)."""

    __tablename__ = "side_income_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_number = Column(Integer, nullable=False, index=True)

    # Step 8 uses only "ride_share" for now, but this stays future-proof
    # for additional side-income loops (delivery, tutoring, gig tasks, etc.).
    side_income_type = Column(String(40), nullable=False, index=True)

    hours_worked = Column(Float, nullable=False)

    # Monetary components are stored separately so net outcomes remain auditable.
    gross_income_xgp = Column(Numeric(14, 4), nullable=False)
    fuel_cost_xgp = Column(Numeric(14, 4), nullable=False)
    wear_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    maintenance_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    net_income_xgp = Column(Numeric(14, 4), nullable=False)

    demand_multiplier = Column(Numeric(8, 4), nullable=False, default=1)
    gross_per_hour_xgp = Column(Numeric(12, 4), nullable=False, default=0)
    gas_price_per_unit_xgp = Column(Numeric(10, 4), nullable=False, default=0)
    wear_cost_per_hour_xgp = Column(Numeric(10, 4), nullable=False, default=0)
    net_per_hour_xgp = Column(Numeric(12, 4), nullable=False, default=0)
    reliability_before = Column(Numeric(8, 4), nullable=False, default=1)
    reliability_after = Column(Numeric(8, 4), nullable=False, default=1)

    stress_change = Column(Integer, nullable=False)
    health_change = Column(Integer, nullable=False)
    hours_before = Column(Integer, nullable=False)
    hours_after = Column(Integer, nullable=False)
    oil_index_used = Column(Float, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    gas_cost_xgp = synonym("fuel_cost_xgp")

    player = relationship("Player", foreign_keys=[player_id])
