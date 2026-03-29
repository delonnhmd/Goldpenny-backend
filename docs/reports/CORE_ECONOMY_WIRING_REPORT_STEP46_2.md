# Core Economy Wiring Report — Step 46.2

## Files Reviewed

- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/components/gameplay/PlayerStatsBar.tsx`
- `src/lib/uiSummaryFormatters.ts`
- `src/hooks/useDailySession.ts`
- `src/lib/gameplayFormatters.ts`
- `src/components/gameplay/SectionSummaryRow.tsx`
- `package.json`

## Files Updated

- `src/types/economy.ts`
- `src/hooks/useEconomyState.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/components/gameplay/PlayerStatsBar.tsx`

## Economy State Shape Introduced

Created a dedicated gameplay economy model in `src/types/economy.ts`:

- `cashOnHand`
- `incomeAmount`
- `expenseAmount`
- `debtAmount`
- `netWorthAmount`
- `netCashFlow`
- `debtPressure`
- `economyStatus`
- `economyWarnings`
- `cashFlowLabel`
- `statusLabel`
- `summaryLine`

This is now the explicit, extendable economy state shape for the active Gold Penny gameplay flow.

## Central Economy Source of Truth

Added `src/hooks/useEconomyState.ts`.

This hook now centralizes economy derivation from the active gameplay inputs:
- `PlayerDashboardResponse`
- `EndOfDaySummaryResponse`

It is now responsible for:
- debt pressure thresholds
- economy status classification
- economy warnings
- cash-flow formatting
- player snapshot economy summary text

This removes the need to compute raw economy summaries ad hoc inside gameplay UI components.

## Derived Calculations Centralized

Moved the following derived economy logic into `useEconomyState`:

- `debtPressure`
  - based on cash-on-hand, debt amount, and net worth
- `economyStatus`
  - based on debt pressure, net cash flow, stress, and health
- `economyWarnings`
  - based on debt pressure, net cash flow, and top dashboard risks
- `cashFlowLabel`
  - centralized display-safe formatting
- `summaryLine`
  - single player-economy summary string for the snapshot section

## Gameplay Integration Changes

### `GameDashboardPage.tsx`
Integrated the new hook:
- `const economyState = useEconomyState(dashboardState.data, eodState.data);`

Used economy state in the active gameplay UI:
- Player Snapshot summary now uses `economyState.summaryLine`
- Player Snapshot status chip now uses `economyState.statusLabel`
- `PlayerStatsBar` now receives `economy={economyState}`

### `PlayerStatsBar.tsx`
Updated to consume centralized economy state for:
- cash
- debt
- net worth
- cash flow tile

This removes duplicated money-state interpretation from the component and keeps it focused on presentation.

## Additional Runtime Fixes Made

### Fixed broken daily brief summary wiring
`GameDashboardPage.tsx` previously interpolated full `top_risks[0]` / `top_opportunities[0]` objects into the summary string, which would produce `[object Object]`.

Fixed by adding a proper `describeSignalItem(...)` helper that reads `title` / `description` safely.

## Old Naming / Token-Era Leakage Check

Checked all touched files for active/runtime-relevant leakage tied to:
- `nnt-token`
- `UI`
- `NNT`
- `GNNT`
- old token-era wallet/balance concepts

Result:
- No old token-era naming remains in touched economy wiring files.
- No token-era balance concepts were reintroduced into gameplay economy state.

## Persistence / Storage Changes

- No new economy persistence keys introduced.
- No legacy-style storage keys added.
- Economy state remains derived from active gameplay payloads rather than persisted locally.

## Validation Results

### TypeScript
- `npx tsc --noEmit` → PASS

### Lint
- `npx expo lint` → PASS (0 errors)
- Existing unrelated warnings remain elsewhere in the repo and were not changed in this step.

### Tests
- No dedicated Expo app test script is configured in `package.json`.
- No relevant app-side tests were available to run for this step.

### Quick Gameplay Route Sanity
Verified the new economy state is wired into the active gameplay route:
- `useEconomyState` imported and used in `GameDashboardPage.tsx`
- Player Snapshot receives `summary={statsSummary}` sourced from economy state
- Player Snapshot receives `statusLabel={economyState.statusLabel}`
- `PlayerStatsBar` receives `economy={economyState}`

## Deferred Issues

- The broader non-gameplay legacy cleanup in `useBackend.ts` remains out of scope for this step.
- Economy state currently derives from dashboard + end-of-day data only; future systems can extend this shape once income/expense engines become richer.
- TopStatusBar still intentionally uses debt-provider lock state rather than the gameplay economy model, to avoid mixing operational lock state with economy presentation.

## Final Outcome

- Active gameplay now has a clear central economy state layer.
- Economy naming is explicit and aligned with Gold Penny intent.
- Economy-derived labels and warnings are centralized instead of scattered.
- Gameplay consumes economy data cleanly through one source of truth.
- No obvious old token-era naming remains in touched economy files.
- App remains stable and ready for the next incremental logic step.
