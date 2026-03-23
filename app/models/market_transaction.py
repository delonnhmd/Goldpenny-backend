"""MarketTransaction — completed player-to-player marketplace purchase record.

Step 8.5: Multiplayer Marketplace and Player-to-Player Commerce System.

Immutable record of every successful marketplace sale. Includes suspicious
pattern flags for future anti-cheat analysis.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class MarketTransaction(Base):
    """Completed marketplace trade between two players.

    suspicious_flag is set by the engine if patterns such as repeated trades
    between the same pair, near-floor / near-ceiling pricing, or unusual volume
    are detected. No automated action is taken in Step 8.5 — records are kept
    for future anti-cheat review.
    """

    __tablename__ = "market_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Plain UUID columns — no FK constraints for lightweight migrations.
    listing_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    seller_player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    buyer_player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    source_type = Column(String(30), nullable=False)  # player_inventory | business_inventory
    basket_name = Column(String(60), nullable=False)
    quantity = Column(Integer, nullable=False)

    unit_price = Column(Numeric(12, 2), nullable=False)
    gross_total = Column(Numeric(12, 2), nullable=False)
    marketplace_fee = Column(Numeric(12, 2), nullable=False)
    seller_net = Column(Numeric(12, 2), nullable=False)

    # Region stored for future transport cost / scarcity expansion.
    buyer_region = Column(String(40), nullable=True)
    seller_region = Column(String(40), nullable=True)

    created_day = Column(Integer, nullable=False)

    # Anti-abuse flags. Set by engine, never shown to players in Step 8.5.
    suspicious_flag = Column(Boolean, nullable=False, default=False)
    suspicious_notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
