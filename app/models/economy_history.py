from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db.database import Base


class EconomyHistory(Base):
    __tablename__ = "economy_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, nullable=False, index=True)
    inflation_rate = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    unemployment_rate = Column(Float, nullable=False)
    oil_index = Column(Float, nullable=False)
    consumer_confidence = Column(Float, nullable=False)
    supply_chain_index = Column(Float, nullable=False)
    seasonal_index = Column(Float, nullable=False)
    basket_price_pressure = Column(Float, nullable=False)
    layoff_pressure = Column(Float, nullable=False)
    wage_pressure = Column(Float, nullable=False)
    sector_pressure_summary = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
