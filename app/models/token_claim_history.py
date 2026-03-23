"""TokenClaimHistory — record of when players mark their token rewards as claimed.

Step 9: Monthly Reward Pool and Token Claim Accounting System.

Immutable audit record created each time a player claims their monthly
token allowance via the /rewards/claim endpoint.

transaction_reference is null in Step 9. It will be populated in a future
blockchain step once on-chain minting is wired up.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class TokenClaimHistory(Base):
    """Audit record of a player token claim event.

    claim_method values:
        "offchain_mark" — Step 9: player flags the allowance as claimed,
                          no blockchain transaction yet.
        "onchain"       — future step: actual on-chain minting confirmed.
    """

    __tablename__ = "token_claim_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Plain UUID column — no FK constraint for lightweight migrations.
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    month_index = Column(Integer, nullable=False, index=True)

    tokens_claimed = Column(Float, nullable=False)

    # Timestamp of the claim action.
    claim_timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # "offchain_mark" in Step 9; "onchain" in future blockchain step.
    claim_method = Column(String(30), nullable=False, default="offchain_mark")

    # Null in Step 9 — will store blockchain tx hash in future step.
    transaction_reference = Column(String(255), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
