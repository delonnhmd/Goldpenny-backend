from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.day_engine import DayEngine
from app.models.day_log import DayLog
from app.models.player import Player
from app.models.user import User
from app.services.daily_settlement_service import (
    DailySettlementError,
    SettlementNotFoundError,
    SettlementValidationError,
    get_latest_settlement_summary,
    settle_player_day,
)
from app.services.day_progression_service import run_player_next_day
from app.services.market_daily_update_service import (
    MarketDataMissingError,
    MarketUpdateError,
    generate_next_stock_day,
)

router = APIRouter()
_day_engine = DayEngine()


class CurrentDayResponse(BaseModel):
    current_day: int
    real_world_timestamp: datetime


class UpdatedPlayerSnapshot(BaseModel):
    cash: float
    health: int
    stress: int
    fatigue: float


class DayEndResponse(BaseModel):
    message: str
    day: int
    fatigue_recovered: float
    stress_recovered: int
    health_recovered: int
    health_penalty: int
    next_day_hours_available: int
    updated_player: UpdatedPlayerSnapshot


class DayLogOut(BaseModel):
    id: str
    day: int
    starting_cash: float
    ending_cash: float
    starting_health: int
    ending_health: int
    starting_stress: int
    ending_stress: int
    starting_fatigue: float
    ending_fatigue: float
    hours_worked: int
    income_earned: float
    actions_taken: int
    notes: str | None
    created_at: str


class MarketAdvanceResponse(BaseModel):
    previous_market_day: int
    new_market_day: int
    number_of_stock_rows_created: int
    macro_day_used: int


class PlayerSettleResponse(BaseModel):
    player_id: str
    settled_day: int
    game_time: dict | None = None
    run_status: dict | None = None
    tomorrow_preview_time: str | None = None
    next_morning_brief_at: str | None = None
    black_swan_pending: bool = False
    black_swan_event_id: str | None = None
    end_state: dict | None = None
    risk_warnings: list[str] = Field(default_factory=list)
    income_xgp: float
    expenses_xgp: float
    total_income: float = 0.0
    total_expense: float = 0.0
    net_change: float = 0.0
    ending_cash: float = 0.0
    income_breakdown: dict = Field(default_factory=dict)
    expense_breakdown: dict = Field(default_factory=dict)
    settlement_breakdown: dict = Field(default_factory=dict)
    settlement_debug: dict = Field(default_factory=dict)
    side_income_net_xgp: float
    stock_sale_income_xgp: float = 0.0
    stock_fee_xgp: float = 0.0
    business_net_xgp: float = 0.0
    business_revenue_xgp: float = 0.0
    business_cogs_xgp: float = 0.0
    business_overhead_xgp: float = 0.0
    business_spoilage_loss_xgp: float = 0.0
    business_fuel_cost_xgp: float = 0.0
    business_maintenance_cost_xgp: float = 0.0
    business_net_profit_xgp: float = 0.0
    total_business_profit_xgp: float = 0.0
    business_count_run: int = 0
    debt_paid_xgp: float
    debt_payment_due_xgp: float = 0.0
    debt_payment_paid_xgp: float = 0.0
    debt_payment_missed: bool = False
    late_fee_xgp: float = 0.0
    accrued_interest_xgp: float = 0.0
    weekly_gas_expense_xgp: float = 0.0
    opening_debt_xgp: float = 0.0
    payment_due_xgp: float = 0.0
    payment_made_xgp: float = 0.0
    interest_added_xgp: float = 0.0
    ending_debt_xgp: float = 0.0
    payment_status: str | None = None
    opening_credit_score: int = 650
    credit_score_change: int = 0
    ending_credit_score: int = 650
    delinquency_flag: bool = False
    distress_state_before: str = "stable"
    distress_state_after: str = "stable"
    distress_score_before: float = 0.0
    distress_score_after: float = 0.0
    borrowing_cost_modifier: float = 1.0
    opportunity_access_penalty: float = 0.0
    business_risk_penalty: float = 0.0
    career_progress_penalty: float = 0.0
    recovery_actions_applied: list[str] = Field(default_factory=list)
    financial_distress_summary: dict = Field(default_factory=dict)
    financial_survival_summary: dict = Field(default_factory=dict)
    required_monthly_obligation_xgp: float = 0.0
    required_daily_burden_xgp: float = 0.0
    obligation_load_ratio: float = 0.0
    liquidity_buffer_days: float = 0.0
    payment_pressure_label: str = "manageable"
    current_delinquency_stage: str = "current"
    survival_status_label: str = "current"
    financial_survival_payment_outcome: str = "paid_full"
    financial_survival_late_fee_xgp: float = 0.0
    financial_survival_late_fee_non_debt_xgp: float = 0.0
    financial_survival_additional_required_paid_xgp: float = 0.0
    financial_survival_credit_score_before: int = 650
    financial_survival_credit_score_after: int = 650
    financial_survival_credit_score_delta: int = 0
    financial_survival_stress_impact_delta: float = 0.0
    financial_survival_practical_actions: list[str] = Field(default_factory=list)
    borrowing_eligibility_profile: dict = Field(default_factory=dict)
    borrowing_liquidity_state: dict = Field(default_factory=dict)
    borrowing_options: dict = Field(default_factory=dict)
    borrowing_risk_summary: dict = Field(default_factory=dict)
    borrowing_pressure_summary: dict = Field(default_factory=dict)
    borrowing_refresh: dict = Field(default_factory=dict)
    ending_cash_xgp: float
    health_change: int
    stress_change: int
    total_hours_used: float = 0.0
    overtime_hours: float = 0.0
    sleep_hours: float = 0.0
    recovery_hours: float = 0.0
    stress_before: int = 0
    stress_after: int = 0
    health_before: int = 100
    health_after: int = 100
    productivity_modifier: float = 1.0
    productivity_modifier_before: float = 1.0
    burnout_risk: float = 0.0
    medical_event_risk: float = 0.0
    medical_cost_xgp: float = 0.0
    missed_work_penalty_xgp: float = 0.0
    life_summary: str | None = None
    time_budget_summary: str | None = None
    personal_shock_summary: str | None = None
    personal_shock_impacts: dict = Field(default_factory=dict)
    personal_shock_cash_impact_xgp: float = 0.0
    personal_shock_operational_delta_xgp: float = 0.0
    personal_shock_income_bonus_xgp: float = 0.0
    personal_shock_extra_expense_xgp: float = 0.0
    personal_shock_work_income_modifier: float = 1.0
    personal_shock_business_modifier: float = 1.0
    personal_shock_side_income_modifier: float = 1.0
    personal_shock_stress_delta: float = 0.0
    personal_shock_health_delta: float = 0.0
    personal_shock_time_hours: float = 0.0
    personal_shock_recent_event: dict = Field(default_factory=dict)
    personal_shock_recovery_state: dict = Field(default_factory=dict)
    personal_shock_profile: dict = Field(default_factory=dict)
    personal_shock_risk_state: dict = Field(default_factory=dict)
    personal_shock_practical_actions: list[str] = Field(default_factory=list)
    personal_shock_debug_meta: dict = Field(default_factory=dict)
    housing_region: str | None = None
    housing_cost_xgp: float = 0.0
    housing_cost_daily_xgp: float = 0.0
    utilities_cost_daily_xgp: float = 0.0
    commute_hours: float = 0.0
    commute_fuel_cost_xgp: float = 0.0
    commute_pressure: float = 0.0
    housing_stress_delta: int = 0
    region_key: str | None = None
    region_stress_delta: float = 0.0
    region_opportunity_modifier: float = 0.0
    region_business_demand_modifier: float = 0.0
    region_side_income_modifier: float = 0.0
    networking_modifier: float = 0.0
    opportunity_quality_signal: float = 1.0
    opportunity_modifier: float = 1.0
    housing_region_summary: dict = Field(default_factory=dict)
    employment_status: str | None = None
    employment_event: str | None = None
    layoff_risk_pct: float = 0.0
    promotion_chance_pct: float = 0.0
    wage_adjustment_pct: float = 0.0
    monthly_pay_xgp_after_event: float = 0.0
    net_worth_xgp: float = 0.0
    total_assets_xgp: float = 0.0
    stock_market_value_xgp: float = 0.0
    business_value_xgp: float = 0.0
    debt_xgp: float = 0.0
    allocation_json: dict = Field(default_factory=dict)
    stock_market_day_used: int | None = None
    summary_json: dict
    retention_summary: dict = Field(default_factory=dict)


class RunNextDayResponse(BaseModel):
    player_id: str
    market_day: int
    settled_day: int
    game_time: dict | None = None
    run_status: dict | None = None
    tomorrow_preview_time: str | None = None
    next_morning_brief_at: str | None = None
    black_swan_pending: bool = False
    black_swan_event_id: str | None = None
    end_state: dict | None = None
    risk_warnings: list[str] = Field(default_factory=list)
    income_xgp: float
    expenses_xgp: float
    total_income: float = 0.0
    total_expense: float = 0.0
    net_change: float = 0.0
    ending_cash: float = 0.0
    income_breakdown: dict = Field(default_factory=dict)
    expense_breakdown: dict = Field(default_factory=dict)
    settlement_breakdown: dict = Field(default_factory=dict)
    settlement_debug: dict = Field(default_factory=dict)
    business_net_xgp: float = 0.0
    stock_sale_income_xgp: float = 0.0
    stock_fee_xgp: float = 0.0
    business_revenue_xgp: float = 0.0
    business_cogs_xgp: float = 0.0
    business_overhead_xgp: float = 0.0
    business_spoilage_loss_xgp: float = 0.0
    business_fuel_cost_xgp: float = 0.0
    business_maintenance_cost_xgp: float = 0.0
    business_net_profit_xgp: float = 0.0
    total_business_profit_xgp: float = 0.0
    business_count_run: int = 0
    business_summary: dict = Field(default_factory=dict)
    fruit_shop_result: dict | None = None
    food_truck_result: dict | None = None
    side_income_result: dict | None = None
    maintenance_cost_xgp: float = 0.0
    spoilage_loss_xgp: float = 0.0
    opening_debt_xgp: float = 0.0
    debt_payment_due_xgp: float = 0.0
    debt_payment_paid_xgp: float = 0.0
    debt_payment_missed: bool = False
    late_fee_xgp: float = 0.0
    accrued_interest_xgp: float = 0.0
    weekly_gas_expense_xgp: float = 0.0
    payment_due_xgp: float = 0.0
    payment_made_xgp: float = 0.0
    interest_added_xgp: float = 0.0
    ending_debt_xgp: float = 0.0
    payment_status: str | None = None
    credit_score_change: int = 0
    ending_credit_score: int = 650
    delinquency_flag: bool = False
    distress_state: str = "stable"
    distress_score: float = 0.0
    distress_state_before: str = "stable"
    distress_score_before: float = 0.0
    borrowing_cost_modifier: float = 1.0
    opportunity_access_penalty: float = 0.0
    business_risk_penalty: float = 0.0
    career_progress_penalty: float = 0.0
    recovery_actions_applied: list[str] = Field(default_factory=list)
    financial_distress_summary: dict = Field(default_factory=dict)
    financial_survival_summary: dict = Field(default_factory=dict)
    required_monthly_obligation_xgp: float = 0.0
    required_daily_burden_xgp: float = 0.0
    obligation_load_ratio: float = 0.0
    liquidity_buffer_days: float = 0.0
    payment_pressure_label: str = "manageable"
    current_delinquency_stage: str = "current"
    survival_status_label: str = "current"
    financial_survival_payment_outcome: str = "paid_full"
    financial_survival_late_fee_xgp: float = 0.0
    financial_survival_late_fee_non_debt_xgp: float = 0.0
    financial_survival_additional_required_paid_xgp: float = 0.0
    financial_survival_credit_score_before: int = 650
    financial_survival_credit_score_after: int = 650
    financial_survival_credit_score_delta: int = 0
    financial_survival_stress_impact_delta: float = 0.0
    financial_survival_practical_actions: list[str] = Field(default_factory=list)
    borrowing_eligibility_profile: dict = Field(default_factory=dict)
    borrowing_liquidity_state: dict = Field(default_factory=dict)
    borrowing_options: dict = Field(default_factory=dict)
    borrowing_risk_summary: dict = Field(default_factory=dict)
    borrowing_pressure_summary: dict = Field(default_factory=dict)
    borrowing_refresh: dict = Field(default_factory=dict)
    ending_cash_xgp: float
    health_change: int
    stress_change: int
    total_hours_used: float = 0.0
    overtime_hours: float = 0.0
    sleep_hours: float = 0.0
    recovery_hours: float = 0.0
    stress: int = 0
    health: int = 100
    productivity_modifier: float = 1.0
    burnout_risk: float = 0.0
    medical_event_risk: float = 0.0
    medical_cost_xgp: float = 0.0
    missed_work_penalty_xgp: float = 0.0
    life_summary: str | None = None
    time_budget_summary: str | None = None
    personal_shock_summary: str | None = None
    personal_shock_impacts: dict = Field(default_factory=dict)
    personal_shock_cash_impact_xgp: float = 0.0
    personal_shock_operational_delta_xgp: float = 0.0
    personal_shock_income_bonus_xgp: float = 0.0
    personal_shock_extra_expense_xgp: float = 0.0
    personal_shock_work_income_modifier: float = 1.0
    personal_shock_business_modifier: float = 1.0
    personal_shock_side_income_modifier: float = 1.0
    personal_shock_stress_delta: float = 0.0
    personal_shock_health_delta: float = 0.0
    personal_shock_time_hours: float = 0.0
    personal_shock_recent_event: dict = Field(default_factory=dict)
    personal_shock_recovery_state: dict = Field(default_factory=dict)
    personal_shock_profile: dict = Field(default_factory=dict)
    personal_shock_risk_state: dict = Field(default_factory=dict)
    personal_shock_practical_actions: list[str] = Field(default_factory=list)
    personal_shock_debug_meta: dict = Field(default_factory=dict)
    housing_region: str | None = None
    housing_cost_xgp: float = 0.0
    housing_cost_daily_xgp: float = 0.0
    utilities_cost_daily_xgp: float = 0.0
    commute_hours: float = 0.0
    commute_fuel_cost_xgp: float = 0.0
    commute_pressure: float = 0.0
    housing_stress_delta: int = 0
    region_key: str | None = None
    region_stress_delta: float = 0.0
    region_opportunity_modifier: float = 0.0
    region_business_demand_modifier: float = 0.0
    region_side_income_modifier: float = 0.0
    networking_modifier: float = 0.0
    opportunity_quality_signal: float = 1.0
    opportunity_modifier: float = 1.0
    housing_region_summary: dict = Field(default_factory=dict)
    employment_status: str | None = None
    employment_event: str | None = None
    layoff_risk_pct: float = 0.0
    promotion_chance_pct: float = 0.0
    wage_adjustment_pct: float = 0.0
    monthly_pay_xgp_after_event: float = 0.0
    net_worth_xgp: float = 0.0
    total_assets_xgp: float = 0.0
    stock_market_value_xgp: float = 0.0
    business_value_xgp: float = 0.0
    debt_xgp: float = 0.0
    allocation_json: dict = Field(default_factory=dict)
    summary_headline: str
    headline: str
    summary: str
    macro_tags_json: list
    player_impact_json: dict
    action_hints_json: list
    economy_headline: str | None = None
    economy_summary_lines: list = Field(default_factory=list)
    top_bottlenecks: list = Field(default_factory=list)
    top_basket_movers: list = Field(default_factory=list)
    top_job_changes: list = Field(default_factory=list)
    basket_pricing_summary: dict = Field(default_factory=dict)
    job_market_summary: dict = Field(default_factory=dict)
    daily_economy_brief: dict = Field(default_factory=dict)
    summary_json: dict
    progression_summary: dict = Field(default_factory=dict)
    commitment_summary: dict = Field(default_factory=dict)
    population_pressure_summary: dict = Field(default_factory=dict)
    population_region_state: dict = Field(default_factory=dict)
    population_opportunity_pressure: dict = Field(default_factory=dict)
    population_competition_state: dict = Field(default_factory=dict)
    population_region_heat: dict = Field(default_factory=dict)
    population_response_summary: dict = Field(default_factory=dict)
    population_refresh: dict = Field(default_factory=dict)
    world_memory_snapshot: dict = Field(default_factory=dict)
    world_patterns: dict = Field(default_factory=dict)
    world_narrative: dict = Field(default_factory=dict)
    local_pressure_summary: dict = Field(default_factory=dict)
    player_pattern_summary: dict = Field(default_factory=dict)
    region_memory_summary: dict = Field(default_factory=dict)
    onboarding_summary: dict = Field(default_factory=dict)
    retention_summary: dict = Field(default_factory=dict)


class SettlementSummaryResponse(BaseModel):
    player_id: str
    day_number: int
    game_time: dict | None = None
    run_status: dict | None = None
    tomorrow_preview_time: str | None = None
    next_morning_brief_at: str | None = None
    black_swan_pending: bool = False
    black_swan_event_id: str | None = None
    end_state: dict | None = None
    risk_warnings: list[str] = Field(default_factory=list)
    income_xgp: float
    expenses_xgp: float
    total_income: float = 0.0
    total_expense: float = 0.0
    net_change: float = 0.0
    ending_cash: float = 0.0
    income_breakdown: dict = Field(default_factory=dict)
    expense_breakdown: dict = Field(default_factory=dict)
    settlement_breakdown: dict = Field(default_factory=dict)
    settlement_debug: dict = Field(default_factory=dict)
    guided_day_number: int = 0
    guided_learning_title: str | None = None
    guided_earned_summary: str | None = None
    guided_spent_summary: str | None = None
    guided_change_summary: str | None = None
    guided_watch_tomorrow: str | None = None
    side_income_net_xgp: float
    business_net_xgp: float = 0.0
    stock_sale_income_xgp: float = 0.0
    stock_fee_xgp: float = 0.0
    business_revenue_xgp: float = 0.0
    business_cogs_xgp: float = 0.0
    business_overhead_xgp: float = 0.0
    business_spoilage_loss_xgp: float = 0.0
    business_fuel_cost_xgp: float = 0.0
    business_maintenance_cost_xgp: float = 0.0
    business_net_profit_xgp: float = 0.0
    total_business_profit_xgp: float = 0.0
    business_count_run: int = 0
    debt_paid_xgp: float
    debt_payment_due_xgp: float = 0.0
    debt_payment_paid_xgp: float = 0.0
    debt_payment_missed: bool = False
    late_fee_xgp: float = 0.0
    accrued_interest_xgp: float = 0.0
    weekly_gas_expense_xgp: float = 0.0
    opening_debt_xgp: float = 0.0
    payment_due_xgp: float = 0.0
    payment_made_xgp: float = 0.0
    interest_added_xgp: float = 0.0
    ending_debt_xgp: float = 0.0
    payment_status: str | None = None
    opening_credit_score: int = 650
    credit_score_change: int = 0
    ending_credit_score: int = 650
    delinquency_flag: bool = False
    distress_state_before: str = "stable"
    distress_state_after: str = "stable"
    distress_score_before: float = 0.0
    distress_score_after: float = 0.0
    borrowing_cost_modifier: float = 1.0
    opportunity_access_penalty: float = 0.0
    business_risk_penalty: float = 0.0
    career_progress_penalty: float = 0.0
    recovery_actions_applied: list[str] = Field(default_factory=list)
    financial_distress_summary: dict = Field(default_factory=dict)
    financial_survival_summary: dict = Field(default_factory=dict)
    required_monthly_obligation_xgp: float = 0.0
    required_daily_burden_xgp: float = 0.0
    obligation_load_ratio: float = 0.0
    liquidity_buffer_days: float = 0.0
    payment_pressure_label: str = "manageable"
    current_delinquency_stage: str = "current"
    survival_status_label: str = "current"
    financial_survival_payment_outcome: str = "paid_full"
    financial_survival_late_fee_xgp: float = 0.0
    financial_survival_late_fee_non_debt_xgp: float = 0.0
    financial_survival_additional_required_paid_xgp: float = 0.0
    financial_survival_credit_score_before: int = 650
    financial_survival_credit_score_after: int = 650
    financial_survival_credit_score_delta: int = 0
    financial_survival_stress_impact_delta: float = 0.0
    financial_survival_practical_actions: list[str] = Field(default_factory=list)
    ending_cash_xgp: float
    health_change: int
    stress_change: int
    total_hours_used: float = 0.0
    overtime_hours: float = 0.0
    sleep_hours: float = 0.0
    recovery_hours: float = 0.0
    stress_before: int = 0
    stress_after: int = 0
    health_before: int = 100
    health_after: int = 100
    productivity_modifier: float = 1.0
    burnout_risk: float = 0.0
    medical_event_risk: float = 0.0
    medical_cost_xgp: float = 0.0
    missed_work_penalty_xgp: float = 0.0
    life_summary: str | None = None
    time_budget_summary: str | None = None
    personal_shock_summary: str | None = None
    personal_shock_impacts: dict = Field(default_factory=dict)
    personal_shock_cash_impact_xgp: float = 0.0
    personal_shock_operational_delta_xgp: float = 0.0
    personal_shock_income_bonus_xgp: float = 0.0
    personal_shock_extra_expense_xgp: float = 0.0
    personal_shock_work_income_modifier: float = 1.0
    personal_shock_business_modifier: float = 1.0
    personal_shock_side_income_modifier: float = 1.0
    personal_shock_stress_delta: float = 0.0
    personal_shock_health_delta: float = 0.0
    personal_shock_time_hours: float = 0.0
    personal_shock_recent_event: dict = Field(default_factory=dict)
    personal_shock_recovery_state: dict = Field(default_factory=dict)
    personal_shock_profile: dict = Field(default_factory=dict)
    personal_shock_risk_state: dict = Field(default_factory=dict)
    personal_shock_practical_actions: list[str] = Field(default_factory=list)
    personal_shock_debug_meta: dict = Field(default_factory=dict)
    housing_region: str | None = None
    housing_cost_xgp: float = 0.0
    housing_cost_daily_xgp: float = 0.0
    utilities_cost_daily_xgp: float = 0.0
    commute_hours: float = 0.0
    commute_fuel_cost_xgp: float = 0.0
    commute_pressure: float = 0.0
    housing_stress_delta: int = 0
    region_key: str | None = None
    region_stress_delta: float = 0.0
    region_opportunity_modifier: float = 0.0
    region_business_demand_modifier: float = 0.0
    region_side_income_modifier: float = 0.0
    networking_modifier: float = 0.0
    opportunity_quality_signal: float = 1.0
    opportunity_modifier: float = 1.0
    housing_region_summary: dict = Field(default_factory=dict)
    employment_status: str | None = None
    employment_event: str | None = None
    layoff_risk_pct: float = 0.0
    promotion_chance_pct: float = 0.0
    wage_adjustment_pct: float = 0.0
    monthly_pay_xgp_after_event: float = 0.0
    net_worth_xgp: float = 0.0
    total_assets_xgp: float = 0.0
    stock_market_value_xgp: float = 0.0
    business_value_xgp: float = 0.0
    debt_xgp: float = 0.0
    allocation_json: dict = Field(default_factory=dict)
    created_at: str | None
    summary_json: dict
    retention_summary: dict = Field(default_factory=dict)


def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == str(user.id)).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player profile not found.")
    return player


def _raise_day_service_error(exc: Exception) -> None:
    if isinstance(exc, (SettlementNotFoundError, MarketDataMissingError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, SettlementValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, (DailySettlementError, MarketUpdateError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected day service error.")


@router.get("/current", response_model=CurrentDayResponse, summary="Get current in-game day")
def get_current_day(db: Session = Depends(get_db)) -> CurrentDayResponse:
    state = _day_engine.get_or_create_game_state(db)
    return CurrentDayResponse(
        current_day=int(state.current_day),
        real_world_timestamp=state.real_world_timestamp,
    )


@router.post("/end", response_model=DayEndResponse, summary="End the current day for the authenticated player")
def end_day(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DayEndResponse:
    player = _get_player_or_404(current_user, db)

    try:
        summary = _day_engine.end_player_day(db=db, player=player)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Day already completed for this player.")

    return DayEndResponse(**summary)


@router.get(
    "/history",
    response_model=list[DayLogOut],
    summary="Get the most recent 30 day settlement logs for the authenticated player",
)
def get_day_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DayLogOut]:
    player = _get_player_or_404(current_user, db)

    logs = (
        db.query(DayLog)
        .filter(DayLog.player_id == player.id)
        .order_by(DayLog.day.desc(), DayLog.created_at.desc())
        .limit(30)
        .all()
    )

    return [
        DayLogOut(
            id=str(log.id),
            day=log.day,
            starting_cash=float(log.starting_cash),
            ending_cash=float(log.ending_cash),
            starting_health=log.starting_health,
            ending_health=log.ending_health,
            starting_stress=log.starting_stress,
            ending_stress=log.ending_stress,
            starting_fatigue=log.starting_fatigue,
            ending_fatigue=log.ending_fatigue,
            hours_worked=log.hours_worked,
            income_earned=float(log.income_earned),
            actions_taken=log.actions_taken,
            notes=log.notes,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.post("/market/advance", response_model=MarketAdvanceResponse, summary="Generate next market stock day")
def advance_market_day(db: Session = Depends(get_db)) -> MarketAdvanceResponse:
    try:
        result = generate_next_stock_day(db)
    except Exception as exc:
        _raise_day_service_error(exc)
    return MarketAdvanceResponse(**result)


@router.post("/settle/{player_id}", response_model=PlayerSettleResponse, summary="Settle one player day")
def settle_player_day_route(player_id: str, db: Session = Depends(get_db)) -> PlayerSettleResponse:
    try:
        result = settle_player_day(db, player_id)
    except Exception as exc:
        _raise_day_service_error(exc)
    return PlayerSettleResponse(**result)


@router.post("/run/{player_id}", response_model=RunNextDayResponse, summary="Advance market if needed and settle player")
def run_player_next_day_route(player_id: str, db: Session = Depends(get_db)) -> RunNextDayResponse:
    try:
        result = run_player_next_day(db, player_id)
    except Exception as exc:
        _raise_day_service_error(exc)
    return RunNextDayResponse(**result)


@router.get("/summary/{player_id}", response_model=SettlementSummaryResponse, summary="Latest settlement summary for player")
def get_player_settlement_summary(player_id: str, db: Session = Depends(get_db)) -> SettlementSummaryResponse:
    try:
        result = get_latest_settlement_summary(db, player_id)
    except Exception as exc:
        _raise_day_service_error(exc)
    return SettlementSummaryResponse(**result)
