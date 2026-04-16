# STEP 95F — Fix New Player Gameplay Loop Bootstrap Failure and Expose Real /loop Backend Error

## Symptom

Fresh Supabase-auth user creates a player successfully, but `GET /gameplay/player/{player_id}/loop` returns 500 with body `{"detail":"Internal Server Error"}`. Frontend renders the generic "Gameplay loop unavailable" banner and has no way to tell which subsection broke.

## Root cause

`get_gameplay_loop_bundle` in [backend/app/api/gameplay.py](backend/app/api/gameplay.py) wrapped only the first three calls (`_resolve_player`, `_sync_player_work_state`, `get_playable_player_summary`) in a try/except. Everything after that — `_build_dashboard_payload`, `_build_authoritative_gameplay_state`, `_build_action_hub_payload` — ran without isolation. For a brand-new Day 1 player with no prior employment/brief/economy history, any one of those builders could raise and bubble up as an unhandled exception, which FastAPI masks as `{"detail":"Internal Server Error"}`. That's why the frontend log never shows the real cause.

We could not point at a single failing line from logs alone because the existing code did not log the exception class, message, or traceback for any section. Step 1 of this step fixes that.

## Changes

### 1. Per-section exception logging helper

`_log_loop_section_failure(section, player_id, exc)` logs `error_class`, `error_message`, and full `traceback` via `logger.exception`. Called from every section-level `except` so the next /loop failure produces a searchable log line with the real cause.

### 2. Loop endpoint restructured into isolated sections

Only `_resolve_player` is treated as critical (a player that cannot be resolved is a real 404/500). Every other section — work_state, playable summary, daily brief, economy, job summary, dashboard, authoritative state, action hub — is wrapped in its own try/except with:

- real traceback logged
- section name added to `degraded_sections`
- safe fallback value so downstream sections still run

### 3. New-player-safe fallbacks

When a section fails for a fresh player, the loop still returns a usable bundle:

- `playable` falls back to a minimal stat snapshot built from the `Player` row
- `dashboard` falls back to `{dashboard_unavailable: true, message, debug_meta}` carrying the failing section/error
- `authoritative_state` falls back to `{player_id, current_day: 1, hours_available}`
- `action_hub` falls back to empty actions list with the authoritative state attached

### 4. Startup log line for diagnostics

`gameplay.loop bootstrap start` now logs `resolved_player_id`, `new_player_first_session`, `player_main_job`, `player_account_created_day` so we can see the state of the player that hit /loop.

### 5. Debug meta reports degraded sections

The response always includes `debug_meta.degraded_sections` (sorted, deduped) and `debug_meta.new_player_first_session` so the frontend can show section-level diagnostics in dev mode without needing a separate endpoint.

## Files changed

- [backend/app/api/gameplay.py](backend/app/api/gameplay.py) — added `traceback` import, `_log_loop_section_failure` helper, rewrote `get_gameplay_loop_bundle`.

## Before / after

**Before** — a failing dashboard builder:
```
WARN apiClient:fetch_api status:500 detail:"Internal Server Error"
WARN gameplayLoop:resolve_section_critical_failure loop_core
```

Server logs had no traceback. No section-level detail. Frontend stuck on retry banner.

**After** — the same failure:
```
ERROR gameplay.loop section failure
  player_id=1025c680-7d59-4ee0-a2f3-20cca0c16f7a
  section=loop_core.dashboard
  error_class=AttributeError
  error_message='NoneType' object has no attribute 'some_field'
  traceback=<full stack>
```

Response body:
```json
{
  "player_id": "1025c680-...",
  "dashboard": {
    "dashboard_unavailable": true,
    "message": "Day 1 dashboard temporarily unavailable. Starter actions still available.",
    "debug_meta": { "section": "loop_core.dashboard", "error_class": "AttributeError", "error_message": "..." }
  },
  "action_hub": { "actions": [], "authoritative_state": {...} },
  "authoritative_state": {...},
  "debug_meta": {
    "degraded_sections": ["dashboard"],
    "new_player_first_session": true
  }
}
```

The loop still returns 200 with the safe envelope, frontend can render starter UI, and the real exception is now in the server log.

## Get-or-create bootstrap (Part 5)

Player creation in [backend/app/api/player.py](backend/app/api/player.py) already calls `ensure_player_daily_state` at row-insert time, which is the canonical get-or-create bootstrap helper. No additional `get_or_create_*` helpers were needed — the real issue was that missing sections were bubbling up as 500s rather than degrading.

## Validation

- **A. Fresh player, no prior history** — /loop returns 200. If any section crashes, it's logged with a traceback and the response carries `degraded_sections`.
- **B. Refresh on fresh player** — `/player/by-user-id/{user_id}` is already idempotent (unique partial index `ux_players_user_id` + `IntegrityError` re-query). Repeated /loop calls do not mutate state outside `_sync_player_work_state` which itself is idempotent.
- **C. Retry after temporary failure** — retries are safe; no duplicate bootstrap rows.
- **D. Existing player** — no regression; the happy path is identical except it now logs a bootstrap-start line.

## Constraints honored

- Missing state is not guessed: every fallback is explicit and marked in `degraded_sections`.
- Day 1 / new player is a first-class path — not an error.
- /loop no longer returns opaque 500s without cause; every failure produces a structured log and a structured response body.
- No duplicate bootstrap rows on retry.
