"""app/models/market_trade.py — Step 12: Multiplayer Marketplace trade record.

Immutable append-only log of every Step 12 player-to-player marketplace trade.

Unlike MarketTransaction (Step 8.5 physical inventory trades), MarketTrade
records abstract goods / service exchanges that are not tied to physical
player inventory.  The distinction matters because:

  - Step 8.5 trades remove real BasketInventory units and include return-on-cancel.
  - Step 12 trades are abstract marketplace units (economic abstraction layer).
    Future steps may connect Step 12 listings to actual business output.

Both tables coexist.  Step 12 API endpoints (POST /marketplace/purchase) write
to market_trades; Step 8.5 endpoints (POST /marketplace/buy) write to
market_transactions.

Economic context:
  gross_amount_xgp = quantity × unit_price_xgp
  market_fee_xgp   = 2% × gross_amount_xgp   (economic sink)
  seller_net_xgp   = gross_amount_xgp − market_fee_xgp
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class MarketTrade(Base):
    """Immutable record of one completed Step 12 marketplace purchase.

    Rows are NEVER updated or deleted.
    """

    __tablename__ = "market_trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Listing that was partially or fully consumed in this trade.
    listing_id       = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Both parties stored as plain UUIDs (no FK constraint for lightweight migrations).
    seller_player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    buyer_player_id  = Column(UUID(as_uuid=True), nullable=False, index=True)

    # ── Listing metadata snapshot ─────────────────────────────────────────────
    # Stored here so the history remains intelligible even if listing is deleted.
    listing_type = Column(String(20), nullable=False, index=True)  # "goods" | "service"
    item_id      = Column(String(40), nullable=False, index=True)   # essentials / mechanic_service / etc.

    # ── Trade quantities and pricing ──────────────────────────────────────────
    quantity         = Column(Numeric(12, 4), nullable=False)
    unit_price_xgp   = Column(Numeric(12, 2), nullable=False)
    gross_amount_xgp = Column(Numeric(12, 2), nullable=False)

    # 2% market fee — sunk from circulation as economic pressure.
    market_fee_xgp   = Column(Numeric(12, 2), nullable=False)

    # Seller receives gross minus market fee.
    seller_net_xgp   = Column(Numeric(12, 2), nullable=False)

    # ── Balance snapshots ─────────────────────────────────────────────────────
    # Captured immediately before the trade is committed so the ledger is
    # fully auditable without needing to replay all prior transactions.
    buyer_balance_before  = Column(Numeric(12, 2), nullable=False)
    buyer_balance_after   = Column(Numeric(12, 2), nullable=False)
    seller_balance_before = Column(Numeric(12, 2), nullable=False)
    seller_balance_after  = Column(Numeric(12, 2), nullable=False)

    # In-game day on which the trade occurred.
    day_number = Column(Integer, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
