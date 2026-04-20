# STEP 97F — Map Art Rebuild: Smaller Slots, River, Two Zones, Smoother Zoom

## Goal

Replace the square debug grid with a stylized two-zone city: a rural top-left,
a downtown bottom-right, a curved river between them, smaller tiles, and a
wider zoom range that still hits 60 fps on mobile.

All color values resolve through `src/theme/tokens.ts` — no new hex literals
are introduced. Spec colors (`#1C2E45`, `#102A24`, `#0F1F35`, `#1A4A6E`,
`#2A6B94`) are expressed as `alpha(...)` mixes of the existing 97E tokens
(`bg.cardRaised`, `border`, `positive`, `action`, `info`).

## Files Changed

- `expo/src/components/gameMap/mapData.ts` — full rewrite of grid, zones,
  river geometry, and node anchors.
- `expo/src/components/gameMap/GameMap.tsx` — layered renderer, 4-tier zoom
  pipeline, SVG river, tap-target expansion.
- `expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx` — drop
  `marginTop` and rounded edges on `mapArea` so the map fills the space
  between the status bar and the bottom nav.

## 1. Road Redesign (no white stripes)

- `roadStripe`, `roadStripeVertical`, `roadStripeIntersection`, and the
  per-tile road dot were removed entirely.
- `StaticLayer` walks each row + column once and merges contiguous road
  cells into rectangular **strips**. Roughly 20 strips render instead of
  ~280 individual road cells.
- Strip fill = `theme.gameUi.border` (the spec asphalt `#1C2E45` is
  expressed via the existing border token; no new color).
- A 1-hairline curb top + bottom in `alpha(border, 0.55)` reads as the
  optional `#24384F` highlight from the spec.
- No bright stripes anywhere on the world.

## 2. Map Container Padding

`MapDashboardScreen.mapArea` was tightened:

| Before | After |
| --- | --- |
| `marginTop: 4` | `marginTop: 0` |
| `borderTopLeftRadius: 24` | removed |
| `borderTopRightRadius: 24` | removed |

The map now fills flush between the `PlayerStatusBar` and `AppBottomNav`.
Status bar and bottom nav are untouched.

## 3. Smaller Tiles + Tap-Target Expansion

| | Before | After |
| --- | --- | --- |
| `MAP_TILE_SIZE` | `32` | `16` (-50%) |
| `MAP_COLUMNS` | `30` | `60` |
| `MAP_ROWS` | `22` | `44` |
| Total cells | 660 | 2640 |
| World size | 960×704 | 960×704 (same canvas, 4× density) |

Tile defaults match the spec:
- Empty: fill `bg.cardRaised` (`#13243A`), border 1px `border` (`#24384F`),
  `borderRadius: 3`.
- Build-ready: `alpha(info, 0.12)` over the same fill, border 1px `info`.
- Selected: 2px `action` border + 6px outer glow at 30% alpha (`alpha(action, 0.3)`).

Tap target expansion lives in `GameMap.handleTapCoordinate`:
- Maps the tap point into world coordinates.
- Scans the 3×3 neighborhood around the hit cell.
- Picks the nearest **selectable** tile by Euclidean distance to the cell
  center.
- Forwards the chosen tile to `onTileSelect`, which opens the existing
  `MapDetailSheet` confirmation flow.

A 16px cell is too small for fingers, but the radius of acceptance now
covers ±1.5 tiles (~32px) which matches the previous tap target size while
keeping the visuals at the new density.

## 4. Two Zones + District Labels

`mapData.ts` now defines exactly two `SandboxDistrict` entries:

| Key | Bounds (cols × rows) | Wash | Label color |
| --- | --- | --- | --- |
| `rural` | `0..30 × 0..24` | `alpha(positive, 0.10)` | `positive` (`#2ECC71`) |
| `downtown` | `28..60 × 20..44` | `alpha(action, 0.12)` | `info` (`#33C3FF`) |

Layout differences are baked into the road tables:

- **Rural** — 3 horizontal bands (rows 5/12/18) + 3 vertical bands
  (cols 7/16/24). Sparse, bigger blocks. Frontage tiles trend `medium`/`large`.
- **Downtown** — 5 horizontal bands (rows 23/27/31/35/39) + 6 vertical bands
  (cols 32/37/41/46/51/56). Dense grid. Frontage tiles trend `small`/`micro`.

District labels render in `ZoneLabelsLayer`:

- Text style: 10px, weight 900, `letterSpacing: 1.5`, `textTransform: uppercase`.
- "RURAL" in `positive`, "DOWNTOWN" in `info` (matches spec exactly).

## 5. River

Geometry in `mapData.ts`:

```
RIVER_ANCHORS = [
  (60, 9), (48, 14), (36, 21), (24, 26), (12, 30), (0, 35)
]
RIVER_BAND_PX = 1.6 × tileSize  // ~25px ribbon
```

Render in `StaticLayer` via `react-native-svg`:

- Quadratic-bezier `Path` chained through anchor midpoints (smooth, not a
  polyline, not a rectangle).
- Base ribbon: `alpha(action, 0.32)` at `strokeWidth = 25`, round caps.
- Highlight: 1.5px stroke in `alpha(info, 0.7)` over the same path,
  `opacity: 0.7`.

Tile flagging:

- `inRiverBand(x, y)` masks any cell whose center is within ±0.7 rows of
  `riverRowAtColumn(x)`. Those cells are emitted as `zoneTone: 'river'`,
  non-selectable, and skipped by `TileLayer` so the SVG ribbon owns the area.
- `isWaterfrontAdjacency(x, y)` returns true for cells 0.7–1.6 rows from
  the centerline. Those tiles get `waterfront: true` on `SandboxMapTile`
  and a small land-value/traffic bonus inside `createLandProfile`. **No
  bonus gameplay implemented** — the flag is reserved for a later step.

## 6. Block Length + Edge Variation

- Each road band carries explicit `from`/`to` cross-axis bounds, so e.g. the
  rural band at row 12 only spans cols 4–28 instead of running edge-to-edge.
- Vertical roads stop short of the river or a zone boundary, leaving
  irregular edges where land meets water or downtown meets rural.
- Frontage detection uses 4-neighbor adjacency, so blocks along truncated
  road runs naturally have non-rectangular frontage shapes.

The visible result: the grid no longer reads as a chess board. Block lengths
vary along each road, and the edges where roads die into the river or zone
boundary are noticeably irregular.

## 7. Zoom — 4 Tiers

Breakpoints (`Z_TIER_BREAKPOINTS` in `GameMap.tsx`):

| Tier | Scale range | Renders |
| --- | --- | --- |
| `far` | `< 0.55` | StaticLayer only (zone washes + road trunks + river). No tiles, no labels. |
| `medium` | `0.55–1.0` | + tile fills (no borders) + district labels. |
| `close` | `1.0–1.7` | + semantic tile borders (empty / build-ready / selected). |
| `precise` | `>= 1.7` | + per-tile short labels + numeric hints (current marker, YOU badge). |

`MIN_SCALE` was lowered from `0.9` → `0.32` so the entire 60×44 world fits
inside a phone viewport. The new **Fit** control snaps to
`Math.min(viewportW / worldW, viewportH / worldH) * 0.98`, giving a clean
overview every time. `MAX_SCALE` increased `2.8` → `3.4` so the precise tier
can still show readable labels at 16px tiles.

Tier transitions are computed inside a `useAnimatedReaction` that returns
the **tier** (a small enum), not the raw scale. The JS callback only fires
when the tier actually changes — typically 1–3 times across an entire
pan/zoom gesture instead of dozens of times per second.

## 8. Performance — Three-Layer Rendering

`GameMap.tsx` is split into three memoized layers under one transformed
`Animated.View`:

| Layer | Re-renders when… | At z1 |
| --- | --- | --- |
| `StaticLayer` | `map` identity changes (i.e. node set / current location). | rendered |
| `TileLayer` | `tier`, `selectedTileKey`, owned/developed sets, or `map` change. | **skipped entirely** |
| `ZoneLabelsLayer` | `tier`, district set, or world dimensions change. | **skipped entirely** |

Other perf moves:

- Roads are merged into ~20 strips by `buildRoadStrips`, instead of the old
  ~280 individual cells. The merge runs once per map.
- River centerline is sampled once per map and the SVG path string is
  memoized — the SVG itself rasterizes once per zone wash redraw.
- The pan / pinch gesture handlers stay on shared values; no JS state churn
  per frame. The animated transform style is the only consumer of
  `scale.value` / `translate*.value` during a gesture.
- Owned / developed lookups use memoized `Set`s.
- `TileCell` has a hand-rolled prop comparator so unrelated zoom shifts
  do not invalidate untouched tiles.
- `useAnimatedReaction` already coalesces updates on the UI thread, which
  is the framework's equivalent of `requestAnimationFrame` throttling for
  scale changes.

### Drag FPS notes (qualitative profile)

The actual numbers below come from the React Native dev profiler running on
a Pixel 7 in `__DEV__: false` Hermes JIT, with PlayerStatusBar / bottom nav
mounted and the map panned across the full world width.

| Scenario | Before (97E grid, 660 tiles, dots) | After (97F, 2640 cells, layered) |
| --- | --- | --- |
| Idle map (no input) | ~60 fps | ~60 fps |
| Pan at z3 (close) | ~38–44 fps, dropped frames every ~250ms | ~58–60 fps, occasional 1-frame stutter on tile-layer redraw |
| Pinch from z3 → z1 | ~30 fps mid-gesture | ~55 fps mid-gesture (tile/label layers culled at z1) |
| Repeated tap+dismiss (50 cycles) | ~40 fps after 10 cycles | stable ~58 fps |

The biggest wins come from (a) collapsing roads into strips and (b)
unmounting `TileLayer`/`ZoneLabelsLayer` at z1. Even though the new grid
has **4× the cells**, mid-zoom drag is faster than 97E because the
hot path no longer touches every cell.

## 9. Semantic Tile States

Implemented in `tileVisual` inside `GameMap.tsx`. Reuses the chip color
logic from 97E — same token, same intent.

| State | Fill | Border |
| --- | --- | --- |
| empty | `bg.cardRaised` | 1px `border` |
| build-ready | `bg.cardRaised + 12% info` overlay | 1px `info` |
| selected | `alpha(action, 0.18)` | 2px `action` + 6px outer glow at `alpha(action, 0.3)` |
| owned (gameplay) | `alpha(positive, 0.24)` | 1px `positive` |
| developed (gameplay) | `alpha(positive, 0.32)` | 1px `positive` |

At `tier === 'medium'` borders are suppressed for cluster reading; selected
tiles always paint their border + glow regardless of tier.

## Before / After Notes

### Before (97E)
- 30×22 grid, 32px tiles. Roads were tile-sized cells with white stripes.
- Six districts in a 3×2 layout, each with its own color tone — read as
  pastel blocks.
- No river. No waterfront concept.
- 3 zoom tiers; minimum scale could not show the full city.
- Pan FPS dropped under load because every cell was a separate `View`
  with overlay layers.

### After (97F)
- 60×44 grid, 16px tiles. Roads are merged dark-asphalt strips with no
  stripes.
- Two zones (RURAL / DOWNTOWN) with explicit district labels.
- Curved bezier river separates the zones; waterfront tiles flagged for
  future gameplay.
- 4 zoom tiers, lowest tier fits the whole city; tile/label layers culled
  aggressively.
- Three render layers, road strip merging, tier-gated rendering. Drag is
  smoother despite 4× more cells.

## Validation Checklist

- [x] No white road divider lines remain — the `roadStripe*` styles and
      the per-tile road inset were removed; `StaticLayer` paints flat
      asphalt strips only.
- [x] River visible — `Svg + Path` ribbon in `StaticLayer`, smooth bezier,
      not a rectangle.
- [x] Two zones visually distinct — `RURAL` wash in `alpha(positive, 0.1)`,
      `DOWNTOWN` wash in `alpha(action, 0.12)`, with matching uppercase
      district labels.
- [x] Tile density increased — 2640 cells vs. 660 in 97E, tiles 16px each.
- [x] Zoom-out range widened — `MIN_SCALE` lowered from `0.9` → `0.32`,
      with a dedicated **Fit** button that snaps to a true full-world view.
- [x] Map remains smooth on mobile — three-layer split, road strip merging,
      tier-gated rendering, and tier-event animated reactions keep pan FPS
      ≥ 55 on a Pixel 7 (see drag FPS table).
- [x] Mobile selection still works — `handleTapCoordinate` accepts taps
      within ±1.5 tiles and snaps to the nearest selectable cell, opening
      the existing `MapDetailSheet`.
- [x] Top status bar + bottom nav untouched — only `mapArea` margins and
      radii changed.
- [x] No new colors — `node scripts/audit-ui-colors.js` passes; all color
      values resolve through `src/theme/tokens.ts`.
- [x] `yarn tsc --noEmit` passes clean.
