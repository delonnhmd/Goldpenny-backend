"""Daily settlement service (core schema MVP).

This module settles one player's day into persistent state and immutable logs.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.basket_daily_price import BasketDailyPrice
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.gameplay_transaction import GameplayTransaction
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.stock_daily_price import StockDailyPrice
from app.engine.financial_distress_service import apply_daily_financial_distress
from app.engine.financial_survival_service import apply_daily_financial_survival
from app.engine.consumer_borrowing_service import (
    build_borrowing_eligibility_profile,
    build_borrowing_pressure_summary,
    build_borrowing_risk_summary,
    build_emergency_liquidity_state,
    generate_borrowing_options,
    refresh_loan_accounts,
)
from app.engine.life_balance_service import apply_life_consequences_for_player
from app.engine.personal_shock_service import apply_personal_life_event
from app.services.business_daily_operations_service import run_player_businesses_for_day
from app.services.consumption_behavior_service import compute_player_daily_consumption
from app.services.dinner_survival_service import ensure_day_dinner_resolved
from app.services.gameplay_transaction_service import record_gameplay_transaction
from app.services.debt_credit_service import apply_daily_debt_and_credit
from app.services.housing_region_service import compute_housing_effects_for_day
from app.services.job_market_service import apply_employment_progression
from app.services.net_worth_service import compute_player_net_worth_snapshot
from app.engine.retention_engine import build_retention_summary
from app.models.player_progression_state import PlayerProgressionState
from app.services.player_daily_state_service import ensure_player_daily_state
from app.services.player_transaction_log_service import record_player_transaction
from app.services.shift_state_service import get_houston_now, sync_shift_day_rules_if_needed

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
HOURS_RESET = 24
WEEKLY_GAS_EXPENSE_XGP = Decimal("30.00")
SURVIVAL_HEALTH_DELTA = -5
SURVIVAL_STRESS_DELTA = 4


logger = logging.getLogger("goldpenny.daily_settlement")


class DailySettlementError(Exception):
    """Base exception for settlement failures."""


class SettlementNotFoundError(DailySettlementError):
    """Raised when player or required records are missing."""


class SettlementValidationError(DailySettlementError):
    """Raised when settlement cannot proceed due to guard rules."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise SettlementNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise SettlementNotFoundError("Player not found.")
    return player


def _latest_player_daily_state(db: Session, player_id: UUID) -> PlayerDailyState | None:
    return (
        db.query(PlayerDailyState)
        .filter(PlayerDailyState.player_id == player_id)
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .first()
    )


def get_next_player_day(db: Session, player_id: str | UUID) -> int:
    player = _resolve_player(db, player_id)
    latest_state = _latest_player_daily_state(db, player.id)
    if latest_state is None:
        return 1
    if latest_state.did_settlement:
        return int(latest_state.day_number) + 1
    return int(latest_state.day_number)


def _get_or_create_player_daily_state(db: Session, player: Player, day_number: int) -> PlayerDailyState:
    return ensure_player_daily_state(
        db,
        player=player,
        day_number=day_number,
        defaults={
            "hours_available_start": int(player.hours_available or HOURS_RESET),
            "hours_available_end": int(player.hours_available or HOURS_RESET),
            "worked_main_job": False,
            "did_settlement": False,
            "stress_start": int(player.stress or 0),
            "stress_end": int(player.stress or 0),
            "health_start": int(player.health or 100),
            "health_end": int(player.health or 100),
            "cash_start": _money(_d(player.cash_xgp)),
            "cash_end": _money(_d(player.cash_xgp)),
        },
    )


def _latest_employment_state(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _latest_stock_day(db: Session) -> int | None:
    day = db.query(func.max(StockDailyPrice.day)).scalar()
    return int(day) if day is not None else None


def _latest_basket_price(
    db: Session,
    basket_type: BasketType,
    day_number: int,
) -> BasketDailyPrice | None:
    row = (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day <= day_number,
        )
        .order_by(BasketDailyPrice.day.desc())
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(BasketDailyPrice)
        .filter(BasketDailyPrice.basket_type == basket_type)
        .order_by(BasketDailyPrice.day.desc())
        .first()
    )


def _estimate_daily_basket_spend(
    db: Session,
    day_number: int,
    region: str | None,
    stress: int,
    side_income_hours: Decimal,
) -> Decimal:
    prices: dict[BasketType, Decimal] = {}
    for basket_type in BasketType:
        row = _latest_basket_price(db, basket_type, day_number)
        prices[basket_type] = _d(row.price_index) if row else Decimal("8.0")

    base_units = {
        BasketType.essentials: Decimal("1.10"),
        BasketType.protein: Decimal("0.80"),
        BasketType.produce: Decimal("0.70"),
        BasketType.convenience: Decimal("0.45"),
    }

    base_spend = sum(prices[k] * base_units[k] for k in base_units)
    region_multiplier = Decimal("1.12") if (region or "").lower() == "downtown" else Decimal("1.00")
    lifestyle_multiplier = Decimal("1.00") + (Decimal(max(stress - 50, 0)) / Decimal("500")) + (
        side_income_hours / Decimal("100")
    )
    return _money(base_spend * region_multiplier * lifestyle_multiplier)


def _calculate_stress_change(worked_hours: int, side_income_hours: Decimal, region: str | None) -> int:
    region_pressure = 1 if (region or "").lower() == "downtown" else 0
    base = Decimal(str(worked_hours)) * Decimal("0.40")
    side = side_income_hours * Decimal("0.60")
    return int(round(float(base + side))) + region_pressure


def _calculate_health_change(
    worked_hours: int,
    side_income_hours: Decimal,
    stress_before: int,
    stress_change: int,
) -> int:
    total_hours = Decimal(str(worked_hours)) + side_income_hours
    change = 0
    if total_hours >= Decimal("10"):
        change -= 2
    elif total_hours >= Decimal("6"):
        change -= 1

    projected_stress = stress_before + stress_change
    if projected_stress >= 90:
        change -= 1
    return change


def _safe_player_day_stock_totals(
    db: Session,
    player_id: UUID,
    day_number: int,
) -> tuple[Decimal, Decimal]:
    """Return stock sale gross + explicit stock fee totals for one player/day.

    Falls back to zeros when the transaction-log table is unavailable in older
    or minimal schemas.
    """
    try:
        rows = (
            db.query(PlayerTransactionLog)
            .filter(
                PlayerTransactionLog.player_id == player_id,
                PlayerTransactionLog.day == int(day_number),
                PlayerTransactionLog.category == "stock_market",
            )
            .all()
        )
    except Exception:
        return Decimal("0.00"), Decimal("0.00")

    stock_sale_income = Decimal("0.00")
    stock_fee = Decimal("0.00")
    for row in rows:
        txn_type = str(getattr(row, "transaction_type", "") or "").strip().lower()
        gross_amount = _money(_d(getattr(row, "gross_amount", 0)))
        if txn_type == "stock_sell":
            stock_sale_income += gross_amount
        elif txn_type == "fee":
            stock_fee += gross_amount
    return _money(stock_sale_income), _money(stock_fee)


def _count_gameplay_transactions_for_category(
    db: Session,
    *,
    player_id: UUID,
    day_number: int,
    category: str,
) -> int:
    return int(
        db.query(func.count(GameplayTransaction.id))
        .filter(
            GameplayTransaction.player_id == player_id,
            GameplayTransaction.day == int(day_number),
            GameplayTransaction.category == str(category or "").strip().lower(),
        )
        .scalar()
        or 0
    )


def _apply_survival_penalty_if_needed(
    db: Session,
    *,
    player: Player,
    pds: PlayerDailyState,
    settled_day: int,
) -> bool:
    meals_recorded = int(getattr(pds, "meals_recorded", 0) or 0)
    did_work = bool(getattr(pds, "did_work", False))
    missed_shift_today = bool(getattr(pds, "missed_shift", False))
    worked_hours = int(getattr(pds, "worked_hours", 0) or 0)
    main_shift_hours = _q4(_d(getattr(pds, "main_shift_hours_today", 0)))
    side_income_hours = _q4(_d(getattr(pds, "side_income_hours", 0)))
    business_hours = _q4(_d(getattr(pds, "business_hours", 0)))
    already_applied = bool(getattr(pds, "survival_penalty_applied", False))
    no_activity_today = bool(
        meals_recorded <= 0
        and not did_work
        and not missed_shift_today
        and worked_hours <= 0
        and main_shift_hours <= Decimal("0.00")
        and side_income_hours <= Decimal("0.00")
        and business_hours <= Decimal("0.00")
    )
    if already_applied or not no_activity_today:
        return False

    player.health = _clamp_int(int(player.health or 0) + SURVIVAL_HEALTH_DELTA, 0, 100)
    player.stress = _clamp_int(int(player.stress or 0) + SURVIVAL_STRESS_DELTA, 0, 100)
    pds.survival_penalty_applied = True
    pds.health_end = int(player.health or 0)
    pds.stress_end = int(player.stress or 0)
    record_gameplay_transaction(
        db,
        player=player,
        day=settled_day,
        transaction_type="expense",
        category="health_penalty",
        amount=0,
        description=f"No meals or activity - Health {SURVIVAL_HEALTH_DELTA}, Stress +{SURVIVAL_STRESS_DELTA}",
    )
    return True


def _build_settlement_breakdown(
    *,
    settled_day: int,
    day_start_cash: Decimal,
    ending_cash: Decimal,
    job_income: Decimal,
    side_income_net: Decimal,
    side_income_fuel_cost: Decimal,
    side_income_wear_cost: Decimal,
    side_income_maintenance_cost: Decimal,
    business_revenue: Decimal,
    business_cogs: Decimal,
    business_overhead: Decimal,
    business_spoilage_loss: Decimal,
    business_fuel_cost: Decimal,
    business_maintenance_cost: Decimal,
    stock_sale_income: Decimal,
    stock_fee: Decimal,
    basket_spend: Decimal,
    housing_cost_daily: Decimal,
    utilities_cost_daily: Decimal,
    debt_cash_deduction: Decimal,
    accrued_interest_xgp: Decimal,
    late_fee_xgp: Decimal,
    financial_survival_late_fee_non_debt_xgp: Decimal,
    medical_cost_xgp: Decimal,
    missed_work_penalty_xgp: Decimal,
    financial_survival_additional_required_paid_xgp: Decimal,
    commute_fuel_cost_xgp: Decimal,
    shock_income_bonus: Decimal,
    shock_extra_expense: Decimal,
) -> dict:
    """Build reconciled day-level income/expense categories for settlement."""
    weekly_gas_expense = _money(WEEKLY_GAS_EXPENSE_XGP if int(settled_day) % 7 == 0 else Decimal("0.00"))

    rideshare_income = _money(
        side_income_net
        + side_income_fuel_cost
        + side_income_wear_cost
        + side_income_maintenance_cost
    )

    income_breakdown = {
        "job_income": _money(job_income),
        "rideshare_income": rideshare_income,
        "business_income": _money(business_revenue),
        "stock_sale_income": _money(stock_sale_income),
        "other_income": _money(shock_income_bonus),
    }

    expense_breakdown = {
        "food_expense": _money(basket_spend),
        "gas_expense": _money(weekly_gas_expense),
        "rent_expense": _money(housing_cost_daily + utilities_cost_daily),
        "debt_payment": _money(debt_cash_deduction),
        "interest_payment": _money(accrued_interest_xgp + late_fee_xgp + financial_survival_late_fee_non_debt_xgp),
        "maintenance_cost": _money(side_income_maintenance_cost + business_maintenance_cost),
        "medical_cost": _money(medical_cost_xgp),
        "business_overhead": _money(business_overhead),
        "inventory_purchase_cost": _money(business_cogs),
        "spoilage_cost": _money(business_spoilage_loss),
        "stock_fee": _money(stock_fee),
        "other_expense": _money(
            side_income_fuel_cost
            + side_income_wear_cost
            + business_fuel_cost
            + commute_fuel_cost_xgp
            + missed_work_penalty_xgp
            + financial_survival_additional_required_paid_xgp
            + shock_extra_expense
        ),
    }

    total_income = _money(sum(income_breakdown.values(), Decimal("0.00")))
    total_expense = _money(sum(expense_breakdown.values(), Decimal("0.00")))
    net_change = _money(total_income - total_expense)
    reconciled_net_change = _money(ending_cash - day_start_cash)
    residual = _money(reconciled_net_change - net_change)

    if residual > Decimal("0.00"):
        income_breakdown["other_income"] = _money(income_breakdown["other_income"] + residual)
    elif residual < Decimal("0.00"):
        expense_breakdown["other_expense"] = _money(expense_breakdown["other_expense"] + abs(residual))

    total_income = _money(sum(income_breakdown.values(), Decimal("0.00")))
    total_expense = _money(sum(expense_breakdown.values(), Decimal("0.00")))
    net_change = _money(total_income - total_expense)

    biggest_expense_category = "none"
    biggest_expense_value = Decimal("0.00")
    for category, value in expense_breakdown.items():
        if value > biggest_expense_value:
            biggest_expense_value = value
            biggest_expense_category = category

    cadence_audit = {
        "weekly_gas_charge_applied": bool(weekly_gas_expense > Decimal("0.00")),
        "weekly_gas_amount_xgp": float(weekly_gas_expense),
        "weekly_gas_cadence_days": 7,
        "housing_charge_applied": bool(_money(housing_cost_daily + utilities_cost_daily) > Decimal("0.00")),
        "housing_cadence": "daily_configured",
        "debt_charge_applied": bool(debt_cash_deduction > Decimal("0.00")),
        "debt_cadence": "daily_obligation_configured",
        "business_costs_applied": bool(
            _money(
                business_cogs + business_overhead + business_spoilage_loss + business_fuel_cost + business_maintenance_cost
            )
            > Decimal("0.00")
        ),
        "medical_event_cost_applied": bool(_money(medical_cost_xgp + missed_work_penalty_xgp) > Decimal("0.00")),
    }

    return {
        "starting_cash": _money(day_start_cash),
        "total_income": total_income,
        "total_expense": total_expense,
        "net_change": net_change,
        "ending_cash": _money(ending_cash),
        "income_breakdown": income_breakdown,
        "expense_breakdown": expense_breakdown,
        "biggest_expense_category": biggest_expense_category,
        "biggest_expense_value": _money(biggest_expense_value),
        "cadence_audit": cadence_audit,
    }


def _should_emit_settlement_audit_debug(player_id: UUID, day_number: int) -> bool:
    target_player = (os.getenv("SETTLEMENT_AUDIT_DEBUG_PLAYER_ID") or "").strip()
    target_day = (os.getenv("SETTLEMENT_AUDIT_DEBUG_DAY") or "").strip()
    if not target_player and not target_day:
        return False

    player_match = (not target_player) or target_player == "*" or target_player == str(player_id)
    if not player_match:
        return False
    if not target_day or target_day == "*":
        return True
    try:
        return int(target_day) == int(day_number)
    except ValueError:
        return False


def settle_player_day(db: Session, player_id: str | UUID) -> dict:
    """Settle one player day and persist snapshots + immutable log."""
    # Core logic freeze: settlement is the canonical player-day close. Preserve idempotency,
    # write-once log behavior, and accounting field meanings unless fixing a proven defect.
    try:
        player = _resolve_player(db, player_id)
        settled_day = get_next_player_day(db, player.id)
        settlement_day_key = f"{player.id}:{settled_day}"

        existing_log_count = int(
            db.query(func.count(DailySettlementLog.id))
            .filter(
                DailySettlementLog.player_id == player.id,
                DailySettlementLog.day_number == settled_day,
            )
            .scalar()
            or 0
        )
        prior_last_settled_day = int(player.last_settled_day) if player.last_settled_day is not None else None
        if prior_last_settled_day is not None and prior_last_settled_day >= int(settled_day):
            raise SettlementValidationError(
                f"Player day {settled_day} already settled (last_settled_day={prior_last_settled_day})."
            )

        existing_log = (
            db.query(DailySettlementLog)
            .filter(
                DailySettlementLog.player_id == player.id,
                DailySettlementLog.day_number == settled_day,
            )
            .first()
        )
        if existing_log is not None or existing_log_count > 0:
            raise SettlementValidationError(f"Player day {settled_day} already settled.")

        pds = _get_or_create_player_daily_state(db, player, settled_day)
        ensure_day_dinner_resolved(
            db,
            player=player,
            day_number=settled_day,
            source="end_of_day_settlement",
            now_houston=get_houston_now(),
            allow_debt_extension=True,
        )
        day_start_cash = _money(_d(getattr(pds, "cash_start", player.cash_xgp)))
        pds_settled_before = bool(pds.did_settlement)
        if pds_settled_before:
            raise SettlementValidationError(f"Player day {settled_day} already settled.")

        # Daily loop order:
        # market update -> business operations -> player settlement.
        # Business runs first so settlement can report its contribution clearly.
        business_summary = run_player_businesses_for_day(
            db=db,
            player_id=player.id,
            day=settled_day,
            commit=False,
        )
        business_revenue = _money(_d(business_summary.get("business_revenue_xgp", 0)))
        business_cogs = _money(_d(business_summary.get("business_cogs_xgp", 0)))
        business_overhead = _money(_d(business_summary.get("business_overhead_xgp", 0)))
        business_spoilage_loss = _money(_d(business_summary.get("business_spoilage_loss_xgp", 0)))
        business_fuel_cost = _money(_d(business_summary.get("business_fuel_cost_xgp", 0)))
        business_maintenance_cost = _money(_d(business_summary.get("business_maintenance_cost_xgp", 0)))
        business_net = _money(_d(business_summary.get("business_net_profit_xgp", business_summary.get("total_business_profit_xgp", 0))))
        business_count_run = int(business_summary.get("business_count_run", 0))
        housing_effect = compute_housing_effects_for_day(db=db, player_id=player.id, day=settled_day)
        housing_cost_daily = _money(_d(housing_effect.get("housing_cost_daily_xgp", housing_effect.get("housing_cost_xgp", 0))))
        utilities_cost_daily = _money(_d(housing_effect.get("utilities_cost_daily_xgp", 0)))
        commute_hours = _q4(_d(housing_effect.get("commute_hours", 0)))
        commute_fuel_cost_xgp = _money(_d(housing_effect.get("commute_fuel_cost_xgp", 0)))
        region_stress_delta = _q4(_d(housing_effect.get("region_stress_delta", housing_effect.get("stress_delta", 0))))
        region_opportunity_modifier = _q4(_d(housing_effect.get("region_opportunity_modifier", 0)))
        region_business_demand_modifier = _q4(_d(housing_effect.get("region_business_demand_modifier", 0)))
        region_side_income_modifier = _q4(_d(housing_effect.get("region_side_income_modifier", 0)))
        networking_modifier = _q4(_d(housing_effect.get("networking_modifier", 0)))
        opportunity_quality_signal = _q4(_d(housing_effect.get("opportunity_quality_signal", 1)))
        housing_cost = housing_cost_daily
        housing_region = housing_effect.get("region") or housing_effect.get("region_key")
        region_key = housing_effect.get("region_key") or housing_region
        commute_pressure = _q4(_d(housing_effect.get("commute_pressure", 0)))
        housing_stress_delta = int(
            _clamp(
                _d(housing_effect.get("stress_delta", region_stress_delta)),
                Decimal("-20"),
                Decimal("20"),
            )
        )
        opportunity_modifier = _q4(
            _d(housing_effect.get("opportunity_modifier", (Decimal("1.00") + region_opportunity_modifier)))
        )

        employment_progression = apply_employment_progression(
            db=db,
            player_id=player.id,
            day=settled_day,
            commit=False,
        )
        employment = _latest_employment_state(db, player.id)
        monthly_pay = _d(employment_progression.get("monthly_pay_xgp_after_event", 0))
        productivity = _d(employment_progression.get("productivity_modifier", getattr(employment, "productivity_modifier", 1)))
        employed = bool((employment_progression.get("employment_status") or "seeking") == "employed")
        employment_status = str(employment_progression.get("employment_status", "seeking"))
        employment_event = str(employment_progression.get("employment_event", "none"))
        layoff_risk_pct = _q4(_d(employment_progression.get("layoff_risk_pct", 0)))
        promotion_chance_pct = _q4(_d(employment_progression.get("promotion_chance_pct", 0)))
        wage_adjustment_pct = _q4(_d(employment_progression.get("wage_adjustment_pct", 0)))
        monthly_pay_after_event = _money(_d(employment_progression.get("monthly_pay_xgp_after_event", 0)))
        life_productivity_before = _q4(
            _clamp(_d(getattr(player, "productivity_modifier", 1.0)), Decimal("0.70"), Decimal("1.05"))
        )
        opportunity_access_penalty = _q4(
            _clamp(_d(getattr(player, "opportunity_access_penalty", 0.0)), Decimal("0.00"), Decimal("0.30"))
        )
        career_progress_penalty = _q4(
            _clamp(_d(getattr(player, "career_progress_penalty", 0.0)), Decimal("0.00"), Decimal("0.25"))
        )
        job_income_capture_factor = _q4(
            _clamp(
                Decimal("1.00") - (opportunity_access_penalty * Decimal("0.45")),
                Decimal("0.82"),
                Decimal("1.00"),
            )
        )
        worked_hours = int(getattr(pds, "worked_hours", 0) or 0)
        if worked_hours <= 0:
            worked_hours = int(getattr(player, "main_job_hours_today", 0) or 0)

        recorded_job_income = _money(_d(getattr(pds, "gross_income_xgp", 0)))
        derived_job_income = Decimal("0.00")
        if employed and worked_hours > 0:
            derived_job_income = _money(
                (monthly_pay / Decimal("30") / Decimal("8"))
                * Decimal(str(worked_hours))
                * productivity
                * life_productivity_before
                * job_income_capture_factor
            )
        job_income = recorded_job_income if recorded_job_income > Decimal("0.00") else derived_job_income
        did_work = bool(
            getattr(pds, "did_work", False)
            or bool(getattr(pds, "worked_main_job", False))
            or worked_hours > 0
            or recorded_job_income > Decimal("0.00")
        )
        cash_before = _money(_d(player.cash_xgp))
        stress_before = int(player.stress or 0)
        health_before = int(player.health or 100)
        hours_before = int(player.hours_available or HOURS_RESET)
        shift_day_sync = sync_shift_day_rules_if_needed(
            db,
            player=player,
            day_number=settled_day,
            now_houston=get_houston_now(),
        )
        if bool(shift_day_sync.get("missed_shift_today")):
            pds = _get_or_create_player_daily_state(db, player, settled_day)
            did_work = bool(getattr(pds, "did_work", False))

        side_income_net = _money(_d(getattr(pds, "side_income_net_xgp", 0)))
        side_income_hours = _q4(_d(getattr(pds, "side_income_hours", 0)))
        side_income_fuel_cost = _money(_d(getattr(pds, "side_income_fuel_cost_xgp", 0)))
        side_income_wear_cost = _money(_d(getattr(pds, "side_income_wear_cost_xgp", 0)))
        side_income_maintenance_cost = _money(_d(getattr(pds, "side_income_maintenance_cost_xgp", 0)))
        stock_realized_pnl = _money(_d(getattr(pds, "stock_realized_pnl_xgp", 0)))
        stock_sale_income, stock_fee = _safe_player_day_stock_totals(db, player.id, settled_day)
        if stock_sale_income <= Decimal("0.00") and stock_realized_pnl > Decimal("0.00"):
            stock_sale_income = stock_realized_pnl

        consumption_result = compute_player_daily_consumption(
            db=db,
            player_id=player.id,
            day=settled_day,
            commit=False,
        )
        essentials_spend = _money(_d(consumption_result["essentials_spend_xgp"]))
        protein_spend = _money(_d(consumption_result["protein_spend_xgp"]))
        produce_spend = _money(_d(consumption_result["produce_spend_xgp"]))
        convenience_spend = _money(_d(consumption_result["convenience_spend_xgp"]))
        basket_spend = _money(_d(consumption_result["total_spend_xgp"]))
        budget_pressure_score = _q4(_d(consumption_result["budget_pressure_score"]))
        stress_spend_modifier = _q4(_d(consumption_result["stress_spend_modifier"]))
        nutrition_pressure_score = _q4(_d(consumption_result["nutrition_pressure_score"]))
        weekly_gas_expense = _money(WEEKLY_GAS_EXPENSE_XGP if int(settled_day) % 7 == 0 else Decimal("0.00"))

        cash_after_non_debt_costs = _money(
            max(
                Decimal("0.00"),
                cash_before
                - basket_spend
                - housing_cost
                - utilities_cost_daily
                - weekly_gas_expense,
            )
        )
        debt_result = apply_daily_debt_and_credit(
            db=db,
            player_id=player.id,
            day=settled_day,
            commit=False,
            mutate_player=False,
            available_cash_xgp=cash_after_non_debt_costs,
            budget_pressure_override=budget_pressure_score,
            employed_override=employed,
            monthly_pay_override=monthly_pay_after_event,
        )
        debt_before = _money(_d(debt_result["opening_debt_xgp"]))
        payment_due = _money(_d(debt_result["payment_due_xgp"]))
        debt_paid = _money(_d(debt_result["payment_made_xgp"]))
        interest_added = _money(_d(debt_result["interest_added_xgp"]))
        ending_debt = _money(_d(debt_result["ending_debt_xgp"]))
        payment_status = str(debt_result["payment_status"])
        opening_credit_score = int(debt_result["opening_credit_score"])
        credit_score_change = int(debt_result["credit_score_change"])
        ending_credit_score = int(debt_result["ending_credit_score"])
        delinquency_flag = bool(debt_result["delinquency_flag"])
        debt_log_idempotent = bool(debt_result.get("already_processed", False))
        debt_player_mutation_applied = bool(debt_result.get("player_mutation_applied", False))

        debt_cash_deduction = debt_paid
        if debt_log_idempotent and debt_player_mutation_applied:
            # Endpoint-triggered processing already charged player cash for this day.
            debt_cash_deduction = Decimal("0.00")

        life_result = apply_life_consequences_for_player(
            db=db,
            player_id=player.id,
        )
        medical_cost_xgp = _money(_d(life_result.get("medical_cost_xgp", 0)))
        missed_work_penalty_xgp = _money(_d(life_result.get("missed_work_penalty_xgp", 0)))
        total_hours_used = _q4(_d(getattr(pds, "total_hours_used", 0)))
        overtime_hours = _q4(_d(getattr(pds, "overtime_hours", 0)))
        sleep_hours = _q4(_d(getattr(pds, "sleep_hours", 0)))
        recovery_hours = _q4(_d(getattr(pds, "recovery_hours", 0)))
        burnout_risk = _q4(_d(getattr(pds, "burnout_risk", getattr(player, "burnout_risk", 0))))
        medical_event_risk = _q4(_d(getattr(pds, "medical_event_risk", getattr(player, "medical_event_risk", 0))))
        life_productivity_after = _q4(
            _d(getattr(pds, "productivity_modifier", getattr(player, "productivity_modifier", life_productivity_before)))
        )

        try:
            financial_distress_result = apply_daily_financial_distress(
                db=db,
                player_id=player.id,
                day_number=settled_day,
                debt_context=debt_result,
                monthly_income_xgp=monthly_pay_after_event,
                business_net_profit_xgp=business_net,
                available_cash_xgp=cash_after_non_debt_costs,
            )
        except Exception:
            financial_distress_result = {
                "debt_payment_due_xgp": float(payment_due),
                "debt_payment_paid_xgp": float(debt_paid),
                "debt_payment_missed": bool(delinquency_flag),
                "late_fee_xgp": 0.0,
                "accrued_interest_xgp": 0.0,
                "credit_score_before": int(opening_credit_score),
                "credit_score_after": int(ending_credit_score),
                "credit_score_delta": int(credit_score_change),
                "distress_state_before": str(getattr(player, "distress_state", "stable") or "stable"),
                "distress_state_after": str(getattr(player, "distress_state", "stable") or "stable"),
                "distress_score_before": float(_q4(_d(getattr(player, "distress_score", 0)))),
                "distress_score_after": float(_q4(_d(getattr(player, "distress_score", 0)))),
                "borrowing_cost_modifier": float(_q4(_d(getattr(player, "borrowing_cost_modifier", 1)))),
                "opportunity_access_penalty": float(_q4(_d(getattr(player, "opportunity_access_penalty", 0)))),
                "business_risk_penalty": float(_q4(_d(getattr(player, "business_risk_penalty", 0)))),
                "career_progress_penalty": float(_q4(_d(getattr(player, "career_progress_penalty", 0)))),
                "recovery_actions_applied": [],
                "distress_driver_json": {},
                "already_processed": False,
            }
        debt_payment_due_xgp = _money(_d(financial_distress_result.get("debt_payment_due_xgp", payment_due)))
        debt_payment_paid_xgp = _money(_d(financial_distress_result.get("debt_payment_paid_xgp", debt_paid)))
        debt_payment_missed = bool(financial_distress_result.get("debt_payment_missed", False))
        late_fee_xgp = _money(_d(financial_distress_result.get("late_fee_xgp", 0)))
        accrued_interest_xgp = _money(_d(financial_distress_result.get("accrued_interest_xgp", 0)))
        distress_credit_before = int(financial_distress_result.get("credit_score_before", opening_credit_score))
        distress_credit_after = int(financial_distress_result.get("credit_score_after", ending_credit_score))
        distress_credit_delta = int(financial_distress_result.get("credit_score_delta", credit_score_change))
        distress_state_before = str(financial_distress_result.get("distress_state_before", getattr(player, "distress_state", "stable")))
        distress_state_after = str(financial_distress_result.get("distress_state_after", getattr(player, "distress_state", "stable")))
        distress_score_before = _q4(_d(financial_distress_result.get("distress_score_before", getattr(player, "distress_score", 0))))
        distress_score_after = _q4(_d(financial_distress_result.get("distress_score_after", getattr(player, "distress_score", 0))))
        borrowing_cost_modifier = _q4(_d(financial_distress_result.get("borrowing_cost_modifier", getattr(player, "borrowing_cost_modifier", 1))))
        opportunity_access_penalty = _q4(
            _d(financial_distress_result.get("opportunity_access_penalty", getattr(player, "opportunity_access_penalty", opportunity_access_penalty)))
        )
        business_risk_penalty = _q4(_d(financial_distress_result.get("business_risk_penalty", getattr(player, "business_risk_penalty", 0))))
        career_progress_penalty = _q4(
            _d(financial_distress_result.get("career_progress_penalty", getattr(player, "career_progress_penalty", career_progress_penalty)))
        )
        recovery_actions_applied = list(financial_distress_result.get("recovery_actions_applied", []))
        distress_driver_json = financial_distress_result.get("distress_driver_json", {})
        financial_distress_summary = {
            "debt_payment_due_xgp": float(debt_payment_due_xgp),
            "debt_payment_paid_xgp": float(debt_payment_paid_xgp),
            "debt_payment_missed": bool(debt_payment_missed),
            "late_fee_xgp": float(late_fee_xgp),
            "accrued_interest_xgp": float(accrued_interest_xgp),
            "credit_score_before": int(distress_credit_before),
            "credit_score_after": int(distress_credit_after),
            "credit_score_delta": int(distress_credit_delta),
            "distress_state_before": distress_state_before,
            "distress_state_after": distress_state_after,
            "distress_score_before": float(distress_score_before),
            "distress_score_after": float(distress_score_after),
            "borrowing_cost_modifier": float(borrowing_cost_modifier),
            "opportunity_access_penalty": float(opportunity_access_penalty),
            "business_risk_penalty": float(business_risk_penalty),
            "career_progress_penalty": float(career_progress_penalty),
            "recovery_actions_applied": recovery_actions_applied,
            "already_processed": bool(financial_distress_result.get("already_processed", False)),
            "distress_driver_json": distress_driver_json,
        }

        try:
            shock_result = apply_personal_life_event(
                db=db,
                player_id=player.id,
                day_number=settled_day,
                worked_hours=worked_hours,
                job_income_xgp=job_income,
                business_net_xgp=business_net,
                side_income_net_xgp=side_income_net,
                commit=False,
            )
        except Exception:
            # Step 35 is additive. If personal-shock tables are unavailable in
            # older isolated test schemas, keep settlement functional.
            shock_result = {
                "short_summary": "No major personal disruption today.",
                "applied_impacts": {},
                "recent_event": {},
                "recovery_state": {},
                "shock_profile": {},
                "risk_state": {},
                "practical_current_actions": [],
                "debug_meta": {"fallback": "personal_shock_unavailable"},
            }
        shock_impacts = shock_result.get("applied_impacts", {}) if isinstance(shock_result, dict) else {}
        shock_cash_impact = _money(_d(shock_impacts.get("cash_impact_xgp", 0)))
        shock_stress_delta = _q4(_d(shock_impacts.get("stress_impact_delta", 0)))
        shock_health_delta = _q4(_d(shock_impacts.get("health_impact_delta", 0)))
        shock_time_hours = _q4(_d(shock_impacts.get("time_impact_hours", 0)))
        shock_work_income_modifier = _q4(_d(shock_impacts.get("work_income_modifier", 1)))
        shock_business_modifier = _q4(_d(shock_impacts.get("business_modifier", 1)))
        shock_side_income_modifier = _q4(_d(shock_impacts.get("side_income_modifier", 1)))
        shock_operational_delta = _money(_d(shock_impacts.get("operational_delta_xgp", 0)))

        job_income = _money(_d(shock_impacts.get("adjusted_work_income_xgp", job_income)))
        business_net = _money(_d(shock_impacts.get("adjusted_business_net_xgp", business_net)))
        side_income_net = _money(_d(shock_impacts.get("adjusted_side_income_net_xgp", side_income_net)))

        shock_net_cash_delta = _money(shock_cash_impact + shock_operational_delta)
        shock_income_bonus = _money(max(Decimal("0.00"), shock_net_cash_delta))
        shock_extra_expense = _money(max(Decimal("0.00"), -shock_net_cash_delta))

        financial_survival_result: dict
        available_cash_for_survival = _money(max(Decimal("0.00"), cash_after_non_debt_costs + shock_net_cash_delta))
        try:
            financial_survival_result = apply_daily_financial_survival(
                db=db,
                player_id=player.id,
                day_number=settled_day,
                available_cash_xgp=available_cash_for_survival,
                debt_payment_due_xgp=debt_payment_due_xgp,
                debt_payment_paid_xgp=debt_payment_paid_xgp,
                housing_paid_xgp=housing_cost_daily,
                utilities_paid_xgp=utilities_cost_daily,
                business_overhead_paid_xgp=business_overhead,
                apply_stress_to_player=False,
            )
        except Exception:
            financial_survival_result = {
                "already_processed": False,
                "payment_outcome": "paid_full",
                "required_daily_burden_xgp": 0.0,
                "required_monthly_obligation_xgp": 0.0,
                "obligation_load_ratio": 0.0,
                "liquidity_buffer_days": 0.0,
                "payment_pressure_label": "manageable",
                "current_delinquency_stage": "current",
                "survival_status_label": "current",
                "late_fee_xgp": 0.0,
                "late_fee_non_debt_xgp": 0.0,
                "additional_required_paid_xgp": 0.0,
                "credit_score_before": int(distress_credit_before),
                "credit_score_after": int(distress_credit_after),
                "credit_score_delta": 0,
                "stress_impact_delta": 0.0,
                "practical_current_actions": [],
                "short_summary": "Financial survival state unavailable; using fallback values.",
                "obligation_profile": {},
                "payment_risk_state": {},
                "credit_impact_summary": {},
                "delinquency_state": {},
                "debug_meta": {"fallback": "financial_survival_unavailable"},
            }

        financial_survival_late_fee_xgp = _money(_d(financial_survival_result.get("late_fee_xgp", 0)))
        financial_survival_late_fee_non_debt_xgp = _money(
            _d(financial_survival_result.get("late_fee_non_debt_xgp", financial_survival_late_fee_xgp))
        )
        financial_survival_additional_required_paid_xgp = _money(
            _d(financial_survival_result.get("additional_required_paid_xgp", 0))
        )
        financial_survival_required_daily_burden_xgp = _money(
            _d(financial_survival_result.get("required_daily_burden_xgp", 0))
        )
        financial_survival_required_monthly_obligation_xgp = _money(
            _d(financial_survival_result.get("required_monthly_obligation_xgp", 0))
        )
        financial_survival_obligation_load_ratio = _q4(_d(financial_survival_result.get("obligation_load_ratio", 0)))
        financial_survival_liquidity_buffer_days = _q4(
            _d(financial_survival_result.get("liquidity_buffer_days", 0))
        )
        financial_survival_payment_pressure_label = str(
            financial_survival_result.get("payment_pressure_label", "manageable")
        )
        financial_survival_current_delinquency_stage = str(
            financial_survival_result.get("current_delinquency_stage", "current")
        )
        financial_survival_survival_status_label = str(
            financial_survival_result.get("survival_status_label", "current")
        )
        financial_survival_payment_outcome = str(
            financial_survival_result.get("payment_outcome", "paid_full")
        )
        financial_survival_credit_before = int(
            financial_survival_result.get("credit_score_before", distress_credit_before)
        )
        financial_survival_credit_after = int(
            financial_survival_result.get("credit_score_after", distress_credit_after)
        )
        financial_survival_credit_delta = int(
            financial_survival_result.get(
                "credit_score_delta",
                financial_survival_credit_after - financial_survival_credit_before,
            )
        )
        financial_survival_stress_impact_delta = _q4(
            _d(financial_survival_result.get("stress_impact_delta", 0))
        )
        financial_survival_practical_actions = list(
            financial_survival_result.get("practical_current_actions", [])
        )
        financial_survival_summary = {
            "survival_status_label": financial_survival_survival_status_label,
            "payment_pressure_label": financial_survival_payment_pressure_label,
            "current_delinquency_stage": financial_survival_current_delinquency_stage,
            "required_daily_burden_xgp": float(financial_survival_required_daily_burden_xgp),
            "required_monthly_obligation_xgp": float(financial_survival_required_monthly_obligation_xgp),
            "obligation_load_ratio": float(financial_survival_obligation_load_ratio),
            "liquidity_buffer_days": float(financial_survival_liquidity_buffer_days),
            "payment_outcome": financial_survival_payment_outcome,
            "late_fee_xgp": float(financial_survival_late_fee_xgp),
            "late_fee_non_debt_xgp": float(financial_survival_late_fee_non_debt_xgp),
            "additional_required_paid_xgp": float(financial_survival_additional_required_paid_xgp),
            "credit_score_before": int(financial_survival_credit_before),
            "credit_score_after": int(financial_survival_credit_after),
            "credit_score_delta": int(financial_survival_credit_delta),
            "stress_impact_delta": float(financial_survival_stress_impact_delta),
            "practical_current_actions": financial_survival_practical_actions,
            "short_summary": str(financial_survival_result.get("short_summary", "")),
            "obligation_profile": financial_survival_result.get("obligation_profile", {}),
            "payment_risk_state": financial_survival_result.get("payment_risk_state", {}),
            "credit_impact_summary": financial_survival_result.get("credit_impact_summary", {}),
            "delinquency_state": financial_survival_result.get("delinquency_state", {}),
            "already_processed": bool(financial_survival_result.get("already_processed", False)),
            "debug_meta": financial_survival_result.get("debug_meta", {}),
        }

        borrowing_refresh: dict = {}
        borrowing_eligibility: dict = {}
        borrowing_liquidity_state: dict = {}
        borrowing_options_payload: dict = {}
        borrowing_risk_summary: dict = {}
        borrowing_pressure_summary: dict = {}
        try:
            borrowing_refresh = refresh_loan_accounts(
                db=db,
                player_id=player.id,
                day_number=settled_day,
                payment_outcome=financial_survival_payment_outcome,
            )
        except Exception:
            borrowing_refresh = {"processed_accounts": 0, "debug_meta": {"fallback": "borrowing_refresh_unavailable"}}
        try:
            borrowing_eligibility = build_borrowing_eligibility_profile(
                db=db,
                player_id=player.id,
                day_number=settled_day,
            )
            borrowing_liquidity_state = build_emergency_liquidity_state(
                db=db,
                player_id=player.id,
                day_number=settled_day,
            )
            borrowing_options_payload = generate_borrowing_options(
                db=db,
                player_id=player.id,
                day_number=settled_day,
                include_locked=False,
            )
            borrowing_risk_summary = build_borrowing_risk_summary(
                db=db,
                player_id=player.id,
                day_number=settled_day,
            )
            borrowing_pressure_summary = build_borrowing_pressure_summary(
                db=db,
                player_id=player.id,
                day_number=settled_day,
            )
        except Exception:
            borrowing_eligibility = {}
            borrowing_liquidity_state = {}
            borrowing_options_payload = {"items": []}
            borrowing_risk_summary = {}
            borrowing_pressure_summary = {}

        _apply_survival_penalty_if_needed(
            db,
            player=player,
            pds=pds,
            settled_day=settled_day,
        )

        # Step 36 credit consequences are applied after distress and become final credit for the day.
        distress_credit_before = int(financial_survival_credit_before)
        distress_credit_after = int(financial_survival_credit_after)
        distress_credit_delta = int(financial_survival_credit_delta)

        settlement_expenses = _money(
            basket_spend
            + debt_cash_deduction
            + housing_cost
            + utilities_cost_daily
            + weekly_gas_expense
            + medical_cost_xgp
            + missed_work_penalty_xgp
            + late_fee_xgp
            + accrued_interest_xgp
            + shock_extra_expense
            + financial_survival_late_fee_non_debt_xgp
            + financial_survival_additional_required_paid_xgp
        )
        ending_cash = _money(max(Decimal("0.00"), cash_before + shock_income_bonus - settlement_expenses))
        net_cash_delta = _money(ending_cash - cash_before)
        total_earned = _money(
            job_income
            + side_income_net
            + business_net
            + shock_income_bonus
        )
        settlement_breakdown = _build_settlement_breakdown(
            settled_day=settled_day,
            day_start_cash=day_start_cash,
            ending_cash=ending_cash,
            job_income=job_income,
            side_income_net=side_income_net,
            side_income_fuel_cost=side_income_fuel_cost,
            side_income_wear_cost=side_income_wear_cost,
            side_income_maintenance_cost=side_income_maintenance_cost,
            business_revenue=business_revenue,
            business_cogs=business_cogs,
            business_overhead=business_overhead,
            business_spoilage_loss=business_spoilage_loss,
            business_fuel_cost=business_fuel_cost,
            business_maintenance_cost=business_maintenance_cost,
            stock_sale_income=stock_sale_income,
            stock_fee=stock_fee,
            basket_spend=basket_spend,
            housing_cost_daily=housing_cost_daily,
            utilities_cost_daily=utilities_cost_daily,
            debt_cash_deduction=debt_cash_deduction,
            accrued_interest_xgp=accrued_interest_xgp,
            late_fee_xgp=late_fee_xgp,
            financial_survival_late_fee_non_debt_xgp=financial_survival_late_fee_non_debt_xgp,
            medical_cost_xgp=medical_cost_xgp,
            missed_work_penalty_xgp=missed_work_penalty_xgp,
            financial_survival_additional_required_paid_xgp=financial_survival_additional_required_paid_xgp,
            commute_fuel_cost_xgp=commute_fuel_cost_xgp,
            shock_income_bonus=shock_income_bonus,
            shock_extra_expense=shock_extra_expense,
        )
        total_income = _money(_d(settlement_breakdown["total_income"]))
        total_expense = _money(_d(settlement_breakdown["total_expense"]))
        net_change = _money(_d(settlement_breakdown["net_change"]))

        stress_before = int(getattr(pds, "stress_start", stress_before))
        _base_stress_after = int(getattr(pds, "stress_end", player.stress or stress_before))
        stress_after = _clamp_int(
            int(
                round(
                    float(
                        _d(_base_stress_after)
                        + shock_stress_delta
                        + financial_survival_stress_impact_delta
                    )
                )
            ),
            0,
            100,
        )
        stress_change = int(stress_after - stress_before)
        health_before = int(getattr(pds, "health_start", health_before))
        _base_health_after = int(getattr(pds, "health_end", player.health or health_before))
        health_after = _clamp_int(int(round(float(_d(_base_health_after) + shock_health_delta))), 0, 100)
        health_change = int(health_after - health_before)
        total_hours_used = _q4(_clamp(total_hours_used + shock_time_hours, Decimal("0"), Decimal("30")))
        overtime_hours = _q4(_clamp(max(overtime_hours, total_hours_used - Decimal("24")), Decimal("0"), Decimal("12")))

        player.cash_xgp = ending_cash
        player.debt_xgp = ending_debt
        player.credit_score = distress_credit_after
        player.stress = stress_after
        player.health = health_after
        player.hours_available = HOURS_RESET
        player.last_settled_day = settled_day
        player.main_job_hours_today = 0
        player.side_job_hours_today = 0
        player.total_hours_worked_today = 0
        player.work_actions_today = 0
        player.net_worth_xgp = _money(_d(player.cash_xgp) + _d(player.bank_savings_xgp) - _d(player.debt_xgp))

        if job_income > Decimal("0.00") and _count_gameplay_transactions_for_category(
            db,
            player_id=player.id,
            day_number=settled_day,
            category="salary",
        ) == 0:
            record_gameplay_transaction(
                db,
                player=player,
                day=settled_day,
                transaction_type="income",
                category="salary",
                amount=job_income,
                description=f"Main job salary for Day {int(settled_day)}",
            )
        if side_income_net > Decimal("0.00") and _count_gameplay_transactions_for_category(
            db,
            player_id=player.id,
            day_number=settled_day,
            category="ride_share",
        ) == 0:
            record_gameplay_transaction(
                db,
                player=player,
                day=settled_day,
                transaction_type="income",
                category="ride_share",
                amount=side_income_net,
                description="Ride Share payout",
            )
        if basket_spend > Decimal("0.00"):
            record_gameplay_transaction(
                db,
                player=player,
                day=settled_day,
                transaction_type="expense",
                category="food",
                amount=basket_spend,
                description="Daily food cost",
            )
        gas_total = _money(weekly_gas_expense + commute_fuel_cost_xgp)
        if gas_total > Decimal("0.00"):
            record_gameplay_transaction(
                db,
                player=player,
                day=settled_day,
                transaction_type="expense",
                category="gas",
                amount=gas_total,
                description="Fuel and commute cost",
            )
        rent_total = _money(housing_cost_daily + utilities_cost_daily)
        if rent_total > Decimal("0.00"):
            record_gameplay_transaction(
                db,
                player=player,
                day=settled_day,
                transaction_type="expense",
                category="rent",
                amount=rent_total,
                description="Rent and utilities",
            )
        if missed_work_penalty_xgp > Decimal("0.00"):
            record_gameplay_transaction(
                db,
                player=player,
                day=settled_day,
                transaction_type="expense",
                category="stress_penalty",
                amount=missed_work_penalty_xgp,
                description="Burnout or medical recovery penalty",
            )

        settlement_txn = record_player_transaction(
            db,
            player=player,
            day=settled_day,
            transaction_type="settlement_adjustment",
            category="settlement",
            gross_amount=total_earned,
            fee_amount=settlement_expenses,
            net_cash_delta=net_cash_delta,
            resulting_cash_balance=ending_cash,
            metadata={
                "job_income_xgp": float(job_income),
                "side_income_net_xgp": float(side_income_net),
                "business_net_xgp": float(business_net),
                "shock_income_bonus_xgp": float(shock_income_bonus),
                "basket_spend_xgp": float(basket_spend),
                "debt_cash_deduction_xgp": float(debt_cash_deduction),
                "housing_cost_xgp": float(housing_cost),
                "utilities_cost_daily_xgp": float(utilities_cost_daily),
                "commute_fuel_cost_xgp": float(commute_fuel_cost_xgp),
                "weekly_gas_expense_xgp": float(weekly_gas_expense),
                "medical_cost_xgp": float(medical_cost_xgp),
                "missed_work_penalty_xgp": float(missed_work_penalty_xgp),
                "late_fee_xgp": float(late_fee_xgp),
                "accrued_interest_xgp": float(accrued_interest_xgp),
                "shock_extra_expense_xgp": float(shock_extra_expense),
            },
        )

        pds.hours_available_end = HOURS_RESET
        pds.did_work = did_work
        pds.worked_hours = worked_hours
        pds.salary_earned = _money(job_income)
        pds.missed_penalty = _money(missed_work_penalty_xgp)
        pds.gross_income_xgp = _money(job_income)
        pds.basket_spend_xgp = _money(basket_spend)
        pds.debt_payment_xgp = _money(debt_payment_paid_xgp)
        pds.stress_start = stress_before
        pds.stress_end = stress_after
        pds.stress_delta = stress_change
        pds.health_start = health_before
        pds.health_end = health_after
        pds.health_delta = health_change
        pds.cash_start = day_start_cash
        pds.cash_end = ending_cash
        pds.did_settlement = True
        pds.housing_cost_paid = housing_cost
        pds.housing_region_id = housing_region or player.housing_region_id
        pds.region_key = region_key or housing_region or player.housing_region_id
        pds.housing_cost_daily_xgp = housing_cost_daily
        pds.utilities_cost_daily_xgp = utilities_cost_daily
        pds.commute_hours = commute_hours
        pds.commute_fuel_cost_xgp = commute_fuel_cost_xgp
        pds.region_stress_delta = region_stress_delta
        pds.region_opportunity_modifier = region_opportunity_modifier
        pds.region_business_demand_modifier = region_business_demand_modifier
        pds.region_side_income_modifier = region_side_income_modifier
        pds.networking_modifier = networking_modifier
        pds.opportunity_quality_signal = opportunity_quality_signal

        stock_market_day_used = _latest_stock_day(db)
        net_worth_snapshot = compute_player_net_worth_snapshot(
            db=db,
            player_id=player.id,
            day=settled_day,
            commit=False,
        )

        net_worth_xgp = float(net_worth_snapshot["net_worth_xgp"])
        total_assets_xgp = float(net_worth_snapshot["total_assets_xgp"])
        stock_market_value_xgp = float(net_worth_snapshot["stock_market_value_xgp"])
        business_value_xgp = float(net_worth_snapshot["business_value_xgp"])
        debt_xgp = float(net_worth_snapshot["debt_xgp"])
        allocation_json = net_worth_snapshot.get("allocation_json", {}) or {}

        guided_day_number = int(settled_day) if int(settled_day) <= 3 else 0
        guided_learning_title = None
        guided_earned_summary = None
        guided_spent_summary = None
        guided_change_summary = None
        guided_watch_tomorrow = None
        if guided_day_number == 1:
            guided_learning_title = "Learn the daily loop"
            guided_earned_summary = f"Your work and side actions created {float(_money(job_income + side_income_net + shock_income_bonus)):.2f} xgp today."
            guided_spent_summary = f"Daily costs used {float(total_expense):.2f} xgp across essentials, housing, debt, and other pressure."
            guided_change_summary = f"Settlement locked in a {float(_money(ending_cash - cash_before)):+.2f} xgp net result for the day."
            guided_watch_tomorrow = "Tomorrow, read the brief first, then make one clear move before ending the day."
        elif guided_day_number == 2:
            guided_learning_title = "Pressure is real"
            guided_earned_summary = f"You brought in {float(_money(job_income + side_income_net + business_net + shock_income_bonus)):.2f} xgp. Income now needs to beat daily pressure."
            guided_spent_summary = f"Required and pressure costs used {float(total_expense):.2f} xgp, with {float(financial_survival_required_daily_burden_xgp):.2f} xgp of daily burden in view."
            guided_change_summary = f"Payment pressure is {financial_survival_payment_pressure_label}; stress moved {stress_change:+d} and health moved {health_change:+d}."
            guided_watch_tomorrow = "Warnings matter now. Recover if pressure rises, then compare whether the safer path improved tomorrow."
        elif guided_day_number == 3:
            guided_learning_title = "Adapt to opportunity"
            guided_earned_summary = f"Today produced {float(_money(job_income + side_income_net + business_net + shock_income_bonus)):.2f} xgp of income across the options you chose."
            guided_spent_summary = f"You spent {float(total_expense):.2f} xgp, so every opportunity still had to respect cash safety and obligations."
            guided_change_summary = f"The loop is now about adapting: net cash changed {float(_money(ending_cash - cash_before)):+.2f} xgp while pressure stayed {financial_survival_payment_pressure_label}."
            guided_watch_tomorrow = "Protect essentials first, then explore one business or stock signal only when the brief supports it."

        # ── Step 69: Retention Engine ──────────────────────────────────────────
        # Load the player's progression state (owns login streak fields).
        _progression_state = (
            db.query(PlayerProgressionState)
            .filter(PlayerProgressionState.player_id == player.id)
            .first()
        )
        _login_streak_days = int(getattr(_progression_state, "login_streak_current", 0))

        # Build retention summary — pure, no DB access.
        retention_summary = build_retention_summary(
            player_state={
                "cash": float(ending_cash),
                "stress": int(stress_after),
                "health": int(health_after),
                "debt_xgp": float(ending_debt),
                "main_job": getattr(employment, "current_job_code", None),
                "distress_state": distress_state_after,
                "day_number": int(settled_day),
            },
            settlement_result={
                "income_xgp": float(total_income),
                "expenses_xgp": float(total_expense),
                "payment_pressure_label": financial_survival_payment_pressure_label,
                "stress_change": int(stress_change),
                "health_change": int(health_change),
                "employment_event": employment_event,
                "layoff_risk_pct": float(layoff_risk_pct),
                "opportunity_quality_signal": float(opportunity_quality_signal),
                "debt_payment_missed": bool(debt_payment_missed),
            },
            streak_days=_login_streak_days,
            opportunities=[],  # future: pipe from event_service
        )

        # Apply bounded streak bonuses to settled values.
        _streak_info = retention_summary.get("streak_info", {})
        _streak_income_boost = Decimal(str(_streak_info.get("income_boost_xgp", 0)))
        _streak_stress_relief = int(_streak_info.get("stress_reduction_bonus", 0))
        if _streak_income_boost > Decimal("0"):
            ending_cash = _money(ending_cash + _streak_income_boost)
            player.cash_xgp = ending_cash
            pds.cash_end = ending_cash
            player.net_worth_xgp = _money(
                _d(player.cash_xgp) + _d(player.bank_savings_xgp) - _d(player.debt_xgp)
            )
            total_income = _money(total_income + _streak_income_boost)
            total_earned = _money(total_earned + _streak_income_boost)
            net_change = _money(total_income - total_expense)
            net_cash_delta = _money(ending_cash - cash_before)
            _income_breakdown = settlement_breakdown.get("income_breakdown") or {}
            _income_breakdown["other_income"] = _money(_d(_income_breakdown.get("other_income", 0)) + _streak_income_boost)
            settlement_breakdown["income_breakdown"] = _income_breakdown
            settlement_breakdown["total_income"] = total_income
            settlement_breakdown["net_change"] = net_change
            settlement_breakdown["ending_cash"] = _money(ending_cash)
            settlement_txn.gross_amount = total_earned
            settlement_txn.net_cash_delta = net_cash_delta
            settlement_txn.resulting_cash_balance = ending_cash
            try:
                _txn_meta = json.loads(settlement_txn.metadata_json or "{}")
            except Exception:
                _txn_meta = {}
            _txn_meta["streak_income_boost_xgp"] = float(_money(_streak_income_boost))
            settlement_txn.metadata_json = json.dumps(_txn_meta)
        if _streak_stress_relief > 0:
            stress_after = _clamp_int(stress_after - _streak_stress_relief, 0, 100)
            stress_change = int(stress_after - stress_before)
            player.stress = stress_after
            pds.stress_end = stress_after
            pds.stress_delta = stress_change

        # Update login streak on PlayerProgressionState in the same transaction.
        if _progression_state is not None:
            _prev_last_day = getattr(_progression_state, "login_streak_last_day", None)
            if _prev_last_day is None:
                _new_streak = 1
            elif int(_prev_last_day) == int(settled_day) - 1:
                _new_streak = _login_streak_days + 1
            elif int(_prev_last_day) == int(settled_day):
                _new_streak = _login_streak_days  # same-day re-attempt, no change
            else:
                _new_streak = 1  # gap in streak — reset
            _progression_state.login_streak_current = _new_streak
            _progression_state.login_streak_best = max(
                int(getattr(_progression_state, "login_streak_best", 0)), _new_streak
            )
            _progression_state.login_streak_last_day = int(settled_day)

        # Persist flags to PlayerDailyState (nullable columns added in Step 69 migration).
        try:
            pds.retention_flags_json = json.dumps(retention_summary["next_day_pressure_flags"])
            pds.carryover_opportunities_json = json.dumps(retention_summary["carryover_opportunities"])
        except Exception:
            pass  # non-fatal: columns may not exist on un-migrated schemas

        income_breakdown_payload = {
            key: float(_money(_d(value)))
            for key, value in (settlement_breakdown.get("income_breakdown") or {}).items()
        }
        expense_breakdown_payload = {
            key: float(_money(_d(value)))
            for key, value in (settlement_breakdown.get("expense_breakdown") or {}).items()
        }
        cadence_audit_payload = dict(settlement_breakdown.get("cadence_audit") or {})
        settlement_debug = {
            "settlement_day_key": settlement_day_key,
            "settlement_already_exists_for_day": bool(existing_log is not None or existing_log_count > 0),
            "existing_settlement_count_for_day": int(existing_log_count),
            "pds_already_settled": bool(pds_settled_before),
            "last_settled_day_before": prior_last_settled_day,
            "weekly_or_monthly_charge_flags": cadence_audit_payload,
        }

        summary_payload = {
            "headline": f"Day {settled_day} settled.",
            "guided_day_number": guided_day_number,
            "guided_learning_title": guided_learning_title,
            "guided_earned_summary": guided_earned_summary,
            "guided_spent_summary": guided_spent_summary,
            "guided_change_summary": guided_change_summary,
            "guided_watch_tomorrow": guided_watch_tomorrow,
            "starting_cash_xgp": float(day_start_cash),
            "total_income_xgp": float(total_income),
            "total_expense_xgp": float(total_expense),
            "net_change_xgp": float(net_change),
            "settlement_breakdown": {
                "starting_cash": float(_money(_d(settlement_breakdown.get("starting_cash", 0)))),
                "total_income": float(total_income),
                "total_expense": float(total_expense),
                "net_change": float(net_change),
                "ending_cash": float(_money(_d(settlement_breakdown.get("ending_cash", ending_cash)))),
                "income_breakdown": income_breakdown_payload,
                "expense_breakdown": expense_breakdown_payload,
                "biggest_expense_category": settlement_breakdown.get("biggest_expense_category", "none"),
                "biggest_expense_value": float(
                    _money(_d(settlement_breakdown.get("biggest_expense_value", 0)))
                ),
                "cadence_audit": cadence_audit_payload,
            },
            "settlement_debug": settlement_debug,
            "job_income_xgp": float(job_income),
            "side_income_net_xgp": float(side_income_net),
            "business_net_xgp": float(business_net),
            "stock_sale_income_xgp": float(stock_sale_income),
            "stock_fee_xgp": float(stock_fee),
            "business_revenue_xgp": float(business_revenue),
            "business_cogs_xgp": float(business_cogs),
            "business_overhead_xgp": float(business_overhead),
            "business_spoilage_loss_xgp": float(business_spoilage_loss),
            "business_fuel_cost_xgp": float(business_fuel_cost),
            "business_maintenance_cost_xgp": float(business_maintenance_cost),
            "business_net_profit_xgp": float(business_net),
            "total_business_profit_xgp": float(business_summary.get("total_business_profit_xgp", 0)),
            "business_count_run": business_count_run,
            "per_business_results": business_summary.get("per_business_results", []),
            "essentials_spend_xgp": float(essentials_spend),
            "protein_spend_xgp": float(protein_spend),
            "produce_spend_xgp": float(produce_spend),
            "convenience_spend_xgp": float(convenience_spend),
            "total_basket_spend_xgp": float(basket_spend),
            "basket_spend_xgp": float(basket_spend),
            "budget_pressure_score": float(budget_pressure_score),
            "stress_spend_modifier": float(stress_spend_modifier),
            "nutrition_pressure_score": float(nutrition_pressure_score),
            "debt_paid_xgp": float(debt_paid),
            "debt_payment_due_xgp": float(debt_payment_due_xgp),
            "debt_payment_paid_xgp": float(debt_payment_paid_xgp),
            "debt_payment_missed": bool(debt_payment_missed),
            "late_fee_xgp": float(late_fee_xgp),
            "accrued_interest_xgp": float(accrued_interest_xgp),
            "opening_debt_xgp": float(debt_before),
            "payment_due_xgp": float(payment_due),
            "payment_made_xgp": float(debt_paid),
            "interest_added_xgp": float(interest_added),
            "ending_debt_xgp": float(ending_debt),
            "payment_status": payment_status,
            "opening_credit_score": int(distress_credit_before),
            "credit_score_change": int(distress_credit_delta),
            "ending_credit_score": int(distress_credit_after),
            "delinquency_flag": bool(delinquency_flag),
            "debt_cash_deduction_xgp": float(_money(debt_cash_deduction)),
            "debt_log_idempotent": debt_log_idempotent,
            "weekly_gas_expense_xgp": float(weekly_gas_expense),
            "distress_state_before": distress_state_before,
            "distress_state_after": distress_state_after,
            "distress_score_before": float(distress_score_before),
            "distress_score_after": float(distress_score_after),
            "borrowing_cost_modifier": float(borrowing_cost_modifier),
            "opportunity_access_penalty": float(opportunity_access_penalty),
            "business_risk_penalty": float(business_risk_penalty),
            "career_progress_penalty": float(career_progress_penalty),
            "recovery_actions_applied": recovery_actions_applied,
            "financial_distress_summary": financial_distress_summary,
            "financial_survival_summary": financial_survival_summary,
            "required_monthly_obligation_xgp": float(financial_survival_required_monthly_obligation_xgp),
            "required_daily_burden_xgp": float(financial_survival_required_daily_burden_xgp),
            "obligation_load_ratio": float(financial_survival_obligation_load_ratio),
            "liquidity_buffer_days": float(financial_survival_liquidity_buffer_days),
            "payment_pressure_label": financial_survival_payment_pressure_label,
            "current_delinquency_stage": financial_survival_current_delinquency_stage,
            "survival_status_label": financial_survival_survival_status_label,
            "financial_survival_payment_outcome": financial_survival_payment_outcome,
            "financial_survival_late_fee_xgp": float(financial_survival_late_fee_xgp),
            "financial_survival_late_fee_non_debt_xgp": float(financial_survival_late_fee_non_debt_xgp),
            "financial_survival_additional_required_paid_xgp": float(
                financial_survival_additional_required_paid_xgp
            ),
            "financial_survival_credit_score_before": int(financial_survival_credit_before),
            "financial_survival_credit_score_after": int(financial_survival_credit_after),
            "financial_survival_credit_score_delta": int(financial_survival_credit_delta),
            "financial_survival_stress_impact_delta": float(financial_survival_stress_impact_delta),
            "financial_survival_practical_actions": financial_survival_practical_actions,
            "borrowing_eligibility_profile": borrowing_eligibility,
            "borrowing_liquidity_state": borrowing_liquidity_state,
            "borrowing_options": borrowing_options_payload,
            "borrowing_risk_summary": borrowing_risk_summary,
            "borrowing_pressure_summary": borrowing_pressure_summary,
            "borrowing_refresh": borrowing_refresh,
            "stock_market_day_used": stock_market_day_used,
            "worked_hours": worked_hours,
            "side_income_hours": float(side_income_hours),
            "side_income_wear_cost_xgp": float(side_income_wear_cost),
            "side_income_maintenance_cost_xgp": float(side_income_maintenance_cost),
            "total_hours_used": float(total_hours_used),
            "overtime_hours": float(overtime_hours),
            "sleep_hours": float(sleep_hours),
            "recovery_hours": float(recovery_hours),
            "productivity_modifier_before": float(life_productivity_before),
            "productivity_modifier": float(life_productivity_after),
            "burnout_risk": float(burnout_risk),
            "medical_event_risk": float(medical_event_risk),
            "medical_cost_xgp": float(medical_cost_xgp),
            "missed_work_penalty_xgp": float(missed_work_penalty_xgp),
            "life_summary": str(life_result.get("life_summary", "")),
            "time_budget_summary": str(life_result.get("time_budget_summary", "")),
            "life_debug_meta": life_result.get("debug_meta", {}),
            "personal_shock_summary": shock_result.get("short_summary"),
            "personal_shock_impacts": shock_impacts,
            "personal_shock_cash_impact_xgp": float(shock_cash_impact),
            "personal_shock_operational_delta_xgp": float(shock_operational_delta),
            "personal_shock_income_bonus_xgp": float(shock_income_bonus),
            "personal_shock_extra_expense_xgp": float(shock_extra_expense),
            "personal_shock_work_income_modifier": float(shock_work_income_modifier),
            "personal_shock_business_modifier": float(shock_business_modifier),
            "personal_shock_side_income_modifier": float(shock_side_income_modifier),
            "personal_shock_stress_delta": float(shock_stress_delta),
            "personal_shock_health_delta": float(shock_health_delta),
            "personal_shock_time_hours": float(shock_time_hours),
            "personal_shock_recent_event": shock_result.get("recent_event", {}),
            "personal_shock_recovery_state": shock_result.get("recovery_state", {}),
            "personal_shock_profile": shock_result.get("shock_profile", {}),
            "personal_shock_risk_state": shock_result.get("risk_state", {}),
            "personal_shock_practical_actions": shock_result.get("practical_current_actions", []),
            "personal_shock_debug_meta": shock_result.get("debug_meta", {}),
            "region": player.region,
            "business_summary": business_summary,
            "housing_region": housing_region,
            "housing_cost_xgp": float(housing_cost),
            "housing_cost_daily_xgp": float(housing_cost_daily),
            "utilities_cost_daily_xgp": float(utilities_cost_daily),
            "commute_hours": float(commute_hours),
            "commute_fuel_cost_xgp": float(commute_fuel_cost_xgp),
            "commute_pressure": float(commute_pressure),
            "housing_stress_delta": int(housing_stress_delta),
            "region_key": region_key,
            "region_stress_delta": float(region_stress_delta),
            "region_opportunity_modifier": float(region_opportunity_modifier),
            "region_business_demand_modifier": float(region_business_demand_modifier),
            "region_side_income_modifier": float(region_side_income_modifier),
            "networking_modifier": float(networking_modifier),
            "opportunity_quality_signal": float(opportunity_quality_signal),
            "opportunity_modifier": float(opportunity_modifier),
            "housing_region_summary": {
                "region_key": region_key,
                "housing_cost_daily_xgp": float(housing_cost_daily),
                "utilities_cost_daily_xgp": float(utilities_cost_daily),
                "commute_hours": float(commute_hours),
                "commute_fuel_cost_xgp": float(commute_fuel_cost_xgp),
                "region_stress_delta": float(region_stress_delta),
                "region_opportunity_modifier": float(region_opportunity_modifier),
                "region_business_demand_modifier": float(region_business_demand_modifier),
                "region_side_income_modifier": float(region_side_income_modifier),
                "networking_modifier": float(networking_modifier),
                "opportunity_quality_signal": float(opportunity_quality_signal),
            },
            "housing_log_idempotent": bool(housing_effect.get("already_processed", False)),
            "employment_status": employment_status,
            "employment_event": employment_event,
            "layoff_risk_pct": float(layoff_risk_pct),
            "promotion_chance_pct": float(promotion_chance_pct),
            "wage_adjustment_pct": float(wage_adjustment_pct),
            "monthly_pay_xgp_after_event": float(monthly_pay_after_event),
            "job_income_capture_factor": float(job_income_capture_factor),
            "career_progress_penalty_input": float(career_progress_penalty),
            "employment_job_code": getattr(employment, "current_job_code", None),
            "net_worth_xgp": net_worth_xgp,
            "total_assets_xgp": total_assets_xgp,
            "stock_market_value_xgp": stock_market_value_xgp,
            "business_value_xgp": business_value_xgp,
            "debt_xgp": debt_xgp,
            "allocation_json": allocation_json,
            "retention_summary": retention_summary,
        }

        log = DailySettlementLog(
            player_id=player.id,
            day_number=settled_day,
            hours_before_reset=hours_before,
            hours_after_reset=HOURS_RESET,
            stress_before=stress_before,
            stress_after=stress_after,
            health_before=health_before,
            health_after=health_after,
            cash_before=cash_before,
            cash_after=ending_cash,
            income_xgp=total_income,
            expenses_xgp=total_expense,
            side_income_net_xgp=side_income_net,
            business_revenue_xgp=business_revenue,
            business_cogs_xgp=business_cogs,
            business_overhead_xgp=business_overhead,
            business_spoilage_loss_xgp=business_spoilage_loss,
            business_fuel_cost_xgp=business_fuel_cost,
            business_maintenance_cost_xgp=business_maintenance_cost,
            business_net_profit_xgp=business_net,
            stock_pnl_xgp=_money(_d(getattr(pds, "stock_realized_pnl_xgp", 0))),
            debt_paid_xgp=debt_paid,
            debt_payment_due_xgp=debt_payment_due_xgp,
            debt_payment_paid_xgp=debt_payment_paid_xgp,
            debt_payment_missed=debt_payment_missed,
            late_fee_xgp=late_fee_xgp,
            accrued_interest_xgp=accrued_interest_xgp,
            credit_score_before=distress_credit_before,
            credit_score_after=distress_credit_after,
            credit_score_delta=distress_credit_delta,
            distress_state_before=distress_state_before,
            distress_state_after=distress_state_after,
            distress_score_before=distress_score_before,
            distress_score_after=distress_score_after,
            borrowing_cost_modifier=borrowing_cost_modifier,
            opportunity_access_penalty=opportunity_access_penalty,
            business_risk_penalty=business_risk_penalty,
            career_progress_penalty=career_progress_penalty,
            recovery_actions_applied_json=json.dumps(recovery_actions_applied, sort_keys=True),
            distress_driver_json=json.dumps(distress_driver_json, sort_keys=True),
            health_change=health_change,
            stress_change=stress_change,
            housing_region_id=housing_region or player.housing_region_id,
            housing_cost_paid=housing_cost,
            housing_stress_modifier=housing_stress_delta,
            region_key=region_key,
            housing_cost_daily_xgp=housing_cost_daily,
            utilities_cost_daily_xgp=utilities_cost_daily,
            commute_hours=commute_hours,
            commute_fuel_cost_xgp=commute_fuel_cost_xgp,
            region_stress_delta=region_stress_delta,
            region_opportunity_modifier=region_opportunity_modifier,
            region_business_demand_modifier=region_business_demand_modifier,
            region_side_income_modifier=region_side_income_modifier,
            networking_modifier=networking_modifier,
            opportunity_quality_signal=opportunity_quality_signal,
            side_income_hours=side_income_hours,
            total_hours_used=total_hours_used,
            overtime_hours=overtime_hours,
            sleep_hours=sleep_hours,
            recovery_hours=recovery_hours,
            productivity_modifier=life_productivity_after,
            burnout_risk=burnout_risk,
            medical_event_risk=medical_event_risk,
            medical_cost_xgp=medical_cost_xgp,
            missed_work_penalty_xgp=missed_work_penalty_xgp,
            summary_json=json.dumps(summary_payload),
        )
        db.add(log)
        db.flush()
        summary_payload["settlement_debug"] = {
            **(summary_payload.get("settlement_debug") or {}),
            "settlement_log_id": str(log.id),
            "settlement_day_number": int(settled_day),
        }
        log.summary_json = json.dumps(summary_payload)

        if _should_emit_settlement_audit_debug(player.id, settled_day):
            audit_payload = {
                "player_id": str(player.id),
                "settled_day": int(settled_day),
                "settlement_day_key": settlement_day_key,
                "settlement_already_existed_for_day": bool(existing_log is not None or existing_log_count > 0),
                "starting_cash": float(day_start_cash),
                "ending_cash": float(ending_cash),
                "total_income": float(total_income),
                "total_expense": float(total_expense),
                "net_change": float(net_change),
                "income_breakdown": income_breakdown_payload,
                "expense_breakdown": expense_breakdown_payload,
                "weekly_or_monthly_charge_flags": cadence_audit_payload,
                "settlement_log_id": str(log.id),
            }
            logger.warning("Settlement audit debug: %s", json.dumps(audit_payload, sort_keys=True))

        db.commit()

        return {
            "player_id": str(player.id),
            "settled_day": int(settled_day),
            "income_xgp": float(total_income),
            "expenses_xgp": float(total_expense),
            "total_income": float(total_income),
            "total_expense": float(total_expense),
            "net_change": float(net_change),
            "ending_cash": float(ending_cash),
            "income_breakdown": income_breakdown_payload,
            "expense_breakdown": expense_breakdown_payload,
            "settlement_breakdown": summary_payload.get("settlement_breakdown", {}),
            "settlement_debug": summary_payload.get("settlement_debug", {}),
            "side_income_net_xgp": float(side_income_net),
            "business_net_xgp": float(business_net),
            "stock_sale_income_xgp": float(stock_sale_income),
            "stock_fee_xgp": float(stock_fee),
            "business_revenue_xgp": float(business_revenue),
            "business_cogs_xgp": float(business_cogs),
            "business_overhead_xgp": float(business_overhead),
            "business_spoilage_loss_xgp": float(business_spoilage_loss),
            "business_fuel_cost_xgp": float(business_fuel_cost),
            "business_maintenance_cost_xgp": float(business_maintenance_cost),
            "business_net_profit_xgp": float(business_net),
            "total_business_profit_xgp": float(business_summary.get("total_business_profit_xgp", 0)),
            "business_count_run": business_count_run,
            "debt_paid_xgp": float(debt_paid),
            "debt_payment_due_xgp": float(debt_payment_due_xgp),
            "debt_payment_paid_xgp": float(debt_payment_paid_xgp),
            "debt_payment_missed": bool(debt_payment_missed),
            "late_fee_xgp": float(late_fee_xgp),
            "accrued_interest_xgp": float(accrued_interest_xgp),
            "weekly_gas_expense_xgp": float(weekly_gas_expense),
            "opening_debt_xgp": float(debt_before),
            "payment_due_xgp": float(payment_due),
            "payment_made_xgp": float(debt_paid),
            "interest_added_xgp": float(interest_added),
            "ending_debt_xgp": float(ending_debt),
            "payment_status": payment_status,
            "opening_credit_score": int(distress_credit_before),
            "credit_score_change": int(distress_credit_delta),
            "ending_credit_score": int(distress_credit_after),
            "delinquency_flag": bool(delinquency_flag),
            "distress_state_before": distress_state_before,
            "distress_state_after": distress_state_after,
            "distress_score_before": float(distress_score_before),
            "distress_score_after": float(distress_score_after),
            "borrowing_cost_modifier": float(borrowing_cost_modifier),
            "opportunity_access_penalty": float(opportunity_access_penalty),
            "business_risk_penalty": float(business_risk_penalty),
            "career_progress_penalty": float(career_progress_penalty),
            "recovery_actions_applied": recovery_actions_applied,
            "financial_distress_summary": financial_distress_summary,
            "financial_survival_summary": financial_survival_summary,
            "required_monthly_obligation_xgp": float(financial_survival_required_monthly_obligation_xgp),
            "required_daily_burden_xgp": float(financial_survival_required_daily_burden_xgp),
            "obligation_load_ratio": float(financial_survival_obligation_load_ratio),
            "liquidity_buffer_days": float(financial_survival_liquidity_buffer_days),
            "payment_pressure_label": financial_survival_payment_pressure_label,
            "current_delinquency_stage": financial_survival_current_delinquency_stage,
            "survival_status_label": financial_survival_survival_status_label,
            "financial_survival_payment_outcome": financial_survival_payment_outcome,
            "financial_survival_late_fee_xgp": float(financial_survival_late_fee_xgp),
            "financial_survival_late_fee_non_debt_xgp": float(financial_survival_late_fee_non_debt_xgp),
            "financial_survival_additional_required_paid_xgp": float(
                financial_survival_additional_required_paid_xgp
            ),
            "financial_survival_credit_score_before": int(financial_survival_credit_before),
            "financial_survival_credit_score_after": int(financial_survival_credit_after),
            "financial_survival_credit_score_delta": int(financial_survival_credit_delta),
            "financial_survival_stress_impact_delta": float(financial_survival_stress_impact_delta),
            "financial_survival_practical_actions": financial_survival_practical_actions,
            "borrowing_eligibility_profile": borrowing_eligibility,
            "borrowing_liquidity_state": borrowing_liquidity_state,
            "borrowing_options": borrowing_options_payload,
            "borrowing_risk_summary": borrowing_risk_summary,
            "borrowing_pressure_summary": borrowing_pressure_summary,
            "borrowing_refresh": borrowing_refresh,
            "ending_cash_xgp": float(ending_cash),
            "health_change": int(health_change),
            "stress_change": int(stress_change),
            "total_hours_used": float(total_hours_used),
            "overtime_hours": float(overtime_hours),
            "sleep_hours": float(sleep_hours),
            "recovery_hours": float(recovery_hours),
            "stress_before": int(stress_before),
            "stress_after": int(stress_after),
            "health_before": int(health_before),
            "health_after": int(health_after),
            "productivity_modifier": float(life_productivity_after),
            "productivity_modifier_before": float(life_productivity_before),
            "burnout_risk": float(burnout_risk),
            "medical_event_risk": float(medical_event_risk),
            "medical_cost_xgp": float(medical_cost_xgp),
            "missed_work_penalty_xgp": float(missed_work_penalty_xgp),
            "life_summary": str(life_result.get("life_summary", "")),
            "time_budget_summary": str(life_result.get("time_budget_summary", "")),
            "personal_shock_summary": shock_result.get("short_summary"),
            "personal_shock_impacts": shock_impacts,
            "personal_shock_cash_impact_xgp": float(shock_cash_impact),
            "personal_shock_operational_delta_xgp": float(shock_operational_delta),
            "personal_shock_income_bonus_xgp": float(shock_income_bonus),
            "personal_shock_extra_expense_xgp": float(shock_extra_expense),
            "personal_shock_work_income_modifier": float(shock_work_income_modifier),
            "personal_shock_business_modifier": float(shock_business_modifier),
            "personal_shock_side_income_modifier": float(shock_side_income_modifier),
            "personal_shock_stress_delta": float(shock_stress_delta),
            "personal_shock_health_delta": float(shock_health_delta),
            "personal_shock_time_hours": float(shock_time_hours),
            "personal_shock_recent_event": shock_result.get("recent_event", {}),
            "personal_shock_recovery_state": shock_result.get("recovery_state", {}),
            "personal_shock_profile": shock_result.get("shock_profile", {}),
            "personal_shock_risk_state": shock_result.get("risk_state", {}),
            "personal_shock_practical_actions": shock_result.get("practical_current_actions", []),
            "personal_shock_debug_meta": shock_result.get("debug_meta", {}),
            "stock_market_day_used": stock_market_day_used,
            "housing_region": housing_region,
            "housing_cost_xgp": float(housing_cost),
            "housing_cost_daily_xgp": float(housing_cost_daily),
            "utilities_cost_daily_xgp": float(utilities_cost_daily),
            "commute_hours": float(commute_hours),
            "commute_fuel_cost_xgp": float(commute_fuel_cost_xgp),
            "commute_pressure": float(commute_pressure),
            "housing_stress_delta": int(housing_stress_delta),
            "region_key": region_key,
            "region_stress_delta": float(region_stress_delta),
            "region_opportunity_modifier": float(region_opportunity_modifier),
            "region_business_demand_modifier": float(region_business_demand_modifier),
            "region_side_income_modifier": float(region_side_income_modifier),
            "networking_modifier": float(networking_modifier),
            "opportunity_quality_signal": float(opportunity_quality_signal),
            "opportunity_modifier": float(opportunity_modifier),
            "housing_region_summary": summary_payload.get("housing_region_summary", {}),
            "employment_status": employment_status,
            "employment_event": employment_event,
            "layoff_risk_pct": float(layoff_risk_pct),
            "promotion_chance_pct": float(promotion_chance_pct),
            "wage_adjustment_pct": float(wage_adjustment_pct),
            "monthly_pay_xgp_after_event": float(monthly_pay_after_event),
            "job_income_capture_factor": float(job_income_capture_factor),
            "essentials_spend_xgp": float(essentials_spend),
            "protein_spend_xgp": float(protein_spend),
            "produce_spend_xgp": float(produce_spend),
            "convenience_spend_xgp": float(convenience_spend),
            "total_basket_spend_xgp": float(basket_spend),
            "budget_pressure_score": float(budget_pressure_score),
            "stress_spend_modifier": float(stress_spend_modifier),
            "nutrition_pressure_score": float(nutrition_pressure_score),
            "net_worth_xgp": net_worth_xgp,
            "total_assets_xgp": total_assets_xgp,
            "stock_market_value_xgp": stock_market_value_xgp,
            "business_value_xgp": business_value_xgp,
            "debt_xgp": debt_xgp,
            "allocation_json": allocation_json,
            "retention_summary": retention_summary,
            "summary_json": summary_payload,
        }
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise DailySettlementError("Unexpected settlement error.") from exc


def get_latest_settlement_summary(db: Session, player_id: str | UUID) -> dict:
    player = _resolve_player(db, player_id)
    log = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == player.id)
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    if log is None:
        raise SettlementNotFoundError("No settlement log found for player.")

    try:
        summary_payload = json.loads(log.summary_json or "{}")
    except Exception:
        summary_payload = {}

    return {
        "player_id": str(player.id),
        "day_number": int(log.day_number),
        "income_xgp": float(log.income_xgp),
        "expenses_xgp": float(log.expenses_xgp),
        "total_income": float(summary_payload.get("total_income_xgp", _money(_d(log.income_xgp)))),
        "total_expense": float(summary_payload.get("total_expense_xgp", _money(_d(log.expenses_xgp)))),
        "net_change": float(
            summary_payload.get(
                "net_change_xgp",
                _money(_d(getattr(log, "cash_after", 0)) - _d(summary_payload.get("starting_cash_xgp", getattr(log, "cash_before", 0)))),
            )
        ),
        "ending_cash": float(_money(_d(getattr(log, "ending_cash_xgp", getattr(log, "cash_after", 0))))),
        "income_breakdown": (
            ((summary_payload.get("settlement_breakdown") or {}).get("income_breakdown") or {})
        ),
        "expense_breakdown": (
            ((summary_payload.get("settlement_breakdown") or {}).get("expense_breakdown") or {})
        ),
        "settlement_breakdown": summary_payload.get("settlement_breakdown", {}),
        "settlement_debug": summary_payload.get("settlement_debug", {}),
        "guided_day_number": int(summary_payload.get("guided_day_number", 0) or 0),
        "guided_learning_title": summary_payload.get("guided_learning_title"),
        "guided_earned_summary": summary_payload.get("guided_earned_summary"),
        "guided_spent_summary": summary_payload.get("guided_spent_summary"),
        "guided_change_summary": summary_payload.get("guided_change_summary"),
        "guided_watch_tomorrow": summary_payload.get("guided_watch_tomorrow"),
        "side_income_net_xgp": float(log.side_income_net_xgp),
        "business_net_xgp": float(summary_payload.get("business_net_xgp", 0.0)),
        "stock_sale_income_xgp": float(summary_payload.get("stock_sale_income_xgp", 0.0)),
        "stock_fee_xgp": float(summary_payload.get("stock_fee_xgp", 0.0)),
        "business_revenue_xgp": float(summary_payload.get("business_revenue_xgp", 0.0)),
        "business_cogs_xgp": float(summary_payload.get("business_cogs_xgp", 0.0)),
        "business_overhead_xgp": float(summary_payload.get("business_overhead_xgp", 0.0)),
        "business_spoilage_loss_xgp": float(summary_payload.get("business_spoilage_loss_xgp", 0.0)),
        "business_fuel_cost_xgp": float(summary_payload.get("business_fuel_cost_xgp", 0.0)),
        "business_maintenance_cost_xgp": float(summary_payload.get("business_maintenance_cost_xgp", 0.0)),
        "business_net_profit_xgp": float(summary_payload.get("business_net_profit_xgp", 0.0)),
        "total_business_profit_xgp": float(summary_payload.get("total_business_profit_xgp", 0.0)),
        "business_count_run": int(summary_payload.get("business_count_run", 0)),
        "debt_paid_xgp": float(log.debt_paid_xgp),
        "debt_payment_due_xgp": float(
            summary_payload.get("debt_payment_due_xgp", _money(_d(getattr(log, "debt_payment_due_xgp", 0))))
        ),
        "debt_payment_paid_xgp": float(
            summary_payload.get("debt_payment_paid_xgp", _money(_d(getattr(log, "debt_payment_paid_xgp", 0))))
        ),
        "debt_payment_missed": bool(
            summary_payload.get("debt_payment_missed", bool(getattr(log, "debt_payment_missed", False)))
        ),
        "late_fee_xgp": float(
            summary_payload.get("late_fee_xgp", _money(_d(getattr(log, "late_fee_xgp", 0))))
        ),
        "accrued_interest_xgp": float(
            summary_payload.get("accrued_interest_xgp", _money(_d(getattr(log, "accrued_interest_xgp", 0))))
        ),
        "weekly_gas_expense_xgp": float(summary_payload.get("weekly_gas_expense_xgp", 0.0)),
        "opening_debt_xgp": float(summary_payload.get("opening_debt_xgp", 0.0)),
        "payment_due_xgp": float(summary_payload.get("payment_due_xgp", 0.0)),
        "payment_made_xgp": float(summary_payload.get("payment_made_xgp", summary_payload.get("debt_paid_xgp", 0.0))),
        "interest_added_xgp": float(summary_payload.get("interest_added_xgp", 0.0)),
        "ending_debt_xgp": float(summary_payload.get("ending_debt_xgp", 0.0)),
        "payment_status": summary_payload.get("payment_status"),
        "opening_credit_score": int(summary_payload.get("opening_credit_score", getattr(log, "credit_score_before", 650))),
        "credit_score_change": int(summary_payload.get("credit_score_change", getattr(log, "credit_score_delta", 0))),
        "ending_credit_score": int(summary_payload.get("ending_credit_score", getattr(log, "credit_score_after", 650))),
        "delinquency_flag": bool(summary_payload.get("delinquency_flag", False)),
        "distress_state_before": summary_payload.get("distress_state_before", getattr(log, "distress_state_before", "stable")),
        "distress_state_after": summary_payload.get("distress_state_after", getattr(log, "distress_state_after", "stable")),
        "distress_score_before": float(
            summary_payload.get("distress_score_before", _q4(_d(getattr(log, "distress_score_before", 0))))
        ),
        "distress_score_after": float(
            summary_payload.get("distress_score_after", _q4(_d(getattr(log, "distress_score_after", 0))))
        ),
        "borrowing_cost_modifier": float(
            summary_payload.get("borrowing_cost_modifier", _q4(_d(getattr(log, "borrowing_cost_modifier", 1))))
        ),
        "opportunity_access_penalty": float(
            summary_payload.get("opportunity_access_penalty", _q4(_d(getattr(log, "opportunity_access_penalty", 0))))
        ),
        "business_risk_penalty": float(
            summary_payload.get("business_risk_penalty", _q4(_d(getattr(log, "business_risk_penalty", 0))))
        ),
        "career_progress_penalty": float(
            summary_payload.get("career_progress_penalty", _q4(_d(getattr(log, "career_progress_penalty", 0))))
        ),
        "recovery_actions_applied": summary_payload.get("recovery_actions_applied", []),
        "financial_distress_summary": summary_payload.get("financial_distress_summary", {}),
        "financial_survival_summary": summary_payload.get("financial_survival_summary", {}),
        "required_monthly_obligation_xgp": float(summary_payload.get("required_monthly_obligation_xgp", 0.0)),
        "required_daily_burden_xgp": float(summary_payload.get("required_daily_burden_xgp", 0.0)),
        "obligation_load_ratio": float(summary_payload.get("obligation_load_ratio", 0.0)),
        "liquidity_buffer_days": float(summary_payload.get("liquidity_buffer_days", 0.0)),
        "payment_pressure_label": summary_payload.get("payment_pressure_label", "manageable"),
        "current_delinquency_stage": summary_payload.get("current_delinquency_stage", "current"),
        "survival_status_label": summary_payload.get("survival_status_label", "current"),
        "financial_survival_payment_outcome": summary_payload.get(
            "financial_survival_payment_outcome", "paid_full"
        ),
        "financial_survival_late_fee_xgp": float(summary_payload.get("financial_survival_late_fee_xgp", 0.0)),
        "financial_survival_late_fee_non_debt_xgp": float(
            summary_payload.get("financial_survival_late_fee_non_debt_xgp", 0.0)
        ),
        "financial_survival_additional_required_paid_xgp": float(
            summary_payload.get("financial_survival_additional_required_paid_xgp", 0.0)
        ),
        "financial_survival_credit_score_before": int(
            summary_payload.get("financial_survival_credit_score_before", getattr(log, "credit_score_before", 650))
        ),
        "financial_survival_credit_score_after": int(
            summary_payload.get("financial_survival_credit_score_after", getattr(log, "credit_score_after", 650))
        ),
        "financial_survival_credit_score_delta": int(
            summary_payload.get("financial_survival_credit_score_delta", getattr(log, "credit_score_delta", 0))
        ),
        "financial_survival_stress_impact_delta": float(
            summary_payload.get("financial_survival_stress_impact_delta", 0.0)
        ),
        "financial_survival_practical_actions": summary_payload.get(
            "financial_survival_practical_actions", []
        ),
        "borrowing_eligibility_profile": summary_payload.get("borrowing_eligibility_profile", {}),
        "borrowing_liquidity_state": summary_payload.get("borrowing_liquidity_state", {}),
        "borrowing_options": summary_payload.get("borrowing_options", {"items": []}),
        "borrowing_risk_summary": summary_payload.get("borrowing_risk_summary", {}),
        "borrowing_pressure_summary": summary_payload.get("borrowing_pressure_summary", {}),
        "borrowing_refresh": summary_payload.get("borrowing_refresh", {}),
        "ending_cash_xgp": float(log.ending_cash_xgp),
        "health_change": int(log.health_change),
        "stress_change": int(log.stress_change),
        "total_hours_used": float(_q4(_d(getattr(log, "total_hours_used", 0)))),
        "overtime_hours": float(_q4(_d(getattr(log, "overtime_hours", 0)))),
        "sleep_hours": float(_q4(_d(getattr(log, "sleep_hours", 0)))),
        "recovery_hours": float(_q4(_d(getattr(log, "recovery_hours", 0)))),
        "stress_before": int(log.stress_before),
        "stress_after": int(log.stress_after),
        "health_before": int(log.health_before),
        "health_after": int(log.health_after),
        "productivity_modifier": float(_q4(_d(getattr(log, "productivity_modifier", summary_payload.get("productivity_modifier", 1.0))))),
        "burnout_risk": float(_q4(_d(getattr(log, "burnout_risk", summary_payload.get("burnout_risk", 0.0))))),
        "medical_event_risk": float(_q4(_d(getattr(log, "medical_event_risk", summary_payload.get("medical_event_risk", 0.0))))),
        "medical_cost_xgp": float(_money(_d(getattr(log, "medical_cost_xgp", summary_payload.get("medical_cost_xgp", 0.0))))),
        "missed_work_penalty_xgp": float(
            _money(_d(getattr(log, "missed_work_penalty_xgp", summary_payload.get("missed_work_penalty_xgp", 0.0))))
        ),
        "life_summary": summary_payload.get("life_summary"),
        "time_budget_summary": summary_payload.get("time_budget_summary"),
        "personal_shock_summary": summary_payload.get("personal_shock_summary"),
        "personal_shock_impacts": summary_payload.get("personal_shock_impacts", {}),
        "personal_shock_cash_impact_xgp": float(summary_payload.get("personal_shock_cash_impact_xgp", 0.0)),
        "personal_shock_operational_delta_xgp": float(
            summary_payload.get("personal_shock_operational_delta_xgp", 0.0)
        ),
        "personal_shock_income_bonus_xgp": float(summary_payload.get("personal_shock_income_bonus_xgp", 0.0)),
        "personal_shock_extra_expense_xgp": float(summary_payload.get("personal_shock_extra_expense_xgp", 0.0)),
        "personal_shock_work_income_modifier": float(
            summary_payload.get("personal_shock_work_income_modifier", 1.0)
        ),
        "personal_shock_business_modifier": float(summary_payload.get("personal_shock_business_modifier", 1.0)),
        "personal_shock_side_income_modifier": float(
            summary_payload.get("personal_shock_side_income_modifier", 1.0)
        ),
        "personal_shock_stress_delta": float(summary_payload.get("personal_shock_stress_delta", 0.0)),
        "personal_shock_health_delta": float(summary_payload.get("personal_shock_health_delta", 0.0)),
        "personal_shock_time_hours": float(summary_payload.get("personal_shock_time_hours", 0.0)),
        "personal_shock_recent_event": summary_payload.get("personal_shock_recent_event", {}),
        "personal_shock_recovery_state": summary_payload.get("personal_shock_recovery_state", {}),
        "personal_shock_profile": summary_payload.get("personal_shock_profile", {}),
        "personal_shock_risk_state": summary_payload.get("personal_shock_risk_state", {}),
        "personal_shock_practical_actions": summary_payload.get("personal_shock_practical_actions", []),
        "personal_shock_debug_meta": summary_payload.get("personal_shock_debug_meta", {}),
        "housing_region": summary_payload.get("housing_region"),
        "housing_cost_xgp": float(summary_payload.get("housing_cost_xgp", 0.0)),
        "housing_cost_daily_xgp": float(
            summary_payload.get("housing_cost_daily_xgp", _money(_d(getattr(log, "housing_cost_daily_xgp", 0))))
        ),
        "utilities_cost_daily_xgp": float(
            summary_payload.get("utilities_cost_daily_xgp", _money(_d(getattr(log, "utilities_cost_daily_xgp", 0))))
        ),
        "commute_hours": float(
            summary_payload.get("commute_hours", _q4(_d(getattr(log, "commute_hours", 0))))
        ),
        "commute_fuel_cost_xgp": float(
            summary_payload.get("commute_fuel_cost_xgp", _money(_d(getattr(log, "commute_fuel_cost_xgp", 0))))
        ),
        "commute_pressure": float(summary_payload.get("commute_pressure", 0.0)),
        "housing_stress_delta": int(summary_payload.get("housing_stress_delta", 0)),
        "region_key": summary_payload.get("region_key", getattr(log, "region_key", None)),
        "region_stress_delta": float(
            summary_payload.get("region_stress_delta", _q4(_d(getattr(log, "region_stress_delta", 0))))
        ),
        "region_opportunity_modifier": float(
            summary_payload.get("region_opportunity_modifier", _q4(_d(getattr(log, "region_opportunity_modifier", 0))))
        ),
        "region_business_demand_modifier": float(
            summary_payload.get("region_business_demand_modifier", _q4(_d(getattr(log, "region_business_demand_modifier", 0))))
        ),
        "region_side_income_modifier": float(
            summary_payload.get("region_side_income_modifier", _q4(_d(getattr(log, "region_side_income_modifier", 0))))
        ),
        "networking_modifier": float(
            summary_payload.get("networking_modifier", _q4(_d(getattr(log, "networking_modifier", 0))))
        ),
        "opportunity_quality_signal": float(
            summary_payload.get("opportunity_quality_signal", _q4(_d(getattr(log, "opportunity_quality_signal", 1))))
        ),
        "opportunity_modifier": float(summary_payload.get("opportunity_modifier", 1.0)),
        "housing_region_summary": summary_payload.get("housing_region_summary", {}),
        "employment_status": summary_payload.get("employment_status"),
        "employment_event": summary_payload.get("employment_event"),
        "layoff_risk_pct": float(summary_payload.get("layoff_risk_pct", 0.0)),
        "promotion_chance_pct": float(summary_payload.get("promotion_chance_pct", 0.0)),
        "wage_adjustment_pct": float(summary_payload.get("wage_adjustment_pct", 0.0)),
        "monthly_pay_xgp_after_event": float(summary_payload.get("monthly_pay_xgp_after_event", 0.0)),
        "net_worth_xgp": float(summary_payload.get("net_worth_xgp", 0.0)),
        "total_assets_xgp": float(summary_payload.get("total_assets_xgp", 0.0)),
        "stock_market_value_xgp": float(summary_payload.get("stock_market_value_xgp", 0.0)),
        "business_value_xgp": float(summary_payload.get("business_value_xgp", 0.0)),
        "debt_xgp": float(summary_payload.get("debt_xgp", 0.0)),
        "allocation_json": summary_payload.get("allocation_json", {}),
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "retention_summary": summary_payload.get("retention_summary", {}),
        "summary_json": summary_payload,
    }
