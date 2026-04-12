# STEP 94 - State Truth Lock, Action Recompute Engine, and Idempotency Stabilization

## Goal

Stabilize the gameplay loop around one backend-computed current state, remove stale blocker drift between dashboard/action panels, and make critical action retries safe.

## Root Problems Confirmed

- Dashboard and action hub were still fetched as two separate backend calls, so they could render from different state snapshots.
- The frontend still had local action-cap blocking in `useDailySession`, which could disagree with backend availability.
- Action success responses did not consistently return a canonical refreshed state, so the client had to wait for a follow-up refresh and could briefly show stale disabled states.
- The backend already had structured blocker work in some areas, especially rideshare and recovery, but there was no single contract the entire gameplay UI could trust.

## Authoritative Gameplay State Contract

Added a canonical backend-computed contract under `authoritative_state` with:

- `player_id`
- `day_number`
- `houston_time`
- `houston_date`
- `houston_timezone`
- `day_phase`
- `current_job_key`
- `current_job_label`
- `refreshed_at`
- `shift_state`
- `player_state`
- `rideshare_state`
- `debt_payment_state`
- `recovery_state`
- `work_state`
- `degraded_sections`

This contract now ships from:

- dashboard payload
- action hub payload
- new combined gameplay loop payload
- successful gameplay action responses as `updated_state`

## Action Recompute Engine

### Backend

The backend now exposes one combined route:

- `GET /gameplay/player/{player_id}/loop`

This route computes `work_state` once, then returns:

- `dashboard`
- `action_hub`
- `authoritative_state`
- `debug_meta`

That removes the old dashboard/action-hub snapshot split for the core gameplay UI.

### Frontend

The gameplay loop service now loads its core state from the combined loop endpoint instead of separate dashboard and action-hub calls.

After every successful gameplay action:

- the action result is applied immediately to the in-memory bundle through `updated_state`
- then a silent refresh runs

This means buttons and blockers rerender from fresh truth immediately instead of waiting for a second pass.

## Blocker Data Model

Structured blocker data is now the durable truth path for the core loop.

Examples:

- rideshare uses `block_reason_code`, `block_reason_value`, thresholds, trip/time caps
- debt payment uses `block_reason_code` and `max_payable_now`
- recovery actions expose structured remaining/used/cap data plus `block_reason_code`

Frontend rendering now favors structured blocker state over frozen display strings.

## Idempotency Fixes and Coverage

Confirmed and preserved:

- debt payment request replay idempotency via request IDs and transaction-log replay lookup
- shift salary posting replay protection via salary audit token/upsert flow

Stabilized the client around those paths by making action responses always return `updated_state`, so retries no longer depend on stale frontend guesses after success.

## Frontend Truth-Lock Changes

- Removed local cap-based action blocking from `useDailySession.canExecuteAction(...)` for backend-owned actions.
- Kept local guards only for client-owned runtime concerns such as:
  - pending action state
  - day ended state
  - timed activity / meal lock
  - not enough remaining time
- Added bundle-level `authoritativeState` storage in the gameplay loop provider.
- Added a dev-only diagnostics panel on the dashboard showing:
  - current job
  - cash / debt
  - stress / health
  - rideshare truth and blocker code
  - debt-payment truth
  - shift start truth
  - recovery remaining
  - refresh timestamp / degraded sections

## Section Resilience Policy

The loop keeps using section-level degradation behavior for optional data:

- economy summary
- stock market
- business summary
- business plan
- end-of-day summary

The core gameplay state is treated as critical and fetched from the combined loop route.

If optional sections fail, the gameplay loop still loads core player/work/action truth.

## Houston Time Truth

The canonical contract explicitly carries Houston-local timing fields:

- `houston_time`
- `houston_date`
- `houston_timezone = America/Chicago`
- `day_phase`

The combined loop route and refreshed work state remain the backend source for weekend/weekday and availability timing.

## Refresh Trigger Policy

Frontend refreshes now happen on:

- screen focus
- app resume
- after every successful gameplay action
- retry success paths already using the same refresh pipeline

Backend recomputation now happens on:

- every combined loop fetch
- every action-hub fetch
- every successful action response through `updated_state`

## Before / After

### Before

- Dashboard could use one snapshot while the action hub used another.
- A successful action could still leave stale blocker text or stale disabled buttons until the next full refresh completed.
- Local caps in `useDailySession` could block actions even when the backend still allowed them.

### After

- Dashboard and action hub load from the same combined backend truth snapshot.
- Successful actions return canonical `updated_state` and patch the visible bundle immediately.
- Backend-owned blockers come from structured truth instead of local cap guesses.
- Dev diagnostics expose the active backend truth for testing.

## Files Changed

- `backend/app/api/gameplay.py`
- `backend/tests/test_job_selection_flow.py`
- `expo/src/features/gameplayLoop/context.tsx`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/service.ts`
- `expo/src/features/gameplayLoop/types.ts`
- `expo/src/hooks/useDailySession.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/types/gameplay.ts`

## Validation Results

### Automated

- `python -m py_compile backend/app/api/gameplay.py`
- `python -m unittest tests.test_job_selection_flow.JobSelectionFlowTests.test_loop_bundle_uses_shared_authoritative_state_contract`
- `python -m unittest tests.test_job_selection_flow.JobSelectionFlowTests.test_execute_action_returns_updated_authoritative_state`
- `python -m unittest tests.test_shift_state_service.ShiftStateServiceTests.test_debt_payment_is_repeatable_but_request_replay_is_idempotent`
- `python -m unittest tests.test_shift_state_service.ShiftStateServiceTests.test_rideshare_state_recomputes_from_effective_stress_override`
- `python -m unittest tests.test_shift_state_service.ShiftStateServiceTests.test_recovery_actions_do_not_cross_block_each_other_before_category_cap`
- `python -m unittest tests.test_shift_state_service.ShiftStateServiceTests.test_recovery_category_cap_blocks_fifth_action_but_dinner_stays_available`
- `yarn typecheck`

All of the above passed in this step.

### 20-Action Stability Run Notes

Ran an ad-hoc scripted 20-step backend interaction sequence covering:

- combined loop fetches
- repeated action-hub recomputes
- debt payment
- idempotent debt payment replay
- recovery actions
- shift start
- shift auto-finalization via refreshed action state
- rideshare
- loan
- housing selection

Result:

- 20/20 interactions completed without crash
- replayed debt payment did not duplicate side effects
- refreshed loop payload remained readable after repeated writes
- no poisoned-session retry failure occurred in the run

Script end state:

- cash: `1176.32`
- debt: `265.00`
- stress: `25`
- health: `88`

## Notes

- This step did not add new gameplay content.
- The diagnostics panel is dev-only.
- Existing unrelated legacy test gaps outside this truth-lock path may still exist elsewhere in the suite, but the targeted state-truth and retry-safe flows above are green for this step.
