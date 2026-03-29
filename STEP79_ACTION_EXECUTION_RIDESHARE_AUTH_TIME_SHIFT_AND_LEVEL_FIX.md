# STEP79_ACTION_EXECUTION_RIDESHARE_AUTH_TIME_SHIFT_AND_LEVEL_FIX

## Summary
Step 79 was implemented in two layers:
1. Backend reliability fixes for action execution and rideshare identity handling.
2. Frontend gameplay visibility completion (job-level progression display, canonical error handling preservation) on top of the existing Step 78 Houston-time/shift/routine dashboard.

## Root Cause: `/gameplay/player/{player_id}/actions/execute` 500
Primary cause was error translation behavior in `app/api/gameplay.py`:
- `action_key == "side_income"` calls `process_rideshare_action(...)`.
- `process_rideshare_action` raises `ValueError` for normal gameplay validation failures (hour caps, availability, etc.).
- The route caught broad `Exception` and routed it through `_raise_gameplay_http_error(...)`.
- `_raise_gameplay_http_error(...)` did not map generic `ValueError` to 422, so these expected gameplay rejects surfaced as generic 500 (`"Unexpected gameplay service error."`).

### Fix
- Added explicit `ValueError -> HTTP 422` mapping in `_raise_gameplay_http_error`.
- Added explicit `except ValueError` handling in `side_income` execute branch.
- Added targeted execution logs with:
  - requested/resolved player id
  - action payload
  - resolved action key
  - day/state snapshot
  - branch-specific exception logs with full traceback (`logger.exception`) for unexpected failures.
- Removed opaque generic masking for unknown exceptions by propagating real exception detail into 500 response detail.

## Root Cause: `/side-income/rideshare` 401 Not authenticated
Primary cause was architecture mismatch:
- Frontend `executeAction` attempted canonical `POST /gameplay/player/{player_id}/actions/execute` first.
- On canonical failure, frontend fell back to legacy `/side-income/rideshare`.
- Legacy `/side-income/rideshare` required `get_current_user` bearer auth, while gameplay loop is player-id based.
- Result: fallback route returned 401 (`Not authenticated`) despite player gameplay context being valid.

### Fix
- Updated `/side-income/rideshare` to support gameplay identity resolution:
  - accepts `player_id` in request body
  - accepts `X-Player-Id` header
  - still supports bearer token path (optional oauth)
- Added identity-source diagnostics logs:
  - source (`player_id` vs token)
  - unauthorized reason context
  - resolved day + player time-state snapshot when successful.
- Frontend fallback now sends `player_id` in rideshare request body.

## Additional Reliability Fix: Canonical error preservation in frontend
`src/lib/api/gameplay.ts` previously fell back for any canonical execute failure.
This could hide real canonical gameplay failures.

### Fix
- Canonical execute now only falls back for route/network unavailability patterns (`404`, `not found`, network failure).
- For canonical 4xx/5xx gameplay errors, frontend now surfaces canonical error directly instead of masking it behind unrelated fallback errors.

## Houston Time / Shift / Rideshare / Recovery / Activity
The Step 78 dashboard structure already provided:
- Houston local time card
- shift window, active-shift state, countdown, auto clock-out handling
- rideshare gating outside active shift with trip/earnings stats
- visible recovery action list
- today activity history stream

Step 79 stability changes ensure those UI systems now receive correct execution outcomes (no false 500/401 chain).

## Job Level Foundation (Max 40) + Salary Growth
Implemented progression foundation in backend and surfaced to dashboard.

### Data model foundation
- Added to `player_employment_states`:
  - `job_level_xp` (int)
  - `job_level_xp_to_next` (int)
- Added startup migration guards in `app/main.py` for both fields.

### Progression behavior
- Level cap: 40 (`JOB_LEVEL_MAX = 40`).
- Work shifts grant XP (`JOB_XP_PER_WORK_HOUR = 25`, bounded minimum).
- XP rollover levels up progressively until cap.
- `skill_level` is synchronized with job-level progression.
- Monthly salary scales with level:
  - `monthly_pay = base_monthly_pay * (1 + 2.5% * (level - 1))`.

### Dashboard payload + UI
- Backend dashboard now returns `job_progress` payload (job key, level, XP, XP-to-next, cap, monthly pay, employer metadata, shift type).
- Frontend types and normalizer updated to consume `job_progress`.
- Dashboard Work card now visibly shows:
  - `Job level` (`Lv X/40`)
  - XP progress to next level
  - pay scale (monthly + approximate hourly view)

## Files Changed
Backend:
- `app/api/gameplay.py`
- `app/api/side_income.py`
- `app/models/player_employment_state.py`
- `app/main.py`

Frontend (`PFT/pft-expo`):
- `src/lib/api/gameplay.ts`
- `src/types/gameplay.ts`
- `src/features/gameplayLoop/screens/DashboardScreen.tsx`

## Validation Results
### Executed validations
- Python compile check passed:
  - `python -m py_compile app/api/gameplay.py app/api/side_income.py app/models/player_employment_state.py app/main.py`
- TypeScript project check run:
  - `npx tsc --noEmit`
  - Result: failed due pre-existing unrelated type issues in `WorkScreen.tsx` and `GameDashboardPage.tsx` (not introduced by this Step 79 patch set).

### Scenario mapping against requested checks
A. Gameplay action execution 500
- Fixed in code-path by explicit `ValueError -> 422`, richer logs, and non-masked error details.

B. Rideshare 401
- Fixed in code-path by gameplay identity support (`player_id`/`X-Player-Id`) and canonical-error preservation in frontend.

C. Clock-in flow visibility
- Existing Step 78 flow retained and now benefits from corrected execute/rideshare behavior.

D. Recovery visibility
- Existing Step 78 visible recovery list retained.

E. Activity history
- Existing Step 78 activity stream retained.

F. Job level foundation
- Added max-level 40, XP progression, dashboard visibility, and salary scaling hook.

## Notes
- This patch set prioritized broken execution/auth behavior first, then completed visible progression wiring.
- Runtime end-to-end API walkthrough should now be performed in the live playtest environment to confirm all scenario flows with real player state and timers.
