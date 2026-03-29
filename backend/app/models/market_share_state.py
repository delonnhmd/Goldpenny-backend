"""app/models/market_share_state.py — Step 14: Regional market share tracking.

One row per (day, region, product_type) captures the aggregate supply picture:
  - How much NPC firms are supplying
  - How much player sources are supplying (future; capped at 15%)
  - Average price index for the product in this region
  - How much demand was unmet (signals market opportunity for new entrants)

product_type is derived from firm_type:
  "fruit_shop" → "produce"
  "food_truck"  → "food"

firm_shares_json: JSON-encoded list of {firm_id, firm_type, supply_value, share_pct}
  representing each firm's fractional share of total supply for this product_type
  in this region on this day.  Serialized to avoid a pivot table for MVP.

Design constraint:
  Player firm supply is capped at PLAYER_FIRM_IMPACT_CAP (15%) of regional
  total supply per product_type.  This prevents single-player market dominance.
  The engine enforces this cap when computing total_player_supply.
"""

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func

from app.db.database import Base


class MarketShareState(Base):
    """Daily snapshot of regional product market supply and demand."""

    __tablename__ = "market_share_states"

    __table_args__ = (
        UniqueConstraint(
            "day", "region", "product_type",
            name="uq_market_share_day_region_product",
        ),
    )

    # Integer PK for ordering and pagination queries.
    id = Column(Integer, primary_key=True, autoincrement=True)

    # In-game day this row covers.
    day = Column(Integer, nullable=False, index=True)

    # Region identifier.  e.g. "downtown" / "suburban"
    region = Column(String(40), nullable=False, index=True)

    # Product category this row tracks.  e.g. "produce" / "food"
    product_type = Column(String(60), nullable=False, index=True)

    # Total supply contributed by NPC and system firms this day.
    total_npc_supply = Column(Numeric(14, 4), nullable=False, default=0.0)

    # Total supply contributed by player sources this day.
    # Engine caps this at PLAYER_FIRM_IMPACT_CAP of (npc + player) total.
    total_player_supply = Column(Numeric(14, 4), nullable=False, default=0.0)

    # Weighted average price index across all supply sources (1.0 = baseline).
    average_price_index = Column(Numeric(10, 4), nullable=False, default=1.0)

    # Units of demand that no firm could fulfill.  Signals market opportunity.
    unmet_demand = Column(Numeric(14, 4), nullable=False, default=0.0)

    # JSON: list of {firm_id, firm_type, supply_value, share_pct}.
    firm_shares_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
