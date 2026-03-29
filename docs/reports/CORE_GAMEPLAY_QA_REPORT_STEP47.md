# Step 47 — Core Gameplay QA Pass on Real Mobile Flows

Status: Complete

## Flows Tested

1. App launch -> gameplay page initial load
2. Gameplay dashboard render -> stats, warnings, and action hub visibility
3. Action preview -> execute action -> refresh summaries
4. End day -> review settled state -> start next day
5. Mid-day reload / modal close / reopen behavior
6. Settings screen interaction on mobile text inputs
7. Blocked action feedback and action list rendering

## Bugs / Issues Found

1. Session day key was inconsistent across flows
- `useDailySession` persistence was keyed by the gameplay session day, but `GameDashboardPage` initialized the session from API `as_of_date` values while `handleStartNextDay` reset it using the numeric game day.
- This could cause wrong-state restoration after reloads or after starting the next day.

2. Previous end-of-day data leaked into active-day summaries
- `useEconomyState`, `useExpenseDebt`, and `useJobIncome` always received `eodState.data`, even when the player had already started a new day.
- Result: player-facing summaries could still show yesterday's income/expense/cash-flow data during an active day.

3. Action feedback could be overwritten immediately after execution
- `handleExecuteSelectedAction` set a clear success message, then `refreshAfterAction` could replace it with progression or commitment feedback.
- Result: the user could lose the direct explanation of what their action just did.

4. Stale action preview results could land after close or action-switch
- The preview request was async, but closing the modal or opening another action did not invalidate the in-flight request.
- Result: stale preview payloads or errors could appear for the wrong action.

5. Preview state was not fully cleared on close
- Closing the modal only hid it.
- Result: stale selected action / guard / payload state could persist longer than intended.

6. Action list keys were not unique enough
- `ActionHubPanel` keyed rows by section title + action key only.
- If the backend returned repeated actions with the same action key in one section, React could reuse the wrong row.

7. Action preview button tap target was undersized for mobile
- The button used compact padding and no explicit minimum height.
- Result: weaker tap reliability on smaller screens.

8. Settings inputs were not fully mobile-safe
- Settings `ScrollView` did not persist taps cleanly with the keyboard up.
- Admin token was visible in plain text.
- URL input lacked mobile keyboard hints.

## Fixes Applied

### Gameplay flow / state consistency

Updated [GameDashboardPage.tsx](C:/GoldPenny/goldpenny-backend/PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx) to:
- use a canonical gameplay session key: `day:${currentGameDay}`
- initialize daily session state from `currentGameDay` rather than API dates
- pass end-of-day data into summary hooks only when `dailySession.sessionStatus === 'ended'`

Impact:
- reload/start-next-day flow now uses one consistent source of truth
- active-day summaries no longer show stale prior-day settlement values

### Action feedback preservation

Updated [GameDashboardPage.tsx](C:/GoldPenny/goldpenny-backend/PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx) so `refreshAfterAction` now returns follow-up feedback instead of writing directly into the shared feedback banner.

Impact:
- the direct action result remains visible
- progression / commitment follow-up can still be appended without replacing the main message

### Preview safety and ordering

Updated [GameDashboardPage.tsx](C:/GoldPenny/goldpenny-backend/PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx) to add:
- `previewRequestIdRef` for invalidating stale in-flight preview responses
- `resetPreviewState()` to fully clear preview state
- `closePreview()` to centralize modal close behavior and prevent close while action execution is active

Impact:
- stale preview payloads no longer apply after modal close or action switch
- modal state is reset cleanly between actions

### Action list rendering

Updated [ActionHubPanel.tsx](C:/GoldPenny/goldpenny-backend/PFT/pft-expo/src/components/gameplay/ActionHubPanel.tsx) to make action row keys unique with an index suffix.

Impact:
- repeated action keys no longer risk row reuse/render mismatches

### Mobile interaction improvements

Updated [ActionCard.tsx](C:/GoldPenny/goldpenny-backend/PFT/pft-expo/src/components/gameplay/ActionCard.tsx) to raise the preview button to a 44px minimum tap target and center the content.

Updated [settings.tsx](C:/GoldPenny/goldpenny-backend/PFT/pft-expo/app/(tabs)/settings.tsx) to:
- use `keyboardShouldPersistTaps="handled"`
- use URL keyboard / autocomplete hints for backend override input
- hide admin token with `secureTextEntry`
- disable autocomplete for admin token and address fields

Impact:
- better mobile tap reliability
- cleaner keyboard behavior in settings
- safer handling of admin token input

## Mobile UX Issues Fixed

1. Preview button tap target too small
2. Settings keyboard interaction could feel sticky while tapping controls
3. Backend URL field lacked mobile URL keyboard hinting
4. Admin token field displayed sensitive value in plain text

## Persistence / State Issues Fixed

1. Canonical session day key mismatch between reload flow and next-day flow
2. Active-day UI showing prior-day settlement summaries
3. Stale preview requests updating state after the modal lifecycle moved on
4. Preview close not resetting selected state fully

## Naming Integrity Findings

Touched files scanned for:
- `nnt-token`
- `NNT`
- `GNNT`
- `nnt_`
- `nnt-expo`
- token-era naming leftovers
- old UI naming leakage

Result: clean in all touched files.

## Validation Results

1. `npx tsc --noEmit`: passed with 0 errors
2. `npx expo lint`: passed with 0 errors, same 12 pre-existing warnings outside touched files
3. Targeted smoke-check reasoning completed for:
- action preview -> execute flow
- end-day -> next-day flow
- active-day summary consistency
- modal close / reopen behavior
- settings input behavior on mobile

## Remaining Known Issues

1. Expo lint still has 12 unrelated pre-existing warnings outside this step's touched files.
2. This pass improved mobile readiness by code inspection and flow hardening, but it did not run a live device simulator session inside the workspace.
3. Backend endpoints still need their own server-side idempotency protections; this step only hardened the client flow.
