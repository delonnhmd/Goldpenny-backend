"""app/models/firm.py — Step 14: Firm Layer foundation.

A Firm is the economic entity that employs workers, holds inventory, generates
revenue, and competes in regional product markets.

In MVP (Step 14), only NPC-owned firms exist.  They seed the market with
baseline supply and generate job openings that players can observe.
Player-owned firms are reserved for a future step.  The schema is fully
forward-compatible: set owner_type = "player" and owner_player_id to activate
player ownership when ready.

Economic context:
  Firms are the supply side of the Gold Penny economy.  NPC firms ensure
  markets never go empty — they provide competition and price anchoring.
  Player firms will eventually compete with NPC firms for market share,
  priced against the same macro parameters (confidence, oil, supply chain).

  distress_level (0–10): rises when cash flow is negative for consecutive days.
  At level 8+ the firm enters "distressed" status.
  Distress resets (decrements) when the firm returns to positive cash flow.

  cash_xgp: liquid capital available to pay bills, salaries, and inputs.
  retained_earnings_xgp: cumulative net profit kept inside the firm.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class Firm(Base):
    """An economic firm — NPC-owned, player-owned, or system-managed."""

    __tablename__ = "firms"

    # Integer PK for ergonomic REST references (e.g. /internal/firms/3).
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Stable UUID for cross-system references (ledger entries, contracts).
    firm_uid = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)

    # Human-readable name shown in admin views.
    name = Column(String(120), nullable=False)

    # Who controls this firm.
    # "npc"    — fully automated, engine-driven
    # "player" — player-owned (reserved; inactive in Step 14)
    # "system" — engine-managed market maker
    owner_type = Column(String(20), nullable=False, default="npc", index=True)

    # Set only when owner_type == "player".
    owner_player_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Which kind of business this firm operates.  Matches business_type.business_id.
    # e.g. "fruit_shop" / "food_truck"  (extensible — engine checks string, not enum)
    firm_type = Column(String(40), nullable=False, index=True)

    # Region where this firm operates.  Matches housing_regions.region_id.
    # e.g. "downtown" / "suburban"
    region = Column(String(40), nullable=False, index=True)

    # Tier level.  1 = starter.  Reserved for future upgrade mechanics.
    tier = Column(Integer, nullable=False, default=1)

    # Lifecycle status.
    # "active"     — fully operational
    # "distressed" — cash flow negative; still running but at risk
    # "closed"     — no longer operational (historical row)
    # "pending"    — registered but not yet operational (player onboarding)
    status = Column(String(20), nullable=False, default="active", index=True)

    # Reputation score (0–100).  Affects wage offers and demand multiplier.
    reputation = Column(Numeric(8, 4), nullable=False, default=50.0)

    # Current liquid cash available to the firm.
    cash_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Cumulative retained profit (revenue minus all costs since founding).
    retained_earnings_xgp = Column(Numeric(14, 2), nullable=False, default=0.0)

    # Distress counter 0–10.  Incremented per consecutive loss day.
    # Reset (decremented) when the firm has a net-positive day.
    distress_level = Column(Integer, nullable=False, default=0)

    # In-game day the firm was founded.
    created_day = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
