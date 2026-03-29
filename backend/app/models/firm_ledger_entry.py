"""app/models/firm_ledger_entry.py — Step 14: Firm accounting ledger.

Every XGP flow in or out of a firm is recorded as a FirmLedgerEntry.
This is the firm-level equivalent of XGPTransaction (player-level flows).

Rows are immutable once created.  The engine sums them to determine net daily
cash flow and decide whether distress_level should increment or recover.

category taxonomy:
  "revenue"      — sales income
  "cogs"         — cost of goods sold (inputs purchased)
  "payroll"      — worker wages (NPC or future player)
  "rent"         — daily location rent
  "maintenance"  — capacity maintenance cost
  "fuel"         — delivery vehicle fuel (food_truck-relevant)
  "utilities"    — fixed running overhead
  "debt_service" — interest + principal payment
  "fees"         — marketplace / licensing fees
  "tax"          — local business tax
  "misc"         — catch-all for unclassified flows

direction: "inflow" (cash received) or "outflow" (cash paid).
amount_xgp is always stored positive; direction encodes the sign.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class FirmLedgerEntry(Base):
    """Immutable daily accounting entry for one firm."""

    __tablename__ = "firm_ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=False, index=True)

    # In-game day this entry applies to.
    day = Column(Integer, nullable=False, index=True)

    # Revenue / cost category.
    category = Column(String(30), nullable=False, index=True)

    # "inflow" / "outflow"
    direction = Column(String(10), nullable=False)

    # Gross amount (always positive; direction encodes the sign).
    amount_xgp = Column(Numeric(14, 2), nullable=False)

    # Optional pointer to the source event (e.g. "coop_deal" + deal_id).
    reference_type = Column(String(60), nullable=True)
    reference_id = Column(String(80), nullable=True)

    # Human-readable annotation for admin / audit views.
    memo = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
