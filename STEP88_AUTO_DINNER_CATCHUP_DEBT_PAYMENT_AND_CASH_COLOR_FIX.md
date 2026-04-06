# Step 88 - Auto Dinner, Catch-Up, Debt Payment, and Cash Color Fix

## Scope
This patch fixes four trust-critical gameplay issues:
- cash color now reflects actual cash sign only
- dinner can still be executed at night while the day is active
- missed-login days now resolve survival (dinner) automatically
- players can pay debt directly with a custom amount

## Root Cause - Wrong Cash Color
- Cash tone in UI was threshold-based (`<50 danger`, `<200 warning`, otherwise positive), not sign-based.
- This could show positive cash in non-green tones, which looked like a financial contradiction.

## New Cash Color Rule
- `cash > 0` -> `positive` (green)
- `cash == 0` -> `neutral`
- `cash < 0` -> `danger` (red)

Applied in:
- `DashboardScreen` stats card
- `LifeScreen` health/stress/cash panel

## Daily Dinner Resolution (No Hidden Survival)
Dinner now resolves through backend day logic, not client session presence.

### Manual dinner
- `eat_meal` execution now routes through `apply_manual_meal_action(...)`.
- Dinner can be paid by:
  - cash (`manual_cash`)
  - debt coverage when cash is short (`manual_debt`)
- If day already settled:
  - returns clear message: `Day finalized. Dinner outcome already recorded.`
- If dinner already resolved today:
  - returns clear message: `Dinner already resolved today.`

### Auto dinner at settlement
- Settlement now enforces dinner resolution via:
  - `ensure_day_dinner_resolved(... source="end_of_day_settlement")`
- This guarantees food outcome is recorded every settled day.

### Auto dinner for missed-login days
- Offline catch-up runs in work-state sync:
  - `run_offline_survival_catchup(...)`
- For each missed day:
  - resolves dinner
  - records transactions
  - updates health/stress/debt effects
  - finalizes daily state markers

## Catch-Up Behavior
- Uses Houston date progression and `players.last_survival_resolved_date`.
- Processes missed days sequentially and logs each processed day snapshot.
- Sync path runs when work-state is resolved (dashboard/work-state fetch path), so survival is not skipped while offline.

## Auto Dinner Cash vs Debt Logic
- If enough cash:
  - expense transaction category `food`
  - dinner mode `auto_cash`
- If cash is short and debt extension allowed:
  - partial/zero cash + debt increase for uncovered meal
  - debt transaction category `survival_debt`
  - health/stress penalty transaction category `health_penalty`
  - dinner mode `auto_debt`
- If debt extension blocked:
  - dinner mode `missed`
  - larger health/stress penalty transaction category `health_penalty`

## Debt Payment Flow (Backend + UI)
### Backend
- Added `debt_payment` execution path in `/gameplay/player/{id}/actions/execute`
- Validation:
  - amount > 0
  - amount <= cash
  - amount <= debt
- Effects:
  - `cash -= amount`
  - `debt_xgp -= amount`
  - ledger transaction:
    - type: `expense`
    - category: `debt_payment`
    - description: `Debt payment`

### Frontend
- Added Pay Debt controls in Dashboard Finance card:
  - amount input
  - `Pay Debt` button
  - quick amounts: `Pay 10`, `Pay 25`, `Pay 50`, `Pay Max`
- Uses the same gameplay execution pipeline (`action_key: debt_payment`)
- Immediate feedback and refresh through existing loop execution + sync.

## Night Reminder + Dinner UX
- Work-state payload now includes:
  - `needs_dinner_reminder`
  - `dinner_reminder_message`
  - `dinner_resolved_today`
  - `dinner_mode_today`
- Dashboard shows high-visibility reminder banner at night when dinner is unresolved.
- Dinner button is no longer blocked by low cash (dinner can use debt coverage).
- Breakfast/lunch still require cash.

## Files Changed
- Backend
  - `backend/app/services/dinner_survival_service.py` (new)
  - `backend/app/models/player.py`
  - `backend/app/models/player_daily_state.py`
  - `backend/app/main.py`
  - `backend/app/services/shift_state_service.py`
  - `backend/app/services/daily_settlement_service.py`
  - `backend/app/api/gameplay.py`
- Frontend
  - `expo/src/hooks/useDailySession.ts`
  - `expo/src/lib/api/gameplay.ts`
  - `expo/src/types/gameplay.ts`
  - `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
  - `expo/src/features/gameplayLoop/screens/LifeScreen.tsx`

## Before vs After
### Before
- Positive cash could appear in non-green warning/danger tones.
- Dinner could be blocked by frontend time guard (`Not enough time today`).
- Offline days could pass without explicit survival outcomes.
- No direct, transparent debt payment action from dashboard.

### After
- Cash color now strictly follows sign.
- Dinner can still execute at night while day is active.
- Missed-login days auto-resolve dinner with visible transactions and consequences.
- Player can pay custom debt amounts with immediate cash/debt updates and ledger entry.

## Validation Results
- Build checks:
  - `python -m compileall backend/app` passed
  - `npx tsc --noEmit` (Expo) passed
- Code-path verification:
  - `eat_meal` no longer uses local duplicate meal logic; now uses shared dinner survival service.
  - zero-time action guard now allows `eat_meal`/`debt_payment`/`quick_loan`/`select_housing` without false time-blocking.
  - settlement path enforces dinner resolution every day.
  - debt payment execution writes gameplay transaction and updates balances atomically.
