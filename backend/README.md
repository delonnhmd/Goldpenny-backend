# Gold Penny Backend

FastAPI backend for Gold Penny.

## Directory Layout

```text
backend/
  app/
  alembic/
  scripts/
  tests/
  requirements.txt
  alembic.ini
  render.yaml
  Procfile
  .env.example
```

## Local Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` from `.env.example`, then run:

```bash
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload
```

## Render Deployment

- Set Render service root directory to `backend`
- Build command:

```bash
pip install -r requirements.txt && alembic upgrade head
```

- Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Real-World Event Pipeline (3-B-1)

The Phase 3-B-1 pipeline runs once per day at 04:00 UTC through the Celery beat task in `app/jobs/realworld_tasks.py`. The job calls `app.services.realworld.daily_generation_job.run_daily_generation`, which attempts the FRED-backed rule generator first, then yesterday's real-world row, then the static catalog fallback.

Operators can manually trigger the same path with `POST /admin/realworld/regenerate?date=YYYY-MM-DD`. The route is mounted under `/admin` and uses the same `X-Internal-Key` header as other internal tools; `INTERNAL_API_KEY` must be configured or the endpoint fails closed.

The cost breaker lives in `app.services.realworld.cost_breaker`. The operational target is `$0.10` per MAU per month and the hard breaker threshold is `$0.20` per MAU per month. Phase 3-B-1 rule generation records `$0.00` cost, but the persisted log and breaker are already in place for the AI layer in Phase 3-B-2.

Read current operator state with `GET /admin/realworld/today` using the same `X-Internal-Key` header. The response includes today's event row, yesterday's row for context, breaker state, and the seven most recent event rows labeled as `rule`, `yesterday_fallback`, or `static_fallback`.

This endpoint is read-only visibility, not the Phase 3-B-2 human-review queue. It does not approve, reject, edit, or publish events; it only shows what the current deterministic pipeline has already produced.
