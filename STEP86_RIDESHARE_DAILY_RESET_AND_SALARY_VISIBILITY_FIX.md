# STEP 86 — Rideshare Daily Reset + Salary Visibility Fix

## Goal Outcome
Step 86 is implemented.

The system now:
- resets rideshare availability by **actual in-game day progression** (not stale session/global-only values),
- computes rideshare "today" values from **current-day records only**,
- keeps rideshare status/button behavior aligned,
- and makes salary payout timing + amounts visible as a **daily model**.

---

## Root Cause: Stale Rideshare `6/6`
The main issue was day-resolution mismatch:

- Work/rideshare state used `GameState.current_day`.
- Player progression settles by `PlayerDailyState`/`last_settled_day`.
- If global day lagged player progression, rideshare usage remained attached to an old day, so players could remain at `6/6` even after progressing.

Secondary issue:
- "Trips today" came from mutable summary fields in daily state (`side_income_hours`) that could appear stale relative to actual per-day actions.

### Fix Applied
1. Added player-aware day resolver in shift/work state:
   - `backend/app/services/shift_state_service.py`
   - `_current_game_day_for_player(...)` chooses max of:
     - global game day
     - player progression day inferred from `last_settled_day` + latest `PlayerDailyState`

2. Rideshare "today" now uses authoritative current-day records:
   - `trips_today` basis switched to `SideIncomeAction` sum for `current_day`
   - `rideshare_earned_today` computed from current-day gameplay ledger (`income + ride_share`)

3. Rideshare engine now executes on resolved player current day:
   - `backend/app/engine/rideshare_engine.py`
   - uses `resolve_expired_shift_if_needed(...).current_game_day` instead of stale global day fetch

4. Added day/reset logs:
   - previous in-game day
   - current in-game day
   - reset applied boolean
   - trips after reset snapshot

---

## Root Cause: Missing / Unclear Salary
Salary pipeline was already daily at shift completion, but visibility was weak:

- UI emphasized projected pay (estimates) over posted salary totals.
- Salary timing model was not explicit in work surfaces.
- Salary transaction descriptions were generic, so payout timing was less auditable.

### Final Pay Model Chosen
**Daily pay after shift completion** (MVP).

- This remains the backend behavior.
- It is now explicit in work state + UI copy.

### Fix Applied
1. Salary ledger clarity:
   - shift completion salary transaction description now includes day:
     - `"Main job salary for Day N (...)"`
   - settlement fallback salary transaction also uses:
     - `"Main job salary for Day N"`

2. Work-state payload now includes explicit pay visibility fields:
   - `salary_earned_today`
   - `salary_earned_yesterday`
   - `pay_model = daily_after_shift_completion`
   - `pay_model_label = Paid daily after shift completion`
   - `salary_pending_until_completion`

3. Frontend work visibility updates:
   - Dashboard shows:
     - Salary today
     - Salary yesterday
     - Pay model
     - explicit status explanation:
       - worked => salary shown
       - shift active => pending
       - missed => no salary
       - weekend => no required shift
   - Brief screen now shows:
     - pay model
     - yesterday salary

---

## Rideshare Status/Button Consistency
Status and button disabled logic remain unified through backend rideshare truth object (from Step 85), and now use corrected day/trip sources.

Result:
- if `trips_today >= max_trips`: status = limit reached and buttons disabled
- if `trips_today < max_trips` and other rules allow: status = available and buttons enabled

---

## Files Changed
- `backend/app/services/shift_state_service.py`
- `backend/app/engine/rideshare_engine.py`
- `backend/app/services/daily_settlement_service.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/types/gameplay.ts`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/BriefScreen.tsx`

---

## Validation
Automated checks run:
- `pytest backend/tests/test_shift_state_service.py -q` → **11 passed**
- `pytest backend/tests/test_day_progression_services.py -q` → **7 passed**
- `pytest backend/tests/test_life_day_progression.py -q` → **4 passed**
- `yarn typecheck` (Expo) → **passed**

Case mapping:
- A. New day reset:
  - verified by `test_player_progress_day_prevents_stale_rideshare_cap_from_global_day_lag`
  - shows stale global day no longer keeps rideshare at old cap
- B. Ride share usage:
  - verified by `test_rideshare_unlocks_when_no_shift_is_scheduled`
  - confirms rideshare earned today > 0 after trip
- C. Main job daily salary:
  - verified by shift completion tests + explicit salary transaction-day description test
- D. Missed shift:
  - verified by `test_weekday_missed_shift_logs_penalty_and_unlock_event`
- E. Multi-day sanity:
  - player-day-aware current-day resolution + salary day labeling + yesterday salary visibility remove "worked many days but no clear pay trail" ambiguity

---

## Before vs After
Before:
- Rideshare could stay at `6/6` due to day mismatch, even when player expected a new day.
- Work UI could show generic pay estimates without clearly showing posted salary timing.

After:
- Rideshare day usage is tied to actual player in-game day and current-day action/ledger records.
- Salary model is explicitly daily-after-shift-completion and visible in Dashboard + Brief + transaction history.
