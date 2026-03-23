"""Housing Balance Engine — Step 8b.

Pure calculation functions for housing affordability pressure, region tuning,
mortgage burden, maintenance, stress impact, and delinquency escalation.

All public functions are side-effect-free (no DB access) except where
bounded randomness is explicit (maintenance roll).
API routes and HousingEngine must stay thin — import this module and call
these functions rather than embedding the math inline.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.debt_account import DebtAccount
    from app.models.economy import EconomyState
    from app.models.housing_definition import HousingDefinition
    from app.models.player import Player
    from app.models.player_housing import PlayerHousing

# ── Constants ─────────────────────────────────────────────────────────────────

_AMORTIZATION_DAYS = 30 * 365  # 10 950 days

# (region, occupancy_type) → pressure multiplier
_REGION_PRESSURE: dict[tuple[str, str], float] = {
    ("suburban", "rent"): 0.95,
    ("suburban", "own"): 1.00,
    ("downtown", "rent"): 1.10,
    ("downtown", "own"): 1.18,
}

# Maintenance roll chance per day by risk level (owned housing only)
_MAINTENANCE_CHANCE: dict[str, float] = {
    "low":         0.02,   # 2 %/day
    "medium":      0.06,   # 6 %/day — suburban owned
    "medium_high": 0.10,   # 10 %/day — downtown owned
}

# (severity_label, (min_cost, max_cost), probability_weight)
_MAINTENANCE_TIERS: list[tuple[str, tuple[int, int], float]] = [
    ("minor",  (20,   50), 0.60),
    ("medium", (60,  140), 0.30),
    ("major",  (160, 320), 0.10),   # rare
]

_DOWNTOWN_MAINTENANCE_PREMIUM = 0.15   # 15 % more expensive repairs downtown

# penalty_rate_modifier applied to mortgage interest by delinquency level
_PENALTY_RATE_BY_STATUS: dict[str, float] = {
    "current":    1.00,
    "late":       1.02,
    "delinquent": 1.05,
    "severe":     1.08,
}

# Penalty magnitudes by missed-payment tier
_DELINQUENCY_PENALTIES: dict[str, dict[str, int]] = {
    "first":    {"credit": -5,  "stability": -4, "stress": 3},
    "repeated": {"credit": -10, "stability": -6, "stress": 5},
    "severe":   {"credit": -15, "stability": -8, "stress": 7},
}

_CREDIT_MIN = 300
_CREDIT_MAX = 850
_STABILITY_MIN = 0
_STABILITY_MAX = 100


# ── Affordability pressure ────────────────────────────────────────────────────

def calculate_affordability_pressure(
    total_housing_cost: float,
    cash_after_housing: float,
) -> float:
    """Estimate housing burden relative to remaining cash.

    Returns a multiplier in [0.90, 1.80].  Higher = more strained.
    """
    pressure = 1.0 + max(0.0, (total_housing_cost - 20.0) * 0.02)
    if cash_after_housing < 100:
        pressure += 0.10
    if cash_after_housing < 50:
        pressure += 0.15
    if cash_after_housing <= 0:
        pressure += 0.20
    return round(max(0.90, min(1.80, pressure)), 4)


# ── Region pressure ───────────────────────────────────────────────────────────

def calculate_region_pressure_modifier(region: str, occupancy_type: str) -> float:
    """Return the region + occupancy pressure multiplier."""
    return _REGION_PRESSURE.get((region, occupancy_type), 1.00)


# ── Mortgage daily components ─────────────────────────────────────────────────

def calculate_daily_mortgage_components(
    debt: "DebtAccount",
    economy: "EconomyState | None",
) -> dict[str, float]:
    """Break a mortgage debt into daily interest and principal components.

    Applies penalty_rate_modifier so delinquent accounts accrue higher cost.
    Returns {"interest_component", "principal_component", "adjusted_minimum_payment"}.
    """
    principal = float(debt.principal_balance)
    penalty_mod = float(getattr(debt, "penalty_rate_modifier", 1.0) or 1.0)
    adjusted_rate = debt.interest_rate * penalty_mod
    interest_comp = principal * (adjusted_rate / 100.0) / 365.0
    principal_comp = principal / _AMORTIZATION_DAYS
    adjusted_payment = interest_comp + principal_comp
    return {
        "interest_component": round(interest_comp, 6),
        "principal_component": round(principal_comp, 6),
        "adjusted_minimum_payment": round(adjusted_payment, 4),
    }


# ── Maintenance ───────────────────────────────────────────────────────────────

def calculate_maintenance_pressure(
    housing: "PlayerHousing",
    economy: "EconomyState | None",
) -> tuple[bool, float, str, str]:
    """Roll for a maintenance event on owned housing.

    Returns (triggered, cost, severity_label, note).
    - Downtown adds a 15 % price premium.
    - High inflation (>3.5 %) inflates repair costs slightly.
    """
    if housing.occupancy_type != "own":
        return False, 0.0, "none", ""

    from app.models.housing_definition import HOUSING_CATALOG
    defn = HOUSING_CATALOG.get(housing.housing_key)
    if not defn:
        return False, 0.0, "none", ""

    chance = _MAINTENANCE_CHANCE.get(defn.maintenance_risk, 0.0)
    if random.random() > chance:
        return False, 0.0, "none", ""

    # Weighted tier selection
    roll = random.random()
    cumulative = 0.0
    chosen = _MAINTENANCE_TIERS[-1]
    for tier in _MAINTENANCE_TIERS:
        cumulative += tier[2]
        if roll <= cumulative:
            chosen = tier
            break

    tier_label, (low, high), _ = chosen
    cost = float(random.randint(low, high))

    if housing.region == "downtown":
        cost = round(cost * (1.0 + _DOWNTOWN_MAINTENANCE_PREMIUM), 2)

    if economy:
        inflation_lift = max(0.0, (economy.inflation_rate - 3.5) * 0.04)
        cost = round(cost * (1.0 + min(0.10, inflation_lift)), 2)

    return True, cost, tier_label, f"{tier_label.capitalize()} maintenance event"


# ── Housing stress impact ─────────────────────────────────────────────────────

def calculate_housing_stress_impact(
    defn: "HousingDefinition",
    affordability_pressure: float,
    missed_payment: bool,
    maintenance_triggered: bool,
    maintenance_severity: str,
) -> int:
    """Return net daily stress change from housing pressure.

    Clamped to [-3, +12].
    Suburban rent can produce mild relief (-1 base).
    Downtown own under strain can push near the cap.
    """
    stress = int(defn.stress_modifier)
    afford_stress = max(0.0, (affordability_pressure - 1.0) * 5.0)
    stress += round(afford_stress)
    if missed_payment:
        stress += 3
    if maintenance_triggered:
        severity_stress = {"major": 5, "medium": 3, "minor": 2}.get(maintenance_severity, 2)
        stress += severity_stress
    return max(-3, min(12, stress))


# ── Delinquency progression ───────────────────────────────────────────────────

def apply_delinquency_progression(
    player: "Player",
    housing: "PlayerHousing",
    debt: "DebtAccount | None",
) -> tuple[int, int, int]:
    """Apply missed-payment penalties.  Mutates player, housing, debt in place.

    Returns (credit_score_change, stability_change, stress_change) — all <= 0
    for credit/stability; >= 0 for stress.
    """
    consecutive = int(getattr(housing, "consecutive_missed_housing_days", 0) or 0)

    if consecutive <= 1:
        tier = _DELINQUENCY_PENALTIES["first"]
    elif consecutive <= 4:
        tier = _DELINQUENCY_PENALTIES["repeated"]
    else:
        tier = _DELINQUENCY_PENALTIES["severe"]

    credit_change = tier["credit"]
    stability_change = tier["stability"]
    stress_change = tier["stress"]

    player.credit_score = max(_CREDIT_MIN, min(_CREDIT_MAX, player.credit_score + credit_change))
    player.housing_stability = max(_STABILITY_MIN, min(_STABILITY_MAX, player.housing_stability + stability_change))

    if debt:
        debt.consecutive_missed_payments = int(getattr(debt, "consecutive_missed_payments", 0) or 0) + 1
        debt.missed_payment_count = int(debt.missed_payment_count or 0) + 1

        new_status = _delinquency_from_consecutive(debt.consecutive_missed_payments)
        debt.delinquency_status = new_status

        # Ratchet penalty modifier upward — never decreases automatically
        current_prm = float(getattr(debt, "penalty_rate_modifier", 1.0) or 1.0)
        target_prm = _PENALTY_RATE_BY_STATUS.get(new_status, 1.0)
        debt.penalty_rate_modifier = round(max(current_prm, target_prm), 4)

    return credit_change, stability_change, stress_change


def _delinquency_from_consecutive(count: int) -> str:
    if count == 0:
        return "current"
    if count <= 2:
        return "late"
    if count <= 5:
        return "delinquent"
    return "severe"


# ── Balance utilities ─────────────────────────────────────────────────────────

def estimate_housing_burden(
    housing_key: str,
    economy: "EconomyState | None",
) -> dict:
    """Admin/debug: estimate total expected daily burden for a housing type."""
    from app.models.housing_definition import HOUSING_CATALOG
    defn = HOUSING_CATALOG.get(housing_key)
    if not defn:
        return {"error": f"Unknown housing_key: {housing_key!r}"}

    base = defn.daily_base_cost
    tax = 0.0
    debt_est = 0.0
    if defn.occupancy_type == "own" and defn.estimated_home_value:
        home_val = defn.estimated_home_value
        principal = home_val * 0.90
        eco_rate = economy.interest_rate if economy else 4.5
        rate = max(3.0, min(12.0, eco_rate + 1.5))
        daily_interest = principal * (rate / 100.0) / 365.0
        daily_principal = principal / _AMORTIZATION_DAYS
        debt_est = daily_interest + daily_principal
        tax = home_val * defn.property_tax_rate / 365.0

    # Expected value: chance × midpoint of each tier
    maint_expected = 0.0
    chance = _MAINTENANCE_CHANCE.get(defn.maintenance_risk, 0.0)
    for _, (low, high), weight in _MAINTENANCE_TIERS:
        maint_expected += chance * weight * ((low + high) / 2.0)
    if defn.region == "downtown":
        maint_expected *= (1.0 + _DOWNTOWN_MAINTENANCE_PREMIUM)

    total_est = base + debt_est + tax + maint_expected
    return {
        "housing_key": housing_key,
        "daily_base_cost": round(base, 2),
        "estimated_daily_debt_payment": round(debt_est, 2),
        "estimated_daily_property_tax": round(tax, 2),
        "estimated_daily_maintenance_expected_value": round(maint_expected, 2),
        "total_estimated_daily_burden": round(total_est, 2),
        "region_pressure_modifier": calculate_region_pressure_modifier(
            defn.region, defn.occupancy_type
        ),
    }


def summarize_housing_affordability(cash: float, total_housing_cost: float) -> dict:
    """Admin/debug: classify housing affordability for given cash and cost."""
    cash_after = cash - total_housing_cost
    pressure = calculate_affordability_pressure(total_housing_cost, cash_after)
    if pressure < 1.10:
        assessment = "comfortable"
    elif pressure < 1.30:
        assessment = "tight"
    elif pressure < 1.55:
        assessment = "strained"
    else:
        assessment = "critical"
    return {
        "cash_before": round(cash, 2),
        "total_housing_cost": round(total_housing_cost, 2),
        "cash_after_housing": round(cash_after, 2),
        "affordability_pressure": pressure,
        "assessment": assessment,
    }
