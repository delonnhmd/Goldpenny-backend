"""app/models/housing_payment.py — Step 7: Immutable housing payment audit log.

One row per successful daily housing deduction.
Rows are NEVER mutated after creation — they exist to:
  - Provide a complete, auditable trail of every housing cost paid.
  - Allow the settlement engine to detect already-paid days (idempotency).
  - Support future analytics (average housing burden, region distribution).

Economic note:
  Housing is the first fixed recurring cost layer in the game.
  Every payment here is paired with an XGPTransaction row so both the
  housing ledger and the XGP ledger remain consistent.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class HousingPayment(Base):
    """Immutable record of a single daily housing cost deduction."""

    __tablename__ = "housing_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The player who paid.
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The region_id the player occupied when this payment was made.
    # Stored directly (not FK) so that historical records are preserved even if
    # the region definition changes.
    region_id = Column(String(40), nullable=False, index=True)

    # The in-game day for which this payment applies.
    day_number = Column(Integer, nullable=False, index=True)

    # XGP deducted this day.  Always positive (> 0).
    amount = Column(Numeric(10, 2), nullable=False)

    # Player XGP balance immediately before and after deduction.
    # Together with amount these three columns are independently verifiable.
    balance_before = Column(Numeric(14, 4), nullable=False)
    balance_after = Column(Numeric(14, 4), nullable=False)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    player = relationship("Player", foreign_keys=[player_id])
