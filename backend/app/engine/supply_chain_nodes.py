"""Static supply-chain node definitions for Step 13 compute-only engine."""

from __future__ import annotations

from decimal import Decimal

DEFAULT_MIN_AVAILABILITY = Decimal("0.70")
DEFAULT_MAX_AVAILABILITY = Decimal("1.10")


# Deterministic tuning map for node availability.
# Values are intentionally conservative and bounded for MVP.
SUPPLY_CHAIN_NODES: dict[str, dict] = {
    "fuel": {
        "node_key": "fuel",
        "display_name": "Fuel",
        "category": "energy",
        "depends_on": [],
        "sensitivities": {
            "oil_pressure": Decimal("0.30"),
            "inflation_pressure": Decimal("0.05"),
            "supply_stress_pressure": Decimal("0.10"),
            "confidence_weakness": Decimal("0.01"),
        },
        "support_sensitivities": {
            "oil_relief": Decimal("0.08"),
            "supply_relief": Decimal("0.03"),
        },
        "dependency_weight": Decimal("0.00"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "labor": {
        "node_key": "labor",
        "display_name": "Labor",
        "category": "workforce",
        "depends_on": [],
        "sensitivities": {
            "unemployment_pressure": Decimal("0.16"),
            "inflation_pressure": Decimal("0.04"),
            "supply_stress_pressure": Decimal("0.05"),
        },
        "support_sensitivities": {
            "confidence_support": Decimal("0.05"),
            "supply_relief": Decimal("0.02"),
        },
        "dependency_weight": Decimal("0.00"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "utilities": {
        "node_key": "utilities",
        "display_name": "Utilities",
        "category": "infrastructure",
        "depends_on": ["fuel", "labor"],
        "sensitivities": {
            "inflation_pressure": Decimal("0.08"),
            "supply_stress_pressure": Decimal("0.07"),
            "oil_pressure": Decimal("0.04"),
        },
        "support_sensitivities": {
            "inflation_relief": Decimal("0.03"),
            "supply_relief": Decimal("0.03"),
        },
        "dependency_weight": Decimal("0.08"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "fertilizer": {
        "node_key": "fertilizer",
        "display_name": "Fertilizer",
        "category": "input",
        "depends_on": ["fuel", "utilities"],
        "sensitivities": {
            "oil_pressure": Decimal("0.13"),
            "supply_stress_pressure": Decimal("0.10"),
            "inflation_pressure": Decimal("0.06"),
        },
        "support_sensitivities": {
            "oil_relief": Decimal("0.05"),
            "supply_relief": Decimal("0.03"),
        },
        "dependency_weight": Decimal("0.07"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "farming": {
        "node_key": "farming",
        "display_name": "Farming",
        "category": "raw_goods",
        "depends_on": ["fertilizer", "labor"],
        "sensitivities": {
            "supply_stress_pressure": Decimal("0.12"),
            "inflation_pressure": Decimal("0.05"),
            "oil_pressure": Decimal("0.04"),
        },
        "support_sensitivities": {
            "confidence_support": Decimal("0.03"),
            "supply_relief": Decimal("0.04"),
        },
        "dependency_weight": Decimal("0.10"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "trucking": {
        "node_key": "trucking",
        "display_name": "Trucking",
        "category": "logistics",
        "depends_on": ["fuel", "labor"],
        "sensitivities": {
            "oil_pressure": Decimal("0.15"),
            "supply_stress_pressure": Decimal("0.12"),
            "inflation_pressure": Decimal("0.05"),
        },
        "support_sensitivities": {
            "oil_relief": Decimal("0.05"),
            "confidence_support": Decimal("0.02"),
        },
        "dependency_weight": Decimal("0.12"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "processing": {
        "node_key": "processing",
        "display_name": "Processing",
        "category": "manufacturing",
        "depends_on": ["utilities", "labor"],
        "sensitivities": {
            "inflation_pressure": Decimal("0.11"),
            "supply_stress_pressure": Decimal("0.09"),
            "confidence_weakness": Decimal("0.04"),
        },
        "support_sensitivities": {
            "inflation_relief": Decimal("0.04"),
            "confidence_support": Decimal("0.03"),
        },
        "dependency_weight": Decimal("0.09"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
    "retail": {
        "node_key": "retail",
        "display_name": "Retail",
        "category": "distribution",
        "depends_on": ["processing", "trucking", "labor"],
        "sensitivities": {
            "confidence_weakness": Decimal("0.11"),
            "inflation_pressure": Decimal("0.08"),
            "supply_stress_pressure": Decimal("0.06"),
        },
        "support_sensitivities": {
            "confidence_support": Decimal("0.06"),
            "inflation_relief": Decimal("0.02"),
        },
        "dependency_weight": Decimal("0.10"),
        "min_availability": DEFAULT_MIN_AVAILABILITY,
        "max_availability": DEFAULT_MAX_AVAILABILITY,
    },
}
