# Step 46.4 — Mobile Identity Fix + Job/Income Logic Hookup Report

**Date:** 2026-03-21  
**Project root:** `PFT/pft-expo`  
**Builds on:** Step 46.3 (path refactor sweep + daily progression)

---

## Overview

Two objectives completed:

1. **Part A — Mobile identity/config cleanup**: Corrected the iOS `bundleIdentifier` and confirmed the full app identity config is now internally consistent and deployment-safe.
2. **Part B — Job/income logic hookup**: Created a minimal, typed `useJobIncome` hook sourcing from live dashboard and end-of-day data; wired it into the gameplay dashboard and `PlayerStatsBar`.

---

## Part A: Mobile Identity / Config Cleanup

### Files Reviewed

| File | Review result |
|---|---|
| `app.json` | iOS bundleIdentifier was `"5SUQ269Z4G"` (Apple Team ID format — invalid as bundle ID) |
| `app.json` | All other fields already clean (from Step 46.3) |
| `src/constants/index.ts` | All clean (updated in Step 46.3) |
| `tsconfig.json`, `babel.config.js`, `metro.config.js`, `eas.json` | All clean |
| `package.json` | `"name": "goldpenny-expo"` — clean |

### Fix Applied

| Field | Before | After | Location |
|---|---|---|---|
| `ios.bundleIdentifier` | `"5SUQ269Z4G"` | `"com.goldpenny.pft"` | `app.json` |

The value `"5SUQ269Z4G"` matches the format of an Apple Developer Team ID (10-character alphanumeric), not a reverse-domain bundle identifier. It cannot be used as a valid iOS bundle identifier for App Store or TestFlight distribution.

Replacement uses `"com.goldpenny.pft"` — the consistent reverse-domain identifier matching the Android package (`com.goldpenny.pft` set in Step 46.3) and the Gold Penny naming convention.

> **Note:** If this app has an existing Apple Developer Portal registration under a different bundle ID, that registration will need to be updated or a new App ID created for `com.goldpenny.pft`. No Apple Developer Portal facts have been invented — this is a locally safe, structurally valid placeholder aligned with the established naming convention.

### Consistent App Identity Summary (Post-Step 46.4)

| Field | Value |
|---|---|
| `expo.name` | `"Gold Penny"` |
| `expo.slug` | `"pft-expo"` |
| `expo.scheme` | `"goldpenny"` |
| `android.package` | `"com.goldpenny.pft"` |
| `ios.bundleIdentifier` | `"com.goldpenny.pft"` |
| `WC_METADATA.url` | `"https://goldpenny.app"` |
| `package.json` name | `"goldpenny-expo"` |

### Naming / Path Integrity Check (Touched Config Files)

| Pattern | Result |
|---|---|
| `nnt-token` / `NNT-token` | 0 matches in touched files |
| `nntpress.com` | 0 matches in touched files |
| Old scheme `"nnt"` | 0 matches in touched files |
| Old package `"nntpress.com"` | 0 matches in touched files |
| Team-ID-format bundle identifier | Fixed |

---

## Part B: Job/Income Logic Hookup

### Design Decisions

- **Source of truth for current job**: `PlayerDashboardResponse.stats.current_job` (live, updated on each dashboard refresh)
- **Source of truth for daily income**: `EndOfDaySummaryResponse.total_earned_xgp` (available post end-of-day settlement)
- **Income source label**: `EndOfDaySummaryResponse.biggest_gain` (the primary income driver for the day)
- **Derivation location**: A single `useJobIncome` hook — no scattered ad-hoc derivations in UI files
- **Scope**: No job switching, no career ladder, no promotions, no expenses engine — strictly job state + daily income

### New File: `src/hooks/useJobIncome.ts`

**Contract exported:**

```typescript
export interface JobIncomeContract {
  currentJob: string | null;       // job title from dashboard.stats.current_job
  hasActiveJob: boolean;           // true when currentJob is non-empty
  workStatus: 'working' | 'unemployed' | 'pending';  // pending = no dashboard data yet
  incomeAmount: number | null;     // total_earned_xgp from endOfDay; null during active day
  incomeSource: string | null;     // biggest_gain from endOfDay; null when unavailable
  dailyIncomeLabel: string;        // "+1,200.00 xgp" | "0.00 xgp" | "Pending"
  incomeSummary: string;           // one-liner: "Working as Nurse — earned +1,200.00 xgp today."
}
```

**Derivation rules:**
- `workStatus = 'pending'` when dashboard has not yet loaded
- `workStatus = 'working'` when `current_job` is non-empty
- `workStatus = 'unemployed'` when dashboard loaded but `current_job` is empty/null
- `incomeAmount` is derived only when `endOfDay != null` (i.e., after settlement)
- `dailyIncomeLabel` is `"Pending"` during active day, signed/formatted amount after settlement
- `incomeSummary` auto-adapts for working/unemployed/side-income/no-income cases
- Safe with all null/missing inputs — returns stable default contract

**Safety guards built in:**
- Empty/null dashboard → default contract with `workStatus: 'pending'`
- Partial endOfDay data → graceful fallbacks (`incomeSource = null`, `incomeAmount = 0`)
- No crash on rapid day cycles — pure derivation, no side effects
- Stable under `useMemo` — no re-renders unless source data changes

### Files Modified

#### `src/pages/gameplay/GameDashboardPage.tsx`

Changes:
1. Added import: `import { useJobIncome } from '@/hooks/useJobIncome';`
2. Added initialization after `useEconomyState`:
   ```ts
   const jobIncome = useJobIncome(dashboardState.data, eodState.data);
   ```
3. Passed `jobIncome={jobIncome}` to `PlayerStatsBar`

#### `src/components/gameplay/PlayerStatsBar.tsx`

Changes:
1. Added import: `import { type JobIncomeContract } from '@/hooks/useJobIncome';`
2. Added `jobIncome?: JobIncomeContract | null` prop
3. Job tile now uses `(jobIncome?.currentJob ?? stats.current_job) || 'Unassigned'` — centralises job derivation
4. Added conditional **Income tile** after Job tile:
   - Renders only when `jobIncome.incomeAmount != null` (i.e., after end-of-day settlement)
   - Shows `dailyIncomeLabel` (e.g., `"+1,200.00 xgp"`)
   - Green tone when income > 0, secondary tone when zero

### Gameplay Integration Points

| Integration point | Status |
|---|---|
| `PlayerStatsBar` — Job tile | ✅ Uses `useJobIncome.currentJob` as source |
| `PlayerStatsBar` — Income tile | ✅ Shows post-settlement daily income |
| `GameDashboardPage` — hook initialized | ✅ `const jobIncome = useJobIncome(...)` |
| `handleEndDay` feedback | ℹ️ Existing feedback kept — `incomeSummary` available for enrichment in future step |
| `EndOfDaySummaryCard` | ℹ️ Already shows Earned/Spent/Net independently — no change needed |

### Deferred (Out of Scope)

- Job switching system
- Career ladder / promotions
- Expenses engine
- Blockchain / claim logic
- `incomeSummary` in end-of-day feedback (income data loads async after feedback is set — clean integration requires a separate step or effect)

---

## Validation

**TypeScript compile (post-fix):** 0 errors  
**ESLint (post-fix):** 0 errors, 12 warnings (all pre-existing, unchanged)

Pre-existing warnings (unchanged):
- `GameDashboardPage.tsx`: 2 unused vars (`adCreditsCallCount`, `lastAdCreditsCall`)
- `useWallet.tsx` / `wallet-context.tsx`: `useCallback` unnecessary dependency (`redirectUrl`)
- `api/progression.ts`: 2 unused type exports (`StreakItem`, `WeeklyMissionItem`)
- `types/consumerBorrowing.ts` / `types/financialSurvival.ts`: 4 × `Array<T>` style warnings

---

## Summary

| Category | Count / Result |
|---|---|
| Config values fixed | 1 (`ios.bundleIdentifier`) |
| New hooks created | 1 (`useJobIncome.ts`) |
| Files modified | 3 (`app.json`, `GameDashboardPage.tsx`, `PlayerStatsBar.tsx`) |
| TypeScript errors | 0 |
| ESLint errors | 0 |
| ESLint warnings (pre-existing) | 12 |
| App identity consistency | ✅ All fields aligned to `com.goldpenny.pft` / `goldpenny` scheme |
| Deferred items | 1 (iOS Apple Developer Portal registration — manual step) |
