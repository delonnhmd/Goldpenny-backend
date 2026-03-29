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
