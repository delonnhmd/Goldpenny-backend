import uuid

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class BusinessDailySnapshot(Base):
    """One row per business operation day — stores all balancing factors.

    Used for:
    - balance and margin analysis
    - anti-exploit review
    - future dashboards and tuning
    """

    __tablename__ = "business_daily_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # ── Day context ───────────────────────────────────────────────────────────
    day = Column(Integer, nullable=False, index=True)
    business_type = Column(String(40), nullable=False)
    tier = Column(String(40), nullable=False)
    region = Column(String(40), nullable=False)

    # ── Balancing factors ─────────────────────────────────────────────────────
    demand_factor = Column(Float, nullable=False)
    operating_efficiency = Column(Float, nullable=False)

    # ── Financials ────────────────────────────────────────────────────────────
    input_cost_total = Column(Numeric(12, 2), nullable=False, default=0)
    revenue_generated = Column(Numeric(12, 2), nullable=False, default=0)
    overhead_cost = Column(Numeric(12, 2), nullable=False, default=0)
    fuel_cost = Column(Numeric(12, 2), nullable=False, default=0)
    spoilage_cost = Column(Numeric(12, 2), nullable=False, default=0)
    net_profit = Column(Numeric(12, 2), nullable=False, default=0)

    # ── Output ────────────────────────────────────────────────────────────────
    units_sold = Column(Integer, nullable=False, default=0)
    spoiled_units = Column(Integer, nullable=False, default=0)

    # ── Pressure scores ───────────────────────────────────────────────────────
    customer_pressure = Column(Float, nullable=False, default=1.0)
    economy_pressure = Column(Float, nullable=False, default=1.0)
    player_condition_penalty = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
