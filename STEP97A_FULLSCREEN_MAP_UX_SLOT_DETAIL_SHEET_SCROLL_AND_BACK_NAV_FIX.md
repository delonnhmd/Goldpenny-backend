# STEP 97A - Full-Screen Map UX, Slot Detail Sheet, Scroll, and Back Navigation Fix

## Goal

Make the map the dominant gameplay surface and move slot inspection into a proper in-map detail sheet instead of a permanent page block.

## What changed

### 1. Map layout refactor

- The map remains the main visual layer between the top status bar and bottom nav.
- Slot detail content no longer consumes permanent page layout space beneath the map.
- The selected-slot experience now renders as an overlay sheet above the map.
- Browse mode now starts with no forced slot selected, so the player can pan and inspect the city first.

### 2. Slot detail sheet behavior

- Added a reusable `MapDetailSheet` component.
- Slot detail opens as a slide-up sheet when a tile is tapped.
- The sheet includes:
  - close control in the sheet header
  - explicit `Back to Map` button
  - slot hierarchy with type, district, coordinates, and status
  - existing contextual actions already wired for work, food, travel, business, and land controls
- The sheet supports drag-down dismissal from the handle area.

### 3. Android/system back handling

- Added focused Android back interception in `MapDashboardScreen`.
- If slot detail is open, hardware back closes the sheet first.
- Only when no slot is selected does back fall through to normal navigation.

### 4. Scroll and gesture fix

- Slot detail content now lives inside a dedicated `ScrollView` in `MapDetailSheet`.
- `nestedScrollEnabled` is enabled for Android-friendly sheet scrolling.
- Drag-to-dismiss is limited to the sheet handle area so content scrolling and map gestures do not fight each other as aggressively.
- Map pan/zoom remains on the base map layer.

### 5. Visual map polish

- Darkened the district palette to match the premium midnight look.
- Increased contrast between roads, lots, services, business tiles, and expansion nodes.
- Strengthened selected-tile glow and current-location contrast.
- Upgraded map frame, overlay badge, and control styling for a more premium full-screen feel.

## Before / After UX

### Before

- The selected slot card sat in normal page flow and pulled attention away from the map.
- The map felt like one section on a page instead of the main gameplay surface.
- Returning from detail state was unclear.
- Android back risked dumping the player out before clearing detail mode.
- Long slot detail content did not have a dedicated sheet scroll container.

### After

- The player enters map browse mode first.
- Tapping a slot opens a bottom sheet while the map stays visible behind it.
- Detail content scrolls independently inside the sheet.
- The player can exit detail mode with `Close`, `Back to Map`, drag-down, or Android back.
- Closing detail returns the player to map browse mode without leaving the map screen.

## Files changed

- `expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx`
- `expo/src/components/gameMap/MapDetailSheet.tsx`
- `expo/src/components/gameMap/GameMap.tsx`
- `expo/src/components/gameMap/mapData.ts`
- `expo/src/components/gameMap/index.ts`

## Validation results

### Verified

- TypeScript check passed via `npm run typecheck` in `goldpenny-backend/expo`.
- Code path for slot tap -> open detail sheet is wired through `selectedTileKey`.
- Code path for hardware back -> close detail first is wired through `BackHandler` + `useFocusEffect`.
- Code path for explicit close -> return to browse mode is wired through `closeSelectedTile`.
- Code path for independent detail scrolling is wired through `MapDetailSheet` `ScrollView`.

### Pending live/manual touch validation

- A. Tap slot -> sheet visually opens over the map
- B. Scroll detail -> sheet scroll feels correct on device
- C. Close detail -> map resumes normal pan/zoom feel
- D. Android hardware back -> closes detail before screen/app exit
- E. Gesture balance between map pan and sheet content on a physical device
- F. Final visual feel tuning on real device sizes

## Notes

- Top status bar was preserved.
- Bottom nav was preserved.
- Selected slot detail was not turned into a separate full page.
- Android back now prioritizes closing detail mode first.
