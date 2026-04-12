# STEP 93G - Rideshare Stress Blocker Refresh Fix

## Goal

Fix the stale rideshare blocker bug where the dashboard stress card reflects a lower, currently valid stress value, but the rideshare panel still shows an older blocker such as `stress too high (100/100)`.

## Root Cause

The rideshare blocker was not using the same live state as the dashboard card.

- The dashboard stress display was derived from the current session state:
  backend base stress minus local passive/active recovery earned in the session.
- The rideshare blocker was still reading backend work-state blocker text that had been generated earlier from stored player stress.
- That created a split source of truth:
  fresh effective stress on the card, stale post-shift blocker text in the rideshare panel.

In practice this meant stress could fall to `61`, while the rideshare blocker kept showing `100/100` until another full backend refresh path happened to replace it.

## Authoritative Source Chosen

Rideshare eligibility now recomputes from current authoritative state on every relevant refresh using:

- current effective stress
- current effective health
- current time remaining
- current shift state
- current rideshare usage/cap
- current location rules

Implementation approach:

- Frontend computes the same effective stress/health values already used for the visible dashboard card.
- Those values are sent to backend dashboard/actions requests as structured overrides.
- Backend rebuilds work state and rideshare state from those current values.
- Frontend renders the blocker from structured blocker metadata plus current effective values, not from a frozen blocker string.

## Threshold

Rideshare is now blocked at:

- `stress >= 80`

## Backend Changes

### Structured rideshare blocker data

`backend/app/services/shift_state_service.py`

Rideshare state now returns structured blocker fields instead of only a pre-rendered message:

```json
{
  "can_rideshare": false,
  "block_reason_code": "stress_high",
  "block_reason_value": 82,
  "stress_threshold": 80,
  "current_stress": 82
}
```

Added fields:

- `block_reason_code`
- `block_reason_value`
- `current_stress`
- `current_health`
- `stress_threshold`
- `health_threshold`
- `effective_current_stress`
- `effective_current_health`

### Fresh recomputation on request

`backend/app/api/gameplay.py`

Dashboard and actions endpoints now accept:

- `current_stress`
- `current_health`

Those values are used to rebuild work state through `resolve_expired_shift_if_needed(...)` on demand.

### Rideshare execution uses current effective stats

`backend/app/api/gameplay.py`
`backend/app/api/side_income.py`
`backend/app/engine/rideshare_engine.py`

Rideshare execution now accepts optional effective stress/health overrides so the eligibility check and action execution use the same current numbers the player sees.

## Frontend Changes

### Refresh triggers added

`expo/src/features/gameplayLoop/context.tsx`

Rideshare freshness is now updated on:

- normal gameplay refresh
- app resume
- dashboard screen focus
- post-action refresh

### Blocker rendering is now dynamic

`expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`

The rideshare card no longer treats the post-shift banner string as durable truth.

Instead it:

- derives current rideshare availability from live effective stress/health and fresh backend work state
- applies deterministic blocker priority from fresh state
- renders current blocker text at render time

Example:

- old: `Shift completed - Rideshare blocked: stress too high (100/100).`
- new: `Unavailable: stress too high (72/100).`
- or, if stress is no longer the blocker: `Not enough time left today for rideshare.`

### Important guard

The dashboard endpoint continues returning canonical base stress/health stats.
The frontend still derives displayed effective stress/health locally for the card.
This avoids double-applying recovery on repeated refreshes while still letting rideshare eligibility use fresh effective overrides.

## Blocker Priority

Current frontend/backend blocker priority is deterministic and fresh-state based:

1. day ended / settled
2. no rideshare action available
3. shift auto-sync / active shift
4. not enough time left
5. daily trip cap reached
6. stress too high
7. health too low
8. invalid location

This prevents the UI from continuing to show a stale stress blocker after stress is no longer the active blocker.

## Before / After

### Before

- Dashboard card could show stress recovered to `61`
- Rideshare panel could still show `stress too high (100/100)`
- Post-shift blocker text could remain effectively frozen

### After

- Rideshare blocker refreshes from current effective stress
- If stress drops below `80`, rideshare unlocks immediately unless another current blocker exists
- If another blocker is now higher priority, the rideshare panel switches to that blocker instead of keeping the old stress message

## Files Changed

- `backend/app/api/gameplay.py`
- `backend/app/api/side_income.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/services/shift_state_service.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/features/gameplayLoop/context.tsx`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/service.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/lib/balanceConfig.ts`
- `expo/src/types/gameplay.ts`

## Validation

Focused validation for this fix:

- `python -m unittest tests.test_shift_state_service.ShiftStateServiceTests.test_post_shift_rideshare_reports_health_and_stress_blockers`
- `python -m unittest tests.test_shift_state_service.ShiftStateServiceTests.test_rideshare_state_recomputes_from_effective_stress_override`
- `yarn typecheck`

Results:

- focused rideshare blocker tests passed
- frontend typecheck passed

Additional note:

- `python -m unittest tests.test_shift_state_service` still has 2 unrelated pre-existing testing-mode expectation failures:
  - `test_testing_mode_shift_one_exposes_overtime_and_post_shift_rideshare`
  - `test_testing_mode_weekend_is_rideshare_only_with_cap_18`

Those failures do not go through the stale-stress blocker path fixed in this step.

## Success Criteria Check

- current stress decrease below threshold now refreshes rideshare eligibility correctly
- blocker text now reflects current stress instead of stale shift-end text
- app resume and dashboard focus now trigger fresh rideshare state refresh
- stale post-shift stress blocker is no longer the permanent source of truth
