"""PurchaseAction — audit log for player basket goods acquisitions.

Step 8.5: Created for Multiplayer Marketplace System.

Tracks when a player acquires basket goods from sources such as:
  - system_market  : NPC in-game shop (future step integration)
  - marketplace     : player-to-player marketplace buy (Step 8.5)

Player-to-player marketplace transactions are primarily recorded in
MarketTransaction. PurchaseAction provides a unified purchase audit trail
for any channel.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PurchaseAction(Base):
    __tablename__ = "purchase_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Source channel: "system_market" | "marketplace" | "reward" | "other"
    source = Column(String(40), nullable=False, default="system_market")

    basket_name = Column(String(60), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    total_paid = Column(Numeric(12, 2), nullable=False, default=0)

    # In-game day this purchase occurred.
    day = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
