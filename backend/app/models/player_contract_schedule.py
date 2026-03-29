"""Step 41: Player contract schedule — rolling per-player obligation cadence state."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PlayerContractSchedule(Base):
    """Rolling per-player contract/obligation schedule — one row per player (upsert).

    Stores the synthesised timing state for all recurring obligations and income
    events so that downstream services (borrowing, delinquency, reputation, planning)
    can read timing pressure without re-computing from raw sources every time.
    """

    __tablename__ = "player_contract_schedules"
    __table_args__ = (UniqueConstraint("player_id", name="uq_pcs_player"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- obligation summary counts ---
    active_contract_count = Column(Integer, nullable=False, default=0)
    # total weighted XGP due in next 7 game days
    total_due_7d_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    # due dates clustering: 'spread' | 'moderate' | 'clustered' | 'critical_cluster'
    clustering_label = Column(String(30), nullable=False, default="spread")

    # --- next major due window ---
    next_major_due_on = Column(Integer, nullable=True)        # game day number
    next_major_due_type = Column(String(60), nullable=True)   # obligation family
    days_to_next_major_due = Column(Integer, nullable=True)

    # --- income timing ---
    next_income_on = Column(Integer, nullable=True)           # game day number
    next_income_type = Column(String(40), nullable=True)      # salary | variable | business
    days_to_next_income = Column(Integer, nullable=True)

    # --- timing pressure scores 0–100 ---
    contract_density_score = Column(Numeric(8, 4), nullable=False, default=50)
    timing_stability_score = Column(Numeric(8, 4), nullable=False, default=50)
    # cash_gap: expected cash shortfall before next income event (positive = gap exists)
    cash_gap_before_next_income_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # --- label outputs ---
    timing_pressure_label = Column(String(30), nullable=False, default="manageable")
    # none | pre_payday_squeeze | obligation_cluster | structural_gap | critical
    bridge_need_label = Column(String(30), nullable=False, default="none")
    # none | minor | moderate | urgent
    obligation_collision_label = Column(String(30), nullable=False, default="none")
    # none | overlap | collision | compound

    # --- JSON payload for full recurring obligation map ---
    # e.g. {"rent": {"amount_xgp": 540, "cadence_days": 30, "next_due_on": 31},
    #        "salary": {"amount_xgp": 2400, "cadence_days": 14, "next_pay_on": 15}}
    recurring_obligation_map_json = Column(Text, nullable=True)
    income_cadence_json = Column(Text, nullable=True)
    due_window_json = Column(Text, nullable=True)
    debug_json = Column(Text, nullable=True)

    # --- flags ---
    false_payday_pressure = Column(Boolean, nullable=False, default=False)
    # True when timing pressure is temporary (pre-payday) not structural

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
