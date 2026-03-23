"""app/models/contribution_event.py — Raw gameplay contribution event.

Every significant gameplay action that can contribute towards a player's
monthly PFT reward score creates one row here.  These raw events are later
aggregated by the monthly epoch finalisation process (Step 1 reward engine)
to produce ContributionSnapshot records and PFT allocations.

Design intent:
  - This table is WRITE-ONCE from the game engine's perspective.
  - Rows must NOT be modified after creation (audit trail).
  - The reward engine reads these rows at epoch close time.
  - Claiming / PFT minting never happens here.

Event types used in Step 2:
  job_work      — XGP earned through labour; xgp_value = earned amount

Future event types:
  business_profit  — net profit from owned business
  market_trade     — marketplace trade volume
  co_op_deal       — completed player-to-player co-operative deal
  penalty          — bad-behaviour deduction (negative xgp_value or units)
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class ContributionEvent(Base):
    """One raw contribution-producing gameplay event."""

    __tablename__ = "contribution_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Player ────────────────────────────────────────────────────────────────
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Event classification ──────────────────────────────────────────────────
    # job_work | business_profit | market_trade | co_op_deal | penalty
    event_type = Column(String(40), nullable=False, index=True)

    # ── Monetary value of this event in XGP ───────────────────────────────────
    # For job_work: XGP earned during the shift.
    # For penalties: negative value is acceptable.
    xgp_value = Column(Numeric(14, 4), nullable=False, default=0.0)

    # ── Unit quantity (type depends on event_type) ────────────────────────────
    # For job_work: hours worked.
    # For market_trade: number of trades.
    # For co_op_deal: number of deals completed.
    event_units = Column(Float, nullable=False, default=0.0)

    # ── Arbitrary structured metadata ─────────────────────────────────────────
    # Stored as a JSON string.  Contains event-specific context such as:
    #   { "job_id": "banker", "day_number": 42, "productivity_multiplier": 0.91 }
    # Using Text rather than JSON column for maximum DB compatibility.
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationship ──────────────────────────────────────────────────────────
    player = relationship("Player", foreign_keys=[player_id])
