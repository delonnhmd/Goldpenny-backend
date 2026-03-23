"""Step 21 balancing profile and anti-exploit tuning constants.

This module centralizes tunable values used by telemetry, exploit detection,
guardrails, and simulation tooling. Existing subsystem formulas can progressively
adopt values from here without requiring risky bulk rewrites.
"""

from __future__ import annotations

from decimal import Decimal

BALANCE_PROFILE_NAME = "mvp_v1"
BALANCE_PROFILE_VERSION = "step21_mvp_v1"

MVP_V1_PROFILE: dict[str, object] = {
    "name": BALANCE_PROFILE_NAME,
    "version": BALANCE_PROFILE_VERSION,
    "anti_exploit": {
        "rideshare": {
            "soft_hour_cap": Decimal("6.0"),
            "hard_hour_cap": Decimal("12.0"),
            "diminish_per_extra_hour": Decimal("0.0600"),
            "min_output_factor": Decimal("0.60"),
            "maintenance_risk_per_extra_hour": Decimal("0.0100"),
        },
        "fruit_shop_markup": {
            "extreme_markup_threshold": Decimal("0.32"),
            "max_extra_elasticity_penalty": Decimal("0.35"),
            "max_extra_sold_units_penalty": Decimal("0.12"),
        },
        "zero_rest": {
            "sleep_threshold_hours": Decimal("4.8"),
            "overtime_threshold_hours": Decimal("2.0"),
            "streak_days": 3,
            "stress_surcharge": Decimal("1.80"),
            "productivity_drag": Decimal("0.0300"),
        },
        "region_switch": {
            "friction_window_days": 3,
            "commute_bonus_hours": Decimal("0.25"),
            "stress_bonus": Decimal("0.35"),
            "fuel_surcharge_xgp": Decimal("1.25"),
        },
    },
    "telemetry": {
        "default_window_days": 14,
        "viability_window_days": 7,
        "harshness_alert": Decimal("70.0"),
        "softness_alert": Decimal("70.0"),
        "dominance_share_alert": Decimal("0.62"),
    },
    "exploit_detection": {
        "rideshare_overfarm_hours_14d": Decimal("48.0"),
        "rideshare_overfarm_net_per_hour": Decimal("14.0"),
        "food_truck_margin_abuse_threshold": Decimal("0.42"),
        "fruit_markup_abuse_threshold": Decimal("0.34"),
        "debt_ignore_missed_days": 4,
        "region_switch_abuse_switches_7d": 3,
        "promotion_skill_jump_threshold": 3,
    },
    "simulation": {
        "max_days": 90,
        "default_days": 30,
    },
}

ACTIVE_BALANCE_PROFILE = MVP_V1_PROFILE

RIDESHARE_GUARDRAILS = dict(ACTIVE_BALANCE_PROFILE["anti_exploit"]["rideshare"])  # type: ignore[index]
FRUIT_MARKUP_GUARDRAILS = dict(ACTIVE_BALANCE_PROFILE["anti_exploit"]["fruit_shop_markup"])  # type: ignore[index]
ZERO_REST_GUARDRAILS = dict(ACTIVE_BALANCE_PROFILE["anti_exploit"]["zero_rest"])  # type: ignore[index]
REGION_SWITCH_GUARDRAILS = dict(ACTIVE_BALANCE_PROFILE["anti_exploit"]["region_switch"])  # type: ignore[index]
TELEMETRY_CONFIG = dict(ACTIVE_BALANCE_PROFILE["telemetry"])  # type: ignore[index]
EXPLOIT_CONFIG = dict(ACTIVE_BALANCE_PROFILE["exploit_detection"])  # type: ignore[index]
SIMULATION_CONFIG = dict(ACTIVE_BALANCE_PROFILE["simulation"])  # type: ignore[index]


def get_balance_profile(profile_name: str | None = None) -> dict[str, object]:
    """Return an active balance profile by name.

    Step 21 ships one profile (mvp_v1). A name mismatch safely falls back to
    the active profile for backwards compatibility.
    """
    normalized = (profile_name or BALANCE_PROFILE_NAME).strip().lower()
    if normalized == BALANCE_PROFILE_NAME:
        return ACTIVE_BALANCE_PROFILE
    return ACTIVE_BALANCE_PROFILE


def get_balance_profile_metadata() -> dict[str, str]:
    """Return lightweight profile metadata for debug/telemetry payloads."""
    return {
        "balance_profile": str(ACTIVE_BALANCE_PROFILE["name"]),
        "balance_profile_version": str(ACTIVE_BALANCE_PROFILE["version"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step 68 — Day 1 Calibration Layer
# ─────────────────────────────────────────────────────────────────────────────
# These presets are intentionally separate from the Step 21 anti-exploit
# profile above.  They control the *feel* of Day 1 — how hard income is to
# earn, how quickly stress and health degrade, and how often opportunities
# surface — without touching core formula logic.
#
# Integration points:
#   income_multiplier        → work_engine.py  (earned_cash * multiplier)
#   expense_pressure_mult    → commitment_service.py (optional; readable via
#                              get_active_day1_config for future expansion)
#   stress_sensitivity       → work_engine.py  (stress_change * sensitivity)
#   health_decay_rate        → work_engine.py  (health_change * decay_rate)
#   opportunity_spawn_rate   → event_service.py (positive-event bias factor)
# ─────────────────────────────────────────────────────────────────────────────

DAY1_BALANCE_PRESETS: dict[str, dict[str, float]] = {
    "easy": {
        # Forgiving first day: boosted income, muted expenses, lighter stress.
        "income_multiplier": 1.30,
        "expense_pressure_multiplier": 0.80,
        "stress_sensitivity": 0.75,
        "health_decay_rate": 0.70,
        "opportunity_spawn_rate": 1.60,
    },
    "normal": {
        # Calibrated baseline — all values at 1.0 mean "engine defaults are used".
        "income_multiplier": 1.00,
        "expense_pressure_multiplier": 1.00,
        "stress_sensitivity": 1.00,
        "health_decay_rate": 1.00,
        "opportunity_spawn_rate": 1.00,
    },
    "hard": {
        # Tighter income, elevated expenses, stress bites harder.
        "income_multiplier": 0.85,
        "expense_pressure_multiplier": 1.25,
        "stress_sensitivity": 1.35,
        "health_decay_rate": 1.40,
        "opportunity_spawn_rate": 0.65,
    },
    "stress_test": {
        # Worst-case calibration run — surfaces edge-case failures quickly.
        "income_multiplier": 0.60,
        "expense_pressure_multiplier": 1.60,
        "stress_sensitivity": 2.00,
        "health_decay_rate": 2.00,
        "opportunity_spawn_rate": 0.40,
    },
}

# Module-level mutable — changed at runtime via set_active_day1_preset().
_active_day1_preset_name: str = "normal"


def get_active_day1_config() -> dict[str, float]:
    """Return the currently active Day 1 balance config dict.

    Always safe to call; falls back to 'normal' if the stored preset is
    somehow invalid.
    """
    return DAY1_BALANCE_PRESETS.get(
        _active_day1_preset_name,
        DAY1_BALANCE_PRESETS["normal"],
    )


def get_active_day1_preset_name() -> str:
    """Return the name of the currently active Day 1 preset."""
    return _active_day1_preset_name


def get_day1_preset(name: str) -> dict[str, float] | None:
    """Return a named preset config dict, or None if the name is unknown."""
    return DAY1_BALANCE_PRESETS.get(name)


def get_all_day1_presets() -> dict[str, dict[str, float]]:
    """Return all preset configs keyed by name (copy for safety)."""
    return {k: dict(v) for k, v in DAY1_BALANCE_PRESETS.items()}


def set_active_day1_preset(name: str) -> None:
    """Switch the active Day 1 preset by name.

    Raises ValueError for unknown preset names so callers get a clear error.
    This mutates the module-level variable — changes apply globally in the
    current process until the next call or process restart.
    """
    global _active_day1_preset_name
    if name not in DAY1_BALANCE_PRESETS:
        valid = sorted(DAY1_BALANCE_PRESETS.keys())
        raise ValueError(f"Unknown Day 1 preset '{name}'. Valid presets: {valid}")
    _active_day1_preset_name = name


# ── Convenience application helpers ──────────────────────────────────────────
# Call these from integration points to apply the active config without
# importing the full preset dict everywhere.


def apply_income_multiplier(base_income: float, config: dict[str, float] | None = None) -> float:
    """Scale *base_income* by the active (or supplied) income_multiplier."""
    cfg = config if config is not None else get_active_day1_config()
    return base_income * cfg.get("income_multiplier", 1.0)


def apply_stress_sensitivity(stress_change: int, config: dict[str, float] | None = None) -> int:
    """Scale *stress_change* by the active stress_sensitivity. Returns int."""
    cfg = config if config is not None else get_active_day1_config()
    return round(stress_change * cfg.get("stress_sensitivity", 1.0))


def apply_health_decay_rate(health_change: int, config: dict[str, float] | None = None) -> int:
    """Scale *health_change* by the active health_decay_rate. Returns int."""
    cfg = config if config is not None else get_active_day1_config()
    return round(health_change * cfg.get("health_decay_rate", 1.0))
