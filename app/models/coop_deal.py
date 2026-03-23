"""app/models/coop_deal.py — Step 13: Co-op Deals System.

CoopDeal stores each active or historical co-op deal opportunity.

One row is created when a host player opens a deal.  The row tracks the full
lifecycle:  open → filled → completed  (or expired / cancelled).

Economic context:
  Deals are short-lived collaboration windows — they expire after 1 in-game day
  if all required roles are not filled in time.  This creates urgency without
  the complexity of escrow or dispute resolution.

  If fully filled, the deal can be completed and XGP is distributed atomically.
  If it expires unfilled, no payout occurs and the host's failed count increments.

  final_payout_xgp may differ from base_payout_xgp after macro adjustment.
  The adjustment is applied at completion time using the current MacroState.
"""

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, func

from app.db.database import Base


class CoopDeal(Base):
    """One co-op deal opportunity, created by a host player."""

    __tablename__ = "coop_deals"

    # Integer PK for ergonomic API usage (e.g. {"deal_id": 14}).
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Which template this deal was generated from.
    template_id = Column(String(60), nullable=False, index=True)

    # Copied from template at creation time so history is fully self-contained
    # even if the template is later renamed or deactivated.
    display_name = Column(String(120), nullable=False)

    # UUID of the hosting player, stored as string for portability.
    # Null is not expected in practice but nullable for safety.
    host_player_id = Column(String(36), nullable=True, index=True)

    # Lifecycle status.
    # open      — waiting for more participants
    # filled    — all required roles assigned; awaiting completion call
    # completed — deal executed, payout distributed
    # expired   — expiry day passed before all roles were filled
    # cancelled — future feature; reserved
    status = Column(String(20), nullable=False, default="open", index=True)

    # Snapshot of required roles at creation time (JSON list).
    # e.g. '["chef", "delivery_driver"]'
    # Stored to keep history self-contained regardless of template changes.
    required_roles_json = Column(Text, nullable=False)

    # The specific split preset chosen by the host.  e.g. '[50,50]'
    # Must be one of template.allowed_split_presets_json at creation time.
    assigned_split_json = Column(Text, nullable=False)

    # Base payout from template (pre macro-adjustment).
    base_payout_xgp = Column(Numeric(10, 2), nullable=False)

    # Macro-adjusted payout assigned when the deal is completed.
    # Zero until then.
    final_payout_xgp = Column(Numeric(10, 2), nullable=False, default=0)

    # Copied from template — hours each player must contribute.
    hours_required_per_participant = Column(Integer, nullable=False, default=2)

    # Optional region context copied from template.
    region_bias = Column(String(40), nullable=True)

    # In-game day on which this deal instance was created.
    created_day_number = Column(Integer, nullable=False, index=True)

    # In-game day on which this deal stops accepting new participants.
    # MVP: current_day + 1 at creation time.
    expires_day_number = Column(Integer, nullable=False, index=True)

    # In-game day on which payout was distributed.  Null until then.
    completed_day_number = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
