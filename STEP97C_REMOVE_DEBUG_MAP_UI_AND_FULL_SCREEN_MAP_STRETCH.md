# STEP97C - Remove Debug Map UI and Full-Screen Map Stretch

## Goal

Turn the map into a true full-screen gameplay layer by removing developer-facing HUD elements and letting the city occupy the full playable area between the top status bar and bottom nav.

## Removed completely

- `MAP MODE: FAR` overlay
- `Houston Sandbox` in-map hero overlay
- `Current / Selected / Zoom` in-map mini stat rail
- top map page stat strip with `Current / Selected / Zoom`
- `Browse Mode` instructional overlay
- floating dark hint/debug boxes around the map

## Kept

- top status bar
- bottom nav
- tile highlight on selection
- bottom sheet detail flow from Step 97A
- minimal zoom controls (`+`, `-`, `Center`)

## Layout changes

### Map stretch

- Removed the page-level map header block above the world.
- Removed horizontal map margins so the map stretches edge-to-edge.
- Kept the map filling the full vertical area between top status and bottom nav.

### Boxed-map removal

- Removed the card-like framed treatment from `GameMap`.
- Removed rounded outer map shell styling.
- Removed border/shadow treatment that made the map feel like a widget instead of the world.

## Interaction model

### Now

- Map is the dominant layer
- Tap tile
- Tile highlights
- Bottom sheet opens
- Close sheet
- Return to map browse state

### Android back

- Back still closes the detail sheet first before normal navigation continues

## Visual control cleanup

- Zoom controls were kept but made smaller and more transparent
- Controls remain edge-aligned and non-bulky
- No debug text replaces removed overlays

## Files changed

- `expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx`
- `expo/src/components/gameMap/GameMap.tsx`

## Before / after

### Before

- Map still lived inside page UI
- Multiple debug/status overlays competed with the world
- Boxed map treatment weakened the full-screen feel

### After

- The map reads as the main world layer
- Nonessential developer labels are gone
- The player sees only the world, controls, tile highlight, and detail sheet when needed

## Validation

### Verified

- `npm run typecheck` passed in `goldpenny-backend/expo`
- top debug strip removed
- in-map debug overlays removed
- map no longer uses rounded boxed-card framing
- map stretches across the playable width
- tile tap still routes into the bottom sheet flow
- hardware back behavior from Step 97A remains intact in code

### Pending manual device check

- confirm edge-to-edge feel on real device aspect ratios
- confirm zoom controls feel appropriately subtle
- confirm map + bottom sheet layering feels like a world, not a dashboard

