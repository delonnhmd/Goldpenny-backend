"""app/models/firm_policy.py — Step 14: Firm autonomous behavior policy.

FirmPolicy controls how a firm's internal economy engine makes decisions.
One row per firm (unique on firm_id).  Used by the NPC engine to:
  - decide when to open new job slots
  - adjust wages relative to market rate
  - determine how aggressively to restock inventory
  - decide when to take on debt vs. scale down

For NPC firms, these are set at seed time and can be tuned by admins.
For player-owned firms (future), these will be configurable via a player API.

hiring_aggressiveness (0.0–1.0):
  0.0 = never hire above minimum staffing
  1.0 = aggressively fill every capacity slot

wage_strategy:
  "market_rate"   — offer the macro-computed baseline wage
  "above_market"  — offer +20% to fill slots faster (higher payroll cost)
  "below_market"  — offer -20% (slower fill; reduces payroll expense)

inventory_buffer_target (0.0–1.0):
  Target fraction of storage capacity to keep filled as safety stock.
  0.2 = maintain 20% inventory buffer above zero.

debt_tolerance (0.0–1.0):
  Maximum debt-to-equity ratio the firm will accept.
  0.3 = borrow up to 30% of equity before refusing further debt.

expansion_threshold (XGP):
  Retained earnings level at which the engine will consider a capacity upgrade.
  Only relevant for future expansion mechanics.

is_active = False → policy row exists but is ignored; engine uses safe defaults.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class FirmPolicy(Base):
    """Behavioral policy governing a firm's autonomous economic decisions."""

    __tablename__ = "firm_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=False, unique=True, index=True)

    # 0.0 (passive) → 1.0 (aggressive): how quickly to open new job slots.
    hiring_aggressiveness = Column(Numeric(8, 4), nullable=False, default=0.5)

    # "market_rate" / "above_market" / "below_market"
    wage_strategy = Column(String(20), nullable=False, default="market_rate")

    # Target inventory buffer fraction of storage capacity (0.0–1.0).
    inventory_buffer_target = Column(Numeric(8, 4), nullable=False, default=0.20)

    # Maximum acceptable debt-to-equity ratio.
    debt_tolerance = Column(Numeric(8, 4), nullable=False, default=0.30)

    # Retained earnings level that triggers an expansion consideration.
    expansion_threshold = Column(Numeric(14, 2), nullable=False, default=5000.0)

    # False → policy is disabled; engine uses safe defaults for this firm.
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
