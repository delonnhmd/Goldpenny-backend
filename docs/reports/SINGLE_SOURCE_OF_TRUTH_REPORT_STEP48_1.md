# Step 48.1 Single Source Of Truth Report

## Goal

Lock the active Gold Penny gameplay runtime to a single source of truth for core state so future exploit hardening and action-guard work build on canonical values instead of duplicated or stale ownership.

## Files Reviewed

- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/hooks/useDailySession.ts`
- `src/hooks/useDailyProgression.ts`
- `src/hooks/useEconomyState.ts`
- `src/hooks/useExpenseDebt.ts`
- `src/hooks/useJobIncome.ts`
- `src/hooks/useRandomEvent.ts`
- `src/types/gameplay.ts`
- `src/types/economy.ts`
- `src/types/randomEvent.ts`

## Files Updated

- `src/lib/gameplayRuntimeState.ts` (new)
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/hooks/useDailySession.ts`
- `src/hooks/useEconomyState.ts`
- `src/hooks/useExpenseDebt.ts`
- `src/hooks/useJobIncome.ts`

## Canonical Gameplay State Contract

Created `GameplayCanonicalState` in `src/lib/gameplayRuntimeState.ts`.

Canonical fields now locked in one contract:

- `playerId`
- `currentDay`
- `sessionStatus`
- `cashOnHand`
- `debtAmount`
- `netWorthAmount`
- `stress`
- `health`
- `currentJob`
- `incomeAmount`
- `expenseAmount`
- `netCashFlow`
- `incomeSource`
- `tomorrowWarnings`
- `topRisks`
- `activeEventId`
- `activeEventSourceDay`

Also added state-boundary helpers:

- `resolveSettledEndOfDay(...)`
- `createGameplayCanonicalState(...)`
- `attachGameplayEventState(...)`

This gives the runtime one canonical extraction path from dashboard data, end-of-day data, session status, and active event markers.

## Duplicated State Removed Or Reduced

### 1. Dashboard and end-of-day extraction duplication reduced

Before:
- `useEconomyState`, `useExpenseDebt`, and `useJobIncome` each re-owned raw dashboard / end-of-day extraction work in slightly different ways.
- `GameDashboardPage` also derived `settledEndOfDay` independently and passed mixed raw/derived values into hooks.

After:
- `GameDashboardPage` creates one canonical gameplay state object.
- `useEconomyState`, `useExpenseDebt`, and `useJobIncome` derive from that canonical contract instead of owning raw snapshot extraction themselves.

### 2. Session day ownership tightened

Before:
- `useDailyProgression` owned `currentGameDay`
- `useDailySession` persisted and compared a separate derived string `dayKey`
- `GameDashboardPage` built `day:${currentGameDay}` locally and fed it back into session persistence

After:
- `useDailyProgression.currentGameDay` remains the canonical day owner
- `useDailySession` now persists numeric `currentDay` instead of a derived string key
- `GameDashboardPage` initializes session with the numeric day directly

This removes one avoidable derived-state persistence layer.

### 3. Random event cash input now comes from canonical gameplay state

Before:
- `useRandomEvent` depended on `economyState.cashOnHand`, which was itself already derived

After:
- `useRandomEvent` receives `cashOnHand` from the canonical gameplay state contract

This reduces dependency chaining and makes recovery eligibility depend on one canonical value.

## Derived Helper / Selector Centralization

Centralized selector ownership around the new canonical contract:

- `useEconomyState` now derives from `GameplayCanonicalState`
- `useExpenseDebt` now derives from `GameplayCanonicalState`
- `useJobIncome` now derives from `GameplayCanonicalState`

This means:
- economy summaries
- debt warnings
- financial stress labels
- work status summaries

all now derive from one canonical runtime object instead of re-parsing dashboard and settlement data in multiple places.

## Persistence Alignment Changes

Updated `useDailySession` persistence so new writes store canonical values only:

Before persisted snapshot:
- `dayKey`
- `remainingTimeUnits`
- `actionCounts`
- `sessionStatus`
- `totalTimeUnits`

After persisted snapshot:
- `currentDay`
- `remainingTimeUnits`
- `actionCounts`
- `sessionStatus`
- `totalTimeUnits`

This removes persistence of the derived `dayKey` string and aligns new writes with the canonical numeric day value.

## Local Vs Shared State Boundary

Kept UI-local state local in `GameDashboardPage`:

- preview modal state
- selected action state
- transient execution/loading flags
- expanded section UI state
- notifications drawer visibility
- feedback banners

Kept shared runtime state in proper owners:

- day number in `useDailyProgression`
- daily time/caps/session lifecycle in `useDailySession`
- random event ownership in `useRandomEvent`
- dashboard and settlement snapshots in page data loaders
- derived economy/debt/job selectors from the canonical contract

## Naming Integrity Findings

Touched files were checked for:

- `nnt-token`
- `NNT`
- `GNNT`
- stale token-era naming in runtime state files

Result:
- No active token-era naming remained in touched runtime files after this pass
- No new stale naming was introduced

## Validation Results

- `npx tsc --noEmit` passed
- `npx expo lint` passed with 0 errors and 10 pre-existing warnings

## Runtime Verification Notes

- The refactor preserves the existing gameplay page wiring and action flow
- Derived economy, debt, and income summaries still derive from the same raw dashboard and end-of-day inputs, now through one canonical contract
- Session persistence remains backward-tolerant at runtime for existing storage read failures, and new writes now align to canonical numeric day ownership

I did not run a live simulator/device gameplay session in this environment, so visual runtime verification was not performed here.

## Deferred Items

These were identified but intentionally left for later steps to keep scope tight:

- action blocker ownership still lives partly in `useDailySession.canExecuteAction` and partly in `GameDashboardPage.applySessionBlockers`
- onboarding bundle state is still applied as multiple page-level section states rather than one bundled canonical onboarding owner
- progression feedback still compares before/after snapshots instead of using a dedicated incremental selector layer
- random event recovery option availability is still derived at render time, which is acceptable for now but could be locked further in later exploit-hardening work

## Outcome

The gameplay runtime now has a clearer single source of truth:

- one canonical gameplay state contract feeds the derived economy/debt/job selectors
- the day number is no longer duplicated as a persisted string key
- persistence writes store canonical values instead of a redundant derived identifier
- future Step 48.2 action guard hardening can build on a cleaner ownership model
