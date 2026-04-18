# STEP97B - App-Wide Premium UI Redesign Based On Map Style

## Goal

Bring the rest of the gameplay app up to the new map screen standard so the product feels like one cohesive premium game UI instead of one strong map page plus several utility-style screens.

## Shared visual system extracted from the map page

### Core system updates

- Dark premium base palette moved into shared design tokens.
- Rounded, elevated card language standardized through `SurfaceCard`.
- Premium cyan/teal, blue, green, amber, and red accents standardized for action, state, growth, warning, and pressure.
- Buttons updated to map-aligned dark/cyan primary and dark-glass secondary treatment.
- Top bar updated to the same dark premium shell direction.
- Bottom nav updated to follow the map page dark bar + active glow treatment.
- Sticky footer action bar updated to the same dark shell.
- Badge/chip treatment updated to premium dark chips instead of pale utility pills.

### Status/navigation extraction

- `PlayerStatusBar` is now reused in `GameplayLoopScaffold`, so the map-style top status bar carries across gameplay screens.
- `GameplayLoopScaffold` now injects page identity hero cards and light fade transitions so screens feel related to the map visually and motion-wise.

## Screens redesigned

### Shared gameplay pages upgraded through scaffold/system

- Brief
- Dashboard
- Work
- Business
- Life
- Market
- Summary and other scaffolded gameplay views also inherit the upgraded system

### Page identity layer added

- Brief: daily intelligence / narrative / settlement framing
- Dashboard: command-center framing
- Work: career progression / shift lane framing
- Business: asset and operations framing
- Life: routine / survival framing
- Market: capital and signal framing

## Components updated

### Layout/system

- `expo/src/design/tokens.ts`
- `expo/src/components/layout/AppShell.tsx`
- `expo/src/components/layout/TopBar.tsx`
- `expo/src/components/layout/BottomNav.tsx`
- `expo/src/components/layout/BottomActionBar.tsx`
- `expo/src/components/ui/SurfaceCard.tsx`
- `expo/src/components/ui/PrimaryButton.tsx`
- `expo/src/components/ui/SecondaryButton.tsx`
- `expo/src/components/ui/Badge.tsx`
- `expo/src/components/ui/TextButton.tsx`
- `expo/src/components/ui/ProgressMeter.tsx`
- `expo/src/components/ui/ErrorStateView.tsx`
- `expo/src/components/ui/LoadingSkeleton.tsx`

### Gameplay scaffold/system

- `expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- `expo/src/features/gameplayLoop/components/GameplayUIParts.tsx`

### Major gameplay cards upgraded from old utility look

- `expo/src/components/gameplay/DailyBriefCard.tsx`
- `expo/src/components/gameplay/ActionCard.tsx`
- `expo/src/components/gameplay/BusinessOperationsCard.tsx`
- `expo/src/components/gameplay/MarketOverviewCard.tsx`
- `expo/src/components/gameplay/PriceTrendsCard.tsx`
- `expo/src/components/gameplay/StockMarketCard.tsx`
- `expo/src/features/gameplayLoop/components/JobMarketPanel.tsx`

## Before / after notes

### Before

- Many screens still used pale surfaces, white cards, and admin-like spacing.
- Buttons often read like plain submit controls.
- Status rows often felt like spreadsheet output.
- Screen-to-screen transitions were flatter and more abrupt.
- The map had stronger identity than the rest of the product.

### After

- Gameplay screens now share the map’s dark premium shell and accent logic.
- Cards feel more like game panels than dashboard widgets.
- Stat surfaces have stronger hierarchy and more emphasis.
- CTAs read more like meaningful actions.
- Each major gameplay page has its own identity without breaking system consistency.
- Light fade-in movement improves continuity between tabs/pages.

## Consistency rules

- Keep `PlayerStatusBar` as the gameplay top-status standard.
- Keep bottom nav in the map’s dark premium direction.
- Use dark surfaces with subtle borders instead of white utility panels.
- Use cyan/teal for active interaction and selected emphasis.
- Use green for cash/growth/profit, red for debt/pressure/danger, amber for warning/pending, blue for info/navigation.
- Prefer chips, grouped values, and premium stat cards over raw table-like rows.
- Preserve readability and avoid decorative noise.

## Validation results

### Verified

- `npm run typecheck` passed in `goldpenny-backend/expo`.
- Shared gameplay scaffold now applies:
  - map-style top status bar
  - page identity hero block
  - light fade-in transition
- Shared buttons/cards/navigation were upgraded to the new premium system.
- Major Brief, Work, Business, Life, Market, and Dashboard surfaces now inherit the same design language through shared components.

### Pending manual UI review

- A. Brief page should be checked visually for narrative feel on device sizes
- B. Dashboard should be reviewed for any remaining isolated light subcomponents
- C. Business should be reviewed on real data for asset-management feel
- D. Work / Life / Market should be reviewed for balance between readability and premium styling
- E. Final consistency pass can still catch older one-off gameplay cards outside the main upgraded set

## Outcome

The app now has a shared premium gameplay shell based on the map screen rather than a split identity between one polished map and a set of utility pages.
