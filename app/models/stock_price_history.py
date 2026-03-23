"""app/models/stock_price_history.py — Step 9: Daily stock price log.

One row is written per (stock, day) pair by apply_daily_stock_price_update().
The function is idempotent — it skips if the row already exists.

The macro snapshot fields let us reconstruct exactly why a price moved on any
given day, which is useful for debugging and for frontend charts.
"""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class StockPriceHistory(Base):
    """Immutable daily price record for a SectorStock."""

    __tablename__ = "stock_price_histories"
    __table_args__ = (
        UniqueConstraint("stock_id", "day_number", name="uq_sph_stock_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References SectorStock.stock_id (logical FK — no DB constraint needed for
    # performance; the engine validates existence before writing).
    stock_id = Column(String(40), nullable=False, index=True)

    day_number = Column(Integer, nullable=False, index=True)

    # Prices
    old_price      = Column(Numeric(12, 4), nullable=False)
    new_price      = Column(Numeric(12, 4), nullable=False)
    change_percent = Column(Numeric(8, 4), nullable=False)

    # Macro snapshot at the time of the update — stored for auditability.
    inflation_used              = Column(Numeric(8, 4), nullable=False)
    interest_rate_used          = Column(Numeric(8, 4), nullable=False)
    unemployment_used           = Column(Numeric(8, 4), nullable=False)
    oil_index_used              = Column(Numeric(8, 4), nullable=False)
    consumer_confidence_used    = Column(Numeric(8, 4), nullable=False)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
