"""District-level economic modifiers.

Shared source of truth for how each map district affects gameplay economy.
Downstream services (jobs, business ops, basket pricing, action resolution)
should import `get_modifier` rather than duplicating tuning values.

This module deliberately introduces *no* behavior — it is data + lookups.
Integration into specific services happens in subsequent focused steps
documented in STEP96M_DISTRICT_ECONOMIC_SIMULATION.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.services.city_map_service import (
    CITY_LOCATIONS,
    DEFAULT_LOCATION_KEY,
    normalize_location_key,
)


@dataclass(frozen=True)
class DistrictModifier:
    """Per-district economic profile.

    Multipliers are applied to base values (1.00 = neutral).
    `stress_delta` is a flat integer added when the player acts in this district.
    `crime_risk` is a 0-100 placeholder reserved for future risk events.
    """

    key: str
    label: str
    customer_traffic_multiplier: Decimal
    wage_multiplier: Decimal
    cost_of_goods_multiplier: Decimal
    stress_delta: int
    survival_multiplier: Decimal
    crime_risk: int


NEUTRAL_MODIFIER = DistrictModifier(
    key="neutral",
    label="Neutral",
    customer_traffic_multiplier=Decimal("1.00"),
    wage_multiplier=Decimal("1.00"),
    cost_of_goods_multiplier=Decimal("1.00"),
    stress_delta=0,
    survival_multiplier=Decimal("1.00"),
    crime_risk=0,
)


DISTRICT_MODIFIERS: dict[str, DistrictModifier] = {
    "heights": DistrictModifier(
        key="heights",
        label="Heights",
        customer_traffic_multiplier=Decimal("0.85"),
        wage_multiplier=Decimal("0.90"),
        cost_of_goods_multiplier=Decimal("0.95"),
        stress_delta=-1,
        survival_multiplier=Decimal("1.00"),
        crime_risk=8,
    ),
    "midtown": DistrictModifier(
        key="midtown",
        label="Midtown",
        customer_traffic_multiplier=Decimal("1.10"),
        wage_multiplier=Decimal("1.05"),
        cost_of_goods_multiplier=Decimal("1.00"),
        stress_delta=0,
        survival_multiplier=Decimal("1.05"),
        crime_risk=18,
    ),
    "exchange": DistrictModifier(
        key="exchange",
        label="Exchange",
        customer_traffic_multiplier=Decimal("1.35"),
        wage_multiplier=Decimal("1.20"),
        cost_of_goods_multiplier=Decimal("1.10"),
        stress_delta=2,
        survival_multiplier=Decimal("1.15"),
        crime_risk=28,
    ),
    "makers": DistrictModifier(
        key="makers",
        label="Makers Row",
        customer_traffic_multiplier=Decimal("0.95"),
        wage_multiplier=Decimal("0.95"),
        cost_of_goods_multiplier=Decimal("0.90"),
        stress_delta=0,
        survival_multiplier=Decimal("0.98"),
        crime_risk=14,
    ),
    "commerce": DistrictModifier(
        key="commerce",
        label="Commerce",
        customer_traffic_multiplier=Decimal("1.20"),
        wage_multiplier=Decimal("1.15"),
        cost_of_goods_multiplier=Decimal("1.05"),
        stress_delta=1,
        survival_multiplier=Decimal("1.10"),
        crime_risk=22,
    ),
    "harbor": DistrictModifier(
        key="harbor",
        label="Harbor",
        customer_traffic_multiplier=Decimal("1.05"),
        wage_multiplier=Decimal("1.00"),
        cost_of_goods_multiplier=Decimal("0.85"),
        stress_delta=0,
        survival_multiplier=Decimal("1.02"),
        crime_risk=18,
    ),
}


# Mapping from city-location keys (see city_map_service.CITY_LOCATIONS) to
# their canonical district. These are kept in sync with the frontend's
# FIXED_NODE_ANCHORS in expo/src/components/gameMap/mapData.ts so that the
# economic modifier for a tile matches the district the player visually sees
# it in. Changing anchor positions there means updating this map here too.
LOCATION_TO_DISTRICT: dict[str, str] = {
    "home": "makers",
    "housing": "makers",
    "clinic": "makers",
    "grocery": "heights",
    "rideshare_hotspot_suburban": "makers",
    "job_center": "midtown",
    "certification_school": "midtown",
    "work": "commerce",
    "rideshare_hotspot_downtown": "midtown",
    "business_spot": "harbor",
    "bank": "exchange",
}


REGION_FALLBACK_DISTRICT: dict[str, str] = {
    "suburban": "heights",
    "downtown": "exchange",
}


def get_modifier(district_key: object) -> DistrictModifier:
    """Return the modifier for a district key, or a neutral profile."""
    key = str(district_key or "").strip().lower()
    return DISTRICT_MODIFIERS.get(key, NEUTRAL_MODIFIER)


def district_key_for_location(location_key: object) -> str:
    """Resolve a city-location key to its district key.

    Falls back to the location's region, then to neutral.
    """
    normalized = normalize_location_key(location_key)
    mapped = LOCATION_TO_DISTRICT.get(normalized)
    if mapped:
        return mapped

    location = CITY_LOCATIONS.get(normalized) or CITY_LOCATIONS[DEFAULT_LOCATION_KEY]
    region = str(location.region or "").strip().lower()
    return REGION_FALLBACK_DISTRICT.get(region, "neutral")


def get_modifier_for_location(location_key: object) -> DistrictModifier:
    return get_modifier(district_key_for_location(location_key))


def list_district_modifiers() -> Iterable[DistrictModifier]:
    return DISTRICT_MODIFIERS.values()
