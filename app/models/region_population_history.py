"""Step 34 bounded daily region population pressure history model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RegionPopulationHistory(Base):
    """Compact day-level region pressure snapshot for rolling memory and auditability."""

    __tablename__ = "region_population_history"
    __table_args__ = (
        UniqueConstraint("region_key", "as_of_day", name="uq_region_population_history_region_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_key = Column(String(40), nullable=False, index=True)
    as_of_day = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True, index=True)

    active_population_score = Column(Numeric(8, 4), nullable=False, default=0)
    opportunity_density_score = Column(Numeric(8, 4), nullable=False, default=0)
    congestion_score = Column(Numeric(8, 4), nullable=False, default=0)
    housing_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    business_competition_score = Column(Numeric(8, 4), nullable=False, default=0)
    consumer_flow_score = Column(Numeric(8, 4), nullable=False, default=0)

    heat_level = Column(String(20), nullable=False, default="moderate")
    recent_growth_direction = Column(String(20), nullable=False, default="stable")
    summary_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
