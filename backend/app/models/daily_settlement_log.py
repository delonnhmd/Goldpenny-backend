"""
DailySettlementLog — immutable audit record of a player's end-of-day settlement.

One row is written per player per settled day.  These rows are never mutated
after creation; they exist for:
  - Auditing daily lifecycle transitions
  - Future UI "day summary" screens
  - Reward engine analytics (how many days did a player actively play?)
  - Debugging player health / stress / economy trajectories
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class DailySettlementLog(Base):
    __tablename__ = "daily_settlement_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to the player who settled.
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # In-game day that was settled.
    day_number = Column(Integer, nullable=False, index=True)
    day = synonym("day_number")

    # ── Hours ─────────────────────────────────────────────────────────────────
    # hours before reset = hours_available at settlement time (i.e. remaining)
    # hours after reset  = always 24 for now (calculate_next_day_hours())
    hours_before_reset = Column(Integer, nullable=False)
    hours_after_reset = Column(Integer, nullable=False)

    # ── Stress ────────────────────────────────────────────────────────────────
    stress_before = Column(Integer, nullable=False)
    stress_after = Column(Integer, nullable=False)

    # ── Health ────────────────────────────────────────────────────────────────
    health_before = Column(Integer, nullable=False)
    health_after = Column(Integer, nullable=False)

    # ── Finances ──────────────────────────────────────────────────────────────
    # Settlement may change XGP through recurring costs (e.g. housing).
    # cash_before/cash_after capture that full end-of-day transition.
    cash_before = Column(Numeric(14, 4), nullable=False)
    cash_after = Column(Numeric(14, 4), nullable=False)
    ending_cash_xgp = synonym("cash_after")

    # Core daily accounting fields.
    income_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    expenses_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    stock_pnl_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_paid_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    health_change = Column(Integer, nullable=False, default=0)
    stress_change = Column(Integer, nullable=False, default=0)

    # True in all normal settlements; False only if recovery was skipped.
    recovery_applied = Column(Boolean, nullable=False, default=True)

    # ── Step 6: Daily needs quality fields ───────────────────────────────────
    # These fields let the frontend explain why recovery was better or worse.
    # They are written atomically with the rest of the settlement log row.

    # Combined daily needs score (0–2+ range).  0 = bought nothing.
    needs_score = Column(Numeric(8, 4), nullable=False, default=0)

    # Tier: poor / weak / adequate / good / excellent.
    needs_tier = Column(Text, nullable=True)

    # Summary signal: negative = quality penalty, positive = quality bonus.
    # Not directly applied to stats; used by the frontend to surface why
    # recovery was modified.
    food_quality_modifier = Column(Integer, nullable=False, default=0)

    # Positive = extra stress added to settlement (poor needs coverage).
    # Negative = bonus stress relief (good needs coverage).
    stress_penalty_from_needs = Column(Integer, nullable=False, default=0)

    # Positive = extra health gain at settlement.
    # Negative = additional health loss at settlement.
    health_modifier_from_needs = Column(Integer, nullable=False, default=0)

    # ── Step 7: Housing cost fields ──────────────────────────────────────────
    # Populated at settlement time by apply_daily_housing_cost().
    # housing_stress_modifier: the effective stress delta applied this day.
    #   Paid suburban: -1  |  Paid downtown: +2
    #   Unpaid suburban: +3  |  Unpaid downtown: +5
    #   No region: 0
    housing_region_id = Column(Text, nullable=True)
    housing_cost_paid = Column(Numeric(10, 2), nullable=False, default=0)
    housing_stress_modifier = Column(Integer, nullable=False, default=0)

    # Step 8: side-income settlement snapshot.
    side_income_hours = Column(Numeric(12, 4), nullable=False, default=0)
    side_income_net_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # Step 16: life consequences settlement snapshot.
    total_hours_used = Column(Numeric(12, 4), nullable=False, default=0)
    overtime_hours = Column(Numeric(12, 4), nullable=False, default=0)
    sleep_hours = Column(Numeric(12, 4), nullable=False, default=7)
    recovery_hours = Column(Numeric(12, 4), nullable=False, default=1)
    productivity_modifier = Column(Numeric(8, 4), nullable=False, default=1)
    burnout_risk = Column(Numeric(8, 4), nullable=False, default=0)
    medical_event_risk = Column(Numeric(8, 4), nullable=False, default=0)
    medical_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    missed_work_penalty_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # Step 17: housing/region full-integration settlement snapshot.
    region_key = Column(Text, nullable=True)
    housing_cost_daily_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    utilities_cost_daily_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    commute_hours = Column(Numeric(12, 4), nullable=False, default=0)
    commute_fuel_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    region_stress_delta = Column(Numeric(8, 4), nullable=False, default=0)
    region_opportunity_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    region_business_demand_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    region_side_income_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    networking_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    opportunity_quality_signal = Column(Numeric(8, 4), nullable=False, default=1)

    # Step 15: business settlement component totals.
    business_revenue_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_cogs_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_overhead_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_spoilage_loss_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_fuel_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_maintenance_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    business_net_profit_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # Step 20: debt trap + recovery arc settlement fields.
    debt_payment_due_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_payment_paid_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_payment_missed = Column(Boolean, nullable=False, default=False)
    late_fee_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    accrued_interest_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    credit_score_before = Column(Integer, nullable=False, default=650)
    credit_score_after = Column(Integer, nullable=False, default=650)
    credit_score_delta = Column(Integer, nullable=False, default=0)
    distress_state_before = Column(Text, nullable=False, default="stable")
    distress_state_after = Column(Text, nullable=False, default="stable")
    distress_score_before = Column(Numeric(8, 4), nullable=False, default=0)
    distress_score_after = Column(Numeric(8, 4), nullable=False, default=0)
    borrowing_cost_modifier = Column(Numeric(8, 4), nullable=False, default=1)
    opportunity_access_penalty = Column(Numeric(8, 4), nullable=False, default=0)
    business_risk_penalty = Column(Numeric(8, 4), nullable=False, default=0)
    career_progress_penalty = Column(Numeric(8, 4), nullable=False, default=0)
    recovery_actions_applied_json = Column(Text, nullable=True)
    distress_driver_json = Column(Text, nullable=True)

    # JSON summary stored as text for portability.
    # Contains: worked_today, stress_recovery, health_recovery,
    #           hours_reset, current_day, needs_summary dict,
    #           housing_summary dict (Step 7),
    #           and side_income_summary dict (Step 8).
    summary_json = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    player = relationship("Player", back_populates="settlement_logs", foreign_keys=[player_id])
