# Step 71I — players.gender Schema Fix

## Root cause
- Production DB schema drift: `players.gender` column was missing in Supabase while backend onboarding insert expected it.
- Existing backend code attempted to insert `gender` during `POST /onboarding/new-player`, causing:
  - `psycopg2.errors.UndefinedColumn: column "gender" of relation "players" does not exist`

## Migration status
- A migration already existed:
  - `20260317_0011_player_gender`
- This indicates production likely missed applying part/all of Alembic history.

## Files changed
- `app/main.py`
- `app/api/onboarding.py`

## What changed
1. Startup schema-guard reliability (`app/main.py`)
- Added explicit guard statement at top of startup migration list:
  - `ALTER TABLE players ADD COLUMN IF NOT EXISTS gender VARCHAR(20)`
- Changed startup migration executor to run each statement in isolated transactions.
  - Prevents one failed `ALTER TABLE` from aborting all subsequent guards in PostgreSQL transaction state.

2. Temporary onboarding safety fallback (`app/api/onboarding.py`)
- Added targeted detection for missing `players.gender` UndefinedColumn errors.
- On that exact error only:
  - rollback transaction
  - run `ALTER TABLE players ADD COLUMN IF NOT EXISTS gender VARCHAR(20)`
  - retry profile creation once
- Keeps onboarding alive while preserving explicit logs of schema mismatch.

## Migration name/id
- Existing migration: `20260317_0011_player_gender`

## Production apply steps
1. Preferred: apply Alembic migrations to production DB
```bash
alembic upgrade head
```

2. If emergency hotfix is needed immediately in Supabase SQL editor
```sql
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS gender VARCHAR(20);
```

3. Redeploy/restart Render service so startup guards execute with latest code.

## Validation result
- Code-level validation confirms:
  - Missing-column signature is detected correctly.
  - Startup guard now runs per statement without transaction-abort cascade.
- After deploy + migration apply, `POST /onboarding/new-player` should succeed without `UndefinedColumn`.
