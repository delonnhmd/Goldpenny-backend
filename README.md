# Gold Penny Monorepo

This repository is organized as a monorepo with a clean separation between backend and Expo frontend.

## Structure

```text
goldpenny-backend/
  backend/          # FastAPI API, Alembic, scripts, tests, Render config
  expo/             # Expo app (Router + src + assets)
  shared/           # Future shared contracts/types/constants
  docs/             # Reports, design notes, migration docs
```

## Run Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Backend URL: `http://localhost:8000`

## Run Expo

```bash
cd expo
yarn install
yarn start
```

Useful Expo commands:

```bash
yarn android
yarn ios
yarn web
yarn typecheck
```

## Deploy Backend On Render

1. Connect this GitHub repo to Render.
2. Set **Root Directory** to `backend`.
3. Use the `backend/render.yaml` blueprint or configure equivalent commands:
   - Build: `pip install -r requirements.txt && alembic upgrade head`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add required env vars (`DATABASE_URL`, `SECRET_KEY`, etc.).

## Build Expo App (EAS)

```bash
cd expo
yarn build:preview:android
yarn build:preview:ios
# or production profiles
yarn build:prod:all
```
