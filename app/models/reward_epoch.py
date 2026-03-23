"""app/models/reward_epoch.py — Monthly PFT reward epoch.

Each row represents one calendar month of the PFT reward cycle.
The epoch is created at the start of a month, accumulates contribution
snapshots during the month, and is finalised at month end to trigger
allocation calculations.

Claiming remains disabled during Step 1.  The table is designed so that
adding on-chain claim integration in a later step requires no schema change.
"""

import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RewardEpoch(Base):
    """One monthly PFT distribution epoch."""

    __tablename__ = "reward_epochs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Season number allows rule-set versioning without breaking epoch history.
    season_number = Column(Integer, nullable=False, index=True)

    # Human-readable label, e.g. "2026-03". Optional convenience field.
    label = Column(String(20), nullable=True)

    # Inclusive epoch window.
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    # Total PFT (in token units) available for distribution this epoch.
    # Stored as BigInteger to accommodate large supply numbers without
    # floating-point precision loss.  Use Numeric for sub-unit precision
    # if fractional allocation is needed.
    reward_pool = Column(Numeric(20, 8), nullable=False)

    # True once the epoch is locked and allocations are computed.
    # Re-finalising an already-finalised epoch is rejected by the API.
    is_finalized = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
