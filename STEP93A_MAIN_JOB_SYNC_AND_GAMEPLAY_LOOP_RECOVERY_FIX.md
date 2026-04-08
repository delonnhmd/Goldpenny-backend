# STEP 93A Main Job Sync and Gameplay Loop Recovery Fix

## Summary

This step fixes two coupled failures:

1. Split-brain job state where the career UI could show a `CURRENT JOB` while the gameplay/work engine still saw no assigned main job.
2. Gameplay dashboard failure where a basket pricing exception could abort the entire brief/dashboard load.

The fix keeps `player.main_job` as the single authoritative main-job field, repairs legacy drift when recovery is unambiguous, and degrades the economy section without taking down work/core gameplay actions.

## Root Cause

### Current job split-brain

The app had multiple job mirrors that could drift:

- `player.main_job`
- `player_careers.current_job_key`
- `player_employment_states.current_job_code`
- frontend work/job-market labels derived from whichever payload arrived last

That let the career card show `Warehouse Operator` while the gameplay dashboard and `work_shift` flow still derived state from a blank `player.main_job`.

### Gameplay loop collapse

`/gameplay/player/{player_id}/dashboard` indirectly runs shift/day sync, which can trigger next-day progression. `run_player_next_day()` called basket pricing directly, and an exception in basket pricing was able to bubble up into a 500 on the dashboard route. The loop loader treated that dashboard failure as critical, so one broken economy section took down the whole brief/dashboard experience.

## Authoritative Main Job Field

Chosen source of truth:

- `player.main_job`

Rules after this fix:

- Career UI `CURRENT JOB` must match `player.main_job`.
- Dashboard/work status/clock-in/action hub now use the authoritative work-state job derived from `player.main_job`.
- `switch_job` updates `player.main_job` and returns canonical job data to the client.
- When mirrors disagree, the backend exposes sync status and warning metadata instead of silently guessing.

## Self-Healing Sync Behavior

New service:

- `backend/app/services/main_job_sync_service.py`

Behavior:

- If `player.main_job` exists, blank mirrors are filled from it when repair is allowed.
- If `player.main_job` is blank but career state contains exactly one unambiguous current job, backend auto-repairs `player.main_job` from `player_careers.current_job_key`.
- If mirrors conflict, backend does not guess. It returns `job_sync_status=repair_needed` and a user-safe warning message.

Repair points:

- On work-state/dashboard sync via `resolve_expired_shift_if_needed(...)`
- In work-state payload composition so the client can render sync health

Client-visible sync fields added to work-state/job-market payloads:

- `main_job_key`
- `job_sync_status`
- `job_sync_warning_message`
- `job_sync_repair_source`
- `job_sync_auto_repaired`

## Basket Pricing Failure Isolation Strategy

Backend changes:

- `run_player_next_day()` now catches `BasketPricingError`, logs full failure context, and substitutes safe neutral basket placeholders.
- When basket pricing degrades, daily economy brief generation also falls back to a degraded brief instead of pretending economy data is healthy.
- Basket pricing service now logs the exact failing compute path and tolerates enum/string row shape mismatches when reading stored basket rows.
- Economy presentation summary catches daily-brief failures and returns a degraded economy section instead of failing the whole response.

Dashboard behavior after fix:

- Core player state still loads.
- Work status still loads.
- Current job still loads.
- Clock-in/work actions remain available if work systems are healthy.
- Economy section is flagged as degraded instead of crashing the whole loop.

Frontend messaging updates:

- Replaced misleading hard-stop messaging with:
  - `Economy module temporarily unavailable`
  - `Dashboard partially loaded. Work and core actions remain available.`
- Replaced misleading split-state warning with:
  - `Your job data is syncing. Please retry in a moment.`

## Files Changed

- `backend/app/api/gameplay.py`
- `backend/app/engine/career_service.py`
- `backend/app/engine/economy_presentation_service.py`
- `backend/app/services/basket_pricing_service.py`
- `backend/app/services/day_progression_service.py`
- `backend/app/services/job_market_service.py`
- `backend/app/services/main_job_sync_service.py`
- `backend/app/services/shift_state_service.py`
- `backend/tests/test_day_progression_services.py`
- `backend/tests/test_job_selection_flow.py`
- `expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- `expo/src/features/gameplayLoop/components/JobMarketPanel.tsx`
- `expo/src/features/gameplayLoop/context.tsx`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/types/gameplay.ts`

## Before / After

### Before

- Career card could show `Warehouse Operator` as current while gameplay still had no main job.
- `switch_job` did not guarantee all mirrors and follow-up payloads were aligned.
- Basket pricing failures could 500 the gameplay dashboard.
- The brief screen showed a global `Gameplay loop unavailable` failure for a single economy problem.

### After

- `player.main_job` is the canonical main-job field used across gameplay/work flows.
- Unambiguous legacy drift auto-repairs on load/sync.
- `switch_job` returns canonical job data and refreshable work-state context.
- Clock-in/work actions derive from authoritative job state only.
- Basket pricing degradation falls back to neutral placeholders and a degraded economy brief.
- Dashboard and core work actions remain available when economy compute fails.

## Validation Results

Validated scenarios:

- Current job sync repair from career state to `player.main_job`
- Switch-job canonical response and immediate work/action availability
- Clock-in/work shift using the authoritative job after switch/repair
- Basket pricing exception isolation during next-day progression
- Degraded dashboard/economy summary behavior
- Shift-state behavior around missed-shift and work status

Test runs:

- `python -m pytest backend/tests/test_job_selection_flow.py backend/tests/test_day_progression_services.py -q`
- `python -m pytest backend/tests/test_shift_state_service.py -q`
- `python -m pytest backend/tests/test_economy_presentation_service.py backend/tests/test_economy_presentation_api.py -q`
- `python -m pytest backend/tests/test_daily_brief_service.py -q`

Result:

- All targeted backend validation passed.

## Notes

- `switch_job` now tolerates older or partially migrated environments where the per-job progression table is unavailable, keeping the canonical main-job update non-blocking.
- Job label consistency is preserved around the canonical `warehouse_operator` key with the player-facing `Warehouse Operator` label.
