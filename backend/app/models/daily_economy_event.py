"""Step 19 / 19.5: Daily economy event — one event per game day, with chain support."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class DailyEconomyEvent(Base):
    """One row per game day. Stores the selected event, its headline, impact tags, and chain state."""

    __tablename__ = "daily_economy_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = Column(Integer, nullable=False, unique=True, index=True)

    # ── Event identity ────────────────────────────────────────────────────────
    event_key = Column(String(80), nullable=False)
    headline = Column(String(300), nullable=False)
    summary = Column(Text, nullable=True)
    event_category = Column(String(40), nullable=False)  # energy, supply_chain, consumer, labor, ...
    sentiment = Column(String(20), nullable=False, default="neutral")  # negative, neutral, positive
    severity = Column(Numeric(6, 4), nullable=False, default=1.0)  # 0.0–3.0 scale

    # ── Structured impact ─────────────────────────────────────────────────────
    impact_tags_json = Column(Text, nullable=True)  # JSON list of {tag, direction, magnitude}

    # ── Source ────────────────────────────────────────────────────────────────
    source_type = Column(String(30), nullable=False, default="generated")  # generated | forced | recovery

    # ── Step 19.5: Chain fields ───────────────────────────────────────────────
    chain_id = Column(String(80), nullable=True, index=True)          # groups related events across days
    chain_position = Column(Integer, nullable=True, default=0)        # 0-based position in chain
    chain_length_expected = Column(Integer, nullable=True)            # estimated total chain length
    chain_stage = Column(String(20), nullable=True)                   # start|mid|escalation|peak|recovery|end
    parent_event_key = Column(String(80), nullable=True)              # previous event_key in chain
    continuation_probability = Column(Numeric(6, 4), nullable=True)   # probability chain continues
    decay_factor = Column(Numeric(6, 4), nullable=True)               # impact decay multiplier
    chain_debug_json = Column(Text, nullable=True)                    # chain selection debug info

    # ── Debug ─────────────────────────────────────────────────────────────────
    debug_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
