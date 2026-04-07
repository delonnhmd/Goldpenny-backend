# STEP 91 - Job Truth + Houston Auto End-Day + Economy Risk Visualization

## 1) Root cause of wrong current job label

### What was happening
- Job identity was being inferred from multiple places (`player.main_job`, scheduled shift template, active shift label, fallback text).
- Player-facing clock-in/action text used backend-style strings and raw ISO timestamp output.
- In edge/test flows, transactional table checks could rollback in-flight shift updates, which made job/shift state appear inconsistent.

### Why player saw confusing labels like "delivery"
- The UI could end up rendering shift/fallback context instead of a single authoritative current-job source.
- Clock-in text was built from request-time/job payload context instead of always rendering the resolved authoritative display job.

## 2) Authoritative job source chosen

Priority now implemented:
1. Active shift job (only when valid and intentionally active)
2. Canonical player job (`player.main_job`) as the default authority
3. No silent fallback hardcode for normal gameplay paths

Job truth context is now included in work payload:
- `authoritative_current_job_id`
- `current_job_display_name`
- `scheduled_shift_job_id`
- `active_shift_job_id`
- `pay_calculation_job_id`
- `ui_job_id`
- `job_truth_mismatch_detected`
- `job_truth_sources`

Mismatch logging now emits a warning with all relevant job IDs/sources.

## 3) Files changed for job identity fix

### Backend
- `backend/app/services/shift_state_service.py`
  - Added job-truth reconciliation context + mismatch logging
  - Added clean Houston-time labels
  - Added safer table-availability detection using the active session connection
  - Added stale-day guard logic for shift-window checks
- `backend/app/api/gameplay.py`
  - Added/expanded current-job display use in dashboard/action payload
  - Humanized clock-in/action summary text
  - Added economy risk overview payload construction

### Frontend
- `expo/src/types/gameplay.ts`
  - Added `current_job_display` and expanded `work_state`/economy types
- `expo/src/lib/api/gameplay.ts`
  - Normalized new job-truth, Houston-time, auto-rollover, and economy-risk fields
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
  - Added explicit work identity block (`Current job`, status, end time, pay model)
  - Added Houston time + reset display
  - Added economy risk/opportunity card + compact risk badges
  - Replaced backend-like UI wording

## 4) Houston timezone rollover rule

- Authoritative timezone: `America/Chicago` (Houston local time with DST handling via timezone-aware conversion)
- Day reset label shown to players: `12:00 AM CT`
- Work payload now exposes:
  - `current_houston_time_label`
  - `day_rollover_timezone`
  - `day_rollover_time_label`
  - `next_day_rollover_time`

## 5) Auto end-day flow (request-cycle MVP)

On gameplay/work state resolution:
1. Resolve current Houston time
2. Check if days were missed since last survival sync
3. Run Houston rollover when applicable
4. If an active shift is expired, auto-finalize it
5. Sync shift/day rules and return current-day-ready state
6. Return recap fields when rollover occurred:
   - `auto_day_rollover`
   - `auto_finalized_previous_day`
   - `auto_finalized_days_count`
   - `new_day_started_houston_time`
   - `auto_rollover_recap_lines`

No external cron dependency was introduced for MVP.

## 6) Shift auto-close flow at/after cutoff

Implemented behavior:
- If shift is active and end time has passed, it auto-finalizes in state resolution.
- Finalization resolves pay/XP/stat updates and marks shift completed.
- Shift/day rules then unlock follow-up actions (for example rideshare after eligible shift end).
- Added guard logic so stale day/date mismatch in minimal-schema environments does not incorrectly mark missed shift.

## 7) New economy risk/opportunity UI

Dashboard now includes an economy card with:
- Macro signals (player-readable)
  - Fuel pressure
  - Food inflation
  - Job market
  - Consumer mood
  - Supply chain
- Opportunity signals
  - Rideshare demand
  - Delivery demand
  - Grocery pressure
  - Downtown stress
- Compact risk badges (`Low` / `Moderate` / `High` / `Critical`)

## 8) Before/after player text examples

### Before
- `Clocked in as delivery. Backend shift ends at 2026-04-06T15:02:49.614562-05:00.`

### After
- `Clocked in as Chef · Shift ends at 3:02 PM CT`
- `Current job: Chef`
- `Shift active · Ends at 3:02 PM CT`
- `Houston time: 9:03 PM CT`
- `Day resets automatically at 12:00 AM CT`

## 9) Validation results

### Automated checks run
- `python -m pytest tests/test_shift_state_service.py tests/test_job_selection_flow.py -q` -> **13 passed**
- `python -m compileall app` -> pass
- `npm run typecheck` (expo) -> pass

### Scenario coverage status
- A. Same-day before cutoff: covered by shift window/state tests
- B. After cutoff auto-finalization/new day handling: covered via rollover/resolve paths and payload recap fields
- C. Open shift past end: covered by expired-shift auto-finalization tests
- D. Open shift across cutoff: covered by finalize + rollover interaction logic in resolver
- E. Offline gap handling: rollover/catchup paths present with guardrails
- F. DST safety: Houston-aware timezone conversion is used (`America/Chicago`)

## 10) Constraints check

- No background cron dependency added
- No raw backend ISO timestamps in player-facing action text
- Job identity now has a clear authoritative source + mismatch diagnostics
- Stale day state is actively reconciled in request-cycle flow
- Economy risk/opportunity is surfaced compactly on dashboard (no oversized analytics screen)
