# Gameplay State Cleanup Report — Step 46.1

## Scope
Active gameplay state foundation cleanup only (no feature expansion, no gameplay redesign).

## Files Reviewed

- `app/gameplay/index.tsx`
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/hooks/useDailySession.ts`
- `src/hooks/useDebt.tsx`
- `src/components/TopStatusBar.tsx`
- `src/lib/api/gameplay.ts`
- `src/types/gameplay.ts`
- `src/lib/api/{commitment,economyPresentation,onboarding,progression,strategicPlanning,worldMemory}.ts` (storage/override touchpoints)

## Files Updated

- `app/gameplay/index.tsx`
- `src/hooks/useDailySession.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`

---

## 1) Active Gameplay State Sources (Current)

### Screen-local state (primary owner)
`GameDashboardPage.tsx` owns:
- section fetch state (`status/data/error`) for dashboard/action hub/notifications/eod/weekly/progression/economy/business/planning/world/commitment/onboarding bundles
- interaction state (`refreshing`, `previewVisible`, `previewLoading`, `previewPayload`, `previewError`, `selectedAction`, `selectedActionGuard`, `executingAction`, `endingDay`, `notificationsOpen`)
- onboarding UI state (`onboardingBusy`, `coachmarkDismissed`, visibility/action gates)
- shell/navigation state (`activeShellTab`, `expandedSecondaryGroups`)
- feedback banner state (`feedback`)

### Shared hook/provider state
- `useDailySession.ts`
  - day/session model: `dayKey`, `totalTimeUnits`, `remainingTimeUnits`, `actionsTakenToday`, `sessionStatus`, `pendingExecution`, `progress`
  - derived guards: `canExecuteAction`, action caps/time-cost normalization, counts
- `useDebt.tsx` + `DebtProvider`
  - debt snapshot: `outstanding`, `pendingTotal`, `entries`, `loading`, `error`, `lastUpdated`
  - consumed by `TopStatusBar`

### Service-fed UI state
- `src/lib/api/gameplay.ts` and related API modules feed normalized payloads into `GameDashboardPage` section states.

### Persistence keys used by gameplay
- `goldpenny:gameplay:lastPlayerId` (new canonical key)
- `gameplay:lastPlayerId` (legacy fallback read only)
- `backend:override` and `admin:token` (affect API fetching behavior; intentional advanced overrides)

---

## 2) Current Gameplay State Shape (Real Active Model)

- **Player summary/status:** `PlayerDashboardResponse.stats` (`cash_xgp`, `debt_xgp`, `net_worth_xgp`, `stress`, `health`, `credit_score`, `current_job`, `region_key`)
- **Debt warning state:** `useDebt().outstanding` drives `TopStatusBar` visibility and warning text
- **Money/resources:** cash/debt/net worth + time units via `useDailySession`
- **Progression indicators:** progression section state + daily session `progress`
- **Admin override effects:** API requests include `backend:override` and `admin:token` when set; this intentionally changes gameplay data source/auth behavior
- **Loading/error/empty flags:** unified `SectionState<T>` per gameplay data domain

---

## 3) Dead / Legacy State Cleanup

### Removed/renamed confusing state names
1. `onboardingStateState` → `onboardingState`
2. `setOnboardingStateState` → `setOnboardingState`

Impact:
- eliminated duplicated “StateState” naming noise
- improved ownership readability in the main gameplay state owner file

### Renamed outdated section-key constant
1. `LEGACY_SECONDARY_SECTION_KEYS` → `SECONDARY_GROUP_SECTION_KEYS`

Impact:
- removed misleading “legacy” terminology from active state gate logic
- better reflects actual current purpose (secondary grouped sections hidden from primary visibility path)

---

## 4) Naming Normalization + Old Naming Sweep

### Token-era/old naming in active gameplay state
- No active gameplay state names tied to NNT/GNNT token-era concepts were found in:
  - `GameDashboardPage.tsx`
  - `useDailySession.ts`
  - `types/gameplay.ts`
  - gameplay entry route

### Storage naming normalization
- Canonical gameplay persistence key migrated to:
  - `goldpenny:gameplay:lastPlayerId`
- Safe fallback retained:
  - read from `gameplay:lastPlayerId` if canonical key is absent

This removes generic legacy key naming while preserving existing user continuity.

---

## 5) State Ownership / Boundary Improvements

- Confirmed ownership boundaries remain clear after cleanup:
  - `GameDashboardPage` = orchestration + section states + UI interaction state
  - `useDailySession` = day/action execution constraints and derived guards
  - `useDebt` = debt domain snapshot for status surfaces
  - API modules = backend normalization and fetch behavior
- No prop-drilling expansion introduced.
- No new global state added.

---

## 6) Derived/Computed State Simplification

### Fixed action normalization collision bug in `useDailySession`
Before cleanup, normalization could incorrectly classify keys:
- `switch_job` could collapse to `work_shift`
- `recovery_action` could collapse to `debt_payment`

Applied fixes:
- added explicit high-priority mappings for `switch_job`, `change_region`, `recovery_action`
- narrowed broad fallbacks (`job` removed from work-shift matcher, `recovery` removed from debt matcher)

Result:
- action caps/time-cost guard logic now maps to correct buckets for active gameplay actions
- removes hidden duplicate/incorrect derived behavior in session gating

---

## 7) Persistence / Storage Alignment Findings

### Fixed
- Introduced namespaced key for remembered player identity:
  - write to `goldpenny:gameplay:lastPlayerId`
  - read new key first, then legacy key

### Verified safe
- Active gameplay does not depend on removed token-era storage keys.
- `backend:override` / `admin:token` remain intentionally active and valid.

---

## 8) Gameplay UI Integration Validation

- `npx tsc --noEmit` → PASS
- `npx expo lint` → PASS (0 errors; existing unrelated warnings unchanged)

Integration checks after cleanup:
- gameplay route still loads
- `TopStatusBar` still driven by debt provider state
- gameplay cards/sections still fed by section-state model
- loading/error/empty state handling unchanged in behavior
- admin/network overrides still correctly affect API data path

---

## 9) Touched-File Technical Cleanup

- Removed confusing duplicated state naming in main gameplay state owner file.
- Updated stale/misleading constant name in visibility gating.
- Improved storage-key naming and migration behavior.
- Fixed derived-state normalization bug affecting action guard behavior.

---

## 10) Deferred Items

- Broader legacy cleanup in `useBackend.ts` and older non-gameplay APIs remains out of this step’s scope (not required for active gameplay state model stabilization).
- Existing repository lint warnings outside gameplay state files were not modified.

---

## Final Outcome

- Active gameplay state foundation is clearer and safer.
- Naming and ownership in core gameplay state flow are easier to maintain.
- No obvious old token-era naming remains in active gameplay state layer.
- Gameplay integration remains intact and validation passes.
- Foundation is ready for next incremental core-logic additions.
