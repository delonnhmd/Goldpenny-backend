"""Step 21 balance report builders for internal tuning workflows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.balance_config import get_balance_profile_metadata
from app.engine.economy_telemetry_service import (
    compute_balance_flags,
    compute_daily_economy_health_metrics,
    get_player_balance_snapshot,
)
from app.engine.exploit_detection_service import (
    detect_system_dominance_flags,
    get_exploit_report,
)

Q4 = Decimal("0.0001")


class BalanceReportError(Exception):
    """Base exception for balance reporting."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def build_system_dominance_report(
    db: Session,
    as_of_date: date | None = None,
) -> dict:
    """Return dominant systems summary for balancing decisions."""
    dominance = detect_system_dominance_flags(db=db, as_of_date=as_of_date)
    debug = dominance.get("debug_meta", {})

    dominant_jobs = []
    job_counts = debug.get("job_counts", {}) if isinstance(debug, dict) else {}
    if isinstance(job_counts, dict):
        dominant_jobs = sorted(job_counts.items(), key=lambda item: item[1], reverse=True)[:5]

    dominant_businesses = []
    business_profit = debug.get("business_profit_by_type", {}) if isinstance(debug, dict) else {}
    if isinstance(business_profit, dict):
        dominant_businesses = sorted(
            business_profit.items(),
            key=lambda item: float(item[1]),
            reverse=True,
        )[:5]

    return {
        "as_of_date": dominance.get("as_of_date"),
        "dominant_flags": dominance.get("dominant_flags", []),
        "dominant_jobs": dominant_jobs,
        "dominant_businesses": dominant_businesses,
        "debug_meta": debug,
    }


def build_player_strategy_report(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return one player's strategy-risk and viability profile."""
    balance = get_player_balance_snapshot(db=db, player_id=player_id, as_of_date=as_of_date)
    exploit = get_exploit_report(db=db, player_id=player_id, as_of_date=as_of_date)

    active_flags = sorted(
        [
            key
            for key, value in exploit.items()
            if key.endswith("_flag") and bool(value)
        ]
    )

    return {
        "player_id": balance["player_id"],
        "as_of_date": balance["as_of_date"],
        "days_cash_cushion": balance["days_cash_cushion"],
        "debt_pressure_ratio": balance["debt_pressure_ratio"],
        "burnout_danger_score": balance["burnout_danger_score"],
        "upward_mobility_score": balance["upward_mobility_score"],
        "active_exploit_flags": active_flags,
        "debug_meta": {
            "balance": balance.get("debug_meta", {}),
            "exploit": exploit.get("debug_meta", {}),
        },
    }


def build_balance_report(
    db: Session,
    as_of_date: date | None = None,
) -> dict:
    """Build consolidated Step 21 balance report with tuning targets."""
    telemetry = compute_daily_economy_health_metrics(db=db, as_of_date=as_of_date)
    balance_flags = compute_balance_flags(telemetry)
    dominance = build_system_dominance_report(db=db, as_of_date=as_of_date)

    harshness = _d(telemetry.get("economy_harshness_score", 0))
    softness = _d(telemetry.get("economy_softness_score", 0))
    recovery = _d(telemetry.get("recovery_success_proxy", 0))
    stress = _d(telemetry.get("average_stress_burden", 0))
    distress = _d(telemetry.get("average_distress_burden", 0))
    basket_vol = _d(telemetry.get("basket_volatility_index", 0))

    top_system_risks: list[str] = []
    if harshness >= Decimal("70"):
        top_system_risks.append("economy_harshness_high")
    if softness >= Decimal("70"):
        top_system_risks.append("economy_softness_high")
    if recovery <= Decimal("0.35"):
        top_system_risks.append("recovery_failure_risk")
    if basket_vol >= Decimal("40"):
        top_system_risks.append("basket_volatility_spike")
    top_system_risks.extend(dominance.get("dominant_flags", []))
    top_system_risks = sorted(set(top_system_risks))

    weak_recovery_areas: list[str] = []
    if recovery <= Decimal("0.45"):
        weak_recovery_areas.append("debt_recovery_pipeline")
    if distress >= Decimal("55"):
        weak_recovery_areas.append("distress_pressure")
    if stress >= Decimal("65"):
        weak_recovery_areas.append("life_load_management")

    high_volatility_areas: list[str] = []
    if basket_vol >= Decimal("30"):
        high_volatility_areas.append("basket_prices")
    if _d(telemetry.get("job_opportunity_spread", 0)) >= Decimal("35"):
        high_volatility_areas.append("job_access_spread")
    if _d(telemetry.get("business_margin_pressure_index", 0)) >= Decimal("60"):
        high_volatility_areas.append("business_margins")

    suggested_tuning_targets: list[str] = []
    if "economy_harshness_high" in top_system_risks:
        suggested_tuning_targets.append("reduce debt/life compounding severity by 5-10%")
    if "economy_softness_high" in top_system_risks:
        suggested_tuning_targets.append("raise late-game pressure floor to preserve tension")
    if "rideshare_dominance_flag" in dominance.get("dominant_flags", []):
        suggested_tuning_targets.append("increase rideshare diminishing returns after soft cap")
    if "business_dominance_flag" in dominance.get("dominant_flags", []):
        suggested_tuning_targets.append("tighten top business demand capture and margin caps")
    if not suggested_tuning_targets:
        suggested_tuning_targets.append("monitor current profile; no urgent retune target")

    return {
        "as_of_date": telemetry.get("as_of_date"),
        **get_balance_profile_metadata(),
        "top_system_risks": top_system_risks,
        "dominant_jobs": dominance.get("dominant_jobs", []),
        "dominant_businesses": dominance.get("dominant_businesses", []),
        "weak_recovery_areas": sorted(set(weak_recovery_areas)),
        "high_volatility_areas": sorted(set(high_volatility_areas)),
        "suggested_tuning_targets": suggested_tuning_targets,
        "debug_meta": {
            "telemetry": telemetry,
            "balance_flags": balance_flags,
            "dominance": dominance,
        },
    }
