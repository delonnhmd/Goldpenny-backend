"""Cost accounting rows for real-world event generation."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class RealWorldGenerationCost(Base):
    """Per-event generation cost log used by the real-world circuit breaker."""

    __tablename__ = "realworld_generation_costs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(120), nullable=False, index=True)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    recorded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class CostBreakerAlert(Base):
    """Operator-facing alert emitted when the real-world cost breaker trips."""

    __tablename__ = "cost_breaker_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reason = Column(Text, nullable=False)
    monthly_cost_per_mau = Column(Numeric(10, 6), nullable=False)
    threshold_usd = Column(Numeric(10, 6), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
