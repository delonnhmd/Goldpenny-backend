import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Supabase Auth user id (UUID string). Nullable to allow legacy rows that
    # were created before the auth migration; uniqueness enforced via
    # partial unique index ux_players_user_id.
    user_id = Column(Text, nullable=True, unique=True, index=True)

    # ── Finances ──────────────────────────────────────────────────────────────
    cash = Column(Numeric(12, 2), nullable=False, default=1000)
    display_name = Column(String(80), nullable=True)
    gender = Column(String(20), nullable=True)
    bank_savings_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    credit_score = Column(Integer, nullable=False, default=650)
    required_daily_debt_payment_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    debt_utilization_ratio = Column(Numeric(8, 4), nullable=False, default=0)
    missed_payment_streak = Column(Integer, nullable=False, default=0)
    on_payment_plan = Column(Boolean, nullable=False, default=False)
    distress_state = Column(String(20), nullable=False, default="stable")
    distress_score = Column(Numeric(8, 4), nullable=False, default=0)
    last_missed_payment_date = Column(Date, nullable=True)
    # Last Houston calendar date for which offline survival catch-up ran.
    # Used to ensure missed-login survival processing is idempotent.
    last_survival_resolved_date = Column(Date, nullable=True)
    borrowing_cost_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    opportunity_access_penalty = Column(Numeric(8, 4), nullable=False, default=0)
    business_risk_penalty = Column(Numeric(8, 4), nullable=False, default=0)
    career_progress_penalty = Column(Numeric(8, 4), nullable=False, default=0)
    credit_debug_json = Column(Text, nullable=True)
    recovery_actions_json = Column(Text, nullable=True)
    reputation = Column(Integer, nullable=False, default=0)

    # ── Vitals ────────────────────────────────────────────────────────────────
    health = Column(Integer, nullable=False, default=100)
    stress = Column(Integer, nullable=False, default=0)
    fatigue = Column(Float, nullable=False, default=0.0)
    productivity_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    base_productivity_modifier = Column(Numeric(8, 4), nullable=False, default=1.0)
    burnout_risk = Column(Numeric(8, 4), nullable=False, default=0.0)
    medical_event_risk = Column(Numeric(8, 4), nullable=False, default=0.0)

    # ── Career ────────────────────────────────────────────────────────────────
    skill_level = Column(Integer, nullable=False, default=1)
    main_job = Column(String(120), nullable=True)
    side_job = Column(String(120), nullable=True)
    rideshare_reliability = Column(Numeric(8, 4), nullable=False, default=0.95)

    # ── Daily work tracking (reset each in-game day) ─────────────────────────
    # hours_available is the player's remaining time budget for the current day.
    # It is consumed by work actions and ONLY resets through end-of-day settlement
    # (POST /daily/settle), never automatically.
    hours_available = Column(Integer, nullable=False, default=24)
    main_job_hours_today = Column(Integer, nullable=False, default=0)
    side_job_hours_today = Column(Integer, nullable=False, default=0)
    total_hours_worked_today = Column(Integer, nullable=False, default=0)
    work_actions_today = Column(Integer, nullable=False, default=0)
    last_worked_day = Column(Integer, nullable=True)   # in-game economy day
    main_shift_active_flag = Column(Boolean, nullable=False, default=False)
    main_shift_status = Column(String(20), nullable=False, default="idle")
    main_shift_started_at = Column(DateTime(timezone=True), nullable=True)
    main_shift_ends_at = Column(DateTime(timezone=True), nullable=True)
    main_shift_completed_at = Column(DateTime(timezone=True), nullable=True)
    main_shift_job_name = Column(String(120), nullable=True)
    main_shift_shift_type = Column(String(40), nullable=True)
    main_shift_hours = Column(Integer, nullable=False, default=0)
    main_shift_number = Column(Integer, nullable=False, default=0)
    main_shift_last_cash_xgp = Column(Numeric(14, 4), nullable=False, default=0)
    main_shift_last_xp_gained = Column(Integer, nullable=False, default=0)
    main_shift_last_stress_delta = Column(Integer, nullable=False, default=0)
    main_shift_last_health_delta = Column(Integer, nullable=False, default=0)

    # last_settled_day prevents players from settling the same day twice.
    # Null until the first successful settlement.  Set to current_day by the
    # run_player_end_of_day_settlement() function in daily_engine.py.
    last_settled_day = Column(Integer, nullable=True)
    # Latest settled day for which the player acknowledged the auto summary.
    last_seen_settlement_day = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Geography ─────────────────────────────────────────────────────────────
    region = Column(String(40), nullable=False, default="suburban")  # suburban | downtown
    current_location_key = Column(String(80), nullable=False, default="home")

    # ── Step 7: Housing Region (recurring cost layer) ─────────────────────────
    # Canonical housing region identifier set via POST /housing/assign.
    # Null until the player explicitly chooses a region.
    # At settlement time a null here means no housing cost is applied.
    # Values: 'suburban' | 'downtown'  (enforced by validate_housing_assignment)
    # This is kept in sync with the `region` field above when assigned,
    # so that existing business-demand modifiers continue to work.
    housing_region_id = Column(String(40), nullable=True)

    # ── Housing / Debt status (Step 8) ───────────────────────────────────────
    net_worth = Column(Numeric(14, 2), nullable=False, default=1000)
    housing_stability = Column(Integer, nullable=False, default=100)   # 0-100
    has_active_housing = Column(Boolean, nullable=False, default=False)

    # ── Step 5.5: Off-chain reward accounting ─────────────────────────────────
    # Accumulated since last process-month run.
    pending_reward_points = Column(Float, nullable=False, default=0.0)
    # Off-chain token amount approved and awaiting future on-chain claim.
    pending_token_amount = Column(Float, nullable=False, default=0.0)
    # Total token units successfully claimed on-chain across all time.
    total_lifetime_token_claimed = Column(Float, nullable=False, default=0.0)
    # "eligible" | "suspended" | "banned"
    reward_eligibility_status = Column(String(20), nullable=False, default="eligible")
    # Raised when suspicious activity crosses severity threshold.
    anti_cheat_flag = Column(Boolean, nullable=False, default=False)
    # In-game day number when this player account first appeared in gameplay.
    account_created_day = Column(Integer, nullable=True)
    # True once a wallet_link row has been verified for this player.
    wallet_linked = Column(Boolean, nullable=False, default=False)

    # ── Step 1: Monetary constitution — PFT reward accounting ────────────────
    # Optional on-chain wallet address for future PFT claim flow.
    # Nullable: claiming is disabled in Step 1, so a missing wallet is fine.
    wallet_address = Column(String(100), nullable=True)

    # Cumulative XGP earned across the entire lifetime of the account,
    # updated by the settlement engine on each income event.
    lifetime_xgp_earned = Column(Float, nullable=False, default=0.0)

    # Cumulative contribution score across all epochs (historical sum).
    lifetime_contribution_score = Column(Float, nullable=False, default=0.0)

    # The epoch id (integer index) of the last epoch for which PFT was claimed.
    # Null until the first successful claim is processed.
    last_claimed_epoch = Column(Integer, nullable=True)

    # Boolean shortcut used by the reward engine eligibility check.
    # True when the player passes all qualification gates for the current epoch.
    is_reward_eligible = Column(Boolean, nullable=False, default=False)

    # ── Step 12: Marketplace reputation fields ──────────────────────────────────
    # completed_trades_count: number of Step 12 marketplace trades as seller.
    # Each successful sale increments this.
    completed_trades_count = Column(Integer, nullable=False, default=0)
    # marketplace_rating_score: simple cumulative score, not an average.
    # Each successful trade adds 1. Future steps may introduce review mechanics.
    marketplace_rating_score = Column(Float, nullable=False, default=0.0)

    # ── Step 13: Co-op deal tracking fields ──────────────────────────────────
    # successful_coop_deals_count: total co-op deals completed as any participant.
    # Incremented by complete_coop_deal() for every paid participant.
    successful_coop_deals_count = Column(Integer, nullable=False, default=0)
    # failed_coop_deals_count: total deals where the player hosted but the deal
    # expired before all roles were filled.  Incremented by expire_open_deals().
    failed_coop_deals_count = Column(Integer, nullable=False, default=0)

    # Core schema aliases to existing canonical columns.
    cash_xgp = synonym("cash")
    net_worth_xgp = synonym("net_worth")
    total_debt_xgp = synonym("debt_xgp")
    available_hours = synonym("hours_available")

    job_actions = relationship("JobAction", back_populates="player", order_by="JobAction.created_at.desc()")
    daily_states = relationship(
        "PlayerDailyState",
        back_populates="player",
        order_by="PlayerDailyState.created_at.desc()",
    )
    stock_holdings = relationship(
        "PlayerStockHolding",
        back_populates="player",
        order_by="PlayerStockHolding.updated_at.desc()",
    )
    stock_trade_logs = relationship(
        "StockTradeLog",
        back_populates="player",
        order_by="StockTradeLog.created_at.desc()",
    )
    employment_states = relationship(
        "PlayerEmploymentState",
        back_populates="player",
        order_by="PlayerEmploymentState.created_at.desc()",
    )
    job_progressions = relationship(
        "PlayerJobProgression",
        back_populates="player",
        order_by="PlayerJobProgression.updated_at.desc()",
    )
    settlement_logs = relationship(
        "DailySettlementLog",
        back_populates="player",
        order_by="DailySettlementLog.created_at.desc()",
    )
    gameplay_transactions = relationship(
        "GameplayTransaction",
        order_by="GameplayTransaction.timestamp.desc()",
    )
    transaction_logs = relationship(
        "PlayerTransactionLog",
        order_by="PlayerTransactionLog.created_at.desc()",
    )
