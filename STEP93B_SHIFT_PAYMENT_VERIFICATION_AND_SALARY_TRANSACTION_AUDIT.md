# STEP 93B - Shift Payment Verification + Salary Transaction Audit

## Goal

Verify and harden the live main-shift salary path so every completed paid shift leaves a provable trail:

1. shift completed
2. salary calculated
3. salary transaction created
4. cash updated
5. dashboard/work UI updated
6. daily activity / ledger aligned

This step does not redesign payroll. It makes the existing payroll path auditable, recoverable, and visible.

## Root Cause

The pre-Step-93B flow already created most salary side effects, but the proof chain was incomplete:

- shift completion, cash mutation, ledger insertion, and UI state were tightly bundled inside `finalize_active_main_shift`
- there was no dedicated salary audit record tying the shift snapshot to the resulting ledger rows and cash delta
- work-state UI only exposed aggregate salary values, not transaction confirmation or posting status
- dashboard activity history was action-driven, not ledger-driven, so salary proof was easy to miss
- failure handling was weak: if salary posting failed mid-flow, the player-facing state did not clearly preserve a recoverable salary-posting failure

That meant we could often infer that salary was paid, but we could not always prove it cleanly from one canonical record.

## End-to-End Salary Flow Map

### 1. Shift start

Entry point:

- `backend/app/services/shift_state_service.py`
- `start_main_shift(...)`

What happens:

- validates authoritative main job
- stores active shift snapshot on `Player`
- writes/updates `PlayerDailyState`
- logs `shift.shift_started`

### 2. Shift completion trigger

Entry points:

- `resolve_expired_shift_if_needed(...)`
- `finalize_active_main_shift(...)`

What happens:

- expired active shifts auto-finalize
- salary-post failures are retried on later sync via `_retry_pending_shift_salary_if_needed(...)`

### 3. Immutable salary snapshot

Builder:

- `_build_shift_salary_snapshot(...)`

Snapshot contents:

- player id
- day number
- job key / display name
- shift token
- started / ended / completed timestamps
- base monthly salary
- pay snapshot used
- base hourly pay
- productivity multiplier
- income multiplier
- job level multiplier
- gross shift pay
- final salary paid
- xp / stress / health / fatigue outcomes
- cash before

### 4. Shift completion record

Writer:

- `_record_completed_shift_pending_salary(...)`

What it writes:

- `JobAction` shift completion row
- `ShiftSalaryAuditLog` row with `payment_status = pending`
- `PlayerDailyState` shift completion markers

Important:

- this stage records that the shift completed before salary is posted
- if salary posting later fails, the completion record still exists

### 5. Salary posting

Writer:

- `_post_shift_salary_from_audit(...)`

What it writes atomically:

- `XGPTransaction`
- `PlayerTransactionLog`
- `GameplayTransaction` with `type = income` and `category = salary`
- `ContributionEvent`
- `PlayerDailyState.salary_transaction_id`
- `PlayerDailyState.salary_posted_at`
- `PlayerDailyState.salary_earned`
- `Player.cash`
- `ShiftSalaryAuditLog.payment_status = posted`

Salary transaction description:

- `Main job salary for Day N (Job Label)`

### 6. Failure handling

Failure handler:

- `_mark_shift_salary_post_failed(...)`

What happens on failure:

- post transaction is rolled back
- cash does not change
- gameplay salary transaction is not created
- audit row is preserved as `payment_status = failed`
- failure reason is stored
- work-state payload returns salary failure status to UI

### 7. UI payload rendering

Payload builder:

- `build_work_state_payload(...)`

Salary-related fields now returned:

- `salary_payment_status`
- `salary_status_label`
- `salary_status_message`
- `salary_transaction_id`
- `salary_posted_at`
- `salary_transaction_confirmed`
- `current_shift_salary_audit`
- `last_salary_posted`
- `recent_salary_audits`
- enriched `last_completed_shift`

Important:

- salary totals shown in work state now prefer gameplay ledger truth
- the ledger wins over stale daily aggregates when both are available

### 8. Dashboard / activity rendering

Backend route logging:

- `backend/app/api/gameplay.py`
- `_log_salary_ui_payload_rendered(...)`

Frontend rendering:

- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/BriefScreen.tsx`

What the player now sees:

- `Shift active - Salary pending until completion`
- `Shift completed - Salary +X XGP posted`
- `Shift completed - Salary calculation failed`
- `Missed shift - No salary earned`
- last salary row
- recent salary audit rows
- ledger-backed activity entries including salary

## Salary Audit Schema

Model:

- `backend/app/models/shift_salary_audit_log.py`

Core fields:

- `player_id`
- `day_number`
- `shift_token`
- `shift_id`
- `job_key`
- `job_display_name`
- `shift_started_at`
- `shift_ends_at`
- `shift_completed_at`
- `shift_type`
- `shift_number`
- `hours_worked`
- `payment_status`
- `failure_reason`
- `base_monthly_salary`
- `pay_snapshot_used`
- `base_hourly_pay`
- `productivity_multiplier`
- `income_multiplier`
- `job_level_multiplier`
- `gross_shift_pay`
- `final_salary_paid`
- `salary_transaction_id`
- `xgp_transaction_id`
- `player_transaction_log_id`
- `salary_posted_at`
- `cash_before`
- `cash_after`

This is the canonical per-shift salary proof object.

## Mandatory Transaction Rule

Rule enforced:

- a paid shift is not considered posted unless a gameplay salary transaction exists

Implementation details:

- `_post_shift_salary_from_audit(...)` now refuses to proceed if gameplay ledger is unavailable
- cash mutation and transaction creation occur in the same DB transaction
- if the gameplay salary transaction fails, the transaction is rolled back and the audit is marked failed
- `PlayerDailyState.salary_transaction_id` is the day-level confirmation pointer

## Duplicate-Payment Protection

Protection layers:

1. `ShiftSalaryAuditLog.shift_token` is unique
2. `_post_shift_salary_from_audit(...)` exits early for `payment_status = posted`
3. `_post_shift_salary_from_audit(...)` checks `PlayerDailyState.salary_transaction_id` before creating a second salary transaction
4. retries repair pending/failed salary rows instead of creating a new shift payment

Result:

- repeated refreshes / expired-shift resolution do not create duplicate salary ledger rows

## Failure Isolation / Recovery Strategy

If salary calculation or posting fails:

- the shift completion record remains
- cash stays unchanged
- salary transaction is absent
- audit row records `failed`
- failure reason is surfaced to UI
- later sync attempts can retry posting through `_retry_pending_shift_salary_if_needed(...)`

This preserves trust:

- no silent money movement
- no lost completed shift
- no duplicate salary on retry

## UI Updates

### Dashboard

Updated:

- work status card now shows explicit salary posting state
- salary today card is paired with transaction confirmation state
- last salary row shows amount and transaction confirmation
- recent salary audits list provides quick debug visibility
- activity history now prefers ledger transactions, so salary appears as a distinct daily activity line item

### Brief

Updated:

- work status now reflects salary posting state, not just generic worked/missed
- last salary value is shown in the work summary
- status caption now mirrors salary posting outcome

## Files Changed

- `backend/app/models/shift_salary_audit_log.py`
- `backend/app/models/player_daily_state.py`
- `backend/app/models/__init__.py`
- `backend/app/main.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/api/gameplay.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/types/gameplay.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/BriefScreen.tsx`

## Before / After

### Before

- shift pay could be inferred from cash and daily totals, but not from one canonical audit record
- dashboard salary visibility was aggregate-only
- activity history could omit explicit salary proof
- posting failures were not surfaced as a durable salary audit state

### After

- every completed paid shift creates a `ShiftSalaryAuditLog` row
- every posted salary points to a gameplay salary transaction
- work-state payload exposes status, transaction id, timestamps, and audit details
- dashboard and brief show pending vs posted vs failed salary states
- activity history shows salary as a distinct ledger-backed line item
- failed salary posting leaves a recoverable failed audit and no cash mutation

## Validation Results

Executed:

- `python -m pytest backend/tests/test_shift_state_service.py backend/tests/test_job_selection_flow.py backend/tests/test_daily_brief_service.py -q`
- `yarn typecheck` in `expo/`

Results:

- `21 passed`
- Expo TypeScript check passed

Scenarios explicitly covered:

- successful shift payment creates salary audit + gameplay salary transaction
- audit cash delta matches posted salary
- expired shift finalization remains idempotent
- salary transaction description remains day-explicit
- salary posting failure preserves failed audit without cash mutation
- job selection flow still passes after the salary instrumentation changes

## Constraints Check

- no payroll redesign: kept existing salary formula, surfaced it via audit
- no salary posting without transaction proof: enforced
- no duplicate salary on refresh / retry: enforced
- ledger remains source of truth for salary visibility: enforced
- backward-compatible for existing players: additive schema changes only

## Final Outcome

Step 93B now gives a provable salary chain:

- completed shift
- auditable salary snapshot
- mandatory gameplay salary transaction
- traceable cash mutation
- visible dashboard / brief status
- ledger-backed daily activity

This closes the payment-trust gap for live shift salary posting.
