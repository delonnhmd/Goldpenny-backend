"""Step 38 per-player debt trend history (append-only rows)."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerDebtTrendHistory(Base):
    """One row per evaluation day capturing the player's debt behavior snapshot."""

    __tablename__ = "player_debt_trend_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day = Column(Integer, nullable=False, index=True)
    as_of_date = Column(Date, nullable=True)

    # score snapshot
    debt_dependency_score = Column(Numeric(8, 4), nullable=False, default=0)
    payment_stack_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    borrowing_frequency_score = Column(Numeric(8, 4), nullable=False, default=0)
    financial_stability_score = Column(Numeric(8, 4), nullable=False, default=100)

    # state at this point in time
    trend_direction = Column(String(20), nullable=False, default="stable")
    debt_state_label = Column(String(30), nullable=False, default="controlled")
    spiral_risk_label = Column(String(20), nullable=False, default="low")
    recovery_stage = Column(String(20), nullable=False, default="none")

    # combined composite risk score (debt_dependency + payment_stack + borrowing_frequency) / 3
    composite_risk_score = Column(Numeric(8, 4), nullable=False, default=0)

    # trigger signals recorded at this point
    trigger_signals_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    player = relationship("Player", foreign_keys=[player_id])
