"""Step 19: Log of event impacts applied to macro state."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class DailyEconomyEventLog(Base):
    """Audit trail: records exactly what deltas were applied and the resulting macro state."""

    __tablename__ = "daily_economy_event_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = Column(Integer, nullable=False, index=True)
    event_key = Column(String(80), nullable=False)

    # ── Delta snapshots ───────────────────────────────────────────────────────
    pre_cap_deltas_json = Column(Text, nullable=True)   # raw deltas before bounding
    post_cap_deltas_json = Column(Text, nullable=True)  # deltas after bounding / clamping
    macro_before_json = Column(Text, nullable=True)     # macro state before event
    macro_after_json = Column(Text, nullable=True)      # macro state after event

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
