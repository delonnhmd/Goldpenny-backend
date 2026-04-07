# STEP 91A - Emergency Stabilization Patch

## Scope
This patch only stabilizes blocking failures. No new feature scope was added.

Blocked issues addressed:
1. Animation crash from mixed native/JS animation driver usage
2. Missing/`None` main job causing misleading work behavior
3. `switch_job` payload missing required `new_job_key`
4. Duplicate `player_daily_state` creation races

Also included:
- Critical fallback policy hardening (no fake critical data)
- Human-readable user error messages for job/switch failures

## 1) Animation crash root cause + fix

### Root cause
`expo/src/components/motion/HighlightOnChangeView.tsx` animated the same `Animated.View` with:
- `scale` using `useNativeDriver: true`
- `backgroundColor` flash using `useNativeDriver: false`

This mixed native + JS driver usage on one animated node and triggered:
- "Attempting to run JS driven animation on animated node that has been moved to 'native'..."

### Fix
In `HighlightOnChangeView.tsx`, standardized this component to JS-driven animation:
- changed `scale` animation to `useNativeDriver: false`
- kept highlight behavior intact, no native/JS driver mixing on this node

## 2) Main job `None` stabilization

### Root cause
Two behaviors combined:
- Work payloads could still carry a stale job key while the player had no assigned main job
- Validation paths produced technical mismatch errors instead of explicit "no job assigned" guidance

### Fixes
- Added strict no-main-job guard before main shift start:
  - `backend/app/services/shift_state_service.py`
  - `backend/app/engine/work_engine.py`
- New player-facing validation message:
  - `"No main job is assigned yet. Choose a job before starting a shift."`
- Work screen now resolves current job from authoritative work-state fields first (not only debug fallback):
  - `expo/src/features/gameplayLoop/screens/WorkScreen.tsx`

## 3) `switch_job` payload correction (`new_job_key`)

### Root cause
`switch_job` action rows for players with an existing job exposed `job_options/current_job_key` but did not include `new_job_key`, which caused backend 422 on direct execution.

### Fixes
- Backend action-hub payload now includes a deterministic default destination for switch action:
  - `backend/app/api/gameplay.py`
  - added `default_switch_job_key` and includes it in `switch_job.parameters.new_job_key`
- Frontend execute guard now requires/normalizes `new_job_key` before dispatch:
  - `expo/src/lib/api/gameplay.ts`
- Backend 422 detail text updated to human-readable wording:
  - `"Could not switch jobs because no destination job was selected."`

## 4) Duplicate daily-state creation (idempotent + race-safe)

### Root cause
Multiple paths used query-then-insert patterns without race handling, allowing duplicate insert attempts under concurrent requests.

### Core fix
Added shared race-safe helper:
- `backend/app/services/player_daily_state_service.py`
- `ensure_player_daily_state(...)`
  - query existing by `(player_id, day_number)`
  - if missing, insert inside nested transaction/savepoint
  - on `IntegrityError` race, re-query and return existing row

### Paths migrated to shared helper
- `backend/app/services/shift_state_service.py`
- `backend/app/services/daily_settlement_service.py`
- `backend/app/services/dinner_survival_service.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/engine/housing_region_service.py`
- `backend/app/engine/financial_distress_service.py`
- `backend/app/engine/life_balance_service.py`
- `backend/app/engine/daily_engine.py`
- `backend/app/engine/work_engine.py`
- `backend/app/services/player_onboarding_service.py` (day-1 creation path)

Result: daily-state creation is now centralized and idempotent across hotspots.

## 5) Critical fallback policy changes

### Problem
Gameplay loop could silently fall back to mock data on critical sections, producing "Mixed Data Mode" while core state was unhealthy.

### Fix
In `expo/src/features/gameplayLoop/service.ts`:
- `resolveSection(...)` now supports `allowMockFallback`
- `dashboard` and `action_hub` are marked critical with `allowMockFallback: false`
- critical load errors now throw instead of returning mock

In `expo/src/features/gameplayLoop/context.tsx`:
- on critical bundle load failure, clear bundle and show explicit error state
- do not keep stale actionable data in place

## 6) User-facing error text cleanup

In `expo/src/features/gameplayLoop/context.tsx`:
- normalized and humanized errors shown in feedback banners
- strips noisy route prefixes (`/gameplay/player/...:`)
- maps technical job/switch errors to readable text:
  - `"No main job is assigned yet. Choose a job before starting a shift."`
  - `"Could not switch jobs because no destination job was selected."`

## Before/After text examples

### Before
- `/gameplay/player/{id}/actions/execute: Your assigned main job is 'None', not 'delivery'.`
- `/gameplay/player/{id}/actions/execute: switch_job requires new_job_key.`

### After
- `No main job is assigned yet. Choose a job before starting a shift.`
- `Could not switch jobs because no destination job was selected.`

## Files changed

Backend:
- `backend/app/api/gameplay.py`
- `backend/app/engine/daily_engine.py`
- `backend/app/engine/financial_distress_service.py`
- `backend/app/engine/housing_region_service.py`
- `backend/app/engine/life_balance_service.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/engine/work_engine.py`
- `backend/app/services/daily_settlement_service.py`
- `backend/app/services/dinner_survival_service.py`
- `backend/app/services/player_onboarding_service.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/services/player_daily_state_service.py` (new)

Frontend:
- `expo/src/components/motion/HighlightOnChangeView.tsx`
- `expo/src/features/gameplayLoop/context.tsx`
- `expo/src/features/gameplayLoop/screens/WorkScreen.tsx`
- `expo/src/features/gameplayLoop/service.ts`
- `expo/src/lib/api/gameplay.ts`

## Validation run

### Backend compile
- `python -m compileall app` (pass)

### Backend targeted tests
- `python -m pytest tests/test_shift_state_service.py tests/test_job_selection_flow.py -q`
- Result: `13 passed`

### Frontend typecheck
- `npm run typecheck` (expo)
- Result: pass (`tsc --noEmit`)

## Stabilization verdict
Emergency stabilization objectives for Step 91A are implemented:
- animation crash path fixed
- main job no longer silently inferred when missing
- switch action enforces canonical `new_job_key`
- daily-state creation is idempotent/race-safe across core paths
- critical backend failures now surface explicit recovery UI instead of fake critical mock state
