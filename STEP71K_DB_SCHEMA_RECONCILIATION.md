# Step 71K — DB Schema Reconciliation (Render vs Supabase)

## Problem statement
- Supabase manual check reported `players.gender` exists.
- Live Render onboarding still reported `UndefinedColumn` for `players.gender` during `POST /onboarding/new-player`.
- This indicates runtime DB/schema resolution mismatch (or stale runtime/env), not frontend behavior.

## What was audited
1. **DB target loading**
- `DATABASE_URL` is loaded in `app/db/database.py` and passed into SQLAlchemy engine.
- Safe diagnostics already log DB host/db name and now include schema resolution checks.

2. **Player model table mapping**
- `Player` model declares:
  - `__tablename__ = "players"`
  - no explicit `schema` in model/table args
- Therefore SQL resolves by active `search_path` (default schema behavior).

3. **Onboarding insert path**
- `POST /onboarding/new-player` -> `create_new_player_profile(...)` inserts into ORM `Player` table (`players`) under active search path.

## Changes made
### 1) Startup DB/schema diagnostics (safe)
- Added one-time startup diagnostics logging:
  - DB host
  - DB name
  - inferred Supabase project ref (when derivable)
  - `current_database()`
  - `current_schema()`
  - `SHOW search_path`
  - all schemas containing table `players`
  - all schemas where `players.gender` exists
- File: `app/db/database.py`
- Wired into startup in `app/main.py`.

### 2) Runtime onboarding table-resolution diagnostics
- Added onboarding log with:
  - ORM table fullname/schema used by `Player`
  - current DB/schema/search_path from the request DB session
- File: `app/api/onboarding.py`

## Files changed
- `app/db/database.py`
- `app/main.py`
- `app/api/onboarding.py`

## Exact DB host/project used by live backend
- This is now emitted in Render startup logs as:
  - `DB target diagnostics: host=... db=... project_ref=...`
- This removes guesswork and directly confirms whether Render points at the same Supabase project inspected manually.

## Multiple players-table check
- This is now emitted in logs as:
  - `players_table_schemas=[...]`
  - `players_gender_column_schemas=[...]`
- If these differ (example: `players` exists in schema A, but `gender` only in schema B), root cause is confirmed as schema-path mismatch.

## Root cause category
- Runtime schema/database reconciliation gap.
- Prior to this patch, there was no authoritative runtime evidence in logs for host/schema/table resolution, so manual SQL checks could target a different effective table than the live insert path.

## Validation status
- Local code validation passed (`py_compile` on changed backend files).
- Live validation requires one deploy cycle and checking Render logs for new diagnostics.

## Post-deploy validation checklist
1. Redeploy Render with this commit.
2. In startup logs, confirm:
   - `host`, `db`, `project_ref`
   - `current_schema`, `search_path`
   - `players_table_schemas` and `players_gender_column_schemas`
3. Trigger `POST /onboarding/new-player` (player1).
4. Confirm no `UndefinedColumn` and onboarding returns success.
