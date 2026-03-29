"""Business Balance Engine — Step 7b (legacy) + Step 11 (anti-exploit balancing).

Step 7b (legacy, class BusinessEngine flavour):
  All demand, efficiency, margin, spoilage, and penalty calculation functions
  for the old multi-tier business system (Player / Business / BusinessInventory).

Step 11 (new, module-level functions):
  Deterministic balancing layer that prevents the Step 10 small-business loop
  from becoming an infinite-money exploit.  Three independent pressure systems:

  1. Fixed Overhead  — every run costs a mandatory overhead fee regardless of
     how much revenue is generated.  Thin-margin businesses are inherently fragile.

  2. Demand Saturation  — repeated same-day runs weaken effective revenue.
     A single player's local market cannot absorb unlimited identical sales.

  3. Macro Margin Compression  — oil prices, inflation, and expensive inputs
     relative to revenue erode real profit margins deterministically.

Design rules (Step 11)
-----------------------
- Businesses are NOT free money machines.
- First run of the day should usually still feel worthwhile.
- Repeated use within the same day becomes progressively less efficient.
- Every operation pays fixed overhead — small businesses are fragile.
- Macro conditions compress margins; they never inflate them past the cap.
- All formulas are deterministic: no randomness in this layer.
- Negative profit is allowed and economically meaningful.
- All balancing values are stored in BusinessOperation for full auditability.

Step 7b legacy design rules (unchanged)
-----------------------------------------
- Demand cannot scale infinitely (saturation + confidence clamps).
- Player condition visibly degrades business performance.
- Economy state visibly affects margins and demand.
- Region is business-type-specific.
- Reputation changes slowly and is bounded.
- Spoilage is inventory-sensitive, not just a coin flip.
- All formulas are deterministic or semi-deterministic — no pure RNG profit.
"""

from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.business_inventory import BusinessInventory
    from app.models.economy import EconomyState
    from app.models.player import Player

from app.models.business_definition import BASKET_BASE_PRICES, BUSINESS_CATALOG, TIER_DEMAND_BOOST

_D = Decimal

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 11 — Business Balancing & Anti-Exploit Systems (module-level functions)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Economic loop:
#   Run Business → Profit → Repeated Use Causes Saturation →
#   Overhead Eats Margin → Macro Compresses Further → Player Must Adapt
#
# Sample diagnostic flow (for debugging / frontend explanations):
#
#   Day 12, fruit_shop — FIRST run:
#     times_operated_today = 0 → saturation_penalty_multiplier = 1.00
#     demand is normal → positive revenue, positive profit
#
#   Day 12, fruit_shop — SECOND run (same day):
#     times_operated_today = 1 → penalty = 0.18 → multiplier = 0.82
#     overhead still applies → second run much weaker, may be negative
#
#   Oil shock day (oil_index = 140), food_truck:
#     oil_component = (140-100)/100 * 0.25 = 0.10 → macro_modifier ≈ −0.10
#     overhead still applies → profit shrinks sharply vs. stable-macro day


def calculate_fixed_overhead(business_type) -> float:
    """Return the mandatory fixed daily operating overhead in XGP.

    Applied every single run regardless of revenue.  This is the first
    anti-exploit layer — small businesses always have real costs.
    A fruit shop with 8 XGP overhead needs at least 8 XGP net revenue
    before it can show a positive profit.
    """
    return round(float(business_type.fixed_overhead_xgp), 2)


def calculate_demand_multiplier(
    business_type,
    consumer_confidence: float,
    unemployment: float,
) -> float:
    """Convert macro demand conditions into a revenue multiplier.

    Better consumer confidence boosts demand; higher unemployment
    suppresses it.  Each business type carries different sensitivities
    so e.g. food_truck (confidence_sensitivity=0.30) reacts more
    strongly to consumer mood than fruit_shop (0.20).

    Formula:
        confidence_component  = ((confidence − 50) / 100) × sensitivity
        unemployment_component = ((5 − unemployment) / 100) × sensitivity
        demand_multiplier = base_demand_factor + both components

    Range: [0.75, 1.25] — clamped.
    """
    confidence_component = (
        (consumer_confidence - 50.0) / 100.0
    ) * float(business_type.confidence_sensitivity)

    unemployment_component = (
        (5.0 - unemployment) / 100.0
    ) * float(business_type.unemployment_sensitivity)

    raw = float(business_type.base_demand_factor) + confidence_component + unemployment_component
    return round(max(0.75, min(1.25, raw)), 4)


def calculate_saturation_penalty_multiplier(
    business_type,
    times_operated_today: int,
) -> float:
    """Reduce revenue efficiency when the player repeats the same business too often.

    First run today (times_operated_today = 0): no penalty, multiplier = 1.00.
    Each subsequent run applies an additional saturation_penalty_rate reduction.

    Economic rationale: a single player's small local market is finite.
    Running the same business five times in one day floods local supply and
    collapses effective demand — the market simply cannot absorb that volume.

    Formula:
        penalty     = times_operated_today × saturation_penalty_rate
        multiplier  = 1.0 − penalty

    Range: [0.55, 1.00] — clamped.
    """
    penalty = times_operated_today * float(business_type.saturation_penalty_rate)
    multiplier = 1.0 - penalty
    return round(max(0.55, min(1.00, multiplier)), 4)


def calculate_macro_margin_modifier(
    business_type,
    oil_index: float,
    inflation: float,
    input_cost_xgp: float,
    base_revenue_xgp: float,
) -> float:
    """Return a negative margin modifier representing macro input cost pressure.

    Three compression sources; none can help margins — this modifier is always ≤ 0:

      oil_component         — oil price spikes hurt fuel-intensive businesses
                              (food_truck oil_margin_sensitivity=0.25 vs
                               fruit_shop=0.05)
      inflation_component   — real margins erode when inflation exceeds 2 % baseline
      input_pressure        — expensive inputs relative to revenue squeeze margins
                              (food_truck input_cost_pressure_weight=0.70 vs 0.55)

    Formula:
        oil_component           = ((oil_index − 100) / 100) × oil_sensitivity
        inflation_component     = ((inflation − 2.0) / 100) × 0.15
        input_pressure_comp     = (input_cost / max(base_revenue, 1)) × weight
        macro_margin_modifier   = −(oil + inflation + input_pressure × 0.10)

    Range: [−0.30, 0.00] — clamped.  Negative profit is allowed downstream.
    """
    oil_component = (
        (oil_index - 100.0) / 100.0
    ) * float(business_type.oil_margin_sensitivity)

    inflation_component = ((inflation - 2.0) / 100.0) * 0.15

    safe_revenue = max(float(base_revenue_xgp), 1.0)
    input_pressure_component = (
        float(input_cost_xgp) / safe_revenue
    ) * float(business_type.input_cost_pressure_weight)

    raw = -(oil_component + inflation_component + input_pressure_component * 0.10)
    return round(max(-0.30, min(0.00, raw)), 4)


def calculate_final_margin_multiplier(
    demand_multiplier: float,
    saturation_penalty_multiplier: float,
    macro_margin_modifier: float,
) -> float:
    """Combine demand, saturation, and macro pressure into one revenue multiplier.

    Formula:
        final = (demand_multiplier × saturation_penalty_multiplier) + macro_margin_modifier

    Range: [0.40, 1.30] — clamped.

    With no saturation and good macro conditions the multiplier approaches 1.25.
    With heavy saturation + oil shock + high inflation it can drop near 0.40,
    making the run barely cover overhead (or not at all).
    """
    raw = demand_multiplier * saturation_penalty_multiplier + macro_margin_modifier
    return round(max(0.40, min(1.30, raw)), 4)


def build_business_balance_summary(
    fixed_overhead_xgp: float,
    demand_multiplier: float,
    saturation_penalty_multiplier: float,
    macro_margin_modifier: float,
    final_margin_multiplier: float,
) -> dict:
    """Return a JSON-friendly dict of all Step 11 balancing values.

    Used by the API to give the frontend full transparency about why
    a business run produced the profit (or loss) that it did.
    """
    return {
        "fixed_overhead_xgp":            fixed_overhead_xgp,
        "demand_multiplier":             demand_multiplier,
        "saturation_penalty_multiplier": saturation_penalty_multiplier,
        "macro_margin_modifier":         macro_margin_modifier,
        "final_margin_multiplier":       final_margin_multiplier,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 7b LEGACY — Player condition, saturation, region, spoilage helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _money(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(_D("0.01"), rounding=ROUND_HALF_UP)


# ── Region demand — business-type-specific ────────────────────────────────────
# fruit_shop: foot traffic matters less → downtown gives modest boost
# food_truck: thrives on high-density areas → downtown gives strong boost, suburban is below baseline

_REGION_DEMAND_BY_TYPE: dict[str, dict[str, float]] = {
    "fruit_shop": {"suburban": 1.00, "downtown": 1.10},
    "food_truck":  {"suburban": 0.95, "downtown": 1.20},
}

# ── Spoilage soft thresholds (total inventory units) ─────────────────────────
_SPOILAGE_SOFT_THRESHOLD: dict[str, int] = {
    "fruit_shop": 8,
    "food_truck": 10,
}

# ── Base spoilage chance ──────────────────────────────────────────────────────
_SPOILAGE_BASE_CHANCE: dict[str, float] = {
    "fruit_shop": 0.35,
    "food_truck": 0.15,
}


# ── Player condition penalty ──────────────────────────────────────────────────

def calculate_player_condition_penalty(player: "Player") -> float:
    """Additive penalty ∈ [0.0, 0.50] that will be subtracted from the condition modifier."""
    penalty = (
        0.003 * float(player.stress)
        + 0.0025 * float(player.fatigue)
        + 0.003 * (100.0 - float(player.health))
    )
    return _clamp(penalty, 0.0, 0.50)


def calculate_player_condition_modifier(player: "Player") -> float:
    """Player condition modifier ∈ [0.50, 1.05]."""
    return _clamp(1.0 - calculate_player_condition_penalty(player), 0.50, 1.05)


# ── Operating efficiency ──────────────────────────────────────────────────────

def calculate_operating_efficiency(player: "Player", business: "Business") -> float:
    """How effectively the player runs the business today ∈ [0.45, 1.10]."""
    eff = (
        1.0
        - 0.003 * float(player.stress)
        - 0.002 * float(player.fatigue)
        - 0.003 * (100.0 - float(player.health))
    )
    # Food truck: physical fatigue hits harder
    if business.business_type == "food_truck":
        eff -= 0.001 * float(player.fatigue)
    return _clamp(eff, 0.45, 1.10)


# ── Saturation modifier ───────────────────────────────────────────────────────

def calculate_saturation_modifier(business: "Business") -> float:
    """Diminishing returns after sustained profitable runs ∈ [0.80, 1.00]."""
    profitable_days = int(getattr(business, "consecutive_profitable_days", 0) or 0)
    excess = max(0, profitable_days - 3)
    mod = 1.0 - excess * 0.03
    return _clamp(mod, 0.80, 1.00)


# ── Reputation modifier ───────────────────────────────────────────────────────

def calculate_reputation_modifier(business: "Business") -> float:
    """Long-run reputation effect ∈ [0.90, 1.15]."""
    rep = float(getattr(business, "demand_reputation", 1.0) or 1.0)
    return _clamp(rep, 0.90, 1.15)


# ── Consumer confidence modifier ──────────────────────────────────────────────

def calculate_confidence_modifier(economy: "EconomyState | None") -> float:
    """Demand rises with confidence, falls when consumers are cautious ∈ [0.80, 1.20]."""
    if economy is None:
        return 1.0
    val = 1.0 + (float(economy.consumer_confidence) - 100.0) * 0.004
    return _clamp(val, 0.80, 1.20)


# ── Inflation modifier ────────────────────────────────────────────────────────

def calculate_inflation_modifier(economy: "EconomyState | None") -> float:
    """High inflation suppresses discretionary demand ∈ [0.75, 1.05]."""
    if economy is None:
        return 1.0
    rate = float(economy.inflation_rate)
    val = 1.0 - max(0.0, (rate - 2.5) * 0.02)
    return _clamp(val, 0.75, 1.05)


# ── Demand factor ─────────────────────────────────────────────────────────────

def calculate_demand_factor(
    player: "Player",
    business: "Business",
    economy: "EconomyState | None",
    defn: Any,
) -> float:
    """Composite daily demand factor ∈ [0.50, 1.60]."""
    region = str(getattr(player, "region", None) or "suburban")
    region_mod = _REGION_DEMAND_BY_TYPE.get(business.business_type, {}).get(region, 1.00)
    tier_mod = TIER_DEMAND_BOOST.get(business.tier, 1.0)

    confidence_mod = calculate_confidence_modifier(economy)
    inflation_mod = calculate_inflation_modifier(economy)
    player_cond_mod = calculate_player_condition_modifier(player)
    saturation_mod = calculate_saturation_modifier(business)
    reputation_mod = calculate_reputation_modifier(business)

    demand = (
        float(defn.base_customer_demand)
        * region_mod
        * tier_mod
        * confidence_mod
        * inflation_mod
        * player_cond_mod
        * saturation_mod
        * reputation_mod
    )
    return _clamp(demand, 0.50, 1.60)


# ── Margin modifier ───────────────────────────────────────────────────────────

def calculate_margin_modifier(business_type: str, economy: "EconomyState | None") -> float:
    """Revenue-to-cost multiplier — reflects macro cost pressure ∈ [0.70, 1.10]."""
    if economy is None:
        return 1.0
    inflation_rate = float(economy.inflation_rate)
    supply_chain = float(economy.supply_chain_index)
    oil_index = float(economy.oil_index)

    mod = 1.0
    mod -= max(0.0, (inflation_rate - 2.5) * 0.015)
    # Supply chain disruption compresses margins
    mod -= max(0.0, (100.0 - supply_chain) * 0.002)

    if business_type == "food_truck":
        # Food trucks are highly sensitive to fuel prices
        mod -= max(0.0, (oil_index - 100.0) * 0.0025)

    return _clamp(mod, 0.70, 1.10)


# ── Economy pressure score ────────────────────────────────────────────────────

def calculate_economy_pressure(economy: "EconomyState | None") -> float:
    """Composite economy headwind score for analytics ∈ [0.85, 1.40].

    Higher value = more economy pressure (worse for businesses).
    """
    if economy is None:
        return 1.0
    inflation_rate = float(economy.inflation_rate)
    oil_index = float(economy.oil_index)
    supply_chain = float(economy.supply_chain_index)
    consumer_confidence = float(economy.consumer_confidence)

    pressure = (
        1.0
        + max(0.0, (inflation_rate - 2.5) * 0.03)
        + max(0.0, (oil_index - 100.0) * 0.002)
        + max(0.0, (100.0 - supply_chain) * 0.002)
        - max(0.0, (consumer_confidence - 100.0) * 0.001)
    )
    return _clamp(pressure, 0.85, 1.40)


# ── Spoilage calculation ──────────────────────────────────────────────────────

def calculate_spoilage(
    business_type: str,
    inventory_rows: "list[BusinessInventory]",
    economy: "EconomyState | None",
    unit_price_fn: Any,  # callable(basket_name: str) -> Decimal
) -> "tuple[int, Decimal]":
    """Compute spoiled_units and spoilage_cost.  Mutates inventory_rows in-place.

    Spoilage chance rises with:
    - excess inventory above soft threshold
    - low freshness
    The economy is reserved for future spoilage extensions (hot weather, etc.).
    """
    if not inventory_rows:
        return 0, _D("0")

    total_qty = sum(max(0, inv.quantity) for inv in inventory_rows)
    soft_threshold = _SPOILAGE_SOFT_THRESHOLD.get(business_type, 8)
    excess = max(0, total_qty - soft_threshold)

    base_chance = _SPOILAGE_BASE_CHANCE.get(business_type, 0.20)
    # Extra +2 % per excess unit, capped at +20 %
    excess_bonus = min(0.20, excess * 0.02)
    # Low freshness adds up to +15 % extra chance
    min_freshness = min((inv.freshness for inv in inventory_rows), default=1.0)
    freshness_bonus = max(0.0, (1.0 - min_freshness) * 0.15)

    spoilage_chance = _clamp(base_chance + excess_bonus + freshness_bonus, 0.0, 0.80)

    if random.random() > spoilage_chance:
        # No spoilage event — still age freshness slightly
        for inv in inventory_rows:
            inv.freshness = max(0.0, inv.freshness - 0.03)
        return 0, _D("0")

    # How many units spoil: 1, or 2 if heavily overstocked
    spoiled_count = 1 + (1 if excess >= 5 else 0)

    spoilage_cost = _D("0")
    remaining = spoiled_count
    for inv in inventory_rows:
        if remaining <= 0:
            break
        can_remove = min(remaining, max(0, inv.quantity))
        if can_remove > 0:
            inv.quantity -= can_remove
            price = unit_price_fn(inv.basket_name)
            spoilage_cost += _D(str(price)) * can_remove
            remaining -= can_remove

    # Age freshness regardless
    for inv in inventory_rows:
        inv.freshness = max(0.0, inv.freshness - 0.05)

    return (
        spoiled_count - remaining,  # actual units removed (may be < spoiled_count if stock ran out)
        spoilage_cost.quantize(_D("0.01"), rounding=ROUND_HALF_UP),
    )


# ── Reputation update ─────────────────────────────────────────────────────────

def update_reputation(business: "Business", net_profit: Decimal, spoiled_units: int) -> None:
    """Adjust business.demand_reputation ∈ [0.90, 1.15]."""
    rep = float(getattr(business, "demand_reputation", 1.0) or 1.0)
    if net_profit > 0:
        rep += 0.01
    else:
        rep -= 0.01
    if spoiled_units > 1:
        rep -= 0.01   # Heavy spoilage damages reputation further
    business.demand_reputation = _clamp(rep, 0.90, 1.15)


# ── Streak update ─────────────────────────────────────────────────────────────

def update_streaks(business: "Business", net_profit: Decimal) -> None:
    """Track consecutive profitable/loss days for saturation logic."""
    if net_profit > 0:
        business.consecutive_profitable_days = (
            int(getattr(business, "consecutive_profitable_days", 0) or 0) + 1
        )
        business.consecutive_loss_days = 0
    else:
        business.consecutive_loss_days = (
            int(getattr(business, "consecutive_loss_days", 0) or 0) + 1
        )
        business.consecutive_profitable_days = 0


# ── Balancing utility functions ───────────────────────────────────────────────

def estimate_expected_margin(business_type: str, tier: str, region: str) -> dict:
    """Admin/debug helper: expected margin under ideal conditions (no player strain).

    Useful for tuning revenue_multiplier and overhead values in the catalog.
    """
    defn = BUSINESS_CATALOG.get(business_type)
    if defn is None:
        return {"error": f"Unknown business type '{business_type}'."}

    region_mod = _REGION_DEMAND_BY_TYPE.get(business_type, {}).get(region, 1.00)
    tier_mod = TIER_DEMAND_BOOST.get(tier, 1.0)
    demand = _clamp(
        float(defn.base_customer_demand) * region_mod * tier_mod,
        0.50, 1.60,
    )
    input_cost = sum(
        BASKET_BASE_PRICES.get(b, 10.0) * qty
        for b, qty in defn.input_consumption.items()
    )
    gross = input_cost * defn.revenue_multiplier * demand
    net = gross - input_cost - defn.daily_overhead
    return {
        "business_type": business_type,
        "tier": tier,
        "region": region,
        "demand_factor": round(demand, 4),
        "input_cost": round(input_cost, 2),
        "expected_gross_revenue": round(gross, 2),
        "expected_overhead": defn.daily_overhead,
        "expected_net_before_fuel_spoilage": round(net, 2),
    }


def summarize_business_performance(business: "Business") -> dict:
    """Admin/debug helper: performance health snapshot for a business."""
    return {
        "business_id": str(business.id),
        "business_name": business.business_name,
        "times_operated": int(business.times_operated or 0),
        "cumulative_profit": float(getattr(business, "cumulative_profit", 0) or 0),
        "consecutive_profitable_days": int(getattr(business, "consecutive_profitable_days", 0) or 0),
        "consecutive_loss_days": int(getattr(business, "consecutive_loss_days", 0) or 0),
        "demand_reputation": round(float(getattr(business, "demand_reputation", 1.0) or 1.0), 4),
        "current_margin_modifier": round(float(getattr(business, "current_margin_modifier", 1.0) or 1.0), 4),
        "lifetime_units_sold": int(getattr(business, "lifetime_units_sold", 0) or 0),
        "lifetime_spoiled_units": int(getattr(business, "lifetime_spoiled_units", 0) or 0),
        "saturation_modifier": round(calculate_saturation_modifier(business), 4),
        "reputation_modifier": round(calculate_reputation_modifier(business), 4),
    }
