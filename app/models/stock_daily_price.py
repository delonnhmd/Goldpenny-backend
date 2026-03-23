"""Core daily stock price snapshot table."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class StockDailyPrice(Base):
    __tablename__ = "stock_daily_prices"
    __table_args__ = (
        UniqueConstraint("day", "ticker", name="uq_stock_daily_price_day_ticker"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = Column(Integer, nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    sector = Column(String(40), nullable=False)

    open_price = Column(Numeric(14, 4), nullable=False)
    close_price = Column(Numeric(14, 4), nullable=False)
    daily_change_pct = Column(Numeric(8, 4), nullable=False)
    macro_impact = Column(Numeric(8, 4), nullable=False, default=0)
    noise_component = Column(Numeric(8, 4), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

