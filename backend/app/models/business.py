import uuid

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class Business(Base):
    """A player-owned business.

    One row per business instance.  A player may only have one ``active``
    business at a time (enforced by the engine).
    """

    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    business_type = Column(String(40), nullable=False)   # fruit_shop | food_truck
    business_name = Column(String(120), nullable=False)
    tier = Column(String(40), nullable=False)             # first entry in upgrade_path
    status = Column(String(20), nullable=False, default="active")  # active|paused|closed

    # ── Financials ────────────────────────────────────────────────────────────
    startup_cost_paid = Column(Numeric(12, 2), nullable=False, default=0)
    current_cash_invested = Column(Numeric(12, 2), nullable=False, default=0)
    cumulative_revenue = Column(Numeric(14, 2), nullable=False, default=0)
    cumulative_expense = Column(Numeric(14, 2), nullable=False, default=0)
    cumulative_profit = Column(Numeric(14, 2), nullable=False, default=0)

    # ── Operations ────────────────────────────────────────────────────────────
    times_operated = Column(Integer, nullable=False, default=0)
    last_operated_day = Column(Integer, nullable=True)

    # ── Step 7b: balancing and reputation tracking ────────────────────────────
    consecutive_profitable_days = Column(Integer, nullable=False, default=0)
    consecutive_loss_days = Column(Integer, nullable=False, default=0)
    lifetime_units_sold = Column(Integer, nullable=False, default=0)
    lifetime_spoiled_units = Column(Integer, nullable=False, default=0)
    demand_reputation = Column(Float, nullable=False, default=1.0)
    current_margin_modifier = Column(Float, nullable=False, default=1.0)
    last_snapshot_day = Column(Integer, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    inventory = relationship(
        "BusinessInventory",
        back_populates="business",
        cascade="all, delete-orphan",
    )
    actions = relationship(
        "BusinessAction",
        back_populates="business",
        cascade="all, delete-orphan",
    )
