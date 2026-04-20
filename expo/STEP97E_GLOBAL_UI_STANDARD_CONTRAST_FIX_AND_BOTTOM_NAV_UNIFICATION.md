# STEP 97E - Global UI Standard, Contrast Fix, and Bottom Nav Unification

## Final Token Table

| Token | Value |
|---|---|
| `bg.app` | `#07111F` |
| `bg.card` | `#0D1B2E` |
| `bg.cardRaised` | `#13243A` |
| `bg.sheet` | `#F5F7FB` |
| `text.onDark` | `#F5F7FB` |
| `text.onDarkMuted` | `#B8C7DB` |
| `text.onLight` | `#0B1523` |
| `text.onLightMuted` | `#4E627D` |
| `positive` | `#2ECC71` |
| `danger` | `#E74C3C` |
| `warning` | `#F4B942` |
| `action` | `#2F6BFF` |
| `info` | `#33C3FF` |
| `health` | `#FF5D8F` |
| `border` | `#24384F` |
| `tab.active` | `#2F6BFF` |
| `tab.inactive` | `#B8C7DB` |
| `radius.card` | `22` |
| `radius.chip` | `999` |
| `radius.navTile` | `16` |

Source of truth: `src/theme/tokens.ts`

## Components Updated

- Token/theme core:
  - `src/theme/tokens.ts`
  - `src/design/tokens.ts`
  - `src/design/theme.ts`
- Card/chip/button standards:
  - `src/components/ui/Card.tsx`
  - `src/components/ui/Chip.tsx`
  - `src/components/ui/SurfaceCard.tsx`
  - `src/components/ui/Badge.tsx`
  - `src/components/ui/PrimaryButton.tsx`
  - `src/components/ui/SecondaryButton.tsx`
- Shared nav system:
  - `src/components/layout/AppBottomNav.tsx`
  - `src/components/layout/AppShell.tsx`
  - `src/components/layout/BottomNav.tsx` (compat wrapper to `AppBottomNav`)
  - `src/features/gameplayLoop/GameplayLoopScaffold.tsx`
  - `src/features/gameplayLoop/screens/MapDashboardScreen.tsx`
- Contrast and audited gameplay surfaces:
  - `src/features/gameplayLoop/components/GameplayUIParts.tsx`
  - `src/features/gameplayLoop/components/JobMarketPanel.tsx`
  - `src/features/gameplayLoop/components/BusinessMarketPanel.tsx`
  - `src/features/gameplayLoop/screens/DashboardScreen.tsx`
  - `src/components/gameMap/MapDetailSheet.tsx`
  - `src/components/gameMap/PlayerStatusBar.tsx`
  - `src/components/gameMap/StressHealthBars.tsx`
  - `src/components/gameplay/ProgressionSummaryCard.tsx`
  - `src/components/gameplay/ActionCard.tsx`
  - `src/components/gameplay/ActionPreviewModal.tsx`
  - `src/components/gameplay/BusinessOperationsCard.tsx`
  - `src/components/gameplay/DailyBriefCard.tsx`
  - `src/components/gameplay/EndOfDaySummaryCard.tsx`
  - `src/components/gameplay/MarketOverviewCard.tsx`
  - `src/components/gameplay/PriceTrendsCard.tsx`
  - `src/components/gameplay/StockMarketCard.tsx`
  - `src/features/gameplayLoop/screens/CityMapScreen.tsx`
- Formatter tokenization (dynamic color sources):
  - `src/lib/economyPresentationFormatters.ts`
  - `src/lib/gameplayFormatters.ts`
  - `src/lib/commitmentFormatters.ts`
  - `src/lib/worldMemoryFormatters.ts`
  - `src/lib/onboardingFormatters.ts`
  - `src/lib/strategicPlanningFormatters.ts`

## Before / After: Two Failing Cards

### 1) Pale green current-job card

- Before:
  - Current job state in `JobMarketPanel` used a tinted green background (`jobCardCurrent`).
  - Result was low-contrast text and a pastel card that broke the single-card standard.
- After:
  - Job states are now only `current | locked | available`.
  - All states use the same base card surface (`bg.card` + `border` + `radius.card`).
  - `current` is expressed via semantic left accent (`Card variant="positive"`) + `Current` chip.
  - No pastel fill remains.

### 2) Pale blue progression card

- Before:
  - Progression summary blocks used blue/green tinted backgrounds and custom ad hoc palette.
  - Styling was inconsistent with the shared card system.
- After:
  - Progression summary now uses shared `Card` primitives with dark card surfaces.
  - Semantic state uses left accent variants (`info`/`positive`) and chips.
  - Readability moved to legal dark-surface text pairings.

## Bottom Nav Unification

- Implemented one global bottom nav: `AppBottomNav`.
- Mounted through `GameplayLoopScaffold` and map screen integration for:
  - Brief
  - Dashboard
  - Work
  - Business
  - Wallet (market route key)
  - Life
  - Map
- Removed divergence by routing legacy `BottomNav` through `AppBottomNav`.
- Active/inactive icon+label colors now come from `tab.active` / `tab.inactive`.

## Stray Color Enforcement

- Added audit script: `scripts/audit-ui-colors.js`.
- Added npm scripts:
  - `tokens:audit`
  - `lint` now runs token audit first
  - `typecheck` now runs token audit first
- If a hardcoded `#hex` or `rgb/rgba(...)` appears in audited gameplay UI scope, command exits with non-zero.

## Checklist

- [x] All text in audited gameplay UI surfaces is readable against dark/light backgrounds.
- [x] Single card system in place (`Card` with semantic left accent only, no pastel card fills).
- [x] Single chip system in place (`Chip` variants).
- [x] Single bottom nav system in place (`AppBottomNav`).
- [x] No stray hex values in audited gameplay UI code scope (`tokens:audit` passes).
