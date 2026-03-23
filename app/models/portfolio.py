"""Player stock portfolio — Step 6.

One row per (player, symbol) pair; updated in-place on every trade.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("player_id", "stock_symbol", name="uq_portfolio_player_symbol"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_symbol = Column(String(16), nullable=False, index=True)
    shares = Column(Integer, nullable=False, default=0)
    # Volume-weighted average purchase price for P&L display.
    average_price = Column(Numeric(12, 4), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
