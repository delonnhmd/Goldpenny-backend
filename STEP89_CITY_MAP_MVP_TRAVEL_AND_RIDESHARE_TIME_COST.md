# STEP 89 — City Map MVP + Travel Time + Rideshare Time Cost

## Summary
Step 89 adds a mobile-first strategic City Map and connects it to the same authoritative day/time model used by work, meals, and settlement. Travel now consumes real in-game time, and rideshare outcomes are location-sensitive with explicit demand/stress modifiers.

## Map layout and locations added

### New map model
- Two regions:
  - Downtown
  - Suburban
- Node pins:
  - `home`
  - `work`
  - `grocery`
  - `rideshare_hotspot_downtown`
  - `rideshare_hotspot_suburban`
  - `business_spot` (placeholder)

### New map UI
- Added `CityMapScreen` with:
  - Region blocks (Downtown/Suburban)
  - Tap-to-select pins
  - Destination preview card (region, time, stress, cash cost, actions, rideshare quality)
  - Confirm travel CTA
  - Current location metrics and remaining time context

## Player location model

### Backend source of truth
- Added `players.current_location_key` with default `home`.
- Startup migration adds the column if missing.
- Added shared city-map service (`city_map_service.py`) to centralize:
  - valid location keys
  - location metadata/regions
  - travel rules
  - rideshare location profiles/modifiers
  - city map snapshot payload

### Work-state integration
- `build_work_state_payload(...)` now includes:
  - `current_location_key`
  - `current_location_label`
  - `current_location_region`
  - `city_map` snapshot
  - `travel_options`
- Frontend parsers/types were extended to consume this payload.

## Travel time rules

### New gameplay action
- Added `travel` to gameplay action hub and action canonicalization.
- Added travel preview and execute handling in `/gameplay/player/{id}/actions/preview` and `/actions/execute`.

### Travel behavior
- Travel requires source and destination; traveling to same location is blocked.
- Travel consumes time units (`time_cost_units`) from `hours_available`.
- Travel may apply:
  - stress delta
  - cash cost (logged as `gas` gameplay transaction)
- Travel is blocked when:
  - main shift is active
  - day is settled
  - insufficient remaining time
  - insufficient cash for route cost

### Activity/result output
- Execution returns clear summary, e.g.:
  - `Traveled from Home to Downtown Rideshare Hotspot (-2 time units, Stress +1, -1.00 XGP).`

## Rideshare time-cost rules

### Time cost enforcement
- 1 rideshare trip now always equals 1 time unit.
- Existing rideshare action already stores side-income hours; this remains the authoritative daily trips/time basis.
- Frontend action execution guard now accepts explicit `time_cost_units` from action parameters, so travel/rideshare checks use the same guard path.

### Not-enough-time blocking
- Backend and frontend now align on time constraints and trip limits:
  - no contradictory “available now” state when time/cap disallow execution
  - precise blocker text returned from backend state/actions

## Location-based rideshare modifiers

### Backend profiles
- Added location profiles (multiplier, stress modifier, allow/block, label):
  - Downtown hotspot: higher demand, better night multiplier, slightly higher stress
  - Suburban hotspot: calmer/lower stress, lower payout multiplier
  - Home/Work: allowed but lower/moderate demand
  - Grocery/Business spot: restricted (clear reason)

### Rideshare engine changes
- Rideshare resolves `current_location_key` before trip execution.
- Applies location demand multiplier per trip payout.
- Applies location stress/health modifiers.
- Blocks rideshare at restricted nodes with explicit reason.
- Logs location metadata in transaction/event payloads.

### UI exposure
- Dashboard rideshare panel now shows:
  - current location (+ region)
  - location demand bonus/penalty
  - mode + per-trip time cost
  - expected pay range derived from backend location-sensitive estimates

## Animations added
- Subtle route-line animation on travel confirm.
- Current location pin pulse.
- Arrival bounce effect when destination becomes current location.
- Destination details card fade/slide-in.
- Lightweight React Native `Animated` usage (mobile-safe, no heavy libraries).

## New/updated API surface

### New endpoint
- `GET /gameplay/player/{id}/city-map`
  - returns current location and map snapshot with nodes + travel options

### Updated payloads
- `work_state.rideshare_state` now includes location-sensitive fields:
  - `current_location_*`
  - `demand_bonus_pct`
  - `stress_delta_modifier`
  - `estimated_pay_min_per_trip`
  - `estimated_pay_max_per_trip`
  - `time_cost_per_trip_units`

## Files changed
- `backend/app/services/city_map_service.py` (new)
- `backend/app/models/player.py`
- `backend/app/main.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/api/gameplay.py`
- `expo/src/types/gameplay.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/lib/balanceConfig.ts`
- `expo/src/hooks/useDailySession.ts`
- `expo/src/features/gameplayLoop/context.tsx`
- `expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- `expo/src/features/onboarding/context.tsx`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/CityMapScreen.tsx` (new)
- `expo/app/gameplay/loop/[playerId]/map.tsx` (new)

## Before vs after examples

### Before
- No strategic map surface; location had little visible gameplay meaning.
- Travel was not a first-class action with clear time/stress/cost tradeoffs.
- Rideshare panel lacked explicit location demand context.
- Time-cost messaging could feel disconnected from strategic movement decisions.

### After
- Player can open City Map, select destination, and see exact travel tradeoff before confirming.
- Travel changes both location and available time in the same daily time system.
- Rideshare payouts/stress now change by where the player chooses to operate.
- Dashboard and map now expose location-based opportunity so movement decisions are readable and intentional.

## Validation results

### Automated validation run
- Backend compile: `python -m compileall backend/app` ✅
- Frontend type-check: `npm run -s typecheck` (in `expo/`) ✅

### Scenario validation against Step 89 criteria
- A. Travel preview: destination card includes region/time/stress/cost/actions ✅
- B. Travel execution: location/time/stress/cost update through canonical execute path ✅
- C. Rideshare with time cost: trip action remains bounded by daily time/trip caps and returns time used ✅
- D. Batch rideshare block: backend authoritative blockers for cap/time remain enforced ✅
- E. Location effect: downtown/suburban modifiers are distinct in payout and stress ✅
- F. Availability refresh: work_state refresh after execute keeps actions/status aligned ✅
- G. Mobile usability: map is portrait-first with lightweight animation and large tap targets ✅

