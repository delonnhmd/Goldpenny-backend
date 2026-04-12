"""Canonical gameplay endpoints used by the Expo gameplay loop shell.

Step 72 goals:
- provide stable /gameplay/player/{player_id}/... routes
- avoid frontend route probing + 404 storms
- keep first-session day-1 flow playable with meaningful starter actions
"""

from __future__ import annotations

import logging
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.career_config import CAREER_CONFIG, CERTIFICATION_CATALOG
from app.engine.career_service import (
    CareerError,
    CareerNotFoundError,
    CareerValidationError,
    apply_daily_career_progression,
    start_certification_track,
    switch_player_job,
)
from app.engine.economy_presentation_service import build_economy_presentation_summary
from app.engine.rideshare_engine import process_rideshare_action
from app.models.game_state import GameState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_transaction_log import PlayerTransactionLog
from app.services.daily_brief_service import (
    DailyBriefError,
    DailyBriefNotFoundError,
    get_player_latest_daily_brief,
)
from app.services.daily_settlement_service import (
    DailySettlementError,
    SettlementNotFoundError,
    SettlementValidationError,
    get_latest_settlement_summary,
)
from app.services.dinner_survival_service import apply_manual_meal_action
from app.services.city_map_service import (
    build_city_map_snapshot,
    ensure_player_location,
    get_location_label,
    get_location_region,
    get_travel_rule,
    normalize_location_key,
)
from app.services.day_progression_service import run_player_next_day
from app.services.job_market_service import (
    JobMarketError,
    JobMarketNotFoundError,
    JobMarketValidationError,
    get_player_job_summary,
)
from app.services.player_onboarding_service import (
    OnboardingError,
    OnboardingNotFoundError,
    get_playable_player_summary,
)
from app.services.job_progress_service import (
    JOB_COMPANY_MAP,
    SHIFT_PROFILES,
    build_job_progress_payload,
    latest_employment_state,
    normalize_shift_type,
    upsert_employment_foundation,
)
from app.services.job_key_service import normalize_main_job_key
from app.services.recovery_service import (
    RECOVERY_ACTION_PRESETS,
    apply_recovery_action,
    resolve_recovery_action_key,
)
from app.services.shift_state_service import (
    SHIFT_STATUS_ACTIVE,
    build_work_state_payload,
    finalize_active_main_shift,
    get_gameplay_testing_mode_config,
    resolve_expired_shift_if_needed,
    start_main_shift,
)
from app.services.player_job_progression_service import (
    award_training_session_xp,
)
from app.services.gameplay_transaction_service import (
    list_gameplay_transactions_for_day,
    record_gameplay_transaction,
)
from app.services.player_transaction_log_service import record_player_transaction

router = APIRouter()
logger = logging.getLogger(__name__)


class GameplayActionRequest(BaseModel):
    action_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class GameplayActionPreviewRequest(BaseModel):
    action_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class EndOfDaySummaryAckRequest(BaseModel):
    day_number: int | None = None

def _money_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))

def _resolve_player(db: Session, player_id: str) -> Player:
    raw_player_id = str(player_id or "").strip()
    if not raw_player_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found.")

    try:
        pid = UUID(raw_player_id)
    except ValueError:
        pid = None

    if pid is not None:
        player = db.query(Player).filter(Player.id == pid).first()
        if player is not None:
            return player

    # Day-1 dev usability guard: allow canonical gameplay routes to resolve by
    # external display name aliases (e.g. "player1") when UUID is not supplied.
    player = (
        db.query(Player)
        .filter(func.lower(Player.display_name) == raw_player_id.lower())
        .order_by(Player.created_at.asc())
        .first()
    )
    if player is not None:
        logger.info(
            "gameplay.player resolved by display_name alias.",
            extra={
                "requested_player_id": raw_player_id,
                "resolved_player_id": str(player.id),
            },
        )
        return player

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found.")


def _raise_gameplay_http_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, (OnboardingNotFoundError, SettlementNotFoundError, DailyBriefNotFoundError, JobMarketNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (SettlementValidationError, CareerValidationError, JobMarketValidationError)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, (DailySettlementError, OnboardingError, DailyBriefError, CareerError, JobMarketError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    detail = str(exc).strip() or "Unexpected gameplay service error."
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _debt_payment_request_id(params: dict[str, Any]) -> str:
    return str(
        params.get("request_id")
        or params.get("idempotency_key")
        or params.get("action_request_id")
        or ""
    ).strip()


def _find_existing_debt_payment_log(
    db: Session,
    *,
    player_id: UUID,
    request_id: str,
) -> PlayerTransactionLog | None:
    raw_request_id = str(request_id or "").strip()
    if not raw_request_id:
        return None
    return (
        db.query(PlayerTransactionLog)
        .filter(
            PlayerTransactionLog.player_id == player_id,
            PlayerTransactionLog.category == "debt_payment",
            PlayerTransactionLog.transaction_type == "debt_payment",
            PlayerTransactionLog.metadata_json.contains(raw_request_id),
        )
        .order_by(PlayerTransactionLog.created_at.desc())
        .first()
    )


JOB_DISPLAY_NAMES: dict[str, str] = {
    "auto_mechanic": "Auto Mechanic",
    "aircraft_mechanic": "Aircraft Mechanic",
    "banker": "Banker",
    "chef": "Chef",
    "cleaner": "Cleaner",
    "warehouse_operator": "Warehouse Manager",
    "real_estate_agent": "Real Estate Agent",
    "retail": "Retail Seller",
    "delivery": "Delivery Driver",
}


def _job_display_name(job_key: str | None) -> str:
    canonical = normalize_main_job_key(job_key, allow_aliases=True)
    if not canonical:
        return "No job selected"
    return JOB_DISPLAY_NAMES.get(canonical, canonical.replace("_", " ").title())


def _safe_iso_to_houston_label(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.strftime("%I:%M %p").lstrip("0") + " CT"


def _pressure_level(
    value: float,
    *,
    moderate_at: float,
    high_at: float,
    critical_at: float,
    inverse: bool = False,
) -> str:
    if inverse:
        if value <= critical_at:
            return "critical"
        if value <= high_at:
            return "high"
        if value <= moderate_at:
            return "moderate"
        return "low"
    if value >= critical_at:
        return "critical"
    if value >= high_at:
        return "high"
    if value >= moderate_at:
        return "moderate"
    return "low"


def _pressure_phrase(level: str, *, demand: bool = False) -> str:
    norm = str(level or "").strip().lower()
    if demand:
        if norm in {"critical", "high"}:
            return "Strong"
        if norm == "moderate":
            return "Elevated"
        return "Soft"
    if norm == "critical":
        return "Critical"
    if norm == "high":
        return "High"
    if norm == "moderate":
        return "Moderate"
    return "Low"


def _build_economy_risk_overview(
    *,
    economy_payload: dict[str, Any] | None,
    debt_xgp: float,
    cash_xgp: float,
    shift_status: str,
) -> dict[str, Any]:
    market = (economy_payload or {}).get("market_overview") or {}
    macro_values = ((market.get("debug_meta") or {}).get("macro_values") or {})
    macro_trends = market.get("macro_trend_labels") or {}
    basket_labels = market.get("basket_pressure_labels") or {}
    supply_summary = (economy_payload or {}).get("supply_chain_summary") or {}
    commute_summary = (economy_payload or {}).get("commute_pressure") or {}

    inflation_rate = _safe_float(macro_values.get("inflation_rate"), 0.0)
    oil_index = _safe_float(macro_values.get("oil_index"), 100.0)
    unemployment_rate = _safe_float(macro_values.get("unemployment_rate"), 0.0)
    consumer_confidence = _safe_float(macro_values.get("consumer_confidence"), 50.0)
    supply_chain_stress = _safe_float(macro_values.get("supply_chain_stress"), 0.0)

    fuel_pressure = _pressure_level(oil_index, moderate_at=105.0, high_at=115.0, critical_at=125.0)
    food_inflation = _pressure_level(inflation_rate, moderate_at=2.6, high_at=3.3, critical_at=4.0)
    unemployment_pressure = _pressure_level(unemployment_rate, moderate_at=5.5, high_at=6.3, critical_at=7.2)
    confidence_pressure = _pressure_level(
        consumer_confidence,
        moderate_at=48.0,
        high_at=44.0,
        critical_at=40.0,
        inverse=True,
    )
    supply_pressure = _pressure_level(supply_chain_stress, moderate_at=0.75, high_at=1.0, critical_at=1.2)

    protein_pressure = str(basket_labels.get("protein") or "low").strip().lower()
    essentials_pressure = str(basket_labels.get("essentials") or "low").strip().lower()

    job_pressure_rows = supply_summary.get("job_pressure") if isinstance(supply_summary.get("job_pressure"), list) else []
    job_pressure_map: dict[str, float] = {}
    for row in job_pressure_rows:
        if not isinstance(row, dict):
            continue
        key = normalize_main_job_key(row.get("job_key"), allow_aliases=True) or str(row.get("job_key") or "").strip().lower()
        if key:
            job_pressure_map[key] = _safe_float(row.get("job_pressure_multiplier"), 1.0)

    delivery_multiplier = max(
        _safe_float(job_pressure_map.get("delivery"), 1.0),
        _safe_float(supply_summary.get("best_job_pressure_multiplier"), 1.0)
        if str(supply_summary.get("best_job_opportunity") or "").strip().lower() in {"delivery", "delivery_driver"}
        else 1.0,
    )
    rideshare_multiplier = max(1.0, delivery_multiplier * 0.92)
    rideshare_demand = _pressure_level(rideshare_multiplier, moderate_at=1.03, high_at=1.12, critical_at=1.22)
    delivery_demand = _pressure_level(delivery_multiplier, moderate_at=1.03, high_at=1.12, critical_at=1.22)

    debt_ratio = debt_xgp / max(1.0, cash_xgp)
    debt_pressure = _pressure_level(debt_ratio, moderate_at=0.7, high_at=1.25, critical_at=2.0)

    downtown_pressure = str(commute_summary.get("commute_pressure_level") or "moderate").strip().lower()
    if downtown_pressure not in {"low", "moderate", "high", "critical"}:
        downtown_pressure = "moderate"

    shift_stability = "moderate" if shift_status == "active" else "low"

    macro_conditions = [
        {
            "key": "fuel_pressure",
            "label": "Fuel pressure",
            "level": fuel_pressure,
            "value_text": f"{_pressure_phrase(fuel_pressure)} - oil index {oil_index:.1f}",
            "trend": str(macro_trends.get("oil_direction") or "stable"),
        },
        {
            "key": "food_inflation",
            "label": "Food inflation",
            "level": food_inflation,
            "value_text": f"{_pressure_phrase(food_inflation)} - inflation {inflation_rate:.2f}%",
            "trend": str(macro_trends.get("inflation_direction") or "stable"),
        },
        {
            "key": "unemployment_pressure",
            "label": "Job market pressure",
            "level": unemployment_pressure,
            "value_text": f"{_pressure_phrase(unemployment_pressure)} - unemployment {unemployment_rate:.2f}%",
            "trend": str(macro_trends.get("unemployment_direction") or "stable"),
        },
        {
            "key": "consumer_mood",
            "label": "Consumer mood",
            "level": confidence_pressure,
            "value_text": f"{_pressure_phrase(confidence_pressure)} - confidence {consumer_confidence:.1f}",
            "trend": str(macro_trends.get("confidence_direction") or "stable"),
        },
        {
            "key": "supply_chain_stress",
            "label": "Supply chain stress",
            "level": supply_pressure,
            "value_text": f"{_pressure_phrase(supply_pressure)} - stress {supply_chain_stress:.2f}",
            "trend": str(macro_trends.get("supply_chain_pressure") or "stable"),
        },
    ]

    opportunity_signals = [
        {
            "key": "rideshare_demand",
            "label": "Rideshare demand",
            "level": rideshare_demand,
            "value_text": f"{_pressure_phrase(rideshare_demand, demand=True)} tonight",
        },
        {
            "key": "delivery_demand",
            "label": "Delivery demand",
            "level": delivery_demand,
            "value_text": f"{_pressure_phrase(delivery_demand, demand=True)}",
        },
        {
            "key": "grocery_costs",
            "label": "Grocery costs",
            "level": essentials_pressure if essentials_pressure in {"low", "moderate", "high", "critical"} else "moderate",
            "value_text": (
                "Up"
                if essentials_pressure in {"high", "critical"}
                else "Steady"
                if essentials_pressure == "moderate"
                else "Soft"
            ),
        },
        {
            "key": "downtown_stress",
            "label": "Downtown stress",
            "level": downtown_pressure,
            "value_text": _pressure_phrase(downtown_pressure),
        },
    ]

    risk_badges = [
        {"key": "debt_pressure", "label": "Debt pressure", "level": debt_pressure},
        {"key": "fuel_pressure", "label": "Fuel pressure", "level": fuel_pressure},
        {"key": "food_inflation", "label": "Food inflation", "level": protein_pressure if protein_pressure in {"low", "moderate", "high", "critical"} else food_inflation},
        {"key": "rideshare_demand", "label": "Rideshare demand", "level": rideshare_demand},
        {"key": "shift_stability", "label": "Shift stability", "level": shift_stability},
    ]

    return {
        "macro_conditions": macro_conditions,
        "opportunity_signals": opportunity_signals,
        "risk_badges": risk_badges,
        "summary_line": str(market.get("short_explainer") or "Market signals are available."),
    }
def _current_game_day(db: Session) -> int:
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    if state is None:
        return 1
    return max(1, _safe_int(getattr(state, "current_day", 1), 1))


def _normalize_optional_stat_override(value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, min(100, _safe_int(value, 0)))


def _sync_player_work_state(
    db: Session,
    player: Player,
    *,
    current_stress_override: int | None = None,
    current_health_override: int | None = None,
) -> dict[str, Any]:
    return resolve_expired_shift_if_needed(
        db,
        player=player,
        current_stress_override=_normalize_optional_stat_override(current_stress_override),
        current_health_override=_normalize_optional_stat_override(current_health_override),
    )


def _log_salary_ui_payload_rendered(*, route: str, player: Player, work_state: dict[str, Any] | None) -> None:
    payload = work_state or {}
    salary_audit = payload.get("current_shift_salary_audit") if isinstance(payload.get("current_shift_salary_audit"), dict) else {}
    logger.info(
        "shift.salary_ui_payload_rendered",
        extra={
            "route": route,
            "player_id": str(player.id),
            "shift_id": str(salary_audit.get("shift_id") or ""),
            "day_number": int(payload.get("current_game_day") or 0),
            "job_key": str(
                payload.get("authoritative_current_job_id")
                or payload.get("active_shift_job_id")
                or payload.get("scheduled_shift_job_id")
                or ""
            ),
            "salary_amount": _safe_float(
                salary_audit.get("final_salary_paid"),
                _safe_float(payload.get("salary_earned_today"), 0.0),
            ),
            "cash_before": _safe_float(salary_audit.get("cash_before"), 0.0),
            "cash_after": _safe_float(salary_audit.get("cash_after"), 0.0),
            "transaction_id": str(
                payload.get("salary_transaction_id")
                or salary_audit.get("salary_transaction_id")
                or ""
            ),
            "failure_reason": str(salary_audit.get("failure_reason") or ""),
            "salary_payment_status": str(payload.get("salary_payment_status") or ""),
        },
    )


def _assert_no_active_main_shift(work_state: dict[str, Any], *, action_key: str) -> None:
    if not bool(work_state.get("main_shift_active_flag")):
        return
    shift_end_label = (
        str(work_state.get("shift_end_time_label") or "").strip()
        or str(work_state.get("scheduled_shift_end_label") or "").strip()
        or "the scheduled Houston end time"
    )
    if action_key == "work_shift":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Main shift is already active and ends at {shift_end_label}."
            ),
        )
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            f"Main shift is still active. Post-shift actions unlock after {shift_end_label}."
        ),
    )


def _execution_state_snapshot(db: Session, player: Player) -> dict[str, Any]:
    work_state = build_work_state_payload(db, player)
    canonical_main_job = normalize_main_job_key(getattr(player, "main_job", None), allow_aliases=True)
    return {
        "current_day": _current_game_day(db),
        "last_settled_day": _safe_int(getattr(player, "last_settled_day", 0), 0),
        "hours_available": _safe_int(getattr(player, "hours_available", getattr(player, "available_hours", 0)), 0),
        "main_job_hours_today": _safe_int(getattr(player, "main_job_hours_today", 0), 0),
        "side_job_hours_today": _safe_int(getattr(player, "side_job_hours_today", 0), 0),
        "total_hours_worked_today": _safe_int(getattr(player, "total_hours_worked_today", 0), 0),
        "work_actions_today": _safe_int(getattr(player, "work_actions_today", 0), 0),
        "cash_xgp": _safe_float(getattr(player, "cash_xgp", getattr(player, "cash", 0)), 0),
        "stress": _safe_int(getattr(player, "stress", 0), 0),
        "health": _safe_int(getattr(player, "health", 100), 100),
        "main_job": canonical_main_job or "",
        "work_state": work_state,
    }


def _recovery_action_summary(action_key: str) -> str:
    preset = RECOVERY_ACTION_PRESETS.get(action_key) or {}
    title = str(preset.get("title") or action_key.replace("_", " ").title())
    stress_delta = int(preset.get("stress_delta") or 0)
    health_delta = int(preset.get("health_delta") or 0)
    summary_bits: list[str] = []
    if stress_delta:
        summary_bits.append(f"Stress {stress_delta:+d}")
    if health_delta:
        summary_bits.append(f"Health {health_delta:+d}")
    summary_text = " | ".join(summary_bits) if summary_bits else "No stat change"
    return f"{title} completed. {summary_text}."


def _is_new_player_first_session(player: Player) -> bool:
    return _safe_int(getattr(player, "last_settled_day", None), 0) <= 0


def _first_line(text_value: Any, fallback: str) -> str:
    raw = str(text_value or "").strip()
    if not raw:
        return fallback
    head = raw.splitlines()[0].strip()
    return head or fallback


def _job_options_payload() -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for cfg in sorted(CAREER_CONFIG.values(), key=lambda row: row.display_name):
        company = JOB_COMPANY_MAP.get(
            cfg.job_key,
            {
                "symbol": "GP_CONSUMER",
                "name": "Gold Penny Group",
                "position": cfg.display_name,
            },
        )
        options.append(
            {
                "job_key": cfg.job_key,
                "title": cfg.display_name,
                "monthly_pay_xgp": _safe_float(cfg.base_pay_reference),
                "stability_weight": _safe_float(cfg.stability_weight),
                "performance_weight": _safe_float(cfg.performance_weight),
                "stress_sensitivity": _safe_float(cfg.stress_sensitivity),
                "employer_company_symbol": company["symbol"],
                "employer_company_name": company["name"],
                "position_title": company["position"],
                "default_shift_type": "standard_shift",
                "shift_options": [
                    {
                        "shift_type": shift_type,
                        "label": shift_meta["label"],
                        "window": shift_meta["window"],
                        "hours_worked": shift_meta["hours_worked"],
                    }
                    for shift_type, shift_meta in SHIFT_PROFILES.items()
                ],
            }
        )
    return options


def _starter_daily_brief(current_job: str | None) -> str:
    if current_job:
        return (
            f"Day 1 starter lane: run one {current_job.replace('_', ' ')} shift, "
            "then check pressure before ending the day."
        )
    return (
        "Day 1 starter lane: choose your first job, run one low-risk action, "
        "then review cash and stress before settlement."
    )


def _build_action_hub_payload(player: Player, *, work_state: dict[str, Any]) -> dict[str, Any]:
    current_job = normalize_main_job_key((work_state or {}).get("authoritative_current_job_id"), allow_aliases=True) or ""
    job_sync_status = str((work_state or {}).get("job_sync_status") or "").strip().lower()
    job_sync_message = str((work_state or {}).get("job_sync_warning_message") or "").strip()
    has_job = bool(current_job)
    is_first_session = _is_new_player_first_session(player)
    as_of_date = str((work_state or {}).get("current_houston_date") or date.today().isoformat())
    job_options = _job_options_payload()
    default_switch_job_key = next(
        (
            str(option.get("job_key") or "")
            for option in job_options
            if normalize_main_job_key(option.get("job_key"), allow_aliases=True)
            and normalize_main_job_key(option.get("job_key"), allow_aliases=True) != current_job
        ),
        None,
    )
    rideshare_state = (
        (work_state.get("rideshare_state") if isinstance(work_state.get("rideshare_state"), dict) else None)
        or {}
    )
    testing_mode = (
        work_state.get("testing_mode")
        if isinstance(work_state.get("testing_mode"), dict)
        else {}
    )
    testing_mode_enabled = bool(testing_mode.get("enabled"))
    weekend_rideshare_only = bool(testing_mode.get("weekend_rideshare_only"))
    overtime_shift_available = bool(testing_mode.get("overtime_shift_available"))
    shifts_completed_today = int(testing_mode.get("shifts_completed_today") or 0)
    max_daily_main_shifts = int(testing_mode.get("max_daily_main_shifts") or 1)
    next_shift_number_available = testing_mode.get("next_shift_number_available")
    shift_length_label = str(testing_mode.get("shift_length_label") or "").strip() or "Standard shift schedule"
    overtime_multiplier = float(testing_mode.get("second_shift_overtime_multiplier") or 1.5)
    shift_active = bool(work_state.get("main_shift_active_flag"))
    shift_completed_today = bool(work_state.get("shift_completed_today"))
    missed_shift_today = bool(work_state.get("missed_shift_today"))
    no_shift_scheduled = bool(work_state.get("no_shift_scheduled"))
    is_weekend = bool(work_state.get("is_weekend"))
    rideshare_available = bool(rideshare_state.get("can_rideshare"))
    rideshare_unlocked = bool(work_state.get("rideshare_unlocked"))
    shift_end_label = str(work_state.get("scheduled_shift_end_label") or "shift end").strip()
    rideshare_unlock_reason = (
        f"Unavailable during active work shift until {work_state.get('shift_end_time_label') or work_state.get('scheduled_shift_end_label') or 'shift completion'}."
        if shift_active
        else (
            "Ride Share is available all day because it is the weekend."
            if is_weekend
            else (
                "Ride Share is available because you do not have a scheduled shift today."
                if no_shift_scheduled
                else (
                    "Ride Share is available now."
                    if rideshare_unlocked
                    else f"Ride Share becomes available after {shift_end_label}."
                )
            )
        )
    )
    backend_rideshare_reason = str(
        work_state.get("rideshare_block_reason")
        or rideshare_state.get("block_reason")
        or rideshare_state.get("reason")
        or ""
    ).strip()
    if backend_rideshare_reason:
        rideshare_unlock_reason = backend_rideshare_reason
    recovery_state = (
        work_state.get("recovery_state")
        if isinstance(work_state.get("recovery_state"), dict)
        else {}
    )
    rest_action_state = next(
        (
            item
            for item in list(recovery_state.get("actions") or [])
            if str(item.get("action_key") or "").strip().lower() == "rest"
        ),
        {},
    )

    recommended_actions: list[dict[str, Any]] = []
    available_actions: list[dict[str, Any]] = []
    blocked_actions: list[dict[str, Any]] = []
    top_tradeoffs: list[str] = []
    next_risk_warnings: list[str] = []
    current_job_display_name = str(work_state.get("current_job_display_name") or _job_display_name(current_job))

    work_shift_title = "Work Shift"
    work_shift_description = f"Use your current role ({current_job_display_name}) for stable day-1 cash."
    work_shift_tradeoffs = ["Consumes time units but improves short-term cash safety."]
    work_shift_blockers: list[str] = []
    if testing_mode_enabled:
        if weekend_rideshare_only:
            work_shift_title = "Weekend Ride Share Only"
            work_shift_description = "Weekend testing rule active. No required main shift today - rideshare only."
            work_shift_blockers = ["Weekend testing rule active. No required main shift today - rideshare only."]
        elif overtime_shift_available:
            work_shift_title = "Start Overtime Shift"
            work_shift_description = (
                f"Shift {int(next_shift_number_available or 2)}/{max_daily_main_shifts} available for {current_job_display_name}. "
                f"Overtime pays {overtime_multiplier:.1f}x."
            )
            work_shift_tradeoffs = ["Higher pay, but stress and fatigue rise faster on overtime."]
        else:
            next_shift_number = int(next_shift_number_available or max(1, shifts_completed_today + 1))
            work_shift_title = (
                f"Start Shift {next_shift_number}"
                if max_daily_main_shifts > 1
                else "Start Shift 1"
            )
            work_shift_description = (
                f"Testing mode active. {current_job_display_name} shifts run for {shift_length_label}."
            )
            work_shift_tradeoffs = [f"Shift length: {shift_length_label}."]

    if has_job and is_weekend and weekend_rideshare_only:
        blocked_actions.append(
            {
                "action_key": "work_shift",
                "title": work_shift_title,
                "description": work_shift_description,
                "status": "blocked",
                "blockers": work_shift_blockers or ["Weekend testing rule active. No required main shift today - rideshare only."],
                "tradeoffs": work_shift_tradeoffs,
                "warnings": [f"Rideshare cap today: {int((testing_mode or {}).get('rideshare_cap_today') or 18)} trips."],
                "confidence_level": "high",
                "parameters": {
                    "job_name": current_job,
                    "shift_type": "standard_shift",
                    "hours_worked": SHIFT_PROFILES["standard_shift"]["hours_worked"],
                    "testing_mode": testing_mode,
                },
            }
        )
    elif has_job and is_weekend:
        available_actions.append(
            {
                "action_key": "work_shift",
                "title": work_shift_title if testing_mode_enabled else "Weekend Shift",
                "description": (
                    work_shift_description
                    if testing_mode_enabled
                    else (
                        f"Your {current_job_display_name} role has no required shift today. "
                        "Work is optional on weekends."
                    )
                ),
                "status": "available",
                "blockers": [],
                "tradeoffs": work_shift_tradeoffs if testing_mode_enabled else ["Weekend time is better for flexible side income unless you want routine pay."],
                "warnings": [],
                "confidence_level": "medium",
                "parameters": {
                    "job_name": current_job,
                    "shift_type": "standard_shift",
                    "hours_worked": SHIFT_PROFILES["standard_shift"]["hours_worked"],
                    "testing_mode": testing_mode,
                    "shift_options": [
                        {
                            "shift_type": shift_type,
                            "label": shift_meta["label"],
                            "window": shift_meta["window"],
                            "hours_worked": shift_meta["hours_worked"],
                        }
                        for shift_type, shift_meta in SHIFT_PROFILES.items()
                    ],
                },
            }
        )
    elif has_job and not shift_active and not shift_completed_today and not missed_shift_today:
        recommended_actions.append(
            {
                "action_key": "work_shift",
                "title": work_shift_title,
                "description": work_shift_description,
                "status": "recommended",
                "blockers": [],
                "tradeoffs": work_shift_tradeoffs,
                "warnings": [],
                "confidence_level": "high",
                "parameters": {
                    "job_name": current_job,
                    "shift_type": "standard_shift",
                    "hours_worked": SHIFT_PROFILES["standard_shift"]["hours_worked"],
                    "testing_mode": testing_mode,
                    "shift_options": [
                        {
                            "shift_type": shift_type,
                            "label": meta["label"],
                            "window": meta["window"],
                            "hours_worked": meta["hours_worked"],
                        }
                        for shift_type, meta in SHIFT_PROFILES.items()
                    ],
                },
            }
        )
    elif has_job and overtime_shift_available:
        recommended_actions.append(
            {
                "action_key": "work_shift",
                "title": work_shift_title,
                "description": work_shift_description,
                "status": "recommended",
                "blockers": [],
                "tradeoffs": work_shift_tradeoffs,
                "warnings": [f"Overtime multiplier: {overtime_multiplier:.1f}x"],
                "confidence_level": "high",
                "parameters": {
                    "job_name": current_job,
                    "shift_type": "standard_shift",
                    "hours_worked": SHIFT_PROFILES["standard_shift"]["hours_worked"],
                    "testing_mode": testing_mode,
                },
            }
        )
    elif has_job:
        blocked_actions.append(
            {
                "action_key": "work_shift",
                "title": work_shift_title,
                "description": (
                    "Weekend testing rule active. No required main shift today - rideshare only."
                    if weekend_rideshare_only
                    else (
                        f"Your main shift is active until {work_state.get('shift_ends_at')}."
                        if shift_active
                        else (
                            f"Today's scheduled window ended at {shift_end_label}."
                            if missed_shift_today
                            else (
                                "Daily shift limit reached."
                                if bool((testing_mode or {}).get("daily_shift_limit_reached"))
                                else "Today's main shift is already completed."
                            )
                        )
                    )
                ),
                "status": "blocked",
                "blockers": [
                    (
                        "Weekend testing rule active. No required main shift today - rideshare only."
                        if weekend_rideshare_only
                        else (
                            f"Main shift is active until {work_state.get('shift_ends_at') or 'Houston shift end'}."
                            if shift_active
                            else (
                                f"Today's shift window has ended. Ride Share unlocks after {shift_end_label}."
                                if missed_shift_today
                                else (
                                    "Daily shift limit reached."
                                    if bool((testing_mode or {}).get("daily_shift_limit_reached"))
                                    else "You have already completed your main shift today."
                                )
                            )
                        )
                    )
                ],
                "tradeoffs": [],
                "warnings": [],
                "confidence_level": "high",
                "parameters": {
                    "job_name": current_job,
                    "shift_type": "standard_shift",
                    "hours_worked": SHIFT_PROFILES["standard_shift"]["hours_worked"],
                    "testing_mode": testing_mode,
                },
            }
        )

    blocked_actions.append(
        {
            "action_key": "switch_job",
            "title": "Job Market",
            "description": (
                "Open the Job Market panel to review roles, certifications, and training before switching."
            ),
            "status": "blocked",
            "blockers": [
                (
                    f"Finish your active shift first (ends {work_state.get('shift_end_time_label') or work_state.get('scheduled_shift_end_label') or 'at shift end'}), then switch from Job Market."
                    if shift_active
                    else "Use the Job Market panel to choose a role or start certification training."
                )
            ],
            "tradeoffs": ["Job changes can alter stress, pay growth, and promotion pace."],
            "warnings": [],
            "confidence_level": "high",
            "parameters": {
                "job_options": job_options,
                "current_job_key": current_job or None,
                "new_job_key": default_switch_job_key,
                "shift_type": "standard_shift",
            },
        }
    )

    if not has_job:
        blocked_actions.append(
            {
                "action_key": "work_shift",
                "title": "Work Shift",
                "description": (
                    "Your job data is syncing. Please retry in a moment."
                    if job_sync_status == "repair_needed"
                    else "Complete job selection first to start earning from shifts."
                ),
                "status": "blocked",
                "blockers": [
                    (
                        job_sync_message
                        or "Your job data is syncing. Please retry in a moment."
                    )
                    if job_sync_status == "repair_needed"
                    else "You don't have a job yet. Choose a job in Job Market to start earning."
                ],
                "tradeoffs": [],
                "warnings": [],
                "confidence_level": "unknown",
                "parameters": {},
            }
        )

    (blocked_actions if shift_active else available_actions).append(
        {
            "action_key": "study",
            "title": "Skill Training",
            "description": "Invest 2 hours in career growth for better long-term outcomes.",
            "status": "blocked" if shift_active else "available",
            "blockers": ([f"Training unlocks after the active shift ends at {work_state.get('shift_ends_at')}."] if shift_active else []),
            "tradeoffs": ["No immediate cash today."],
            "warnings": [],
            "confidence_level": "medium",
            "parameters": {"training_hours": 2},
        }
    )
    rest_status = "available" if bool(rest_action_state.get("available")) else "blocked"
    rest_blockers = []
    if rest_status != "available":
        rest_blockers = [str(rest_action_state.get("block_reason") or "Recovery action unavailable.")]
    rest_remaining = int(rest_action_state.get("remaining") or 0)
    rest_category_remaining = int(recovery_state.get("category_remaining") or 0)
    rest_payload = {
        "action_key": "rest",
        "title": "Rest",
        "description": "Lower stress before settlement without burning the whole recovery category.",
        "status": rest_status,
        "blockers": rest_blockers,
        "tradeoffs": ["No direct income this action."],
        "warnings": [
            f"Rest remaining today: {rest_remaining}.",
            f"Recovery actions remaining today: {rest_category_remaining}.",
        ],
        "confidence_level": "high",
        "parameters": {},
    }
    (available_actions if rest_status == "available" else blocked_actions).append(rest_payload)

    debt_now = max(0.0, _safe_float(getattr(player, "debt_xgp", 0), 0.0))
    cash_now = max(0.0, _safe_float(getattr(player, "cash", 0), 0.0))
    max_payable = round(min(cash_now, debt_now), 2)
    debt_action = {
        "action_key": "debt_payment",
        "title": "Pay Debt",
        "description": "Reduce debt directly from current cash.",
        "status": "available" if max_payable > 0 and not shift_active else "blocked",
        "blockers": (
            [f"Finish your active shift first (ends {work_state.get('shift_end_time_label') or work_state.get('scheduled_shift_end_label') or 'at shift end'})."]
            if shift_active
            else ([] if max_payable > 0 else ["Pay Debt is available only when both cash and debt remain above zero."])
        ),
        "tradeoffs": ["Improves debt pressure without consuming time units."],
        "warnings": [f"Cash {cash_now:.2f} XGP | debt {debt_now:.2f} XGP | max payable {max_payable:.2f} XGP."],
        "confidence_level": "high",
        "parameters": {
            "payment_amount": round(min(50.0, max_payable), 2) if max_payable > 0 else 0.0,
        },
    }
    (available_actions if debt_action["status"] == "available" else blocked_actions).append(debt_action)

    (available_actions if rideshare_available else blocked_actions).append(
        {
            "action_key": "side_income",
            "title": "Ride Share",
            "description": "Flexible emergency income with higher stress volatility.",
            "status": "available" if rideshare_available else "blocked",
            "blockers": [] if rideshare_available else [rideshare_unlock_reason],
            "tradeoffs": ["Variable payout and stress cost."],
            "warnings": ["Use short shifts to avoid stacking stress."],
            "confidence_level": "low",
            "parameters": {"hours_worked": 2},
        }
    )

    current_location_key = str(work_state.get("current_location_key") or "home")
    current_location_label = str(work_state.get("current_location_label") or "Home")
    travel_options = (
        work_state.get("travel_options")
        if isinstance(work_state.get("travel_options"), list)
        else []
    )
    suggested_destination = None
    if travel_options:
        suggested_destination = str(travel_options[0].get("destination_key") or "")
    travel_action_payload = {
        "action_key": "travel",
        "title": "Travel",
        "description": f"Move from {current_location_label} to another location. Travel consumes time.",
        "status": "available",
        "blockers": [],
        "tradeoffs": ["Better locations can improve ride share outcomes but cost time."],
        "warnings": [],
        "confidence_level": "medium",
        "parameters": {
            "from_location_key": current_location_key,
            "destination_key": suggested_destination,
            "travel_options": travel_options,
        },
    }
    if bool(work_state.get("day_settled")):
        travel_action_payload["status"] = "blocked"
        travel_action_payload["blockers"] = ["Day already settled. Start next day to travel."]
        blocked_actions.append(travel_action_payload)
    elif shift_active:
        travel_action_payload["status"] = "blocked"
        travel_action_payload["blockers"] = [
            f"Travel unlocks after the active shift ends at {work_state.get('shift_end_time_label') or work_state.get('scheduled_shift_end_label') or 'shift completion'}."
        ]
        blocked_actions.append(travel_action_payload)
    else:
        available_actions.append(travel_action_payload)

    if shift_active:
        top_tradeoffs.append("Your main shift is in progress. Post-shift actions unlock after completion.")
    elif weekend_rideshare_only:
        top_tradeoffs.append(
            f"Weekend testing rule active. No main shift today - rideshare cap {int((testing_mode or {}).get('rideshare_cap_today') or 18)} trips."
        )
    elif is_weekend:
        top_tradeoffs.append("Weekend rules are active. Your main shift is optional and ride share is open all day.")
    elif has_job:
        top_tradeoffs.append("Use one cash-positive shift before optional upside actions.")
    else:
        top_tradeoffs.append("Pick a first job first so day-1 work actions unlock.")
    if testing_mode_enabled:
        top_tradeoffs.append(f"Testing mode active. Shift length: {shift_length_label}.")
    top_tradeoffs.append("Protect stress and health before ending the day.")

    if _safe_int(player.stress, 0) >= 65:
        next_risk_warnings.append("Stress is elevated. Mix recovery into your next move.")
    if _safe_float(player.debt_xgp, 0) > max(200.0, _safe_float(player.cash_xgp, 0)):
        next_risk_warnings.append("Debt pressure is high relative to cash buffer.")
    if not bool(work_state.get("market_data_available", True)):
        next_risk_warnings.insert(
            0,
            str(
                work_state.get("market_data_message")
                or "Market data temporarily unavailable. Core dashboard loaded with limited economy data."
            ),
        )

    return {
        "player_id": str(player.id),
        "as_of_date": as_of_date,
        "recommended_actions": recommended_actions,
        "available_actions": available_actions,
        "blocked_actions": blocked_actions,
        "top_tradeoffs": top_tradeoffs,
        "next_risk_warnings": next_risk_warnings,
        "work_state": work_state,
        "debug_meta": {
            "new_player_first_session": is_first_session,
            "has_starter_job_selected": has_job,
            "current_job_key": current_job or None,
            "job_options_count": len(job_options),
            "work_state": work_state,
            "rideshare_available": rideshare_available,
            "rideshare_state": rideshare_state,
            "can_rideshare": bool(work_state.get("can_rideshare", rideshare_available)),
            "rideshare_block_reason": backend_rideshare_reason or None,
            "degraded_sections": list(work_state.get("degraded_sections") or []),
            "market_data_available": bool(work_state.get("market_data_available", True)),
            "market_data_message": work_state.get("market_data_message"),
            "testing_mode": testing_mode,
            "trips_today": int(work_state.get("trips_today") or rideshare_state.get("trips_today") or 0),
            "trips_remaining": int(work_state.get("trips_remaining") or rideshare_state.get("remaining_trips") or 0),
            "remaining_time_units": int(work_state.get("remaining_time_units") or work_state.get("hours_available") or 0),
            "current_location": {
                "key": str(work_state.get("current_location_key") or ""),
                "label": str(work_state.get("current_location_label") or ""),
                "region": str(work_state.get("current_location_region") or ""),
            },
        },
    }


@router.get("/player/{player_id}/dashboard")
def get_gameplay_dashboard(
    player_id: str,
    current_stress: int | None = Query(default=None, ge=0, le=100),
    current_health: int | None = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    logger.info(
        "gameplay.dashboard request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/dashboard"},
    )
    try:
        player = _resolve_player(db, player_id)
        effective_stress = _normalize_optional_stat_override(current_stress)
        effective_health = _normalize_optional_stat_override(current_health)
        work_state = _sync_player_work_state(
            db,
            player,
            current_stress_override=effective_stress,
            current_health_override=effective_health,
        )
        playable = get_playable_player_summary(db, player.id)
    except Exception as exc:
        _raise_gameplay_http_error(exc)

    brief_payload: dict[str, Any] | None = None
    economy_payload: dict[str, Any] | None = None
    job_payload: dict[str, Any] | None = None
    degraded_sections: list[str] = []

    try:
        brief_payload = get_player_latest_daily_brief(db, player.id)
    except Exception:
        brief_payload = None
        degraded_sections.append("daily_brief")

    try:
        economy_payload = build_economy_presentation_summary(db=db, player_id=str(player.id))
    except Exception:
        economy_payload = None
        degraded_sections.append("economy")

    try:
        job_payload = get_player_job_summary(db=db, player_id=str(player.id))
    except Exception:
        job_payload = None
        degraded_sections.append("job_summary")

    is_first_session = _is_new_player_first_session(player)
    authoritative_job = normalize_main_job_key(
        (work_state or {}).get("authoritative_current_job_id"),
        allow_aliases=True,
    ) or ""
    job_sync_status = str((work_state or {}).get("job_sync_status") or "").strip().lower()
    current_job = (
        authoritative_job
        if job_sync_status == "repair_needed"
        else (
            authoritative_job
            or (job_payload or {}).get("current_job_code")
            or playable.get("latest_daily_brief", {}).get("current_job")
            or player.main_job
        )
    )
    current_job = normalize_main_job_key(current_job, allow_aliases=True) or ""
    current_job_display_name = str(
        (work_state or {}).get("current_job_display_name")
        or _job_display_name(current_job)
    )
    current_job_progress = (
        (work_state or {}).get("current_job_progression")
        if isinstance((work_state or {}).get("current_job_progression"), dict)
        else None
    )
    if current_job_progress is not None:
        job_progress = {
            "job_key": str(current_job_progress.get("job_key") or current_job or ""),
            "job_level": int(current_job_progress.get("job_level") or 1),
            "skill_level": int(current_job_progress.get("skill_level") or current_job_progress.get("job_level") or 1),
            "job_xp": int(current_job_progress.get("job_xp") or 0),
            "job_xp_to_next_level": int(current_job_progress.get("job_xp_to_next_level") or 0),
            "xp_total": int(current_job_progress.get("xp_total") or 0),
            "max_job_level": int(current_job_progress.get("max_job_level") or 10),
            "promotion_tier": str(current_job_progress.get("promotion_tier") or "Junior"),
            "shifts_completed": int(current_job_progress.get("shifts_completed") or 0),
            "monthly_pay_xgp": _safe_float(current_job_progress.get("base_salary_xgp"), 0.0),
            "estimated_current_monthly_salary_xgp": _safe_float(
                current_job_progress.get("estimated_current_monthly_salary_xgp"), 0.0
            ),
            "estimated_next_level_monthly_salary_xgp": _safe_float(
                current_job_progress.get("estimated_next_level_monthly_salary_xgp"), 0.0
            ),
            "next_level_salary_increase_pct": _safe_float(
                current_job_progress.get("next_level_salary_increase_pct"), 3.0
            ),
            "salary_preview_note": str(
                current_job_progress.get("salary_preview_note")
                or "Estimated only - live payroll remains unchanged."
            ),
        }
    else:
        employment_state = latest_employment_state(db, player.id)
        job_progress = build_job_progress_payload(
            employment_state,
            fallback_job_key=current_job or None,
            fallback_shift_type="standard_shift",
        )
    economy_risk_overview = _build_economy_risk_overview(
        economy_payload=economy_payload,
        debt_xgp=_safe_float(playable.get("debt_xgp"), _safe_float(player.debt_xgp, 0.0)),
        cash_xgp=_safe_float(playable.get("cash_xgp"), _safe_float(player.cash_xgp, 0.0)),
        shift_status=str((work_state or {}).get("shift_status") or "idle"),
    )

    player_warnings = ((economy_payload or {}).get("player_warnings") or [])[:3]
    player_opportunities = ((economy_payload or {}).get("player_opportunities") or [])[:3]
    top_risks = [
        {"key": f"risk_{idx}", "title": str(item), "description": str(item), "severity": "warning"}
        for idx, item in enumerate(player_warnings)
    ]
    top_opportunities = [
        {"key": f"opportunity_{idx}", "title": str(item), "description": str(item), "severity": "positive"}
        for idx, item in enumerate(player_opportunities)
    ]

    if not top_risks:
        top_risks = [
            {
                "key": "risk_buffer",
                "title": "Protect cash buffer",
                "description": "Avoid high-volatility actions until baseline cash flow is stable.",
                "severity": "warning",
            }
        ]
    if not bool(work_state.get("market_data_available", True)):
        degraded_sections.append("market_data")
        top_risks.insert(
            0,
            {
                "key": "market_data_degraded",
                "title": "Market data temporarily unavailable",
                "description": str(
                    work_state.get("market_data_message")
                    or "Core dashboard loaded with limited economy data."
                ),
                "severity": "warning",
            },
        )
    if "economy" in degraded_sections:
        top_risks.insert(
            0,
            {
                "key": "economy_degraded",
                "title": "Economy data is temporarily unavailable",
                "description": "Dashboard partially loaded. Work and core actions remain available.",
                "severity": "warning",
            },
        )
    if not top_opportunities:
        top_opportunities = [
            {
                "key": "opportunity_shift",
                "title": "Run one cash-positive action",
                "description": "Take one low-risk income action before ending the day.",
                "severity": "info",
            }
        ]

    headline = _first_line(
        (brief_payload or {}).get("headline"),
        "Day 1 starter: stabilize income and protect downside.",
    )
    daily_brief = _first_line(
        (brief_payload or {}).get("summary"),
        _starter_daily_brief(current_job if current_job else None),
    )

    recommended_actions = [
        {
            "action_key": "work_shift" if current_job else "switch_job",
            "title": "Work Shift" if current_job else "Choose Your First Job",
            "reason": (
                f"Use {current_job_display_name} for immediate day-1 cash."
                if current_job
                else "Pick one starter role to unlock reliable day-1 work actions."
            ),
        }
    ]

    dashboard = {
        "player_id": str(player.id),
        "as_of_date": str(
            (brief_payload or {}).get("day")
            or (work_state or {}).get("current_houston_date")
            or date.today().isoformat()
        ),
        "headline": headline,
        "daily_brief": daily_brief,
        "stats": {
            "cash_xgp": _safe_float(playable.get("cash_xgp"), _safe_float(player.cash_xgp, 0.0)),
            "debt_xgp": _safe_float(playable.get("debt_xgp"), _safe_float(player.debt_xgp, 0.0)),
            "net_worth_xgp": _safe_float(playable.get("net_worth_xgp"), _safe_float(player.net_worth_xgp, 0.0)),
            "stress": _safe_int(playable.get("stress"), _safe_int(player.stress, 0)),
            "health": _safe_int(playable.get("health"), _safe_int(player.health, 100)),
            "credit_score": _safe_int(playable.get("credit_score"), _safe_int(player.credit_score, 650)),
            "current_job": current_job or None,
            "current_job_display": current_job_display_name,
            "region_key": str(playable.get("region") or player.region or "suburban"),
        },
        "top_opportunities": top_opportunities,
        "top_risks": top_risks,
        "economy_risk_overview": economy_risk_overview,
        "recommended_actions": recommended_actions,
        "job_progress": job_progress,
        "work_state": work_state,
        "debug_meta": {
            "new_player_first_session": is_first_session,
            "has_starter_job_selected": bool(current_job),
            "authoritative_current_job_id": str((work_state or {}).get("authoritative_current_job_id") or ""),
            "source_brief_available": brief_payload is not None,
            "source_economy_available": economy_payload is not None,
            "degraded_sections": sorted({str(section) for section in degraded_sections if str(section).strip()}),
            "work_state": work_state,
        },
    }
    _log_salary_ui_payload_rendered(
        route="/gameplay/player/{player_id}/dashboard",
        player=player,
        work_state=work_state,
    )
    logger.info(
        "gameplay.dashboard resolved.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "new_player_first_session": is_first_session,
            "has_starter_job_selected": bool(current_job),
            "authoritative_current_job_id": str((work_state or {}).get("authoritative_current_job_id") or ""),
        },
    )
    return dashboard


@router.get("/player/{player_id}/actions")
def get_gameplay_actions(
    player_id: str,
    current_stress: int | None = Query(default=None, ge=0, le=100),
    current_health: int | None = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    logger.info(
        "gameplay.actions request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/actions"},
    )
    try:
        player = _resolve_player(db, player_id)
        work_state = _sync_player_work_state(
            db,
            player,
            current_stress_override=current_stress,
            current_health_override=current_health,
        )
        _log_salary_ui_payload_rendered(
            route="/gameplay/player/{player_id}/actions",
            player=player,
            work_state=work_state,
        )
        payload = _build_action_hub_payload(player, work_state=work_state)
        logger.info(
            "gameplay.actions resolved player action hub.",
            extra={
                "player_id": player_id,
                "resolved_player_id": str(player.id),
                "new_player_first_session": _is_new_player_first_session(player),
                "has_starter_job_selected": bool((work_state or {}).get("authoritative_current_job_id")),
            },
        )
        return payload
    except Exception as exc:
        _raise_gameplay_http_error(exc)


@router.get("/player/{player_id}/action-hub")
def get_gameplay_action_hub_alias(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.action_hub alias route used.",
        extra={
            "player_id": player_id,
            "canonical_alias_route": "/gameplay/player/{player_id}/action-hub",
        },
    )
    return get_gameplay_actions(player_id=player_id, db=db)


@router.get("/player/{player_id}/work-state")
def get_gameplay_work_state(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    work_state = _sync_player_work_state(db, player)
    _log_salary_ui_payload_rendered(
        route="/gameplay/player/{player_id}/work-state",
        player=player,
        work_state=work_state,
    )
    logger.info(
        "gameplay.work_state resolved.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "shift_status": work_state.get("shift_status"),
            "shift_expired": work_state.get("shift_expired"),
            "rideshare_available": work_state.get("rideshare_available"),
        },
    )
    return work_state


@router.post("/player/{player_id}/work-state/finalize")
def post_gameplay_finalize_work_state(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    work_state = finalize_active_main_shift(
        db,
        player=player,
        trigger="frontend_finalize_request",
        require_expired=True,
    )
    _log_salary_ui_payload_rendered(
        route="/gameplay/player/{player_id}/work-state/finalize",
        player=player,
        work_state=work_state,
    )
    logger.info(
        "gameplay.work_state finalize request handled.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "shift_status": work_state.get("shift_status"),
            "main_shift_active_flag": work_state.get("main_shift_active_flag"),
            "rideshare_available": work_state.get("rideshare_available"),
        },
    )
    return work_state


@router.get("/player/{player_id}/city-map")
def get_gameplay_city_map(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    work_state = _sync_player_work_state(db, player)
    current_location_key = ensure_player_location(player)
    snapshot = build_city_map_snapshot(current_location_key=current_location_key)
    return {
        "player_id": str(player.id),
        "current_day": int(work_state.get("current_game_day") or _current_game_day(db)),
        "current_location_key": snapshot.get("current_location_key"),
        "current_location_label": snapshot.get("current_location_label"),
        "current_location_region": snapshot.get("current_location_region"),
        "nodes": snapshot.get("nodes", []),
        "travel_options": snapshot.get("travel_options", []),
        "work_state": work_state,
    }


@router.get("/player/{player_id}/end-of-day-summary")
def get_gameplay_end_of_day_summary(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.end_of_day_summary request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/end-of-day-summary"},
    )
    try:
        player = _resolve_player(db, player_id)
        _sync_player_work_state(db, player)
        payload = get_latest_settlement_summary(db, str(player.id))
        latest_completed_day = int(payload.get("day_number") or 0)
        summary_seen_day = int(getattr(player, "last_seen_settlement_day", 0) or 0)
        summary_seen_for_day = summary_seen_day >= latest_completed_day and latest_completed_day > 0
        should_auto_show = bool(latest_completed_day > 0 and not summary_seen_for_day)

        payload_debug_meta = dict(payload.get("debug_meta") or {})
        payload_debug_meta.update(
            {
                "latest_completed_day": latest_completed_day,
                "summary_seen_day": summary_seen_day,
                "summary_seen_for_day": summary_seen_for_day,
                "should_auto_show_summary": should_auto_show,
                "summary_gate_reason": (
                    "show_unseen_latest_settlement"
                    if should_auto_show
                    else "suppress_already_seen_or_missing"
                ),
            }
        )
        payload["debug_meta"] = payload_debug_meta

        logger.info(
            "gameplay.end_of_day_summary resolved settlement summary.",
            extra={
                "requested_player_id": player_id,
                "resolved_player_id": str(player.id),
                "summary_exists": True,
                "day_number": latest_completed_day,
                "summary_seen_day": summary_seen_day,
                "summary_seen_for_day": summary_seen_for_day,
                "should_auto_show_summary": should_auto_show,
            },
        )
        return payload
    except Exception as exc:
        logger.warning(
            "gameplay.end_of_day_summary unavailable for player.",
            extra={"requested_player_id": player_id, "summary_exists": False, "error": str(exc)},
        )
        _raise_gameplay_http_error(exc)


@router.post("/player/{player_id}/end-of-day-summary/ack")
def acknowledge_gameplay_end_of_day_summary(
    player_id: str,
    body: EndOfDaySummaryAckRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark latest settlement summary as acknowledged for one-time auto-show gating."""
    player = _resolve_player(db, player_id)
    latest = get_latest_settlement_summary(db, str(player.id))
    latest_completed_day = int(latest.get("day_number") or 0)
    target_day = int(body.day_number or latest_completed_day or 0)
    if target_day <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No completed day available to acknowledge.")
    if target_day > latest_completed_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot acknowledge day {target_day}; latest completed day is {latest_completed_day}.",
        )

    current_seen_day = int(getattr(player, "last_seen_settlement_day", 0) or 0)
    player.last_seen_settlement_day = max(current_seen_day, target_day)
    db.commit()
    logger.info(
        "gameplay.end_of_day_summary acknowledged.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "target_day": target_day,
            "latest_completed_day": latest_completed_day,
            "summary_seen_day": int(player.last_seen_settlement_day or 0),
        },
    )
    return {
        "player_id": str(player.id),
        "acknowledged_day": target_day,
        "latest_completed_day": latest_completed_day,
        "summary_seen_day": int(player.last_seen_settlement_day or 0),
    }


@router.get("/player/{player_id}/transactions")
def get_gameplay_transaction_history(
    player_id: str,
    day: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one day of player-facing gameplay ledger activity."""
    player = _resolve_player(db, player_id)
    work_state = _sync_player_work_state(db, player)
    resolved_day = max(1, int(day or work_state.get("current_game_day") or 1))
    rows = list_gameplay_transactions_for_day(db, player=player, day=resolved_day)
    items: list[dict[str, Any]] = []
    total_income = Decimal("0.00")
    total_expense = Decimal("0.00")
    for row in rows:
        amount = _money_decimal(getattr(row, "amount", 0))
        if str(getattr(row, "type", "")).strip().lower() == "income":
            total_income += amount
        else:
            total_expense += abs(amount)
        items.append(
            {
                "id": str(row.id),
                "player_id": str(player.id),
                "day": int(row.day),
                "type": row.type,
                "category": row.category,
                "amount": float(amount),
                "description": row.description,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
        )
    total_income = _money_decimal(total_income)
    total_expense = _money_decimal(total_expense)
    net = _money_decimal(total_income - total_expense)
    return {
        "player_id": str(player.id),
        "day": resolved_day,
        "transactions": items,
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "net": float(net),
    }


@router.post("/player/{player_id}/end-day")
def post_gameplay_end_day(player_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    logger.info(
        "gameplay.end_day request received.",
        extra={"player_id": player_id, "canonical_route": "/gameplay/player/{player_id}/end-day"},
    )
    try:
        player = _resolve_player(db, player_id)
        work_state = _sync_player_work_state(db, player)
        _assert_no_active_main_shift(work_state, action_key="end_day")
        logger.info(
            "gameplay.end_day resolved player.",
            extra={
                "requested_player_id": player_id,
                "resolved_player_id": str(player.id),
                "shift_status": work_state.get("shift_status"),
            },
        )
        return run_player_next_day(db, str(player.id))
    except Exception as exc:
        _raise_gameplay_http_error(exc)


@router.post("/player/{player_id}/actions/preview")
def preview_gameplay_action(
    player_id: str,
    body: GameplayActionPreviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    work_state = _sync_player_work_state(db, player)
    key = str(body.action_key or "").strip().lower()
    params = body.parameters or {}
    shift_type = normalize_shift_type(params.get("shift_type"))
    shift_profile = SHIFT_PROFILES[shift_type]
    hours = max(1, _safe_int(params.get("hours_worked"), int(shift_profile["hours_worked"])))
    training = max(1, _safe_int(params.get("training_hours"), 2))

    base = {
        "player_id": str(player.id),
        "action_key": key,
        "summary": "Preview generated.",
        "expected_cash_impact": {"label": "Cash", "direction": "flat", "amount": 0, "text": "0"},
        "expected_stress_impact": {"label": "Stress", "direction": "flat", "amount": 0, "text": "0"},
        "expected_health_impact": {"label": "Health", "direction": "flat", "amount": 0, "text": "0"},
        "expected_time_impact": {"label": "Time", "direction": "down", "amount": -hours, "text": f"-{hours} units"},
        "expected_career_impact": {"label": "Career", "direction": "flat", "amount": 0, "text": "No material change"},
        "expected_distress_impact": {"label": "Distress", "direction": "flat", "amount": 0, "text": "No material change"},
        "blockers": [],
        "warnings": [],
        "confidence_level": "medium",
        "debug_meta": {"preview_route": "canonical"},
    }

    if key in {"switch_job", "start_training", "study", "rest", "watch_tv", "watch_movie", "read_book", "jogging", "side_income", "travel"} and bool(work_state.get("main_shift_active_flag")):
        base["blockers"] = [
            f"Main shift is active until {work_state.get('shift_end_time_label') or work_state.get('scheduled_shift_end_label') or 'shift completion'}."
        ]
        base["warnings"] = ["Refresh after shift completion to unlock this action."]
        base["confidence_level"] = "high"
        return base

    if key == "work_shift":
        base["summary"] = "Work shift should improve cash and add moderate stress."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "up", "amount": 65 * hours, "text": f"+~{65 * hours} xgp"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": max(1, hours), "text": f"+{max(1, hours)}"}
        base["expected_health_impact"] = {"label": "Health", "direction": "down", "amount": -max(0, hours // 4), "text": f"-{max(0, hours // 4)}"}
        base["debug_meta"] = {
            "preview_route": "canonical",
            "shift_type": shift_type,
            "shift_window": shift_profile["window"],
            "shift_label": shift_profile["label"],
            "work_state": work_state,
        }
    elif key == "switch_job":
        base["summary"] = "Switching jobs changes pay trajectory and stress profile."
        base["expected_career_impact"] = {"label": "Career", "direction": "mixed", "text": "Role and progression path update"}
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
    elif key == "start_training":
        cert_key = str(params.get("certification_key") or params.get("track_key") or "").strip().lower()
        cert_meta = CERTIFICATION_CATALOG.get(cert_key, {})
        cert_name = str(cert_meta.get("display_name") or cert_key.replace("_", " ").title() or "Certification")
        cert_cost = int(cert_meta.get("cost_xgp") or 0)
        cert_days = int(cert_meta.get("required_days") or 0)
        base["summary"] = f"Start {cert_name} training to unlock the required job path."
        base["expected_cash_impact"] = {
            "label": "Cash",
            "direction": "down" if cert_cost > 0 else "flat",
            "amount": -cert_cost if cert_cost > 0 else 0,
            "text": f"-{cert_cost} XGP" if cert_cost > 0 else "0 XGP",
        }
        base["expected_time_impact"] = {"label": "Time", "direction": "down", "amount": -1, "text": "-1 units"}
        base["expected_career_impact"] = {
            "label": "Career",
            "direction": "up",
            "amount": cert_days,
            "text": f"Training plan started ({cert_days} in-game days)",
        }
    elif key == "study":
        base["summary"] = "Training improves long-term growth with no immediate cash."
        base["expected_career_impact"] = {"label": "Career", "direction": "up", "amount": training, "text": f"+{training} training hours"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": 1, "text": "+1"}
    elif key == "side_income":
        base["summary"] = "Ride share adds variable cash with stress tradeoff."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "up", "amount": 20 * hours, "text": f"+~{20 * hours} xgp"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": max(1, hours), "text": f"+{max(1, hours)}"}
    elif resolve_recovery_action_key(key, params):
        recovery_key = str(resolve_recovery_action_key(key, params) or "")
        recovery_preset = RECOVERY_ACTION_PRESETS[recovery_key]
        base["summary"] = f"{recovery_preset['title']} lowers stress without consuming the whole day."
        base["expected_stress_impact"] = {
            "label": "Stress",
            "direction": "down",
            "amount": int(recovery_preset["stress_delta"]),
            "text": str(int(recovery_preset["stress_delta"])),
        }
        base["expected_health_impact"] = {
            "label": "Health",
            "direction": "up" if int(recovery_preset["health_delta"]) > 0 else "flat",
            "amount": int(recovery_preset["health_delta"]),
            "text": (
                f"+{int(recovery_preset['health_delta'])}"
                if int(recovery_preset["health_delta"]) > 0
                else "0"
            ),
        }
        base["expected_time_impact"] = {
            "label": "Time",
            "direction": "down",
            "amount": -int(recovery_preset["time_cost_units"]),
            "text": f"-{int(recovery_preset['time_cost_units'])} units",
        }
    elif key == "eat_meal":
        meal_type = str(params.get("meal_type") or "meal").strip().lower()
        base["summary"] = f"Eating {meal_type} costs 6 XGP and restores health and reduces stress."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "down", "amount": -6, "text": "-6 XGP"}
        base["expected_health_impact"] = {"label": "Health", "direction": "up", "amount": 2, "text": "+2"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "down", "amount": -2, "text": "-2"}
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
    elif key == "quick_loan":
        raw_amount = max(100, min(500, int(params.get("loan_amount") or 200)))
        due = round(raw_amount * 1.15, 2)
        base["summary"] = f"Borrow {raw_amount} XGP now and owe {due} XGP (15% interest)."
        base["expected_cash_impact"] = {"label": "Cash", "direction": "up", "amount": raw_amount, "text": f"+{raw_amount} XGP"}
        base["expected_stress_impact"] = {"label": "Stress", "direction": "up", "amount": 5, "text": "+5"}
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
        base["warnings"] = [f"You will owe {due} XGP total. Pay before weekly settlement to avoid credit damage."]
    elif key == "travel":
        source_key = ensure_player_location(player)
        destination_key = normalize_location_key(
            params.get("destination_key") or params.get("to_location_key") or params.get("location_key")
        )
        travel_rule = get_travel_rule(source_key, destination_key)
        if destination_key == source_key:
            base["summary"] = "You are already at that location."
            base["blockers"] = ["Select a different destination."]
            base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
        else:
            time_cost = int(travel_rule.time_cost_units)
            stress_delta = int(travel_rule.stress_delta)
            cash_cost = float(travel_rule.cash_cost_xgp)
            base["summary"] = (
                f"Travel from {get_location_label(source_key)} to {get_location_label(destination_key)}."
            )
            base["expected_time_impact"] = {
                "label": "Time",
                "direction": "down",
                "amount": -time_cost,
                "text": f"-{time_cost} time unit{'s' if time_cost != 1 else ''}",
            }
            base["expected_stress_impact"] = {
                "label": "Stress",
                "direction": "up" if stress_delta > 0 else "flat",
                "amount": stress_delta,
                "text": f"{'+' if stress_delta > 0 else ''}{stress_delta}",
            }
            base["expected_cash_impact"] = {
                "label": "Cash",
                "direction": "down" if cash_cost > 0 else "flat",
                "amount": -cash_cost if cash_cost > 0 else 0,
                "text": f"-{cash_cost:.2f} XGP" if cash_cost > 0 else "0 XGP",
            }
            if _safe_int(getattr(player, "hours_available", 0), 0) < time_cost:
                base["blockers"] = [f"Not enough time left today for travel ({time_cost} units needed)."]
            elif cash_cost > 0 and _safe_float(getattr(player, "cash", 0), 0.0) < cash_cost:
                base["blockers"] = [f"Not enough cash for travel cost ({cash_cost:.2f} XGP)."]
            else:
                base["warnings"] = [
                    (
                        f"Route: {travel_rule.route_label}. "
                        f"Destination region: {get_location_region(destination_key)}."
                    )
                ]
    elif key == "debt_payment":
        debt_now = max(0.0, _safe_float(getattr(player, "debt_xgp", 0), 0.0))
        cash_now = max(0.0, _safe_float(getattr(player, "cash", 0), 0.0))
        max_payable = round(min(cash_now, debt_now), 2)
        requested_amount = _safe_float(params.get("payment_amount"), max_payable if max_payable > 0 else 10.0)
        suggested_amount = round(max(0.01, min(max_payable, requested_amount)), 2) if max_payable > 0 else 0.0
        base["summary"] = "Pay debt directly to reduce pressure and improve cash clarity."
        base["expected_cash_impact"] = {
            "label": "Cash",
            "direction": "down",
            "amount": -suggested_amount,
            "text": f"-{suggested_amount:.2f} XGP",
        }
        base["expected_distress_impact"] = {
            "label": "Distress",
            "direction": "down",
            "amount": suggested_amount,
            "text": f"Debt -{suggested_amount:.2f} XGP",
        }
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}
        if max_payable <= 0:
            base["blockers"] = ["No payable debt amount right now. Add cash or wait for a debt balance."]
        else:
            base["warnings"] = [
                f"Current cash {cash_now:.2f} XGP | debt {debt_now:.2f} XGP | max payable now {max_payable:.2f} XGP."
            ]
    elif key == "select_housing":
        housing_type = str(params.get("housing_type") or "suburban").lower()
        HOUSING_INFO = {
            "suburban": "Weekly rent 80 XGP, gas 40 XGP, lower stress.",
            "downtown": "Weekly rent 140 XGP, gas 20 XGP, higher stress.",
        }
        base["summary"] = f"{housing_type.capitalize()} housing: {HOUSING_INFO.get(housing_type, '')}"
        base["expected_time_impact"] = {"label": "Time", "direction": "flat", "amount": 0, "text": "No time cost"}

    return base


@router.post("/player/{player_id}/actions/execute")
def execute_gameplay_action(
    player_id: str,
    body: GameplayActionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    player = _resolve_player(db, player_id)
    action_key = str(body.action_key or "").strip().lower()
    params = body.parameters or {}
    work_state = _sync_player_work_state(db, player)
    execution_state = _execution_state_snapshot(db, player)
    logger.info(
        "gameplay.actions.execute request received.",
        extra={
            "requested_player_id": player_id,
            "resolved_player_id": str(player.id),
            "action_key": action_key,
            "action_payload": params,
            "execution_state": execution_state,
        },
    )

    if action_key == "switch_job":
        _assert_no_active_main_shift(work_state, action_key=action_key)
        target = str(params.get("new_job_key") or params.get("job_key") or params.get("target_job") or "").strip()
        if not target:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not switch jobs because no destination job was selected.")
        shift_type = normalize_shift_type(params.get("shift_type"))
        try:
            logger.info(
                "gameplay.actions.execute switch_job validating payload.",
                extra={
                    "player_id": str(player.id),
                    "incoming_switch_job_payload": params,
                    "previous_main_job": normalize_main_job_key(player.main_job, allow_aliases=True),
                    "resolved_new_job_key": normalize_main_job_key(target, allow_aliases=False),
                },
            )
            result = switch_player_job(db, player_id, target)
            db.refresh(player)
            job_progress = upsert_employment_foundation(
                db,
                player=player,
                settled_day=max(1, _safe_int(getattr(player, "last_settled_day", None), 0) + 1),
                job_key=result.get("new_job_key"),
                shift_type=shift_type,
            )
            db.commit()
            logger.info(
                "gameplay.actions.execute switch_job succeeded.",
                extra={
                    "player_id": str(player.id),
                    "target_job": result.get("new_job_key"),
                    "updated_main_job": normalize_main_job_key(player.main_job, allow_aliases=True),
                    "persistence_success": True,
                    "job_progress": job_progress,
                },
            )
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": str(result.get("message") or "Job switched."),
                "result_summary": str(result.get("message") or f"Switched to {target}."),
                "time_cost_units": 1,
                "cash_delta_xgp": 0.0,
                "stress_delta": 0,
                "health_delta": 0,
                "raw_result": {
                    **result,
                    "main_job_key": str(result.get("main_job_key") or result.get("new_job_key") or ""),
                    "current_job_label": str(
                        result.get("current_job_label")
                        or _job_display_name(str(result.get("main_job_key") or result.get("new_job_key") or ""))
                    ),
                    "work_state": build_work_state_payload(db, player),
                    "employer_company_symbol": JOB_COMPANY_MAP.get(str(result.get("new_job_key") or ""), {}).get("symbol"),
                    "employer_company_name": JOB_COMPANY_MAP.get(str(result.get("new_job_key") or ""), {}).get("name"),
                    "position_title": JOB_COMPANY_MAP.get(str(result.get("new_job_key") or ""), {}).get("position"),
                    "shift_type": shift_type,
                    "job_progress": job_progress,
                },
            }
        except Exception as exc:
            db.rollback()
            logger.exception(
                "gameplay.actions.execute switch_job failed.",
                extra={
                    "player_id": str(player.id),
                    "requested_player_id": player_id,
                    "target_job": target,
                    "resolved_new_job_key": normalize_main_job_key(target, allow_aliases=False),
                    "previous_main_job": normalize_main_job_key(player.main_job, allow_aliases=True),
                    "persistence_success": False,
                    "action_payload": params,
                },
            )
            _raise_gameplay_http_error(exc)

    if action_key == "start_training":
        _assert_no_active_main_shift(work_state, action_key=action_key)
        certification_key = str(
            params.get("certification_key") or params.get("track_key") or ""
        ).strip().lower()
        if not certification_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not start training because no certification was selected.",
            )
        try:
            result = start_certification_track(db, player_id, certification_key)
            db.commit()
            db.refresh(player)
            cert_label = str(
                (CERTIFICATION_CATALOG.get(certification_key, {}) or {}).get("display_name")
                or certification_key.replace("_", " ").title()
            )
            remaining_days = int(result.get("training_days_remaining") or 0)
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": str(result.get("message") or f"Training started for {cert_label}."),
                "result_summary": (
                    f"Training started: {cert_label} - {remaining_days} day{'s' if remaining_days != 1 else ''} remaining"
                ),
                "time_cost_units": 1,
                "cash_delta_xgp": -_safe_float(result.get("cost_xgp"), 0.0),
                "stress_delta": 0,
                "health_delta": 0,
                "raw_result": {
                    **result,
                    "certification_key": certification_key,
                    "work_state": build_work_state_payload(db, player),
                },
            }
        except Exception as exc:
            db.rollback()
            _raise_gameplay_http_error(exc)

    if action_key == "work_shift":
        shift_type = normalize_shift_type(params.get("shift_type"))
        shift_profile = SHIFT_PROFILES[shift_type]
        requested_hours = _safe_int(params.get("hours_worked"), int(shift_profile["hours_worked"]))
        hours_worked = max(1, min(8, requested_hours))
        job_name = normalize_main_job_key(
            params.get("job_name")
            or (work_state or {}).get("authoritative_current_job_id")
            or player.main_job,
            allow_aliases=True,
        ) or ""
        if not job_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose a job before running work_shift.")
        try:
            logger.info(
                "gameplay.actions.execute work_shift validating payload.",
                extra={
                    "player_id": str(player.id),
                    "incoming_clock_in_payload": params,
                    "current_persisted_main_job": normalize_main_job_key(player.main_job, allow_aliases=True),
                    "resolved_job_name": job_name,
                },
            )
            work_state = start_main_shift(
                db,
                player=player,
                job_name=job_name,
                shift_type=shift_type,
                hours_worked=hours_worked,
            )
            job_progress = build_job_progress_payload(
                latest_employment_state(db, player.id),
                fallback_job_key=job_name,
                fallback_shift_type=shift_type,
            )
            logger.info(
                "gameplay.actions.execute work_shift started backend shift.",
                extra={
                    "player_id": str(player.id),
                    "job_name": job_name,
                    "hours_worked": hours_worked,
                    "shift_started_at": work_state.get("shift_started_at"),
                    "shift_ends_at": work_state.get("shift_ends_at"),
                    "job_progress": job_progress,
                },
            )
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": "Shift clocked in.",
                "result_summary": (
                    f"Clocked in as {str(work_state.get('current_job_display_name') or _job_display_name(job_name))}"
                    f" - Shift ends at {str(work_state.get('shift_end_time_label') or _safe_iso_to_houston_label(work_state.get('shift_ends_at')) or 'scheduled Houston end')}"
                ),
                "time_cost_units": max(1, min(4, hours_worked // 2)),
                "cash_delta_xgp": 0.0,
                "stress_delta": 0,
                "health_delta": 0,
                "raw_result": {
                    "job_name": job_name,
                    "hours_worked": hours_worked,
                    "work_state": work_state,
                    "shift_type": shift_type,
                    "shift_window": shift_profile["window"],
                    "shift_label": shift_profile["label"],
                    "employer_company_symbol": JOB_COMPANY_MAP.get(job_name, {}).get("symbol"),
                    "employer_company_name": JOB_COMPANY_MAP.get(job_name, {}).get("name"),
                    "job_progress": job_progress,
                },
            }
        except ValueError as exc:
            logger.warning(
                "gameplay.actions.execute work_shift rejected.",
                extra={
                    "player_id": str(player.id),
                    "job_name": job_name,
                    "hours_worked": hours_worked,
                    "current_persisted_main_job": normalize_main_job_key(player.main_job, allow_aliases=True),
                    "validation_result": "rejected",
                    "reason": str(exc),
                },
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except Exception as exc:
            db.rollback()
            logger.exception(
                "gameplay.actions.execute work_shift failed.",
                extra={
                    "player_id": str(player.id),
                    "job_name": job_name,
                    "hours_worked": hours_worked,
                    "action_payload": params,
                },
            )
            _raise_gameplay_http_error(exc)

    if action_key == "study":
        _assert_no_active_main_shift(work_state, action_key=action_key)
        training_hours = Decimal(str(max(1, min(4, _safe_int(params.get("training_hours"), 2)))))
        try:
            result = apply_daily_career_progression(
                db=db,
                player_id=player_id,
                training_hours=training_hours,
                commit=False,
            )
            # STEP 93G — +25 XP per 1-hour certification training session,
            # but only for jobs that require certification.
            training_progression: dict | None = None
            training_job_key = normalize_main_job_key(
                (result or {}).get("job_key") or player.main_job,
                allow_aliases=True,
            )
            training_cfg = CAREER_CONFIG.get(training_job_key or "")
            if training_cfg is not None and bool(training_cfg.certification_required):
                sessions = int(training_hours)
                training_progression = award_training_session_xp(
                    db,
                    player_id=player.id,
                    job_key=training_job_key,
                    xp_gain=25 * max(1, sessions),
                )
            db.commit()
            db.refresh(player)
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": "Training logged.",
                "result_summary": "Training completed. Career progression updated.",
                "time_cost_units": int(training_hours),
                "cash_delta_xgp": 0.0,
                "stress_delta": 1,
                "health_delta": 0,
                "raw_result": {
                    **result,
                    "training_progression": training_progression,
                    "work_state": build_work_state_payload(db, player),
                },
            }
        except Exception as exc:
            db.rollback()
            _raise_gameplay_http_error(exc)

    if action_key == "travel":
        _assert_no_active_main_shift(work_state, action_key=action_key)
        if bool(work_state.get("day_settled")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Day already settled. Start next day to travel.",
            )
        from_location_key = ensure_player_location(player)
        destination_key = normalize_location_key(
            params.get("destination_key") or params.get("to_location_key") or params.get("location_key")
        )
        if destination_key == from_location_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="You are already at this location.",
            )

        travel_rule = get_travel_rule(from_location_key, destination_key)
        time_cost_units = int(travel_rule.time_cost_units)
        stress_delta = int(travel_rule.stress_delta)
        travel_cash_cost = Decimal(str(travel_rule.cash_cost_xgp)).quantize(Decimal("0.01"))
        hours_before = _safe_int(getattr(player, "hours_available", 0), 0)
        if hours_before < time_cost_units:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Not enough time left today for travel ({time_cost_units} units needed).",
            )
        cash_before = Decimal(str(_safe_float(getattr(player, "cash", 0), 0.0))).quantize(Decimal("0.01"))
        if travel_cash_cost > Decimal("0.00") and cash_before < travel_cash_cost:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Not enough cash for travel cost ({travel_cash_cost:.2f} XGP).",
            )

        stress_before = _safe_int(getattr(player, "stress", 0), 0)
        player.current_location_key = destination_key  # type: ignore[assignment]
        player.hours_available = max(0, hours_before - time_cost_units)  # type: ignore[assignment]
        player.stress = max(0, min(100, stress_before + stress_delta))
        cash_after = cash_before
        if travel_cash_cost > Decimal("0.00"):
            cash_after = (cash_before - travel_cash_cost).quantize(Decimal("0.01"))
            player.cash = cash_after  # type: ignore[assignment]
            record_gameplay_transaction(
                db,
                player=player,
                day=_current_game_day(db),
                transaction_type="expense",
                category="gas",
                amount=travel_cash_cost,
                description=(
                    f"Travel cost: {get_location_label(from_location_key)} -> "
                    f"{get_location_label(destination_key)}"
                ),
            )
        db.commit()
        db.refresh(player)

        result_summary = (
            f"Traveled from {get_location_label(from_location_key)} to {get_location_label(destination_key)} "
            f"(-{time_cost_units} time unit{'s' if time_cost_units != 1 else ''}"
            f"{', Stress +' + str(stress_delta) if stress_delta > 0 else ''}"
            f"{', -' + format(travel_cash_cost, '.2f') + ' XGP' if travel_cash_cost > Decimal('0.00') else ''})."
        )
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": "Travel completed.",
            "result_summary": result_summary,
            "time_cost_units": time_cost_units,
            "cash_delta_xgp": -float(travel_cash_cost),
            "stress_delta": _safe_int(getattr(player, "stress", 0), stress_before) - stress_before,
            "health_delta": 0,
            "raw_result": {
                "from_location_key": from_location_key,
                "from_location_label": get_location_label(from_location_key),
                "to_location_key": destination_key,
                "to_location_label": get_location_label(destination_key),
                "destination_region": get_location_region(destination_key),
                "travel_time_units": time_cost_units,
                "travel_stress_delta": stress_delta,
                "travel_cash_cost_xgp": float(travel_cash_cost),
                "route_label": travel_rule.route_label,
                "hours_before": hours_before,
                "hours_after": _safe_int(getattr(player, "hours_available", 0), 0),
                "work_state": build_work_state_payload(db, player),
            },
        }

    if action_key == "side_income":
        _assert_no_active_main_shift(work_state, action_key=action_key)
        requested_trips = _safe_int(params.get("trips"), 0)
        if requested_trips not in (1, 3, 5):
            hours_worked = max(1, min(6, _safe_int(params.get("hours_worked"), 1)))
            if hours_worked <= 1:
                requested_trips = 1
            elif hours_worked <= 3:
                requested_trips = 3
            else:
                requested_trips = 5
        try:
            raw_stress_override = params.get("current_stress")
            raw_health_override = params.get("current_health")
            current_stress_override = (
                _normalize_optional_stat_override(_safe_int(raw_stress_override, 0))
                if raw_stress_override is not None
                else None
            )
            current_health_override = (
                _normalize_optional_stat_override(_safe_int(raw_health_override, 0))
                if raw_health_override is not None
                else None
            )
            result = process_rideshare_action(
                db=db,
                player=player,
                trips=requested_trips,
                current_stress=current_stress_override,
                current_health=current_health_override,
            )
            completed_trips = max(0, _safe_int(result.get("trips"), requested_trips))
            time_used = max(1, _safe_int(result.get("time_used"), completed_trips or 1))
            earned = _safe_float(result.get("earned"), _safe_float(result.get("net_income_xgp")))
            mode_used = str(result.get("mode") or result.get("mode_used") or "midday")
            partial_completion = bool(result.get("partial_completion", False))
            completion_note = (
                f" ({completed_trips}/{requested_trips} trips due to remaining time)"
                if partial_completion
                else f" ({completed_trips} trips)"
            )
            logger.info(
                "gameplay.actions.execute side_income succeeded.",
                extra={
                    "player_id": str(player.id),
                    "requested_trips": requested_trips,
                    "completed_trips": completed_trips,
                    "earned_xgp": earned,
                    "mode_used": mode_used,
                    "stress_change": _safe_int(result.get("stress_change")),
                    "health_change": _safe_int(result.get("health_change")),
                },
            )
            return {
                "player_id": str(player.id),
                "action_key": action_key,
                "success": True,
                "message": "Ride share completed.",
                "result_summary": f"Ride share {mode_used}{completion_note}: +{earned:.2f} XGP.",
                "time_cost_units": time_used,
                "cash_delta_xgp": earned,
                "stress_delta": _safe_int(result.get("stress_change")),
                "health_delta": _safe_int(result.get("health_change")),
                "raw_result": {
                    **result,
                    "work_state": build_work_state_payload(db, player),
                },
            }
        except ValueError as exc:
            logger.warning(
                "gameplay.actions.execute side_income rejected.",
                extra={
                    "player_id": str(player.id),
                    "requested_trips": requested_trips,
                    "reason": str(exc),
                },
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except Exception as exc:
            logger.exception(
                "gameplay.actions.execute side_income failed.",
                extra={
                    "player_id": str(player.id),
                    "requested_trips": requested_trips,
                    "action_payload": params,
                },
            )
            _raise_gameplay_http_error(exc)

    resolved_recovery_action = resolve_recovery_action_key(action_key, params)
    if resolved_recovery_action is not None:
        _assert_no_active_main_shift(work_state, action_key=action_key)
        current_day = int(work_state.get("current_game_day") or _current_game_day(db))
        try:
            result = apply_recovery_action(
                db,
                player=player,
                day_number=current_day,
                action_key=action_key,
                parameters=params,
                active_shift=bool(work_state.get("main_shift_active_flag")),
                day_settled=bool(work_state.get("day_settled")),
                is_weekend=bool(work_state.get("is_weekend")),
                side_income_hours_today=_safe_float(work_state.get("side_income_hours_today"), 0.0),
            )
            db.commit()
            db.refresh(player)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except Exception as exc:
            db.rollback()
            _raise_gameplay_http_error(exc)

        return {
            "player_id": str(player.id),
            "action_key": resolved_recovery_action,
            "success": True,
            "message": f"{str(result.get('title') or resolved_recovery_action.replace('_', ' ').title())} complete.",
            "result_summary": _recovery_action_summary(resolved_recovery_action),
            "time_cost_units": int(result.get("time_cost_units") or 0),
            "cash_delta_xgp": 0.0,
            "stress_delta": int(result.get("stress_delta") or 0),
            "health_delta": int(result.get("health_delta") or 0),
            "raw_result": {
                **result,
                "work_state": build_work_state_payload(db, player),
            },
        }

    # ── Step 74: eat_meal ─────────────────────────────────────────────────────
    if action_key == "eat_meal":
        meal_type = str(params.get("meal_type") or "meal").strip().lower()
        current_day = _current_game_day(db)
        latest_work_state = _sync_player_work_state(db, player)
        if bool(latest_work_state.get("day_settled")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Day already settled.",
            )
        if meal_type == "dinner" and bool(latest_work_state.get("dinner_resolved_today")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Meal already completed",
            )
        try:
            result = apply_manual_meal_action(
                db,
                player=player,
                day_number=current_day,
                meal_type=meal_type,
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except Exception as exc:
            db.rollback()
            _raise_gameplay_http_error(exc)

        debt_added = _safe_float(result.get("debt_added_xgp"), 0.0)
        debt_note = f", +{debt_added:.2f} debt" if debt_added > 0 else ""
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"{meal_type.capitalize()} eaten.",
            "result_summary": (
                f"You ate {meal_type} (-{_safe_float(result.get('meal_cost_xgp'), 6.0):.2f} XGP"
                f"{debt_note}, +2 health, -2 stress)."
            ),
            "time_cost_units": 0,
            "cash_delta_xgp": -_safe_float(result.get("cash_used_xgp"), 0.0),
            "stress_delta": _safe_int(result.get("stress_delta"), 0),
            "health_delta": _safe_int(result.get("health_delta"), 0),
            "raw_result": {
                **result,
                "work_state": build_work_state_payload(db, player),
            },
        }

    # ── Step 74: quick_loan ───────────────────────────────────────────────────
    if action_key == "quick_loan":
        raw_amount = _safe_int(params.get("loan_amount"), 200)
        loan_amount = Decimal(str(max(100, min(500, raw_amount))))
        interest_rate = Decimal("0.15")  # 15% flat
        due_amount = (loan_amount * (1 + interest_rate)).quantize(Decimal("0.01"))
        cash_before = Decimal(str(_safe_float(getattr(player, "cash", 0))))
        debt_before = Decimal(str(_safe_float(getattr(player, "debt_xgp", 0))))
        stress_before = _safe_int(player.stress, 0)
        player.cash = cash_before + loan_amount  # type: ignore[assignment]
        player.debt_xgp = debt_before + due_amount  # type: ignore[assignment]
        player.stress = min(100, stress_before + 5)
        db.commit()
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"Borrowed {loan_amount} XGP.",
            "result_summary": f"Quick loan of {loan_amount} XGP received. You owe {due_amount} XGP (15% interest).",
            "time_cost_units": 0,
            "cash_delta_xgp": float(loan_amount),
            "stress_delta": player.stress - stress_before,
            "health_delta": 0,
            "raw_result": {
                "loan_amount_xgp": float(loan_amount),
                "interest_rate": float(interest_rate),
                "due_amount_xgp": float(due_amount),
                "cash_after": float(player.cash),  # type: ignore[arg-type]
                "debt_after": float(player.debt_xgp),  # type: ignore[arg-type]
                "stress_after": _safe_int(player.stress, stress_before),
            },
        }

    # ── Step 74: select_housing ───────────────────────────────────────────────
    if action_key == "debt_payment":
        current_day = _current_game_day(db)
        request_id = _debt_payment_request_id(params)
        if request_id:
            existing_log = _find_existing_debt_payment_log(
                db,
                player_id=player.id,
                request_id=request_id,
            )
            if existing_log is not None:
                metadata: dict[str, Any] = {}
                try:
                    metadata = json.loads(existing_log.metadata_json or "{}")
                except Exception:
                    metadata = {}
                existing_payment_amount = _safe_float(
                    metadata.get("payment_amount_xgp"),
                    _safe_float(getattr(existing_log, "gross_amount", 0), 0.0),
                )
                existing_cash_before = _safe_float(metadata.get("cash_before"), _safe_float(getattr(player, "cash", 0), 0.0))
                existing_cash_after = _safe_float(metadata.get("cash_after"), _safe_float(getattr(player, "cash", 0), 0.0))
                existing_debt_before = _safe_float(metadata.get("debt_before"), _safe_float(getattr(player, "debt_xgp", 0), 0.0))
                existing_debt_after = _safe_float(metadata.get("debt_after"), _safe_float(getattr(player, "debt_xgp", 0), 0.0))
                return {
                    "player_id": str(player.id),
                    "action_key": action_key,
                    "success": True,
                    "message": f"Paid {existing_payment_amount:.2f} XGP toward debt.",
                    "result_summary": (
                        f"Debt payment already processed: -{existing_payment_amount:.2f} XGP cash, "
                        f"debt reduced by {existing_payment_amount:.2f} XGP."
                    ),
                    "time_cost_units": 0,
                    "cash_delta_xgp": -float(existing_payment_amount),
                    "stress_delta": 0,
                    "health_delta": 0,
                    "raw_result": {
                        "payment_amount_xgp": float(existing_payment_amount),
                        "cash_before": existing_cash_before,
                        "cash_after": existing_cash_after,
                        "debt_before": existing_debt_before,
                        "debt_after": existing_debt_after,
                        "request_id": request_id,
                        "idempotent_replay": True,
                        "work_state": build_work_state_payload(db, player),
                    },
                }

        raw_amount = params.get("payment_amount")
        if raw_amount is None:
            raw_amount = params.get("amount")
        try:
            requested_amount = Decimal(str(raw_amount or 0)).quantize(Decimal("0.01"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="payment_amount must be a valid number.",
            )

        if requested_amount <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="payment_amount must be greater than 0.",
            )

        cash_before = Decimal(str(_safe_float(getattr(player, "cash", 0)))).quantize(Decimal("0.01"))
        debt_before = Decimal(str(_safe_float(getattr(player, "debt_xgp", 0)))).quantize(Decimal("0.01"))
        if debt_before <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No current debt to pay.",
            )
        if requested_amount > cash_before:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Not enough cash for this debt payment.",
            )
        if requested_amount > debt_before:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Amount exceeds current debt.",
            )

        player.cash = (cash_before - requested_amount).quantize(Decimal("0.01"))  # type: ignore[assignment]
        player.debt_xgp = (debt_before - requested_amount).quantize(Decimal("0.01"))  # type: ignore[assignment]
        record_gameplay_transaction(
            db,
            player=player,
            day=current_day,
            transaction_type="expense",
            category="debt_payment",
            amount=requested_amount,
            description="Debt payment",
        )
        record_player_transaction(
            db,
            player=player,
            day=current_day,
            transaction_type="debt_payment",
            category="debt_payment",
            gross_amount=requested_amount,
            fee_amount=0,
            net_cash_delta=-requested_amount,
            resulting_cash_balance=player.cash,
            metadata={
                "request_id": request_id or None,
                "payment_amount_xgp": float(requested_amount),
                "cash_before": float(cash_before),
                "cash_after": _safe_float(getattr(player, "cash", 0), 0.0),
                "debt_before": float(debt_before),
                "debt_after": _safe_float(getattr(player, "debt_xgp", 0), 0.0),
                "action_key": action_key,
            },
        )
        pds = (
            db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == player.id,
                PlayerDailyState.day_number == current_day,
            )
            .first()
        )
        if pds is not None:
            pds.debt_payment_xgp = Decimal(str(getattr(pds, "debt_payment_xgp", 0) or 0)) + requested_amount
            pds.debt_payment_paid_xgp = Decimal(str(getattr(pds, "debt_payment_paid_xgp", 0) or 0)) + requested_amount
        db.commit()

        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"Paid {requested_amount:.2f} XGP toward debt.",
            "result_summary": f"Debt payment: -{requested_amount:.2f} XGP cash, debt reduced by {requested_amount:.2f} XGP.",
            "time_cost_units": 0,
            "cash_delta_xgp": -float(requested_amount),
            "stress_delta": 0,
            "health_delta": 0,
            "raw_result": {
                "payment_amount_xgp": float(requested_amount),
                "cash_before": float(cash_before),
                "cash_after": _safe_float(getattr(player, "cash", 0), 0.0),
                "debt_before": float(debt_before),
                "debt_after": _safe_float(getattr(player, "debt_xgp", 0), 0.0),
                "request_id": request_id or None,
                "idempotent_replay": False,
                "work_state": build_work_state_payload(db, player),
            },
        }

    if action_key == "select_housing":
        housing_type = str(params.get("housing_type") or "suburban").strip().lower()
        if housing_type not in ("suburban", "downtown"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="housing_type must be 'suburban' or 'downtown'.",
            )
        player.region = housing_type  # type: ignore[assignment]
        player.housing_region_id = housing_type  # type: ignore[assignment]
        db.commit()
        HOUSING_INFO = {
            "suburban": {"rent_xgp": 80, "stress_modifier": -2, "gas_xgp": 40},
            "downtown": {"rent_xgp": 140, "stress_modifier": +5, "gas_xgp": 20},
        }
        info = HOUSING_INFO[housing_type]
        return {
            "player_id": str(player.id),
            "action_key": action_key,
            "success": True,
            "message": f"Housing set to {housing_type}.",
            "result_summary": (
                f"You chose {housing_type.capitalize()} housing. "
                f"Weekly rent: {info['rent_xgp']} XGP. "
                f"Weekly gas: {info['gas_xgp']} XGP."
            ),
            "time_cost_units": 0,
            "cash_delta_xgp": 0.0,
            "stress_delta": info["stress_modifier"],
            "health_delta": 0,
            "raw_result": {
                "housing_type": housing_type,
                "weekly_rent_xgp": info["rent_xgp"],
                "weekly_gas_xgp": info["gas_xgp"],
                "stress_modifier": info["stress_modifier"],
            },
        }

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported action_key '{action_key}'.",
    )















