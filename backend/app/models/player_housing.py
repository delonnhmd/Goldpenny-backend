import uuid

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerHousing(Base):
    """Tracks a player's active or past housing arrangement.

    One active housing row per player (enforced in engine layer).
    Status lifecycle: active → inactive | defaulted | sold
    """

    __tablename__ = "player_housings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    housing_key = Column(String(60), nullable=False)
    region = Column(String(40), nullable=False)           # suburban | downtown
    occupancy_type = Column(String(20), nullable=False)   # rent | own
    status = Column(String(20), nullable=False, default="active")  # active | inactive | defaulted | sold
    daily_cost = Column(Numeric(10, 2), nullable=False)
    move_in_day = Column(Integer, nullable=False)
    last_cost_applied_day = Column(Integer, nullable=True)
    linked_debt_account_id = Column(UUID(as_uuid=True), nullable=True)
    property_value = Column(Numeric(12, 2), nullable=True)
    # ── Step 8b: pressure tracking ────────────────────────────────────────────
    affordability_pressure = Column(Float, nullable=False, default=1.0)
    cumulative_housing_paid = Column(Numeric(12, 2), nullable=False, default=0)
    cumulative_property_tax_paid = Column(Numeric(12, 2), nullable=False, default=0)
    cumulative_maintenance_paid = Column(Numeric(12, 2), nullable=False, default=0)
    cumulative_debt_paid = Column(Numeric(12, 2), nullable=False, default=0)
    consecutive_missed_housing_days = Column(Integer, nullable=False, default=0)
    region_pressure_modifier = Column(Float, nullable=False, default=1.0)
    last_snapshot_day = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
