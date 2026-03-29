"""Step 38 rolling per-player debt behavior state model."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerDebtBehaviorState(Base):
    """Rolling snapshot of a player's debt behavior profile (one row per player)."""

    __tablename__ = "player_debt_behavior_states"
    __table_args__ = (UniqueConstraint("player_id", name="uq_pdbs_player"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- core behavior scores (0–100) ---
    debt_dependency_score = Column(Numeric(8, 4), nullable=False, default=0)
    payment_stack_pressure_score = Column(Numeric(8, 4), nullable=False, default=0)
    borrowing_frequency_score = Column(Numeric(8, 4), nullable=False, default=0)
    financial_stability_score = Column(Numeric(8, 4), nullable=False, default=100)

    # --- directional trend ---
    trend_direction = Column(String(20), nullable=False, default="stable")  # improving / stable / deteriorating

    # --- state labels ---
    debt_state_label = Column(String(30), nullable=False, default="controlled")  # controlled / building pressure / unstable / spiral
    spiral_risk_label = Column(String(20), nullable=False, default="low")  # low / rising / high / critical
    recovery_stage = Column(String(20), nullable=False, default="none")  # none / early / stabilizing / rebuilding / strong

    # --- top drivers ---
    top_risk_driver = Column(String(80), nullable=True)
    top_recovery_driver = Column(String(80), nullable=True)

    # --- advisory data ---
    planning_warnings_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    # --- time tracking ---
    last_updated_on = Column(Integer, nullable=True)
    last_updated_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    player = relationship("Player", foreign_keys=[player_id])
