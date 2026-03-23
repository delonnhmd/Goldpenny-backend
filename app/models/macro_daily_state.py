"""Core macro snapshot table (one row per in-game day)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, func

from app.db.database import Base


class MacroDailyState(Base):
    __tablename__ = "macro_daily_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, nullable=False, unique=True, index=True)

    inflation_rate = Column(Numeric(8, 4), nullable=False, default=2.0)
    interest_rate = Column(Numeric(8, 4), nullable=False, default=4.0)
    unemployment_rate = Column(Numeric(8, 4), nullable=False, default=5.0)
    oil_index = Column(Numeric(10, 4), nullable=False, default=100.0)
    consumer_confidence = Column(Numeric(8, 4), nullable=False, default=50.0)
    supply_chain_stress = Column(Numeric(8, 4), nullable=False, default=0.0)

    event_headline = Column(String(200), nullable=True)
    event_summary = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

