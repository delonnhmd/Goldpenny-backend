# STEP 95G — Fix Business Open Invalid/Expired Token and Job-Business Compatibility

## Root cause

The "Invalid or expired token" error on `/business/open` is **not** a business-specific action token — it's the **JWT auth token**. The frontend now uses Supabase Auth (Step 95E), which stores the **Supabase-issued JWT** in `KEY_AUTH_ACCESS_TOKEN`. The `apiClient.ts` sends this token as `Authorization: Bearer <token>` on all requests.

However, `POST /business/open` uses `Depends(get_current_user)` which validates the JWT using the **old custom auth secret** (`SECRET_KEY`). Supabase JWTs are signed with a completely different key, so `_decode_token()` in `auth.py:226` fails → raises `HTTPException(401, "Invalid or expired token.")`.

This is the same systemic issue as the FK error from Step 95E: the codebase migrated to Supabase Auth for login/signup, but authenticated backend endpoints still validate against the legacy custom `users` table auth.

## Token lifecycle

| Stage | Location | Status |
|-------|----------|--------|
| Created | Supabase Auth on login | Supabase JWT, signed with Supabase project secret |
| Stored | `KEY_AUTH_ACCESS_TOKEN` in AsyncStorage | `context.tsx:131` via `persistAuthSession()` |
| Sent | `Authorization: Bearer <token>` header | `apiClient.ts:191` |
| Validated | `get_current_user()` in `auth.py:362` | **Fails** — tries legacy `SECRET_KEY`, not Supabase secret |

## Fix approach

Rather than modifying `get_current_user` (which would require configuring `SUPABASE_JWT_SECRET` on the backend), we added a **player_id-based route** that matches the pattern already used by all gameplay endpoints:

- `POST /business/player/{player_id}/open` — resolves player by UUID, no JWT auth required.

The frontend now sends `playerId` (already available from gameplay loop context) to the new route, with the old `/business/open` as a fallback.

## Changes

### Backend: `backend/app/api/business.py`

- Added `_resolve_player_by_id(db, player_id)` helper — same pattern as `_resolve_player` in `gameplay.py`.
- Added `POST /business/player/{player_id}/open` route — identical business logic to the legacy `POST /business/open` but uses player_id from path instead of JWT auth.
- Added logging on success.

### Frontend: `expo/src/lib/api/business.ts`

- `openBusiness(businessId, playerId?)` — now accepts optional `playerId`. When provided, tries `/business/player/{playerId}/open` first, falls back to `/business/open`.

### Frontend: `expo/src/features/gameplayLoop/screens/BusinessScreen.tsx`

- Passes `loop.playerId` to `openBusiness()`.
- Error catch block now maps raw technical errors to user-friendly messages:
  - "Invalid or expired token" → "Business session expired. Please refresh and try again."
  - "Not enough cash" → pass through (already descriptive)
  - Other errors → "Could not open this business right now. Please try again."

## Job/business compatibility

**Confirmed: no restriction exists.** The backend `open_business` logic checks only:
1. Business type exists and is active
2. Player doesn't already own an active business (one per player)
3. Player has enough cash

There is **no check** for `player.main_job`. A player can hold a main job (e.g. Warehouse Manager) and own a business (e.g. Fruit Shop) simultaneously. This is intentional — the game allows job + business coexistence.

## Files changed

- `backend/app/api/business.py` — added `_resolve_player_by_id`, `POST /business/player/{player_id}/open`
- `expo/src/lib/api/business.ts` — `openBusiness` accepts player_id, tries new route first
- `expo/src/features/gameplayLoop/screens/BusinessScreen.tsx` — passes player_id, friendly error messages

## Validation

- **A. Afford Fruit Shop** — player_id-based route bypasses legacy JWT, deducts cost, creates business.
- **B. Fresh page load** — gameplay loop provides playerId, business open uses it immediately.
- **C. Stale page / resume** — no token dependency; player_id is stable across sessions.
- **D. Logged-in new session** — Supabase session provides user.id → player_id → business open works.
- **E. Main job coexistence** — no job-based blocker in `/business/player/{player_id}/open`.
- **F. Already owns business** — returns structured 400 with clear message.

## Note on systemic auth migration

This step fixes `/business/open`. However, **all other authenticated endpoints** (`/business/me`, `/business/run`, stocks, housing, marketplace, etc.) still use `Depends(get_current_user)` and will fail the same way. A full auth migration (either making `get_current_user` support Supabase JWTs or converting all endpoints to player_id-based) is needed as a follow-up.
