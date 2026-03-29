"""
BasketPriceHistory — immutable daily audit record of basket price index changes.

One row is created per (basket_id, day_number) pair each time the daily basket
price update is applied.  These rows are:
  - Append-only (never mutated after creation)
  - Used for frontend charting and economic debugging
  - The source of truth for "what was the price index on day N?"

Design principles:
  - A unique constraint on (basket_id, day_number) prevents double-updating
    the same basket on the same day.
  - All macro inputs that drove the change are captured at snapshot time so
    the row is fully self-contained and auditable without joins.

Economic intent:
  Providing visible history of price changes makes the economy legible to
  players.  When produce prices spike after a supply chain shock, players can
  see the daily progression in their frontend basket chart.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class BasketPriceHistory(Base):
    """Immutable snapshot of a basket's daily price index change.

    Created once per (basket_id, day_number) by apply_daily_basket_price_update().
    """

    __tablename__ = "basket_price_history"

    # Table-level uniqueness: one row per basket per day.
    __table_args__ = (
        UniqueConstraint("basket_id", "day_number", name="uq_basket_price_history_basket_day"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Which basket this row describes (e.g. "essentials", "protein").
    basket_id = Column(String(40), nullable=False, index=True)

    # The in-game day on which the price update was applied.
    day_number = Column(Integer, nullable=False, index=True)

    # Price index before today's update was applied.
    old_price_index = Column(Numeric(10, 4), nullable=False)

    # Price index after today's update was applied.
    new_price_index = Column(Numeric(10, 4), nullable=False)

    # The calculated daily change expressed as a fraction.
    # e.g. 0.0125 means +1.25%, -0.03 means -3%.
    # Capped at [-0.05, +0.05] by the engine.
    change_percent = Column(Numeric(10, 6), nullable=False)

    # ── Macro snapshot: the inputs that drove this change ─────────────────────
    # Captured at update time so the row is self-contained for auditing.

    inflation_used = Column(Numeric(10, 4), nullable=False)
    oil_index_used = Column(Numeric(10, 4), nullable=False)
    consumer_confidence_used = Column(Numeric(10, 4), nullable=False)
    supply_chain_stress_used = Column(Numeric(10, 4), nullable=False)

    # Optional human-readable note (e.g. "Supply chain shock event applied").
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
