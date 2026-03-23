"""
BasketPurchase — immutable record of a player's goods basket purchase.

One row per purchase event.  This is the spending equivalent of XGPTransaction:
a permanent audit trail of every XGP outflow caused by basket buying.

Design rules:
  - Rows are WRITE-ONCE.  Never mutate after creation.
  - balance_before and balance_after must exactly mirror the XGPTransaction row
    created in the same DB transaction.
  - Serves as reference_id for the corresponding XGPTransaction.

Economic note:
  Basket spending is the first mandatory living cost in the game.
  These rows will later feed into:
    - daily health/stress recovery quality calculations
    - inflation demand signals
    - supply-chain business demand models
    - lifestyle lifestyle scoring for PFT contribution weighting
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class BasketPurchase(Base):
    """One basket purchase by a player on a given in-game day."""

    __tablename__ = "basket_purchases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Who bought it ─────────────────────────────────────────────────────────
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── What was bought ───────────────────────────────────────────────────────
    # basket_id matches GoodsBasket.id (string: essentials/protein/produce/convenience)
    basket_id = Column(String(40), nullable=False, index=True)

    # ── When (in-game time) ───────────────────────────────────────────────────
    day_number = Column(Integer, nullable=False, index=True)

    # ── Purchase details ──────────────────────────────────────────────────────
    # quantity: units purchased (fractional units allowed for future daily-rate billing)
    quantity = Column(Numeric(12, 4), nullable=False)

    # unit_price = base_price * (price_index / 100) at purchase time — locked in
    unit_price = Column(Numeric(12, 4), nullable=False)

    # total_cost = unit_price * quantity, rounded to 2 decimal places
    total_cost = Column(Numeric(14, 4), nullable=False)

    # XGP balance snapshots at the moment of purchase — must match XGPTransaction
    balance_before = Column(Numeric(14, 4), nullable=False)
    balance_after = Column(Numeric(14, 4), nullable=False)

    # Wall-clock time of the purchase
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    player = relationship("Player", foreign_keys=[player_id])
