"""Internal admin/debug control service for simulation balancing.

This module is intentionally internal-use only. It exposes consolidated
inspection snapshots and deterministic scenario forcing utilities to speed up
local balancing and QA loops.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.balance_config import get_balance_profile_metadata
from app.engine.event_catalog import EVENT_CATALOG
from app.engine.economy_telemetry_service import (
    compute_daily_economy_health_metrics,
    get_player_balance_snapshot,
)
from app.engine.exploit_detection_service import (
    detect_player_exploit_flags,
    detect_system_dominance_flags,
)
from app.engine.supply_chain_service import (
    SupplyChainError,
    SupplyChainNotFoundError,
    compute_supply_chain_daily_snapshot,
)
from app.engine.supply_chain_graph_service import (
    SupplyChainGraphError,
    build_supply_chain_daily_summary,
)
from app.engine.player_strategy_service import classify_player_strategy
from app.engine.weekly_strategy_service import (
    build_economy_weekly_summary,
    build_player_weekly_strategy_summary,
)
from app.engine.progression_service import build_progression_summary
from app.engine.onboarding_service import (
    build_first_session_dashboard_config,
    build_onboarding_guidance,
    build_onboarding_state,
    build_unlock_schedule,
    evaluate_onboarding_completion,
)
from app.engine.economy_presentation_service import (
    build_business_margin_summary,
    build_commute_pressure_summary,
    build_economy_presentation_summary,
    build_future_opportunity_teasers,
    build_market_overview,
    build_player_economy_explainer,
    build_price_trend_summary,
)
from app.engine.strategic_planning_service import (
    build_business_mode_plan_analysis,
    build_debt_vs_growth_analysis,
    build_housing_tradeoff_analysis,
    build_locked_future_path_preparation,
    build_player_strategy_recommendation,
    build_recovery_vs_push_analysis,
    build_short_horizon_plan_options,
    build_strategic_planning_summary,
)
from app.engine.commitment_service import (
    build_available_commitments,
    build_commitment_feedback,
    build_commitment_summary,
    detect_commitment_drift,
    evaluate_commitment_adherence,
    get_player_commitment_history,
)
from app.engine.world_memory_service import (
    build_local_pressure_summary as build_world_local_pressure_summary,
    build_player_pattern_summary as build_world_player_pattern_summary,
    build_region_memory_summary as build_world_region_memory_summary,
    build_world_memory_history,
    build_world_memory_summary,
    build_world_narrative,
    detect_recurring_patterns as detect_world_patterns,
    get_world_memory_snapshot,
)
from app.engine.population_pressure_service import (
    build_local_competition_state,
    build_local_opportunity_pressure,
    build_population_pressure_summary,
    build_population_response_summary,
    build_region_heat_summary,
    build_region_population_state,
    update_population_pressure,
)
from app.engine.personal_shock_service import (
    build_personal_shock_profile,
    build_personal_shock_summary,
    build_personal_shock_system_summary,
    build_player_resilience_summary,
    build_shock_risk_state,
    get_player_recovery_state,
    get_recent_personal_life_event,
)
from app.engine.financial_survival_service import (
    build_delinquency_state,
    build_financial_survival_summary,
    build_financial_survival_system_summary,
    build_payment_risk_state,
    build_player_obligation_profile,
    get_player_payment_history,
)
from app.engine.consumer_borrowing_service import (
    build_borrowing_eligibility_profile,
    build_borrowing_pressure_summary,
    build_borrowing_risk_summary,
    build_consumer_borrowing_system_summary,
    build_emergency_liquidity_state,
    generate_borrowing_options,
    get_player_borrowing_history,
    get_player_loan_accounts,
)
from app.engine.wealth_progression_service import (
    build_wealth_profile,
    build_net_worth_summary,
    build_wealth_momentum_summary,
    WealthProgressionError,
)
from app.engine.reputation_trust_service import (
    build_player_reputation_profile,
    build_trust_signal_state,
    apply_reputation_effects,
    ReputationTrustError,
)
from app.engine.contract_timing_service import (
    build_player_contract_schedule,
    build_upcoming_obligation_window,
    build_cash_timing_pressure_state,
    ContractTimingError,
)
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition import JOB_CATALOG
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_goal_history import PlayerGoalHistory
from app.models.player_progression_state import PlayerProgressionState
from app.models.player_onboarding_state import PlayerOnboardingState
from app.models.player_commitment_history import PlayerCommitmentHistory
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_world_memory_state import PlayerWorldMemoryState
from app.models.player_world_pattern_history import PlayerWorldPatternHistory
from app.models.player_shock_state import PlayerShockState
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.region_population_history import RegionPopulationHistory
from app.models.region_population_state import RegionPopulationState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.side_income_action import SideIncomeAction
from app.models.stock_daily_price import StockDailyPrice
from app.models.stock_trade_log import StockTradeLog
from app.services.housing_region_service import assign_player_housing
from app.services.basket_pricing_service import BasketPricingError, compute_daily_basket_price_updates
from app.services.daily_brief_service import build_daily_economy_brief
from app.services.job_market_service import JobMarketError, compute_daily_job_market_updates
from app.services.player_onboarding_service import (
    STARTER_BASELINES,
    SUPPORTED_STARTER_JOBS,
    get_playable_player_summary,
)
from app.services.stock_trading_service import StockTradingError, StockTradingService
from app.engine.career_service import get_player_career_snapshot, CareerError as CareerServiceError

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
GAME_EPOCH = date(2026, 1, 1)

SUPPORTED_MACRO_SCENARIOS = {
    "oil_spike",
    "confidence_drop",
    "inflation_relief",
    "unemployment_shock",
    "supply_chain_disruption",
    "consumer_recovery",
}

SUPPORTED_PLAYER_SCENARIOS = {
    "low_cash",
    "high_debt",
    "high_stress",
    "near_layoff",
    "business_bad_day",
    "clean_restart",
}

_stock_service = StockTradingService()


class AdminDebugError(Exception):
    """Base exception for internal admin/debug operations."""


class AdminDebugNotFoundError(AdminDebugError):
    """Raised when target player/resources do not exist."""


class AdminDebugValidationError(AdminDebugError):
    """Raised when a debug scenario request is invalid."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(maximum, value))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _day_to_date(day: int) -> date:
    return GAME_EPOCH + timedelta(days=max(0, int(day) - 1))


def _parse_json(text_value: str | None) -> dict | list | None:
    if not text_value:
        return None
    try:
        return json.loads(text_value)
    except Exception:
        return None


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise AdminDebugNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise AdminDebugNotFoundError("Player not found.")
    return player


def _serialize_housing_state(state: PlayerHousingState | None) -> dict | None:
    if state is None:
        return None
    return {
        "id": str(state.id),
        "region": state.region,
        "region_key": state.region,
        "housing_type": state.housing_type,
        "monthly_housing_cost_xgp": float(_money(_d(getattr(state, "monthly_housing_cost_xgp", 0)))),
        "monthly_utilities_cost_xgp": float(_money(_d(getattr(state, "monthly_utilities_cost_xgp", 0)))),
        "monthly_transport_base_xgp": float(_money(_d(getattr(state, "monthly_transport_base_xgp", 0)))),
        "daily_housing_cost_xgp": float(_money(_d(state.daily_housing_cost_xgp))),
        "commute_mode": str(getattr(state, "commute_mode", "car")),
        "commute_modifier": float(_q4(_d(state.commute_modifier))),
        "stress_modifier": int(state.stress_modifier or 0),
        "opportunity_modifier": float(_q4(_d(state.opportunity_modifier))),
        "business_demand_modifier": float(_q4(_d(getattr(state, "business_demand_modifier", 1.0)))),
        "side_income_modifier": float(_q4(_d(getattr(state, "side_income_modifier", 1.0)))),
        "networking_modifier": float(_q4(_d(getattr(state, "networking_modifier", 0.0)))),
        "active_flag": bool(state.active_flag),
        "created_at": state.created_at.isoformat() if state.created_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_employment_state(state: PlayerEmploymentState | None) -> dict | None:
    if state is None:
        return None
    return {
        "id": str(state.id),
        "day": int(state.day),
        "current_job_code": state.current_job_code,
        "skill_level": int(state.skill_level or 1),
        "monthly_pay_xgp": float(_money(_d(state.monthly_pay_xgp))),
        "employed_flag": bool(state.employed_flag),
        "job_status": str(state.job_status or "seeking"),
        "layoff_risk_pct": float(_q4(_d(state.layoff_risk_pct))),
        "productivity_modifier": float(_q4(_d(state.productivity_modifier))),
        "opportunity_score": float(_q4(_d(state.opportunity_score))),
        "promotion_chance_pct": float(_q4(_d(state.promotion_chance_pct))),
        "wage_adjustment_pct": float(_q4(_d(state.wage_adjustment_pct))),
        "last_employment_event": state.last_employment_event,
        "created_at": state.created_at.isoformat() if state.created_at else None,
    }


def _serialize_consumption(log: BasketConsumptionLog | None) -> dict | None:
    if log is None:
        return None
    return {
        "day": int(log.day),
        "essentials_spend_xgp": float(_money(_d(log.essentials_spend_xgp))),
        "protein_spend_xgp": float(_money(_d(log.protein_spend_xgp))),
        "produce_spend_xgp": float(_money(_d(log.produce_spend_xgp))),
        "convenience_spend_xgp": float(_money(_d(log.convenience_spend_xgp))),
        "total_spend_xgp": float(_money(_d(log.total_spend_xgp))),
        "budget_pressure_score": float(_q4(_d(log.budget_pressure_score))),
        "stress_spend_modifier": float(_q4(_d(log.stress_spend_modifier))),
        "nutrition_pressure_score": float(_q4(_d(log.nutrition_pressure_score))),
        "notes_json": _parse_json(log.notes_json),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_debt_credit(log: DebtCreditLog | None) -> dict | None:
    if log is None:
        return None
    return {
        "day": int(log.day),
        "opening_debt_xgp": float(_money(_d(log.opening_debt_xgp))),
        "payment_due_xgp": float(_money(_d(log.payment_due_xgp))),
        "payment_made_xgp": float(_money(_d(log.payment_made_xgp))),
        "interest_added_xgp": float(_money(_d(log.interest_added_xgp))),
        "ending_debt_xgp": float(_money(_d(log.ending_debt_xgp))),
        "payment_status": str(log.payment_status),
        "opening_credit_score": int(log.opening_credit_score),
        "credit_score_change": int(log.credit_score_change),
        "ending_credit_score": int(log.ending_credit_score),
        "delinquency_flag": bool(log.delinquency_flag),
        "notes_json": _parse_json(log.notes_json),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_financial_distress(log: FinancialDistressLog | None) -> dict | None:
    if log is None:
        return None
    return {
        "day": int(log.day),
        "as_of_date": log.as_of_date.isoformat() if log.as_of_date else None,
        "debt_payment_due_xgp": float(_money(_d(log.debt_payment_due_xgp))),
        "debt_payment_paid_xgp": float(_money(_d(log.debt_payment_paid_xgp))),
        "debt_payment_missed": bool(log.debt_payment_missed),
        "late_fee_xgp": float(_money(_d(log.late_fee_xgp))),
        "accrued_interest_xgp": float(_money(_d(log.accrued_interest_xgp))),
        "credit_score_before": int(log.credit_score_before),
        "credit_score_after": int(log.credit_score_after),
        "credit_score_delta": int(log.credit_score_delta),
        "distress_state_before": str(log.distress_state_before),
        "distress_state_after": str(log.distress_state_after),
        "distress_score_before": float(_q4(_d(log.distress_score_before))),
        "distress_score_after": float(_q4(_d(log.distress_score_after))),
        "borrowing_cost_modifier": float(_q4(_d(log.borrowing_cost_modifier))),
        "opportunity_access_penalty": float(_q4(_d(log.opportunity_access_penalty))),
        "business_risk_penalty": float(_q4(_d(log.business_risk_penalty))),
        "career_progress_penalty": float(_q4(_d(log.career_progress_penalty))),
        "distress_driver_json": _parse_json(log.distress_driver_json),
        "recovery_actions_json": _parse_json(log.recovery_actions_json),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_delinquency_state(state: PlayerDelinquencyState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "current_delinquency_stage": str(getattr(state, "current_delinquency_stage", "current") or "current"),
        "missed_payment_count_30d": int(getattr(state, "missed_payment_count_30d", 0) or 0),
        "late_payment_count_30d": int(getattr(state, "late_payment_count_30d", 0) or 0),
        "days_under_payment_stress": int(getattr(state, "days_under_payment_stress", 0) or 0),
        "last_missed_obligation_type": getattr(state, "last_missed_obligation_type", None),
        "credit_pressure_score": float(_q4(_d(getattr(state, "credit_pressure_score", 0)))),
        "financial_distress_score": float(_q4(_d(getattr(state, "financial_distress_score", 0)))),
        "last_updated_on": int(getattr(state, "last_updated_on", 0) or 0),
        "last_updated_date": (
            state.last_updated_date.isoformat() if getattr(state, "last_updated_date", None) else None
        ),
        "stage_debug_json": _parse_json(getattr(state, "stage_debug_json", None)) or {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_payment_history_row(row: PlayerPaymentHistory | None) -> dict | None:
    if row is None:
        return None
    return {
        "player_id": str(row.player_id),
        "day_number": int(getattr(row, "day_number", 0) or 0),
        "as_of_date": row.as_of_date.isoformat() if getattr(row, "as_of_date", None) else None,
        "payment_outcome": str(getattr(row, "payment_outcome", "paid_full") or "paid_full"),
        "required_daily_burden_xgp": float(_money(_d(getattr(row, "required_daily_burden_xgp", 0)))),
        "obligation_load_ratio": float(_q4(_d(getattr(row, "obligation_load_ratio", 0)))),
        "liquidity_buffer_days": float(_q4(_d(getattr(row, "liquidity_buffer_days", 0)))),
        "total_due_xgp": float(_money(_d(getattr(row, "total_due_xgp", 0)))),
        "total_paid_xgp": float(_money(_d(getattr(row, "total_paid_xgp", 0)))),
        "unpaid_amount_xgp": float(_money(_d(getattr(row, "unpaid_amount_xgp", 0)))),
        "late_fee_xgp": float(_money(_d(getattr(row, "late_fee_xgp", 0)))),
        "credit_score_before": int(getattr(row, "credit_score_before", 650) or 650),
        "credit_score_after": int(getattr(row, "credit_score_after", 650) or 650),
        "credit_score_delta": int(getattr(row, "credit_score_delta", 0) or 0),
        "delinquency_stage_before": str(getattr(row, "delinquency_stage_before", "current") or "current"),
        "delinquency_stage_after": str(getattr(row, "delinquency_stage_after", "current") or "current"),
        "survival_status_label": str(getattr(row, "survival_status_label", "current") or "current"),
        "payment_pressure_label": str(getattr(row, "payment_pressure_label", "manageable") or "manageable"),
        "full_pay_feasible": bool(getattr(row, "full_pay_feasible", False)),
        "partial_pay_feasible": bool(getattr(row, "partial_pay_feasible", False)),
        "stress_impact_delta": float(_q4(_d(getattr(row, "stress_impact_delta", 0)))),
        "summary_json": _parse_json(getattr(row, "summary_json", None)) or {},
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_borrowing_state(state: PlayerBorrowingState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "borrowing_access_score": float(_q4(_d(getattr(state, "borrowing_access_score", 0)))),
        "credit_access_tier": str(getattr(state, "credit_access_tier", "locked") or "locked"),
        "emergency_liquidity_label": str(
            getattr(state, "emergency_liquidity_label", "stable") or "stable"
        ),
        "max_safe_borrow_amount_xgp": float(
            _money(_d(getattr(state, "max_safe_borrow_amount_xgp", 0)))
        ),
        "estimated_risk_pricing_band": str(
            getattr(state, "estimated_risk_pricing_band", "unavailable") or "unavailable"
        ),
        "recent_distress_penalty": float(_q4(_d(getattr(state, "recent_distress_penalty", 0)))),
        "active_loan_count": int(getattr(state, "active_loan_count", 0) or 0),
        "repeat_borrowing_count_30d": int(getattr(state, "repeat_borrowing_count_30d", 0) or 0),
        "dependence_risk_score": float(_q4(_d(getattr(state, "dependence_risk_score", 0)))),
        "debug_json": _parse_json(getattr(state, "debug_json", None)) or {},
        "last_updated_on": int(getattr(state, "last_updated_on", 0) or 0),
        "last_updated_date": (
            state.last_updated_date.isoformat()
            if getattr(state, "last_updated_date", None)
            else None
        ),
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_loan_account_row(row: PlayerLoanAccount) -> dict:
    return {
        "loan_account_id": str(row.id),
        "player_id": str(row.player_id),
        "offer_key": str(getattr(row, "offer_key", "") or ""),
        "offer_family": str(getattr(row, "offer_family", "") or ""),
        "status": str(getattr(row, "status", "active") or "active"),
        "principal_original_xgp": float(_money(_d(getattr(row, "principal_original_xgp", 0)))),
        "principal_outstanding_xgp": float(_money(_d(getattr(row, "principal_outstanding_xgp", 0)))),
        "apr_pct": float(_q4(_d(getattr(row, "apr_pct", 0)))),
        "fee_amount_xgp": float(_money(_d(getattr(row, "fee_amount_xgp", 0)))),
        "term_days": int(getattr(row, "term_days", 0) or 0),
        "days_elapsed": int(getattr(row, "days_elapsed", 0) or 0),
        "days_remaining": int(getattr(row, "days_remaining", 0) or 0),
        "scheduled_daily_payment_xgp": float(
            _money(_d(getattr(row, "scheduled_daily_payment_xgp", 0)))
        ),
        "current_due_xgp": float(_money(_d(getattr(row, "current_due_xgp", 0)))),
        "missed_payment_count": int(getattr(row, "missed_payment_count", 0) or 0),
        "delinquency_stage": str(getattr(row, "delinquency_stage", "current") or "current"),
        "rollover_allowed": bool(getattr(row, "rollover_allowed", False)),
        "accepted_on_day": int(getattr(row, "accepted_on_day", 0) or 0),
        "accepted_on_date": (
            row.accepted_on_date.isoformat() if getattr(row, "accepted_on_date", None) else None
        ),
        "last_payment_day": (
            int(getattr(row, "last_payment_day", 0))
            if getattr(row, "last_payment_day", None) is not None
            else None
        ),
        "last_payment_amount_xgp": float(_money(_d(getattr(row, "last_payment_amount_xgp", 0)))),
        "closed_on_day": (
            int(getattr(row, "closed_on_day", 0))
            if getattr(row, "closed_on_day", None) is not None
            else None
        ),
        "closed_on_date": (
            row.closed_on_date.isoformat() if getattr(row, "closed_on_date", None) else None
        ),
        "account_meta_json": _parse_json(getattr(row, "account_meta_json", None)) or {},
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_borrowing_history_row(row: PlayerBorrowingHistory) -> dict:
    return {
        "history_id": str(row.id),
        "player_id": str(row.player_id),
        "day_number": int(getattr(row, "day_number", 0) or 0),
        "as_of_date": row.as_of_date.isoformat() if getattr(row, "as_of_date", None) else None,
        "event_type": str(getattr(row, "event_type", "") or ""),
        "offer_key": str(getattr(row, "offer_key", "") or ""),
        "offer_family": str(getattr(row, "offer_family", "") or ""),
        "loan_account_id": str(getattr(row, "loan_account_id", "")) if getattr(row, "loan_account_id", None) else None,
        "principal_xgp": float(_money(_d(getattr(row, "principal_xgp", 0)))),
        "fee_xgp": float(_money(_d(getattr(row, "fee_xgp", 0)))),
        "apr_pct": float(_q4(_d(getattr(row, "apr_pct", 0)))),
        "term_days": int(getattr(row, "term_days", 0) or 0),
        "estimated_total_cost_xgp": float(_money(_d(getattr(row, "estimated_total_cost_xgp", 0)))),
        "cash_delta_xgp": float(_money(_d(getattr(row, "cash_delta_xgp", 0)))),
        "debt_delta_xgp": float(_money(_d(getattr(row, "debt_delta_xgp", 0)))),
        "obligation_delta_xgp": float(_money(_d(getattr(row, "obligation_delta_xgp", 0)))),
        "status_after": str(getattr(row, "status_after", "active") or "active"),
        "summary_json": _parse_json(getattr(row, "summary_json", None)) or {},
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_progression_state(state: PlayerProgressionState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "current_day": int(getattr(state, "current_day", 0) or 0),
        "current_week_start_day": int(getattr(state, "current_week_start_day", 0) or 0),
        "current_week_end_day": int(getattr(state, "current_week_end_day", 0) or 0),
        "last_goal_refresh_day": int(getattr(state, "last_goal_refresh_day", 0) or 0),
        "last_mission_refresh_week_start_day": int(
            getattr(state, "last_mission_refresh_week_start_day", 0) or 0
        ),
        "last_progress_evaluated_day": int(getattr(state, "last_progress_evaluated_day", 0) or 0),
        "streaks": {
            "login_streak": int(getattr(state, "login_streak_current", 0) or 0),
            "productive_day_streak": int(getattr(state, "productive_day_streak_current", 0) or 0),
            "positive_cash_flow_streak": int(
                getattr(state, "positive_cash_flow_streak_current", 0) or 0
            ),
            "training_streak": int(getattr(state, "training_streak_current", 0) or 0),
            "business_consistency_streak": int(
                getattr(state, "business_consistency_streak_current", 0) or 0
            ),
            "low_distress_streak": int(getattr(state, "low_distress_streak_current", 0) or 0),
        },
        "recently_completed_json": _parse_json(getattr(state, "recently_completed_json", None)) or [],
        "reward_trace_json": _parse_json(getattr(state, "reward_trace_json", None)) or [],
        "last_action_digest_json": _parse_json(getattr(state, "last_action_digest_json", None)) or {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_onboarding_state(state: PlayerOnboardingState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "onboarding_status": str(getattr(state, "onboarding_status", "not_started") or "not_started"),
        "current_step_key": str(getattr(state, "current_step_key", "") or ""),
        "current_step_index": int(getattr(state, "current_step_index", 1) or 1),
        "started_on": state.started_on.isoformat() if getattr(state, "started_on", None) else None,
        "completed_on": state.completed_on.isoformat() if getattr(state, "completed_on", None) else None,
        "skipped_on": state.skipped_on.isoformat() if getattr(state, "skipped_on", None) else None,
        "last_guidance_shown_on": (
            state.last_guidance_shown_on.isoformat()
            if getattr(state, "last_guidance_shown_on", None)
            else None
        ),
        "visible_modules_json": _parse_json(getattr(state, "visible_modules_json", None)) or [],
        "unlocked_modules_json": _parse_json(getattr(state, "unlocked_modules_json", None)) or [],
        "completed_step_keys_json": _parse_json(getattr(state, "completed_step_keys_json", None)) or [],
        "first_session_day_count": int(getattr(state, "first_session_day_count", 0) or 0),
        "debug_meta": _parse_json(getattr(state, "debug_meta", None)) or {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_progression_goal_history(row: PlayerGoalHistory) -> dict:
    return {
        "goal_scope": str(getattr(row, "goal_scope", "")),
        "goal_key": str(getattr(row, "goal_key", "")),
        "title": str(getattr(row, "title", "")),
        "status": str(getattr(row, "status", "not_started")),
        "progress_current": float(_q4(_d(getattr(row, "progress_current", 0)))),
        "progress_target": float(_q4(_d(getattr(row, "progress_target", 1)))),
        "reward_summary": str(getattr(row, "reward_summary", "") or ""),
        "credited_flag": bool(getattr(row, "credited_flag", False)),
        "credited_on_day": int(getattr(row, "credited_on_day", 0) or 0),
        "as_of_date": row.as_of_date.isoformat() if getattr(row, "as_of_date", None) else None,
        "day_number": int(getattr(row, "day_number", 0) or 0),
        "week_start_day": int(getattr(row, "week_start_day", 0) or 0),
        "week_end_day": int(getattr(row, "week_end_day", 0) or 0),
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "reward_applied_json": _parse_json(getattr(row, "reward_applied_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_commitment_state(state: PlayerCommitmentState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "commitment_key": str(getattr(state, "commitment_key", "") or ""),
        "title": str(getattr(state, "title", "") or ""),
        "description": str(getattr(state, "description", "") or ""),
        "status": str(getattr(state, "status", "inactive") or "inactive"),
        "start_day": int(getattr(state, "start_day", 0) or 0),
        "target_end_day": int(getattr(state, "target_end_day", 0) or 0),
        "planned_duration_days": int(getattr(state, "planned_duration_days", 0) or 0),
        "start_date": state.start_date.isoformat() if getattr(state, "start_date", None) else None,
        "target_end_date": state.target_end_date.isoformat() if getattr(state, "target_end_date", None) else None,
        "adherence_score": float(_q4(_d(getattr(state, "adherence_score", 0)))),
        "momentum_score": float(_q4(_d(getattr(state, "momentum_score", 0)))),
        "days_followed": int(getattr(state, "days_followed", 0) or 0),
        "days_drifted": int(getattr(state, "days_drifted", 0) or 0),
        "last_evaluated_on": int(getattr(state, "last_evaluated_on", 0) or 0),
        "completion_summary": str(getattr(state, "completion_summary", "") or ""),
        "reward_summary": str(getattr(state, "reward_summary", "") or ""),
        "initial_context_json": _parse_json(getattr(state, "initial_context_json", None)) or {},
        "debug_json": _parse_json(getattr(state, "debug_json", None)) or {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_commitment_history(row: PlayerCommitmentHistory) -> dict:
    return {
        "commitment_key": str(getattr(row, "commitment_key", "") or ""),
        "title": str(getattr(row, "title", "") or ""),
        "status": str(getattr(row, "status", "") or ""),
        "start_day": int(getattr(row, "start_day", 0) or 0),
        "target_end_day": int(getattr(row, "target_end_day", 0) or 0),
        "planned_duration_days": int(getattr(row, "planned_duration_days", 0) or 0),
        "start_date": row.start_date.isoformat() if getattr(row, "start_date", None) else None,
        "target_end_date": row.target_end_date.isoformat() if getattr(row, "target_end_date", None) else None,
        "completed_on_day": int(getattr(row, "completed_on_day", 0) or 0),
        "completed_on_date": row.completed_on_date.isoformat() if getattr(row, "completed_on_date", None) else None,
        "adherence_score": float(_q4(_d(getattr(row, "adherence_score", 0)))),
        "momentum_score": float(_q4(_d(getattr(row, "momentum_score", 0)))),
        "days_followed": int(getattr(row, "days_followed", 0) or 0),
        "days_drifted": int(getattr(row, "days_drifted", 0) or 0),
        "completion_summary": str(getattr(row, "completion_summary", "") or ""),
        "reward_summary": str(getattr(row, "reward_summary", "") or ""),
        "main_driver": str(getattr(row, "main_driver", "") or ""),
        "feedback_trace_json": _parse_json(getattr(row, "feedback_trace_json", None)) or [],
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_shock_state(state: PlayerShockState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "shock_risk_score": float(_q4(_d(getattr(state, "shock_risk_score", 0)))),
        "financial_fragility_score": float(_q4(_d(getattr(state, "financial_fragility_score", 0)))),
        "health_fragility_score": float(_q4(_d(getattr(state, "health_fragility_score", 0)))),
        "work_disruption_risk_score": float(_q4(_d(getattr(state, "work_disruption_risk_score", 0)))),
        "recovery_capacity_score": float(_q4(_d(getattr(state, "recovery_capacity_score", 0)))),
        "recent_pressure_direction": str(getattr(state, "recent_pressure_direction", "stable") or "stable"),
        "recent_negative_streak": int(getattr(state, "recent_negative_streak", 0) or 0),
        "recent_recovery_support": int(getattr(state, "recent_recovery_support", 0) or 0),
        "last_event_key": getattr(state, "last_event_key", None),
        "last_event_family": getattr(state, "last_event_family", None),
        "last_event_severity": getattr(state, "last_event_severity", None),
        "last_event_day": int(getattr(state, "last_event_day", 0) or 0) if getattr(state, "last_event_day", None) else None,
        "last_event_date": state.last_event_date.isoformat() if getattr(state, "last_event_date", None) else None,
        "profile_debug_json": _parse_json(getattr(state, "profile_debug_json", None)) or {},
        "last_updated_on": int(getattr(state, "last_updated_on", 0) or 0),
        "last_updated_date": state.last_updated_date.isoformat() if getattr(state, "last_updated_date", None) else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_recovery_state(state: PlayerRecoveryState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "recovery_days_remaining": int(getattr(state, "recovery_days_remaining", 0) or 0),
        "temporary_stress_modifier": float(_q4(_d(getattr(state, "temporary_stress_modifier", 0)))),
        "temporary_health_modifier": float(_q4(_d(getattr(state, "temporary_health_modifier", 0)))),
        "temporary_income_modifier": float(_q4(_d(getattr(state, "temporary_income_modifier", 0)))),
        "temporary_business_modifier": float(_q4(_d(getattr(state, "temporary_business_modifier", 0)))),
        "temporary_time_modifier": float(_q4(_d(getattr(state, "temporary_time_modifier", 0)))),
        "recovery_status_label": str(getattr(state, "recovery_status_label", "stable") or "stable"),
        "source_event_key": getattr(state, "source_event_key", None),
        "source_event_severity": getattr(state, "source_event_severity", None),
        "last_applied_day": int(getattr(state, "last_applied_day", 0) or 0) if getattr(state, "last_applied_day", None) else None,
        "next_expire_day": int(getattr(state, "next_expire_day", 0) or 0) if getattr(state, "next_expire_day", None) else None,
        "recovery_debug_json": _parse_json(getattr(state, "recovery_debug_json", None)) or {},
        "last_updated_on": int(getattr(state, "last_updated_on", 0) or 0),
        "last_updated_date": state.last_updated_date.isoformat() if getattr(state, "last_updated_date", None) else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_life_event_history(row: PlayerLifeEventHistory) -> dict:
    return {
        "event_key": str(getattr(row, "event_key", "") or ""),
        "event_family": str(getattr(row, "event_family", "") or ""),
        "headline": str(getattr(row, "headline", "") or ""),
        "severity_band": str(getattr(row, "severity_band", "") or ""),
        "day_number": int(getattr(row, "day_number", 0) or 0),
        "as_of_date": row.as_of_date.isoformat() if getattr(row, "as_of_date", None) else None,
        "cash_impact_xgp": float(_money(_d(getattr(row, "cash_impact_xgp", 0)))),
        "stress_impact_delta": float(_q4(_d(getattr(row, "stress_impact_delta", 0)))),
        "health_impact_delta": float(_q4(_d(getattr(row, "health_impact_delta", 0)))),
        "time_impact_hours": float(_q4(_d(getattr(row, "time_impact_hours", 0)))),
        "work_income_impact": float(_q4(_d(getattr(row, "work_income_impact", 0)))),
        "business_impact": float(_q4(_d(getattr(row, "business_impact", 0)))),
        "side_income_impact": float(_q4(_d(getattr(row, "side_income_impact", 0)))),
        "duration_days": int(getattr(row, "duration_days", 0) or 0),
        "recovery_hint": str(getattr(row, "recovery_hint", "") or ""),
        "trigger_tags_json": _parse_json(getattr(row, "trigger_tags_json", None)) or [],
        "impact_json": _parse_json(getattr(row, "impact_json", None)) or {},
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_world_memory_state(state: PlayerWorldMemoryState | None) -> dict | None:
    if state is None:
        return None
    return {
        "player_id": str(state.player_id),
        "region_key": str(getattr(state, "region_key", "suburban") or "suburban"),
        "memory_window_start_day": int(getattr(state, "memory_window_start_day", 1) or 1),
        "memory_window_end_day": int(getattr(state, "memory_window_end_day", 1) or 1),
        "memory_window_start": state.memory_window_start.isoformat() if state.memory_window_start else None,
        "memory_window_end": state.memory_window_end.isoformat() if state.memory_window_end else None,
        "macro_pressure_score": float(_q4(_d(getattr(state, "macro_pressure_score", 0)))),
        "commute_pressure_score": float(_q4(_d(getattr(state, "commute_pressure_score", 0)))),
        "business_pressure_score": float(_q4(_d(getattr(state, "business_pressure_score", 0)))),
        "life_pressure_score": float(_q4(_d(getattr(state, "life_pressure_score", 0)))),
        "opportunity_score": float(_q4(_d(getattr(state, "opportunity_score", 0)))),
        "dominant_patterns_json": _parse_json(getattr(state, "dominant_patterns_json", None)) or [],
        "narrative_state_json": _parse_json(getattr(state, "narrative_state_json", None)) or {},
        "local_pressure_json": _parse_json(getattr(state, "local_pressure_json", None)) or {},
        "player_pattern_json": _parse_json(getattr(state, "player_pattern_json", None)) or {},
        "region_memory_json": _parse_json(getattr(state, "region_memory_json", None)) or {},
        "last_updated_on": int(getattr(state, "last_updated_on", 0) or 0),
        "last_updated_date": state.last_updated_date.isoformat() if state.last_updated_date else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_world_pattern_history(row: PlayerWorldPatternHistory) -> dict:
    summary = _parse_json(getattr(row, "summary_json", None)) or {}
    return {
        "pattern_key": str(getattr(row, "pattern_key", "") or ""),
        "category": str(getattr(row, "category", "") or ""),
        "title": str(getattr(row, "title", "") or ""),
        "first_seen_on_day": int(getattr(row, "first_seen_on_day", 0) or 0),
        "last_seen_on_day": int(getattr(row, "last_seen_on_day", 0) or 0),
        "first_seen_on_date": row.first_seen_on_date.isoformat() if row.first_seen_on_date else None,
        "last_seen_on_date": row.last_seen_on_date.isoformat() if row.last_seen_on_date else None,
        "consecutive_days": int(getattr(row, "consecutive_days", 0) or 0),
        "persistence_score": float(_q4(_d(getattr(row, "persistence_score", 0)))),
        "severity": str(getattr(row, "severity", "low") or "low"),
        "direction": str(getattr(row, "direction", "stable") or "stable"),
        "status": str(getattr(row, "status", "active") or "active"),
        "summary_json": summary,
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_region_population_state(state: RegionPopulationState | None) -> dict | None:
    if state is None:
        return None
    return {
        "region_key": str(getattr(state, "region_key", "suburban") or "suburban"),
        "memory_window_start_day": int(getattr(state, "memory_window_start_day", 1) or 1),
        "memory_window_end_day": int(getattr(state, "memory_window_end_day", 1) or 1),
        "memory_window_start": (
            state.memory_window_start.isoformat() if getattr(state, "memory_window_start", None) else None
        ),
        "memory_window_end": (
            state.memory_window_end.isoformat() if getattr(state, "memory_window_end", None) else None
        ),
        "active_population_score": float(_q4(_d(getattr(state, "active_population_score", 0)))),
        "opportunity_density_score": float(_q4(_d(getattr(state, "opportunity_density_score", 0)))),
        "congestion_score": float(_q4(_d(getattr(state, "congestion_score", 0)))),
        "housing_pressure_score": float(_q4(_d(getattr(state, "housing_pressure_score", 0)))),
        "business_competition_score": float(_q4(_d(getattr(state, "business_competition_score", 0)))),
        "consumer_flow_score": float(_q4(_d(getattr(state, "consumer_flow_score", 0)))),
        "recent_growth_direction": str(getattr(state, "recent_growth_direction", "stable") or "stable"),
        "state_debug_json": _parse_json(getattr(state, "state_debug_json", None)) or {},
        "last_updated_on": int(getattr(state, "last_updated_on", 0) or 0),
        "last_updated_date": (
            state.last_updated_date.isoformat() if getattr(state, "last_updated_date", None) else None
        ),
    }


def _serialize_region_population_history(row: RegionPopulationHistory) -> dict:
    return {
        "region_key": str(getattr(row, "region_key", "suburban") or "suburban"),
        "as_of_day": int(getattr(row, "as_of_day", 0) or 0),
        "as_of_date": row.as_of_date.isoformat() if getattr(row, "as_of_date", None) else None,
        "active_population_score": float(_q4(_d(getattr(row, "active_population_score", 0)))),
        "opportunity_density_score": float(_q4(_d(getattr(row, "opportunity_density_score", 0)))),
        "congestion_score": float(_q4(_d(getattr(row, "congestion_score", 0)))),
        "housing_pressure_score": float(_q4(_d(getattr(row, "housing_pressure_score", 0)))),
        "business_competition_score": float(_q4(_d(getattr(row, "business_competition_score", 0)))),
        "consumer_flow_score": float(_q4(_d(getattr(row, "consumer_flow_score", 0)))),
        "heat_level": str(getattr(row, "heat_level", "warm") or "warm"),
        "recent_growth_direction": str(getattr(row, "recent_growth_direction", "stable") or "stable"),
        "summary_json": _parse_json(getattr(row, "summary_json", None)) or {},
        "debug_json": _parse_json(getattr(row, "debug_json", None)) or {},
    }


def _serialize_business_row(row: PlayerBusiness) -> dict:
    upgrades_raw = _parse_json(getattr(row, "upgrades_json", "[]"))
    upgrades = (
        sorted(
            set(
                item.strip()
                for item in upgrades_raw
                if isinstance(item, str) and item.strip()
            )
        )
        if isinstance(upgrades_raw, list)
        else []
    )
    return {
        "business_id": str(row.id),
        "business_type": row.business_type,
        "business_name": row.business_name,
        "region": row.region,
        "region_key": row.region,
        "level_key": row.level_key,
        "tier": int(row.tier or 1),
        "active_flag": bool(row.active_flag),
        "reputation": int(row.reputation or 0),
        "fruit_markup_pct": float(_q4(_d(getattr(row, "fruit_markup_pct", 0)))),
        "cash_invested_xgp": float(_money(_d(getattr(row, "cash_invested_xgp", 0)))),
        "cash_reserve_xgp": float(_money(_d(row.cash_reserve_xgp))),
        "inventory_produce_units": float(_q4(_d(getattr(row, "inventory_produce_units", 0)))),
        "inventory_essentials_units": float(_q4(_d(getattr(row, "inventory_essentials_units", 0)))),
        "inventory_protein_units": float(_q4(_d(getattr(row, "inventory_protein_units", 0)))),
        "operating_mode": str(getattr(row, "operating_mode", "") or ""),
        "upgrades": upgrades,
        "created_day": int(row.created_day or 0),
        "last_operated_day": int(row.last_operated_day) if row.last_operated_day is not None else None,
        "last_operated_on": row.last_operated_on.isoformat() if getattr(row, "last_operated_on", None) else None,
    }


def _serialize_business_log(row: BusinessDailyLog) -> dict:
    debug_meta = _parse_json(row.debug_json or row.notes_json) or {}
    return {
        "business_id": str(row.business_id),
        "player_id": str(row.player_id),
        "day": int(row.day),
        "as_of_date": row.as_of_date.isoformat() if getattr(row, "as_of_date", None) else None,
        "business_type": row.business_type,
        "region_key": row.region_key,
        "gross_revenue_xgp": float(_money(_d(row.gross_revenue_xgp))),
        "revenue_xgp": float(_money(_d(row.gross_revenue_xgp))),
        "input_cost_xgp": float(_money(_d(row.input_cost_xgp))),
        "cogs_xgp": float(_money(_d(row.input_cost_xgp))),
        "fuel_cost_xgp": float(_money(_d(row.fuel_cost_xgp))),
        "maintenance_cost_xgp": float(_money(_d(getattr(row, "maintenance_cost_xgp", 0)))),
        "spoilage_cost_xgp": float(_money(_d(row.spoilage_cost_xgp))),
        "spoilage_loss_xgp": float(_money(_d(row.spoilage_cost_xgp))),
        "overhead_cost_xgp": float(_money(_d(row.overhead_cost_xgp))),
        "overhead_xgp": float(_money(_d(row.overhead_cost_xgp))),
        "net_profit_xgp": float(_money(_d(row.net_profit_xgp))),
        "units_sold": int(getattr(row, "units_sold", 0) or 0),
        "inventory_start_units": float(_q4(_d(getattr(row, "inventory_start_units", 0)))),
        "inventory_end_units": float(_q4(_d(getattr(row, "inventory_end_units", 0)))),
        "demand_signal": float(_q4(_d(getattr(row, "demand_signal", 0)))),
        "reputation_before": int(getattr(row, "reputation_before", 0) or 0),
        "reputation_after": int(getattr(row, "reputation_after", 0) or 0),
        "operating_mode": str(debug_meta.get("operating_mode", "") or ""),
        "upgrades": (
            sorted(
                set(
                    item.strip()
                    for item in (debug_meta.get("upgrades") or [])
                    if isinstance(item, str) and item.strip()
                )
            )
            if isinstance(debug_meta.get("upgrades"), list)
            else []
        ),
        "demand_score": float(_q4(_d(row.demand_score))),
        "utilization_pct": float(_q4(_d(row.utilization_pct))),
        "profit_driver_breakdown": {
            "revenue_xgp": float(_money(_d(row.gross_revenue_xgp))),
            "cogs_xgp": float(_money(_d(row.input_cost_xgp))),
            "overhead_xgp": float(_money(_d(row.overhead_cost_xgp))),
            "spoilage_loss_xgp": float(_money(_d(row.spoilage_cost_xgp))),
            "fuel_cost_xgp": float(_money(_d(row.fuel_cost_xgp))),
            "maintenance_cost_xgp": float(_money(_d(getattr(row, "maintenance_cost_xgp", 0)))),
            "net_profit_xgp": float(_money(_d(row.net_profit_xgp))),
            "units_sold": int(getattr(row, "units_sold", 0) or 0),
            "demand_signal": float(_q4(_d(getattr(row, "demand_signal", 0)))),
        },
        "fruit_shop_drivers": {
            "markup_pct": debug_meta.get("markup_pct"),
            "elasticity": debug_meta.get("elasticity"),
            "sell_price": debug_meta.get("sell_price"),
            "market_reference_price": debug_meta.get("market_reference_price"),
            "wholesale_unit_cost": debug_meta.get("wholesale_unit_cost"),
        },
        "food_truck_drivers": {
            "foot_traffic": debug_meta.get("foot_traffic"),
            "avg_ticket_xgp": debug_meta.get("avg_ticket_xgp"),
            "available_sales": debug_meta.get("available_sales"),
            "desired_sales": debug_meta.get("desired_sales"),
            "oil_index": debug_meta.get("oil_index"),
        },
        "notes_json": _parse_json(row.notes_json),
        "debug_json": debug_meta,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_settlement(log: DailySettlementLog | None) -> dict | None:
    if log is None:
        return None
    summary_json = _parse_json(log.summary_json) or {}
    return {
        "day_number": int(log.day_number),
        "income_xgp": float(_money(_d(log.income_xgp))),
        "expenses_xgp": float(_money(_d(log.expenses_xgp))),
        "debt_paid_xgp": float(_money(_d(log.debt_paid_xgp))),
        "debt_payment_due_xgp": float(
            _money(_d(summary_json.get("debt_payment_due_xgp", getattr(log, "debt_payment_due_xgp", 0))))
        ),
        "debt_payment_paid_xgp": float(
            _money(_d(summary_json.get("debt_payment_paid_xgp", getattr(log, "debt_payment_paid_xgp", 0))))
        ),
        "debt_payment_missed": bool(
            summary_json.get("debt_payment_missed", bool(getattr(log, "debt_payment_missed", False)))
        ),
        "late_fee_xgp": float(_money(_d(summary_json.get("late_fee_xgp", getattr(log, "late_fee_xgp", 0))))),
        "accrued_interest_xgp": float(
            _money(_d(summary_json.get("accrued_interest_xgp", getattr(log, "accrued_interest_xgp", 0))))
        ),
        "credit_score_before": int(summary_json.get("opening_credit_score", getattr(log, "credit_score_before", 650))),
        "credit_score_after": int(summary_json.get("ending_credit_score", getattr(log, "credit_score_after", 650))),
        "credit_score_delta": int(summary_json.get("credit_score_change", getattr(log, "credit_score_delta", 0))),
        "distress_state_before": summary_json.get("distress_state_before", getattr(log, "distress_state_before", "stable")),
        "distress_state_after": summary_json.get("distress_state_after", getattr(log, "distress_state_after", "stable")),
        "distress_score_before": float(
            _q4(_d(summary_json.get("distress_score_before", getattr(log, "distress_score_before", 0))))
        ),
        "distress_score_after": float(
            _q4(_d(summary_json.get("distress_score_after", getattr(log, "distress_score_after", 0))))
        ),
        "borrowing_cost_modifier": float(
            _q4(_d(summary_json.get("borrowing_cost_modifier", getattr(log, "borrowing_cost_modifier", 1))))
        ),
        "opportunity_access_penalty": float(
            _q4(_d(summary_json.get("opportunity_access_penalty", getattr(log, "opportunity_access_penalty", 0))))
        ),
        "business_risk_penalty": float(
            _q4(_d(summary_json.get("business_risk_penalty", getattr(log, "business_risk_penalty", 0))))
        ),
        "career_progress_penalty": float(
            _q4(_d(summary_json.get("career_progress_penalty", getattr(log, "career_progress_penalty", 0))))
        ),
        "recovery_actions_applied": summary_json.get("recovery_actions_applied", []),
        "financial_distress_summary": summary_json.get("financial_distress_summary", {}),
        "ending_cash_xgp": float(_money(_d(log.ending_cash_xgp))),
        "health_change": int(log.health_change or 0),
        "stress_change": int(log.stress_change or 0),
        "total_hours_used": float(_q4(_d(getattr(log, "total_hours_used", 0)))),
        "overtime_hours": float(_q4(_d(getattr(log, "overtime_hours", 0)))),
        "sleep_hours": float(_q4(_d(getattr(log, "sleep_hours", 0)))),
        "recovery_hours": float(_q4(_d(getattr(log, "recovery_hours", 0)))),
        "productivity_modifier": float(_q4(_d(getattr(log, "productivity_modifier", summary_json.get("productivity_modifier", 1))))),
        "burnout_risk": float(_q4(_d(getattr(log, "burnout_risk", summary_json.get("burnout_risk", 0))))),
        "medical_event_risk": float(
            _q4(_d(getattr(log, "medical_event_risk", summary_json.get("medical_event_risk", 0))))
        ),
        "medical_cost_xgp": float(_money(_d(getattr(log, "medical_cost_xgp", summary_json.get("medical_cost_xgp", 0))))),
        "missed_work_penalty_xgp": float(
            _money(_d(getattr(log, "missed_work_penalty_xgp", summary_json.get("missed_work_penalty_xgp", 0))))
        ),
        "personal_shock_summary": summary_json.get("personal_shock_summary"),
        "personal_shock_impacts": summary_json.get("personal_shock_impacts", {}),
        "personal_shock_cash_impact_xgp": float(summary_json.get("personal_shock_cash_impact_xgp", 0.0)),
        "personal_shock_operational_delta_xgp": float(
            summary_json.get("personal_shock_operational_delta_xgp", 0.0)
        ),
        "personal_shock_income_bonus_xgp": float(summary_json.get("personal_shock_income_bonus_xgp", 0.0)),
        "personal_shock_extra_expense_xgp": float(summary_json.get("personal_shock_extra_expense_xgp", 0.0)),
        "personal_shock_work_income_modifier": float(summary_json.get("personal_shock_work_income_modifier", 1.0)),
        "personal_shock_business_modifier": float(summary_json.get("personal_shock_business_modifier", 1.0)),
        "personal_shock_side_income_modifier": float(summary_json.get("personal_shock_side_income_modifier", 1.0)),
        "personal_shock_stress_delta": float(summary_json.get("personal_shock_stress_delta", 0.0)),
        "personal_shock_health_delta": float(summary_json.get("personal_shock_health_delta", 0.0)),
        "personal_shock_time_hours": float(summary_json.get("personal_shock_time_hours", 0.0)),
        "personal_shock_recent_event": summary_json.get("personal_shock_recent_event", {}),
        "personal_shock_recovery_state": summary_json.get("personal_shock_recovery_state", {}),
        "personal_shock_profile": summary_json.get("personal_shock_profile", {}),
        "personal_shock_risk_state": summary_json.get("personal_shock_risk_state", {}),
        "personal_shock_practical_actions": summary_json.get("personal_shock_practical_actions", []),
        "personal_shock_debug_meta": summary_json.get("personal_shock_debug_meta", {}),
        "region_key": (
            summary_json.get("region_key")
            or getattr(log, "region_key", None)
            or summary_json.get("housing_region")
            or getattr(log, "housing_region_id", None)
        ),
        "housing_cost_daily_xgp": float(
            _money(_d(summary_json.get("housing_cost_daily_xgp", getattr(log, "housing_cost_daily_xgp", 0))))
        ),
        "utilities_cost_daily_xgp": float(
            _money(_d(summary_json.get("utilities_cost_daily_xgp", getattr(log, "utilities_cost_daily_xgp", 0))))
        ),
        "commute_hours": float(_q4(_d(summary_json.get("commute_hours", getattr(log, "commute_hours", 0))))),
        "commute_fuel_cost_xgp": float(
            _money(_d(summary_json.get("commute_fuel_cost_xgp", getattr(log, "commute_fuel_cost_xgp", 0))))
        ),
        "region_stress_delta": float(
            _q4(_d(summary_json.get("region_stress_delta", getattr(log, "region_stress_delta", 0))))
        ),
        "region_opportunity_modifier": float(
            _q4(_d(summary_json.get("region_opportunity_modifier", getattr(log, "region_opportunity_modifier", 0))))
        ),
        "region_business_demand_modifier": float(
            _q4(_d(summary_json.get("region_business_demand_modifier", getattr(log, "region_business_demand_modifier", 0))))
        ),
        "region_side_income_modifier": float(
            _q4(_d(summary_json.get("region_side_income_modifier", getattr(log, "region_side_income_modifier", 0))))
        ),
        "networking_modifier": float(
            _q4(_d(summary_json.get("networking_modifier", getattr(log, "networking_modifier", 0))))
        ),
        "opportunity_quality_signal": float(
            _q4(_d(summary_json.get("opportunity_quality_signal", getattr(log, "opportunity_quality_signal", 1))))
        ),
        "housing_region_summary": summary_json.get("housing_region_summary", {}),
        "summary_json": summary_json,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_side_income_action(action: SideIncomeAction | None) -> dict | None:
    if action is None:
        return None
    return {
        "id": str(action.id),
        "day_number": int(action.day_number),
        "side_income_type": action.side_income_type,
        "hours_worked": float(action.hours_worked or 0),
        "gross_income_xgp": float(_money(_d(action.gross_income_xgp))),
        "fuel_cost_xgp": float(_money(_d(action.fuel_cost_xgp))),
        "wear_cost_xgp": float(_money(_d(getattr(action, "wear_cost_xgp", 0)))),
        "maintenance_cost_xgp": float(_money(_d(getattr(action, "maintenance_cost_xgp", 0)))),
        "net_income_xgp": float(_money(_d(action.net_income_xgp))),
        "demand_multiplier": float(_q4(_d(getattr(action, "demand_multiplier", 1)))),
        "region_side_income_modifier": float(_q4(_d(getattr(action, "region_side_income_modifier", 1)))),
        "gas_price_per_unit_xgp": float(_q4(_d(getattr(action, "gas_price_per_unit_xgp", 0)))),
        "wear_cost_per_hour_xgp": float(_q4(_d(getattr(action, "wear_cost_per_hour_xgp", 0)))),
        "reliability_before": float(_q4(_d(getattr(action, "reliability_before", 1)))),
        "reliability_after": float(_q4(_d(getattr(action, "reliability_after", 1)))),
        "oil_index_used": float(_q4(_d(action.oil_index_used))),
        "created_at": action.created_at.isoformat() if action.created_at else None,
    }


def _serialize_life_daily_state(row: PlayerDailyState | None) -> dict | None:
    if row is None:
        return None
    return {
        "day_number": int(row.day_number),
        "total_hours_used": float(_q4(_d(getattr(row, "total_hours_used", 0)))),
        "job_hours": float(_q4(_d(getattr(row, "job_hours", 0)))),
        "business_hours": float(_q4(_d(getattr(row, "business_hours", 0)))),
        "side_income_hours": float(_q4(_d(getattr(row, "side_income_hours", 0)))),
        "commute_hours": float(_q4(_d(getattr(row, "commute_hours", 0)))),
        "sleep_hours": float(_q4(_d(getattr(row, "sleep_hours", 0)))),
        "recovery_hours": float(_q4(_d(getattr(row, "recovery_hours", 0)))),
        "overtime_hours": float(_q4(_d(getattr(row, "overtime_hours", 0)))),
        "stress_before": int(getattr(row, "stress_start", 0)),
        "stress_after": int(getattr(row, "stress_end", 0)),
        "stress_delta": int(getattr(row, "stress_delta", 0)),
        "health_before": int(getattr(row, "health_start", 100)),
        "health_after": int(getattr(row, "health_end", 100)),
        "health_delta": int(getattr(row, "health_delta", 0)),
        "productivity_modifier": float(_q4(_d(getattr(row, "productivity_modifier", 1)))),
        "burnout_risk": float(_q4(_d(getattr(row, "burnout_risk", 0)))),
        "medical_event_risk": float(_q4(_d(getattr(row, "medical_event_risk", 0)))),
        "medical_cost_xgp": float(_money(_d(getattr(row, "medical_cost_xgp", 0)))),
        "missed_work_penalty_xgp": float(_money(_d(getattr(row, "missed_work_penalty_xgp", 0)))),
        "region_key": getattr(row, "region_key", None),
        "housing_cost_daily_xgp": float(_money(_d(getattr(row, "housing_cost_daily_xgp", 0)))),
        "utilities_cost_daily_xgp": float(_money(_d(getattr(row, "utilities_cost_daily_xgp", 0)))),
        "commute_fuel_cost_xgp": float(_money(_d(getattr(row, "commute_fuel_cost_xgp", 0)))),
        "region_stress_delta": float(_q4(_d(getattr(row, "region_stress_delta", 0)))),
        "region_opportunity_modifier": float(_q4(_d(getattr(row, "region_opportunity_modifier", 0)))),
        "region_business_demand_modifier": float(_q4(_d(getattr(row, "region_business_demand_modifier", 0)))),
        "region_side_income_modifier": float(_q4(_d(getattr(row, "region_side_income_modifier", 0)))),
        "networking_modifier": float(_q4(_d(getattr(row, "networking_modifier", 0)))),
        "opportunity_quality_signal": float(_q4(_d(getattr(row, "opportunity_quality_signal", 1)))),
        "housing_debug_json": _parse_json(getattr(row, "housing_debug_json", None)),
        "life_debug_json": _parse_json(getattr(row, "life_debug_json", None)),
    }


def _serialize_brief(log: DailyBriefLog | None) -> dict | None:
    if log is None:
        return None
    return {
        "id": str(log.id),
        "day": int(log.day),
        "headline": str(log.headline),
        "summary": str(log.summary),
        "macro_tags_json": _parse_json(log.macro_tags_json) or [],
        "player_impact_json": _parse_json(log.player_impact_json) or {},
        "action_hints_json": _parse_json(log.action_hints_json) or [],
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_macro(row: MacroDailyState | None) -> dict | None:
    if row is None:
        return None
    return {
        "day": int(row.day),
        "inflation_rate": float(_q4(_d(row.inflation_rate))),
        "interest_rate": float(_q4(_d(row.interest_rate))),
        "unemployment_rate": float(_q4(_d(row.unemployment_rate))),
        "oil_index": float(_q4(_d(row.oil_index))),
        "consumer_confidence": float(_q4(_d(row.consumer_confidence))),
        "supply_chain_stress": float(_q4(_d(row.supply_chain_stress))),
        "event_headline": row.event_headline,
        "event_summary": row.event_summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _latest_employment_state(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _job_monthly_pay(db: Session, job_code: str | None) -> Decimal:
    normalized = (job_code or "").strip().lower()
    if not normalized:
        return Decimal("0.00")

    db_row = db.query(JobDefinitionDB).filter(JobDefinitionDB.job_code == normalized).first()
    if db_row is not None:
        return _money(_d(db_row.base_monthly_pay_xgp))

    static = JOB_CATALOG.get(normalized)
    if static is not None:
        return _money(_d(static.monthly_salary))

    return Decimal("2600.00")


def _player_debug_summary(db: Session, player: Player) -> dict:
    active_housing = (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player.id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc())
        .first()
    )
    employment = _latest_employment_state(db, player.id)

    return {
        "player_id": str(player.id),
        "display_name": player.display_name,
        "gender": player.gender,
        "region": player.region,
        "cash_xgp": float(_money(_d(player.cash_xgp))),
        "bank_savings_xgp": float(_money(_d(player.bank_savings_xgp))),
        "debt_xgp": float(_money(_d(player.debt_xgp))),
        "credit_score": int(player.credit_score or 650),
        "net_worth_xgp": float(_money(_d(player.net_worth_xgp))),
        "health": int(player.health or 100),
        "stress": int(player.stress or 0),
        "productivity_modifier": float(_q4(_d(getattr(player, "productivity_modifier", 1.0)))),
        "base_productivity_modifier": float(_q4(_d(getattr(player, "base_productivity_modifier", 1.0)))),
        "burnout_risk": float(_q4(_d(getattr(player, "burnout_risk", 0.0)))),
        "medical_event_risk": float(_q4(_d(getattr(player, "medical_event_risk", 0.0)))),
        "available_hours": int(player.available_hours or 0),
        "active_housing_summary": _serialize_housing_state(active_housing),
        "active_employment_summary": _serialize_employment_state(employment),
    }


def _ensure_employment_row_for_debug(db: Session, player: Player) -> PlayerEmploymentState:
    existing = _latest_employment_state(db, player.id)
    if existing is not None:
        return existing

    default_job = (player.main_job or "retail_worker").strip().lower()
    if default_job not in SUPPORTED_STARTER_JOBS:
        default_job = "retail_worker"

    day = max(int(player.last_settled_day or 0) + 1, 1)
    monthly_pay = _job_monthly_pay(db, default_job)

    row = PlayerEmploymentState(
        player_id=player.id,
        day=day,
        current_job_code=default_job,
        skill_level=max(int(player.skill_level or 1), 1),
        monthly_pay_xgp=monthly_pay,
        employed_flag=True,
        layoff_risk_pct=Decimal("8.00"),
        productivity_modifier=Decimal("1.0000"),
        job_status="employed",
        promotion_eligible_flag=False,
        promotion_count=0,
        last_raise_pct=Decimal("0.00"),
        last_employment_event="debug_seeded",
        opportunity_score=Decimal("1.0000"),
        layoff_event_flag=False,
        promotion_chance_pct=Decimal("0.00"),
        wage_adjustment_pct=Decimal("0.00"),
        employment_evaluated_flag=False,
    )
    db.add(row)
    db.flush()
    return row


def _serialize_housing_log(row: HousingDailyLog | None) -> dict | None:
    if row is None:
        return None
    debug_meta = _parse_json(getattr(row, "housing_debug_json", None))
    return {
        "day": int(row.day),
        "region": row.region,
        "region_key": row.region,
        "housing_cost_daily_xgp": float(_money(_d(row.housing_cost_xgp))),
        "housing_cost_xgp": float(_money(_d(row.housing_cost_xgp))),
        "utilities_cost_daily_xgp": float(_money(_d(getattr(row, "utilities_cost_xgp", 0)))),
        "commute_hours": float(_q4(_d(getattr(row, "commute_hours", 0)))),
        "commute_fuel_cost_xgp": float(_money(_d(getattr(row, "commute_fuel_cost_xgp", 0)))),
        "commute_pressure": float(_q4(_d(row.commute_pressure))),
        "region_stress_delta": float(_q4(_d(getattr(row, "region_stress_delta", row.stress_delta)))),
        "stress_delta": int(row.stress_delta or 0),
        "region_opportunity_modifier": float(_q4(_d(getattr(row, "region_opportunity_modifier", 0)))),
        "region_business_demand_modifier": float(_q4(_d(getattr(row, "region_business_demand_modifier", 0)))),
        "region_side_income_modifier": float(_q4(_d(getattr(row, "region_side_income_modifier", 0)))),
        "networking_modifier": float(_q4(_d(getattr(row, "networking_modifier", 0)))),
        "opportunity_quality_signal": float(_q4(_d(getattr(row, "opportunity_quality_signal", 1)))),
        "opportunity_modifier": float(_q4(_d(row.opportunity_modifier))),
        "housing_debug_json": debug_meta,
        "notes_json": _parse_json(row.notes_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_basket_price(row: BasketDailyPrice) -> dict:
    return {
        "day": int(row.day),
        "basket_type": str(getattr(row.basket_type, "value", row.basket_type)),
        "price_index": float(_q4(_d(row.price_index))),
        "daily_change_pct": float(_q4(_d(row.daily_change_pct))),
        "supply_pressure": float(_q4(_d(row.supply_pressure))),
        "demand_pressure": float(_q4(_d(row.demand_pressure))),
    }


def _serialize_stock_price(row: StockDailyPrice) -> dict:
    return {
        "day": int(row.day),
        "ticker": row.ticker,
        "sector": row.sector,
        "open_price": float(_q4(_d(row.open_price))),
        "close_price": float(_q4(_d(row.close_price))),
        "daily_change_pct": float(_q4(_d(row.daily_change_pct))),
        "macro_impact": float(_q4(_d(row.macro_impact))),
        "noise_component": float(_q4(_d(row.noise_component))),
    }


def _placeholder_portfolio(player: Player) -> dict:
    return {
        "player_id": str(player.id),
        "cash_xgp": float(_money(_d(player.cash_xgp))),
        "total_market_value": 0.0,
        "total_cost_basis": 0.0,
        "total_unrealized_pnl": 0.0,
        "holdings": [],
    }


def _starter_region(region: str | None) -> str:
    normalized = (region or "suburban").strip().lower()
    if normalized not in STARTER_BASELINES:
        return "suburban"
    return normalized


def _starter_baseline(region: str | None) -> dict[str, Decimal | int]:
    return STARTER_BASELINES[_starter_region(region)]


def _current_or_new_employment_row(db: Session, player: Player, day: int) -> PlayerEmploymentState:
    existing = (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player.id,
            PlayerEmploymentState.day == int(day),
        )
        .order_by(PlayerEmploymentState.created_at.desc())
        .first()
    )
    if existing is not None:
        return existing

    row = PlayerEmploymentState(
        player_id=player.id,
        day=int(day),
        current_job_code=(player.main_job or "retail_worker"),
        skill_level=max(int(player.skill_level or 1), 1),
        monthly_pay_xgp=_job_monthly_pay(db, player.main_job or "retail_worker"),
        employed_flag=True,
        layoff_risk_pct=Decimal("8.00"),
        productivity_modifier=Decimal("1.0000"),
        job_status="employed",
        promotion_eligible_flag=False,
        promotion_count=0,
        last_raise_pct=Decimal("0.00"),
        last_employment_event="debug_reset",
        opportunity_score=Decimal("1.0000"),
        layoff_event_flag=False,
        promotion_chance_pct=Decimal("0.00"),
        wage_adjustment_pct=Decimal("0.00"),
        employment_evaluated_flag=False,
    )
    db.add(row)
    db.flush()
    return row


def _apply_starter_like_player_state(
    db: Session,
    player: Player,
    *,
    preserve_profile: bool,
    wipe_dependent_logs: bool,
) -> None:
    region = _starter_region(player.region)
    baseline = _starter_baseline(region)

    if wipe_dependent_logs:
        business_ids = [
            row[0]
            for row in (
                db.query(PlayerBusiness.id)
                .filter(PlayerBusiness.player_id == player.id)
                .all()
            )
        ]

        if business_ids:
            (
                db.query(BusinessDailyLog)
                .filter(BusinessDailyLog.business_id.in_(business_ids))
                .delete(synchronize_session=False)
            )
            (
                db.query(BusinessLedgerEntry)
                .filter(BusinessLedgerEntry.business_id.in_(business_ids))
                .delete(synchronize_session=False)
            )

        (
            db.query(PlayerBusiness)
            .filter(PlayerBusiness.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(BasketConsumptionLog)
            .filter(BasketConsumptionLog.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(DebtCreditLog)
            .filter(DebtCreditLog.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(HousingDailyLog)
            .filter(HousingDailyLog.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(DailySettlementLog)
            .filter(DailySettlementLog.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(DailyBriefLog)
            .filter(DailyBriefLog.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(PlayerDailyState)
            .filter(PlayerDailyState.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(StockTradeLog)
            .filter(StockTradeLog.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(PlayerStockHolding)
            .filter(PlayerStockHolding.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(PlayerEmploymentState)
            .filter(PlayerEmploymentState.player_id == player.id)
            .delete(synchronize_session=False)
        )
        (
            db.query(PlayerHousingState)
            .filter(PlayerHousingState.player_id == player.id)
            .delete(synchronize_session=False)
        )

    if not preserve_profile:
        player.display_name = player.display_name or f"Player-{str(player.id)[:8]}"
        player.gender = player.gender if player.gender in {"male", "female"} else "male"

    player.region = region
    player.housing_region_id = region
    player.has_active_housing = True

    player.cash_xgp = _money(_d(baseline["cash_xgp"]))
    player.bank_savings_xgp = _money(_d(baseline["bank_savings_xgp"]))
    player.debt_xgp = _money(_d(baseline["debt_xgp"]))
    player.credit_score = int(_clamp_int(int(baseline["credit_score"]), 300, 850))
    player.health = int(_clamp_int(int(baseline["health"]), 0, 100))
    player.stress = int(_clamp_int(int(baseline["stress"]), 0, 100))
    player.available_hours = int(max(int(baseline["available_hours"]), 0))
    player.skill_level = int(max(int(baseline["skill_level"]), 1))
    player.reputation = int(baseline["reputation"])

    player.main_job = (player.main_job or "retail_worker").strip().lower()
    if player.main_job not in SUPPORTED_STARTER_JOBS:
        player.main_job = "retail_worker"

    player.main_job_hours_today = 0
    player.side_job_hours_today = 0
    player.total_hours_worked_today = 0
    player.work_actions_today = 0

    if wipe_dependent_logs:
        player.last_settled_day = None

    player.net_worth_xgp = _money(
        _d(player.cash_xgp) + _d(player.bank_savings_xgp) - _d(player.debt_xgp)
    )

    assign_player_housing(
        db=db,
        player_id=player.id,
        region=region,
        housing_type="starter_rent",
        commit=False,
    )

    target_day = 1 if wipe_dependent_logs else max(int(player.last_settled_day or 0) + 1, 1)
    employment_row = _current_or_new_employment_row(db, player, target_day)
    employment_row.current_job_code = player.main_job
    employment_row.skill_level = max(int(player.skill_level or 1), 1)
    employment_row.monthly_pay_xgp = _job_monthly_pay(db, player.main_job)
    employment_row.employed_flag = True
    employment_row.job_status = "employed"
    employment_row.layoff_risk_pct = Decimal("8.00")
    employment_row.productivity_modifier = Decimal("1.0000")
    employment_row.promotion_eligible_flag = False
    employment_row.last_employment_event = "debug_reset"
    employment_row.opportunity_score = Decimal("1.0000")
    employment_row.layoff_event_flag = False
    employment_row.promotion_chance_pct = Decimal("0.00")
    employment_row.wage_adjustment_pct = Decimal("0.00")
    employment_row.employment_evaluated_flag = False


def _career_snapshot_safe(db: Session, player_id: UUID) -> dict:
    """Return career snapshot for debug snapshot; silently returns empty dict on error."""
    try:
        return get_player_career_snapshot(db, player_id)
    except CareerServiceError:
        return {}
    except Exception:
        return {}


def _event_snapshot_safe(db: Session, day: int | None) -> dict:
    """Return event snapshot for debug; silently returns empty dict on error."""
    if day is None:
        return {}
    try:
        from app.engine.event_service import get_event_snapshot, get_active_chains
        snapshot = get_event_snapshot(db, day) or {}
        # Step 19.5: append chain summary
        try:
            active = get_active_chains(db, day)
            if active:
                snapshot["active_chains"] = active
        except Exception:
            pass
        return snapshot
    except Exception:
        return {}


def get_full_player_debug_snapshot(db: Session, player_id: str | UUID) -> dict:
    """Return a consolidated multi-system debug snapshot for one player."""
    player = _resolve_player(db, player_id)

    active_housing = (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player.id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc())
        .first()
    )
    latest_employment = _latest_employment_state(db, player.id)
    latest_consumption = (
        db.query(BasketConsumptionLog)
        .filter(BasketConsumptionLog.player_id == player.id)
        .order_by(BasketConsumptionLog.day.desc(), BasketConsumptionLog.created_at.desc())
        .first()
    )
    latest_debt = (
        db.query(DebtCreditLog)
        .filter(DebtCreditLog.player_id == player.id)
        .order_by(DebtCreditLog.day.desc(), DebtCreditLog.created_at.desc())
        .first()
    )
    try:
        latest_financial_distress = (
            db.query(FinancialDistressLog)
            .filter(FinancialDistressLog.player_id == player.id)
            .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
            .first()
        )
    except Exception:
        latest_financial_distress = None
    try:
        delinquency_state = (
            db.query(PlayerDelinquencyState)
            .filter(PlayerDelinquencyState.player_id == player.id)
            .first()
        )
    except Exception:
        delinquency_state = None
    try:
        latest_payment_history = (
            db.query(PlayerPaymentHistory)
            .filter(PlayerPaymentHistory.player_id == player.id)
            .order_by(PlayerPaymentHistory.day_number.desc(), PlayerPaymentHistory.created_at.desc())
            .first()
        )
        payment_history_rows = (
            db.query(PlayerPaymentHistory)
            .filter(PlayerPaymentHistory.player_id == player.id)
            .order_by(PlayerPaymentHistory.day_number.desc(), PlayerPaymentHistory.created_at.desc())
            .limit(20)
            .all()
        )
    except Exception:
        latest_payment_history = None
        payment_history_rows = []
    try:
        borrowing_state = (
            db.query(PlayerBorrowingState)
            .filter(PlayerBorrowingState.player_id == player.id)
            .first()
        )
    except Exception:
        borrowing_state = None
    try:
        borrowing_loan_account_rows = (
            db.query(PlayerLoanAccount)
            .filter(PlayerLoanAccount.player_id == player.id)
            .order_by(
                PlayerLoanAccount.accepted_on_day.desc(),
                PlayerLoanAccount.updated_at.desc(),
            )
            .limit(20)
            .all()
        )
    except Exception:
        borrowing_loan_account_rows = []
    try:
        borrowing_history_rows = (
            db.query(PlayerBorrowingHistory)
            .filter(PlayerBorrowingHistory.player_id == player.id)
            .order_by(
                PlayerBorrowingHistory.day_number.desc(),
                PlayerBorrowingHistory.updated_at.desc(),
            )
            .limit(30)
            .all()
        )
    except Exception:
        borrowing_history_rows = []
    latest_settlement = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == player.id)
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    latest_brief = (
        db.query(DailyBriefLog)
        .filter(DailyBriefLog.player_id == player.id)
        .order_by(DailyBriefLog.day.desc(), DailyBriefLog.created_at.desc())
        .first()
    )
    latest_housing_log = (
        db.query(HousingDailyLog)
        .filter(HousingDailyLog.player_id == player.id)
        .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
        .first()
    )
    latest_daily_state = (
        db.query(PlayerDailyState)
        .filter(PlayerDailyState.player_id == player.id)
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .first()
    )
    try:
        progression_state = (
            db.query(PlayerProgressionState)
            .filter(PlayerProgressionState.player_id == player.id)
            .first()
        )
        progression_history_rows = (
            db.query(PlayerGoalHistory)
            .filter(PlayerGoalHistory.player_id == player.id)
            .order_by(PlayerGoalHistory.day_number.desc(), PlayerGoalHistory.updated_at.desc())
            .limit(20)
            .all()
        )
    except Exception:
        progression_state = None
        progression_history_rows = []
    try:
        onboarding_state = (
            db.query(PlayerOnboardingState)
            .filter(PlayerOnboardingState.player_id == player.id)
            .first()
        )
    except Exception:
        onboarding_state = None
    try:
        commitment_state = (
            db.query(PlayerCommitmentState)
            .filter(PlayerCommitmentState.player_id == player.id)
            .first()
        )
        commitment_history_rows = (
            db.query(PlayerCommitmentHistory)
            .filter(PlayerCommitmentHistory.player_id == player.id)
            .order_by(PlayerCommitmentHistory.updated_at.desc())
            .limit(20)
            .all()
        )
    except Exception:
        commitment_state = None
        commitment_history_rows = []
    try:
        latest_side_income = (
            db.query(SideIncomeAction)
            .filter(SideIncomeAction.player_id == player.id)
            .order_by(SideIncomeAction.day_number.desc(), SideIncomeAction.created_at.desc())
            .first()
        )
    except Exception:
        latest_side_income = None
    try:
        shock_state = (
            db.query(PlayerShockState)
            .filter(PlayerShockState.player_id == player.id)
            .first()
        )
    except Exception:
        shock_state = None
    try:
        recovery_state = (
            db.query(PlayerRecoveryState)
            .filter(PlayerRecoveryState.player_id == player.id)
            .first()
        )
    except Exception:
        recovery_state = None
    try:
        life_event_rows = (
            db.query(PlayerLifeEventHistory)
            .filter(PlayerLifeEventHistory.player_id == player.id)
            .order_by(
                PlayerLifeEventHistory.day_number.desc(),
                PlayerLifeEventHistory.created_at.desc(),
            )
            .limit(20)
            .all()
        )
    except Exception:
        life_event_rows = []

    businesses = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id)
        .order_by(PlayerBusiness.created_at.desc())
        .all()
    )
    latest_business_logs = (
        db.query(BusinessDailyLog)
        .filter(BusinessDailyLog.player_id == player.id)
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .limit(10)
        .all()
    )
    latest_business_day = int(latest_business_logs[0].day) if latest_business_logs else None
    latest_day_business_net = Decimal("0.00")
    if latest_business_day is not None:
        latest_day_business_net = _money(
            sum(
                (
                    _d(log.net_profit_xgp)
                    for log in latest_business_logs
                    if int(log.day) == latest_business_day
                ),
                Decimal("0"),
            )
        )

    try:
        portfolio = _stock_service.get_player_portfolio(db, player.id)
    except StockTradingError:
        portfolio = _placeholder_portfolio(player)
    except Exception:
        portfolio = _placeholder_portfolio(player)

    latest_settlement_payload = _serialize_settlement(latest_settlement)
    settlement_summary = latest_settlement_payload["summary_json"] if latest_settlement_payload else {}

    context_day = (
        int(latest_settlement.day_number)
        if latest_settlement is not None
        else (
            int(latest_employment.day)
            if latest_employment is not None
            else int(db.query(func.max(MacroDailyState.day)).scalar() or 1)
        )
    )
    active_job_modifiers = {
        "active_job_pressure": 0.0,
        "active_job_opportunity_modifier": 0.0,
        "active_job_wage_drift_modifier": 0.0,
        "active_job_layoff_risk_modifier": 0.0,
        "active_job_direction": "neutral",
        "job_market_day_used": context_day,
    }
    current_job_code = (
        (latest_employment.current_job_code if latest_employment is not None else None)
        or player.main_job
    )
    if current_job_code:
        try:
            market_updates = compute_daily_job_market_updates(db, day=context_day)
            by_job = {str(row["job_key"]): row for row in market_updates.get("job_updates", [])}
            row = by_job.get(str(current_job_code).strip().lower())
            if row is not None:
                active_job_modifiers = {
                    "active_job_pressure": float(_q4(_d(row.get("pressure", 0)))),
                    "active_job_opportunity_modifier": float(
                        _q4(_d(row.get("opportunity_modifier", 0)))
                    ),
                    "active_job_wage_drift_modifier": float(
                        _q4(_d(row.get("wage_drift_modifier", 0)))
                    ),
                    "active_job_layoff_risk_modifier": float(
                        _q4(_d(row.get("layoff_risk_modifier", 0)))
                    ),
                    "active_job_direction": str(row.get("direction", "neutral")),
                    "job_market_day_used": int(market_updates.get("day", context_day)),
                }
        except (JobMarketError, SupplyChainError):
            pass

    housing_snapshot = _serialize_housing_state(active_housing)
    housing_log_snapshot = _serialize_housing_log(latest_housing_log)
    life_snapshot = _serialize_life_daily_state(latest_daily_state)
    settlement_snapshot = latest_settlement_payload or {}
    location_chain = {
        "region_key": (
            (housing_snapshot or {}).get("region_key")
            or (housing_log_snapshot or {}).get("region_key")
            or settlement_snapshot.get("region_key")
            or player.region
        ),
        "housing_state": housing_snapshot,
        "daily_housing_effect": housing_log_snapshot,
        "from_life": {
            "commute_hours": (life_snapshot or {}).get("commute_hours"),
            "region_stress_delta": (life_snapshot or {}).get("region_stress_delta"),
            "region_opportunity_modifier": (life_snapshot or {}).get("region_opportunity_modifier"),
            "region_business_demand_modifier": (life_snapshot or {}).get("region_business_demand_modifier"),
            "region_side_income_modifier": (life_snapshot or {}).get("region_side_income_modifier"),
        },
        "from_settlement": {
            "housing_cost_daily_xgp": settlement_snapshot.get("housing_cost_daily_xgp"),
            "utilities_cost_daily_xgp": settlement_snapshot.get("utilities_cost_daily_xgp"),
            "commute_fuel_cost_xgp": settlement_snapshot.get("commute_fuel_cost_xgp"),
            "networking_modifier": settlement_snapshot.get("networking_modifier"),
            "opportunity_quality_signal": settlement_snapshot.get("opportunity_quality_signal"),
        },
        "from_financial_distress": (
            _serialize_financial_distress(latest_financial_distress) or {}
        ),
    }
    try:
        player_balance_snapshot = get_player_balance_snapshot(db=db, player_id=player.id)
    except Exception:
        player_balance_snapshot = {}
    try:
        exploit_flags_snapshot = detect_player_exploit_flags(db=db, player_id=player.id)
    except Exception:
        exploit_flags_snapshot = {}
    try:
        strategy_classification_snapshot = classify_player_strategy(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            lookback_days=7,
        )
    except Exception:
        strategy_classification_snapshot = {}
    try:
        weekly_strategy_summary = build_player_weekly_strategy_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        weekly_strategy_summary = {}
    try:
        progression_summary_snapshot = build_progression_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
            persist=False,
        )
    except Exception:
        progression_summary_snapshot = {}
    try:
        onboarding_state_snapshot = build_onboarding_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        onboarding_state_snapshot = {}
    try:
        onboarding_guidance_snapshot = build_onboarding_guidance(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        onboarding_guidance_snapshot = {}
    try:
        onboarding_dashboard_config_snapshot = build_first_session_dashboard_config(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        onboarding_dashboard_config_snapshot = {}
    try:
        onboarding_unlock_schedule_snapshot = build_unlock_schedule(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        onboarding_unlock_schedule_snapshot = {}
    try:
        onboarding_completion_debug = evaluate_onboarding_completion(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            action_key=None,
        )
    except Exception:
        onboarding_completion_debug = {}
    try:
        economy_presentation_summary = build_economy_presentation_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        economy_presentation_summary = {}
    try:
        strategic_planning_summary = build_strategic_planning_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        strategic_planning_summary = {}
    try:
        commitment_available = build_available_commitments(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        commitment_available = {}
    try:
        commitment_summary_snapshot = build_commitment_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            evaluate=False,
        )
    except Exception:
        commitment_summary_snapshot = {}
    try:
        commitment_feedback_snapshot = build_commitment_feedback(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        commitment_feedback_snapshot = {}
    try:
        commitment_drift_snapshot = detect_commitment_drift(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        commitment_drift_snapshot = {}
    try:
        commitment_adherence_snapshot = evaluate_commitment_adherence(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            action_key=None,
        )
    except Exception:
        commitment_adherence_snapshot = {}
    try:
        commitment_history_snapshot = get_player_commitment_history(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            limit=20,
        )
    except Exception:
        commitment_history_snapshot = {}
    try:
        world_memory_state = (
            db.query(PlayerWorldMemoryState)
            .filter(PlayerWorldMemoryState.player_id == player.id)
            .first()
        )
        world_pattern_history_rows = (
            db.query(PlayerWorldPatternHistory)
            .filter(PlayerWorldPatternHistory.player_id == player.id)
            .order_by(
                PlayerWorldPatternHistory.last_seen_on_day.desc(),
                PlayerWorldPatternHistory.updated_at.desc(),
            )
            .limit(30)
            .all()
        )
    except Exception:
        world_memory_state = None
        world_pattern_history_rows = []
    try:
        world_memory_snapshot = get_world_memory_snapshot(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_memory_snapshot = {}
    try:
        world_pattern_detection = detect_world_patterns(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_pattern_detection = {}
    try:
        world_narrative_snapshot = build_world_narrative(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_narrative_snapshot = {}
    try:
        world_local_pressure_snapshot = build_world_local_pressure_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_local_pressure_snapshot = {}
    try:
        world_player_pattern_snapshot = build_world_player_pattern_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_player_pattern_snapshot = {}
    try:
        world_region_memory_snapshot = build_world_region_memory_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_region_memory_snapshot = {}
    try:
        world_memory_history_snapshot = build_world_memory_history(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            limit=30,
        )
    except Exception:
        world_memory_history_snapshot = {}
    try:
        world_memory_summary_snapshot = build_world_memory_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        world_memory_summary_snapshot = {}
    try:
        personal_shock_profile_snapshot = build_personal_shock_profile(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        personal_shock_profile_snapshot = {}
    try:
        personal_shock_risk_snapshot = build_shock_risk_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        personal_shock_risk_snapshot = {}
    try:
        personal_shock_recent_event_snapshot = get_recent_personal_life_event(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        personal_shock_recent_event_snapshot = {}
    try:
        personal_shock_recovery_snapshot = get_player_recovery_state(
            db=db,
            player_id=player.id,
        )
    except Exception:
        personal_shock_recovery_snapshot = {}
    try:
        personal_resilience_summary_snapshot = build_player_resilience_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        personal_resilience_summary_snapshot = {}
    try:
        personal_shock_summary_snapshot = build_personal_shock_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        personal_shock_summary_snapshot = {}
    try:
        personal_shock_system_summary_snapshot = build_personal_shock_system_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        personal_shock_system_summary_snapshot = {}
    try:
        financial_obligation_profile_snapshot = build_player_obligation_profile(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        financial_obligation_profile_snapshot = {}
    try:
        financial_payment_risk_snapshot = build_payment_risk_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        financial_payment_risk_snapshot = {}
    try:
        financial_delinquency_state_snapshot = build_delinquency_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        financial_delinquency_state_snapshot = {}
    try:
        financial_survival_summary_snapshot = build_financial_survival_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        financial_survival_summary_snapshot = {}
    try:
        financial_payment_history_snapshot = get_player_payment_history(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
            limit=20,
        )
    except Exception:
        financial_payment_history_snapshot = {}
    try:
        financial_survival_system_summary_snapshot = build_financial_survival_system_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        financial_survival_system_summary_snapshot = {}
    financial_credit_impact_snapshot = (
        financial_survival_system_summary_snapshot.get("credit_impact", {})
        if isinstance(financial_survival_system_summary_snapshot, dict)
        else {}
    )
    try:
        borrowing_eligibility_profile_snapshot = build_borrowing_eligibility_profile(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        borrowing_eligibility_profile_snapshot = {}
    try:
        borrowing_liquidity_state_snapshot = build_emergency_liquidity_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        borrowing_liquidity_state_snapshot = {}
    try:
        borrowing_options_snapshot = generate_borrowing_options(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
            include_locked=True,
        )
    except Exception:
        borrowing_options_snapshot = {}
    try:
        borrowing_risk_summary_snapshot = build_borrowing_risk_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        borrowing_risk_summary_snapshot = {}
    try:
        borrowing_pressure_summary_snapshot = build_borrowing_pressure_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        borrowing_pressure_summary_snapshot = {}
    try:
        borrowing_loan_accounts_snapshot = get_player_loan_accounts(
            db=db,
            player_id=player.id,
            include_closed=False,
        )
    except Exception:
        borrowing_loan_accounts_snapshot = {}
    try:
        borrowing_history_snapshot = get_player_borrowing_history(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
            limit=30,
        )
    except Exception:
        borrowing_history_snapshot = {}
    try:
        borrowing_system_summary_snapshot = build_consumer_borrowing_system_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
            day_number=context_day,
        )
    except Exception:
        borrowing_system_summary_snapshot = {}
    region_context_key = (
        str(getattr(active_housing, "region", "") or player.region or "suburban")
        .strip()
        .lower()
        or "suburban"
    )
    try:
        region_population_state_row = (
            db.query(RegionPopulationState)
            .filter(RegionPopulationState.region_key == region_context_key)
            .first()
        )
    except Exception:
        region_population_state_row = None
    try:
        region_population_history_rows = (
            db.query(RegionPopulationHistory)
            .filter(RegionPopulationHistory.region_key == region_context_key)
            .order_by(
                RegionPopulationHistory.as_of_day.desc(),
                RegionPopulationHistory.updated_at.desc(),
            )
            .limit(20)
            .all()
        )
    except Exception:
        region_population_history_rows = []
    try:
        population_region_state_snapshot = build_region_population_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_region_state_snapshot = {}
    try:
        population_opportunity_snapshot = build_local_opportunity_pressure(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_opportunity_snapshot = {}
    try:
        population_competition_snapshot = build_local_competition_state(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_competition_snapshot = {}
    try:
        population_heat_snapshot = build_region_heat_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_heat_snapshot = {}
    try:
        population_response_snapshot = build_population_response_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_response_snapshot = {}
    try:
        population_summary_snapshot = build_population_pressure_summary(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_summary_snapshot = {}
    try:
        population_refresh_snapshot = update_population_pressure(
            db=db,
            player_id=player.id,
            as_of_date=_day_to_date(context_day),
        )
    except Exception:
        population_refresh_snapshot = {}

    mode_breakdown: dict[str, int] = {}
    for row in latest_business_logs:
        debug_meta = _parse_json(row.debug_json) or {}
        if not isinstance(debug_meta, dict):
            continue
        mode_key = str(debug_meta.get("operating_mode") or "default")
        mode_breakdown[mode_key] = int(mode_breakdown.get(mode_key, 0)) + 1

    return {
        "player_profile": {
            "player_id": str(player.id),
            "display_name": player.display_name,
            "gender": player.gender,
            "region": player.region,
            "cash_xgp": float(_money(_d(player.cash_xgp))),
            "bank_savings_xgp": float(_money(_d(player.bank_savings_xgp))),
            "debt_xgp": float(_money(_d(player.debt_xgp))),
            "credit_score": int(player.credit_score or 650),
            "required_daily_debt_payment_xgp": float(_money(_d(getattr(player, "required_daily_debt_payment_xgp", 0)))),
            "debt_utilization_ratio": float(_q4(_d(getattr(player, "debt_utilization_ratio", 0)))),
            "missed_payment_streak": int(getattr(player, "missed_payment_streak", 0) or 0),
            "on_payment_plan": bool(getattr(player, "on_payment_plan", False)),
            "distress_state": str(getattr(player, "distress_state", "stable") or "stable"),
            "distress_score": float(_q4(_d(getattr(player, "distress_score", 0)))),
            "borrowing_cost_modifier": float(_q4(_d(getattr(player, "borrowing_cost_modifier", 1)))),
            "opportunity_access_penalty": float(_q4(_d(getattr(player, "opportunity_access_penalty", 0)))),
            "business_risk_penalty": float(_q4(_d(getattr(player, "business_risk_penalty", 0)))),
            "career_progress_penalty": float(_q4(_d(getattr(player, "career_progress_penalty", 0)))),
            "net_worth_xgp": float(_money(_d(player.net_worth_xgp))),
            "health": int(player.health or 100),
            "stress": int(player.stress or 0),
            "productivity_modifier": float(_q4(_d(getattr(player, "productivity_modifier", 1.0)))),
            "base_productivity_modifier": float(_q4(_d(getattr(player, "base_productivity_modifier", 1.0)))),
            "burnout_risk": float(_q4(_d(getattr(player, "burnout_risk", 0.0)))),
            "medical_event_risk": float(_q4(_d(getattr(player, "medical_event_risk", 0.0)))),
            "available_hours": int(player.available_hours or 0),
            "main_job": player.main_job,
            "last_settled_day": int(player.last_settled_day) if player.last_settled_day is not None else None,
            "created_at": player.created_at.isoformat() if player.created_at else None,
            "updated_at": player.updated_at.isoformat() if player.updated_at else None,
        },
        "active_housing_summary": housing_snapshot,
        "latest_housing_log": housing_log_snapshot,
        "active_employment_summary": _serialize_employment_state(latest_employment),
        "latest_job_summary": {
            "employment_state": _serialize_employment_state(latest_employment),
            "from_latest_settlement": {
                "employment_status": settlement_summary.get("employment_status"),
                "employment_event": settlement_summary.get("employment_event"),
                "layoff_risk_pct": settlement_summary.get("layoff_risk_pct"),
                "promotion_chance_pct": settlement_summary.get("promotion_chance_pct"),
                "wage_adjustment_pct": settlement_summary.get("wage_adjustment_pct"),
                "employment_job_code": settlement_summary.get("employment_job_code"),
            },
            **active_job_modifiers,
        },
        "latest_consumption_summary": _serialize_consumption(latest_consumption),
        "latest_debt_credit_summary": _serialize_debt_credit(latest_debt),
        "latest_financial_distress_summary": _serialize_financial_distress(latest_financial_distress),
        "businesses": [_serialize_business_row(row) for row in businesses],
        "latest_business_summary": {
            "total_business_count": len(businesses),
            "active_business_count": len([row for row in businesses if bool(row.active_flag)]),
            "latest_day": latest_business_day,
            "latest_day_net_profit_xgp": float(_money(_d(latest_day_business_net))),
            "current_business_modes": [
                {
                    "business_id": str(row.id),
                    "business_type": str(row.business_type),
                    "operating_mode": str(getattr(row, "operating_mode", "") or ""),
                    "upgrades": _serialize_business_row(row).get("upgrades", []),
                }
                for row in businesses
            ],
            "mode_breakdown": mode_breakdown,
            "recent_logs": [_serialize_business_log(row) for row in latest_business_logs],
        },
        "latest_side_income_summary": _serialize_side_income_action(latest_side_income),
        "personal_shock_state_raw": _serialize_shock_state(shock_state),
        "personal_recovery_state_raw": _serialize_recovery_state(recovery_state),
        "personal_life_event_history_raw": [
            _serialize_life_event_history(row) for row in life_event_rows
        ],
        "personal_shock_profile": personal_shock_profile_snapshot,
        "personal_shock_risk_state": personal_shock_risk_snapshot,
        "personal_recent_life_event": personal_shock_recent_event_snapshot,
        "personal_recovery_state": personal_shock_recovery_snapshot,
        "personal_resilience_summary": personal_resilience_summary_snapshot,
        "personal_shock_summary": personal_shock_summary_snapshot,
        "personal_shock_system_summary": personal_shock_system_summary_snapshot,
        "financial_delinquency_state_raw": _serialize_delinquency_state(delinquency_state),
        "financial_latest_payment_history_raw": _serialize_payment_history_row(latest_payment_history),
        "financial_payment_history_raw": [
            _serialize_payment_history_row(row) for row in payment_history_rows
        ],
        "financial_obligation_profile": financial_obligation_profile_snapshot,
        "financial_payment_risk_state": financial_payment_risk_snapshot,
        "financial_delinquency_state": financial_delinquency_state_snapshot,
        "financial_credit_impact": financial_credit_impact_snapshot,
        "financial_survival_summary": financial_survival_summary_snapshot,
        "financial_payment_history": financial_payment_history_snapshot,
        "financial_survival_system_summary": financial_survival_system_summary_snapshot,
        "borrowing_state_raw": _serialize_borrowing_state(borrowing_state),
        "borrowing_loan_accounts_raw": [
            _serialize_loan_account_row(row) for row in borrowing_loan_account_rows
        ],
        "borrowing_history_raw": [
            _serialize_borrowing_history_row(row) for row in borrowing_history_rows
        ],
        "borrowing_eligibility_profile": borrowing_eligibility_profile_snapshot,
        "borrowing_liquidity_state": borrowing_liquidity_state_snapshot,
        "borrowing_options": borrowing_options_snapshot,
        "borrowing_risk_summary": borrowing_risk_summary_snapshot,
        "borrowing_pressure_summary": borrowing_pressure_summary_snapshot,
        "borrowing_loan_accounts": borrowing_loan_accounts_snapshot,
        "borrowing_history": borrowing_history_snapshot,
        "borrowing_system_summary": borrowing_system_summary_snapshot,
        "latest_life_summary": life_snapshot,
        "latest_settlement_summary": settlement_snapshot,
        "location_chain": location_chain,
        "latest_daily_brief": _serialize_brief(latest_brief),
        "latest_portfolio_summary": portfolio,
        "career_snapshot": _career_snapshot_safe(db, player.id),
        "event_snapshot": _event_snapshot_safe(db, context_day),
        "balance_profile": get_balance_profile_metadata(),
        "player_balance_snapshot": player_balance_snapshot,
        "exploit_flags": exploit_flags_snapshot,
        "strategy_classification": strategy_classification_snapshot,
        "weekly_strategy_summary": weekly_strategy_summary,
        "onboarding_state": _serialize_onboarding_state(onboarding_state),
        "onboarding_state_snapshot": onboarding_state_snapshot,
        "onboarding_guidance": onboarding_guidance_snapshot,
        "onboarding_dashboard_config": onboarding_dashboard_config_snapshot,
        "onboarding_unlock_schedule": onboarding_unlock_schedule_snapshot,
        "onboarding_completion_debug": onboarding_completion_debug,
        "progression_state": _serialize_progression_state(progression_state),
        "progression_goal_history": [
            _serialize_progression_goal_history(row) for row in progression_history_rows
        ],
        "progression_summary": progression_summary_snapshot,
        "economy_presentation_summary": economy_presentation_summary,
        "strategic_planning_summary": strategic_planning_summary,
        "commitment_state": _serialize_commitment_state(commitment_state),
        "commitment_history": [
            _serialize_commitment_history(row) for row in commitment_history_rows
        ],
        "commitment_available": commitment_available,
        "commitment_summary": commitment_summary_snapshot,
        "commitment_feedback": commitment_feedback_snapshot,
        "commitment_drift_debug": commitment_drift_snapshot,
        "commitment_adherence_debug": commitment_adherence_snapshot,
        "commitment_history_snapshot": commitment_history_snapshot,
        "world_memory_state": _serialize_world_memory_state(world_memory_state),
        "world_pattern_history": [
            _serialize_world_pattern_history(row) for row in world_pattern_history_rows
        ],
        "world_memory_snapshot": world_memory_snapshot,
        "world_pattern_detection": world_pattern_detection,
        "world_narrative": world_narrative_snapshot,
        "world_local_pressure_summary": world_local_pressure_snapshot,
        "world_player_pattern_summary": world_player_pattern_snapshot,
        "world_region_memory_summary": world_region_memory_snapshot,
        "world_memory_history_snapshot": world_memory_history_snapshot,
        "world_memory_summary": world_memory_summary_snapshot,
        "population_region_state_raw": _serialize_region_population_state(region_population_state_row),
        "population_region_history_raw": [
            _serialize_region_population_history(row) for row in region_population_history_rows
        ],
        "population_region_state": population_region_state_snapshot,
        "population_opportunity_pressure": population_opportunity_snapshot,
        "population_competition_state": population_competition_snapshot,
        "population_region_heat": population_heat_snapshot,
        "population_response_summary": population_response_snapshot,
        "population_pressure_summary": population_summary_snapshot,
        "population_refresh_debug": population_refresh_snapshot,
    }


def get_economy_debug_snapshot(db: Session) -> dict:
    """Return a top-level debug view of current economy state."""
    latest_macro = (
        db.query(MacroDailyState)
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )

    latest_basket_day = db.query(func.max(BasketDailyPrice.day)).scalar()
    latest_stock_day = db.query(func.max(StockDailyPrice.day)).scalar()

    basket_rows = []
    if latest_basket_day is not None:
        basket_rows = (
            db.query(BasketDailyPrice)
            .filter(BasketDailyPrice.day == int(latest_basket_day))
            .order_by(BasketDailyPrice.basket_type.asc())
            .all()
        )

    stock_rows = []
    if latest_stock_day is not None:
        stock_rows = (
            db.query(StockDailyPrice)
            .filter(StockDailyPrice.day == int(latest_stock_day))
            .order_by(StockDailyPrice.ticker.asc())
            .all()
        )

    average_daily_change_pct = Decimal("0.0000")
    largest_gainer: dict | None = None
    largest_loser: dict | None = None
    if stock_rows:
        total_change = sum((_d(row.daily_change_pct) for row in stock_rows), Decimal("0"))
        average_daily_change_pct = _q4(total_change / Decimal(str(len(stock_rows))))

        sorted_rows = sorted(stock_rows, key=lambda row: _d(row.daily_change_pct))
        largest_loser = {
            "ticker": sorted_rows[0].ticker,
            "daily_change_pct": float(_q4(_d(sorted_rows[0].daily_change_pct))),
            "close_price": float(_q4(_d(sorted_rows[0].close_price))),
        }
        largest_gainer = {
            "ticker": sorted_rows[-1].ticker,
            "daily_change_pct": float(_q4(_d(sorted_rows[-1].daily_change_pct))),
            "close_price": float(_q4(_d(sorted_rows[-1].close_price))),
        }

    supply_chain_daily: dict | None = None
    supply_chain_graph_summary: dict | None = None
    basket_pricing_daily: dict | None = None
    job_market_daily: dict | None = None
    daily_economy_brief: dict | None = None
    top_bottlenecks: list[str] = []
    top_basket_movers: list[str] = []
    top_job_pressure_movers: list[str] = []

    target_day = int(latest_macro.day) if latest_macro is not None else None
    if target_day is not None and target_day > 0:
        try:
            supply_chain_daily = compute_supply_chain_daily_snapshot(db, macro_day=target_day)
        except (SupplyChainNotFoundError, SupplyChainError):
            supply_chain_daily = None

        try:
            graph_result = build_supply_chain_daily_summary(db, target_day)
            supply_chain_graph_summary = graph_result.to_dict()
        except Exception:
            supply_chain_graph_summary = None

        try:
            basket_pricing_daily = compute_daily_basket_price_updates(
                db,
                day=target_day,
                persist=False,
                commit=False,
            )
        except BasketPricingError:
            basket_pricing_daily = None

        try:
            job_market_daily = compute_daily_job_market_updates(db, day=target_day)
        except JobMarketError:
            job_market_daily = None

        try:
            daily_economy_brief = build_daily_economy_brief(
                db,
                day=target_day,
                supply_chain_snapshot=supply_chain_daily,
                basket_pricing_daily=basket_pricing_daily,
                job_market_daily=job_market_daily,
            )
        except Exception:
            daily_economy_brief = None

        if daily_economy_brief is not None:
            top_bottlenecks = list(daily_economy_brief.get("top_bottlenecks", []))
            top_basket_movers = list(daily_economy_brief.get("top_basket_movers", []))
            top_job_pressure_movers = list(daily_economy_brief.get("top_job_changes", []))
    try:
        economy_telemetry_snapshot = compute_daily_economy_health_metrics(db)
    except Exception:
        economy_telemetry_snapshot = {}
    try:
        system_dominance_flags = detect_system_dominance_flags(db)
    except Exception:
        system_dominance_flags = {}
    try:
        economy_weekly_summary = build_economy_weekly_summary(db=db)
    except Exception:
        economy_weekly_summary = {}
    economy_presentation_market_overview: dict = {}
    economy_presentation_price_trends: dict = {}
    economy_presentation_business_margins: dict = {}
    economy_presentation_commute_pressure: dict = {}
    economy_presentation_explainer: dict = {}
    economy_presentation_future_teasers: dict = {}
    economy_presentation_player_id: str | None = None
    strategic_planning_summary: dict = {}
    strategic_planning_recommendation: dict = {}
    strategic_planning_future_preparation: dict = {}
    strategic_planning_plans: dict = {}
    strategic_planning_housing_tradeoff: dict = {}
    strategic_planning_debt_vs_growth: dict = {}
    strategic_planning_business_plan: dict = {}
    strategic_planning_recovery_vs_push: dict = {}
    strategic_planning_player_id: str | None = None
    commitment_player_id: str | None = None
    world_memory_sample_player_id: str | None = None
    commitment_available_snapshot: dict = {}
    commitment_summary_snapshot: dict = {}
    commitment_feedback_snapshot: dict = {}
    commitment_drift_snapshot: dict = {}
    commitment_adherence_snapshot: dict = {}
    world_memory_snapshot_sample: dict = {}
    world_pattern_detection_sample: dict = {}
    world_narrative_sample: dict = {}
    world_local_pressure_sample: dict = {}
    world_player_pattern_sample: dict = {}
    world_region_memory_sample: dict = {}
    world_memory_history_sample: dict = {}
    world_memory_summary_sample: dict = {}
    personal_shock_sample_player_id: str | None = None
    personal_shock_profile_sample: dict = {}
    personal_shock_risk_sample: dict = {}
    personal_shock_recent_event_sample: dict = {}
    personal_shock_recovery_sample: dict = {}
    personal_shock_resilience_sample: dict = {}
    personal_shock_summary_sample: dict = {}
    personal_shock_system_sample: dict = {}
    financial_survival_sample_player_id: str | None = None
    financial_obligation_profile_sample: dict = {}
    financial_payment_risk_sample: dict = {}
    financial_delinquency_state_sample: dict = {}
    financial_credit_impact_sample: dict = {}
    financial_survival_summary_sample: dict = {}
    financial_payment_history_sample: dict = {}
    financial_survival_system_sample: dict = {}
    borrowing_sample_player_id: str | None = None
    borrowing_eligibility_sample: dict = {}
    borrowing_liquidity_sample: dict = {}
    borrowing_options_sample: dict = {}
    borrowing_risk_sample: dict = {}
    borrowing_pressure_sample: dict = {}
    borrowing_loan_accounts_sample: dict = {}
    borrowing_history_sample: dict = {}
    borrowing_system_sample: dict = {}
    onboarding_sample_player_id: str | None = None
    onboarding_state_sample: dict = {}
    onboarding_guidance_sample: dict = {}
    onboarding_dashboard_config_sample: dict = {}
    onboarding_unlock_schedule_sample: dict = {}
    onboarding_completion_debug_sample: dict = {}
    population_sample_player_id: str | None = None
    population_region_state_sample: dict = {}
    population_opportunity_sample: dict = {}
    population_competition_sample: dict = {}
    population_heat_sample: dict = {}
    population_response_sample: dict = {}
    population_summary_sample: dict = {}
    population_refresh_sample: dict = {}
    region_population_states: list[dict] = []
    region_population_history_rows: list[dict] = []
    try:
        region_population_states = [
            _serialize_region_population_state(row)
            for row in (
                db.query(RegionPopulationState)
                .order_by(RegionPopulationState.region_key.asc())
                .all()
            )
        ]
    except Exception:
        region_population_states = []
    try:
        region_population_history_rows = [
            _serialize_region_population_history(row)
            for row in (
                db.query(RegionPopulationHistory)
                .order_by(
                    RegionPopulationHistory.as_of_day.desc(),
                    RegionPopulationHistory.region_key.asc(),
                )
                .limit(50)
                .all()
            )
        ]
    except Exception:
        region_population_history_rows = []
    sample_player = db.query(Player).order_by(Player.created_at.asc()).first()
    if sample_player is not None:
        economy_presentation_player_id = str(sample_player.id)
        strategic_planning_player_id = str(sample_player.id)
        commitment_player_id = str(sample_player.id)
        world_memory_sample_player_id = str(sample_player.id)
        personal_shock_sample_player_id = str(sample_player.id)
        financial_survival_sample_player_id = str(sample_player.id)
        borrowing_sample_player_id = str(sample_player.id)
        onboarding_sample_player_id = str(sample_player.id)
        population_sample_player_id = str(sample_player.id)
        try:
            economy_presentation_market_overview = build_market_overview(db=db, player_id=sample_player.id)
        except Exception:
            economy_presentation_market_overview = {}
        try:
            economy_presentation_price_trends = build_price_trend_summary(db=db, player_id=sample_player.id)
        except Exception:
            economy_presentation_price_trends = {}
        try:
            economy_presentation_business_margins = build_business_margin_summary(db=db, player_id=sample_player.id)
        except Exception:
            economy_presentation_business_margins = {}
        try:
            economy_presentation_commute_pressure = build_commute_pressure_summary(db=db, player_id=sample_player.id)
        except Exception:
            economy_presentation_commute_pressure = {}
        try:
            economy_presentation_explainer = build_player_economy_explainer(db=db, player_id=sample_player.id)
        except Exception:
            economy_presentation_explainer = {}
        try:
            economy_presentation_future_teasers = build_future_opportunity_teasers(db=db, player_id=sample_player.id)
        except Exception:
            economy_presentation_future_teasers = {}
        try:
            strategic_planning_summary = build_strategic_planning_summary(db=db, player_id=sample_player.id)
        except Exception:
            strategic_planning_summary = {}
        try:
            strategic_planning_recommendation = build_player_strategy_recommendation(db=db, player_id=sample_player.id)
        except Exception:
            strategic_planning_recommendation = {}
        try:
            strategic_planning_future_preparation = build_locked_future_path_preparation(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            strategic_planning_future_preparation = {}
        try:
            strategic_planning_plans = build_short_horizon_plan_options(db=db, player_id=sample_player.id)
        except Exception:
            strategic_planning_plans = {}
        try:
            strategic_planning_housing_tradeoff = build_housing_tradeoff_analysis(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            strategic_planning_housing_tradeoff = {}
        try:
            strategic_planning_debt_vs_growth = build_debt_vs_growth_analysis(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            strategic_planning_debt_vs_growth = {}
        try:
            strategic_planning_business_plan = build_business_mode_plan_analysis(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            strategic_planning_business_plan = {}
        try:
            strategic_planning_recovery_vs_push = build_recovery_vs_push_analysis(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            strategic_planning_recovery_vs_push = {}
        try:
            commitment_available_snapshot = build_available_commitments(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            commitment_available_snapshot = {}
        try:
            commitment_summary_snapshot = build_commitment_summary(
                db=db,
                player_id=sample_player.id,
                evaluate=False,
            )
        except Exception:
            commitment_summary_snapshot = {}
        try:
            commitment_feedback_snapshot = build_commitment_feedback(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            commitment_feedback_snapshot = {}
        try:
            commitment_drift_snapshot = detect_commitment_drift(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            commitment_drift_snapshot = {}
        try:
            commitment_adherence_snapshot = evaluate_commitment_adherence(
                db=db,
                player_id=sample_player.id,
                action_key=None,
            )
        except Exception:
            commitment_adherence_snapshot = {}
        try:
            world_memory_snapshot_sample = get_world_memory_snapshot(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_memory_snapshot_sample = {}
        try:
            world_pattern_detection_sample = detect_world_patterns(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_pattern_detection_sample = {}
        try:
            world_narrative_sample = build_world_narrative(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_narrative_sample = {}
        try:
            world_local_pressure_sample = build_world_local_pressure_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_local_pressure_sample = {}
        try:
            world_player_pattern_sample = build_world_player_pattern_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_player_pattern_sample = {}
        try:
            world_region_memory_sample = build_world_region_memory_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_region_memory_sample = {}
        try:
            world_memory_history_sample = build_world_memory_history(
                db=db,
                player_id=sample_player.id,
                limit=20,
            )
        except Exception:
            world_memory_history_sample = {}
        try:
            world_memory_summary_sample = build_world_memory_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            world_memory_summary_sample = {}
        try:
            personal_shock_profile_sample = build_personal_shock_profile(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_profile_sample = {}
        try:
            personal_shock_risk_sample = build_shock_risk_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_risk_sample = {}
        try:
            personal_shock_recent_event_sample = get_recent_personal_life_event(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_recent_event_sample = {}
        try:
            personal_shock_recovery_sample = get_player_recovery_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_recovery_sample = {}
        try:
            personal_shock_resilience_sample = build_player_resilience_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_resilience_sample = {}
        try:
            personal_shock_summary_sample = build_personal_shock_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_summary_sample = {}
        try:
            personal_shock_system_sample = build_personal_shock_system_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            personal_shock_system_sample = {}
        try:
            financial_obligation_profile_sample = build_player_obligation_profile(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            financial_obligation_profile_sample = {}
        try:
            financial_payment_risk_sample = build_payment_risk_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            financial_payment_risk_sample = {}
        try:
            financial_delinquency_state_sample = build_delinquency_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            financial_delinquency_state_sample = {}
        try:
            financial_survival_summary_sample = build_financial_survival_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            financial_survival_summary_sample = {}
        try:
            financial_payment_history_sample = get_player_payment_history(
                db=db,
                player_id=sample_player.id,
                limit=20,
            )
        except Exception:
            financial_payment_history_sample = {}
        try:
            financial_survival_system_sample = build_financial_survival_system_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            financial_survival_system_sample = {}
        financial_credit_impact_sample = (
            financial_survival_system_sample.get("credit_impact", {})
            if isinstance(financial_survival_system_sample, dict)
            else {}
        )
        try:
            borrowing_eligibility_sample = build_borrowing_eligibility_profile(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            borrowing_eligibility_sample = {}
        try:
            borrowing_liquidity_sample = build_emergency_liquidity_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            borrowing_liquidity_sample = {}
        try:
            borrowing_options_sample = generate_borrowing_options(
                db=db,
                player_id=sample_player.id,
                include_locked=True,
            )
        except Exception:
            borrowing_options_sample = {}
        try:
            borrowing_risk_sample = build_borrowing_risk_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            borrowing_risk_sample = {}
        try:
            borrowing_pressure_sample = build_borrowing_pressure_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            borrowing_pressure_sample = {}
        try:
            borrowing_loan_accounts_sample = get_player_loan_accounts(
                db=db,
                player_id=sample_player.id,
                include_closed=False,
            )
        except Exception:
            borrowing_loan_accounts_sample = {}
        try:
            borrowing_history_sample = get_player_borrowing_history(
                db=db,
                player_id=sample_player.id,
                limit=30,
            )
        except Exception:
            borrowing_history_sample = {}
        try:
            borrowing_system_sample = build_consumer_borrowing_system_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            borrowing_system_sample = {}
        try:
            onboarding_state_sample = build_onboarding_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            onboarding_state_sample = {}
        try:
            onboarding_guidance_sample = build_onboarding_guidance(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            onboarding_guidance_sample = {}
        try:
            onboarding_dashboard_config_sample = build_first_session_dashboard_config(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            onboarding_dashboard_config_sample = {}
        try:
            onboarding_unlock_schedule_sample = build_unlock_schedule(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            onboarding_unlock_schedule_sample = {}
        try:
            onboarding_completion_debug_sample = evaluate_onboarding_completion(
                db=db,
                player_id=sample_player.id,
                action_key=None,
            )
        except Exception:
            onboarding_completion_debug_sample = {}
        try:
            population_region_state_sample = build_region_population_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_region_state_sample = {}
        try:
            population_opportunity_sample = build_local_opportunity_pressure(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_opportunity_sample = {}
        try:
            population_competition_sample = build_local_competition_state(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_competition_sample = {}
        try:
            population_heat_sample = build_region_heat_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_heat_sample = {}
        try:
            population_response_sample = build_population_response_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_response_sample = {}
        try:
            population_summary_sample = build_population_pressure_summary(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_summary_sample = {}
        try:
            population_refresh_sample = update_population_pressure(
                db=db,
                player_id=sample_player.id,
            )
        except Exception:
            population_refresh_sample = {}

    event_categories = sorted({str(event.category) for event in EVENT_CATALOG})
    chain_groups = sorted(
        {
            str(event.chain_group_key)
            for event in EVENT_CATALOG
            if bool(event.can_chain) and bool(event.chain_group_key)
        }
    )
    event_catalog_metadata = {
        "total_templates": int(len(EVENT_CATALOG)),
        "categories": event_categories,
        "chain_groups": chain_groups,
        "sentiment_counts": {
            "negative": int(sum(1 for event in EVENT_CATALOG if event.sentiment == "negative")),
            "positive": int(sum(1 for event in EVENT_CATALOG if event.sentiment == "positive")),
            "neutral": int(sum(1 for event in EVENT_CATALOG if event.sentiment == "neutral")),
        },
    }

    return {
        "latest_macro_state": _serialize_macro(latest_macro),
        "latest_basket_day": int(latest_basket_day) if latest_basket_day is not None else None,
        "latest_basket_daily_prices": [_serialize_basket_price(row) for row in basket_rows],
        "latest_stock_day": int(latest_stock_day) if latest_stock_day is not None else None,
        "latest_stock_daily_prices_summary": {
            "row_count": len(stock_rows),
            "average_daily_change_pct": float(average_daily_change_pct),
            "largest_gainer": largest_gainer,
            "largest_loser": largest_loser,
            "sample_rows": [_serialize_stock_price(row) for row in stock_rows[:10]],
        },
        "latest_supply_chain_daily": supply_chain_daily,
        "latest_supply_chain_graph": supply_chain_graph_summary,
        "latest_basket_pricing_daily": basket_pricing_daily,
        "latest_job_market_daily": job_market_daily,
        "latest_daily_economy_brief": daily_economy_brief,
        "top_bottlenecks": top_bottlenecks,
        "top_basket_movers": top_basket_movers,
        "top_job_pressure_movers": top_job_pressure_movers,
        "economy_telemetry_snapshot": economy_telemetry_snapshot,
        "system_dominance_flags": system_dominance_flags,
        "economy_weekly_summary": economy_weekly_summary,
        "economy_presentation_sample_player_id": economy_presentation_player_id,
        "economy_presentation_market_overview": economy_presentation_market_overview,
        "economy_presentation_price_trends": economy_presentation_price_trends,
        "economy_presentation_business_margins": economy_presentation_business_margins,
        "economy_presentation_commute_pressure": economy_presentation_commute_pressure,
        "economy_presentation_explainer": economy_presentation_explainer,
        "economy_presentation_future_teasers": economy_presentation_future_teasers,
        "strategic_planning_sample_player_id": strategic_planning_player_id,
        "strategic_planning_summary": strategic_planning_summary,
        "strategic_planning_plans": strategic_planning_plans,
        "strategic_planning_housing_tradeoff": strategic_planning_housing_tradeoff,
        "strategic_planning_debt_vs_growth": strategic_planning_debt_vs_growth,
        "strategic_planning_business_plan": strategic_planning_business_plan,
        "strategic_planning_recovery_vs_push": strategic_planning_recovery_vs_push,
        "strategic_planning_recommendation": strategic_planning_recommendation,
        "strategic_planning_future_preparation": strategic_planning_future_preparation,
        "commitment_sample_player_id": commitment_player_id,
        "commitment_available": commitment_available_snapshot,
        "commitment_summary": commitment_summary_snapshot,
        "commitment_feedback": commitment_feedback_snapshot,
        "commitment_drift_debug": commitment_drift_snapshot,
        "commitment_adherence_debug": commitment_adherence_snapshot,
        "world_memory_sample_player_id": world_memory_sample_player_id,
        "world_memory_snapshot": world_memory_snapshot_sample,
        "world_pattern_detection": world_pattern_detection_sample,
        "world_narrative": world_narrative_sample,
        "world_local_pressure_summary": world_local_pressure_sample,
        "world_player_pattern_summary": world_player_pattern_sample,
        "world_region_memory_summary": world_region_memory_sample,
        "world_memory_history_snapshot": world_memory_history_sample,
        "world_memory_summary": world_memory_summary_sample,
        "personal_shock_sample_player_id": personal_shock_sample_player_id,
        "personal_shock_profile": personal_shock_profile_sample,
        "personal_shock_risk_state": personal_shock_risk_sample,
        "personal_recent_life_event": personal_shock_recent_event_sample,
        "personal_recovery_state": personal_shock_recovery_sample,
        "personal_resilience_summary": personal_shock_resilience_sample,
        "personal_shock_summary": personal_shock_summary_sample,
        "personal_shock_system_summary": personal_shock_system_sample,
        "financial_survival_sample_player_id": financial_survival_sample_player_id,
        "financial_obligation_profile": financial_obligation_profile_sample,
        "financial_payment_risk_state": financial_payment_risk_sample,
        "financial_delinquency_state": financial_delinquency_state_sample,
        "financial_credit_impact": financial_credit_impact_sample,
        "financial_survival_summary": financial_survival_summary_sample,
        "financial_payment_history": financial_payment_history_sample,
        "financial_survival_system_summary": financial_survival_system_sample,
        "borrowing_sample_player_id": borrowing_sample_player_id,
        "borrowing_eligibility_profile": borrowing_eligibility_sample,
        "borrowing_liquidity_state": borrowing_liquidity_sample,
        "borrowing_options": borrowing_options_sample,
        "borrowing_risk_summary": borrowing_risk_sample,
        "borrowing_pressure_summary": borrowing_pressure_sample,
        "borrowing_loan_accounts": borrowing_loan_accounts_sample,
        "borrowing_history": borrowing_history_sample,
        "borrowing_system_summary": borrowing_system_sample,
        "onboarding_sample_player_id": onboarding_sample_player_id,
        "onboarding_state": onboarding_state_sample,
        "onboarding_guidance": onboarding_guidance_sample,
        "onboarding_dashboard_config": onboarding_dashboard_config_sample,
        "onboarding_unlock_schedule": onboarding_unlock_schedule_sample,
        "onboarding_completion_debug": onboarding_completion_debug_sample,
        "population_sample_player_id": population_sample_player_id,
        "population_region_state": population_region_state_sample,
        "population_opportunity_pressure": population_opportunity_sample,
        "population_competition_state": population_competition_sample,
        "population_region_heat": population_heat_sample,
        "population_response_summary": population_response_sample,
        "population_pressure_summary": population_summary_sample,
        "population_refresh_debug": population_refresh_sample,
        "region_population_states_raw": region_population_states,
        "region_population_history_raw": region_population_history_rows,
        "event_catalog_metadata": event_catalog_metadata,
        "balance_profile": get_balance_profile_metadata(),
        "event_snapshot": _event_snapshot_safe(db, target_day),
        "aggregate_counts": {
            "players": int(db.query(func.count(Player.id)).scalar() or 0),
            "active_businesses": int(
                db.query(func.count(PlayerBusiness.id))
                .filter(PlayerBusiness.is_active.is_(True))
                .scalar()
                or 0
            ),
            "total_settlements": int(db.query(func.count(DailySettlementLog.id)).scalar() or 0),
            "total_brief_logs": int(db.query(func.count(DailyBriefLog.id)).scalar() or 0),
        },
    }


def _ensure_macro_target_row(db: Session, day: int | None) -> tuple[MacroDailyState, bool]:
    if day is not None and int(day) <= 0:
        raise AdminDebugValidationError("day must be greater than 0.")

    if day is not None:
        target_day = int(day)
        existing = db.query(MacroDailyState).filter(MacroDailyState.day == target_day).first()
        if existing is not None:
            return existing, False

        seed = db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()
        if seed is None:
            row = MacroDailyState(
                day=target_day,
                inflation_rate=Decimal("2.0000"),
                interest_rate=Decimal("4.0000"),
                unemployment_rate=Decimal("5.0000"),
                oil_index=Decimal("100.0000"),
                consumer_confidence=Decimal("50.0000"),
                supply_chain_stress=Decimal("0.5000"),
                event_headline="Debug baseline macro state",
                event_summary="Created by internal debug scenario tooling.",
            )
        else:
            row = MacroDailyState(
                day=target_day,
                inflation_rate=_q4(_d(seed.inflation_rate)),
                interest_rate=_q4(_d(seed.interest_rate)),
                unemployment_rate=_q4(_d(seed.unemployment_rate)),
                oil_index=_q4(_d(seed.oil_index)),
                consumer_confidence=_q4(_d(seed.consumer_confidence)),
                supply_chain_stress=_q4(_d(seed.supply_chain_stress)),
                event_headline=seed.event_headline,
                event_summary=seed.event_summary,
            )
        db.add(row)
        db.flush()
        return row, True

    latest = db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()
    if latest is not None:
        return latest, False

    row = MacroDailyState(
        day=1,
        inflation_rate=Decimal("2.0000"),
        interest_rate=Decimal("4.0000"),
        unemployment_rate=Decimal("5.0000"),
        oil_index=Decimal("100.0000"),
        consumer_confidence=Decimal("50.0000"),
        supply_chain_stress=Decimal("0.5000"),
        event_headline="Debug baseline macro state",
        event_summary="Created by internal debug scenario tooling.",
    )
    db.add(row)
    db.flush()
    return row, True


def force_macro_scenario(db: Session, scenario_name: str, day: int | None = None) -> dict:
    """Force deterministic macro shifts for balancing and QA."""
    normalized = (scenario_name or "").strip().lower()
    if normalized not in SUPPORTED_MACRO_SCENARIOS:
        raise AdminDebugValidationError(
            f"Unsupported macro scenario. Use one of: {sorted(SUPPORTED_MACRO_SCENARIOS)}"
        )

    try:
        row, created_new_row = _ensure_macro_target_row(db, day)
        before = _serialize_macro(row)

        inflation = _d(row.inflation_rate)
        interest = _d(row.interest_rate)
        unemployment = _d(row.unemployment_rate)
        oil = _d(row.oil_index)
        confidence = _d(row.consumer_confidence)
        supply = _d(row.supply_chain_stress)

        if normalized == "oil_spike":
            oil = oil * Decimal("1.0600")
            inflation += Decimal("0.1800")
            confidence -= Decimal("1.2000")
            supply += Decimal("0.2500")
            row.event_headline = "Oil and freight costs jump after an energy shock"
            row.event_summary = "Fuel-sensitive sectors face higher transport costs and tighter margins."
        elif normalized == "confidence_drop":
            confidence -= Decimal("6.0000")
            unemployment += Decimal("0.4500")
            interest += Decimal("0.0500")
            row.event_headline = "Consumer confidence dips as households turn cautious"
            row.event_summary = "Discretionary demand softens while labor anxiety starts to rise."
        elif normalized == "inflation_relief":
            inflation -= Decimal("0.3500")
            supply -= Decimal("0.2200")
            confidence += Decimal("2.0000")
            oil *= Decimal("0.9920")
            row.event_headline = "Price pressure eases as supply lanes improve"
            row.event_summary = "Cooling inflation and smoother logistics improve short-term affordability."
        elif normalized == "unemployment_shock":
            unemployment += Decimal("1.2500")
            confidence -= Decimal("3.2000")
            inflation -= Decimal("0.1000")
            row.event_headline = "Labor markets weaken after a hiring pullback"
            row.event_summary = "Layoff risk rises and consumer demand tilts defensive."
        elif normalized == "supply_chain_disruption":
            supply += Decimal("0.8000")
            oil *= Decimal("1.0300")
            inflation += Decimal("0.2800")
            confidence -= Decimal("1.5000")
            row.event_headline = "Supply chain disruption drives broad cost pressure"
            row.event_summary = "Input and delivery friction increase pricing and availability strain."
        elif normalized == "consumer_recovery":
            confidence += Decimal("4.2000")
            unemployment -= Decimal("0.5000")
            supply -= Decimal("0.1600")
            row.event_headline = "Consumer demand recovers as labor conditions stabilize"
            row.event_summary = "Confidence improves and spending momentum begins to rebuild."

        row.inflation_rate = _q4(_clamp(inflation, Decimal("0.5000"), Decimal("15.0000")))
        row.interest_rate = _q4(_clamp(interest, Decimal("0.2500"), Decimal("20.0000")))
        row.unemployment_rate = _q4(_clamp(unemployment, Decimal("2.0000"), Decimal("30.0000")))
        row.oil_index = _q4(_clamp(oil, Decimal("60.0000"), Decimal("300.0000")))
        row.consumer_confidence = _q4(_clamp(confidence, Decimal("10.0000"), Decimal("95.0000")))
        row.supply_chain_stress = _q4(_clamp(supply, Decimal("0.0000"), Decimal("5.0000")))

        db.flush()
        db.commit()
        db.refresh(row)

        return {
            "scenario_name": normalized,
            "day": int(row.day),
            "created_new_macro_day": bool(created_new_row),
            "before_macro": before,
            "after_macro": _serialize_macro(row),
        }
    except AdminDebugError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise AdminDebugError("Unexpected macro scenario forcing error.") from exc


def force_player_debug_state(db: Session, player_id: str | UUID, scenario_name: str) -> dict:
    """Apply bounded, explainable debug mutations for one player."""
    normalized = (scenario_name or "").strip().lower()
    if normalized not in SUPPORTED_PLAYER_SCENARIOS:
        raise AdminDebugValidationError(
            f"Unsupported player scenario. Use one of: {sorted(SUPPORTED_PLAYER_SCENARIOS)}"
        )

    try:
        player = _resolve_player(db, player_id)
        before = _player_debug_summary(db, player)
        notes: list[str] = []

        if normalized == "low_cash":
            cash_before = _money(_d(player.cash_xgp))
            target = Decimal("20.00")
            player.cash_xgp = target if cash_before > target else cash_before
            notes.append("cash_xgp was reduced to a tight-liquidity level.")
        elif normalized == "high_debt":
            debt_before = _money(_d(player.debt_xgp))
            target_debt = _money(max(Decimal("2500.00"), debt_before * Decimal("2.00")))
            player.debt_xgp = _clamp(target_debt, Decimal("2500.00"), Decimal("20000.00"))
            player.credit_score = _clamp_int(int(player.credit_score or 650) - 24, 300, 850)
            notes.append("debt_xgp was raised and credit_score was lowered for pressure testing.")
        elif normalized == "high_stress":
            player.stress = _clamp_int(max(int(player.stress or 0), 88), 0, 100)
            player.health = _clamp_int(int(player.health or 100) - 4, 0, 100)
            notes.append("stress and health were shifted toward a distressed profile.")
        elif normalized == "near_layoff":
            employment = _ensure_employment_row_for_debug(db, player)
            employment.employed_flag = True
            employment.job_status = "employed"
            employment.layoff_risk_pct = Decimal("38.00")
            employment.productivity_modifier = Decimal("0.8600")
            employment.opportunity_score = Decimal("0.7600")
            employment.promotion_chance_pct = Decimal("0.00")
            employment.wage_adjustment_pct = Decimal("-0.40")
            employment.last_employment_event = "layoff_warning"
            employment.layoff_event_flag = False
            employment.employment_evaluated_flag = False
            notes.append("employment state was set to near-layoff risk conditions.")
        elif normalized == "business_bad_day":
            businesses = (
                db.query(PlayerBusiness)
                .filter(
                    PlayerBusiness.player_id == player.id,
                    PlayerBusiness.is_active.is_(True),
                )
                .order_by(PlayerBusiness.created_at.desc())
                .all()
            )
            if not businesses:
                fallback_business = PlayerBusiness(
                    player_id=player.id,
                    business_id="food_truck",
                    region=(player.region or "suburban"),
                    business_level=1,
                    reputation=45,
                    cash_reserve_xgp=Decimal("35.00"),
                    created_day=max(int(player.last_settled_day or 0), 1),
                    is_active=True,
                    times_operated_today=0,
                    lifetime_business_runs=0,
                )
                db.add(fallback_business)
                db.flush()
                businesses = [fallback_business]

            scenario_day = max(int(player.last_settled_day or 0), 1)
            for business in businesses:
                business.reputation = _clamp_int(int(business.reputation or 50) - 18, 0, 100)
                reserve = _money(_d(business.cash_reserve_xgp))
                business.cash_reserve_xgp = _money(max(Decimal("0.00"), reserve - Decimal("40.00")))

                existing_log = (
                    db.query(BusinessDailyLog)
                    .filter(
                        BusinessDailyLog.business_id == business.id,
                        BusinessDailyLog.day == scenario_day,
                    )
                    .first()
                )
                if existing_log is None:
                    bad_log = BusinessDailyLog(
                        business_id=business.id,
                        player_id=player.id,
                        day=scenario_day,
                        gross_revenue_xgp=Decimal("34.0000"),
                        input_cost_xgp=Decimal("28.0000"),
                        fuel_cost_xgp=Decimal("10.0000"),
                        spoilage_cost_xgp=Decimal("3.0000"),
                        overhead_cost_xgp=Decimal("17.0000"),
                        net_profit_xgp=Decimal("-24.0000"),
                        demand_score=Decimal("0.7200"),
                        utilization_pct=Decimal("0.4800"),
                        notes_json=json.dumps({"source": "debug_business_bad_day"}),
                    )
                    db.add(bad_log)

            notes.append("business demand/profit context was shifted to a bad-day outcome.")
        elif normalized == "clean_restart":
            _apply_starter_like_player_state(
                db=db,
                player=player,
                preserve_profile=True,
                wipe_dependent_logs=False,
            )
            notes.append("player state was restored to a safer starter-like baseline.")

        player.credit_score = _clamp_int(int(player.credit_score or 650), 300, 850)
        player.health = _clamp_int(int(player.health or 100), 0, 100)
        player.stress = _clamp_int(int(player.stress or 0), 0, 100)
        player.cash_xgp = _money(max(Decimal("0.00"), _d(player.cash_xgp)))
        player.bank_savings_xgp = _money(max(Decimal("0.00"), _d(player.bank_savings_xgp)))
        player.debt_xgp = _money(max(Decimal("0.00"), _d(player.debt_xgp)))
        player.net_worth_xgp = _money(
            _d(player.cash_xgp) + _d(player.bank_savings_xgp) - _d(player.debt_xgp)
        )

        db.flush()
        db.commit()
        db.refresh(player)

        return {
            "player_id": str(player.id),
            "scenario_name": normalized,
            "notes": notes,
            "before_player_summary": before,
            "after_player_summary": _player_debug_summary(db, player),
        }
    except AdminDebugError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise AdminDebugError("Unexpected player scenario forcing error.") from exc


def reset_player_to_starter_state(
    db: Session,
    player_id: str | UUID,
    preserve_profile: bool = True,
) -> dict:
    """Reset one player into a clean, playable starter-like state."""
    try:
        player = _resolve_player(db, player_id)

        _apply_starter_like_player_state(
            db=db,
            player=player,
            preserve_profile=bool(preserve_profile),
            wipe_dependent_logs=True,
        )

        db.flush()
        db.commit()
        db.refresh(player)

        return {
            "player_id": str(player.id),
            "reset_complete": True,
            "playable_summary": get_playable_player_summary(db, player.id),
        }
    except AdminDebugError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise AdminDebugError("Unexpected player reset error.") from exc

def build_wealth_debug_snapshot(db: Session, player_id: str | UUID, day: int | None = None) -> dict:
    """Return a consolidated wealth progression debug snapshot for a player.

    Exposes wealth score drivers, net worth component drivers, debt drag
    drivers, false-growth warning drivers, early-game softening drivers, and
    safe-invest threshold drivers in a single call for admin inspection.
    """
    player = _resolve_player(db, player_id)
    from app.engine.wealth_progression_service import GAME_EPOCH as _WP_EPOCH

    if day is None:
        from app.services.daily_settlement_service import get_next_player_day

        day = int(get_next_player_day(db, player.id))

    as_of_date = _WP_EPOCH + timedelta(days=day - 1)

    try:
        profile = build_wealth_profile(db=db, player_id=str(player.id), day=day)
    except WealthProgressionError:
        profile = {}

    try:
        nw_summary = build_net_worth_summary(
            db=db, player_id=str(player.id), day=day, as_of_date=as_of_date
        )
    except WealthProgressionError:
        nw_summary = {}

    try:
        momentum = build_wealth_momentum_summary(
            db=db, player_id=str(player.id), day=day, as_of_date=as_of_date
        )
    except WealthProgressionError:
        momentum = {}

    wealth_score_drivers = {
        "stability_before_growth_score": profile.get("stability_before_growth_score"),
        "wealth_momentum_score": profile.get("wealth_momentum_score"),
        "wealth_phase_label": profile.get("wealth_phase_label"),
        "experience_phase": profile.get("experience_phase"),
        "days_in_phase": profile.get("days_in_phase"),
        "softening_active": profile.get("softening_active"),
    }

    net_worth_component_drivers = {
        "net_worth_xgp": profile.get("net_worth_xgp"),
        "total_asset_value_xgp": profile.get("total_asset_value_xgp"),
        "total_debt_xgp": profile.get("total_debt_xgp"),
        "liquid_asset_value_xgp": profile.get("liquid_asset_value_xgp"),
        "market_asset_value_xgp": profile.get("market_asset_value_xgp"),
        "business_equity_xgp": profile.get("business_equity_xgp"),
        "cash_reserve_xgp": profile.get("cash_reserve_xgp"),
        "savings_reserve_xgp": profile.get("savings_reserve_xgp"),
        "net_worth_direction": nw_summary.get("net_worth_direction"),
        "net_worth_delta_xgp": nw_summary.get("net_worth_delta_xgp"),
        "growth_quality_label": nw_summary.get("growth_quality_label"),
    }

    debt_drag_drivers = {
        "debt_drag_xgp": profile.get("debt_drag_xgp"),
        "debt_drag_ratio": nw_summary.get("debt_drag_ratio"),
        "top_drag_driver": profile.get("top_drag_driver"),
        "investable_surplus_xgp": profile.get("investable_surplus_xgp"),
        "buffer_days": profile.get("buffer_days"),
    }

    false_growth_warning_drivers = {
        "false_growth_detected": profile.get("false_growth_detected"),
        "false_growth_warnings": profile.get("false_growth_warnings", []),
        "asset_growth_trend": profile.get("asset_growth_trend"),
    }

    softening_drivers = {
        "experience_phase": profile.get("experience_phase"),
        "softening_active": profile.get("softening_active"),
        "softening_modifiers": momentum.get("softening_modifiers", {}),
        "days_in_phase": profile.get("days_in_phase"),
    }

    safe_invest_threshold_drivers = {
        "safe_to_save_label": profile.get("safe_to_save_label"),
        "safe_to_invest_label": profile.get("safe_to_invest_label"),
        "buffer_days": profile.get("buffer_days"),
        "savings_capacity_summary": momentum.get("savings_capacity_summary"),
        "top_growth_driver": profile.get("top_growth_driver"),
    }

    return {
        "player_id": str(player.id),
        "day": day,
        "as_of_date": str(as_of_date),
        "wealth_score_drivers": wealth_score_drivers,
        "net_worth_component_drivers": net_worth_component_drivers,
        "debt_drag_drivers": debt_drag_drivers,
        "false_growth_warning_drivers": false_growth_warning_drivers,
        "experience_phase_softening_drivers": softening_drivers,
        "safe_invest_threshold_drivers": safe_invest_threshold_drivers,
        "planning_insights": profile.get("planning_insights", []),
        "phase_advisory": momentum.get("phase_advisory", []),
    }


def build_reputation_debug_snapshot(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Step 40: Admin debug view of the player's reputation and trust state."""
    from app.engine.reputation_trust_service import GAME_EPOCH as _RT_EPOCH
    from datetime import date as _date

    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError:
        return {"error": "invalid player_id"}

    from app.models.player import Player as _Player
    player = db.query(_Player).filter(_Player.id == pid).first()
    if player is None:
        return {"error": "player not found"}

    if day is None:
        try:
            from app.services.daily_settlement_service import get_next_player_day
            day = int(get_next_player_day(db, pid))
        except Exception:
            day = 1
    as_of_date = _RT_EPOCH + __import__("datetime").timedelta(days=int(day) - 1)

    try:
        profile = build_player_reputation_profile(db, player_id, day=day)
    except ReputationTrustError as exc:
        profile = {"error": str(exc)}

    try:
        trust_signals = build_trust_signal_state(db, player_id, day=day)
    except ReputationTrustError as exc:
        trust_signals = {"error": str(exc)}

    try:
        effects = apply_reputation_effects(db, player_id, day=day)
    except ReputationTrustError as exc:
        effects = {"error": str(exc)}

    reputation_score_drivers = {
        "reputation_score": profile.get("reputation_score"),
        "trust_score": profile.get("trust_score"),
        "financial_reliability_score": profile.get("financial_reliability_score"),
        "work_reliability_score": profile.get("work_reliability_score"),
        "business_reliability_score": profile.get("business_reliability_score"),
        "opportunity_readiness_score": profile.get("opportunity_readiness_score"),
    }

    signal_summary = {
        "payment_signal_label": profile.get("payment_signal_label"),
        "borrowing_signal_label": profile.get("borrowing_signal_label"),
        "work_signal_label": profile.get("work_signal_label"),
        "business_signal_label": profile.get("business_signal_label"),
        "stability_signal_label": profile.get("stability_signal_label"),
        "overall_trust_label": profile.get("overall_trust_label"),
    }

    opportunity_drivers = {
        "opportunity_access_label": profile.get("opportunity_access_label"),
        "reputation_direction": profile.get("reputation_direction"),
        "top_reputation_driver": profile.get("top_reputation_driver"),
        "top_reputation_drag": profile.get("top_reputation_drag"),
    }

    effects_summary = effects.get("effects", {}) if isinstance(effects, dict) else {}

    return {
        "player_id": str(pid),
        "day": day,
        "as_of_date": str(as_of_date),
        "reputation_score_drivers": reputation_score_drivers,
        "signal_summary": signal_summary,
        "opportunity_drivers": opportunity_drivers,
        "effects_summary": effects_summary,
        "practical_actions": profile.get("practical_actions", []),
        "planning_insights": profile.get("planning_insights", []),
    }


def build_contract_debug_snapshot(
    db: Session,
    player_id: str | UUID,
    day: int | None = None,
) -> dict:
    """Step 41: Admin debug view of the player's contract timing and obligation state."""
    from app.engine.contract_timing_service import GAME_EPOCH as _CT_EPOCH
    import datetime as _dt

    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError:
        return {"error": "invalid player_id"}

    from app.models.player import Player as _Player
    player = db.query(_Player).filter(_Player.id == pid).first()
    if player is None:
        return {"error": "player not found"}

    if day is None:
        try:
            from app.services.daily_settlement_service import get_next_player_day
            day = int(get_next_player_day(db, pid))
        except Exception:
            day = 1
    as_of_date = _CT_EPOCH + _dt.timedelta(days=int(day) - 1)

    try:
        schedule = build_player_contract_schedule(db, player_id, day=day)
        db.flush()
    except ContractTimingError as exc:
        schedule = {"error": str(exc)}

    try:
        upcoming = build_upcoming_obligation_window(db, player_id, day=day)
    except ContractTimingError as exc:
        upcoming = {"error": str(exc)}

    try:
        pressure = build_cash_timing_pressure_state(db, player_id, day=day)
    except ContractTimingError as exc:
        pressure = {"error": str(exc)}

    return {
        "player_id": str(pid),
        "day": day,
        "as_of_date": str(as_of_date),
        "timing_pressure_label": pressure.get("timing_pressure_label") if isinstance(pressure, dict) else None,
        "clustering_label": pressure.get("clustering_label") if isinstance(pressure, dict) else None,
        "bridge_need_label": pressure.get("bridge_need_label") if isinstance(pressure, dict) else None,
        "obligation_collision_label": pressure.get("obligation_collision_label") if isinstance(pressure, dict) else None,
        "contract_density_score": pressure.get("contract_density_score") if isinstance(pressure, dict) else None,
        "timing_stability_score": pressure.get("timing_stability_score") if isinstance(pressure, dict) else None,
        "cash_gap_before_next_income_xgp": pressure.get("cash_gap_before_next_income_xgp") if isinstance(pressure, dict) else None,
        "false_payday_pressure": pressure.get("false_payday_pressure") if isinstance(pressure, dict) else None,
        "active_contract_count": schedule.get("active_contract_count") if isinstance(schedule, dict) else None,
        "total_due_7d_xgp": schedule.get("total_due_7d_xgp") if isinstance(schedule, dict) else None,
        "outflows_due_today_xgp": upcoming.get("outflows_due_today_xgp") if isinstance(upcoming, dict) else None,
        "outflows_due_3d_xgp": upcoming.get("outflows_due_3d_xgp") if isinstance(upcoming, dict) else None,
        "outflows_due_7d_xgp": upcoming.get("outflows_due_7d_xgp") if isinstance(upcoming, dict) else None,
        "inflows_expected_7d_xgp": upcoming.get("inflows_expected_7d_xgp") if isinstance(upcoming, dict) else None,
        "net_7d_xgp": upcoming.get("net_7d_xgp") if isinstance(upcoming, dict) else None,
    }