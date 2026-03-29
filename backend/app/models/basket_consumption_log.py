"""BasketConsumptionLog – per-player, per-day refined basket spending record.

One row per player per in-game day.  Written by the consumption behavior
service during settlement (or on-demand compute).  A unique constraint on
(player_id, day) enforces idempotency so the same day is never double-logged.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class BasketConsumptionLog(Base):
    __tablename__ = "basket_consumption_logs"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "day", name="uq_basket_consumption_log_player_day"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(Integer, nullable=False, index=True)

    # ── Basket spend outputs (Decimal-safe, quantized to 2dp) ─────────────────
    essentials_spend_xgp = Column(Numeric(12, 2), nullable=False, default=0)
    protein_spend_xgp = Column(Numeric(12, 2), nullable=False, default=0)
    produce_spend_xgp = Column(Numeric(12, 2), nullable=False, default=0)
    convenience_spend_xgp = Column(Numeric(12, 2), nullable=False, default=0)
    total_spend_xgp = Column(Numeric(12, 2), nullable=False, default=0)

    # ── Behavioral pressure scores (0.0 – 1.0 range unless noted) ────────────
    budget_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    stress_spend_modifier = Column(Numeric(8, 4), nullable=False, default=1)
    nutrition_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)

    # ── Free-form explainability payload ─────────────────────────────────────
    notes_json = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    player = relationship("Player", foreign_keys=[player_id])
