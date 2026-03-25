"""Ride share side-income engine (Step 8).

Economic design:
  - Ride share is a flexible emergency income tool, not a salary replacement.
  - Players trade remaining daily time and wellbeing for immediate XGP.
  - Fuel cost is linked to macro oil conditions, so profitability is dynamic.
  - Every cash movement is ledger-backed for full auditability.
"""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.engine.daily_engine import get_or_create_game_state
from app.engine.housing_region_service import get_side_income_region_modifier
from app.engine.macro_engine import get_or_create_macro_state_for_day
from app.engine.side_income_service import compute_rideshare_shift
from app.models.contribution_event import ContributionEvent
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.side_income_action import SideIncomeAction
from app.models.xgp_transaction import XGPTransaction
from app.services.player_transaction_log_service import record_player_transaction

RIDESHARE_TYPE = "ride_share"
MAX_RIDESHARE_HOURS_PER_DAY = 6


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _get_or_create_player_daily_state_in_txn(
    db: Session,
    player: Player,
    day_number: int,
) -> PlayerDailyState:
    """Get/create PlayerDailyState without committing (for atomic actions)."""
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == day_number,
        )
        .first()
    )
    if pds is None:
        cash_value = round(float(player.cash or 0), 4)
        pds = PlayerDailyState(
            player_id=player.id,
            day_number=day_number,
            hours_available_start=int(player.hours_available),
            hours_available_end=int(player.hours_available),
            worked_main_job=False,
            did_settlement=False,
            stress_start=int(player.stress),
            stress_end=int(player.stress),
            health_start=int(player.health),
            health_end=int(player.health),
            cash_start=cash_value,
            cash_end=cash_value,
            side_income_hours=0,
            side_income_gross_xgp=0,
            side_income_fuel_cost_xgp=0,
            side_income_net_xgp=0,
        )
        db.add(pds)
        db.flush()
    return pds


def get_current_oil_index(db: Session, day_number: int) -> float:
    """Return the active oil index for an in-game day (auto-seeded if missing)."""
    macro = get_or_create_macro_state_for_day(db, day_number)
    return round(float(macro.oil_index or 100.0), 4)


def calculate_rideshare_gross_income(
    hours_worked: float,
    demand_multiplier: float = 1.0,
) -> float:
    """Gross ride-share earnings for a shift."""
    base_rate_per_hour = 18.0
    gross = float(hours_worked) * base_rate_per_hour * float(demand_multiplier)
    return round(max(0.0, gross), 2)


def calculate_rideshare_fuel_cost(hours_worked: float, oil_index: float) -> float:
    """Fuel cost driven by oil pressure (100 index = baseline fuel cost)."""
    hourly_fuel_at_baseline = 2.5
    hourly_cost = hourly_fuel_at_baseline * (float(oil_index) / 100.0)
    total_cost = hourly_cost * float(hours_worked)
    return round(max(0.0, total_cost), 2)


def calculate_rideshare_stress_change(hours_worked: float) -> int:
    """Stress gain from side-shift workload."""
    stress = 1 + round(float(hours_worked) * 0.75)
    return max(1, int(stress))


def calculate_rideshare_health_change(hours_worked: float) -> int:
    """Small health pressure for long side shifts."""
    hrs = float(hours_worked)
    if hrs < 4:
        return 0
    if hrs < 8:
        return -1
    return -2


def validate_rideshare_action(
    hours_requested: float,
    hours_available: int,
    max_side_income_hours_per_day: int = 6,
) -> tuple[bool, str | None]:
    """Validate anti-exploit constraints before DB mutation."""
    if float(hours_requested) <= 0:
        return False, "hours_requested must be greater than 0."

    # Player daily clock currently uses integer hours across the backend.
    if not float(hours_requested).is_integer():
        return False, "Ride share currently supports whole-hour shifts only."

    if float(hours_requested) > float(hours_available):
        return (
            False,
            f"Not enough available time. Requested {hours_requested}h, "
            f"but only {hours_available}h remaining.",
        )

    if float(hours_requested) > float(max_side_income_hours_per_day):
        return (
            False,
            f"Ride share is capped at {max_side_income_hours_per_day} hours per day.",
        )

    return True, None


def process_rideshare_action(db: Session, player: Player, hours_worked: float) -> dict:
    """Process one ride-share side-income action atomically.

    This is the first flexible labor-response mechanic:
    players can hustle extra XGP when finances are tight, but it costs time,
    stress, and occasionally health.
    """
    try:
        game_state = get_or_create_game_state(db)
        current_day = int(game_state.current_day)

        # Keep daily work counters aligned to this in-game day so the job engine
        # does not later reset hours and erase side-income time consumption.
        if player.last_worked_day != current_day:
            player.main_job_hours_today = 0
            player.side_job_hours_today = 0
            player.total_hours_worked_today = 0
            player.work_actions_today = 0

        pds = _get_or_create_player_daily_state_in_txn(db, player, current_day)

        side_income_hours_today = int(float(getattr(pds, "side_income_hours", 0) or 0))
        remaining_side_cap = max(0, MAX_RIDESHARE_HOURS_PER_DAY - side_income_hours_today)
        hours_available_for_action = min(int(player.hours_available or 0), remaining_side_cap)

        valid, reason = validate_rideshare_action(
            hours_requested=hours_worked,
            hours_available=hours_available_for_action,
            max_side_income_hours_per_day=MAX_RIDESHARE_HOURS_PER_DAY,
        )
        if not valid:
            raise ValueError(reason or "Invalid ride-share action.")

        hours_worked_int = int(hours_worked)
        macro = get_or_create_macro_state_for_day(db, current_day)
        oil_index = round(float(macro.oil_index or 100.0), 4)
        confidence = Decimal(str(getattr(macro, "consumer_confidence", 50) or 50))
        unemployment = Decimal(str(getattr(macro, "unemployment_rate", 5) or 5))
        reliability_before = Decimal(str(getattr(player, "rideshare_reliability", 0.95) or 0.95))
        region = (player.region or "suburban").strip().lower()
        try:
            region_side_income_modifier = get_side_income_region_modifier(db, player.id)
        except Exception:
            # Backward-compat fallback for test fixtures/DBs missing housing tables.
            region_side_income_modifier = Decimal("1.0000")

        hours_before = int(player.hours_available or 0)
        balance_before = round(float(player.cash or 0), 4)
        stress_before = int(player.stress or 0)
        health_before = int(player.health or 0)

        shift = compute_rideshare_shift(
            player_seed=str(player.id),
            day_number=current_day,
            region_key=region,
            hours_worked=hours_worked_int,
            oil_index=Decimal(str(oil_index)),
            consumer_confidence=confidence,
            unemployment_rate=unemployment,
            reliability=reliability_before,
            productivity_modifier=Decimal(str(getattr(player, "productivity_modifier", 1.0) or 1.0)),
            region_side_income_modifier=region_side_income_modifier,
            opportunity_access_penalty=Decimal(str(getattr(player, "opportunity_access_penalty", 0.0) or 0.0)),
        )

        gross_income_xgp = round(float(shift["gross_income_xgp"]), 2)
        fuel_cost_xgp = round(float(shift["gas_cost_xgp"]), 2)
        wear_cost_xgp = round(float(shift["wear_cost_xgp"]), 2)
        maintenance_cost_xgp = round(float(shift["maintenance_cost_xgp"]), 2)
        net_income_xgp = round(float(shift["net_income_xgp"]), 2)

        stress_change = calculate_rideshare_stress_change(hours_worked_int)
        health_change = calculate_rideshare_health_change(hours_worked_int)

        hours_after = _clamp_int(hours_before - hours_worked_int, 0, 24)
        balance_after_gross = round(balance_before + gross_income_xgp, 4)
        balance_after_fuel = round(balance_after_gross - fuel_cost_xgp, 4)
        balance_after_wear = round(balance_after_fuel - wear_cost_xgp, 4)
        balance_after = round(balance_after_wear - maintenance_cost_xgp, 4)

        player.cash = balance_after
        player.stress = _clamp_int(stress_before + stress_change, 0, 100)
        player.health = _clamp_int(health_before + health_change, 0, 100)
        player.hours_available = hours_after
        player.last_worked_day = current_day
        player.rideshare_reliability = float(shift["reliability_after"])

        action = SideIncomeAction(
            player_id=player.id,
            day_number=current_day,
            side_income_type=RIDESHARE_TYPE,
            hours_worked=float(hours_worked_int),
            gross_income_xgp=round(gross_income_xgp, 4),
            fuel_cost_xgp=round(fuel_cost_xgp, 4),
            wear_cost_xgp=round(wear_cost_xgp, 4),
            maintenance_cost_xgp=round(maintenance_cost_xgp, 4),
            net_income_xgp=round(net_income_xgp, 4),
            stress_change=stress_change,
            health_change=health_change,
            hours_before=hours_before,
            hours_after=hours_after,
            oil_index_used=oil_index,
            demand_multiplier=float(shift["demand_multiplier"]),
            gross_per_hour_xgp=float(shift["gross_per_hour_xgp"]),
            gas_price_per_unit_xgp=float(shift["gas_price_xgp"]),
            wear_cost_per_hour_xgp=float(shift["wear_cost_per_hour_xgp"]),
            net_per_hour_xgp=float(shift["net_per_hour_xgp"]),
            reliability_before=float(shift["reliability_before"]),
            reliability_after=float(shift["reliability_after"]),
        )
        db.add(action)
        db.flush()

        gross_txn = XGPTransaction(
            player_id=player.id,
            transaction_type="rideshare_income",
            direction="in",
            amount=round(gross_income_xgp, 4),
            balance_before=balance_before,
            balance_after=balance_after_gross,
            reference_type="side_income_action",
            reference_id=str(action.id),
            description="Ride share gross income",
        )
        db.add(gross_txn)

        fuel_txn = XGPTransaction(
            player_id=player.id,
            transaction_type="rideshare_fuel_cost",
            direction="out",
            amount=round(fuel_cost_xgp, 4),
            balance_before=balance_after_gross,
            balance_after=balance_after_fuel,
            reference_type="side_income_action",
            reference_id=str(action.id),
            description="Ride share fuel cost",
        )
        db.add(fuel_txn)

        wear_txn = XGPTransaction(
            player_id=player.id,
            transaction_type="rideshare_wear_cost",
            direction="out",
            amount=round(wear_cost_xgp, 4),
            balance_before=balance_after_fuel,
            balance_after=balance_after_wear,
            reference_type="side_income_action",
            reference_id=str(action.id),
            description="Ride share vehicle wear cost",
        )
        db.add(wear_txn)

        if maintenance_cost_xgp > 0:
            maint_txn = XGPTransaction(
                player_id=player.id,
                transaction_type="rideshare_maintenance_cost",
                direction="out",
                amount=round(maintenance_cost_xgp, 4),
                balance_before=balance_after_wear,
                balance_after=balance_after,
                reference_type="side_income_action",
                reference_id=str(action.id),
                description="Ride share maintenance event cost",
            )
            db.add(maint_txn)

        record_player_transaction(
            db,
            player=player,
            day=current_day,
            transaction_type="side_income",
            category="work",
            quantity=hours_worked_int,
            unit_price=round(float(shift["gross_per_hour_xgp"]), 4),
            gross_amount=round(gross_income_xgp, 4),
            fee_amount=round(fuel_cost_xgp + wear_cost_xgp + maintenance_cost_xgp, 4),
            net_cash_delta=round(net_income_xgp, 4),
            resulting_cash_balance=balance_after,
            metadata={
                "mode": RIDESHARE_TYPE,
                "fuel_cost_xgp": round(fuel_cost_xgp, 4),
                "wear_cost_xgp": round(wear_cost_xgp, 4),
                "maintenance_cost_xgp": round(maintenance_cost_xgp, 4),
                "demand_multiplier": float(shift["demand_multiplier"]),
                "oil_index_used": oil_index,
            },
        )

        contribution = ContributionEvent(
            player_id=player.id,
            event_type="ride_share",
            xgp_value=round(net_income_xgp, 4),
            event_units=float(hours_worked_int),
            metadata_json=json.dumps(
                {
                    "side_income_type": RIDESHARE_TYPE,
                    "gross_income_xgp": round(gross_income_xgp, 4),
                    "fuel_cost_xgp": round(fuel_cost_xgp, 4),
                    "wear_cost_xgp": round(wear_cost_xgp, 4),
                    "maintenance_cost_xgp": round(maintenance_cost_xgp, 4),
                    "oil_index_used": oil_index,
                    "demand_multiplier": float(shift["demand_multiplier"]),
                    "labor_efficiency_modifier": float(shift["labor_efficiency_modifier"]),
                    "productivity_modifier": float(shift["productivity_modifier"]),
                    "region_side_income_modifier": float(shift["region_side_income_modifier"]),
                    "opportunity_access_penalty": float(shift["opportunity_access_penalty"]),
                    "financial_access_factor": float(shift["financial_access_factor"]),
                    "maintenance_triggered": bool(shift["maintenance_triggered"]),
                    "day_number": current_day,
                }
            ),
        )
        db.add(contribution)

        pds.side_income_hours = round(float(getattr(pds, "side_income_hours", 0) or 0) + hours_worked_int, 4)
        pds.side_income_gross_xgp = round(
            float(getattr(pds, "side_income_gross_xgp", 0) or 0) + gross_income_xgp, 4
        )
        pds.side_income_fuel_cost_xgp = round(
            float(getattr(pds, "side_income_fuel_cost_xgp", 0) or 0) + fuel_cost_xgp, 4
        )
        pds.side_income_wear_cost_xgp = round(
            float(getattr(pds, "side_income_wear_cost_xgp", 0) or 0) + wear_cost_xgp, 4
        )
        pds.side_income_maintenance_cost_xgp = round(
            float(getattr(pds, "side_income_maintenance_cost_xgp", 0) or 0) + maintenance_cost_xgp, 4
        )
        pds.side_income_net_xgp = round(
            float(getattr(pds, "side_income_net_xgp", 0) or 0) + net_income_xgp, 4
        )
        pds.hours_available_end = player.hours_available
        pds.stress_end = player.stress
        pds.health_end = player.health
        pds.cash_end = round(float(player.cash or 0), 4)

        try:
            player.lifetime_xgp_earned = round(
                float(player.lifetime_xgp_earned or 0.0) + net_income_xgp, 4
            )
        except AttributeError:
            pass

        db.commit()
        db.refresh(player)

        return {
            "day_number": current_day,
            "hours_worked": hours_worked_int,
            "gross_income_xgp": round(gross_income_xgp, 2),
            "fuel_cost_xgp": round(fuel_cost_xgp, 2),
            "net_income_xgp": round(net_income_xgp, 2),
            "oil_index_used": oil_index,
            "wear_cost_xgp": round(wear_cost_xgp, 2),
            "maintenance_cost_xgp": round(maintenance_cost_xgp, 2),
            "demand_multiplier": round(float(shift["demand_multiplier"]), 4),
            "gas_price_xgp": round(float(shift["gas_price_xgp"]), 4),
            "wear_cost_per_hour_xgp": round(float(shift["wear_cost_per_hour_xgp"]), 4),
            "maintenance_triggered": bool(shift["maintenance_triggered"]),
            "maintenance_probability": round(float(shift["maintenance_probability"]), 4),
            "reliability_before": round(float(shift["reliability_before"]), 4),
            "reliability_after": round(float(shift["reliability_after"]), 4),
            "labor_efficiency_modifier": round(float(shift["labor_efficiency_modifier"]), 4),
            "productivity_modifier": round(float(shift["productivity_modifier"]), 4),
            "region_side_income_modifier": round(float(shift["region_side_income_modifier"]), 4),
            "opportunity_access_penalty": round(float(shift["opportunity_access_penalty"]), 4),
            "financial_access_factor": round(float(shift["financial_access_factor"]), 4),
            "stress_change": stress_change,
            "health_change": health_change,
            "hours_before": hours_before,
            "hours_after": hours_after,
            "balance_before": round(balance_before, 2),
            "balance_after": round(float(player.cash or 0), 2),
            "side_income_type": RIDESHARE_TYPE,
        }
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
