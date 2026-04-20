# STEP 97F — Map Art Rebuild (Smaller Slots, River, Two Zones, Smoother Zoom)

## Scope Completed
This pass rebuilt the map presentation from a debug-like grid into a layered city view with:
- darker asphalt roads (no white divider stripes),
- smaller tiles and denser slot layout,
- two zone washes (`RURAL`, `DOWNTOWN`),
- a curved diagonal river,
- four zoom levels with aggressive culling,
- render-layer separation for smoother pan/zoom.

Status bar and bottom nav were preserved.

## Root Cause of Drag Slowdown
Primary drag/pan cost came from the map rendering all cell-level detail at once:
- one large tile tree rendered continuously at all zoom levels,
- per-tile decorative sub-elements and labels adding node count,
- no zoom-tier culling for far overview,
- no frame-throttled bridge update path for zoom-side UI state.

## Changes Implemented

### 1) Road Redesign (No White Stripes)
- Removed road stripe sub-elements entirely from tile rendering.
- Roads now render in the static layer as dark asphalt blocks using token-derived dark tones.
- Added subtle curb cue highlight in the same static layer.

Updated file:
- `src/components/gameMap/GameMap.tsx`

### 2) Tile Size + Density Rebuild
- Map grid changed from `30 x 22 @ 32px` to `56 x 40 @ 16px` (roughly half-size tiles).
- Selection remains touch-friendly via nearest-tile hit resolution (not strict floor-cell only).
- Rural tiles use slightly larger/varied visual scales; downtown tiles use tighter/smaller scales.

Updated file:
- `src/components/gameMap/mapData.ts`

### 3) Two-Zone Layout + District Mapping
- Added two zone washes:
  - `RURAL` (top-left region)
  - `DOWNTOWN` (bottom-right region)
- Kept district keys (`heights`, `makers`, `exchange`, `midtown`, `commerce`, `harbor`) for gameplay compatibility, while visually grouping into the two-zone art direction.
- Added zone labels in the label layer with zoom-aware visibility.

Updated files:
- `src/components/gameMap/mapData.ts`
- `src/components/gameMap/GameMap.tsx`

### 4) Curved River + Waterfront Flags
- Added smooth cubic-bezier river geometry across the map diagonal.
- River rendered as a static stroked band plus highlight stroke.
- Added `waterfront: boolean` to `SandboxMapTile` by distance sampling against river curve points.
- Waterfront flag is currently metadata only (future bonus hook), no gameplay bonus logic applied yet.

Updated file:
- `src/components/gameMap/mapData.ts`

### 5) Zoom System (4 Levels)
- Implemented 4 zoom tiers:
  - `z1` far: static world only (zone washes + trunk roads + river), tiles hidden
  - `z2` medium: sampled tile clusters + district labels
  - `z3` close: full tile set (non-road) with semantic states
  - `z4` precise: tile tags and numeric hints for detailed inspection
- Extended zoom-out minimum (`MIN_SCALE = 0.38`) for full-city overview.

Updated file:
- `src/components/gameMap/GameMap.tsx`

### 6) Performance Layering + Throttling
- Split world rendering into three layers:
  - Static layer: zones + roads + river (`Svg`)  
  - Tile layer: semantic lots/slots  
  - Label layer: district + node labels (culled by zoom tier)
- At `z1`, tile layer returns `null` (skip tile rendering entirely).
- Added requestAnimationFrame-throttled zoom-tier bridge updates to avoid excessive JS-side zoom updates.
- Pan/zoom transforms remain Reanimated shared-value driven.

Updated file:
- `src/components/gameMap/GameMap.tsx`

### 7) Map Canvas Fill Adjustment
- Reduced map container top gap so the world occupies more of the stage between status bar and bottom nav.

Updated file:
- `src/features/gameplayLoop/screens/MapDashboardScreen.tsx`

## Before / After Behavior

### Before
- Debug-grid feel with visible stripe noise.
- Less zoom-out context.
- Single dense render path across zoom states.
- Decorative/debug-like tile detail competed with readability.

### After
- Cleaner map-art direction: dark roads, muted zones, clearer tile semantics.
- River provides geographic identity and future gameplay hook.
- Far overview is actually overview (`z1` with no tile rendering).
- Interaction model remains tap-to-select with detailed sheet flow.

## Drag FPS / Performance Notes
Device FPS profiling cannot be captured from this headless CLI environment, so exact on-device FPS numbers are not included in this report.

Render-load proxy changes:
- Previous grid: `660` tiles rendered continuously (plus additional per-tile decorators).
- New grid total: `2240` cells, with `525` road cells moved to static layer.
- `z1`: `0` tile cells rendered.
- `z3/z4`: up to `1715` non-road tiles rendered.

Practical implication:
- far and medium browsing are materially lighter due zoom culling + static layer split,
- high-detail cost is intentionally paid only at close/precision zoom.

## Validation Checklist
- [x] No white road divider lines remain.
- [x] River is visible and curved (non-rectangular).
- [x] Two zone washes are visible and distinct (`RURAL` vs `DOWNTOWN`).
- [x] Tile density increased (smaller slot size, denser grid).
- [x] Zoom-out range widened (lower minimum zoom).
- [x] `z1` skips tile rendering entirely.
- [x] Semantic tile states preserved (empty/build-ready/selected).
- [x] Touch selection preserved with nearest-tile tap handling.
- [x] Top status bar and bottom nav preserved.

## Verification Run
- `npm run typecheck` ✅
- `npm run lint` ✅ (warnings only, no errors)
- `npm run tokens:audit` ✅
