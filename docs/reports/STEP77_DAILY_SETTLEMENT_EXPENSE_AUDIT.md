# STEP 77 — Daily Settlement Expense Audit and Breakdown Fix

## Scope
Audited daily settlement accounting for:
- abnormal expense spikes (example class: ~389 XGP days),
- expense cadence correctness (daily vs weekly/monthly),
- duplicate settlement protection,
- income posting visibility and reconciliation,
- player-facing brief visibility.

## Root Cause Summary
1. Settlement previously exposed only aggregate `income_xgp`/`expenses_xgp`, so large expense days were opaque.
2. Expense spikes are real in high-risk states and are mostly driven by event-heavy categories (especially `medical_cost` + `missed_work_penalty` + pressure-related `other_expense`), not just base food/rent.
3. Gas cadence was adjusted to explicit weekly charging (`30 XGP` on day multiples of 7), instead of being treated like a daily settlement drain.
4. A reconciliation defect existed where streak income boosts could be applied after initial totals were computed, causing mismatch between `starting_cash + net_change` and `ending_cash`; this is now reconciled.

## Exact Cash-Drain Categories (Observed)

### High-expense reproduced run (high-risk player, no work)
Reproduced day with extreme expense:
- Day 7:
  - `total_income`: `0.00`
  - `total_expense`: `392.05`
  - `medical_cost`: `215.20`
  - `missed_work_penalty`: `80.00`
  - `other_expense`: `85.00`
  - `interest_payment`: `0.26`
  - `debt_payment`: `8.13`

This confirms abnormal daily totals are primarily from stacked event/pressure penalties, not baseline housing/food alone.

### Normal early-player 5-day validation (no business, no rare health event)
Simulated with deterministic seed, manual worked days `{1,3,5}` and posted job income:

1. Day 1: income `123.86`, expense `55.79`, net `+68.07`, ending `1068.07`
2. Day 2: income `0.00`, expense `52.39`, net `-52.39`, ending `1015.68`
3. Day 3: income `123.91`, expense `56.17`, net `+67.74`, ending `1083.42`
4. Day 4: income `0.00`, expense `52.41`, net `-52.41`, ending `1031.01`
5. Day 5: income `164.27`, expense `65.16`, net `+99.11`, ending `1130.12`

Checks:
- `weekly_gas_expense_xgp`: `0.00` on days 1–5
- `medical_cost_xgp`: `0.00` on all 5 days
- `business_overhead_xgp`: `0.00` on all 5 days
- each day reconciles exactly: `starting_cash + net_change == ending_cash`

## Cadence Audit Results

### Gas
- Implemented weekly cadence in settlement:
  - `WEEKLY_GAS_EXPENSE_XGP = 30.00`
  - charged only when `settled_day % 7 == 0`
- Verification run:
  - days 1–6 gas = `0.0`
  - day 7 gas = `30.0`

### Housing / Rent
- `rent_expense` currently reflects configured daily housing+utilities settlement model (`housing_cadence: daily_configured`).

### Debt
- `debt_payment`/`interest_payment` are included per configured debt engine daily obligation model (`debt_cadence: daily_obligation_configured`).

### Business / Spoilage / Overhead
- Verified zero when no active business (`business_costs_applied: false`).

### Medical / Maintenance
- Event-driven behavior confirmed:
  - normal run: `medical_cost = 0`
  - high-risk run: large medical + missed-work penalties can produce 300+ expense days.

## Duplicate Settlement Application

### Guard rails added
- `settlement_day_key = "{player_id}:{day}"` recorded in debug payload.
- `existing_settlement_count_for_day` check added.
- `last_settled_day` monotonic guard added.
- existing per-day log + `pds.did_settlement` checks retained.

### Validation
- Normal progression: no duplicate settlement observed.
- Synthetic inconsistent-state test (existing day log + unsettled day-state) now fails with:
  - `SettlementValidationError: Player day 1 already settled.`

## Income Posting Verification
- Breakdown now reports true income channels:
  - `job_income`, `rideshare_income`, `business_income`, `stock_sale_income`, `other_income`.
- Worked days in validation run show posted income (>0), non-worked days remain near 0 except event-driven `other_income`.
- Settlement now returns `total_income`, `total_expense`, `net_change`, `ending_cash` alongside full breakdown objects.

## Debug Output Added

Enable focused settlement audit logging with:
- `SETTLEMENT_AUDIT_DEBUG_PLAYER_ID=<player_uuid|*>`
- `SETTLEMENT_AUDIT_DEBUG_DAY=<day|*>`

When enabled, one log line prints:
- `starting_cash`
- each income bucket
- each expense bucket
- `ending_cash`
- cadence flags (weekly/monthly charge indicators)
- duplicate-detection state (`settlement_day_key`, existence flags, log id)

## Player-Facing Brief Visibility
Added to daily brief `player_impact_json`:
- `yesterday_income_total_xgp`
- `yesterday_expense_total_xgp`
- `yesterday_biggest_expense_category`
- `yesterday_net_change_xgp`

## Before vs After (1 Settled Day Example)

### Before fix (observed reconciliation defect in settlement payload)
- `starting_cash`: `986.28`
- `total_income`: `123.91`
- `total_expense`: `67.70`
- `net_change`: `56.21`
- `ending_cash`: `1044.97`
- mismatch: `986.28 + 56.21 = 1042.49` (off by `+2.48`)

### After fix (same code path class, reconciled)
- `starting_cash`: `1031.01`
- `total_income`: `164.27`
- `total_expense`: `65.16`
- `net_change`: `99.11`
- `ending_cash`: `1130.12`
- reconciles exactly: `1031.01 + 99.11 = 1130.12`

## Files Changed
- `app/services/daily_settlement_service.py`
- `app/services/day_progression_service.py`
- `app/services/daily_brief_service.py`
- `app/api/day.py`
- `STEP77_DAILY_SETTLEMENT_EXPENSE_AUDIT.md`
