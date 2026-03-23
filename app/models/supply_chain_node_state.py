"""Step 43 — Supply Chain Node State DB model.

Stores per-day per-node override state for the 12 MVP physical supply chain
nodes.  When no override row exists for a given (node_key, day) pair the
graph service falls back to macro-derived defaults.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class SupplyChainNodeState(Base):
    __tablename__ = "supply_chain_node_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    node_key = Column(String(40), nullable=False)
    day = Column(Integer, nullable=False)

    # Availability inputs
    capacity = Column(Numeric(8, 4), nullable=False, default=1.0000)
    required = Column(Numeric(8, 4), nullable=False, default=1.0000)
    reliability = Column(Numeric(8, 4), nullable=False, default=1.0000)

    # Optional cost override (XGP per unit equivalent).  NULL = use computed.
    unit_cost_override = Column(Numeric(14, 4), nullable=True)

    # Region-specific availability modifiers (multiplicative)
    region_modifier_suburban = Column(Numeric(8, 4), nullable=False, default=1.0000)
    region_modifier_downtown = Column(Numeric(8, 4), nullable=False, default=1.0000)
    region_modifier_rural = Column(Numeric(8, 4), nullable=False, default=1.0000)

    # Audit
    notes = Column(Text, nullable=True)
    last_updated_on = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("node_key", "day", name="uq_scns_node_day"),
    )
