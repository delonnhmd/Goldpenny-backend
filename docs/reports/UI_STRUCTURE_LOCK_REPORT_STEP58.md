# UI Structure Lock Report - Step 58

## Objective
Lock the gameplay screen into a permanent portrait-first structure for one-hand use without changing canonical gameplay logic.

## Outcome
Step 58 is complete.

The gameplay screen now follows a fixed three-layer hierarchy:
1. Context: Daily Brief
2. Player State: Player Snapshot
3. Action Zone: thumb dock plus compact primary action surfaces

Everything outside that loop is now explicitly secondary and collapsible.

## Structural Decisions Locked

### Persistent / top-of-scroll sections
- `daily_brief`
  - Rendered as the first primary card.
  - Remains the top context surface for headline, opportunity, and risk.
- `player_stats`
  - Rendered immediately after Daily Brief.
  - Remains the persistent player-state snapshot.

### Action Zone surfaces
- `ThumbReachActionDock`
  - Remains persistent in the footer on mobile.
  - Primary row: Work, End Day / Start Next Day.
  - Secondary row: Business, Recovery, Stocks, Jobs.
- `action_hub`
  - Kept in the primary scroll region.
  - Default-expanded on mobile.
- `business_operations`
  - Kept in the primary scroll region.
  - Collapsible on mobile.
  - Opens from the dock's Business action when the player has no active business lane to run immediately.
- `stock_market`
  - Kept in the primary scroll region.
  - Collapsible on mobile.
- `random_event`
  - Stays in the primary region only when an event is active.

### Secondary / collapsible groups
- `economy_overview`
  - `market_overview`
  - `price_trends`
  - `commute_pressure`
  - `housing_tradeoff`
  - `economy_explainer`
  - `future_teasers`
  - `supply_chain_story`
- `business_insights`
  - `business_margins`
  - `business_plan`
- `planning_commitment`
  - `strategic_recommendation`
  - `strategic_planning`
  - `debt_growth`
  - `recovery_vs_push`
  - `future_preparation`
  - commitment cards and history
- `progression`
  - progression summary
  - daily goals
  - streaks
  - weekly missions
  - weekly summary
- `world_memory`
  - world narrative
  - local pressure
  - pattern insights
  - player patterns
  - region memory

## Code Changes
- Locked `src/lib/ui_layout_config.ts` to the permanent portrait hierarchy.
- Reduced `PRIMARY_SECTION_KEYS` to:
  - `daily_brief`
  - `player_stats`
  - `action_hub`
- Moved `strategic_recommendation` into the `planning_commitment` secondary group.
- Added `strategic_recommendation` to `hideByDefault` so it cannot render as a competing primary surface.
- Updated `GameDashboardPage.tsx` so:
  - `action_hub` defaults to expanded on mobile.
  - mobile bottom navigation targets the locked layers directly:
    - `Brief` scrolls to Daily Brief
    - `Actions` opens and scrolls to Action Hub
    - `Progress` expands and scrolls to Progression
    - `Insights` expands and scrolls to Economy Overview
    - `Account` routes to the account screen
  - section dividers now make the hierarchy legible:
    - `Action Zone`
    - `Deep Dives`
  - Strategy Recommendation no longer renders as a standalone primary card.
  - Strategy Recommendation now renders inside Planning + Commitment.

## Layout-Level Dead Code Removed
Deleted unused components/wrappers confirmed to have no active source references:
- `src/components/layout/MobileTabShell.tsx`
- `src/components/gameplay/FirstSessionSummaryCard.tsx`
- `src/components/gameplay/OnboardingUnlockPreviewCard.tsx`
- `src/components/gameplay/OnboardingProgressCard.tsx`
- `src/components/gameplay/OnboardingCoachmark.tsx`
- `src/components/gameplay/PlayerStateGrid.tsx`
- `src/components/gameplay/RiskOpportunityPanel.tsx`

Also removed stale Expo ESLint cache residue:
- `.expo/cache/eslint/.cache_v42i1o`

## Naming Integrity Check
Touched names now align with the locked layout roles:
- `Daily Brief` = context layer
- `Player Snapshot` = player-state layer
- `Action Zone` = immediate daily loop
- `Deep Dives` = secondary/collapsible analysis area
- `Planning + Commitment` now owns Strategy Recommendation

No new ambiguous parallel layout surfaces remain in the gameplay page.

## Validation
- `yarn typecheck`
  - Passed
- `yarn lint`
  - Passed with 6 pre-existing warnings, 0 errors

Pre-existing warnings remain in:
- `src/lib/api/progression.ts`
- `src/types/consumerBorrowing.ts`
- `src/types/financialSurvival.ts`

Step 58 introduced no new lint warnings.

## Manual Structure Review Summary
Terminal-side review confirms the portrait loop is now easier to parse in under 3 seconds:
1. Read the brief
2. Check player state
3. Act from the dock / action zone
4. Open deeper analysis only when needed

A final on-device UX pass is still advisable for thumb reach, spacing, and fold behavior, but the structural system is now locked in code.

## Conclusion
Step 58 is complete and ready for the next phase.

Core gameplay logic remains untouched. The gameplay screen now has a single, non-competing portrait layout system with clear persistent, primary, and secondary roles.
