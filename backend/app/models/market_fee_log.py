"""MarketFeeLog — record of sunk marketplace transaction fees.

Step 8.5: Multiplayer Marketplace and Player-to-Player Commerce System.

The 5% marketplace fee is NOT transferred to any player. It is sunk from
circulation as an inflation-control mechanism. This table tracks every fee
event for economy balancing and a future system treasury if needed.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class MarketFeeLog(Base):
    """Sunk marketplace fee record for a completed transaction.

    fee_type:
        "marketplace_transaction_fee" — standard 5% fee on gross sale value
    """

    __tablename__ = "market_fee_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Plain UUID columns — no FK constraints for lightweight migrations.
    transaction_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    listing_id = Column(UUID(as_uuid=True), nullable=False)

    fee_amount = Column(Numeric(12, 2), nullable=False)
    fee_rate = Column(Float, nullable=False)  # e.g. 0.05

    # "marketplace_transaction_fee"
    fee_type = Column(String(40), nullable=False, default="marketplace_transaction_fee")

    created_day = Column(Integer, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
