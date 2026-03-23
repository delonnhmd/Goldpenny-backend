"""app/models/firm_capacity.py — Step 14: Firm capacity tracking.

FirmCapacity tracks what a firm can produce / store / employ per day.
One row per (firm_id, capacity_type) pair.

Capacity types (MVP):
  "production" — units of product output per day
  "storage"    — inventory storage slots
  "staffing"   — maximum workers (NPC or player) that can be employed
  "delivery"   — delivery runs per day (food_truck relevant)

utilization (0.0–1.0): fraction of current_capacity actively in use.
  Helps the engine decide when to generate extra job openings.

maintenance_state: degrades over time if no maintenance cost is paid.
  Degraded maintenance reduces reliability and effective current_capacity.

reliability (0.0–1.0): probability that a production run succeeds fully.
  Below 0.7 → some output is lost.  Below 0.4 → firm should be flagged distressed.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class FirmCapacity(Base):
    """One capacity dimension for a single firm."""

    __tablename__ = "firm_capacities"

    __table_args__ = (
        UniqueConstraint("firm_id", "capacity_type", name="uq_firm_capacity_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=False, index=True)

    # One of: "production" / "storage" / "staffing" / "delivery"
    capacity_type = Column(String(40), nullable=False)

    # Theoretical maximum when fully staffed and maintained.
    base_capacity = Column(Numeric(10, 2), nullable=False, default=0.0)

    # Effective capacity after maintenance and staffing degradation.
    current_capacity = Column(Numeric(10, 2), nullable=False, default=0.0)

    # 0.0–1.0: fraction of current_capacity currently in use.
    utilization = Column(Numeric(8, 4), nullable=False, default=0.0)

    # "good" / "worn" / "degraded" / "critical"
    maintenance_state = Column(String(20), nullable=False, default="good")

    # 0.0–1.0: probability a production run completes without output loss.
    reliability = Column(Numeric(8, 4), nullable=False, default=1.0)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
