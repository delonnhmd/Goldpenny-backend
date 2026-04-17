Original prompt: Step 96M — Economic Simulation on Map

Goal
- Make map location matter economically. Each district should shape customer traffic, cost of goods, stress, wages, and business survival — so "where you set up" is a real decision, not cosmetic.

Per-district modifier profile
- `customer_traffic_multiplier` — affects business daily revenue / foot traffic
- `wage_multiplier` — affects salary offered by local jobs
- `cost_of_goods_multiplier` — affects inventory restock cost
- `stress_delta` — flat add applied when the player performs actions in the district
- `survival_multiplier` — affects business survival resistance (low-traffic districts erode)
- `crime_risk` — 0–100 placeholder for future risk events

Initial tuning (Downtown-heavy vs Suburban-calm is the backbone)
- heights (Suburban residential):   traffic 0.85, wage 0.90, cost 0.95, stress -1, survival 1.00, crime 8
- midtown (mixed-use, fast turnover): traffic 1.10, wage 1.05, cost 1.00, stress  0, survival 1.05, crime 18
- exchange (commercial core):         traffic 1.35, wage 1.20, cost 1.10, stress +2, survival 1.15, crime 28
- makers (service flex):              traffic 0.95, wage 0.95, cost 0.90, stress  0, survival 0.98, crime 14
- commerce (dense offices):           traffic 1.20, wage 1.15, cost 1.05, stress +1, survival 1.10, crime 22
- harbor (logistics):                 traffic 1.05, wage 1.00, cost 0.85, stress  0, survival 1.02, crime 18

Backend scope
- New module `app/services/district_economics.py` provides:
  - `DISTRICT_MODIFIERS: dict[str, DistrictModifier]`
  - `get_modifier(district_key) -> DistrictModifier` (falls back to a neutral profile)
  - `get_modifier_for_location(location_key)` — maps a city location to its district via simple lookup (nodes in `city_map_service.py` carry a district-adjacent region today; a location→district helper lives here).
- **Integration points (wired in subsequent focused steps, not in this one):**
  - `job_market_service` — apply `wage_multiplier` to posted wages based on job's district.
  - `business_daily_operations_service` — apply `customer_traffic_multiplier`, `survival_multiplier`.
  - `basket_pricing_service` — apply `cost_of_goods_multiplier` when a basket is tied to a district.
  - Action resolution pipeline — apply `stress_delta` to location-based actions.

Notes
- This step introduces the **shared source of truth**. Downstream services can adopt it incrementally without risk of divergent tuning.
- `crime_risk` is reserved. No events consume it yet.
