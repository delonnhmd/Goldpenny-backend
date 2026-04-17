"""City map rules for strategic travel and location-sensitive actions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models.player import Player

DEFAULT_LOCATION_KEY = "home"


@dataclass(frozen=True)
class CityLocation:
    key: str
    label: str
    region: str
    node_type: str
    opportunity_tier: str
    rideshare_quality: str


@dataclass(frozen=True)
class TravelRule:
    time_cost_units: int
    stress_delta: int
    cash_cost_xgp: Decimal
    route_label: str


CITY_LOCATIONS: dict[str, CityLocation] = {
    "home": CityLocation(
        key="home",
        label="Home",
        region="Suburban",
        node_type="home",
        opportunity_tier="moderate",
        rideshare_quality="low",
    ),
    "work": CityLocation(
        key="work",
        label="Work",
        region="Downtown",
        node_type="work",
        opportunity_tier="moderate",
        rideshare_quality="moderate",
    ),
    "job_center": CityLocation(
        key="job_center",
        label="Job Center",
        region="Downtown",
        node_type="job_board",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "grocery": CityLocation(
        key="grocery",
        label="Grocery / Food",
        region="Suburban",
        node_type="grocery",
        opportunity_tier="low",
        rideshare_quality="restricted",
    ),
    "rideshare_hotspot_downtown": CityLocation(
        key="rideshare_hotspot_downtown",
        label="Downtown Rideshare Hotspot",
        region="Downtown",
        node_type="rideshare_hotspot",
        opportunity_tier="high",
        rideshare_quality="high",
    ),
    "rideshare_hotspot_suburban": CityLocation(
        key="rideshare_hotspot_suburban",
        label="Suburban Rideshare Hotspot",
        region="Suburban",
        node_type="rideshare_hotspot",
        opportunity_tier="moderate",
        rideshare_quality="moderate",
    ),
    "business_spot": CityLocation(
        key="business_spot",
        label="Business Spot (Soon)",
        region="Downtown",
        node_type="business",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "car_sale": CityLocation(
        key="car_sale",
        label="Car Dealership",
        region="Downtown",
        node_type="car_sale",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "bank": CityLocation(
        key="bank",
        label="Bank",
        region="Downtown",
        node_type="bank",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "housing": CityLocation(
        key="housing",
        label="Housing Office",
        region="Suburban",
        node_type="housing",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "stock_center": CityLocation(
        key="stock_center",
        label="Stock Center",
        region="Downtown",
        node_type="stock_center",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "certification_school": CityLocation(
        key="certification_school",
        label="Certification School",
        region="Downtown",
        node_type="certification_school",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "clinic": CityLocation(
        key="clinic",
        label="Clinic",
        region="Suburban",
        node_type="clinic",
        opportunity_tier="moderate",
        rideshare_quality="restricted",
    ),
    "gas_station": CityLocation(
        key="gas_station",
        label="Gas Station",
        region="Suburban",
        node_type="gas_station",
        opportunity_tier="low",
        rideshare_quality="restricted",
    ),
}


TRAVEL_RULES: dict[frozenset[str], TravelRule] = {
    frozenset({"home", "grocery"}): TravelRule(1, 0, Decimal("0.00"), "Local errand route"),
    frozenset({"home", "work"}): TravelRule(2, 1, Decimal("1.00"), "Commute corridor"),
    frozenset({"home", "job_center"}): TravelRule(2, 1, Decimal("1.00"), "Career commute"),
    frozenset({"home", "rideshare_hotspot_suburban"}): TravelRule(1, 0, Decimal("0.00"), "Suburban connector"),
    frozenset({"home", "rideshare_hotspot_downtown"}): TravelRule(2, 1, Decimal("1.00"), "City inbound route"),
    frozenset({"grocery", "job_center"}): TravelRule(2, 1, Decimal("1.00"), "Errand-to-career route"),
    frozenset({"grocery", "work"}): TravelRule(2, 1, Decimal("1.00"), "Cross-district route"),
    frozenset({"grocery", "rideshare_hotspot_suburban"}): TravelRule(1, 0, Decimal("0.00"), "Local rideshare loop"),
    frozenset({"grocery", "rideshare_hotspot_downtown"}): TravelRule(2, 1, Decimal("1.00"), "Downtown transfer"),
    frozenset({"job_center", "work"}): TravelRule(1, 0, Decimal("0.00"), "Job district connector"),
    frozenset({"job_center", "rideshare_hotspot_downtown"}): TravelRule(1, 0, Decimal("0.00"), "Career district hop"),
    frozenset({"job_center", "rideshare_hotspot_suburban"}): TravelRule(2, 1, Decimal("1.00"), "Cross-town hiring route"),
    frozenset({"work", "rideshare_hotspot_downtown"}): TravelRule(1, 0, Decimal("0.00"), "Downtown short hop"),
    frozenset({"work", "rideshare_hotspot_suburban"}): TravelRule(2, 1, Decimal("1.00"), "Suburban transfer"),
    frozenset({"rideshare_hotspot_suburban", "rideshare_hotspot_downtown"}): TravelRule(2, 1, Decimal("1.00"), "Hotspot transfer"),
    frozenset({"work", "business_spot"}): TravelRule(1, 0, Decimal("0.00"), "Business district route"),
    frozenset({"job_center", "business_spot"}): TravelRule(1, 0, Decimal("0.00"), "Opportunity corridor"),
    frozenset({"home", "business_spot"}): TravelRule(2, 1, Decimal("1.00"), "Business commute"),
    frozenset({"grocery", "business_spot"}): TravelRule(2, 1, Decimal("1.00"), "Supply route"),
    frozenset({"rideshare_hotspot_downtown", "business_spot"}): TravelRule(1, 0, Decimal("0.00"), "Downtown opportunity lane"),
    frozenset({"rideshare_hotspot_suburban", "business_spot"}): TravelRule(2, 1, Decimal("1.00"), "Cross-town business lane"),
}


RIDESHARE_BASE_PROFILES: dict[str, dict[str, Any]] = {
    "rideshare_hotspot_downtown": {
        "multiplier": Decimal("1.12"),
        "night_multiplier": Decimal("1.22"),
        "stress_delta_modifier": 1,
        "health_delta_modifier": 0,
        "label": "Downtown hotspot bonus",
        "tier": "high",
        "allowed": True,
        "reason_if_blocked": "",
    },
    "rideshare_hotspot_suburban": {
        "multiplier": Decimal("0.95"),
        "night_multiplier": Decimal("0.98"),
        "stress_delta_modifier": -1,
        "health_delta_modifier": 0,
        "label": "Suburban hotspot stability",
        "tier": "moderate",
        "allowed": True,
        "reason_if_blocked": "",
    },
    "work": {
        "multiplier": Decimal("0.98"),
        "night_multiplier": Decimal("1.00"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Work area demand",
        "tier": "moderate",
        "allowed": True,
        "reason_if_blocked": "",
    },
    "job_center": {
        "multiplier": Decimal("0.82"),
        "night_multiplier": Decimal("0.82"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Job center demand",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Job Center. Travel to a hotspot first.",
    },
    "home": {
        "multiplier": Decimal("0.88"),
        "night_multiplier": Decimal("0.92"),
        "stress_delta_modifier": -1,
        "health_delta_modifier": 0,
        "label": "Home zone low demand",
        "tier": "low",
        "allowed": True,
        "reason_if_blocked": "",
    },
    "grocery": {
        "multiplier": Decimal("0.80"),
        "night_multiplier": Decimal("0.80"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Grocery zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at Grocery. Travel to a hotspot first.",
    },
    "business_spot": {
        "multiplier": Decimal("0.90"),
        "night_multiplier": Decimal("0.95"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Business district demand",
        "tier": "moderate",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at Business Spot right now.",
    },
    "car_sale": {
        "multiplier": Decimal("0.85"),
        "night_multiplier": Decimal("0.88"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Dealership zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Car Dealership. Travel to a hotspot first.",
    },
    "bank": {
        "multiplier": Decimal("0.85"),
        "night_multiplier": Decimal("0.88"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Bank zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Bank. Travel to a hotspot first.",
    },
    "housing": {
        "multiplier": Decimal("0.82"),
        "night_multiplier": Decimal("0.85"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Housing zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Housing Office. Travel to a hotspot first.",
    },
    "stock_center": {
        "multiplier": Decimal("0.88"),
        "night_multiplier": Decimal("0.90"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Stock center zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Stock Center. Travel to a hotspot first.",
    },
    "certification_school": {
        "multiplier": Decimal("0.85"),
        "night_multiplier": Decimal("0.85"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Certification school zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Certification School. Travel to a hotspot first.",
    },
    "clinic": {
        "multiplier": Decimal("0.85"),
        "night_multiplier": Decimal("0.90"),
        "stress_delta_modifier": -1,
        "health_delta_modifier": 0,
        "label": "Clinic zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Clinic. Travel to a hotspot first.",
    },
    "gas_station": {
        "multiplier": Decimal("0.82"),
        "night_multiplier": Decimal("0.88"),
        "stress_delta_modifier": 0,
        "health_delta_modifier": 0,
        "label": "Gas station zone",
        "tier": "low",
        "allowed": False,
        "reason_if_blocked": "Ride share is unavailable at the Gas Station. Travel to a hotspot first.",
    },
}


RIDESHARE_BASE_PAY_RANGE: dict[str, tuple[Decimal, Decimal]] = {
    "midday": (Decimal("12.00"), Decimal("20.00")),
    "morning_peak": (Decimal("18.00"), Decimal("28.00")),
    "evening_peak": (Decimal("18.00"), Decimal("28.00")),
    "night": (Decimal("22.00"), Decimal("35.00")),
}


def normalize_location_key(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in CITY_LOCATIONS:
        return raw
    return DEFAULT_LOCATION_KEY


def ensure_player_location(player: Player) -> str:
    normalized = normalize_location_key(getattr(player, "current_location_key", DEFAULT_LOCATION_KEY))
    if getattr(player, "current_location_key", None) != normalized:
        player.current_location_key = normalized
    return normalized


def get_location_definition(location_key: object) -> CityLocation:
    return CITY_LOCATIONS[normalize_location_key(location_key)]


def get_location_label(location_key: object) -> str:
    return get_location_definition(location_key).label


def get_location_region(location_key: object) -> str:
    return get_location_definition(location_key).region


def list_city_nodes(*, current_location_key: object | None = None) -> list[dict[str, Any]]:
    current = normalize_location_key(current_location_key)
    nodes: list[dict[str, Any]] = []
    for location in CITY_LOCATIONS.values():
        nodes.append(
            {
                "key": location.key,
                "label": location.label,
                "region": location.region,
                "node_type": location.node_type,
                "opportunity_tier": location.opportunity_tier,
                "rideshare_quality": location.rideshare_quality,
                "is_current_location": location.key == current,
            }
        )
    return nodes


def get_travel_rule(from_location_key: object, to_location_key: object) -> TravelRule:
    src = normalize_location_key(from_location_key)
    dest = normalize_location_key(to_location_key)
    if src == dest:
        return TravelRule(
            time_cost_units=0,
            stress_delta=0,
            cash_cost_xgp=Decimal("0.00"),
            route_label="Already at destination",
        )

    keyed = TRAVEL_RULES.get(frozenset({src, dest}))
    if keyed is not None:
        return keyed

    src_region = get_location_region(src).lower()
    dest_region = get_location_region(dest).lower()
    if src_region == dest_region:
        return TravelRule(
            time_cost_units=1,
            stress_delta=0,
            cash_cost_xgp=Decimal("0.00"),
            route_label="Intra-region route",
        )
    return TravelRule(
        time_cost_units=2,
        stress_delta=1,
        cash_cost_xgp=Decimal("1.00"),
        route_label="Cross-region route",
    )


def get_rideshare_location_profile(location_key: object, mode: object) -> dict[str, Any]:
    normalized_location = normalize_location_key(location_key)
    normalized_mode = str(mode or "midday").strip().lower() or "midday"
    base = RIDESHARE_BASE_PROFILES.get(normalized_location) or RIDESHARE_BASE_PROFILES["home"]
    multiplier = Decimal(str(base["night_multiplier"] if normalized_mode == "night" else base["multiplier"]))
    bonus_pct = (multiplier - Decimal("1.00")) * Decimal("100")
    return {
        "location_key": normalized_location,
        "location_label": get_location_label(normalized_location),
        "region": get_location_region(normalized_location),
        "allowed": bool(base["allowed"]),
        "multiplier": float(multiplier),
        "demand_bonus_pct": float(round(bonus_pct, 2)),
        "stress_delta_modifier": int(base["stress_delta_modifier"]),
        "health_delta_modifier": int(base["health_delta_modifier"]),
        "label": str(base["label"]),
        "tier": str(base["tier"]),
        "reason_if_blocked": str(base["reason_if_blocked"]),
    }


def estimate_rideshare_pay_range(
    *,
    mode: object,
    location_key: object,
    trips: int = 1,
) -> tuple[float, float]:
    normalized_mode = str(mode or "midday").strip().lower() or "midday"
    base_min, base_max = RIDESHARE_BASE_PAY_RANGE.get(normalized_mode, RIDESHARE_BASE_PAY_RANGE["midday"])
    profile = get_rideshare_location_profile(location_key, normalized_mode)
    multiplier = Decimal(str(profile["multiplier"]))
    trip_count = max(1, int(trips))
    adjusted_min = (base_min * multiplier * Decimal(str(trip_count))).quantize(Decimal("0.01"))
    adjusted_max = (base_max * multiplier * Decimal(str(trip_count))).quantize(Decimal("0.01"))
    return float(adjusted_min), float(adjusted_max)


def build_city_map_snapshot(*, current_location_key: object) -> dict[str, Any]:
    current_key = normalize_location_key(current_location_key)
    current = get_location_definition(current_key)
    travel_options: list[dict[str, Any]] = []
    for location in CITY_LOCATIONS.values():
        if location.key == current_key:
            continue
        rule = get_travel_rule(current_key, location.key)
        profile = get_rideshare_location_profile(location.key, "midday")
        travel_options.append(
            {
                "from_key": current_key,
                "from_label": current.label,
                "destination_key": location.key,
                "destination_label": location.label,
                "destination_region": location.region,
                "destination_node_type": location.node_type,
                "destination_opportunity_tier": location.opportunity_tier,
                "time_cost_units": int(rule.time_cost_units),
                "stress_delta": int(rule.stress_delta),
                "cash_cost_xgp": float(rule.cash_cost_xgp),
                "route_label": rule.route_label,
                "rideshare_quality": location.rideshare_quality,
                "rideshare_allowed": bool(profile["allowed"]),
                "rideshare_demand_bonus_pct": float(profile["demand_bonus_pct"]),
            }
        )

    return {
        "current_location_key": current.key,
        "current_location_label": current.label,
        "current_location_region": current.region,
        "current_location_node_type": current.node_type,
        "nodes": list_city_nodes(current_location_key=current.key),
        "travel_options": travel_options,
    }
