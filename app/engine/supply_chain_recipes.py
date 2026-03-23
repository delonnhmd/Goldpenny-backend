"""Step 43 — Supply Chain Graph Physical Node Recipes.

Defines the 12 MVP physical nodes, their mapping to Step 13 abstract nodes,
basket recipes using physical node weights, and job pressure mappings for
bottleneck-driven opportunity detection.
"""

from __future__ import annotations

# ── Physical node IDs ─────────────────────────────────────────────────────────

MVP_NODE_IDS: tuple[str, ...] = (
    "OIL_FUEL",
    "ELECTRICITY",
    "WATER",
    "FERTILIZER",
    "FEED",
    "PACKAGING",
    "FARM",
    "DAIRY",
    "RANCH_POULTRY",
    "FOOD_PROCESSING",
    "WAREHOUSE_DISTRIBUTION",
    "TRUCKING_LASTMILE",
)

# ── Physical node → Step 13 abstract node bridge ──────────────────────────────
#
# Physical nodes derive their baseline availability from the corresponding
# Step 13 abstract node's computed availability.  Multiple physical nodes
# can share the same abstract bridge (e.g., FARM, DAIRY, and WATER all derive
# from the "farming" abstract node).

NODE_TO_ABSTRACT_BRIDGE: dict[str, str] = {
    "OIL_FUEL": "fuel",
    "ELECTRICITY": "utilities",
    "WATER": "farming",
    "FERTILIZER": "fertilizer",
    "FEED": "farming",
    "PACKAGING": "retail",
    "FARM": "farming",
    "DAIRY": "farming",
    "RANCH_POULTRY": "farming",
    "FOOD_PROCESSING": "processing",
    "WAREHOUSE_DISTRIBUTION": "retail",
    "TRUCKING_LASTMILE": "trucking",
}

# ── Per-node reliability scaling factors ─────────────────────────────────────
#
# Multiplier applied on top of the abstract availability to differentiate
# physical nodes that share the same abstract bridge.  Values < 1.0 represent
# nodes that are more vulnerable than the abstract average.

NODE_RELIABILITY_SCALE: dict[str, float] = {
    "OIL_FUEL": 1.00,
    "ELECTRICITY": 1.00,
    "WATER": 0.97,          # slightly more fragile than general farming
    "FERTILIZER": 1.00,
    "FEED": 0.98,
    "PACKAGING": 1.00,
    "FARM": 0.99,
    "DAIRY": 0.96,          # perishable operations, higher fragility
    "RANCH_POULTRY": 0.97,
    "FOOD_PROCESSING": 1.00,
    "WAREHOUSE_DISTRIBUTION": 1.00,
    "TRUCKING_LASTMILE": 1.00,
}

# ── Region availability modifiers ─────────────────────────────────────────────
#
# Multiply the base availability for each (node, region) combination.
# suburban is the baseline (1.00); downtown often has better distribution
# but higher oil/trucking dependency.

NODE_REGION_MODIFIERS: dict[str, dict[str, float]] = {
    "OIL_FUEL": {
        "suburban": 1.00,
        "downtown": 0.96,       # higher congestion degrades fuel logistics
        "rural": 1.02,
    },
    "ELECTRICITY": {
        "suburban": 1.00,
        "downtown": 1.02,
        "rural": 0.95,
    },
    "WATER": {
        "suburban": 1.00,
        "downtown": 1.00,
        "rural": 0.96,
    },
    "FERTILIZER": {
        "suburban": 1.00,
        "downtown": 0.98,
        "rural": 1.02,
    },
    "FEED": {
        "suburban": 1.00,
        "downtown": 0.97,
        "rural": 1.01,
    },
    "PACKAGING": {
        "suburban": 1.00,
        "downtown": 1.02,
        "rural": 0.96,
    },
    "FARM": {
        "suburban": 1.00,
        "downtown": 0.94,       # minimal farming capacity downtown
        "rural": 1.04,
    },
    "DAIRY": {
        "suburban": 1.00,
        "downtown": 0.95,
        "rural": 1.03,
    },
    "RANCH_POULTRY": {
        "suburban": 1.00,
        "downtown": 0.95,
        "rural": 1.04,
    },
    "FOOD_PROCESSING": {
        "suburban": 1.00,
        "downtown": 1.01,
        "rural": 0.97,
    },
    "WAREHOUSE_DISTRIBUTION": {
        "suburban": 1.02,
        "downtown": 0.98,       # congestion limits warehouse throughput
        "rural": 0.96,
    },
    "TRUCKING_LASTMILE": {
        "suburban": 1.00,
        "downtown": 0.93,       # downtown congestion hits last-mile hard
        "rural": 1.00,
    },
}

# ── MVP basket recipes (physical node weights) ────────────────────────────────
#
# Each basket maps physical node IDs to contribution weights that sum to 1.00.

GRAPH_BASKET_RECIPES: dict[str, dict[str, float]] = {
    "essentials": {
        "FARM": 0.25,
        "DAIRY": 0.20,
        "PACKAGING": 0.10,
        "WAREHOUSE_DISTRIBUTION": 0.20,
        "TRUCKING_LASTMILE": 0.15,
        "OIL_FUEL": 0.10,
    },
    "protein": {
        "FEED": 0.15,
        "RANCH_POULTRY": 0.20,
        "FOOD_PROCESSING": 0.20,
        "PACKAGING": 0.10,
        "WAREHOUSE_DISTRIBUTION": 0.10,
        "TRUCKING_LASTMILE": 0.15,
        "OIL_FUEL": 0.10,
    },
    "produce": {
        "FARM": 0.30,
        "WATER": 0.15,
        "FERTILIZER": 0.15,
        "PACKAGING": 0.10,
        "WAREHOUSE_DISTRIBUTION": 0.10,
        "TRUCKING_LASTMILE": 0.15,
        "OIL_FUEL": 0.05,
    },
    "convenience": {
        "FOOD_PROCESSING": 0.25,
        "PACKAGING": 0.15,
        "ELECTRICITY": 0.15,
        "WAREHOUSE_DISTRIBUTION": 0.20,
        "TRUCKING_LASTMILE": 0.15,
        "OIL_FUEL": 0.10,
    },
}

# ── Job pressure map (node → job → bottleneck weight) ─────────────────────────
#
# When a physical node is constrained, jobs that depend on its supply chain
# see increased demand / opportunity pressure.  Weights represent the
# proportional contribution to job_pressure_multiplier.

JOB_BOTTLENECK_MAP: dict[str, dict[str, float]] = {
    "TRUCKING_LASTMILE": {
        "delivery_driver": 0.70,
        "ride_share_driver": 0.40,
    },
    "WAREHOUSE_DISTRIBUTION": {
        "retail_worker": 0.70,
        "delivery_driver": 0.25,
    },
    "FARM": {
        "delivery_driver": 0.20,
        "chef": 0.40,
    },
    "WATER": {
        "delivery_driver": 0.20,
        "chef": 0.30,
    },
    "FERTILIZER": {
        "delivery_driver": 0.15,
        "chef": 0.30,
    },
    "FEED": {
        "chef": 0.60,
        "delivery_driver": 0.20,
    },
    "RANCH_POULTRY": {
        "chef": 0.60,
        "delivery_driver": 0.20,
    },
    "FOOD_PROCESSING": {
        "chef": 0.40,
        "retail_worker": 0.25,
    },
    "ELECTRICITY": {
        "chef": 0.35,
        "retail_worker": 0.25,
    },
    "OIL_FUEL": {
        "auto_mechanic": 0.70,
        "delivery_driver": 0.30,
    },
    "DAIRY": {
        "chef": 0.35,
        "delivery_driver": 0.20,
    },
    "PACKAGING": {
        "retail_worker": 0.20,
    },
}

# ── Severity label thresholds ─────────────────────────────────────────────────

def bottleneck_severity_label(availability: float) -> str:
    """Map a node availability score to a human-readable severity label."""
    if availability >= 0.90:
        return "none"
    if availability >= 0.80:
        return "minor"
    if availability >= 0.70:
        return "moderate"
    if availability >= 0.60:
        return "severe"
    return "critical"


def cost_pressure_label(multiplier: float) -> str:
    """Map a basket supply multiplier to a cost-pressure label."""
    if multiplier >= 1.08:
        return "critical"
    if multiplier >= 1.03:
        return "high"
    if multiplier >= 1.00:
        return "elevated"
    return "low"


def opportunity_label(bottleneck_count: int, max_pressure: float) -> str:
    """Derive an opportunity label from number of bottlenecks and max pressure."""
    if bottleneck_count == 0 or max_pressure < 0.05:
        return "weak"
    if max_pressure < 0.15:
        return "emerging"
    if max_pressure < 0.30:
        return "strong"
    return "surge"


def validate_graph_recipes() -> None:
    """Assert that all basket weights sum to 1.00 (within floating-point tolerance)."""
    for basket, weights in GRAPH_BASKET_RECIPES.items():
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"GRAPH_BASKET_RECIPES[{basket!r}] weights sum to {total:.6f} — expected 1.0"
            )
    for node_id in MVP_NODE_IDS:
        if node_id not in NODE_TO_ABSTRACT_BRIDGE:
            raise ValueError(f"Node {node_id!r} missing from NODE_TO_ABSTRACT_BRIDGE")


validate_graph_recipes()
