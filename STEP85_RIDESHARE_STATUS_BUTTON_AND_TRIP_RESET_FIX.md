# STEP 85 — Rideshare Status/Button Alignment + Daily Trip Reset

## Summary
Step 85 is implemented. Rideshare availability now comes from one backend truth object and the Dashboard uses that same object for:
- status label text
- button enabled/disabled state
- per-bundle validation (Run 1 / Run 3 / Run 5)
- trips/cap counters

This removes the contradictory state where UI said "available now" while actions were blocked.

## Root Cause of Contradictory State
The mismatch came from split logic paths in the Dashboard:
- status messaging used one set of conditions (`rideshare_unlocked`/local fallback text)
- button disabled state used a different guard path (action execution guards/cap/time checks)
- trips/cap display could fall back to values that did not match button gating in all cases

Result: panel could display "Ride Share is available now" while buttons remained disabled.

## Backend Source of Truth
Added backend rideshare state generation in `shift_state_service` and returned it via work state:

```json
{
  "can_rideshare": true,
  "status": "available",
  "reason": "Ride Share is available now.",
  "trips_today": 2,
  "max_trips": 6,
  "remaining_trips": 4,
  "hours_remaining_today": 6,
  "mode": "night"
}
```

Status values now include:
- `available`
- `shift_active`
- `limit_reached`
- `not_enough_time`

`rideshare_available` is now derived directly from `rideshare_state.can_rideshare`.

## Trip Reset Fix (New Day)
Daily counters now reset reliably through backend day-sync/reset flow:
- `trips_today` resolves from current day `PlayerDailyState.side_income_hours`
- advancing to a new game day reads a new day context, so rideshare usage resets to 0
- work counters are reset when day changes (`_maybe_reset_daily_counters`)

Validated by test: rideshare reaches 6/6 on day N, then reads 0/6 on day N+1.

## Frontend Alignment
Dashboard now uses `work_state.rideshare_state` as the single source for rideshare rendering and execution guards.

Implemented behavior:
- status label uses backend `reason`
- buttons disabled via one shared helper (`getRideShareDisabledReason`)
- execution path uses the same helper before dispatch (no divergent button/runtime logic)
- bundle rules enforced:
  - requires `can_rideshare == true`
  - requested trips must fit remaining capacity
  - requested trips must fit remaining time

## Logging Added
Backend logs now include rideshare diagnostics:
- `player_id`
- `shift_active`
- `trips_today`
- `max_trips`
- `can_rideshare`
- `rideshare_status`
- `reason`
- `daily_reset_applied` (yes/no at work-state resolution)

Frontend diagnostics now log:
- rideshare payload received
- status label shown
- button disabled reason for Run 1 / Run 3 / Run 5

## Files Changed
- `backend/app/services/shift_state_service.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/api/gameplay.py`
- `expo/src/types/gameplay.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `backend/tests/test_shift_state_service.py`

## Validation Results
Automated validation executed:
- `pytest backend/tests/test_shift_state_service.py -q` → **9 passed**
- `pytest backend/tests/test_day_progression_services.py -q` → **7 passed**
- `pytest backend/tests/test_life_day_progression.py -q` → **4 passed**
- `yarn typecheck` (expo) → **passed**

Behavioral outcomes now match Step 85 goals:
- 6/6 trips => status shows limit reached and buttons disabled
- new day => trips reset to 0/6
- truly available => status says available and buttons enabled
- frontend and backend rideshare logic are aligned
