# STEP 95C — Fix Account Registration Backend and Return Clean JSON Errors

## Root cause of /auth/register failure

The signup screen surfaced:

```
Non-JSON response at /auth/register: Internal Server Error
```

Two compounding issues were responsible:

1. **Schema drift.** Step 95 introduced four new columns on the `users` table
   (`auth_provider`, `status`, `last_login_at`, `password_updated_at`) via the
   alembic migration `20260414_0027_auth_account_foundation`. On the deployed
   database that migration had not been applied, so the `User(...)` insert in
   `register()` raised a `ProgrammingError: column "auth_provider" does not
   exist`. Because the startup `_run_schema_migrations` block only covered
   `players`/`game_states`/etc. additive columns, the new `users` columns were
   not self-healed on boot.
2. **No global exception handler.** FastAPI/Starlette's default
   `ServerErrorMiddleware` response for an uncaught exception is the plain-text
   string `"Internal Server Error"` — not JSON. The mobile API client tries to
   parse the body as JSON and raises `Non-JSON response at /auth/register:
   Internal Server Error`.

## Exact failing layer

- Layer: `db.flush()` / `db.commit()` inside `register()` at
  [goldpenny-backend/backend/app/api/auth.py:374](goldpenny-backend/backend/app/api/auth.py#L374)
  when the live schema lacked the auth-account metadata columns.
- Propagation: bare `raise` re-threw the SQLAlchemy error. FastAPI had no
  matching `HTTPException`, so Starlette returned the raw 500.

## JSON error contract for auth endpoints

All `/auth/*` responses now return structured JSON on every outcome.

### Success
```json
{
  "success": true,
  "user_id": "uuid",
  "email": "user@example.com",
  "has_linked_player": false,
  "access_token": "...",
  "token_type": "bearer",
  "expires_at": "2026-05-14T00:00:00Z",
  "account": { ... },
  "player_profile": null
}
```

### Failure
```json
{
  "success": false,
  "error_code": "email_already_exists",
  "message": "That email is already registered. Try logging in.",
  "detail": "That email is already registered. Try logging in."
}
```

### Error codes emitted by /auth/register
- `validation_error` — Pydantic body rejected (422).
- `http_400` — invalid email / short password (via `HTTPException`).
- `email_already_exists` — duplicate via pre-check or DB `IntegrityError`.
- `password_hash_failed` — bcrypt backend crashed.
- `internal_register_error` — unexpected DB/lookup/commit failure.
- `session_build_failed` — account created, session construction failed.
- `internal_server_error` — final catch-all from the app-wide handler.

## Account creation flow cleanup

- Registration creates **only** the `users` row. It does **not** call
  `_bootstrap_clean_player_profile` anymore (it already did not in Step 95, and
  this step documents and locks that behavior in the unit test
  `test_auth_account_flow.py`).
- First login returns `player_profile: null`. The client then invokes
  `POST /auth/player-profile` (Create New Player flow) to bootstrap the
  Day-1 baseline. This fully decouples the registration path from the
  gameplay state machine.

## Files changed

- [goldpenny-backend/backend/app/main.py](goldpenny-backend/backend/app/main.py)
  - Added `users` additive column guards (auth_provider, status,
    last_login_at, password_updated_at) to `_run_schema_migrations`.
  - Added three global exception handlers (`StarletteHTTPException`,
    `RequestValidationError`, `Exception`) that always emit JSON with
    `success/error_code/message/detail`.
- [goldpenny-backend/backend/app/api/auth.py](goldpenny-backend/backend/app/api/auth.py)
  - Hardened `register()`: staged try/except around lookup, password hash,
    insert/commit, and session build; each failure returns a structured
    `JSONResponse` and is logged with `logger.exception` (no password
    logged).
  - Extended `AuthSessionResponse` with `success`, `user_id`, `email`,
    `has_linked_player` for the new success contract.

## Before / after

### Before — register on a drifted DB
```
HTTP/1.1 500 Internal Server Error
Content-Type: text/plain
Internal Server Error
```

### After — same failure
```
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
{
  "success": false,
  "error_code": "internal_register_error",
  "message": "Could not create account right now. Please try again.",
  "detail": "Could not create account right now. Please try again."
}
```

### After — boot fully heals the schema so the next attempt succeeds
```
HTTP/1.1 201 Created
{
  "success": true,
  "user_id": "...",
  "email": "md.noithat@gmail.com",
  "has_linked_player": false,
  "access_token": "...",
  ...
}
```

## Validation results

- `test_auth_account_flow.py::test_signup_login_and_session_restore_require_explicit_fresh_player_creation`
  continues to pass — registration returns `AuthSessionResponse` with
  `player_profile=None` and no `Player` rows are created.
- Manual validation scenarios:
  - **A.** New email + valid password → 201 JSON with session + tokens.
  - **B.** Duplicate email → 400 JSON `error_code=email_already_exists`.
  - **C.** Simulated DB failure (e.g. schema drift) → 500 JSON
    `error_code=internal_register_error`, never raw HTML/plain text.
  - **D.** No auto-player creation — `Player` count is 0 immediately after
    register. Player creation now runs through `/auth/player-profile`.
  - **E.** Session handling — register auto-logs the new account in by
    returning an access token in the same response; the client can proceed
    directly to Create New Player or drop back to login cleanly.

## Frontend error handling

`expo/src/lib/apiClient.ts` already prefers `payload.detail` / `payload.error`.
With the new JSON error bodies the user now sees the human-readable
`message`/`detail` (e.g. "That email is already registered. Try logging in.")
instead of `Non-JSON response at /auth/register: Internal Server Error`. No
frontend change was required, but the fallback path (`Could not create
account right now.`) now only triggers on genuine network/parse failures.

## Constraints honored

- Player profile creation is not triggered inside register.
- No non-JSON errors can reach the mobile app from any route (global
  handler).
- Passwords are never logged — only email + stage + exception type.
- Duplicate email creation is blocked by pre-check and DB uniqueness
  (`IntegrityError` mapped to the same `email_already_exists` error code).
- Register is isolated from gameplay state code paths.
