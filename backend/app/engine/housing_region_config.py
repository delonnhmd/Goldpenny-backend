"""Static tuning config for Step 17 housing/region tradeoffs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RegionConfig:
    region_key: str
    housing_type_default: str
    commute_mode_default: str
    monthly_housing_cost_xgp: Decimal
    monthly_utilities_cost_xgp: Decimal
    monthly_transport_base_xgp: Decimal
    commute_hours_baseline: Decimal
    commute_hours_per_activity: Decimal
    region_stress_load: Decimal
    job_opportunity_modifier: Decimal
    business_demand_modifier: Decimal
    side_income_modifier: Decimal
    networking_modifier: Decimal


REGION_CONFIG: dict[str, RegionConfig] = {
    "suburban": RegionConfig(
        region_key="suburban",
        housing_type_default="rent",
        commute_mode_default="car",
        monthly_housing_cost_xgp=Decimal("540.00"),
        monthly_utilities_cost_xgp=Decimal("105.00"),
        monthly_transport_base_xgp=Decimal("165.00"),
        commute_hours_baseline=Decimal("1.20"),
        commute_hours_per_activity=Decimal("0.35"),
        region_stress_load=Decimal("-0.60"),
        job_opportunity_modifier=Decimal("-0.06"),
        business_demand_modifier=Decimal("-0.08"),
        side_income_modifier=Decimal("-0.05"),
        networking_modifier=Decimal("-0.05"),
    ),
    "downtown": RegionConfig(
        region_key="downtown",
        housing_type_default="rent",
        commute_mode_default="transit",
        monthly_housing_cost_xgp=Decimal("1050.00"),
        monthly_utilities_cost_xgp=Decimal("135.00"),
        monthly_transport_base_xgp=Decimal("120.00"),
        commute_hours_baseline=Decimal("0.55"),
        commute_hours_per_activity=Decimal("0.22"),
        region_stress_load=Decimal("1.10"),
        job_opportunity_modifier=Decimal("0.09"),
        business_demand_modifier=Decimal("0.14"),
        side_income_modifier=Decimal("0.08"),
        networking_modifier=Decimal("0.12"),
    ),
}


SUPPORTED_REGION_KEYS = frozenset(REGION_CONFIG.keys())
