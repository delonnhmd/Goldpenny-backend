"""Static business definition catalog for Gold Penny — Step 7.

Business definitions are pure Python data, not stored in the database.
They are loaded by the business engine and exposed through the API.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BusinessDefinition:
    name: str
    display_name: str
    startup_cost: float
    daily_overhead: float
    base_customer_demand: float
    spoilage_risk: str              # "high" | "medium" | "low"
    fuel_sensitivity: str           # "high" | "medium" | "low"
    labor_intensity: str            # "high" | "medium" | "low"
    health_stress_impact: str       # "high" | "medium" | "low"
    required_input_baskets: list    # list[str] — baskets that must be in inventory
    revenue_multiplier: float       # applied on top of input cost basis
    max_daily_operations: int
    upgrade_path: list              # list[str] — tier names in progression order
    # ── Per-operation player impact ────────────────────────────────────────
    time_cost_hours: int
    stress_change_per_op: int
    health_change_per_op: int
    fatigue_change_per_op: float
    # ── Input units consumed per operation ────────────────────────────────
    input_consumption: dict         # {basket_name: int}
    # ── Upgrade cost from current tier to next ────────────────────────────
    upgrade_costs: dict             # {current_tier: float}


# ── MVP Business Catalog ──────────────────────────────────────────────────────

BUSINESS_CATALOG: dict[str, BusinessDefinition] = {
    "fruit_shop": BusinessDefinition(
        name="fruit_shop",
        display_name="Fruit Shop",
        startup_cost=500.0,
        daily_overhead=20.0,
        base_customer_demand=1.0,
        spoilage_risk="high",
        fuel_sensitivity="low",
        labor_intensity="medium",
        health_stress_impact="medium",
        required_input_baskets=["produce_basket"],
        revenue_multiplier=1.20,
        max_daily_operations=1,
        upgrade_path=["cart", "small_shop", "large_store"],
        time_cost_hours=4,
        stress_change_per_op=5,
        health_change_per_op=1,
        fatigue_change_per_op=5.0,
        input_consumption={"produce_basket": 2},
        upgrade_costs={
            "cart": 700.0,
            "small_shop": 2000.0,
        },
    ),
    "food_truck": BusinessDefinition(
        name="food_truck",
        display_name="Food Truck",
        startup_cost=1200.0,
        daily_overhead=35.0,
        base_customer_demand=1.1,
        spoilage_risk="medium",
        fuel_sensitivity="high",
        labor_intensity="high",
        health_stress_impact="high",
        required_input_baskets=["essentials_basket", "protein_basket"],
        revenue_multiplier=1.35,
        max_daily_operations=1,
        upgrade_path=["basic_truck", "upgraded_truck", "restaurant_future"],
        time_cost_hours=5,
        stress_change_per_op=7,
        health_change_per_op=2,
        fatigue_change_per_op=6.0,
        input_consumption={"essentials_basket": 2, "protein_basket": 2},
        upgrade_costs={
            "basic_truck": 1200.0,
            # upgraded_truck -> restaurant_future is blocked for MVP
        },
    ),
}

# ── Per-basket base market price (before economy modifiers) ──────────────────
# Used by business engine to price inventory purchases and compute COGS.

BASKET_BASE_PRICES: dict[str, float] = {
    "produce_basket": 10.00,      # fresh fruit and vegetables
    "essentials_basket": 15.00,   # basic food staples
    "protein_basket": 12.00,      # meats, eggs, legumes
}

# ── Tier demand boosts (applied to base_customer_demand during operate) ───────

TIER_DEMAND_BOOST: dict[str, float] = {
    "cart": 1.00,
    "small_shop": 1.10,
    "large_store": 1.20,
    "basic_truck": 1.00,
    "upgraded_truck": 1.10,
    "restaurant_future": 1.25,
}

# ── Region modifiers ──────────────────────────────────────────────────────────

REGION_DEMAND_MOD: dict[str, float] = {
    "downtown": 1.15,
    "suburban": 1.00,
}

REGION_PRICE_MOD: dict[str, float] = {
    "downtown": 1.05,
    "suburban": 1.00,
}
