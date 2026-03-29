import uuid

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class HousingDailySnapshot(Base):
    """One row per player housing per in-game day.

    Stores the full breakdown of housing pressure for analytics, balancing
    review, and future dashboards.  No FK constraints — uses plain UUID columns
    to keep schema migrations lightweight.
    """

    __tablename__ = "housing_daily_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    housing_id = Column(UUID(as_uuid=True), nullable=False)
    day = Column(Integer, nullable=False, index=True)
    region = Column(String(40), nullable=False)
    occupancy_type = Column(String(20), nullable=False)
    daily_base_cost = Column(Numeric(10, 2), nullable=False)
    debt_payment_amount = Column(Numeric(10, 2), nullable=False, default=0)
    property_tax_amount = Column(Numeric(10, 2), nullable=False, default=0)
    maintenance_amount = Column(Numeric(10, 2), nullable=False, default=0)
    total_housing_cost = Column(Numeric(10, 2), nullable=False)
    affordability_ratio = Column(Float, nullable=True)          # pressure [0.90, 1.80]
    housing_stress_impact = Column(Integer, nullable=True)      # net stress change
    delinquency_penalty = Column(Integer, nullable=True)        # 0 if paid, 1+ if missed
    credit_score_change = Column(Integer, nullable=True)
    housing_stability_change = Column(Integer, nullable=True)
    cash_after_housing = Column(Numeric(12, 2), nullable=True)
    net_worth_after_housing = Column(Numeric(14, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
