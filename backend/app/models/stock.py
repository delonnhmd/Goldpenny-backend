"""Stock market listing model — Step 6.

The existing `stocks` table is kept so the Basket model's foreign key is
preserved. New columns are added via startup migration (ALTER TABLE).
"""

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, func

from app.db.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(16), unique=True, nullable=False, index=True)
    # Legacy alias kept for backward compat with Basket relationship.
    name = Column(String(120), nullable=False)
    company_name = Column(String(120), nullable=True)   # same value, richer column
    sector = Column(String(40), nullable=False, default="consumer")

    base_price = Column(Numeric(12, 2), nullable=False, default=50)
    current_price = Column(Numeric(12, 4), nullable=False, default=50)
    # Legacy column alias — mirrors current_price, kept for backward compat.
    last_price = Column(Numeric(12, 2), nullable=True)

    # 0–1: magnitude of company-specific random noise applied on top of sector move.
    volatility = Column(Float, nullable=False, default=0.5)
    # Small daily drift added to the sector move to give companies character.
    # Positive = slow grower; negative = contrarian.
    growth_bias = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

