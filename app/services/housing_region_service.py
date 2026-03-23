"""Compatibility wrappers for Step 17 housing/region engine."""

from __future__ import annotations

from app.engine.housing_region_service import (
    HousingNotFoundError,
    HousingRegionError,
    HousingValidationError,
    assign_player_housing,
    compute_daily_housing_region_effects,
    compute_housing_effects_for_day,
    get_active_housing_state,
    get_business_region_demand_modifier,
    get_job_region_opportunity_modifier,
    get_or_create_player_housing,
    get_player_housing_history,
    get_player_housing_logs,
    get_player_housing_snapshot,
    get_player_housing_summary,
    get_side_income_region_modifier,
    update_player_region,
)

__all__ = [
    "HousingRegionError",
    "HousingNotFoundError",
    "HousingValidationError",
    "get_or_create_player_housing",
    "update_player_region",
    "compute_daily_housing_region_effects",
    "get_player_housing_snapshot",
    "get_player_housing_history",
    "get_active_housing_state",
    "get_business_region_demand_modifier",
    "get_side_income_region_modifier",
    "get_job_region_opportunity_modifier",
    # Backward-compatible names:
    "assign_player_housing",
    "compute_housing_effects_for_day",
    "get_player_housing_summary",
    "get_player_housing_logs",
]
