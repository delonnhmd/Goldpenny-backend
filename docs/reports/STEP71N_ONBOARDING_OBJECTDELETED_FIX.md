# Step 71N — Onboarding ObjectDeletedError Fix

## Exact root cause
- `create_new_player_onboarding` used ORM instance `player` across rollback/commit/fallback paths.
- In failure/retry branches, the original ORM instance could become stale/deleted/detached.
- The route then still accessed `player.id` for logging/fallback (`line ~311` area in current file), which triggered:
  - `ObjectDeletedError: Instance '<Player ...>' has been deleted, or its row is otherwise not present.`

## What was changed
- File changed: `app/api/onboarding.py`

### 1) Stable identifier through transaction lifecycle
- Captured and reused `created_player_id` as a plain string immediately after flush.
- Replaced downstream usage of `player.id` with `created_player_id` in:
  - starter init call
  - onboarding state init
  - summary hydration
  - logging metadata

### 2) Fresh re-query for fallback response
- On summary hydration failure, route now re-queries a fresh Player row by `created_player_id` before building minimal response.
- Avoids using stale ORM instance after rollback/commit.

### 3) Idempotent behavior for repeated player names
- Added pre-create lookup by normalized `display_name`.
- If existing player is found, returns existing summary (`load_ready=True`) instead of creating duplicates.
- Makes repeated requests for `player1` safer.

### 4) Targeted lifecycle logging
- Added explicit logs for:
  - creating profile
  - commit completed
  - idempotent existing-player path
  - summary rehydration/fallback path

## Lifecycle classification
- Issue type: rollback/commit/requery object lifecycle misuse (stale ORM instance access).
- Not a DB auth/deploy issue.

## Validation
- `python -m py_compile app/api/onboarding.py app/services/player_onboarding_service.py` passed.
- Live endpoint validation requires deploying this patch, then re-testing:
  - `POST /onboarding/new-player` for `player1`
  - repeated request for same player id/display_name

## Expected outcome after deploy
- `/onboarding/new-player` returns success for first creation.
- Repeated request for `player1` returns existing player safely.
- No `ObjectDeletedError` from stale/deleted ORM instance access.
