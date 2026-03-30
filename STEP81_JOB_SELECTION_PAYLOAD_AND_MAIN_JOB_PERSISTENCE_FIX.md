# Step 81 - Job Selection Payload And Main Job Persistence Fix

## Root cause

Two issues were causing the live `switch_job` -> `clock in` flow to fail:

1. The gameplay UI and action payloads were still carrying legacy job keys like `delivery_driver` and `retail_worker`.
2. The backend main-shift validator only accepted main-job keys that matched the persisted `player.main_job`, while `delivery_driver` was still classified as a side job in the static job catalog.

That created the broken sequence:

- frontend selected a legacy key
- backend either rejected the `switch_job` payload or stored a mismatched value
- `work_shift` then read a missing or invalid `main_job`
- clock-in failed with `422`, including misleading messages like:
  - `switch_job requires new_job_key.`
  - `Main shift requires a main job. Received 'delivery_driver'.`

## Old mismatched job keys found

- `delivery_driver`
- `retail_worker`

These were still present in:

- gameplay job-option payload generation
- frontend starter-job cards
- frontend action payload normalization
- backend career/job validation
- backend job catalog classification
- onboarding starter-job defaults

## Canonical job key format chosen

Gameplay-facing main jobs now use one canonical format everywhere:

- `auto_mechanic`
- `aircraft_mechanic`
- `banker`
- `chef`
- `retail`
- `delivery`

Legacy aliases are only normalized internally on read paths so older saved state does not break live gameplay:

- `retail_worker -> retail`
- `delivery_driver -> delivery`

Legacy aliases are not accepted as valid `switch_job` input anymore.

## switch_job payload contract

Canonical gameplay contract:

```json
{
  "action_key": "switch_job",
  "parameters": {
    "new_job_key": "delivery"
  }
}
```

Frontend no longer relies on `job`, `job_key`, or `target_job` in the normal flow.

## Persistence fix

Backend now persists canonical main-job state before clock-in is allowed:

- `switch_player_job(...)` now validates strict canonical `new_job_key`
- successful switch updates:
  - `player.main_job`
  - `player_career.current_job_key`
- gameplay employment foundation upsert now stores canonical `current_job_code`
- job progress, action hub, dashboard reads, and work-state reads normalize older legacy values to canonical keys
- `work_shift` reads the canonical persisted `main_job` and uses that for clock-in validation

## How clock-in correctness was fixed

- `delivery` is now treated as a main job in the static job catalog
- gameplay `work_shift` payload normalization converts legacy UI values to canonical keys before the request
- backend `start_main_shift(...)` normalizes incoming `job_name` and the persisted `player.main_job`
- main-shift validation compares canonical job keys only

This means a successful `switch_job` to `delivery` can immediately clock in with no hidden follow-up setup.

## Backend error clarity

Bad direct input now returns a precise message:

```text
Invalid job key: delivery_driver. Expected one of: auto_mechanic, aircraft_mechanic, banker, chef, retail, delivery
```

That replaces the previous misleading behavior where invalid naming leaked downstream into work-shift validation.

## Files changed

Backend:

- `backend/app/services/job_key_service.py`
- `backend/app/engine/career_config.py`
- `backend/app/engine/career_service.py`
- `backend/app/models/job_definition.py`
- `backend/app/services/job_progress_service.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/api/gameplay.py`
- `backend/app/services/job_market_service.py`
- `backend/app/services/player_onboarding_service.py`
- `backend/app/engine/work_engine.py`
- `backend/app/api/jobs.py`
- `backend/tests/test_job_selection_flow.py`

Frontend:

- `expo/src/lib/economySafety.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/WorkScreen.tsx`
- `expo/src/lib/api/onboarding.ts`
- `expo/src/lib/worldEconomySignalMapper.ts`

## Validation results

### A. Select job

Validated with backend test:

- `switch_job` using `new_job_key=delivery` succeeds
- `player.main_job` persists as `delivery`
- no `422`

### B. Verify player state

Validated with gameplay actions fetch:

- `GET /gameplay/player/{player_id}/actions` returns `debug_meta.current_job_key = delivery`
- action hub now recommends `work_shift` after successful job selection

### C. Clock in

Validated with backend test:

- `work_shift` using canonical `job_name=delivery` succeeds
- player enters active main-shift state
- persisted `main_shift_job_name = delivery`

### D. Invalid key test

Validated with backend test:

- direct `switch_job` request with `new_job_key=delivery_driver` returns `422`
- response detail is the new explicit invalid-job-key message

## Commands run

Backend:

- `python -m py_compile backend/app/services/job_key_service.py backend/app/engine/career_config.py backend/app/engine/career_service.py backend/app/models/job_definition.py backend/app/services/job_progress_service.py backend/app/services/shift_state_service.py backend/app/api/gameplay.py backend/app/services/job_market_service.py backend/app/services/player_onboarding_service.py backend/app/engine/work_engine.py backend/app/api/jobs.py backend/tests/test_job_selection_flow.py`
- `python -m unittest tests.test_job_selection_flow`
- `python -m unittest tests.test_job_selection_flow tests.test_shift_state_service`

Frontend:

- `yarn eslint src/lib/api/gameplay.ts src/lib/economySafety.ts src/features/gameplayLoop/screens/DashboardScreen.tsx src/features/gameplayLoop/screens/WorkScreen.tsx src/lib/api/onboarding.ts src/lib/worldEconomySignalMapper.ts --max-warnings 0`

## Outcome

Step 81 success criteria are now met:

- player can choose a job successfully
- selected job persists on backend in canonical form
- clock-in works immediately after a valid job switch
- no more missing-`new_job_key` normal-flow payloads from the frontend
- no more `Main shift requires a main job` caused by `delivery_driver` / `retail_worker` naming mismatch
