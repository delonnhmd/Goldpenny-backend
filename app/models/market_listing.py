"""MarketListing — a player-created listing on the multiplayer marketplace.

Step 8.5: Multiplayer Marketplace and Player-to-Player Commerce System.

Inventory is removed from the source at listing creation time (preferred MVP
approach — no double-spend possible). Returns on cancel or expiration.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class MarketListing(Base):
    """A marketplace listing created by a player seller.

    source_type:
        "player_inventory"   — goods from the player's household inventory
        "business_inventory" — goods from a player-owned business
        "step12"             — Step 12 abstract goods / services listing (no physical inventory)

    listing_status:
        "active"    — accepting purchases
        "sold_out"  — all units sold
        "cancelled" — cancelled by seller, goods returned (Step 8.5 only)
        "expired"   — listing duration elapsed

    listing_type (Step 12):
        "goods"   — abstract goods unit (essentials / protein / produce / convenience)
        "service" — abstract service unit (mechanic_service / delivery_service / cooking_service)
        None      — legacy Step 8.5 listing (use basket_name field instead)
    """

    __tablename__ = "market_listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Seller identity — plain UUID column, no FK constraint for lightweight migrations.
    seller_player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # "player_inventory" | "business_inventory" | "step12"
    source_type = Column(String(30), nullable=False)
    # Populated only when source_type == "business_inventory".
    source_business_id = Column(UUID(as_uuid=True), nullable=True)

    basket_name = Column(String(60), nullable=False, index=True)

    quantity_total = Column(Integer, nullable=False)
    quantity_remaining = Column(Integer, nullable=False)

    unit_price = Column(Numeric(12, 2), nullable=False)

    # "active" | "sold_out" | "cancelled" | "expired"
    listing_status = Column(String(20), nullable=False, default="active", index=True)

    # Seller region at time of listing. Stored for future shipping/transport cost expansion.
    region = Column(String(40), nullable=False, default="suburban")

    created_day = Column(Integer, nullable=False)
    # Listing expires at the start of this in-game day.
    expires_day = Column(Integer, nullable=False, index=True)

    # ── Step 12 fields ────────────────────────────────────────────────────
    # listing_type distinguishes Step 12 abstract listings from Step 8.5 physical ones.
    # None on all pre-Step-12 rows.
    listing_type = Column(String(20), nullable=True, index=True)  # "goods" | "service"

    # Canonical item identifier for Step 12 listings.
    # Goods: essentials | protein | produce | convenience
    # Services: mechanic_service | delivery_service | cooking_service
    item_id = Column(String(40), nullable=True, index=True)

    # Upfront anti-spam listing fee paid by seller at listing creation.
    # Formula: max(1.0, gross_listing_value * 0.01)  i.e. 1%, min 1 XGP.
    listing_fee_xgp = Column(Numeric(10, 2), nullable=False, default=0)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
