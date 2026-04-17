Original prompt: Step 96N — UX Cleanup for Map-First Game

Goal
- Remove the stacked-form feel of the app. The map is the primary UI; every contextual action should emerge from a selected tile, not from a detached page.

Pixel map calibration
- Logic/tile base: `MAP_TILE_SIZE = 32` (changed from 28).
  Rationale: better mobile touch targets while staying fine-grained enough for land-slot purchase.
- Zoom bounds stay at [0.9, 2.8] in `GameMap.tsx`, but interaction tiers clarify intent:
  - **far zoom (< 1.15)** — district overview. Tile selection still works but is coarse.
  - **medium zoom (1.15 – 2.0)** — building / lot selection. Primary interaction tier.
  - **close zoom (> 2.0)** — tile-slot precision (frontage picking, adjacency scouting).

Interaction guidance
- Cluster high-volume actions by zoom level instead of making every tile equally clickable at far zoom.
- Keep the bottom slide panel as the single contextual action surface — do not add floating modals per node type.

UX cleanup tasks
- Confirm `expo/app/gameplay/loop/[playerId]/map.tsx` renders `MapDashboardScreen` (done; verify guardrail).
- Deprecate `CityMapScreen` from active routes (keep source for reference until 96K+96M land).
- Ensure the old "page buttons" pattern is not re-introduced on new node types — actions attach to tiles via `mapData.labelForNodeType` and surface through `BottomSlidePanel`.

Notes
- The overlay help text ("Pinch to zoom. Drag to scout. Tap a slot.") stays — it's the only place that teaches the gesture model.
- No Canvas / Skia rewrite in this step. React Native views at 32px scale cleanly on current devices; GPU rendering is out of scope until tile count grows past ~800.
