"""Day progression orchestrator service."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.career_service import apply_daily_career_progression, CareerError
from app.engine.event_service import run_daily_event_engine
from app.engine.population_pressure_service import (
    build_population_pressure_summary,
    update_population_pressure,
)
from app.models.stock_daily_price import StockDailyPrice
from app.services.basket_pricing_service import BasketPricingError, compute_daily_basket_price_updates
from app.services.daily_brief_service import DailyBriefError, build_daily_economy_brief
from app.services.daily_settlement_service import (
    DailySettlementError,
    SettlementValidationError,
    get_next_player_day,
    settle_player_day,
)
from app.services.daily_brief_service import generate_player_daily_brief
from app.services.job_market_service import compute_daily_job_market_updates
from app.services.market_daily_update_service import (
    MarketUpdateError,
    ensure_stock_market_day,
)
from app.services.game_time_service import get_game_time_payload
from app.services.run_end_service import RUN_STATUS_ACTIVE, get_player_run_status

logger = logging.getLogger(__name__)


def _fallback_basket_pricing_summary(*, day: int, reason: str) -> dict:
    return {
        "as_of_date": None,
        "macro_state_id": None,
        "day": int(day),
        "already_processed": False,
        "basket_updates": [],
        "degraded": True,
        "fallback_mode": "neutral_placeholder",
        "debug_meta": {
            "constants_version": "basket_pricing_v1",
            "fallback_reason": reason,
            "fallback_applied": True,
        },
    }


def _fallback_daily_economy_brief(*, day: int, reason: str) -> dict:
    return {
        "day": int(day),
        "headline": "Economy data is temporarily unavailable",
        "summary_lines": [
            "Work and core actions are still available.",
            "Basket pricing used safe fallback values for this day.",
        ],
        "top_bottlenecks": [],
        "top_basket_movers": [],
        "top_job_changes": [],
        "debug_meta": {
            "fallback_reason": reason,
            "fallback_applied": True,
            "degraded_sections": ["basket_pricing"],
        },
    }


def _latest_stock_day(db: Session) -> int | None:
    day = db.query(func.max(StockDailyPrice.day)).scalar()
    return int(day) if day is not None else None


def run_player_next_day(db: Session, player_id: str | UUID) -> dict:
    """Advance market day if needed, then settle one player day."""
    # Core logic freeze: keep this orchestration order stable unless a verified bug requires change.
    # Frontend summaries, settlement integrity, and progression tests assume this exact pipeline.
    run_status_payload = get_player_run_status(db, player_id)
    if run_status_payload.get("run_status") != RUN_STATUS_ACTIVE:
        raise SettlementValidationError(
            f"Player run has ended with status '{run_status_payload.get('run_status')}'. Start a new run to continue settlement."
        )
    target_settlement_day = get_next_player_day(db, player_id)
    market_day = _latest_stock_day(db)
    try:
        market_bootstrap = ensure_stock_market_day(
            db,
            target_settlement_day,
            caller="run_player_next_day",
        )
        market_day = int(market_bootstrap["latest_market_day"])
    except MarketUpdateError as exc:
        logger.exception(
            "day_progression.market_bootstrap_failed",
            extra={
                "player_id": str(player_id),
                "day_number": int(target_settlement_day),
                "latest_market_day": market_day,
                "failing_function": "ensure_stock_market_day",
            },
        )
        raise DailySettlementError(
            f"Market data temporarily unavailable for day {target_settlement_day}. {exc}"
        ) from exc

    # Step 19: Run event engine BEFORE basket/supply chain so macro values
    # are adjusted before downstream systems consume them.
    event_result: dict = {}
    try:
        event_result = run_daily_event_engine(db, target_settlement_day)
    except Exception:
        pass  # event engine errors must not abort day progression

    basket_pricing_error: str | None = None
    try:
        basket_pricing = compute_daily_basket_price_updates(
            db,
            day=target_settlement_day,
            persist=True,
            commit=True,
        )
    except BasketPricingError as exc:
        basket_pricing_error = str(exc)
        logger.exception(
            "day_progression.basket_pricing_degraded",
            extra={
                "player_id": str(player_id),
                "day_number": int(target_settlement_day),
                "failing_function": "compute_daily_basket_price_updates",
                "economy_state_used": {
                    "market_day": int(market_day or 0),
                    "event_result_keys": sorted(event_result.keys()),
                },
                "fallback_applied": True,
            },
        )
        basket_pricing = _fallback_basket_pricing_summary(
            day=target_settlement_day,
            reason=basket_pricing_error,
        )
    job_market = compute_daily_job_market_updates(
        db,
        day=target_settlement_day,
    )
    if basket_pricing_error:
        economy_brief = _fallback_daily_economy_brief(
            day=target_settlement_day,
            reason=basket_pricing_error,
        )
    else:
        try:
            economy_brief = build_daily_economy_brief(
                db,
                day=target_settlement_day,
                basket_pricing_daily=basket_pricing,
                job_market_daily=job_market,
            )
        except Exception as exc:
            logger.exception(
                "day_progression.daily_brief_degraded",
                extra={
                    "player_id": str(player_id),
                    "day_number": int(target_settlement_day),
                    "failing_function": "build_daily_economy_brief",
                    "basket_pricing_fallback_applied": bool(basket_pricing_error),
                    "fallback_applied": True,
                },
            )
            economy_brief = _fallback_daily_economy_brief(
                day=target_settlement_day,
                reason=str(exc),
            )
    population_refresh: dict = {}
    try:
        from datetime import date, timedelta

        _GAME_EPOCH = date(2026, 1, 1)
        target_date = _GAME_EPOCH + timedelta(days=int(target_settlement_day) - 1)
        population_refresh = update_population_pressure(
            db=db,
            player_id=player_id,
            as_of_date=target_date,
        )
    except Exception:
        pass

    settlement = settle_player_day(db, player_id)
    # Step 18: Career progression runs after work/life outputs are settled.
    career_result: dict = {}
    settled_date = None
    try:
        from datetime import date, timedelta
        _GAME_EPOCH = date(2026, 1, 1)
        _settled_day = int(settlement["settled_day"])
        _settled_date = _GAME_EPOCH + timedelta(days=_settled_day - 1)
        settled_date = _settled_date
        career_result = apply_daily_career_progression(
            db=db,
            player_id=player_id,
            as_of_date=_settled_date,
            training_hours=None,
            commit=False,
        )
    except CareerError:
        pass  # career errors must not abort day progression
    except Exception:
        pass  # table-not-found and other transient errors must not abort day progression
    progression_summary: dict = {}
    commitment_summary: dict = {}
    world_memory_snapshot: dict = {}
    world_patterns: dict = {}
    world_narrative: dict = {}
    local_pressure_summary: dict = {}
    player_pattern_summary: dict = {}
    region_memory_summary: dict = {}
    population_summary: dict = {}
    onboarding_summary: dict = {}
    try:
        from datetime import date, timedelta
        from app.engine.progression_service import evaluate_end_of_day_progress

        if settled_date is None:
            _GAME_EPOCH = date(2026, 1, 1)
            _settled_day = int(settlement["settled_day"])
            settled_date = _GAME_EPOCH + timedelta(days=_settled_day - 1)
        progression_summary = evaluate_end_of_day_progress(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
    except Exception:
        pass  # progression evaluation errors must not abort day progression
    try:
        from datetime import date, timedelta
        from app.engine.commitment_service import (
            build_commitment_summary,
            evaluate_commitment_progress,
        )

        if settled_date is None:
            _GAME_EPOCH = date(2026, 1, 1)
            _settled_day = int(settlement["settled_day"])
            settled_date = _GAME_EPOCH + timedelta(days=_settled_day - 1)
        evaluate_commitment_progress(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
            action_key=None,
        )
        commitment_summary = build_commitment_summary(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
            evaluate=False,
        )
    except Exception:
        pass  # commitment evaluation errors must not abort day progression
    try:
        from datetime import date, timedelta
        from app.engine.world_memory_service import (
            build_local_pressure_summary,
            build_player_pattern_summary,
            build_region_memory_summary,
            build_world_narrative,
            detect_recurring_patterns,
            update_world_memory,
        )

        if settled_date is None:
            _GAME_EPOCH = date(2026, 1, 1)
            _settled_day = int(settlement["settled_day"])
            settled_date = _GAME_EPOCH + timedelta(days=_settled_day - 1)
        world_memory_snapshot = update_world_memory(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        world_patterns = detect_recurring_patterns(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        world_narrative = build_world_narrative(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        local_pressure_summary = build_local_pressure_summary(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        player_pattern_summary = build_player_pattern_summary(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        region_memory_summary = build_region_memory_summary(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
    except Exception:
        pass  # world memory errors must not abort day progression
    try:
        from datetime import date, timedelta

        if settled_date is None:
            _GAME_EPOCH = date(2026, 1, 1)
            _settled_day = int(settlement["settled_day"])
            settled_date = _GAME_EPOCH + timedelta(days=_settled_day - 1)
        population_summary = build_population_pressure_summary(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
    except Exception:
        pass  # population-pressure errors must not abort day progression
    try:
        from datetime import date, timedelta
        from app.engine.onboarding_service import (
            build_first_session_dashboard_config,
            build_onboarding_guidance,
            build_onboarding_state,
            build_unlock_schedule,
            evaluate_onboarding_completion,
        )

        if settled_date is None:
            _GAME_EPOCH = date(2026, 1, 1)
            _settled_day = int(settlement["settled_day"])
            settled_date = _GAME_EPOCH + timedelta(days=_settled_day - 1)

        state = evaluate_onboarding_completion(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
            action_key="end_day",
        )
        guidance = build_onboarding_guidance(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        dashboard_config = build_first_session_dashboard_config(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        unlock_schedule = build_unlock_schedule(
            db=db,
            player_id=player_id,
            as_of_date=settled_date,
        )
        onboarding_summary = {
            "state": state,
            "guidance": guidance,
            "dashboard_config": dashboard_config,
            "unlock_schedule": unlock_schedule,
        }
    except Exception:
        pass  # onboarding errors must not abort day progression
    brief = generate_player_daily_brief(db, player_id, int(settlement["settled_day"]), commit=True)
    business_net = float(settlement.get("business_net_xgp", 0.0))
    business_layer = ((settlement.get("summary_json") or {}).get("business_summary") or {})
    headline = (
        f"Day {settlement['settled_day']} settled. "
        f"Income {settlement['income_xgp']:.2f} XGP, expenses {settlement['expenses_xgp']:.2f} XGP."
    )
    if abs(business_net) > 0:
        headline += f" Business net {business_net:+.2f} XGP."
    overtime_hours = float(settlement.get("overtime_hours", 0.0))
    if overtime_hours > 0:
        headline += f" Overtime {overtime_hours:.1f}h."
    game_time_payload = get_game_time_payload()
    next_morning_brief_at = str(game_time_payload["next_morning_brief_at"])

    return {
        "player_id": settlement["player_id"],
        "market_day": int(market_day),
        "settled_day": int(settlement["settled_day"]),
        "game_time": game_time_payload,
        "run_status": settlement.get("run_status") or get_player_run_status(db, player_id),
        "tomorrow_preview_time": next_morning_brief_at,
        "next_morning_brief_at": next_morning_brief_at,
        "black_swan_pending": bool(settlement.get("black_swan_pending", False)),
        "black_swan_event_id": settlement.get("black_swan_event_id"),
        "end_state": settlement.get("end_state"),
        "risk_warnings": settlement.get("risk_warnings", []),
        "income_xgp": float(settlement["income_xgp"]),
        "expenses_xgp": float(settlement["expenses_xgp"]),
        "total_income": float(settlement.get("total_income", settlement["income_xgp"])),
        "total_expense": float(settlement.get("total_expense", settlement["expenses_xgp"])),
        "net_change": float(settlement.get("net_change", 0.0)),
        "ending_cash": float(settlement.get("ending_cash", settlement.get("ending_cash_xgp", 0.0))),
        "income_breakdown": settlement.get("income_breakdown", {}),
        "expense_breakdown": settlement.get("expense_breakdown", {}),
        "settlement_breakdown": settlement.get("settlement_breakdown", {}),
        "settlement_debug": settlement.get("settlement_debug", {}),
        "business_net_xgp": business_net,
        "stock_sale_income_xgp": float(settlement.get("stock_sale_income_xgp", 0.0)),
        "stock_fee_xgp": float(settlement.get("stock_fee_xgp", 0.0)),
        "business_revenue_xgp": float(settlement.get("business_revenue_xgp", 0.0)),
        "business_cogs_xgp": float(settlement.get("business_cogs_xgp", 0.0)),
        "business_overhead_xgp": float(settlement.get("business_overhead_xgp", 0.0)),
        "business_spoilage_loss_xgp": float(settlement.get("business_spoilage_loss_xgp", 0.0)),
        "business_fuel_cost_xgp": float(settlement.get("business_fuel_cost_xgp", 0.0)),
        "business_maintenance_cost_xgp": float(settlement.get("business_maintenance_cost_xgp", 0.0)),
        "weekly_gas_expense_xgp": float(settlement.get("weekly_gas_expense_xgp", 0.0)),
        "business_net_profit_xgp": float(settlement.get("business_net_profit_xgp", business_net)),
        "total_business_profit_xgp": float(settlement.get("total_business_profit_xgp", business_net)),
        "business_count_run": int(settlement.get("business_count_run", 0)),
        "business_summary": business_layer,
        "fruit_shop_result": business_layer.get("fruit_shop_result"),
        "food_truck_result": business_layer.get("food_truck_result"),
        "side_income_result": business_layer.get("side_income_result"),
        "maintenance_cost_xgp": float(business_layer.get("maintenance_cost_xgp", 0.0)),
        "spoilage_loss_xgp": float(business_layer.get("spoilage_loss_xgp", 0.0)),
        "life_summary": settlement.get("life_summary"),
        "time_budget_summary": settlement.get("time_budget_summary"),
        "stress": int(settlement.get("stress_after", settlement.get("stress_change", 0))),
        "health": int(settlement.get("health_after", 100)),
        "productivity_modifier": float(settlement.get("productivity_modifier", 1.0)),
        "burnout_risk": float(settlement.get("burnout_risk", 0.0)),
        "medical_event_risk": float(settlement.get("medical_event_risk", 0.0)),
        "medical_cost_xgp": float(settlement.get("medical_cost_xgp", 0.0)),
        "missed_work_penalty_xgp": float(settlement.get("missed_work_penalty_xgp", 0.0)),
        "personal_shock_summary": settlement.get("personal_shock_summary"),
        "personal_shock_impacts": settlement.get("personal_shock_impacts", {}),
        "personal_shock_cash_impact_xgp": float(settlement.get("personal_shock_cash_impact_xgp", 0.0)),
        "personal_shock_operational_delta_xgp": float(
            settlement.get("personal_shock_operational_delta_xgp", 0.0)
        ),
        "personal_shock_income_bonus_xgp": float(settlement.get("personal_shock_income_bonus_xgp", 0.0)),
        "personal_shock_extra_expense_xgp": float(settlement.get("personal_shock_extra_expense_xgp", 0.0)),
        "personal_shock_work_income_modifier": float(
            settlement.get("personal_shock_work_income_modifier", 1.0)
        ),
        "personal_shock_business_modifier": float(settlement.get("personal_shock_business_modifier", 1.0)),
        "personal_shock_side_income_modifier": float(
            settlement.get("personal_shock_side_income_modifier", 1.0)
        ),
        "personal_shock_stress_delta": float(settlement.get("personal_shock_stress_delta", 0.0)),
        "personal_shock_health_delta": float(settlement.get("personal_shock_health_delta", 0.0)),
        "personal_shock_time_hours": float(settlement.get("personal_shock_time_hours", 0.0)),
        "personal_shock_recent_event": settlement.get("personal_shock_recent_event", {}),
        "personal_shock_recovery_state": settlement.get("personal_shock_recovery_state", {}),
        "personal_shock_profile": settlement.get("personal_shock_profile", {}),
        "personal_shock_risk_state": settlement.get("personal_shock_risk_state", {}),
        "personal_shock_practical_actions": settlement.get("personal_shock_practical_actions", []),
        "personal_shock_debug_meta": settlement.get("personal_shock_debug_meta", {}),
        "total_hours_used": float(settlement.get("total_hours_used", 0.0)),
        "overtime_hours": overtime_hours,
        "sleep_hours": float(settlement.get("sleep_hours", 0.0)),
        "recovery_hours": float(settlement.get("recovery_hours", 0.0)),
        "opening_debt_xgp": float(settlement.get("opening_debt_xgp", 0.0)),
        "debt_payment_due_xgp": float(settlement.get("debt_payment_due_xgp", settlement.get("payment_due_xgp", 0.0))),
        "debt_payment_paid_xgp": float(settlement.get("debt_payment_paid_xgp", settlement.get("payment_made_xgp", 0.0))),
        "debt_payment_missed": bool(settlement.get("debt_payment_missed", False)),
        "late_fee_xgp": float(settlement.get("late_fee_xgp", 0.0)),
        "accrued_interest_xgp": float(settlement.get("accrued_interest_xgp", 0.0)),
        "payment_due_xgp": float(settlement.get("payment_due_xgp", 0.0)),
        "payment_made_xgp": float(settlement.get("payment_made_xgp", settlement.get("debt_paid_xgp", 0.0))),
        "interest_added_xgp": float(settlement.get("interest_added_xgp", 0.0)),
        "ending_debt_xgp": float(settlement.get("ending_debt_xgp", 0.0)),
        "payment_status": settlement.get("payment_status"),
        "credit_score_change": int(settlement.get("credit_score_change", 0)),
        "ending_credit_score": int(settlement.get("ending_credit_score", 650)),
        "delinquency_flag": bool(settlement.get("delinquency_flag", False)),
        "distress_state": settlement.get("distress_state_after", "stable"),
        "distress_score": float(settlement.get("distress_score_after", 0.0)),
        "distress_state_before": settlement.get("distress_state_before", "stable"),
        "distress_score_before": float(settlement.get("distress_score_before", 0.0)),
        "borrowing_cost_modifier": float(settlement.get("borrowing_cost_modifier", 1.0)),
        "opportunity_access_penalty": float(settlement.get("opportunity_access_penalty", 0.0)),
        "business_risk_penalty": float(settlement.get("business_risk_penalty", 0.0)),
        "career_progress_penalty": float(settlement.get("career_progress_penalty", 0.0)),
        "recovery_actions_applied": settlement.get("recovery_actions_applied", []),
        "financial_distress_summary": settlement.get("financial_distress_summary", {}),
        "financial_survival_summary": settlement.get("financial_survival_summary", {}),
        "required_monthly_obligation_xgp": float(settlement.get("required_monthly_obligation_xgp", 0.0)),
        "required_daily_burden_xgp": float(settlement.get("required_daily_burden_xgp", 0.0)),
        "obligation_load_ratio": float(settlement.get("obligation_load_ratio", 0.0)),
        "liquidity_buffer_days": float(settlement.get("liquidity_buffer_days", 0.0)),
        "payment_pressure_label": settlement.get("payment_pressure_label", "manageable"),
        "current_delinquency_stage": settlement.get("current_delinquency_stage", "current"),
        "survival_status_label": settlement.get("survival_status_label", "current"),
        "financial_survival_payment_outcome": settlement.get("financial_survival_payment_outcome", "paid_full"),
        "financial_survival_late_fee_xgp": float(settlement.get("financial_survival_late_fee_xgp", 0.0)),
        "financial_survival_late_fee_non_debt_xgp": float(
            settlement.get("financial_survival_late_fee_non_debt_xgp", 0.0)
        ),
        "financial_survival_additional_required_paid_xgp": float(
            settlement.get("financial_survival_additional_required_paid_xgp", 0.0)
        ),
        "financial_survival_credit_score_before": int(
            settlement.get("financial_survival_credit_score_before", settlement.get("opening_credit_score", 650))
        ),
        "financial_survival_credit_score_after": int(
            settlement.get("financial_survival_credit_score_after", settlement.get("ending_credit_score", 650))
        ),
        "financial_survival_credit_score_delta": int(
            settlement.get("financial_survival_credit_score_delta", settlement.get("credit_score_change", 0))
        ),
        "financial_survival_stress_impact_delta": float(
            settlement.get("financial_survival_stress_impact_delta", 0.0)
        ),
        "financial_survival_practical_actions": settlement.get("financial_survival_practical_actions", []),
        "borrowing_eligibility_profile": settlement.get("borrowing_eligibility_profile", {}),
        "borrowing_liquidity_state": settlement.get("borrowing_liquidity_state", {}),
        "borrowing_options": settlement.get("borrowing_options", {"items": []}),
        "borrowing_risk_summary": settlement.get("borrowing_risk_summary", {}),
        "borrowing_pressure_summary": settlement.get("borrowing_pressure_summary", {}),
        "borrowing_refresh": settlement.get("borrowing_refresh", {}),
        "ending_cash_xgp": float(settlement["ending_cash_xgp"]),
        "health_change": int(settlement["health_change"]),
        "stress_change": int(settlement["stress_change"]),
        "housing_region": settlement.get("housing_region"),
        "housing_cost_xgp": float(settlement.get("housing_cost_xgp", 0.0)),
        "housing_cost_daily_xgp": float(settlement.get("housing_cost_daily_xgp", settlement.get("housing_cost_xgp", 0.0))),
        "utilities_cost_daily_xgp": float(settlement.get("utilities_cost_daily_xgp", 0.0)),
        "commute_hours": float(settlement.get("commute_hours", 0.0)),
        "commute_fuel_cost_xgp": float(settlement.get("commute_fuel_cost_xgp", 0.0)),
        "commute_pressure": float(settlement.get("commute_pressure", 0.0)),
        "housing_stress_delta": int(settlement.get("housing_stress_delta", 0)),
        "region_key": settlement.get("region_key", settlement.get("housing_region")),
        "region_stress_delta": float(settlement.get("region_stress_delta", settlement.get("housing_stress_delta", 0.0))),
        "region_opportunity_modifier": float(settlement.get("region_opportunity_modifier", 0.0)),
        "region_business_demand_modifier": float(settlement.get("region_business_demand_modifier", 0.0)),
        "region_side_income_modifier": float(settlement.get("region_side_income_modifier", 0.0)),
        "networking_modifier": float(settlement.get("networking_modifier", 0.0)),
        "opportunity_quality_signal": float(settlement.get("opportunity_quality_signal", 1.0)),
        "opportunity_modifier": float(settlement.get("opportunity_modifier", 1.0)),
        "housing_region_summary": settlement.get("housing_region_summary", {}),
        "employment_status": settlement.get("employment_status"),
        "employment_event": settlement.get("employment_event"),
        "layoff_risk_pct": float(settlement.get("layoff_risk_pct", 0.0)),
        "promotion_chance_pct": float(settlement.get("promotion_chance_pct", 0.0)),
        "wage_adjustment_pct": float(settlement.get("wage_adjustment_pct", 0.0)),
        "monthly_pay_xgp_after_event": float(settlement.get("monthly_pay_xgp_after_event", 0.0)),
        "net_worth_xgp": float(settlement.get("net_worth_xgp", 0.0)),
        "total_assets_xgp": float(settlement.get("total_assets_xgp", 0.0)),
        "stock_market_value_xgp": float(settlement.get("stock_market_value_xgp", 0.0)),
        "business_value_xgp": float(settlement.get("business_value_xgp", 0.0)),
        "debt_xgp": float(settlement.get("debt_xgp", 0.0)),
        "allocation_json": settlement.get("allocation_json", {}),
        "summary_headline": headline,
        "headline": brief["headline"],
        "summary": brief["summary"],
        "macro_tags_json": brief["macro_tags_json"],
        "player_impact_json": brief["player_impact_json"],
        "action_hints_json": brief["action_hints_json"],
        "economy_headline": economy_brief.get("headline"),
        "economy_summary_lines": economy_brief.get("summary_lines", []),
        "top_bottlenecks": economy_brief.get("top_bottlenecks", []),
        "top_basket_movers": economy_brief.get("top_basket_movers", []),
        "top_job_changes": economy_brief.get("top_job_changes", []),
        "basket_pricing_summary": basket_pricing,
        "job_market_summary": job_market,
        "daily_economy_brief": economy_brief,
        "summary_json": settlement.get("summary_json", {}),
        "progression_summary": progression_summary,
        "commitment_summary": commitment_summary,
        "world_memory_snapshot": world_memory_snapshot,
        "world_patterns": world_patterns,
        "world_narrative": world_narrative,
        "local_pressure_summary": local_pressure_summary,
        "player_pattern_summary": player_pattern_summary,
        "region_memory_summary": region_memory_summary,
        "population_pressure_summary": population_summary,
        "population_region_state": (population_summary.get("region_state") or {}),
        "population_opportunity_pressure": (population_summary.get("opportunity_pressure") or {}),
        "population_competition_state": (population_summary.get("competition_state") or {}),
        "population_region_heat": (population_summary.get("region_heat") or {}),
        "population_response_summary": (population_summary.get("response_summary") or {}),
        "population_refresh": population_refresh,
        "onboarding_summary": onboarding_summary,
        # Step 18: career progression outputs
        "career_summary": {
            "current_job_key": career_result.get("current_job_key"),
            "current_job_rank": career_result.get("current_job_rank"),
            "current_job_skill": career_result.get("skill_after"),
            "skill_delta": career_result.get("skill_delta"),
            "trailing_performance_score": career_result.get("trailing_performance_score"),
            "promotion_eligible": career_result.get("promotion_eligible"),
            "promotion_progress": career_result.get("promotion_progress"),
            "promotion_unlocked_today": career_result.get("promotion_unlocked_today"),
            "certification_track_key": career_result.get("certification_track_key"),
            "certification_progress_days": career_result.get("certification_progress_days"),
            "certification_required_days": career_result.get("certification_required_days"),
            "certification_completed": career_result.get("certification_completed"),
        } if career_result else {},
        # Step 19: event engine outputs
        "event_summary": {
            "event_key": event_result.get("event_key"),
            "headline": event_result.get("headline"),
            "event_category": event_result.get("event_category"),
            "sentiment": event_result.get("sentiment"),
            "severity": event_result.get("severity"),
            "impact_tags": event_result.get("impact_tags"),
            "already_processed": event_result.get("already_processed", False),
        } if event_result else {},
    }
