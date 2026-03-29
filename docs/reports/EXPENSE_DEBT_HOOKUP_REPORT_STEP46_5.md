# Expense + Debt Logic Hookup Report — Step 46.5

**Date:** 2025-10-04  
**Scope:** Minimal expense/debt layer for Gold Penny gameplay economy loop  
**Baseline:** Step 46.4.1 complete (0 TS errors, 12 ESLint warnings)

---

## Objective

Introduce a clean, named expense/debt contract that feeds the gameplay economy loop without duplicating existing logic or overbuilding a full finance simulator.

---

## Existing Infrastructure (Pre-Step 46.5)

The following was already in place before this step:

| File | What existed |
|---|---|
| `src/types/economy.ts` | `DebtPressureLevel`, `EconomyStatus`, `GameplayEconomyState` with `expenseAmount`, `debtAmount`, `debtPressure`, `netCashFlow`, `economyWarnings` |
| `src/hooks/useEconomyState.ts` | `deriveGameplayEconomyState()` — derives full economy contract from `PlayerDashboardResponse` + `EndOfDaySummaryResponse`. Exports `useEconomyState` hook. |
| `src/pages/gameplay/GameDashboardPage.tsx` | Already calls `useEconomyState` and passes `economy={economyState}` to `PlayerStatsBar` |
| `src/components/gameplay/PlayerStatsBar.tsx` | Displays Cash, Debt, Net Worth, Cash Flow, Stress, Health, Credit, Job, Income tiles |
| `src/types/gameplay.ts` | `EndOfDaySummaryResponse.tomorrow_warnings` — array of forward-facing warning strings |

**What was NOT yet in place:**
- A dedicated `ExpenseDebtContract` interface giving the expense/debt domain a clean named type (like `JobIncomeContract` for income)
- `Expenses` tile in `PlayerStatsBar` (daily spend, post-settlement)
- `Pressure` tile in `PlayerStatsBar` (qualitative debt pressure label when high/critical)
- `debtWarning`, `tomorrowWarnings`, `financialStressWarning` as explicitly named contract fields
- `useExpenseDebt` hook wired into the page

---

## Files Reviewed

| File | Purpose | Changed |
|---|---|---|
| `src/hooks/useEconomyState.ts` | Economy state derivation (read only — reused via import) | No |
| `src/types/economy.ts` | Economy domain types | No |
| `src/types/gameplay.ts` | Gameplay API response types | No |
| `src/lib/gameplayFormatters.ts` | `formatMoney` and label helpers | No |
| `src/hooks/useDebt.tsx` | Token-era social debt hook (wallet-address-based) | No (see notes) |
| `src/components/TopStatusBar.tsx` | Shows old social debt warning via `useDebt` | No (see notes) |
| `src/pages/gameplay/GameDashboardPage.tsx` | Gameplay page — hooks + PlayerStatsBar wiring | **Yes** |
| `src/components/gameplay/PlayerStatsBar.tsx` | Stats tile bar | **Yes** |
| `src/hooks/useExpenseDebt.ts` | New expense/debt contract hook | **Yes (created)** |

---

## Files Updated

### NEW: `src/hooks/useExpenseDebt.ts`

Clean minimal hook following the same derivation pattern as `useJobIncome`. Reuses `deriveGameplayEconomyState` from `useEconomyState` to avoid duplicating logic.

**`ExpenseDebtContract` interface:**

| Field | Type | Source |
|---|---|---|
| `expenseAmount` | `number \| null` | `EndOfDaySummaryResponse.total_spent_xgp` (null during active day) |
| `expenseLabel` | `string` | `formatMoney(expenseAmount)` or `"Pending"` |
| `debtAmount` | `number` | `DashboardStatSnapshot.debt_xgp` |
| `debtLabel` | `string` | `formatMoney(debtAmount)` |
| `debtPressure` | `DebtPressureLevel` | Derived: debt-to-cash ratio + net worth check |
| `debtWarning` | `boolean` | `debtPressure === 'high' \| 'critical'` |
| `netCashFlow` | `number \| null` | `EndOfDaySummaryResponse.net_change_xgp` (null during active day) |
| `netCashFlowLabel` | `string` | `"+x.xx xgp"`, `"-x.xx xgp"`, or `"Pending"` |
| `financialStressLevel` | `EconomyStatus` | Derived: `stable \| watch \| strained \| critical` |
| `financialStressWarning` | `boolean` | `financialStressLevel === 'strained' \| 'critical'` |
| `economyWarnings` | `string[]` | Debt pressure + top_risks from dashboard |
| `tomorrowWarnings` | `string[]` | `EndOfDaySummaryResponse.tomorrow_warnings` |
| `financialSummary` | `string` | Human-readable economy summary line |

**Safety guarantees:**
- Returns `DEFAULT_EXPENSE_DEBT` when dashboard is null — no crashes during initial load
- All `Number()` casts in `deriveGameplayEconomyState` handle NaN/undefined/null → 0
- `tomorrowWarnings` guarded with `Array.isArray` check
- Pure `useMemo` derivation — no side effects, safe for repeated day advancement

### MODIFIED: `src/components/gameplay/PlayerStatsBar.tsx`

Added `expenseDebt?: ExpenseDebtContract | null` optional prop.

New tiles (post-settlement and conditional):

| Tile | Condition | Value | Tone |
|---|---|---|---|
| `Expenses` | `expenseDebt.expenseAmount != null` | `expenseLabel` | Amber when > 0 |
| `Pressure` | `expenseDebt.debtWarning === true` | Pressure level label | Amber (`high`) or Red (`critical`) |

Tile order in bar (full day cycle):
`Day → Cash → Debt → Net Worth → Cash Flow → Stress → Health → Credit → Job → Income → Expenses → Pressure (when warning) → Region`

### MODIFIED: `src/pages/gameplay/GameDashboardPage.tsx`

- Added `import { useExpenseDebt } from '@/hooks/useExpenseDebt';`
- Added `const expenseDebt = useExpenseDebt(dashboardState.data, eodState.data);` alongside `economyState` and `jobIncome`
- Passed `expenseDebt={expenseDebt}` to `<PlayerStatsBar />`

---

## Daily Progression Integration

`expenseDebt` is derived from `dashboardState.data` and `eodState.data` — both are refreshed after day advancement by the existing `GameDashboardPage` refresh logic. This means:
- After `endDay()` → `eodState.data` is loaded → `expenseDebt.expenseAmount` and `netCashFlow` become available
- `debtPressure`, `debtWarning`, and `economyWarnings` update from the fresh dashboard snapshot
- `tomorrowWarnings` surfaces from the most recent settlement

No new persistence layer is needed — all state flows from the existing backend API fetch cycle.

---

## Derived Calculation Helpers

All core math lives in `useEconomyState.ts` (`deriveGameplayEconomyState`):
- `deriveDebtPressure(cashOnHand, debtAmount, netWorthAmount)` — debt-to-cash ratio thresholds
- `deriveEconomyStatus(debtPressure, netCashFlow, stress, health)` — composite financial stress
- `deriveWarnings(dashboard, debtPressure, netCashFlow)` — warning string list

`useExpenseDebt.ts` calls `deriveGameplayEconomyState` directly — no math is duplicated. All formatting uses `formatMoney` from `gameplayFormatters.ts`.

---

## Persistence Changes

None. `useExpenseDebt` is a pure derivation hook (no storage reads/writes). All source data flows through the existing API fetch + state lifecycle managed by `GameDashboardPage`.

---

## Naming Integrity Findings

All three touched files checked against patterns: `nnt`, `gnnt`, `NNT`, `GNNT`, `nnt-token`, `walletBalance`, `adCredit`, `token-era`.

| File | Result |
|---|---|
| `useExpenseDebt.ts` | ✅ CLEAN |
| `GameDashboardPage.tsx` | ✅ CLEAN |
| `PlayerStatsBar.tsx` | ✅ CLEAN |

**Out-of-scope notes (not touched this step):**
- `src/hooks/useDebt.tsx` — token-era social debt hook using wallet address and `backend.getDebt(address)`. Used by `TopStatusBar.tsx` for "Posting and voting remain paused" messaging. This is the old NNT/GNNT social credit system. No gameplay impact; cleanup is a separate backlog item.
- `src/hooks/index.tsx` — barrel export still includes `useDebt`. Cleanup deferred.

---

## Validation

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ 0 errors |
| `npx expo lint` | ✅ 0 errors, 12 pre-existing warnings (unchanged) |
| New regressions | None |

---

## Deferred Items

| Item | Reason deferred |
|---|---|
| `economyWarnings` / `tomorrowWarnings` UI surface | Available from `expenseDebt` contract; surfacing to a dedicated warning panel is next-step UI work |
| `useDebt.tsx` token-era cleanup | Social debt system cleanup is a separate step; doesn't affect gameplay |
| Full bills/categories system | Out of scope for this step |
| Collections/default logic | Out of scope for this step |
| Debt payment amount derivation from `biggest_loss` | Requires further analysis of API data shape; deferred |

---

## Summary

- ✅ `ExpenseDebtContract` interface defined — named expense/debt domain contract
- ✅ `useExpenseDebt.ts` created — reuses `deriveGameplayEconomyState`, zero logic duplication
- ✅ Wired into `GameDashboardPage.tsx` alongside `useEconomyState` + `useJobIncome`  
- ✅ `PlayerStatsBar` extended with `Expenses` + conditional `Pressure` tiles
- ✅ Daily progression integration via existing API refresh cycle — no new persistence
- ✅ All safety guards in place (null dashboard, missing values, zero debt, repeated advancement)
- ✅ 0 TS errors · 0 lint errors · same 12 pre-existing warnings
