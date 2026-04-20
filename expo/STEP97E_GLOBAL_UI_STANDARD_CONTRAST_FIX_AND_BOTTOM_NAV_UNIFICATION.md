# STEP 97E — Global UI Standard, Contrast Fix, Bottom Nav Unification

## Token Table

| Token | Value |
| --- | --- |
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

Source of truth: [`src/theme/tokens.ts`](</C:/GoldPenny/goldpenny-backend/expo/src/theme/tokens.ts>)

## Shared System Updates

- Added one global token source in [`src/theme/tokens.ts`](</C:/GoldPenny/goldpenny-backend/expo/src/theme/tokens.ts>) and remapped the legacy `theme.color` / `theme.gameUi` compatibility layer in [`src/design/theme.ts`](</C:/GoldPenny/goldpenny-backend/expo/src/design/theme.ts>) so existing screens consume the same palette.
- Replaced the old card surface variants with a single semantic card primitive in [`src/components/ui/Card.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/Card.tsx>) and made [`SurfaceCard.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/SurfaceCard.tsx>) a compatibility wrapper.
- Replaced the old badge/status chip variants with one chip system in [`src/components/ui/Chip.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/Chip.tsx>) and routed [`Badge.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/Badge.tsx>) / [`StatusChip.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/StatusChip.tsx>) through it.
- Normalized button styles in [`PrimaryButton.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/PrimaryButton.tsx>) and [`SecondaryButton.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/ui/SecondaryButton.tsx>) to the 97E primary / secondary / destructive set.
- Extracted the shared icon+label gameplay nav into [`src/components/layout/AppBottomNav.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/layout/AppBottomNav.tsx>) and centralized the gameplay tab config in [`src/features/gameplayLoop/navigation.ts`](</C:/GoldPenny/goldpenny-backend/expo/src/features/gameplayLoop/navigation.ts>).
- Updated the gameplay scaffold and map screen to use the same nav component:
  - [`src/features/gameplayLoop/GameplayLoopScaffold.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx>)
  - [`src/features/gameplayLoop/screens/MapDashboardScreen.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx>)
- Re-enabled the dedicated Work route and added a Wallet alias route:
  - [`app/gameplay/loop/[playerId]/work.tsx`](</C:/GoldPenny/goldpenny-backend/expo/app/gameplay/loop/[playerId]/work.tsx>)
  - [`app/gameplay/loop/[playerId]/wallet.tsx`](</C:/GoldPenny/goldpenny-backend/expo/app/gameplay/loop/[playerId]/wallet.tsx>)
- Added the build guard in [`scripts/audit-ui-colors.js`](</C:/GoldPenny/goldpenny-backend/expo/scripts/audit-ui-colors.js>) and wired it into `yarn typecheck` / `yarn lint`.

## Bottom Nav Standard

Shared gameplay tab structure now uses the same icon+label treatment everywhere it is mounted:

| Route key | Label | Icon |
| --- | --- | --- |
| `map` | `Map` | `map-outline` |
| `brief` | `Brief` | `file-document-outline` |
| `dashboard` | `Dashboard` | `view-dashboard-outline` |
| `work` | `Work` | `briefcase-outline` |
| `business` | `Business` | `storefront-outline` |
| `market` / `wallet` | `Wallet` | `wallet-outline` |
| `life` | `Life` | `heart-outline` |

Active state:
- icon + label = `tab.active`
- tile fill = action alpha

Inactive state:
- icon + label = `tab.inactive`

Nav shell:
- background = `bg.card`
- top border = `border`

## Key Contrast / Card Fixes

### 1. Current Job card

Before:
- full pale green fill
- mixed green-on-green treatment
- state styling was bespoke to the job market list

After:
- same `Card` component as every other gameplay card
- `positive` left rail only, with standard `bg.card` body
- explicit `Current` chip
- readable `text.onDark` / `text.onDarkMuted` copy with semantic accent only where needed

Primary file: [`src/features/gameplayLoop/components/JobMarketPanel.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/features/gameplayLoop/components/JobMarketPanel.tsx>)

### 2. Progression summary card

Before:
- pale blue section block
- low-contrast light background + blue text treatment
- separate styling path from the rest of the UI system

After:
- wrapped in the shared `Card`
- “Suggested Focus” now uses the same `info` card variant instead of a pastel fill
- “Recently Completed” uses the same `positive` card variant
- copy now follows the legal dark-surface text pairings

Primary file: [`src/components/gameplay/ProgressionSummaryCard.tsx`](</C:/GoldPenny/goldpenny-backend/expo/src/components/gameplay/ProgressionSummaryCard.tsx>)

## Contrast Pass Coverage

The 97E pass also normalized legacy hardcoded colors across gameplay and supporting UI, including:

- Job Market and Career Progression
- Dashboard stat and signal surfaces
- Economy chips / price trend pills
- Business operation cards
- Map overlay sheet / map HUD support surfaces
- Auth and soft-launch sheets
- Shared motion overlays and loading states

All remaining source files under `src/` and `app/` now resolve color through tokens or token-derived `alpha(...)` values. Literal hex / rgba / hsla values are blocked outside the token file.

## Validation Checklist

- [x] All text now resolves to legal dark-surface or light-sheet pairings.
- [x] One card system is in place via `Card` / `SurfaceCard`.
- [x] One chip system is in place via `Chip` / `Badge` / `StatusChip`.
- [x] One bottom nav system is in place via `AppBottomNav`.
- [x] No stray hex values remain in `src/` or `app/` outside `src/theme/tokens.ts`.

## Verification Notes

- `yarn typecheck` passes, including the UI color audit.
- `yarn lint` passes with existing unrelated warnings only; no 97E errors remain.
- The audit is enforced in:
  - `yarn typecheck`
  - `yarn lint`
