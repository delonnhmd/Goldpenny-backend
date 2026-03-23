"""Step 21 deterministic simulation harness for balancing sweeps."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.balance_config import SIMULATION_CONFIG, get_balance_profile_metadata
from app.engine.economy_telemetry_service import compute_daily_economy_health_metrics
from app.engine.exploit_detection_service import detect_player_exploit_flags
from app.engine.housing_region_service import update_player_region
from app.engine.player_strategy_service import classify_player_strategy
from app.engine.weekly_strategy_service import build_player_weekly_strategy_summary
from app.models.business_daily_log import BusinessDailyLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.services.admin_debug_service import force_macro_scenario, force_player_debug_state
from app.services.day_progression_service import run_player_next_day

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
GAME_EPOCH = date(2026, 1, 1)

SCENARIO_PRESETS = {
    # Step 21 presets (kept for compatibility)
    "neutral_baseline",
    "oil_shock",
    "recession_pressure",
    "recovery_arc",
    "debt_spiral",
    "business_push",
    "certification_focus",
    "suburban_survival",
    "downtown_hustle",
    # Step 22 content-aware presets
    "conservative_worker_path",
    "aggressive_business_push",
    "debt_recovery_mode",
    "certification_first_path",
    "downtown_high_risk_path",
    "suburban_stability_path",
    "event_chain_crisis_path",
    "confidence_rebound_path",
}


class SimulationServiceError(Exception):
    """Base exception for simulation service operations."""


class SimulationValidationError(SimulationServiceError):
    """Raised when simulation request is invalid."""


class SimulationNotFoundError(SimulationServiceError):
    """Raised when simulation target player cannot be found."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise SimulationNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise SimulationNotFoundError("Player not found.")
    return row


def _day_to_date(day: int) -> date:
    return GAME_EPOCH + timedelta(days=max(0, int(day) - 1))


def _safe_json(text_value: str | None) -> dict | list | None:
    if not text_value:
        return None
    try:
        return json.loads(text_value)
    except Exception:
        return None


def _collect_business_mode_outcomes(
    db: Session,
    *,
    player_id: UUID,
    start_day: int,
    end_day: int,
) -> list[dict]:
    rows = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player_id,
            BusinessDailyLog.day >= int(start_day),
            BusinessDailyLog.day <= int(end_day),
        )
        .order_by(BusinessDailyLog.day.asc(), BusinessDailyLog.created_at.asc())
        .all()
    )

    grouped: dict[tuple[str, str], dict[str, Decimal | int | str]] = {}
    for row in rows:
        debug_meta = _safe_json(getattr(row, "debug_json", None))
        if not isinstance(debug_meta, dict):
            debug_meta = {}
        mode_key = str(debug_meta.get("operating_mode") or "default")
        business_type = str(getattr(row, "business_type", "") or "unknown")
        bucket_key = (business_type, mode_key)
        if bucket_key not in grouped:
            grouped[bucket_key] = {
                "business_type": business_type,
                "mode_key": mode_key,
                "days_count": 0,
                "revenue_xgp": Decimal("0.00"),
                "net_profit_xgp": Decimal("0.00"),
            }
        bucket = grouped[bucket_key]
        bucket["days_count"] = int(bucket["days_count"]) + 1
        bucket["revenue_xgp"] = _d(bucket["revenue_xgp"]) + _d(getattr(row, "gross_revenue_xgp", 0))
        bucket["net_profit_xgp"] = _d(bucket["net_profit_xgp"]) + _d(getattr(row, "net_profit_xgp", 0))

    outcomes: list[dict] = []
    for payload in grouped.values():
        days_count = int(payload["days_count"])
        total_net_profit = _money(_d(payload["net_profit_xgp"]))
        outcomes.append(
            {
                "business_type": str(payload["business_type"]),
                "mode_key": str(payload["mode_key"]),
                "days_count": days_count,
                "total_revenue_xgp": float(_money(_d(payload["revenue_xgp"]))),
                "total_net_profit_xgp": float(total_net_profit),
                "avg_net_profit_xgp": float(_money(total_net_profit / Decimal(str(max(1, days_count))))),
            }
        )
    outcomes.sort(key=lambda row: (row["business_type"], row["mode_key"]))
    return outcomes


def _collect_upgrade_roi_signals(
    db: Session,
    *,
    player_id: UUID,
    start_day: int,
    end_day: int,
) -> dict:
    businesses = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player_id)
        .order_by(PlayerBusiness.created_at.asc())
        .all()
    )

    current_upgrades: list[dict] = []
    for row in businesses:
        parsed = _safe_json(getattr(row, "upgrades_json", "[]"))
        upgrades = sorted(
            set(
                item.strip()
                for item in parsed
                if isinstance(parsed, list) and isinstance(item, str) and item.strip()
            )
        ) if isinstance(parsed, list) else []
        current_upgrades.append(
            {
                "business_id": str(row.id),
                "business_type": str(row.business_type),
                "upgrades": upgrades,
            }
        )

    logs = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player_id,
            BusinessDailyLog.day >= int(start_day),
            BusinessDailyLog.day <= int(end_day),
        )
        .order_by(BusinessDailyLog.day.asc(), BusinessDailyLog.created_at.asc())
        .all()
    )

    upgrade_totals: dict[str, dict[str, Decimal | int]] = {}
    for row in logs:
        debug_meta = _safe_json(getattr(row, "debug_json", None))
        if not isinstance(debug_meta, dict):
            continue
        upgrades = debug_meta.get("upgrades")
        if not isinstance(upgrades, list):
            continue
        for upgrade in upgrades:
            if not isinstance(upgrade, str) or not upgrade.strip():
                continue
            key = upgrade.strip()
            if key not in upgrade_totals:
                upgrade_totals[key] = {
                    "days_count": 0,
                    "total_net_profit_xgp": Decimal("0.00"),
                }
            slot = upgrade_totals[key]
            slot["days_count"] = int(slot["days_count"]) + 1
            slot["total_net_profit_xgp"] = _d(slot["total_net_profit_xgp"]) + _d(getattr(row, "net_profit_xgp", 0))

    upgrade_outcomes: list[dict] = []
    for key, payload in upgrade_totals.items():
        days_count = int(payload["days_count"])
        total_net = _money(_d(payload["total_net_profit_xgp"]))
        upgrade_outcomes.append(
            {
                "upgrade_key": key,
                "days_count": days_count,
                "total_net_profit_xgp": float(total_net),
                "avg_net_profit_xgp": float(_money(total_net / Decimal(str(max(1, days_count))))),
            }
        )
    upgrade_outcomes.sort(key=lambda row: row["upgrade_key"])

    return {
        "current_upgrades": current_upgrades,
        "upgrade_outcomes": upgrade_outcomes,
    }


def _apply_scenario_preset(db: Session, player_id: str | UUID, scenario_key: str) -> list[str]:
    notes: list[str] = []
    key = (scenario_key or "neutral_baseline").strip().lower()
    if key not in SCENARIO_PRESETS:
        raise SimulationValidationError(f"Unsupported scenario_key. Use one of: {sorted(SCENARIO_PRESETS)}")

    if key == "neutral_baseline":
        return notes

    if key == "oil_shock":
        force_macro_scenario(db, "oil_spike")
        notes.append("Applied macro oil_spike scenario.")
    elif key == "recession_pressure":
        force_macro_scenario(db, "unemployment_shock")
        force_macro_scenario(db, "confidence_drop")
        notes.append("Applied unemployment_shock + confidence_drop macro scenarios.")
    elif key == "recovery_arc":
        force_macro_scenario(db, "consumer_recovery")
        force_player_debug_state(db, player_id, "clean_restart")
        notes.append("Applied consumer_recovery and clean_restart player scenario.")
    elif key == "debt_spiral":
        force_player_debug_state(db, player_id, "high_debt")
        force_player_debug_state(db, player_id, "high_stress")
        force_macro_scenario(db, "confidence_drop")
        notes.append("Applied high_debt + high_stress + confidence_drop scenarios.")
    elif key == "business_push":
        force_macro_scenario(db, "consumer_recovery")
        notes.append("Applied consumer_recovery macro scenario for business upside pressure.")
    elif key == "certification_focus":
        force_macro_scenario(db, "inflation_relief")
        notes.append("Applied inflation_relief macro scenario for certification-focus simulation.")
    elif key == "suburban_survival":
        update_player_region(db=db, player_id=player_id, region_key="suburban")
        notes.append("Moved player to suburban region for survival profile.")
    elif key == "downtown_hustle":
        update_player_region(db=db, player_id=player_id, region_key="downtown")
        notes.append("Moved player to downtown region for hustle profile.")
    elif key == "conservative_worker_path":
        force_player_debug_state(db, player_id, "clean_restart")
        update_player_region(db=db, player_id=player_id, region_key="suburban")
        force_macro_scenario(db, "inflation_relief")
        notes.append("Applied conservative worker baseline: clean_restart + suburban + inflation_relief.")
    elif key == "aggressive_business_push":
        update_player_region(db=db, player_id=player_id, region_key="downtown")
        force_macro_scenario(db, "consumer_recovery")
        notes.append("Applied aggressive business push: downtown + consumer_recovery.")
    elif key == "debt_recovery_mode":
        force_player_debug_state(db, player_id, "high_debt")
        force_player_debug_state(db, player_id, "low_cash")
        update_player_region(db=db, player_id=player_id, region_key="suburban")
        notes.append("Applied debt recovery mode: high_debt + low_cash + suburban.")
    elif key == "certification_first_path":
        force_player_debug_state(db, player_id, "clean_restart")
        force_macro_scenario(db, "inflation_relief")
        notes.append("Applied certification-first baseline: clean_restart + inflation_relief.")
    elif key == "downtown_high_risk_path":
        update_player_region(db=db, player_id=player_id, region_key="downtown")
        force_macro_scenario(db, "oil_spike")
        force_macro_scenario(db, "confidence_drop")
        notes.append("Applied downtown high-risk pressure: downtown + oil_spike + confidence_drop.")
    elif key == "suburban_stability_path":
        update_player_region(db=db, player_id=player_id, region_key="suburban")
        force_macro_scenario(db, "inflation_relief")
        notes.append("Applied suburban stability profile: suburban + inflation_relief.")
    elif key == "event_chain_crisis_path":
        force_macro_scenario(db, "oil_spike")
        force_macro_scenario(db, "supply_chain_disruption")
        force_macro_scenario(db, "unemployment_shock")
        notes.append("Applied crisis chain pressure: oil_spike + supply_chain_disruption + unemployment_shock.")
    elif key == "confidence_rebound_path":
        force_macro_scenario(db, "consumer_recovery")
        force_macro_scenario(db, "inflation_relief")
        notes.append("Applied confidence rebound path: consumer_recovery + inflation_relief.")

    db.flush()
    return notes


def run_player_scenario_simulation(
    db: Session,
    player_id: int | str | UUID,
    days: int,
    scenario_key: str | None = None,
) -> dict:
    """Run a deterministic multi-day simulation without mutating live state."""
    days_int = int(days)
    if days_int <= 0:
        raise SimulationValidationError("days must be greater than 0.")
    max_days = int(SIMULATION_CONFIG.get("max_days", 90))
    if days_int > max_days:
        raise SimulationValidationError(f"days must be <= {max_days}.")

    player = _resolve_player(db, player_id)
    scenario = (scenario_key or "neutral_baseline").strip().lower()
    if scenario not in SCENARIO_PRESETS:
        raise SimulationValidationError(f"Unsupported scenario_key. Use one of: {sorted(SCENARIO_PRESETS)}")

    savepoint = db.begin_nested()
    original_commit = db.commit

    def _flush_only() -> None:
        db.flush()

    # Prevent nested day/settlement services from committing live state.
    db.commit = _flush_only  # type: ignore[method-assign]

    try:
        scenario_notes = _apply_scenario_preset(db, player.id, scenario)

        run_rows: list[dict] = []
        weekly_summary_snapshots: list[dict] = []
        stress_total = Decimal("0")
        health_total = Decimal("0")
        business_profit_total = Decimal("0")
        missed_payments = 0
        promotions_earned = 0
        distress_path: list[str] = []
        start_day: int | None = None
        end_day: int | None = None

        for _ in range(days_int):
            row = run_player_next_day(db, str(player.id))
            run_rows.append(row)
            if start_day is None:
                start_day = int(row.get("settled_day", 1))
            end_day = int(row.get("settled_day", 1))
            stress_total += _d(row.get("stress", 0))
            health_total += _d(row.get("health", 100))
            business_profit_total += _d(row.get("business_net_profit_xgp", row.get("business_net_xgp", 0)))
            if bool(row.get("debt_payment_missed", False)):
                missed_payments += 1
            if bool((row.get("career_summary") or {}).get("promotion_unlocked_today", False)):
                promotions_earned += 1
            distress_path.append(str(row.get("distress_state", "stable")))
            settled_day = int(row.get("settled_day", 1))
            if settled_day % 7 == 0:
                try:
                    weekly_summary_snapshots.append(
                        build_player_weekly_strategy_summary(
                            db=db,
                            player_id=player.id,
                            as_of_date=_day_to_date(settled_day),
                        )
                    )
                except Exception:
                    pass

        db.flush()
        db.refresh(player)

        as_of_date = _day_to_date(int(run_rows[-1]["settled_day"])) if run_rows else None
        exploit_flags = detect_player_exploit_flags(
            db=db,
            player_id=str(player.id),
            as_of_date=as_of_date,
        )
        telemetry_summary = compute_daily_economy_health_metrics(db=db, as_of_date=as_of_date)
        try:
            strategy_snapshot = classify_player_strategy(
                db=db,
                player_id=player.id,
                as_of_date=as_of_date,
                lookback_days=min(14, max(days_int, 7)),
            )
        except Exception:
            strategy_snapshot = {
                "strategy_classification": "stable_worker",
                "classification_drivers": {},
                "debug_meta": {"fallback": "classification_unavailable"},
            }

        avg_stress = _q4(stress_total / Decimal(str(max(1, len(run_rows)))))
        avg_health = _q4(health_total / Decimal(str(max(1, len(run_rows)))))
        mode_outcomes = _collect_business_mode_outcomes(
            db=db,
            player_id=player.id,
            start_day=int(start_day or 1),
            end_day=int(end_day or (start_day or 1)),
        )
        upgrade_roi_signals = _collect_upgrade_roi_signals(
            db=db,
            player_id=player.id,
            start_day=int(start_day or 1),
            end_day=int(end_day or (start_day or 1)),
        )

        result = {
            "scenario_key": scenario,
            "days": int(days_int),
            "final_cash_xgp": float(_money(_d(player.cash_xgp))),
            "final_net_worth_xgp": float(_money(_d(player.net_worth_xgp))),
            "avg_stress": float(avg_stress),
            "avg_health": float(avg_health),
            "final_distress_state": distress_path[-1] if distress_path else str(getattr(player, "distress_state", "stable") or "stable"),
            "promotions_earned": int(promotions_earned),
            "missed_payments": int(missed_payments),
            "total_business_profit_xgp": float(_money(business_profit_total)),
            "strategy_classification": str(strategy_snapshot.get("strategy_classification", "stable_worker")),
            "strategy_classification_drivers": strategy_snapshot.get("classification_drivers", {}),
            "business_mode_outcomes": mode_outcomes,
            "upgrade_roi_signals": upgrade_roi_signals,
            "weekly_summary_snapshots": weekly_summary_snapshots,
            "exploit_flags": {
                "rideshare_overfarm_flag": bool(exploit_flags.get("rideshare_overfarm_flag", False)),
                "food_truck_margin_abuse_flag": bool(exploit_flags.get("food_truck_margin_abuse_flag", False)),
                "fruit_shop_markup_abuse_flag": bool(exploit_flags.get("fruit_shop_markup_abuse_flag", False)),
                "zero_rest_grind_flag": bool(exploit_flags.get("zero_rest_grind_flag", False)),
                "debt_ignore_abuse_flag": bool(exploit_flags.get("debt_ignore_abuse_flag", False)),
                "too_fast_promotion_flag": bool(exploit_flags.get("too_fast_promotion_flag", False)),
                "region_switch_abuse_flag": bool(exploit_flags.get("region_switch_abuse_flag", False)),
                "event_chain_prediction_advantage_flag": bool(
                    exploit_flags.get("event_chain_prediction_advantage_flag", False)
                ),
            },
            "telemetry_summary": telemetry_summary,
            "debug_meta": {
                "scenario_notes": scenario_notes,
                "distress_path": distress_path,
                "run_rows_count": int(len(run_rows)),
                "last_row": run_rows[-1] if run_rows else None,
                "strategy_debug_meta": strategy_snapshot.get("debug_meta", {}),
                "window": {
                    "start_day": int(start_day or 1),
                    "end_day": int(end_day or (start_day or 1)),
                },
                **get_balance_profile_metadata(),
            },
        }
        return result
    finally:
        db.commit = original_commit  # type: ignore[method-assign]
        if savepoint.is_active:
            savepoint.rollback()
        db.expire_all()


def run_economy_scenario_sweep(
    db: Session,
    player_id: int | str | UUID,
    days: int,
    scenario_keys: list[str] | None = None,
) -> dict:
    """Run deterministic multi-scenario sweep for one player."""
    keys = list(scenario_keys or sorted(SCENARIO_PRESETS))
    runs = [
        run_player_scenario_simulation(db=db, player_id=player_id, days=days, scenario_key=key)
        for key in keys
    ]

    return {
        "player_id": str(_resolve_player(db, player_id).id),
        "days": int(days),
        "scenarios_run": keys,
        "runs": runs,
        "debug_meta": {
            "scenario_count": int(len(runs)),
            **get_balance_profile_metadata(),
        },
    }


def compare_balance_profiles(
    db: Session,
    player_id: int | str | UUID,
    days: int,
    profiles: list[str] | None = None,
    scenario_key: str | None = None,
) -> dict:
    """Compare profile outputs for future profile tuning support.

    Step 21 ships one active profile. This function still returns comparison
    structure so future profiles can plug in without API breakage.
    """
    profile_names = list(profiles or [get_balance_profile_metadata()["balance_profile"]])
    comparisons = []
    for name in profile_names:
        run = run_player_scenario_simulation(db=db, player_id=player_id, days=days, scenario_key=scenario_key)
        comparisons.append(
            {
                "profile": name,
                "scenario_key": run["scenario_key"],
                "days": run["days"],
                "final_cash_xgp": run["final_cash_xgp"],
                "final_net_worth_xgp": run["final_net_worth_xgp"],
                "avg_stress": run["avg_stress"],
                "avg_health": run["avg_health"],
                "final_distress_state": run["final_distress_state"],
            }
        )

    return {
        "player_id": str(_resolve_player(db, player_id).id),
        "profiles": profile_names,
        "comparisons": comparisons,
        "debug_meta": {
            "note": "Single-profile comparison in Step 21; structure is future-ready.",
            **get_balance_profile_metadata(),
        },
    }
