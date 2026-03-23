from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, func

from app.db.database import Base


class EconomyEvent(Base):
    __tablename__ = "economy_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    event_type = Column(String, nullable=False, default="neutral")
    inflation_impact = Column(Float, nullable=False, default=0.0)
    interest_rate_impact = Column(Float, nullable=False, default=0.0)
    unemployment_impact = Column(Float, nullable=False, default=0.0)
    oil_impact = Column(Float, nullable=False, default=0.0)
    confidence_impact = Column(Float, nullable=False, default=0.0)
    supply_chain_impact = Column(Float, nullable=False, default=0.0)
    seasonal_impact = Column(Float, nullable=False, default=0.0)
    severity = Column(String, nullable=False, default="minor")
    is_system_generated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
