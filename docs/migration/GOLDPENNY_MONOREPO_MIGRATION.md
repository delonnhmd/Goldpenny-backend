# GOLDPENNY_MONOREPO_MIGRATION

## Objective
Migrate the project into a clean Gold Penny monorepo layout with separated backend/frontend and remove legacy `nnt-expo` naming from active code/config paths.

## Old Structure (before)

```text
goldpenny-backend/
  app/
  alembic/
  tests/
  requirements.txt
  alembic.ini
  render.yaml
  README.md
  seed.py
  seed_core_schema.py
  *.sql
  PFT/
    pft-expo/   # nested git repo
      app/
      src/
      assets/
      scripts/
      package.json
      app.json
      ...
```

## New Structure (after)

```text
goldpenny-backend/
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
    README.md

  expo/
    app/
    src/
    assets/
    scripts/
    package.json
    app.json
    babel.config.js
    tsconfig.json
    metro.config.js
    eas.json
    .env.example
    README.md

  shared/
    contracts/
    types/
    constants/

  docs/
    reports/
    design/
    migration/

  .gitignore
  README.md
```

## Files/Folders Moved

### Backend moves
- `app/` -> `backend/app/`
- `alembic/` -> `backend/alembic/`
- `tests/` -> `backend/tests/`
- `requirements.txt` -> `backend/requirements.txt`
- `alembic.ini` -> `backend/alembic.ini`
- `render.yaml` -> `backend/render.yaml`
- root `README.md` -> `backend/README.md`
- `seed.py`, `seed_core_schema.py`, `drop_legacy_tables.sql`, `enable_rls.sql`, `schema_fixes.sql` -> `backend/scripts/`

### Expo moves
- `PFT/pft-expo/*` -> `expo/*`
- removed nested Expo `.git` boundary
- removed old `PFT/` wrapper folder

### Docs/report moves
- all step/QA/design/freeze reports (`*.md`, excluding runtime READMEs) consolidated under `docs/reports/`

## Renamed `nnt-expo` References

Active code/config naming cleanup performed:
- `expo/package.json`
  - `name`: `gold-penny-expo` -> `goldpenny-expo`
- `expo/app.json`
  - `expo.slug`: `gold-penny-expo` -> `goldpenny-expo`
- `expo/app/_layout.tsx`
  - header comment path updated from `pft-expo` to `goldpenny/expo`
- `expo/app/(tabs)/settings.tsx`
  - fallback slug updated to `goldpenny-expo`
- `expo/README.md`
  - slug docs updated to `goldpenny-expo`

Note: historical mentions remain in archived reports under `docs/reports/` by design, as historical artifacts.

## Config Changes

### Backend
- Added `backend/Procfile` for process manager compatibility.
- Added `backend/.env.example`.
- Backend run/deploy files now live entirely under `backend/`.

### Root
- Root `.gitignore` rewritten for monorepo paths (`backend/*`, `expo/*` cache/build/env patterns).
- Root `README.md` added with monorepo run/deploy instructions.

### Expo
- Expo app remains runnable from `expo/` with existing scripts and configs.

## Render Configuration (backend root)

Render should target backend as service root:
- **Root Directory**: `backend`
- Build command: `pip install -r requirements.txt && alembic upgrade head`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Blueprint file: `backend/render.yaml`

## Expo Run Instructions (from `expo/`)

```bash
cd expo
yarn install
yarn start
```

Optional:

```bash
yarn android
yarn ios
yarn web
yarn typecheck
```

## Validation Notes
- Structural migration completed: backend/expo/shared/docs now separated at root.
- Active code/config sweep for `nnt-expo`/`pft-expo` identifiers completed (none remaining outside historical reports).
- Historical reports moved under `docs/reports/`.

## Manual Follow-Up Needed
1. Update Render dashboard service settings to use root directory `backend`.
2. If CI/CD workflows reference old paths (`app/`, `PFT/pft-expo`), update them to `backend/` and `expo/`.
3. Re-run dependency install in `expo/` and backend venv setup in `backend/` on fresh environments.
4. Decide whether to keep large local Expo artifacts (`expo/node_modules`, `.expo`, `dist`) or clean/regenerate.
