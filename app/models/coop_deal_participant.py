"""app/models/coop_deal_participant.py — Step 13: Co-op Deals System.

CoopDealParticipant links a player to a specific co-op deal in a specific role.

One row per (deal_id, player_id) pair.  The UniqueConstraint prevents a player
from joining the same deal twice, enforcing the anti-exploit rule at the
database level as a second line of defense behind the engine-level check.

Role assignment is first-come, first-qualified — deterministic and non-negotiable
in MVP.  A player fills whichever unfilled role they qualify for; they cannot
choose a role they are not qualified for.

Economic context:
  The participant row is the binding contract for the deal.  Once a player joins,
  their split_percent is locked.  They receive exactly that fraction of the
  final_payout_xgp when complete_coop_deal() is called.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, UniqueConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class CoopDealParticipant(Base):
    """One player's participation record in a single co-op deal."""

    __tablename__ = "coop_deal_participants"

    __table_args__ = (
        # Hard constraint: one participation row per player per deal.
        UniqueConstraint("deal_id", "player_id", name="uq_cdp_deal_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    deal_id = Column(Integer, ForeignKey("coop_deals.id"), nullable=False, index=True)

    # The participating player (logical FK — no cascade constraint for portability).
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Which role this player fills in the deal.
    # e.g. "chef" | "delivery_driver" | "auto_mechanic" | "fruit_shop_owner"
    role_id = Column(String(60), nullable=False, index=True)

    # This participant's share of final_payout_xgp (0–100).
    # All split_percent values across participants for a deal sum to 100.
    split_percent = Column(Float, nullable=False)

    # True for the player who created (hosted) the deal.
    is_host = Column(Boolean, nullable=False, default=False)

    # Flipped to True when complete_coop_deal() credits this player's cash.
    is_paid = Column(Boolean, nullable=False, default=False)

    joined_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
