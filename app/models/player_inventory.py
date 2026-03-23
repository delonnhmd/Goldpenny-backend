"""PlayerInventory — household basket goods inventory for a player.

Step 8.5: Created for Multiplayer Marketplace System.

One row per (player, basket_name) pair; quantity is updated in place.
Goods here can be listed on the marketplace or consumed by the player.

This is distinct from:
- BusinessInventory  — input goods owned by a business
- Basket (baskets table) — financial/stock basket portfolio positions
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerInventory(Base):
    """Household basket goods held by a player.

    basket_name values match the approved marketplace basket catalog:
    essentials_basket, protein_basket, produce_basket, convenience_basket
    """

    __tablename__ = "player_inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    basket_name = Column(String(60), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    # In-game day this inventory row was first created.
    created_day = Column(Integer, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
