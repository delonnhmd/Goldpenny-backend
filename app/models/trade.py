"""Trade history record — Step 6.

Immutable log of every buy/sell transaction.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_symbol = Column(String(16), nullable=False, index=True)
    # "BUY" or "SELL"
    trade_type = Column(String(4), nullable=False)
    shares = Column(Integer, nullable=False)
    price_per_share = Column(Numeric(12, 4), nullable=False)
    total_value = Column(Numeric(14, 2), nullable=False)
    # In-game economy day when the trade was executed.
    day = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
