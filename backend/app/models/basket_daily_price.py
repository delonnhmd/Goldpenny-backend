"""Core daily basket pricing table."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Enum, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base
from app.models.enums import BasketType


class BasketDailyPrice(Base):
    __tablename__ = "basket_daily_prices"
    __table_args__ = (
        UniqueConstraint("day", "basket_type", name="uq_basket_daily_price_day_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = Column(Integer, nullable=False, index=True)
    basket_type = Column(
        Enum(BasketType, name="basket_type_enum", native_enum=False, length=20),
        nullable=False,
        index=True,
    )

    price_index = Column(Numeric(12, 4), nullable=False)
    daily_change_pct = Column(Numeric(8, 4), nullable=False, default=0)
    supply_pressure = Column(Numeric(8, 4), nullable=False, default=1.0)
    demand_pressure = Column(Numeric(8, 4), nullable=False, default=1.0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

