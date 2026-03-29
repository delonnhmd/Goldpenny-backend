# Step 71G — Gender Selection Added

## UI changes
- Added a `Select Gender` row under the player ID input on the Gameplay Dashboard.
- Added two tap options: `Male` and `Female`.
- Active selection is highlighted and disabled while opening gameplay.

## State handling
- Added local state in gameplay entry route:
  - `gender: 'male' | 'female' | null`
- Added storage key:
  - `goldpenny:gameplay:lastGender`
- On screen load, app now restores last saved `playerId` and `gender` from local storage.
- On successful open (or dev fallback route), app persists both `playerId` and `gender`.

## API payload change
- Updated onboarding create-player client request to always send gender and include `player_id`.
- `POST /onboarding/new-player` payload now includes:
  - `player_id`
  - `display_name`
  - `gender`
  - `region`
  - `starter_job_code`

## Validation behavior
- Tapping `Open Gameplay Loop` now validates:
  - player ID is not empty
  - gender is selected
- If either value is missing, inline error is shown and navigation does not proceed.
- Existing-player path is unchanged: if player exists, app proceeds without blocking on gender mismatch.

## Validation run
- `yarn typecheck` passed.
- `yarn lint` passed with existing repository warnings only (no new errors).
