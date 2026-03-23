# Gold Penny Backend

FastAPI backend for the Gold Penny financial simulation game.

## Tech Stack

- **FastAPI** — async API framework
- **SQLAlchemy 2.0** — ORM with PostgreSQL
- **Alembic** — schema migrations
- **psycopg2-binary** — PostgreSQL driver
- **Redis + Celery** — async task queue
- **Pydantic v2** — request/response schemas
- **python-dotenv** — environment variable loading

## Quick Start

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the template below into a `.env` file at the project root and fill in real values:

```env
# PostgreSQL / Supabase connection string
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/goldpenny

# JWT settings
SECRET_KEY=replace-with-a-long-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Supabase (optional — used by future client-side uploads)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Internal admin API key  (used by /internal/* routes — keep this secret)
INTERNAL_API_KEY=generate-a-strong-random-key
```

### 4. Apply database migrations

Make sure `DATABASE_URL` points to a running PostgreSQL instance (local or Supabase), then:

```bash
# First time — generate the migration from the ORM models
alembic revision --autogenerate -m "initial_schema"

# Apply all pending migrations
alembic upgrade head
```

For subsequent schema changes (after adding or modifying models), repeat:

```bash
alembic revision --autogenerate -m "describe_your_change"
alembic upgrade head
```

### Supabase RLS Hardening (Deny-by-Default)

Supabase may flag warnings when public schema tables do not have Row Level
Security (RLS) enabled. This is expected for projects where tables were created
by SQLAlchemy/Alembic migrations, because migrations do not auto-enable RLS.

Gold Penny uses FastAPI as the primary backend path today, so this project
enables RLS at the table level first and keeps policies closed by default:

- RLS is enabled on core game tables in Alembic migration `20260316_0002_enable_rls`.
- No permissive anon/public policies are added yet.
- No direct Supabase frontend access is enabled yet.

Planned follow-up:

- Add read-only public policies for non-sensitive market data tables.
- Add per-user policies for private player data.
- Map application auth identities to database policy enforcement.

### 5. Seed reference data

```bash
python seed.py
```

This inserts the canonical starting rows (baskets, sector stocks, housing regions,
business types, co-op deal templates, NPC firms, day-1 macro state).
All operations are idempotent — safe to run multiple times.

### 6. Start the API server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Basic liveness check |
| GET | `/health/db` | Database connectivity check |
| GET | `/internal/bootstrap-summary` | Seeded row counts (requires `X-Internal-Key`) |
| GET | `/internal/security-summary` | Core RLS posture summary (requires `X-Internal-Key`) |
| POST | `/auth/register` | Player registration |
| POST | `/auth/token` | Login → JWT |
| GET | `/player/me` | Authenticated player profile |
| POST | `/day/advance` | Advance the in-game day |
| GET | `/stocks/prices` | Current sector stock prices |
| GET | `/market/listings` | Active marketplace listings |

Full OpenAPI spec available at `/docs` or `/redoc`.

---

## Project Layout

```text
goldpenny-backend/
  alembic/              — Alembic migration environment
  alembic.ini           — Alembic configuration
  seed.py               — Standalone seed script (run once after migrations)
  requirements.txt
  README.md
  app/
    main.py             — FastAPI app, lifespan, startup seeds
    api/                — Route handlers (one file per domain)
    engine/             — Business logic / simulation engines
    models/             — SQLAlchemy ORM models
    schemas/            — Pydantic v2 request/response schemas
    db/
      database.py       — Engine, SessionLocal, Base, get_db
    jobs/
      celery_worker.py  — Celery background tasks
```

---

## Migrations workflow (reference)

```bash
# Check current migration state
alembic current

# Show pending migrations
alembic history --verbose

# Roll back one step
alembic downgrade -1

# Roll back to the very beginning
alembic downgrade base
```
