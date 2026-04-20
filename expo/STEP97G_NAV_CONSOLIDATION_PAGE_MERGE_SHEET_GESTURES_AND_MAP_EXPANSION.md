# STEP 97G — Nav Consolidation, Page Merge, Sheet Gestures, and Map Expansion

## Final 5-Tab Structure

Bottom nav now renders exactly five equal-width tabs with `repeat(5, 1fr)` on web and the shared 97E visual treatment:

- `Map` — icon `🗺️`
- `Work` — icon `💼`
- `Business` — icon `🏪`
- `Portfolio` — icon `📈`
- `Life` — icon `❤️`

Token usage:

- Active icon + label: `theme.ui.tab.active` (`#2F6BFF`)
- Inactive icon + label: `theme.ui.tab.inactive` (`#B8C7DB`)
- Nav background: `theme.ui.bg.card` (`#0D1B2E`)
- Top border: `theme.ui.border` (`#24384F`)

Removed standalone tabs/routes:

- `Brief`
- `Dashboard`
- `Wallet`

Redirect compatibility routes kept intentionally:

- `/gameplay/loop/[playerId]/brief` → `/life`
- `/gameplay/loop/[playerId]/dashboard` → `/work`
- `/gameplay/loop/[playerId]/wallet` → `/portfolio`
- `/gameplay/loop/[playerId]/market` → `/portfolio`

## Page Merge Map

### Brief → Life

Life now starts with the old briefing lane and keeps the previous life sub-sections underneath it.

Moved into Life top section:

- `DailyBriefCard` as the new `Today` block
- Opportunity / pressure / next-beat bullets from the briefing feed
- Daily money/time pressure summary in `Daily Pressure & Momentum`
- Settlement-ready state chip and `Open Summary` action

Life structure after merge:

1. `Today` block
2. `Health / mood`
3. `Habits / routine`
4. `Personal events`
5. `Quick Loan`

### Dashboard → Work / Portfolio

Career-related widgets moved to Work:

- Current job
- Shift window
- Salary today
- Payment status
- Job level
- Next salary
- Pay model
- Stress
- Health
- Time left
- Job market / certification panel
- Work action hub + preview modal

Financial widgets moved to Portfolio:

- Cash
- Net cash flow
- Net worth
- Debt
- Debt pressure
- Top capital upside banner
- Top capital pressure banner
- Market overview
- Price trends
- Stock holdings / brokerage lane

Decision note:

- Stress and health stayed in `Work` because they are being shown in a work-readiness / shift-performance context there.
- Daily briefing and personal-survival widgets stayed in `Life`.
- No standalone dashboard screen remains in the gameplay route tree.

## Bottom Sheet Rebuild

Library chosen:

- `@gorhom/bottom-sheet` v5

Snap points:

- `25%` peek
- `55%` mid
- `90%` expanded

Implemented behavior:

- Spring animation via `useBottomSheetSpringConfigs({ stiffness: 300, damping: 30 })`
- Drag handle always visible at top
- Custom handle/header area supports dragging from the handle or header copy
- Pan-down-to-close enabled
- Backdrop press closes the sheet and clears the selected tile
- Opening a new tile snaps the sheet to `55%`
- Inner content uses `BottomSheetScrollView`
- Inner scroll is enabled only at `90%`

Sheet styling:

- Background: `theme.ui.bg.sheet` (`#F5F7FB`)
- Primary text: `theme.ui.text.onLight` (`#0B1523`)
- Secondary text: `theme.ui.text.onLightMuted` (`#4E627D`)
- Handle: token-derived muted blue-gray using the 97E token set

Dismiss rules wired:

- Drag below the lowest snap closes
- Fast downward swipe closes
- Tap outside on the map/backdrop closes
- Back button still clears the selected tile

## Map Expansion

World dimensions:

- Before: `56 × 40` tiles = `896 × 640 px`
- After: `72 × 46` tiles = `1152 × 736 px`

Tile counts:

- Before non-road tiles: `1715`
- After non-road tiles: `2498`
- Rural non-road tiles: `806 → 1102` (`+36.7%`)
- Downtown non-road tiles: `909 → 1396` (`+53.6%`)

Zone notes:

- Rural kept the longer, staggered frontage pattern with lighter density
- Downtown gained tighter east-side verticals plus longer major east-west corridors
- River path now starts off the left edge and exits beyond the right edge so it spans the full width of the expanded world

Pan bounds:

- Clamp rule remains `viewport - (world * scale) - 18` to `18`
- New max-zoom (`scale = 4`) horizontal clamp: `viewportWidth - 4626` to `18`
- New max-zoom (`scale = 4`) vertical clamp: `viewportHeight - 2962` to `18`

Result:

- The map now fills the frame at close zoom with materially more playable land in both zones and no intentional off-world panning.

## Locate-Me Button and Marker

Locate button:

- Placement: bottom-right of map container
- Inset: `16px` from right, `16px` from bottom of the map container
- Size: `38 × 38`
- Radius: `10`
- Background: `theme.ui.action` (`#2F6BFF`)
- Ring: `alpha(theme.ui.action, 0.25)`
- Icon: SVG crosshair using `theme.ui.bg.sheet` (`#F5F7FB`)

Tap behavior:

- Recenters on the current player tile
- If current zoom is in `z1` or `z2`, bumps to `z3` (`1.6` scale)
- Triggers a `600ms` marker pulse

Player marker:

- `14px` circle
- Fill: `theme.ui.action`
- `2px` ring: `theme.ui.bg.sheet`
- Rendered above map tiles and below the detail sheet

## Before / After Notes

No screenshots were captured in-repo for this step, so implementation notes are recorded instead.

Before:

- Seven bottom tabs split related content across `Brief`, `Dashboard`, and `Wallet`
- Map detail overlay used a custom pan responder and could stick open
- Max zoom still framed too much empty world for the amount of visible city content
- No dedicated locate-me control or player marker pulse

After:

- Five-tab nav consolidates the loop into `Map / Work / Business / Portfolio / Life`
- Briefing content lives at the top of Life
- Dashboard metrics are split by meaning into Work and Portfolio
- Slot detail uses a vetted snap-sheet with gesture close and backdrop dismiss
- Expanded world size plus longer river and denser east-side road grid make close zoom feel fuller
- Locate-me control recenters the player and visually confirms position

## Validation

Validation methods run:

- `yarn typecheck`
- `yarn lint`
- `npx expo export --platform web`
- fixed-string route/deeplink sweep for legacy gameplay route targets

Checklist:

- [x] Bottom nav shows exactly 5 tabs: Map, Work, Business, Portfolio, Life.
- [x] `/brief` and `/dashboard` routes redirect, and no in-app navigation call sites still point to them directly.
- [x] Tapping a map slot opens the sheet; the implementation now supports snap-up, drag-down, swipe-close, and outside-tap dismissal through `@gorhom/bottom-sheet`.
- [x] At max zoom, the map uses the expanded `72 × 46` world with more rural and downtown tiles and updated clamp bounds.
- [x] Locate-me button is bottom-right on the map, recenters on the player, and pulses the marker.

Known verification note:

- Browser export and static validation passed. Live manual gesture QA was not captured in this repo step, so a quick interactive smoke pass is still recommended after merge.
