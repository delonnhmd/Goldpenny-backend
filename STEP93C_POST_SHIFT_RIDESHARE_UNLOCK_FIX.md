# STEP93C Post-Shift Rideshare Unlock Fix

## Root Cause

The post-shift rideshare block was not primarily a rideshare engine bug.

The real issue was that backend work-state resolution still tied rideshare unlock to the scheduled shift window ending (`scheduled_shift_end_label` / `reached_shift_end`) even after the active main shift had already been finalized as completed.

That left the player in a contradictory state:

- `main_shift_status = completed`
- `main_shift_active_flag = false`
- shift pay and XP posted
- but rideshare still locked until the old scheduled window ended

The frontend then rendered that stale blocker because the work-state payload did not expose a clear post-shift phase or a dedicated rideshare block reason.

## Fields And Flags Audited

Authoritative backend fields used in the fix:

- `main_shift_active_flag`
- `main_shift_status`
- `main_shift_started_at`
- `main_shift_ends_at`
- `main_shift_completed_at`
- `main_shift_hours_today`
- `last_worked_day`
- `hours_available`
- `side_income_hours_today`
- current location from city-map state

Frontend/backend payload aliases added so the post-shift transition is explicit:

- `is_on_shift`
- `work_status`
- `current_action_state`
- `shift_ended_at`
- `can_rideshare`
- `rideshare_block_reason`
- `trips_today`
- `trips_remaining`
- `remaining_time_units`
- `action_state_refreshed_at`

Note:

- there was no dedicated persisted `active_shift_id` in the existing system, so a deterministic active-shift payload id is exposed only while a shift is active and clears immediately after completion

## Shift Completion State Transition Fix

Backend work-state now treats a completed main shift on the current day as an immediate post-shift/off-shift state.

Changed behavior:

- completed shifts now set the player into `work_status = off_shift_after_work`
- `is_on_shift` is derived from the authoritative backend active-shift flag
- `current_action_state` mirrors the off-shift post-work state
- `shift_ended_at` is populated from the authoritative completed timestamp

Most importantly:

- rideshare unlock now keys off `completed_shift_today` as well as weekend / no-shift / scheduled end cases
- it no longer waits for the old scheduled shift window after the main shift has already been completed

## Rideshare Blocker Visibility Fix

Rideshare state now returns exact backend blocker text instead of forcing the UI to infer it.

Added/returned:

- `rideshare_state.block_reason`
- top-level `rideshare_block_reason`
- top-level `can_rideshare`

Exact blocker categories now surfaced:

- shift still active
- not enough time left today
- daily trip limit reached
- location restricted
- health too low
- stress too high

## Action Hub And Refresh Fix

The work-state/action-hub payload now returns refreshed post-shift action data immediately after shift finalization.

Returned values include:

- `can_rideshare`
- `rideshare_block_reason`
- `trips_today`
- `trips_remaining`
- `remaining_time_units`
- current location key/label/region

Frontend dashboard changes:

- shift completion banner now explicitly says the player is off shift
- post-shift rideshare banner shows either:
  - `Shift completed · You are now off shift. Ride share available now.`
  - or `Shift completed · Rideshare blocked: ...`
- rideshare disable messaging now uses backend blocker truth first
- finalize feedback after timer expiry now reports the real post-shift rideshare state

## Files Changed

- `backend/app/services/shift_state_service.py`
- `backend/app/api/gameplay.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/types/gameplay.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`

## Before / After

Before:

- a shift could already be finalized and paid out
- backend still kept rideshare locked until the scheduled shift window ended
- UI had no explicit post-shift state
- rideshare blockers were vague or reused stale shift-window messaging

After:

- completed shift immediately becomes `off_shift_after_work`
- `is_on_shift` flips false as soon as finalization succeeds
- action/work/rideshare payloads expose fresh post-shift state immediately
- rideshare unlocks immediately when time/cap/location/health/stress allow
- if blocked, the UI shows the exact blocker

## Validation Results

Automated validation run:

- `python -m pytest backend/tests/test_shift_state_service.py -q`
  - result: `15 passed`
- `python -m py_compile backend/app/services/shift_state_service.py backend/app/api/gameplay.py`
  - result: passed
- `yarn typecheck` in `expo/`
  - result: passed

Scenario coverage:

- A. Normal after-work rideshare
  - validated by new regression: completed shift before scheduled window end now unlocks rideshare immediately
- B. Shift complete but no time left
  - validated by new regression: exact blocker is `Not enough time left today for rideshare.`
- C. Shift auto-close
  - existing auto-resolve route test still passes
- D. Daily trip cap reached
  - existing rideshare cap regression still passes
- E. Health/stress blocker
  - validated by new regressions for both high stress and low health post-shift blockers
- F. No stale work state
  - validated by explicit assertions on `is_on_shift = false`, `work_status = off_shift_after_work`, and refreshed rideshare payload fields

## Summary

This step fixes the real bug: shift state release after completion.

The player now leaves `on_shift` immediately when the backend finalizes the shift, the action hub recalculates from fresh state, and rideshare unlocks right away unless a real blocker remains.
