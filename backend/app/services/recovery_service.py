from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.services.player_daily_state_service import ensure_player_daily_state

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
WAKING_HOURS = Decimal("16.0")
WEEKDAY_OFF_HOURS_WINDOW = Decimal("8.0")
WEEKDAY_OFF_HOURS_BLOCK = Decimal("2.0")
WEEKDAY_PASSIVE_RECOVERY_PER_BLOCK = 2
WEEKDAY_PASSIVE_RECOVERY_RIDESHARE_PER_BLOCK = 1
WEEKDAY_PASSIVE_RECOVERY_CAP = 8
DEFAULT_DAILY_TIME_UNITS = 24

RECOVERY_CATEGORY_KEY = "recovery"
RECOVERY_CATEGORY_LABEL = "Recovery / Leisure"
RECOVERY_CATEGORY_CAP = 4

WEEKEND_RECOVERY_BASE = 12
WEEKEND_RECOVERY_MODERATE = 8
WEEKEND_RECOVERY_HEAVY = 5
WEEKEND_HEAVY_RIDESHARE_HOURS = Decimal("6.0")

RECOVERY_ACTION_PRESETS: dict[str, dict[str, Any]] = {
    "rest": {
        "title": "Rest",
        "stress_delta": -6,
        "health_delta": 0,
        "time_cost_units": 1,
        "daily_cap": 2,
        "counts_toward_category": True,
    },
    "watch_tv": {
        "title": "Watch TV",
        "stress_delta": -4,
        "health_delta": 0,
        "time_cost_units": 1,
        "daily_cap": 1,
        "counts_toward_category": True,
    },
    "watch_movie": {
        "title": "Watch Movie",
        "stress_delta": -5,
        "health_delta": 0,
        "time_cost_units": 1,
        "daily_cap": 1,
        "counts_toward_category": True,
    },
    "read_book": {
        "title": "Read Book",
        "stress_delta": -3,
        "health_delta": 0,
        "time_cost_units": 1,
        "daily_cap": 2,
        "counts_toward_category": True,
    },
    "jogging": {
        "title": "Jogging",
        "stress_delta": -3,
        "health_delta": 2,
        "time_cost_units": 1,
        "daily_cap": 1,
        "counts_toward_category": True,
    },
}


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _get_or_create_daily_state(db: Session, *, player: Player, day_number: int) -> PlayerDailyState:
    cash_now = _money(_d(getattr(player, "cash", 0)))
    return ensure_player_daily_state(
        db,
        player=player,
        day_number=int(day_number),
        defaults={
            "hours_available_start": int(getattr(player, "hours_available", DEFAULT_DAILY_TIME_UNITS) or DEFAULT_DAILY_TIME_UNITS),
            "hours_available_end": int(getattr(player, "hours_available", DEFAULT_DAILY_TIME_UNITS) or DEFAULT_DAILY_TIME_UNITS),
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


def _default_day_recovery_state() -> dict[str, Any]:
    return {
        "version": 1,
        "actions_used": {},
    }


def get_day_recovery_state(pds: PlayerDailyState | None) -> dict[str, Any]:
    if pds is None:
        return _default_day_recovery_state()
    container = _parse_json(getattr(pds, "recovery_actions_json", None))
    raw_state = container.get("day_recovery") if isinstance(container.get("day_recovery"), dict) else {}
    state = _default_day_recovery_state()
    actions_used: dict[str, int] = {}
    for key, raw_value in dict(raw_state.get("actions_used") or {}).items():
        normalized_key = str(key or "").strip().lower()
        if normalized_key not in RECOVERY_ACTION_PRESETS:
            continue
        try:
            count = max(0, int(raw_value))
        except Exception:
            continue
        if count > 0:
            actions_used[normalized_key] = count
    state["actions_used"] = actions_used
    return state


def save_day_recovery_state(
    pds: PlayerDailyState,
    *,
    day_state: dict[str, Any],
    updated_at: datetime | None = None,
) -> None:
    container = _parse_json(getattr(pds, "recovery_actions_json", None))
    normalized_actions: dict[str, int] = {}
    for key, raw_value in dict(day_state.get("actions_used") or {}).items():
        normalized_key = str(key or "").strip().lower()
        if normalized_key not in RECOVERY_ACTION_PRESETS:
            continue
        try:
            count = max(0, int(raw_value))
        except Exception:
            continue
        if count > 0:
            normalized_actions[normalized_key] = count

    container["day_recovery"] = {
        "version": 1,
        "actions_used": normalized_actions,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
    pds.recovery_actions_json = json.dumps(container, sort_keys=True)


def resolve_recovery_action_key(action_key: str, parameters: dict[str, Any] | None = None) -> str | None:
    raw_key = str(action_key or "").strip().lower()
    params = parameters or {}
    recovery_mode = str(params.get("recovery_mode") or "").strip().lower()

    for candidate in (raw_key, recovery_mode):
        if candidate in RECOVERY_ACTION_PRESETS:
            return candidate

    if raw_key == "recovery_action" and recovery_mode in RECOVERY_ACTION_PRESETS:
        return recovery_mode
    if raw_key == "rest" and recovery_mode in RECOVERY_ACTION_PRESETS:
        return recovery_mode
    if raw_key == "study" and recovery_mode == "read_book":
        return "read_book"
    return None


def compute_passive_off_hours_recovery(side_income_hours_today: Decimal | float | int) -> dict[str, Any]:
    rideshare_hours = _q4(_clamp_hours(_d(side_income_hours_today), Decimal("0.0"), WEEKDAY_OFF_HOURS_WINDOW))
    pure_off_hours = _q4(max(Decimal("0.0"), WEEKDAY_OFF_HOURS_WINDOW - rideshare_hours))
    pure_blocks = int(pure_off_hours // WEEKDAY_OFF_HOURS_BLOCK)
    rideshare_blocks = int(rideshare_hours // WEEKDAY_OFF_HOURS_BLOCK)
    raw_points = (
        pure_blocks * WEEKDAY_PASSIVE_RECOVERY_PER_BLOCK
        + rideshare_blocks * WEEKDAY_PASSIVE_RECOVERY_RIDESHARE_PER_BLOCK
    )
    points = max(0, min(WEEKDAY_PASSIVE_RECOVERY_CAP, int(raw_points)))
    return {
        "points": points,
        "stress_delta": -points,
        "pure_off_hours": float(pure_off_hours),
        "rideshare_hours": float(rideshare_hours),
        "pure_blocks": pure_blocks,
        "rideshare_blocks": rideshare_blocks,
        "daily_cap": WEEKDAY_PASSIVE_RECOVERY_CAP,
        "window_hours": float(WEEKDAY_OFF_HOURS_WINDOW),
    }


def compute_weekend_recovery_bonus(
    *,
    is_weekend: bool,
    side_income_hours_today: Decimal | float | int,
) -> dict[str, Any]:
    if not bool(is_weekend):
        return {
            "points": 0,
            "stress_delta": 0,
            "tier": "none",
            "rideshare_hours": 0.0,
        }

    rideshare_hours = _q4(max(Decimal("0.0"), _d(side_income_hours_today)))
    if rideshare_hours >= WEEKEND_HEAVY_RIDESHARE_HOURS:
        points = WEEKEND_RECOVERY_HEAVY
        tier = "heavy"
    elif rideshare_hours > Decimal("0.0"):
        points = WEEKEND_RECOVERY_MODERATE
        tier = "moderate"
    else:
        points = WEEKEND_RECOVERY_BASE
        tier = "full"

    return {
        "points": int(points),
        "stress_delta": -int(points),
        "tier": tier,
        "rideshare_hours": float(rideshare_hours),
    }


def _clamp_hours(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def build_recovery_state(
    *,
    pds: PlayerDailyState | None,
    hours_available: int,
    active_shift: bool,
    day_settled: bool,
    is_weekend: bool,
    side_income_hours_today: Decimal | float | int,
    dinner_resolved: bool,
    life_debug_json: str | None = None,
) -> dict[str, Any]:
    day_state = get_day_recovery_state(pds)
    actions_used = dict(day_state.get("actions_used") or {})
    category_used = sum(
        int(actions_used.get(key, 0) or 0)
        for key, preset in RECOVERY_ACTION_PRESETS.items()
        if bool(preset.get("counts_toward_category"))
    )
    category_remaining = max(0, RECOVERY_CATEGORY_CAP - category_used)

    life_debug = _parse_json(life_debug_json)
    passive_meta = life_debug.get("passive_recovery") if isinstance(life_debug.get("passive_recovery"), dict) else {}
    applied_meta = bool(day_settled and passive_meta)
    off_hours_state = (
        {
            "points": int(passive_meta.get("off_hours_points", 0) or 0),
            "stress_delta": -int(passive_meta.get("off_hours_points", 0) or 0),
            "pure_off_hours": float(passive_meta.get("pure_off_hours", 0.0) or 0.0),
            "rideshare_hours": float(passive_meta.get("rideshare_hours", 0.0) or 0.0),
            "pure_blocks": int(passive_meta.get("pure_blocks", 0) or 0),
            "rideshare_blocks": int(passive_meta.get("rideshare_blocks", 0) or 0),
            "daily_cap": WEEKDAY_PASSIVE_RECOVERY_CAP,
            "window_hours": float(WEEKDAY_OFF_HOURS_WINDOW),
        }
        if applied_meta
        else compute_passive_off_hours_recovery(side_income_hours_today)
    )
    weekend_state = (
        {
            "points": int(passive_meta.get("weekend_points", 0) or 0),
            "stress_delta": -int(passive_meta.get("weekend_points", 0) or 0),
            "tier": str(passive_meta.get("weekend_tier", "none") or "none"),
            "rideshare_hours": float(passive_meta.get("weekend_rideshare_hours", 0.0) or 0.0),
        }
        if applied_meta
        else compute_weekend_recovery_bonus(
            is_weekend=is_weekend,
            side_income_hours_today=side_income_hours_today,
        )
    )

    actions: list[dict[str, Any]] = []
    for key, preset in RECOVERY_ACTION_PRESETS.items():
        used = int(actions_used.get(key, 0) or 0)
        daily_cap = int(preset["daily_cap"])
        remaining = max(0, daily_cap - used)
        block_reason: str | None = None

        if day_settled:
            block_reason = "Day already settled."
        elif active_shift:
            block_reason = "Action unavailable during active shift"
        elif remaining <= 0:
            block_reason = f"{preset['title']} daily limit reached"
        elif bool(preset.get("counts_toward_category")) and category_remaining <= 0:
            block_reason = "Recovery category limit reached"
        elif int(hours_available or 0) < int(preset["time_cost_units"]):
            block_reason = "Not enough time left today"

        actions.append(
            {
                "action_key": key,
                "title": str(preset["title"]),
                "used": used,
                "daily_cap": daily_cap,
                "remaining": remaining,
                "counts_toward_category": bool(preset.get("counts_toward_category")),
                "time_cost_units": int(preset["time_cost_units"]),
                "stress_delta": int(preset["stress_delta"]),
                "health_delta": int(preset["health_delta"]),
                "available": block_reason is None,
                "block_reason": block_reason,
            }
        )

    meal_block_reason: str | None = None
    if day_settled:
        meal_block_reason = "Day already settled."
    elif active_shift:
        meal_block_reason = "Action unavailable during active shift"
    elif bool(dinner_resolved):
        meal_block_reason = "Meal already completed"

    meal_action = {
        "action_key": "eat_meal",
        "title": "Eat Meal",
        "used": 1 if dinner_resolved else 0,
        "daily_cap": 1,
        "remaining": 0 if dinner_resolved else 1,
        "counts_toward_category": False,
        "time_cost_units": 0,
        "stress_delta": -2,
        "health_delta": 2,
        "available": meal_block_reason is None,
        "block_reason": meal_block_reason,
    }

    return {
        "category_key": RECOVERY_CATEGORY_KEY,
        "category_label": RECOVERY_CATEGORY_LABEL,
        "category_cap": RECOVERY_CATEGORY_CAP,
        "category_used": category_used,
        "category_remaining": category_remaining,
        "actions": actions,
        "meal_action": meal_action,
        "passive_off_hours_recovery": {
            **off_hours_state,
            "status": "applied" if applied_meta else ("pending" if not day_settled else "none"),
        },
        "weekend_recovery": {
            **weekend_state,
            "status": "applied" if applied_meta else ("pending" if bool(is_weekend) and not day_settled else "none"),
            "is_weekend": bool(is_weekend),
        },
    }


def apply_recovery_action(
    db: Session,
    *,
    player: Player,
    day_number: int,
    action_key: str,
    parameters: dict[str, Any] | None = None,
    now_houston: datetime | None = None,
    active_shift: bool = False,
    day_settled: bool = False,
    is_weekend: bool = False,
    side_income_hours_today: Decimal | float | int = 0,
) -> dict[str, Any]:
    resolved_key = resolve_recovery_action_key(action_key, parameters)
    if resolved_key is None:
        raise ValueError("Unsupported recovery action.")

    pds = _get_or_create_daily_state(db, player=player, day_number=day_number)
    recovery_state = build_recovery_state(
        pds=pds,
        hours_available=int(getattr(player, "hours_available", 0) or 0),
        active_shift=bool(active_shift),
        day_settled=bool(day_settled),
        is_weekend=bool(is_weekend),
        side_income_hours_today=side_income_hours_today,
        dinner_resolved=bool(getattr(pds, "dinner_resolved", False)),
        life_debug_json=getattr(pds, "life_debug_json", None),
    )
    action_state = next(
        (item for item in recovery_state.get("actions", []) if str(item.get("action_key")) == resolved_key),
        None,
    )
    if action_state is None:
        raise ValueError("Unsupported recovery action.")
    if not bool(action_state.get("available")):
        raise ValueError(str(action_state.get("block_reason") or "Recovery action unavailable."))

    preset = RECOVERY_ACTION_PRESETS[resolved_key]
    stress_before = int(getattr(player, "stress", 0) or 0)
    health_before = int(getattr(player, "health", 100) or 100)
    hours_before = int(getattr(player, "hours_available", 0) or 0)

    player.stress = _clamp_int(stress_before + int(preset["stress_delta"]), 0, 100)
    player.health = _clamp_int(health_before + int(preset["health_delta"]), 0, 100)
    player.hours_available = max(0, hours_before - int(preset["time_cost_units"]))

    pds.hours_available_end = int(getattr(player, "hours_available", 0) or 0)
    pds.stress_end = int(getattr(player, "stress", 0) or 0)
    pds.health_end = int(getattr(player, "health", 100) or 100)

    day_state = get_day_recovery_state(pds)
    actions_used = dict(day_state.get("actions_used") or {})
    actions_used[resolved_key] = int(actions_used.get(resolved_key, 0) or 0) + 1
    day_state["actions_used"] = actions_used
    save_day_recovery_state(pds, day_state=day_state, updated_at=now_houston)

    updated_state = build_recovery_state(
        pds=pds,
        hours_available=int(getattr(player, "hours_available", 0) or 0),
        active_shift=bool(active_shift),
        day_settled=bool(day_settled),
        is_weekend=bool(is_weekend),
        side_income_hours_today=side_income_hours_today,
        dinner_resolved=bool(getattr(pds, "dinner_resolved", False)),
        life_debug_json=getattr(pds, "life_debug_json", None),
    )

    return {
        "action_key": resolved_key,
        "title": str(preset["title"]),
        "time_cost_units": int(preset["time_cost_units"]),
        "stress_delta": int(getattr(player, "stress", 0) or 0) - stress_before,
        "health_delta": int(getattr(player, "health", 100) or 100) - health_before,
        "stress_before": stress_before,
        "stress_after": int(getattr(player, "stress", 0) or 0),
        "health_before": health_before,
        "health_after": int(getattr(player, "health", 100) or 100),
        "hours_before": hours_before,
        "hours_after": int(getattr(player, "hours_available", 0) or 0),
        "recovery_state": updated_state,
    }
