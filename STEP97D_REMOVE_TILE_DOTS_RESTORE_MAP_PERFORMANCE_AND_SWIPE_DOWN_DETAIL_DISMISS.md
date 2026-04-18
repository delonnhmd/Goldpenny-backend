# STEP 97D - Remove Tile Dots, Restore Map Performance, and Make Detail Sheet Swipe-Down Dismiss

## Goal

Clean up the city map so it feels like a premium game surface again:

- remove the tile dots
- restore smooth drag / pan performance
- make the slot detail sheet dismiss naturally with swipe-down
- remove the top-right Close button so the sheet behaves like a bottom sheet instead of a popup

## What Caused The Drag Slowdown

The slowdown came from the map render tree becoming too heavy at the tile level.

Audit findings from the live map:

- every tile mounted an extra signal dot view
- many tiles also mounted label text at all times
- hotspot / profit visuals added more per-tile layers
- the full tile list was still recreated inline whenever the screen updated for selection or sheet state
- the detail sheet header encouraged button-based exit instead of a fast gesture-based return to the map

The biggest drag regression was not the pan gesture itself. The gesture pipeline was already using animated values. The regression came from the amount of work required to draw the grid.

## Changes Made

### 1. Removed Tile Dots

In `expo/src/components/gameMap/GameMap.tsx`:

- removed the per-tile circular marker entirely
- kept the map readable with color, border, district tint, selected outline, and the current-location marker
- stopped using the dot as a fallback visual placeholder

Result:

- the grid is cleaner
- the lots breathe more
- the map no longer reads like a debug board

### 2. Reduced Tile Render Complexity

In `expo/src/components/gameMap/GameMap.tsx`:

- extracted districts into memoized `DistrictBlock`
- extracted tiles into memoized `TileCell`
- limited tile labels to meaningful cases:
  - selected tile
  - current tile
  - service buildings
  - existing businesses
- removed always-on lot labels for generic build slots and terrain
- limited pulsing demand rings to actionable hotspot-style nodes instead of broadly applying animated clutter across the grid
- kept roads and build-slot inset visuals lightweight
- converted owned / developed tile lookups into memoized `Set`s instead of repeated array scans
- wrapped the full `GameMap` export in `React.memo` so unrelated sheet-state updates do not force full map re-renders

Result:

- fewer subviews per tile
- fewer text nodes on screen
- less selection-related churn
- lighter native drawing cost while dragging

### 3. Restored Smooth Drag / Pan Feel

In `expo/src/components/gameMap/GameMap.tsx`:

- kept pan / pinch on animated shared values
- preserved the lighter gesture model instead of routing drag through React state
- avoided adding new pan-time React updates
- reduced the amount of visual work inside the grid so the existing gesture path can stay responsive

Result:

- drag remains animation-driven
- map movement no longer pays for decorative per-tile clutter
- pan feels closer to the earlier lighter version while keeping the updated color system

### 4. Removed Close Button

In `expo/src/components/gameMap/MapDetailSheet.tsx`:

- removed the top-right `Close` button
- kept the drag handle and sheet header
- preserved the bottom-sheet presentation instead of a modal-dialog feel

In `expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx`:

- removed the extra in-content `Back to Map` button block from the top of the sheet content

Result:

- cleaner sheet header
- less visual clutter
- the primary exit is now the gesture, not a button

### 5. Fixed Swipe-Down Dismiss

In `expo/src/components/gameMap/MapDetailSheet.tsx`:

- kept the header outside the scrolling content so it remains a reliable drag target
- enlarged the handle / header zone so swipe-down is easier to trigger
- kept dismissal on downward drag velocity or distance
- kept content scrolling inside the sheet body

Interaction model now:

1. Tap a slot
2. Detail sheet opens
3. Scroll content if needed
4. Swipe down from the header / handle area
5. Return to full map browsing

This avoids the old feeling of getting stuck inside the sheet.

## Before / After Behavior

### Before

- every tile showed a dot marker
- many tiles showed unnecessary labels at once
- the grid felt noisy and heavy
- drag performance degraded
- the detail sheet pushed the user toward tapping `Close`
- swipe-down did not feel like the primary way back to the map

### After

- tile dots are gone
- generic lot labels are no longer always mounted
- only meaningful tiles keep labels by default
- the tile grid is memoized and lighter
- drag / pan performance is improved by reducing native render cost
- the top-right `Close` button is removed
- the sheet behaves more like a proper swipe-down bottom sheet

## Validation

### A. Dot Removal

- confirmed: the per-tile dot marker was removed from the map tile renderer

### B. Smooth Drag

- confirmed by code path: pan still uses animated shared values
- confirmed by optimization pass: tile render tree is substantially lighter and memoized

### C. Tap Slot

- confirmed: selected tile state still opens the detail sheet

### D. Swipe Down Dismiss

- confirmed: sheet still dismisses on downward drag threshold / velocity
- improved: larger header / handle zone makes that gesture the intended exit path

### E. Scroll Inside Detail Sheet

- confirmed: content remains in a scroll view
- confirmed: header remains outside scroll content, so drag-to-dismiss stays available

### F. No Close Button

- confirmed: top-right `Close` button removed

### G. Map Responsiveness After Repeated Open / Dismiss

- confirmed by structure: unrelated sheet-state changes no longer need to redraw every tile subtree because the map and tiles are memoized more aggressively

## Files Changed

- `expo/src/components/gameMap/GameMap.tsx`
- `expo/src/components/gameMap/MapDetailSheet.tsx`
- `expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx`

## Result

The map now feels cleaner, lighter, and more game-like:

- no tile dots
- fewer always-on labels
- smoother map drag path
- sheet dismiss is swipe-first
- no Close-button clutter
