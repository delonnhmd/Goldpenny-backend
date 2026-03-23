"""app/models/player_stock_holding.py — Step 9: Per-player, per-stock position.

One row per (player, stock).  The row is created on the first buy and kept even
if shares_owned reaches 0, so we retain average cost basis history.

average_cost_basis and total_cost_basis are updated on every buy using the
weighted-average method.  On a full sell they are zeroed so a re-entry starts
fresh.

Integer shares only — no fractional shares in the MVP.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class PlayerStockHolding(Base):
    """Player's position in a single SectorStock."""

    __tablename__ = "player_stock_holdings"
    __table_args__ = (
        UniqueConstraint("player_id", "stock_id", name="uq_psh_player_stock"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_id  = Column(String(40), nullable=False, index=True)

    # Current position.  Can be 0 when the player has sold everything.
    shares_owned = Column(Integer, nullable=False, default=0)

    # Weighted-average purchase price per share.
    average_cost_basis = Column(Numeric(12, 4), nullable=False, default=0.0)

    # Total cost of all shares currently held (shares_owned * avg_cost_basis).
    total_cost_basis = Column(Numeric(12, 4), nullable=False, default=0.0)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Core schema aliases.
    ticker = synonym("stock_id")
    shares = synonym("shares_owned")

    player = relationship("Player", back_populates="stock_holdings", foreign_keys=[player_id])
