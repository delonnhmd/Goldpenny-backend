"""Step 34 region population pressure rolling state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RegionPopulationState(Base):
    """Current bounded population/opportunity/friction state for a region."""

    __tablename__ = "region_population_states"
    __table_args__ = (
        UniqueConstraint("region_key", name="uq_region_population_state_region"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_key = Column(String(40), nullable=False, index=True)

    memory_window_start_day = Column(Integer, nullable=False, default=1, index=True)
    memory_window_end_day = Column(Integer, nullable=False, default=1, index=True)
    memory_window_start = Column(Date, nullable=True)
    memory_window_end = Column(Date, nullable=True)

    active_population_score = Column(Numeric(8, 4), nullable=False, default=0)
    opportunity_density_score = Column(Numeric(8, 4), nullable=False, default=0)
    congestion_score = Column(Numeric(8, 4), nullable=False, default=0)
    housing_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    business_competition_score = Column(Numeric(8, 4), nullable=False, default=0)
    consumer_flow_score = Column(Numeric(8, 4), nullable=False, default=0)

    recent_growth_direction = Column(String(20), nullable=False, default="stable")
    state_debug_json = Column(Text, nullable=True)

    last_updated_on = Column(Integer, nullable=True, index=True)
    last_updated_date = Column(Date, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
