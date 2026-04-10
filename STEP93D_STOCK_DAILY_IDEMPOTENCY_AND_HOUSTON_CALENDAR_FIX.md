# STEP 93D - Stock Daily Idempotency and Houston Calendar Fix

## Root cause

### Duplicate stock daily price insert crash
- `run_player_next_day()` only checked `max(stock_daily_prices.day)` once, then called `generate_next_stock_day()`.
- `generate_next_stock_day()` always wrote `previous_max_day + 1` with plain inserts and assumed it was the only caller creating that day.
- If dashboard/actions/auto-rollover re-entered settlement around the same time, a second caller could still try to create the same `(day, ticker)` rows and hit `uq_stock_daily_price_day_ticker`.

### Thursday shown as weekend
- Work/calendar state used `_day_to_date(current_game_day)` for `day_of_week` and `is_weekend`.
- The clock card rendered the visible date from the live Houston clock, but rendered weekend/weekday state from the game-day mapping.
- That let the UI show a real Houston date like `Apr 9, 2026` while still using a weekend classification derived from a different mapped game day.

## Fix summary

### Shared idempotent stock generation helper
- Added `get_or_create_stock_daily_price(...)` in `backend/app/services/market_daily_update_service.py`.
- Added `generate_stock_day_for_day(...)` so stock day creation is target-day aware and idempotent.
- Added `ensure_stock_market_day(...)` so callers ask for `market day N` explicitly instead of blindly generating `max + 1`.
- `run_player_next_day()` now uses `ensure_stock_market_day(..., caller="run_player_next_day")`.
- Stock row creation now:
  - checks for existing `(day, ticker)` first
  - inserts inside a nested transaction
  - re-queries on `IntegrityError`
  - returns the existing row instead of crashing

### Settlement/day generation safety
- Day progression now advances market data only through the requested settlement day.
- This prevents stale `max(day)` reads from skipping ahead and accidentally generating the wrong next market day.

### Correct Houston calendar derivation
- `backend/app/services/shift_state_service.py` now derives:
  - Houston local date
  - weekday index
  - weekday label
  - weekend/weekday phase
  from `now_houston.date()` in `America/Chicago`.
- The work payload now returns:
  - `current_houston_date`
  - `current_houston_date_label`
  - `day_of_week`
  - `phase_status_label`
- Dashboard clock UI now uses those backend-truth calendar fields and shows an explicit `Day of week` row.

### Gameplay loop degradation
- If Houston auto-rollover hits a market/settlement failure, `resolve_expired_shift_if_needed()` now:
  - logs the failure
  - rolls back the failing transaction
  - returns core work/dashboard state with degraded market metadata
- Dashboard/action payloads surface:
  - `market_data_available`
  - `market_data_message`
  - `degraded_sections`
- Dashboard UI now shows:
  - `Market data temporarily unavailable`
  - `Core dashboard loaded with limited economy data`

## Fields and flags audited
- `stock_daily_prices.day`
- `stock_daily_prices.ticker`
- `current_houston_time`
- `current_houston_date`
- `day_of_week`
- `is_weekend`
- `phase_status_label`
- `scheduled_shift_window_label`
- `degraded_sections`
- `market_data_available`
- `market_data_message`

## Files changed
- `backend/app/services/market_daily_update_service.py`
- `backend/app/services/day_progression_service.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/api/gameplay.py`
- `backend/tests/test_day_progression_services.py`
- `backend/tests/test_shift_state_service.py`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/types/gameplay.ts`

## Before / after

### Stock day creation
- Before: repeated settlement/dashboard/action loads could retry plain inserts for the same `(day, ticker)` and crash.
- After: repeated calls for the same target market day reuse existing rows and do not create duplicates.

### Houston clock truth
- Before: the clock card could show `Apr 9, 2026` while still labeling the day as `Weekend`.
- After: `Apr 9, 2026` resolves to `Thursday` and `Weekday`, and the shift window stays on the weekday schedule.

### Dashboard resilience
- Before: a stock daily-price failure could take down dashboard/actions through auto-rollover settlement.
- After: core work/dashboard state still returns with a degraded market warning when rollover market bootstrap fails.

## Validation results
- `python -m pytest backend/tests/test_day_progression_services.py backend/tests/test_shift_state_service.py -q`
  - `26 passed`
- `python -m py_compile backend/app/services/market_daily_update_service.py backend/app/services/day_progression_service.py backend/app/services/shift_state_service.py backend/app/api/gameplay.py`
  - passed
- `npm.cmd run typecheck` in `expo/`
  - passed

## Targeted scenarios covered
- Repeated same-day stock bootstrap does not duplicate rows.
- Houston `2026-04-09` resolves to `Thursday / Weekday` even if the mapped game day points at a weekend date.
- Weekend still resolves correctly for actual Houston weekend dates.
- Auto-rollover market failure no longer crashes work-state resolution; dashboard can degrade gracefully.
