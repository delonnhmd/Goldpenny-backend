# One-Hand UX Optimization Report — Step 53

## Goal

Refactor the Gold Penny Expo gameplay UI so the daily loop can be completed comfortably in portrait mode with one hand, keeping the primary actions reachable from the lower portion of the screen.

## Critical Daily Actions Identified

Primary daily actions reviewed for thumb reach:

- Work
- Advance Day / Start Next Day
- Business Operation
- Stock Buy / Sell
- Recovery Action
- Job Switch

## Actions Moved To The Bottom Zone

Implemented a mobile-only thumb dock above the existing bottom navigation.

New lower-zone actions:

- Work
- End Day or Start Next Day
- Run Business or open Business section
- Recover or jump to active event recovery
- Stocks shortcut
- Jobs shortcut

Files involved:

- `src/components/gameplay/ThumbReachActionDock.tsx`
- `src/components/layout/AppShell.tsx`
- `src/components/layout/BottomActionBar.tsx`
- `src/pages/gameplay/GameDashboardPage.tsx`

## UI Structure Changes

### Mobile Footer Action Dock

Added a sticky gameplay footer for mobile that now keeps the daily loop in the thumb zone:

- day state summary
- immediate action feedback
- direct work action
- direct end-day or next-day action
- secondary quick actions for business, recovery, stocks, and jobs

### Top-Heavy Controls Removed From Mobile

The old top day-control card is no longer rendered on mobile.

Result:

- no critical daily action now depends on reaching the upper part of the screen

### First Screenful Reordered

Priority on mobile now favors:

1. Daily Brief
2. Thumb dock actions
3. Player Snapshot
4. Optional sections and deeper planning content

`Daily Brief` now appears ahead of `Player Snapshot`, which better matches the intended play loop.

## Sections Collapsed Or Kept Open

### Collapsed By Default On Mobile

- Action Hub
- Business Operations
- Stock Market
- Action Hub `Available` list
- Action Hub `Blocked` list
- Existing secondary insight groups remained collapsed by default

### Kept Open

- Daily Brief
- Player Snapshot
- Recommended actions inside the Action Hub once expanded
- Random event card when active

## Thumb-Zone Mapping Decisions

### Direct Actions In Footer

- `Work` executes immediately when a valid work action is available; otherwise it opens the Action Hub
- `End Day` / `Start Next Day` stays permanently reachable in the footer
- `Run Business` executes immediately when an active business exists; otherwise it opens the business lane

### Fast Access Shortcuts In Footer

- `Recover` jumps to the active random event recovery flow when relevant, or directly executes the available recovery action when the hub exposes one
- `Stocks` opens the stock lane from the bottom zone rather than forcing upper-screen hunting
- `Jobs` opens the job-switch preview when available, otherwise it opens the Action Hub

### Why This Split Was Chosen

- high-frequency actions are now one tap from the footer
- riskier or context-heavy actions still retain preview or section context where needed
- optional lanes remain reachable without staying expanded all day

## Action Flow Simplification

### Daily Loop Improvement

Common happy path on mobile is now:

1. Open app
2. Read Daily Brief
3. Tap `Work` or `Run Business`
4. Tap `End Day`

That reduces the common loop to the intended short-session path without routing through nested screens.

### Modal Dependency Reduced

Previously, common actions depended on preview-first flows inside the Action Hub.

Now:

- direct work execution is supported from the thumb dock
- direct business execution is supported from the thumb dock
- Action Hub remains available for deeper tradeoff review, but it is no longer the only way to act

## Visual Hierarchy Improvements

- top mobile feedback banner was removed in favor of lower-zone feedback inside the thumb dock
- mobile action surfaces now emphasize a single primary action row plus a secondary utility row
- optional sections no longer dominate the first screenful
- Action Hub now promotes `Recommended` while hiding `Available` and `Blocked` details until requested

## Feedback Speed Improvements

On mobile, action results now surface in the footer dock immediately after execution.

This matters because the user no longer needs to scroll back to the top to confirm results like:

- earnings
- costs
- pressure changes
- stock trade outcome

## Touch Target Quality

Confirmed existing and updated controls use thumb-friendly dimensions:

- primary and secondary shared buttons already use `minHeight: 44`
- stock trade buttons were already increased previously and remain thumb-safe
- new footer controls use shared button primitives and wrapped spacing
- collapsed section headers are tap-friendly and use 44px minimum height

## Safe Area Handling

- footer dock is rendered through the app shell, above the existing bottom nav
- safe-area handling continues through the existing `SafeAreaPage` shell wrapper
- the gameplay screen no longer relies on clipped absolute overlays for its primary footer actions

## Performance / Friction Improvements

Primary UX improvements delivered:

- less vertical scanning for the next move
- less scrolling before action
- less dependence on top-screen controls
- less modal usage for common actions
- faster return loop after action because feedback now appears near the controls

## Validation

Validation performed:

- touched-file diagnostics: clean
- TypeScript: passed (`TS_EXIT=0`)
- Expo lint: passed with `0` errors and `6` pre-existing warnings

Remaining lint warnings are unchanged and outside Step 53 scope:

- `src/lib/api/progression.ts` unused imports
- `src/types/consumerBorrowing.ts` array-style warnings
- `src/types/financialSurvival.ts` array-style warnings

## Remaining UX Risks

- stock buy / sell still requires opening the stock section before picking a trade, so it is improved but not fully one-tap
- job switching still uses preview-first behavior when the action exists, which is safer but slightly slower
- recovery can still require scrolling to the random event card when multiple recovery choices are presented
- I did not perform a real hand-held device test or stopwatch run, so true under-10-second confirmation still needs physical validation

## Outcome

Step 53 materially improved one-hand portrait play:

- the core daily actions are reachable from the bottom zone
- mobile scrolling pressure is lower
- optional sections no longer crowd the first screenful
- feedback lands near the controls instead of at the top of the page
- the gameplay screen now behaves more like a mobile-native daily loop and less like a desktop dashboard compressed into a phone screen