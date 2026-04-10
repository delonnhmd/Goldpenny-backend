# STEP 93E - Testing Mode Short Shifts + Overtime + Weekend Rideshare + Debt Action Refresh + Retry Fix

## Root cause

### Pay Debt locked after the first payment
- The client still treated `debt_payment` like a capped daily action.
- Local action history incremented the debt-payment count and the balance config still assigned it a time cost and cap behavior, so the button could stay disabled even when `cash > 0` and `debt > 0`.
- The action refresh path also did not distinguish between:
  - replay of the same debt-payment request
  - a brand-new valid second payment

### Retry crashed on duplicate shift salary audit insert
- Shift salary audit logging assumed each completion/retry path owned the insert for `shift_token`.
- A retry could attempt to insert the same `shift_token` again and hit `ix_shift_salary_audit_log_shift_token`.
- Salary posting logic also reused the day-level `PlayerDailyState.salary_transaction_id` as if it belonged to the current shift, which broke second-shift overtime posting and blurred per-shift retry recovery.

## Testing mode configuration

Shared testing-mode config now lives in `backend/app/services/shift_state_service.py`:

- `testing_mode`
- `shift_minutes = 15`
- `two_shift_jobs = ["retail_worker", "warehouse_operator"]`
- `max_daily_shifts_for_two_shift_jobs = 2`
- `second_shift_overtime_multiplier = 1.5`
- `weekday_rideshare_cap = 6`
- `weekend_rideshare_cap = 18`
- `weekend_main_shift_enabled = false`

These overrides apply only when testing mode is enabled. Production behavior remains behind the normal path when testing mode is off.

## Fix summary

### Debt action refresh and repeatable payments
- Removed client-side daily-cap behavior for `debt_payment`.
- Debt payments now use request-scoped idempotency keys so:
  - the same tap replay does not duplicate the payment
  - the next deliberate tap creates a new valid payment
- Dashboard debt handling now leaves the control usable after success when both of these remain true:
  - `cash > 0`
  - `debt > 0`
- Action hub, cash, debt, and debt-card state now recompute from fresh backend values after success.

### Shift salary audit idempotency and retry safety
- Shift audit creation now goes through `_upsert_shift_salary_audit_row(...)`.
- Audit writes use nested-transaction recovery and re-query existing rows by `shift_token` on conflict.
- Salary posting now treats `audit_row.salary_transaction_id` as the authoritative per-shift pointer instead of reusing the day-level salary transaction pointer.
- Retry paths reuse the existing salary result for the same shift token instead of creating:
  - duplicate audit rows
  - duplicate salary transactions
  - duplicate XGP payments

### 15-minute shifts, overtime, and weekend rideshare-only
- Testing mode shifts now resolve to 15 minutes.
- `warehouse_operator` and `retail_worker` can complete up to 2 main shifts per day in testing mode.
- Shift 2 applies a `1.5x` overtime multiplier.
- Weekend testing mode blocks required main shifts and switches the day to rideshare-only with an 18-trip cap.
- Rideshare remains available after Shift 1 or Shift 2 when time, health, stress, location, and cap checks all allow it.

### UI and payload updates
- Work-state payload now returns testing-mode fields including:
  - shift length
  - shifts completed today
  - whether overtime is available
  - weekend rideshare-only state
  - rideshare cap today
- Dashboard now shows:
  - testing mode flag
  - `Shift length: 15 minutes`
  - `Shifts today: X / Y`
  - overtime availability / daily shift limit reached
  - weekend rideshare-only messaging
- Job labels were standardized for player-facing text:
  - `retail` => `Retail Seller`
  - `warehouse_operator` => `Warehouse Manager`

## Files changed

- `backend/app/services/shift_state_service.py`
- `backend/app/api/gameplay.py`
- `backend/app/services/job_progress_service.py`
- `backend/app/engine/career_config.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/hooks/useDailySession.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/lib/balanceConfig.ts`
- `expo/src/types/gameplay.ts`

## Before / after

### Debt payment
- Before: a successful debt payment could leave the button disabled for the rest of the day even though the player still had cash and debt remaining.
- After: debt payment stays available after each success as long as `cash > 0` and `debt > 0`, while replaying the same request still does not duplicate the payment.

### Shift retry
- Before: retrying a partially completed shift could hit duplicate `shift_token` audit inserts and poison the session/transaction.
- After: retries reuse the existing audit/payment result for that shift token and do not crash or double-pay.

### Testing mode work loop
- Before: work still behaved like a single long shift and did not support the requested testing loop.
- After:
  - Shift 1 lasts 15 minutes
  - Shift 2 unlocks only for eligible testing-mode jobs
  - Shift 2 posts overtime salary at `1.5x`
  - weekend becomes rideshare-only with an 18-trip cap

## Validation results

- `python -m pytest backend/tests/test_shift_state_service.py -q`
  - `22 passed`
- `python -m py_compile backend/app/services/shift_state_service.py backend/app/api/gameplay.py backend/app/services/job_progress_service.py backend/app/engine/career_config.py`
  - passed
- `npm.cmd run typecheck` in `expo/`
  - passed

## Targeted scenarios covered

- Repeated debt payment stays usable while cash and debt remain.
- Replay of the same debt-payment request does not create a second payment.
- Shift 1 in testing mode lasts 15 minutes and exposes overtime availability for eligible jobs.
- Shift 2 posts `Overtime Salary - Shift 2 - Warehouse Manager (1.5x)`.
- Rideshare remains available after Shift 1 and after Shift 2 when normal blockers allow it.
- Weekend testing mode resolves to rideshare-only with an 18-trip cap.
- Retry after partial shift salary posting reuses the existing payment path and does not duplicate salary rows.
