"""
PlayerDailyState — per-player, per-day state snapshot.

One row per player per in-game day.  The settlement engine writes the final
values here at end-of-day and uses it to enforce the idempotency rule
(a player cannot settle the same day twice).

Unique constraint on (player_id, day_number) prevents duplicate rows.
"""

import uuid

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class PlayerDailyState(Base):
    __tablename__ = "player_daily_states"

    # One row per player per in-game day — duplicates are prevented by the
    # unique constraint at the bottom of this class.
    __table_args__ = (
        UniqueConstraint("player_id", "day_number", name="uq_player_daily_state_player_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to the players table.
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # In-game day this row describes.
    day_number = Column(Integer, nullable=False, index=True)
    # Core-schema compatibility alias.
    day = synonym("day_number")

    # ── Hours ─────────────────────────────────────────────────────────────────
    # hours_available_start: hours at the start of the day (before any work).
    # hours_available_end:   hours remaining at settlement time.
    # These reset to 24 each new day through the settlement process, not
    # automatically — time must be "earned back" by closing the day.
    hours_available_start = Column(Integer, nullable=False, default=24)
    hours_available_end = Column(Integer, nullable=False, default=24)

    # ── Work flags ────────────────────────────────────────────────────────────
    # True once the player has completed at least one main-job shift today.
    worked_main_job = Column(Boolean, nullable=False, default=False)
    did_work = Column(Boolean, nullable=False, default=False)
    missed_shift = Column(Boolean, nullable=False, default=False)
    shift_start = Column(DateTime(timezone=True), nullable=True)
    shift_end = Column(DateTime(timezone=True), nullable=True)
    salary_earned = Column(Numeric(14, 4), nullable=False, default=0)
    missed_penalty = Column(Numeric(14, 4), nullable=False, default=0)
    meals_recorded = Column(Integer, nullable=False, default=0)
    survival_penalty_applied = Column(Boolean, nullable=False, default=False)
    dinner_resolved = Column(Boolean, nullable=False, default=False)
    dinner_mode = Column(Text, nullable=True)
    dinner_cost = Column(Numeric(14, 4), nullable=False, default=0)
    food_debt_added = Column(Numeric(14, 4), nullable=False, default=0)
    night_eat_reminder_shown = Column(Boolean, nullable=False, default=False)
    dinner_resolved_at = Column(DateTime(timezone=True), nullable=True)
    # Core daily tracking metrics.
    worked_hours = Column(Integer, nullable=False, default=0)
    gross_income_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # True once the player has successfully settled this day.
    # Settlement is idempotent: once True, a second POST /daily/settle is rejected.
    did_settlement = Column(Boolean, nullable=False, default=False)

    # ── Vitals snapshots ──────────────────────────────────────────────────────
    # *_start  = player stat value when the day opened (or when this row was created)
    # *_end    = player stat value at settlement time
    stress_start = Column(Integer, nullable=False, default=0)
    stress_end = Column(Integer, nullable=False, default=0)
    health_start = Column(Integer, nullable=False, default=100)
    health_end = Column(Integer, nullable=False, default=100)

    # ── Finances ──────────────────────────────────────────────────────────────
    # cash is used as the XGP balance field throughout the codebase.
    cash_start = Column(Numeric(14, 4), nullable=False, default=0)
    cash_end = Column(Numeric(14, 4), nullable=False, default=0)

    # ── Step 4: Daily basket consumption trackers ─────────────────────────────
    # These fields accumulate throughout the day as the player buys goods
    # baskets.  They are NOT reset inside buy_basket — each purchase adds to
    # the running total.  They reset naturally when a new PlayerDailyState row
    # is created for the next day.
    #
    # Later steps use these values for:
    #   - Recovery quality (did the player eat essentials/protein today?)
    #   - Inflation demand signal (aggregate basket demand per day)
    #   - Lifestyle scoring (contributes to PFT contribution weight)
    essentials_units = Column(Numeric(12, 4), nullable=False, default=0)
    protein_units = Column(Numeric(12, 4), nullable=False, default=0)
    produce_units = Column(Numeric(12, 4), nullable=False, default=0)
    convenience_units = Column(Numeric(12, 4), nullable=False, default=0)

    # Running XGP total spent on baskets today (all basket types combined).
    # Updated atomically within the basket purchase transaction.
    total_spent_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_payment_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    stock_realized_pnl_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # ── Step 6: Daily needs evaluation ─────────────────────────────────────────
    # Populated at settlement time by the needs engine.  Zero/None before
    # the player settles the day.
    #
    # daily basket spending now affects personal wellbeing:
    #   - skipping essentials causes stress penalty and health pressure
    #   - convenience-only living is mediocre (not catastrophic but worse)
    #   - essentials + protein + produce gives modest recovery improvement

    # Combined needs score (survival * 0.65 + quality * 0.35).  Roughly 0–2+.
    needs_score = Column(Numeric(8, 4), nullable=False, default=0)

    # Tier label: poor / weak / adequate / good / excellent
    needs_tier = Column(Text, nullable=True)

    # True once needs have been evaluated during settlement.
    needs_evaluated = Column(Boolean, nullable=False, default=False)

    # Sub-scores stored separately for analytics and frontend hints.
    food_quality_score = Column(Numeric(8, 4), nullable=False, default=0)
    survival_coverage_score = Column(Numeric(8, 4), nullable=False, default=0)

    # ── Step 7: Daily housing cost snapshot ─────────────────────────────────
    # Written at settlement time from the housing engine result.
    # housing_cost_paid = 0 when: player has no region, or balance was too low.
    # housing_region_id mirrors player.housing_region_id at settlement time.
    housing_cost_paid = Column(Numeric(10, 2), nullable=False, default=0)
    housing_region_id = Column(Text, nullable=True)  # 'suburban' | 'downtown' | None

    # Step 8: side-income totals for the current day.
    # Ride share is a flexible emergency income system: it trades time and
    # wellbeing for money. These values accumulate across multiple actions.
    main_shift_hours_today = Column(Numeric(12, 4), nullable=False, default=0)
    side_income_hours = Column(Numeric(12, 4), nullable=False, default=0)
    side_income_gross_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    side_income_fuel_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    side_income_wear_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    side_income_maintenance_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    side_income_net_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # Step 16: life consequences + time-budget tracking.
    total_hours_used = Column(Numeric(12, 4), nullable=False, default=0)
    job_hours = Column(Numeric(12, 4), nullable=False, default=0)
    business_hours = Column(Numeric(12, 4), nullable=False, default=0)
    commute_hours = Column(Numeric(12, 4), nullable=False, default=0)
    sleep_hours = Column(Numeric(12, 4), nullable=False, default=7)
    recovery_hours = Column(Numeric(12, 4), nullable=False, default=1)
    overtime_hours = Column(Numeric(12, 4), nullable=False, default=0)
    stress_delta = Column(Integer, nullable=False, default=0)
    health_delta = Column(Integer, nullable=False, default=0)
    productivity_modifier = Column(Numeric(8, 4), nullable=False, default=1)
    burnout_risk = Column(Numeric(8, 4), nullable=False, default=0)
    medical_event_risk = Column(Numeric(8, 4), nullable=False, default=0)
    medical_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    missed_work_penalty_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    life_debug_json = Column(Text, nullable=True)

    # Step 17: housing/region full-integration daily fields.
    region_key = Column(Text, nullable=True)
    housing_cost_daily_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    utilities_cost_daily_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    commute_fuel_cost_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    region_stress_delta = Column(Numeric(8, 4), nullable=False, default=0)
    region_opportunity_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    region_business_demand_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    region_side_income_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    networking_modifier = Column(Numeric(8, 4), nullable=False, default=0)
    opportunity_quality_signal = Column(Numeric(8, 4), nullable=False, default=1)
    housing_debug_json = Column(Text, nullable=True)

    # Step 20: debt trap + recovery arc daily fields.
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
    distress_driver_json = Column(Text, nullable=True)
    recovery_actions_json = Column(Text, nullable=True)

    # ── Step 69: Retention Engine ─────────────────────────────────────────────
    # JSON arrays/objects written at settlement; read by summary endpoint and
    # future notification layer.  Nullable so older rows are unaffected.
    retention_flags_json = Column(Text, nullable=True)          # list[dict] pressure flags
    carryover_opportunities_json = Column(Text, nullable=True)  # dict {carried, evolved, expired}

    # Core-schema aliases mapped to existing snapshot fields.
    basket_spend_xgp = synonym("total_spent_xgp")
    end_cash_xgp = synonym("cash_end")
    end_stress = synonym("stress_end")
    end_health = synonym("health_end")
    side_income_hours_today = synonym("side_income_hours")
    recovery_hours_today = synonym("recovery_hours")
    total_time_used_today = synonym("total_hours_used")

    # Free-form notes for debugging / audit.
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    player = relationship("Player", back_populates="daily_states", foreign_keys=[player_id])
