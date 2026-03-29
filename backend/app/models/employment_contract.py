"""app/models/employment_contract.py — Step 14: Firm employment contracts.

An EmploymentContract binds a worker (NPC or player) to a firm for a defined
or open-ended period.

In Step 14, all contracts are NPC-to-NPC (fictional workers).  They exist to
make firm economics legible and testable before player hiring goes live.

pay_type controls how payroll ledger entries are generated:
  "hourly"   — pay = pay_rate × expected_hours per in-game day
  "daily"    — pay = pay_rate once per in-game day (flat daily wage)
  "monthly"  — pay = pay_rate once per 30 in-game days (reserved)
  "contract" — pay = pay_rate once when active_to_day is reached (milestone)

active_to_day = None → open-ended (ongoing employment until cancelled).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class EmploymentContract(Base):
    """Binding agreement between a firm and a worker (NPC or player)."""

    __tablename__ = "employment_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=False, index=True)

    # "npc" — automated fictional worker; "player" — real player account
    worker_type = Column(String(20), nullable=False, default="npc")

    # Set only when worker_type == "player".
    worker_player_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Role this worker fulfills (matches job_type strings).
    job_type = Column(String(60), nullable=False)

    # "hourly" / "daily" / "monthly" / "contract"
    pay_type = Column(String(20), nullable=False, default="daily")

    # Base pay rate (interpretation depends on pay_type).
    pay_rate_xgp = Column(Numeric(10, 2), nullable=False, default=0.0)

    # Expected working hours per day.  Used for hourly pay calculation.
    expected_hours = Column(Numeric(8, 2), nullable=True)

    # In-game day the contract became active.
    active_from_day = Column(Integer, nullable=False)

    # In-game day the contract ends.  Null = open-ended.
    active_to_day = Column(Integer, nullable=True)

    # "active" / "ended" / "suspended"
    status = Column(String(20), nullable=False, default="active", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
