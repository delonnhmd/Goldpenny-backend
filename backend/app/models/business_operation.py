"""app/models/business_operation.py — Step 10: Immutable business run log.

One row is appended every time a player operates their business.
Rows are NEVER updated or deleted — this is a strict append-only ledger.

Each row captures the full economics of a single operation so that
profitability can be reconstructed and audited at any time:
  - Basket units consumed and their XGP cost at live prices
  - Revenue generated (already macro-adjusted in the engine)
  - Profit / loss = revenue - input_cost_xgp
  - Player cash snapshot before and after

balance_before / balance_after refer to player.cash (XGP).
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class BusinessOperation(Base):
    """Append-only record of one business operation cycle."""

    __tablename__ = "business_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    player_id   = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Matches PlayerBusiness.business_id / BusinessType.business_id.
    business_id = Column(String(40), nullable=False, index=True)

    day_number  = Column(Integer, nullable=False, index=True)
    hours_used  = Column(Integer, nullable=False)

    # ── Basket inputs consumed ────────────────────────────────────────────────
    produce_units    = Column(Integer, nullable=False, default=0)
    essentials_units = Column(Integer, nullable=False, default=0)
    protein_units    = Column(Integer, nullable=False, default=0)

    # ── Financial outcome ─────────────────────────────────────────────────────
    input_cost_xgp = Column(Numeric(12, 4), nullable=False)  # total basket cost
    revenue_xgp    = Column(Numeric(12, 4), nullable=False)  # macro-adjusted revenue
    profit_xgp     = Column(Numeric(12, 4), nullable=False)  # revenue - input_cost

    # ── Player-state delta ────────────────────────────────────────────────────
    stress_change  = Column(Integer, nullable=False, default=0)
    balance_before = Column(Numeric(12, 4), nullable=False)
    balance_after  = Column(Numeric(12, 4), nullable=False)

    # ── Step 11 balancing audit fields ───────────────────────────────────────
    # Stored so the frontend and debugging tools can explain exactly why
    # profit changed vs. a previous run: saturation, overhead, macro pressure.
    fixed_overhead_xgp            = Column(Numeric(12, 4), nullable=False, default=0)
    demand_multiplier             = Column(Numeric(8, 4),  nullable=False, default=1.0)
    saturation_penalty_multiplier = Column(Numeric(8, 4),  nullable=False, default=1.0)
    macro_margin_modifier         = Column(Numeric(8, 4),  nullable=False, default=0)
    final_margin_multiplier       = Column(Numeric(8, 4),  nullable=False, default=1.0)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
