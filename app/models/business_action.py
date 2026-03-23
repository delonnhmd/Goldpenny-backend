import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class BusinessAction(Base):
    """Immutable audit log for all business activity.

    action_type values:
        start_business  — initial creation
        buy_inventory   — purchasing input stock
        operate         — running the business for a day
        upgrade         — advancing to the next tier
        close           — shutting the business down
    """

    __tablename__ = "business_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # ── When ──────────────────────────────────────────────────────────────────
    day = Column(Integer, nullable=False)
    action_type = Column(String(40), nullable=False)

    # ── Financials ────────────────────────────────────────────────────────────
    input_cost = Column(Numeric(12, 2), nullable=False, default=0)
    overhead_cost = Column(Numeric(12, 2), nullable=False, default=0)
    fuel_cost = Column(Numeric(12, 2), nullable=False, default=0)
    revenue_generated = Column(Numeric(12, 2), nullable=False, default=0)
    net_profit = Column(Numeric(12, 2), nullable=False, default=0)

    # ── Operation detail ──────────────────────────────────────────────────────
    units_sold = Column(Integer, nullable=False, default=0)
    spoiled_units = Column(Integer, nullable=False, default=0)

    # ── Player impact ─────────────────────────────────────────────────────────
    stress_change = Column(Integer, nullable=False, default=0)
    health_change = Column(Integer, nullable=False, default=0)
    time_spent = Column(Integer, nullable=False, default=0)

    # ── Step 7b: balance analytics (operate actions only) ────────────────────
    demand_factor = Column(Float, nullable=True)
    efficiency_factor = Column(Float, nullable=True)
    margin_modifier = Column(Float, nullable=True)
    economy_pressure = Column(Float, nullable=True)
    player_condition_penalty = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    business = relationship("Business", back_populates="actions")
