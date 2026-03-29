# Step 71H — DATABASE_URL Socket-Path Fix

## Root cause
- Primary root cause: Render `DATABASE_URL` formatting/encoding issue (not a SQLAlchemy host parser bug).
- A malformed URI (especially unescaped `@` in password or copied `URI:` prefix) can produce host parsing that leads to socket-style errors like:
  - `connection to server on socket "@aws-0-us-west-2.pooler.supabase.com/.s.PGSQL.5432" failed`
- Secondary issue: backend startup previously passed `DATABASE_URL` directly to `create_engine(...)` with no validation, so failures were opaque.

## What was fixed
- Added minimal URL normalization and validation in DB startup:
  - strips accidental `URI:` prefix
  - converts `postgres://` to `postgresql://`
  - validates scheme and host presence
  - detects malformed `@@` pattern and raises explicit guidance (`@` must be `%40` if in password)
  - rejects socket-like host values
  - appends `sslmode=require` automatically for Supabase hosts when missing
- Added safe diagnostics log output (scheme/host/port/db only, no password).

## Files changed
- `app/db/database.py`

## Expected correct DATABASE_URL format
```env
postgresql://postgres.<project-ref>:<URL_ENCODED_PASSWORD>@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
```

Example for this project ref:
```env
postgresql://postgres.nizqmiosjtbimkfjbrec:<URL_ENCODED_PASSWORD>@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
```

## Validation result
- Malformed URL test with `@@` now fails fast with explicit error message.
- Valid Supabase pooler URL parses correctly and normalizes to include `sslmode=require`.
- No backend redesign; fix is limited to DB URL startup handling.
