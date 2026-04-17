Original prompt: Step 96K — Map-Based Services Expansion

Goal
- Expand the city map's set of selectable node types so downstream systems (economy, jobs, housing, finance, health, certifications, stocks, vehicles) all surface through the same map-first UI rather than detached pages.

New node types introduced (data-only in this step; behavior lands in later steps)
- car_sale          — vehicle dealership (future: purchase, upgrade, depreciation)
- bank              — cash deposit / loan origination anchor
- housing           — housing market entry point (future: rent/buy flows)
- stock_center      — stock market kiosk (future: brokerage lane)
- certification_school — training / licensing hub
- clinic            — health and recovery services (future: treatment purchase)
- gas_station       — vehicle fuel, small quick-spend anchor

Backend scope
- `app/services/city_map_service.py`
  - Add a `CityLocation` entry per new node.
  - Add `RIDESHARE_BASE_PROFILES` entries marked `allowed=False` with a consistent `reason_if_blocked`, so rideshare lane rules don't explode.
  - Rely on the existing cross-region fallback in `get_travel_rule` instead of enumerating every pair — keeps `TRAVEL_RULES` readable.
- No DB migration required — nodes are data definitions in code.

Frontend scope
- `expo/src/components/gameMap/mapData.ts`
  - Add `labelForNodeType` branches mapping each node type to `shortLabel`, `description`, `kind = service_building`, and empty `actionTags` (actions are wired later).
  - Add anchors in `FIXED_NODE_ANCHORS` for each new node so they render in a stable location.
- `MapDashboardScreen` `FALLBACK_NODES` — include new nodes so dev/mock mode still renders the full set when backend is unavailable.

Notes
- This step intentionally introduces **no behavior** — the goal is to show the nodes on the map with sensible placements. Actions (withdraw cash, enroll in certification, buy car) land in later steps alongside 96M's economic wiring.
- Icons / sprites are out of scope; short-labels are used as placeholders.
