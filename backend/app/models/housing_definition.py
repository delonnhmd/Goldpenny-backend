"""Static housing definition catalog for Gold Penny — Step 8.

Housing definitions are pure Python data, not stored in the database.
They are loaded by the housing engine and exposed through the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HousingDefinition:
    housing_key: str
    display_name: str
    region: str                      # suburban | downtown
    occupancy_type: str              # rent | own
    daily_base_cost: float
    estimated_home_value: Optional[float]  # None for rent options
    stress_modifier: int             # applied every day housing cost is applied
    opportunity_modifier: float      # multiplier for job/business opportunity
    commute_modifier: float          # multiplier for commute-related job costs
    property_tax_rate: float         # annual fraction (e.g. 0.018 = 1.8%)
    maintenance_risk: str            # low | medium | medium_high


# ── MVP Housing Catalog ───────────────────────────────────────────────────────

HOUSING_CATALOG: dict[str, HousingDefinition] = {
    "suburban_rent": HousingDefinition(
        housing_key="suburban_rent",
        display_name="Suburban Rental",
        region="suburban",
        occupancy_type="rent",
        daily_base_cost=18.0,
        estimated_home_value=None,
        stress_modifier=-1,
        opportunity_modifier=0.95,
        commute_modifier=1.05,
        property_tax_rate=0.0,
        maintenance_risk="low",
    ),
    "suburban_own": HousingDefinition(
        housing_key="suburban_own",
        display_name="Suburban Home (Owned)",
        region="suburban",
        occupancy_type="own",
        daily_base_cost=22.0,
        estimated_home_value=180_000.0,
        stress_modifier=-1,
        opportunity_modifier=0.95,
        commute_modifier=1.05,
        property_tax_rate=0.018,
        maintenance_risk="medium",
    ),
    "downtown_rent": HousingDefinition(
        housing_key="downtown_rent",
        display_name="Downtown Rental",
        region="downtown",
        occupancy_type="rent",
        daily_base_cost=28.0,
        estimated_home_value=None,
        stress_modifier=1,
        opportunity_modifier=1.10,
        commute_modifier=0.90,
        property_tax_rate=0.0,
        maintenance_risk="low",
    ),
    "downtown_own": HousingDefinition(
        housing_key="downtown_own",
        display_name="Downtown Home (Owned)",
        region="downtown",
        occupancy_type="own",
        daily_base_cost=34.0,
        estimated_home_value=260_000.0,
        stress_modifier=1,
        opportunity_modifier=1.10,
        commute_modifier=0.90,
        property_tax_rate=0.018,
        maintenance_risk="medium_high",
    ),
}
