"""Ride-share side-income engine with Houston-time trip execution."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from decimal import Decimal
from hashlib import sha256

import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.macro_engine import get_or_create_macro_state_for_day
from app.models.contribution_event import ContributionEvent
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.side_income_action import SideIncomeAction
from app.models.xgp_transaction import XGPTransaction
from app.services.gameplay_transaction_service import record_gameplay_transaction
from app.services.player_daily_state_service import ensure_player_daily_state
from app.services.player_transaction_log_service import record_player_transaction
from app.services.city_map_service import (
    ensure_player_location,
    get_location_label,
    get_rideshare_location_profile,
)
from app.services.shift_state_service import resolve_expired_shift_if_needed

RIDESHARE_TYPE = "ride_share"
TRIP_OPTIONS = (1, 3, 5)
MAX_RIDESHARE_HOURS_PER_DAY = 6  # treated as time-units in the current loop
HOUSTON_TZ = pytz.timezone("America/Chicago")
logger = logging.getLogger(__name__)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _get_or_create_player_daily_state_in_txn(
    db: Session,
    player: Player,
    day_number: int,
) -> PlayerDailyState:
    """Get/create PlayerDailyState without committing (for atomic actions)."""
    return ensure_player_daily_state(
        db,
        player=player,
        day_number=day_number,
        defaults={
            "hours_available_start": int(player.hours_available),
            "hours_available_end": int(player.hours_available),
            "worked_main_job": False,
            "did_settlement": False,
            "stress_start": int(player.stress),
            "stress_end": int(player.stress),
            "health_start": int(player.health),
            "health_end": int(player.health),
            "cash_start": round(float(player.cash or 0), 4),
            "cash_end": round(float(player.cash or 0), 4),
            "side_income_hours": 0,
            "side_income_gross_xgp": 0,
            "side_income_fuel_cost_xgp": 0,
            "side_income_net_xgp": 0,
        },
    )

def get_current_oil_index(db: Session, day_number: int) -> float:
    """Return the active oil index for an in-game day (auto-seeded if missing)."""
    macro = get_or_create_macro_state_for_day(db, day_number)
    return round(float(macro.oil_index or 100.0), 4)


def get_rideshare_mode(hour: int) -> str:
    """Map Houston hour to rideshare demand/stress mode."""
    if 6 <= hour < 9:
        return "morning_peak"
    if 9 <= hour < 16:
        return "midday"
    if 16 <= hour < 19:
        return "evening_peak"
    if hour >= 20 or hour < 1:
        return "night"
    return "midday"


def _seeded_rng(seed: str) -> random.Random:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    seed_int = int(digest[:16], 16)
    return random.Random(seed_int)


def _trip_duration_hours(rng: random.Random) -> float:
    return round(rng.uniform(0.30, 0.75), 4)


def calculate_trip_outcome(mode: str, rng: random.Random) -> dict[str, float | int]:
    if mode == "midday":
        return {
            "pay": round(rng.uniform(12, 20), 2),
            "stress": 2,
            "health": -1,
        }
    if mode in {"morning_peak", "evening_peak"}:
        return {
            "pay": round(rng.uniform(18, 28), 2),
            "stress": 5,
            "health": -1,
        }
    if mode == "night":
        return {
            "pay": round(rng.uniform(22, 35), 2),
            "stress": 4,
            "health": -3,
        }
    return {
        "pay": round(rng.uniform(12, 20), 2),
        "stress": 2,
        "health": -1,
    }


def _resolve_requested_trips(trips: int | None, hours_worked: float | None) -> int:
    if trips is not None:
        parsed = int(trips)
        if parsed not in TRIP_OPTIONS:
            raise ValueError(f"Trips must be one of {list(TRIP_OPTIONS)}.")
        return parsed

    # Backward-compat path for callers still sending hours_worked.
    if hours_worked is None:
        return 1

    rounded = int(round(float(hours_worked)))
    if rounded <= 1:
        return 1
    if rounded <= 3:
        return 3
    return 5


def process_rideshare_action(
    db: Session,
    player: Player,
    hours_worked: float | None = None,
    trips: int | None = None,
    current_stress: int | None = None,
    current_health: int | None = None,
) -> dict:
    """Process rideshare as trip-based execution with Houston-time mode buckets."""
    try:
        effective_stress = None if current_stress is None else _clamp_int(int(current_stress), 0, 100)
        effective_health = None if current_health is None else _clamp_int(int(current_health), 0, 100)
        if effective_stress is not None:
            player.stress = effective_stress
        if effective_health is not None:
            player.health = effective_health
        if effective_stress is not None or effective_health is not None:
            db.flush()

        work_state = resolve_expired_shift_if_needed(
            db,
            player=player,
            current_stress_override=effective_stress,
            current_health_override=effective_health,
        )
        current_day = int(work_state.get("current_game_day") or 1)
        previous_day = int(getattr(player, "last_worked_day", 0) or 0)
        daily_reset_applied = False
        rideshare_state = (
            (work_state.get("rideshare_state") if isinstance(work_state.get("rideshare_state"), dict) else None)
            or {}
        )
        logger.info(
            "rideshare.process_rideshare_action eligibility checked.",
            extra={
                "player_id": str(player.id),
                "shift_active": bool(work_state.get("main_shift_active_flag")),
                "previous_in_game_day": previous_day,
                "current_in_game_day": current_day,
                "trips_today": int(rideshare_state.get("trips_today") or 0),
                "max_trips": int(rideshare_state.get("max_trips") or MAX_RIDESHARE_HOURS_PER_DAY),
                "can_rideshare": bool(rideshare_state.get("can_rideshare")),
                "rideshare_status": str(rideshare_state.get("status") or ""),
                "reason": str(rideshare_state.get("reason") or ""),
            },
        )

        if bool(work_state.get("main_shift_active_flag")):
            raise ValueError(
                "Ride share is unavailable during an active main shift. "
                "Wait until the shift is over."
            )
        if not bool(rideshare_state.get("can_rideshare")):
            reason = str(rideshare_state.get("reason") or "").strip()
            if not reason:
                reason = "Ride share is not available right now."
            raise ValueError(reason)

        if player.last_worked_day != current_day:
            player.main_job_hours_today = 0
            player.side_job_hours_today = 0
            player.total_hours_worked_today = 0
            player.work_actions_today = 0
            daily_reset_applied = True

        pds = _get_or_create_player_daily_state_in_txn(db, player, current_day)
        requested_trips = _resolve_requested_trips(trips, hours_worked)

        side_income_time_used_today = int(float(getattr(pds, "side_income_hours", 0) or 0))
        remaining_side_cap = max(0, MAX_RIDESHARE_HOURS_PER_DAY - side_income_time_used_today)
        available_time_units = min(int(player.hours_available or 0), remaining_side_cap)

        if available_time_units < 1:
            raise ValueError(
                "Not enough available time for one ride-share trip. "
                f"Remaining today: {available_time_units}."
            )

        trips_completed = min(requested_trips, available_time_units)
        partial_completion = trips_completed < requested_trips

        now_houston = datetime.now(HOUSTON_TZ)
        houston_hour = int(now_houston.hour)
        mode_used = get_rideshare_mode(houston_hour)
        current_location_key = ensure_player_location(player)
        current_location_label = get_location_label(current_location_key)
        location_profile = get_rideshare_location_profile(current_location_key, mode_used)
        if not bool(location_profile.get("allowed")):
            reason = str(location_profile.get("reason_if_blocked") or "").strip()
            if not reason:
                reason = "Ride share is unavailable at this location."
            raise ValueError(reason)
        demand_multiplier = Decimal(str(location_profile.get("multiplier", 1.0)))
        location_stress_modifier = int(location_profile.get("stress_delta_modifier") or 0)
        location_health_modifier = int(location_profile.get("health_delta_modifier") or 0)

        sequence_index = int(
            db.query(func.count(SideIncomeAction.id))
            .filter(
                SideIncomeAction.player_id == player.id,
                SideIncomeAction.day_number == current_day,
            )
            .scalar()
            or 0
        ) + 1

        total_pay = Decimal("0.00")
        total_stress_change = 0
        total_health_change = 0
        total_trip_duration_hours = 0.0

        for trip_idx in range(trips_completed):
            seed = f"{player.id}:{current_day}:{sequence_index}:{mode_used}:{trip_idx}"
            trip_rng = _seeded_rng(seed)
            outcome = calculate_trip_outcome(mode_used, trip_rng)
            adjusted_pay = (Decimal(str(outcome["pay"])) * demand_multiplier).quantize(Decimal("0.01"))
            adjusted_stress = max(1, int(outcome["stress"]) + location_stress_modifier)
            adjusted_health = int(outcome["health"]) + location_health_modifier
            total_pay += adjusted_pay
            total_stress_change += adjusted_stress
            total_health_change += adjusted_health
            total_trip_duration_hours += _trip_duration_hours(trip_rng)

        time_used_units = int(trips_completed)  # one time-unit per completed trip
        total_earned = round(float(total_pay), 2)
        oil_index = get_current_oil_index(db, current_day)

        hours_before = int(player.hours_available or 0)
        balance_before = round(float(player.cash or 0), 4)
        stress_before = int(player.stress or 0)
        health_before = int(player.health or 0)

        hours_after = _clamp_int(hours_before - time_used_units, 0, 24)
        balance_after = round(balance_before + total_earned, 4)

        player.cash = balance_after
        player.stress = _clamp_int(stress_before + total_stress_change, 0, 100)
        player.health = _clamp_int(health_before + total_health_change, 0, 100)
        player.hours_available = hours_after
        player.side_job_hours_today = int(player.side_job_hours_today or 0) + time_used_units
        player.total_hours_worked_today = int(player.total_hours_worked_today or 0) + time_used_units
        player.last_worked_day = current_day

        action = SideIncomeAction(
            player_id=player.id,
            day_number=current_day,
            side_income_type=RIDESHARE_TYPE,
            hours_worked=float(time_used_units),
            gross_income_xgp=round(total_earned, 4),
            fuel_cost_xgp=0.0,
            wear_cost_xgp=0.0,
            maintenance_cost_xgp=0.0,
            net_income_xgp=round(total_earned, 4),
            stress_change=total_stress_change,
            health_change=total_health_change,
            hours_before=hours_before,
            hours_after=hours_after,
            oil_index_used=oil_index,
            demand_multiplier=float(demand_multiplier),
            gross_per_hour_xgp=0.0,
            gas_price_per_unit_xgp=0.0,
            wear_cost_per_hour_xgp=0.0,
            net_per_hour_xgp=0.0,
            reliability_before=float(getattr(player, "rideshare_reliability", 0.95) or 0.95),
            reliability_after=float(getattr(player, "rideshare_reliability", 0.95) or 0.95),
        )
        db.add(action)
        db.flush()

        income_txn = XGPTransaction(
            player_id=player.id,
            transaction_type="rideshare_income",
            direction="in",
            amount=round(total_earned, 4),
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="side_income_action",
            reference_id=str(action.id),
            description=f"Ride share trips ({trips_completed}) - {mode_used} @ {current_location_label}",
        )
        db.add(income_txn)

        record_player_transaction(
            db,
            player=player,
            day=current_day,
            transaction_type="rideshare",
            category="work",
            quantity=trips_completed,
            unit_price=round(total_earned / max(1, trips_completed), 4),
            gross_amount=round(total_earned, 4),
            fee_amount=0,
            net_cash_delta=round(total_earned, 4),
            resulting_cash_balance=balance_after,
            metadata={
                "type": "rideshare",
                "trips": trips_completed,
                "mode": mode_used,
                "location_key": current_location_key,
                "location_label": current_location_label,
                "demand_multiplier": float(demand_multiplier),
                "timestamp": now_houston.isoformat(),
                "time_used_units": time_used_units,
                "time_used_hours": round(total_trip_duration_hours, 4),
            },
        )
        record_gameplay_transaction(
            db,
            player=player,
            day=current_day,
            transaction_type="income",
            category="ride_share",
            amount=round(total_earned, 4),
            description=f"Ride Share payout ({trips_completed} trips, {mode_used}, {current_location_label})",
        )

        contribution = ContributionEvent(
            player_id=player.id,
            event_type="ride_share",
            xgp_value=round(total_earned, 4),
            event_units=float(trips_completed),
            metadata_json=json.dumps(
                {
                    "side_income_type": RIDESHARE_TYPE,
                    "trips": trips_completed,
                    "requested_trips": requested_trips,
                    "mode": mode_used,
                    "location_key": current_location_key,
                    "location_label": current_location_label,
                    "demand_multiplier": float(demand_multiplier),
                    "timestamp": now_houston.isoformat(),
                    "time_used_units": time_used_units,
                    "time_used_hours": round(total_trip_duration_hours, 4),
                    "day_number": current_day,
                }
            ),
        )
        db.add(contribution)

        pds.side_income_hours = round(float(getattr(pds, "side_income_hours", 0) or 0) + time_used_units, 4)
        pds.side_income_gross_xgp = round(
            float(getattr(pds, "side_income_gross_xgp", 0) or 0) + total_earned, 4
        )
        pds.side_income_fuel_cost_xgp = round(float(getattr(pds, "side_income_fuel_cost_xgp", 0) or 0), 4)
        pds.side_income_wear_cost_xgp = round(float(getattr(pds, "side_income_wear_cost_xgp", 0) or 0), 4)
        pds.side_income_maintenance_cost_xgp = round(
            float(getattr(pds, "side_income_maintenance_cost_xgp", 0) or 0), 4
        )
        pds.side_income_net_xgp = round(
            float(getattr(pds, "side_income_net_xgp", 0) or 0) + total_earned, 4
        )
        pds.total_hours_used = round(
            float(getattr(pds, "total_hours_used", 0) or 0) + time_used_units, 4
        )
        pds.hours_available_end = player.hours_available
        pds.stress_end = player.stress
        pds.health_end = player.health
        pds.cash_end = round(float(player.cash or 0), 4)

        try:
            player.lifetime_xgp_earned = round(
                float(player.lifetime_xgp_earned or 0.0) + total_earned, 4
            )
        except AttributeError:
            pass

        db.commit()
        db.refresh(player)

        logger.info(
            "rideshare.process_rideshare_action completed.",
            extra={
                "player_id": str(player.id),
                "requested_trips": requested_trips,
                "completed_trips": trips_completed,
                "current_houston_time": now_houston.isoformat(),
                "main_shift_active_flag": work_state.get("main_shift_active_flag"),
                "rideshare_unlocked": work_state.get("rideshare_unlocked"),
                "rideshare_status": str(rideshare_state.get("status") or ""),
                "rideshare_reason": str(rideshare_state.get("reason") or ""),
                "trips_today_before": int(rideshare_state.get("trips_today") or 0),
                "max_trips": int(rideshare_state.get("max_trips") or MAX_RIDESHARE_HOURS_PER_DAY),
                "daily_reset_applied": bool(daily_reset_applied),
                "current_location_key": current_location_key,
                "current_location_label": current_location_label,
                "demand_multiplier": float(demand_multiplier),
                "side_income_hours_today": round(float(getattr(pds, "side_income_hours", 0) or 0), 4),
                "main_shift_hours_today": round(float(getattr(pds, "main_shift_hours_today", 0) or 0), 4),
            },
        )

        return {
            "day_number": current_day,
            "hours_worked": float(time_used_units),
            "trips": int(trips_completed),
            "trips_completed": int(trips_completed),
            "requested_trips": int(requested_trips),
            "mode": mode_used,
            "mode_used": mode_used,
            "houston_hour": houston_hour,
            "current_houston_time": now_houston.isoformat(),
            "time_used": int(time_used_units),
            "time_used_hours": round(total_trip_duration_hours, 4),
            "earned": round(total_earned, 2),
            "gross_income_xgp": round(total_earned, 2),
            "fuel_cost_xgp": 0.0,
            "wear_cost_xgp": 0.0,
            "maintenance_cost_xgp": 0.0,
            "net_income_xgp": round(total_earned, 2),
            "oil_index_used": oil_index,
            "demand_multiplier": float(demand_multiplier),
            "gas_price_xgp": 0.0,
            "wear_cost_per_hour_xgp": 0.0,
            "maintenance_triggered": False,
            "maintenance_probability": 0.0,
            "reliability_before": round(float(getattr(player, "rideshare_reliability", 0.95) or 0.95), 4),
            "reliability_after": round(float(getattr(player, "rideshare_reliability", 0.95) or 0.95), 4),
            "location_key": current_location_key,
            "location_label": current_location_label,
            "location_stress_modifier": int(location_stress_modifier),
            "location_health_modifier": int(location_health_modifier),
            "stress_change": int(total_stress_change),
            "health_change": int(total_health_change),
            "hours_before": int(hours_before),
            "hours_after": int(hours_after),
            "balance_before": round(balance_before, 2),
            "balance_after": round(float(player.cash or 0), 2),
            "side_income_type": RIDESHARE_TYPE,
            "partial_completion": bool(partial_completion),
        }
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
