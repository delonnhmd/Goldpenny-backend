# STEP71D_DEAD_BUTTONS_FIX_REPORT
Date: 2026-03-23
Status: FIX APPLIED - READY FOR DEVICE VERIFICATION

## Goal
Restore gameplay loop interactivity after "Open Gameplay Loop" so Brief / Dashboard / Work / Market / Summary tabs and controls remain tappable on Android, with a safe first-session player flow.

## Root Cause
The dead-interaction behavior came from a combination of issues:

1. Expo Router layout rule violation
- `app/_layout.tsx` mounted `<Slot />` inside `<Stack>`, which is invalid for Expo Router layout routes.
- This matched the runtime warning: layout children inside Stack must be `Screen`.

2. Onboarding route lock made tabs feel dead
- During first-session onboarding, `navigateTo` only allowed the single expected route.
- Bottom-tab presses were blocked (not visually obvious enough), which looked like broken taps.

3. Invalid player bootstrap (`player1` not found)
- Entering a non-existent player ID triggered repeated API failures and mixed fallback behavior.
- This created noisy state and unclear UX instead of a clean entry flow.

## Fix Summary (Minimal + Safe)

### 1) Fixed Expo Router root layout
- File: `app/_layout.tsx`
- Replaced invalid `<Stack><Slot /></Stack>` with valid `<Stack screenOptions={{ headerShown: false }} />`.

### 2) Restored usable tab navigation during dev/testing
- File: `src/features/onboarding/context.tsx`
- Added `EXPO_PUBLIC_ONBOARDING_ROUTE_LOCK` toggle.
- Default behavior now allows navigation unless route lock is explicitly enabled.
- Kept onboarding guidance/steps; only removed forced nav lock by default.

### 3) Added dev-safe player bootstrap flow
- Files:
  - `app/gameplay/index.tsx`
  - `src/lib/api/onboarding.ts`
- On "Open Gameplay Loop":
  - Validate player via `/onboarding/player/{player_id}`.
  - If player is missing and dev auto-create is enabled, create a starter player via `/onboarding/new-player` and route to the returned real `player_id`.
  - If validation fails for non-not-found reasons, allow entry with clear info message (fallback mode).
- Prevents entry into broken half-error state for missing players.

### 4) Added interaction diagnostics (temporary-safe)
- Files:
  - `src/features/gameplayLoop/GameplayLoopScaffold.tsx`
  - `src/features/gameplayLoop/context.tsx`
  - `src/components/onboarding/OnboardingStepOverlay.tsx`
  - `src/features/onboarding/context.tsx`
- Added logs for:
  - tab press accepted/blocked
  - route changes
  - onboarding overlay mount/unmount
  - loading/refreshing transitions
  - soft-launch gate state changes

## Files Changed
- `app/_layout.tsx`
- `app/gameplay/index.tsx`
- `src/lib/api/onboarding.ts`
- `src/features/onboarding/context.tsx`
- `src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- `src/features/gameplayLoop/context.tsx`
- `src/components/onboarding/OnboardingStepOverlay.tsx`

## Validation

### Static checks
- `yarn typecheck` -> PASS (0 errors)
- `yarn lint` -> PASS (0 errors, existing non-blocking warnings only)

### Behavioral validation targets for device test
1. Open app -> Gameplay entry screen.
2. Enter `player1` -> tap "Open Gameplay Loop".
3. If `player1` does not exist, app auto-creates dev player and opens loop.
4. Bottom tabs (`Brief`, `Dashboard`, `Work`, `Market`, `Summary`) remain tappable.
5. `Refresh` remains tappable.
6. No persistent transparent overlay blocks interaction.
7. Diagnostics log tab press + route change events.

## Issue Classification
- Layout: YES (root Expo Router layout bug)
- Overlay: NO hard blocker found; verified no persistent full-screen touch interceptor in loop path
- Routing: YES (onboarding route-lock behavior)
- Player bootstrap: YES (invalid `player1` path now handled)

## Remaining Risks
1. If backend onboarding endpoints are unavailable, auto-create cannot run; app still allows fallback entry with explicit message.
2. If strict guided route lock is desired in production, set `EXPO_PUBLIC_ONBOARDING_ROUTE_LOCK=true`.
3. If you want deterministic auto-create outside dev builds, set `EXPO_PUBLIC_DEV_AUTO_CREATE_PLAYER=true` explicitly.

## Next Recommended Verification on Device
1. Force close the Expo app and reopen to clear stale route state.
2. Reproduce with `player1` and confirm auto-create -> loop opens.
3. Tap through every tab twice and confirm no blocked interaction.
4. Check logs for `gameplayLoop:tab_press` and `gameplayLoop:route_change` entries.
