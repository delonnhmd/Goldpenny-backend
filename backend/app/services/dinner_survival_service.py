"""Dinner survival resolution and offline catch-up helpers."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.services.gameplay_transaction_service import record_gameplay_transaction
from app.services.player_daily_state_service import ensure_player_daily_state

logger = logging.getLogger(__name__)

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
DEFAULT_DINNER_COST_XGP = Decimal("6.00")
AUTO_DEBT_HEALTH_DELTA = -2
AUTO_DEBT_STRESS_DELTA = 3
MISSED_DINNER_HEALTH_DELTA = -4
MISSED_DINNER_STRESS_DELTA = 6
NIGHT_REMINDER_START_HOUR = 18
MAX_OFFLINE_CATCHUP_DAYS = 30


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _coerce_houston_date(value: datetime | None, fallback: date, *, tz_reference: datetime) -> date:
    if value is None:
        return fallback
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(tz_reference.tzinfo).date()


def _get_or_create_daily_state(db: Session, *, player: Player, day_number: int) -> PlayerDailyState:
    cash_now = _q4(_d(getattr(player, "cash", 0)))
    return ensure_player_daily_state(
        db,
        player=player,
        day_number=int(day_number),
        defaults={
            "hours_available_start": int(getattr(player, "hours_available", 16) or 16),
            "hours_available_end": int(getattr(player, "hours_available", 16) or 16),
            "worked_main_job": False,
            "did_settlement": False,
            "stress_start": int(getattr(player, "stress", 0) or 0),
            "stress_end": int(getattr(player, "stress", 0) or 0),
            "health_start": int(getattr(player, "health", 100) or 100),
            "health_end": int(getattr(player, "health", 100) or 100),
            "cash_start": cash_now,
            "cash_end": cash_now,
        },
    )


def _hydrate_dinner_snapshot(
    *,
    player: Player,
    pds: PlayerDailyState,
    day_number: int,
) -> dict[str, Any]:
    return {
        "day_number": int(day_number),
        "dinner_resolved": bool(getattr(pds, "dinner_resolved", False)),
        "dinner_mode": str(getattr(pds, "dinner_mode", "") or ""),
        "dinner_cost_xgp": float(_money(_d(getattr(pds, "dinner_cost", 0)))),
        "food_debt_added_xgp": float(_money(_d(getattr(pds, "food_debt_added", 0)))),
        "cash_after": float(_money(_d(getattr(player, "cash", 0)))),
        "debt_after": float(_money(_d(getattr(player, "debt_xgp", 0)))),
        "health_after": int(getattr(player, "health", 0) or 0),
        "stress_after": int(getattr(player, "stress", 0) or 0),
    }


def apply_manual_meal_action(
    db: Session,
    *,
    player: Player,
    day_number: int,
    meal_type: str,
    now_houston: datetime | None = None,
) -> dict[str, Any]:
    normalized_meal = str(meal_type or "meal").strip().lower()
    cost = _money(DEFAULT_DINNER_COST_XGP)
    pds = _get_or_create_daily_state(db, player=player, day_number=day_number)

    cash_before = _money(_d(getattr(player, "cash", 0)))
    debt_before = _money(_d(getattr(player, "debt_xgp", 0)))
    health_before = int(getattr(player, "health", 0) or 0)
    stress_before = int(getattr(player, "stress", 0) or 0)

    if normalized_meal != "dinner" and cash_before < cost:
        raise ValueError(f"Not enough XGP for a {normalized_meal}. Need {cost:.2f} XGP.")

    cash_used = _money(min(max(cash_before, Decimal("0.00")), cost))
    debt_added = _money(cost - cash_used) if normalized_meal == "dinner" else Decimal("0.00")

    if normalized_meal != "dinner":
        cash_used = cost
        debt_added = Decimal("0.00")

    if cash_used > Decimal("0.00"):
        player.cash = _money(cash_before - cash_used)
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category="food",
            amount=cash_used,
            description=f"{normalized_meal.capitalize()} purchase for Day {int(day_number)}",
        )

    if debt_added > Decimal("0.00"):
        player.debt_xgp = _money(debt_before + debt_added)
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category="food_debt",
            amount=0,
            description=f"Dinner covered by debt for Day {int(day_number)} (+{debt_added:.2f} debt)",
        )

    player.health = _clamp_int(health_before + 5, 0, 100)
    player.stress = _clamp_int(stress_before - 3, 0, 100)

    pds.meals_recorded = int(getattr(pds, "meals_recorded", 0) or 0) + 1
    if normalized_meal == "dinner":
        pds.dinner_resolved = True
        pds.dinner_mode = "manual_debt" if debt_added > Decimal("0.00") else "manual_cash"
        pds.dinner_cost = _q4(cost)
        pds.food_debt_added = _q4(debt_added)
        pds.dinner_resolved_at = now_houston
    pds.health_end = int(getattr(player, "health", 0) or 0)
    pds.stress_end = int(getattr(player, "stress", 0) or 0)
    pds.cash_end = _q4(_d(getattr(player, "cash", 0)))

    return {
        "meal_type": normalized_meal,
        "meal_cost_xgp": float(cost),
        "cash_used_xgp": float(cash_used),
        "debt_added_xgp": float(debt_added),
        "cash_after": float(_money(_d(getattr(player, "cash", 0)))),
        "debt_after": float(_money(_d(getattr(player, "debt_xgp", 0)))),
        "health_delta": int(getattr(player, "health", 0) or 0) - health_before,
        "stress_delta": int(getattr(player, "stress", 0) or 0) - stress_before,
        "dinner_mode": str(getattr(pds, "dinner_mode", "") or ""),
        "dinner_resolved": bool(getattr(pds, "dinner_resolved", False)),
    }


def ensure_day_dinner_resolved(
    db: Session,
    *,
    player: Player,
    day_number: int,
    source: str,
    now_houston: datetime | None = None,
    allow_debt_extension: bool = True,
) -> dict[str, Any]:
    pds = _get_or_create_daily_state(db, player=player, day_number=day_number)
    if bool(getattr(pds, "dinner_resolved", False)):
        return _hydrate_dinner_snapshot(player=player, pds=pds, day_number=day_number)

    dinner_cost = _money(DEFAULT_DINNER_COST_XGP)
    cash_before = _money(_d(getattr(player, "cash", 0)))
    debt_before = _money(_d(getattr(player, "debt_xgp", 0)))
    health_before = int(getattr(player, "health", 0) or 0)
    stress_before = int(getattr(player, "stress", 0) or 0)

    cash_used = _money(min(max(cash_before, Decimal("0.00")), dinner_cost))
    uncovered = _money(dinner_cost - cash_used)
    dinner_mode = "auto_cash"
    health_delta = 0
    stress_delta = 0
    food_debt_added = Decimal("0.00")

    if uncovered <= Decimal("0.00"):
        player.cash = _money(cash_before - dinner_cost)
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category="food",
            amount=dinner_cost,
            description=f"Auto dinner for Day {int(day_number)}",
        )
    elif allow_debt_extension:
        if cash_used > Decimal("0.00"):
            player.cash = _money(cash_before - cash_used)
            record_gameplay_transaction(
                db,
                player=player,
                day=day_number,
                transaction_type="expense",
                category="food",
                amount=cash_used,
                description=f"Auto dinner partial cash for Day {int(day_number)}",
            )
        player.debt_xgp = _money(debt_before + uncovered)
        food_debt_added = uncovered
        dinner_mode = "auto_debt"
        health_delta = AUTO_DEBT_HEALTH_DELTA
        stress_delta = AUTO_DEBT_STRESS_DELTA
        player.health = _clamp_int(health_before + health_delta, 0, 100)
        player.stress = _clamp_int(stress_before + stress_delta, 0, 100)
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category="survival_debt",
            amount=0,
            description=f"Dinner covered by debt for Day {int(day_number)} (+{uncovered:.2f} debt)",
        )
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category="health_penalty",
            amount=0,
            description=f"Dinner debt pressure - Health {AUTO_DEBT_HEALTH_DELTA}, Stress +{AUTO_DEBT_STRESS_DELTA}",
        )
    else:
        dinner_mode = "missed"
        health_delta = MISSED_DINNER_HEALTH_DELTA
        stress_delta = MISSED_DINNER_STRESS_DELTA
        player.health = _clamp_int(health_before + health_delta, 0, 100)
        player.stress = _clamp_int(stress_before + stress_delta, 0, 100)
        record_gameplay_transaction(
            db,
            player=player,
            day=day_number,
            transaction_type="expense",
            category="health_penalty",
            amount=0,
            description=f"Missed dinner due to insufficient funds - Health {MISSED_DINNER_HEALTH_DELTA}, Stress +{MISSED_DINNER_STRESS_DELTA}",
        )

    pds.dinner_resolved = True
    pds.dinner_mode = dinner_mode
    pds.dinner_cost = _q4(dinner_cost)
    pds.food_debt_added = _q4(food_debt_added)
    pds.dinner_resolved_at = now_houston
    if dinner_mode != "missed":
        pds.meals_recorded = max(1, int(getattr(pds, "meals_recorded", 0) or 0))
    else:
        pds.survival_penalty_applied = True
    pds.health_end = int(getattr(player, "health", health_before) or health_before)
    pds.stress_end = int(getattr(player, "stress", stress_before) or stress_before)
    pds.cash_end = _q4(_d(getattr(player, "cash", cash_before)))

    logger.info(
        "dinner.ensure_day_dinner_resolved applied.",
        extra={
            "player_id": str(player.id),
            "day_number": int(day_number),
            "source": str(source),
            "dinner_mode": dinner_mode,
            "cash_used_xgp": float(cash_used if dinner_mode != "auto_cash" else dinner_cost),
            "food_debt_added_xgp": float(food_debt_added),
            "health_delta": int(health_delta),
            "stress_delta": int(stress_delta),
        },
    )

    return _hydrate_dinner_snapshot(player=player, pds=pds, day_number=day_number)


def compute_night_dinner_reminder(
    *,
    day_settled: bool,
    active_shift: bool,
    dinner_resolved: bool,
    now_houston: datetime,
) -> tuple[bool, str | None]:
    if day_settled or active_shift or dinner_resolved:
        return False, None
    if int(now_houston.hour) < NIGHT_REMINDER_START_HOUR:
        return False, None
    return True, "Dinner not completed. Eat now to avoid health loss."


def run_offline_survival_catchup(
    db: Session,
    *,
    player: Player,
    current_day: int,
    now_houston: datetime,
) -> dict[str, Any]:
    today = now_houston.date()
    last_sync = getattr(player, "last_survival_resolved_date", None)
    if last_sync is None:
        updated_at = getattr(player, "updated_at", None)
        last_sync = _coerce_houston_date(updated_at, today, tz_reference=now_houston)
    missed_days = max(0, int((today - last_sync).days))
    if missed_days <= 0:
        sync_updated = bool(getattr(player, "last_survival_resolved_date", None) != today)
        if sync_updated:
            player.last_survival_resolved_date = today
        return {
            "applied_days": 0,
            "missed_days": 0,
            "truncated_days": 0,
            "processed_days": [],
            "current_day_after": int(current_day),
            "sync_date_updated": sync_updated,
        }

    days_to_process = min(missed_days, MAX_OFFLINE_CATCHUP_DAYS)
    processed_days: list[dict[str, Any]] = []
    for offset in range(days_to_process):
        day_number = int(current_day) + offset
        snapshot = ensure_day_dinner_resolved(
            db,
            player=player,
            day_number=day_number,
            source="offline_catchup",
            now_houston=now_houston,
            allow_debt_extension=True,
        )
        pds = _get_or_create_daily_state(db, player=player, day_number=day_number)
        pds.did_settlement = True
        pds.hours_available_end = int(getattr(player, "hours_available", 16) or 16)
        player.last_settled_day = max(int(getattr(player, "last_settled_day", 0) or 0), day_number)
        processed_days.append(snapshot)

    player.main_job_hours_today = 0
    player.side_job_hours_today = 0
    player.total_hours_worked_today = 0
    player.work_actions_today = 0
    player.hours_available = 16
    player.last_survival_resolved_date = today

    logger.info(
        "dinner.run_offline_survival_catchup processed days.",
        extra={
            "player_id": str(player.id),
            "previous_sync_date": str(last_sync),
            "today_date": str(today),
            "missed_days": missed_days,
            "applied_days": days_to_process,
            "truncated_days": max(0, missed_days - days_to_process),
            "processed_day_numbers": [int(row.get("day_number") or 0) for row in processed_days],
        },
    )

    return {
        "applied_days": days_to_process,
        "missed_days": missed_days,
        "truncated_days": max(0, missed_days - days_to_process),
        "processed_days": processed_days,
        "current_day_after": int(current_day) + int(days_to_process),
        "sync_date_updated": True,
    }
