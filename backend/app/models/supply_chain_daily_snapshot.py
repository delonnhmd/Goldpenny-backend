"""Step 43 — Supply Chain Daily Snapshot DB model.

Caches the full per-day supply chain graph computation (all 12 node states,
basket multipliers, bottlenecks, job pressure, and story output) so that each
day is computed once and served cheaply thereafter.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class SupplyChainDailySnapshot(Base):
    __tablename__ = "supply_chain_daily_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Day key
    day = Column(Integer, nullable=False)

    # Top-level summary fields (denormalised for quick access)
    top_bottleneck_node = Column(String(40), nullable=True)
    most_affected_basket = Column(String(30), nullable=True)
    best_job_opportunity = Column(String(40), nullable=True)
    overall_stress_score = Column(Numeric(8, 4), nullable=True)

    # JSON blobs
    node_states_json = Column(Text, nullable=True)
    basket_multipliers_json = Column(Text, nullable=True)
    bottlenecks_json = Column(Text, nullable=True)
    job_pressure_json = Column(Text, nullable=True)
    story_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    # Audit
    computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("day", name="uq_scds_day"),
    )
