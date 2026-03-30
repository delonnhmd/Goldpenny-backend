# Step 80 - Shift State Machine And Backend Auto-Resolve Fix

## Root Cause Of The Stuck Auto Clock-Out

- The dashboard owned the main shift lifecycle locally with `activeShift` and a frontend timer.
- The frontend treated timer expiry as shift completion and called the work action at zero, but the backend did not own a persistent main-shift state machine with `shift_started_at`, `shift_ends_at`, `shift_status`, and an idempotent finalize path.
- Result: the UI could show `Auto clocking out...` while the backend still considered the player to be on shift or otherwise in an inconsistent work state.
- Because rideshare, action execution, and time-limit rules still depended on backend state, later actions could fail with stale-state errors and 422s.

## Root Cause Of The Side-Income Time Bleed

- Main-shift completion and side-income execution were not separated cleanly enough in daily accounting.
- Main-shift lifecycle data was not persisted independently, so the system could not reliably distinguish:
  - main-shift hours already reserved/completed
  - side-income hours already consumed
  - total daily time used
- Rideshare execution now reads and updates only side-income counters, while main-shift completion updates only main-shift counters.

## What Changed

### Backend Source Of Truth

- Added persisted main-shift fields to `players`:
  - `main_shift_active_flag`
  - `main_shift_status`
  - `main_shift_started_at`
  - `main_shift_ends_at`
  - `main_shift_completed_at`
  - `main_shift_job_name`
  - `main_shift_shift_type`
  - `main_shift_hours`
  - `main_shift_number`
  - last completed shift reward deltas for UI feedback
- Added `main_shift_hours_today` to `player_daily_states`.
- Normalized daily aliases for:
  - `side_income_hours_today`
  - `recovery_hours_today`
  - `total_time_used_today`

### Expired Shift Auto-Resolve

- Added `backend/app/services/shift_state_service.py`.
- Core service functions:
  - `start_main_shift(...)`
  - `finalize_active_main_shift(...)`
  - `resolve_expired_shift_if_needed(...)`
  - `build_work_state_payload(...)`
- Shift expiration is now evaluated against Houston time only.
- If `now_houston >= shift_ends_at` for an active main shift, the backend finalizes immediately.
- Finalization is idempotent:
  - no second pay
  - no second XP grant
  - no duplicate job action / contribution / transaction log rows

### Fetch-Time Finalization

- The following gameplay fetch paths now resolve expired shifts before returning data:
  - `/gameplay/player/{player_id}/dashboard`
  - `/gameplay/player/{player_id}/actions`
  - `/gameplay/player/{player_id}/action-hub`
  - `/gameplay/player/{player_id}/work-state`
  - `/gameplay/player/{player_id}/end-of-day-summary`
  - `/gameplay/player/{player_id}/transactions`
  - `/gameplay/player/{player_id}/actions/preview`
  - `/gameplay/player/{player_id}/actions/execute`
  - `/gameplay/player/{player_id}/end-day`
- Side-income execution also resolves shift state first:
  - `/side-income/rideshare`

### Explicit Finalize Endpoint

- Added:
  - `GET /gameplay/player/{player_id}/work-state`
  - `POST /gameplay/player/{player_id}/work-state/finalize`
- The finalize endpoint is safe to call repeatedly.
- If the shift is already completed, it returns the current work state without duplicating settlement.

### Main Shift vs Side-Income Accounting

- Main-shift start now reserves and records main-shift time separately.
- Main-shift finalize awards cash, XP, stress, health, fatigue, and audit records once.
- Rideshare now:
  - resolves main-shift state first
  - rejects while backend still says the main shift is active
  - increments `side_job_hours_today`
  - increments `side_income_hours`
  - increments `total_hours_used`
  - does not mutate `main_shift_hours_today`

### Rideshare Unlock Gating

- Rideshare is no longer unlocked from the local countdown.
- `rideshare_unlocked` and `rideshare_available` are computed from backend `work_state`.
- Rideshare becomes available only after:
  - the main shift is backend-confirmed completed
  - the day is not already settled
  - side-income cap remains
  - enough time remains

### Frontend Dashboard Behavior

- Removed local `activeShift` as the source of truth.
- The dashboard timer now reads backend `work_state.shift_ends_at`.
- When the timer reaches zero, the frontend:
  - logs the event
  - calls `POST /work-state/finalize`
  - refreshes gameplay state
  - waits for backend confirmation before showing completion and rideshare unlock
- UI states now distinguish:
  - on shift
  - auto-finalizing
  - shift completed

## Files Changed

- `backend/app/api/gameplay.py`
- `backend/app/api/side_income.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/main.py`
- `backend/app/models/player.py`
- `backend/app/models/player_daily_state.py`
- `backend/app/services/job_progress_service.py`
- `backend/app/services/shift_state_service.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/types/gameplay.ts`

## Validation Results

### Automated Validation Run

- Passed: `python -m unittest tests.test_shift_state_service`
- Passed: `python -m py_compile app/api/gameplay.py app/api/side_income.py app/engine/rideshare_engine.py app/services/shift_state_service.py app/services/job_progress_service.py`
- Passed: `yarn eslint src/lib/api/gameplay.ts src/types/gameplay.ts src/features/gameplayLoop/screens/DashboardScreen.tsx --max-warnings 0`

### Scenario Coverage

- A. Normal shift completion
  - Covered by `test_actions_fetch_auto_resolves_expired_main_shift`
  - Confirmed: expired main shift auto-finalizes on fetch and rideshare becomes available
- B. Frontend timer misses completion
  - Covered by fetch-time auto-resolve design and same auto-resolve test path
  - Backend no longer depends on the frontend timer callback
- C. No double completion
  - Covered by `test_expired_shift_finalize_is_idempotent`
  - Confirmed: no duplicate pay, XP, contribution rows, or transaction logs
- D. Side-income accounting
  - Covered by `test_main_shift_hours_do_not_consume_side_income_cap`
  - Confirmed: completed main-shift hours do not consume rideshare cap
- E. Live state clarity
  - Implemented in dashboard work-state driven UI
  - Confirmed by frontend lint pass and backend work-state payload wiring

## Notes

- `yarn typecheck` still reports unrelated pre-existing errors in:
  - `expo/src/features/gameplayLoop/screens/WorkScreen.tsx`
  - `expo/src/pages/gameplay/GameDashboardPage.tsx`
- Those errors were not introduced by this Step 80 change set.
