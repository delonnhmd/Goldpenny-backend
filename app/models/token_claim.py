"""Token claim request record — placeholder for future on-chain execution.

No blockchain logic is triggered in Step 5.5. This model prepares the data
that a future claim contract step will consume.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class TokenClaim(Base):
    """One pending or completed claim request per player per month."""

    __tablename__ = "token_claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    month_key = Column(String(7), nullable=False, index=True)
    wallet_address = Column(String(255), nullable=False)
    requested_amount = Column(Float, nullable=False)
    approved_amount = Column(Float, nullable=False, default=0.0)
    # tx_hash is null until an on-chain step is executed in a future step.
    tx_hash = Column(String(255), nullable=True)
    # Statuses: pending → approved → rejected → submitted_onchain → confirmed
    status = Column(String(30), nullable=False, default="pending")
    requested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
