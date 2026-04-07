# STEP91B - Job List and Certification System

## Scope
- Replaced the broken "Switch Job -> Start -> backend error" interaction with a Job Market progression flow.
- Added visible 10-job list, visible certification requirements, training start, unlock state, and switch-job execution.
- Kept this as a stabilization/progression patch without adding unrelated systems.

## Root Problems Fixed
- Switch-job UX was action-card-first and often failed with `switch_job requires new_job_key`.
- Certification gates existed in backend but were not surfaced in a usable UI flow.
- Players with no main job could fall into confusing dead states.

## Job List (MVP 10)
- Retail Worker (`retail`) - Entry - No certification needed.
- Delivery Driver (`delivery`) - Entry - No certification needed.
- Cleaner (`cleaner`) - Entry - No certification needed.
- Chef (`chef`) - Mid - Requires `chef_cert`.
- Auto Mechanic (`auto_mechanic`) - Mid - Requires `auto_mechanic_cert`.
- Warehouse Operator (`warehouse_operator`) - Mid - No certification needed.
- Aircraft Mechanic (`aircraft_mechanic`) - High - Requires `aircraft_mechanic_cert`.
- Banker (`banker`) - High - Requires `banking_license`.
- Real Estate Agent (`real_estate_agent`) - High - Requires `real_estate_license`.
- Business Owner (`business_owner`) - Future unlock (locked in MVP).

## Certification List
- Chef Certification (`chef_cert`) - Unlocks Chef - 2 days - 20 XGP.
- Auto Mechanic Certification (`auto_mechanic_cert`) - Unlocks Auto Mechanic - 3 days - 40 XGP.
- Aircraft Mechanic Certification (`aircraft_mechanic_cert`) - Unlocks Aircraft Mechanic - 6 days - 100 XGP.
- Banking License (`banking_license`) - Unlocks Banker - 5 days - 80 XGP.
- Real Estate License (`real_estate_license`) - Unlocks Real Estate Agent - 4 days - 60 XGP.

## Training Flow
- UI sends canonical start training action:
- `action_key: "start_training"`
- `parameters: { "certification_key": "<cert_key>" }`
- Backend starts track, charges configured training cost, and stores active training state.
- Work state now returns training status and progress fields used by UI:
- `training_active`
- `training_certification_key`
- `training_days_completed`
- `training_days_required`
- `training_days_remaining`
- Certification completion is persisted in `completed_certification_keys` (not just a single boolean), so unlocks are track-specific and durable.

## Switch Job Payload Fix
- Canonical switch payload now always includes:
- `action_key: "switch_job"`
- `parameters: { "new_job_key": "<job_key>" }`
- Frontend normalization enforces `new_job_key` for switch actions.
- Job Market buttons use the selected card key directly for `new_job_key`.

## No-Main-Job Recovery Behavior
- Job Market panel explicitly shows no-job warning when no main job is assigned.
- Action hub work shift remains blocked until a real job is selected.
- UI text is human-readable and no fake default delivery role is injected.

## UI Redesign
- Added reusable Job Market panel component with job cards:
- Shows job name, salary, stress level, requirement, and status (`Locked` / `Available` / `Current Job`).
- Card CTA behavior:
- Unlocked and not current: `Switch to <Job>`.
- Locked with cert path: `Start Training`.
- Current/future lock: disabled state.
- Dashboard and Work screens now use this panel instead of legacy starter-job chooser cards.

## Key Files Changed
- Backend:
- `backend/app/engine/career_config.py`
- `backend/app/engine/career_service.py`
- `backend/app/api/gameplay.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/services/job_key_service.py`
- `backend/app/services/job_market_service.py`
- `backend/app/models/job_definition.py`
- `backend/app/services/job_progress_service.py`
- Frontend:
- `expo/src/features/gameplayLoop/components/JobMarketPanel.tsx` (new)
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/WorkScreen.tsx`
- `expo/src/lib/api/gameplay.ts`
- `expo/src/types/gameplay.ts`
- `expo/src/features/gameplayLoop/context.tsx`

## Validation
- TypeScript validation passed:
- `yarn typecheck` in `expo` completed successfully.
- Python syntax validation passed:
- `python -m compileall` on changed backend modules completed successfully.
- Backend pytest run note:
- Targeted tests were attempted, but test collection failed due environment `DATABASE_URL` policy requiring PostgreSQL scheme in this workspace setup.

## Before / After Behavior
- Before:
- Switch Job card could send incomplete payloads and fail with missing `new_job_key`.
- Certification requirements were enforced by backend but not shown as progression UI.
- After:
- Player sees complete job list with lock state and requirement text.
- Locked jobs route to training with explicit certification key.
- Unlocked jobs switch with canonical `new_job_key` payload.
- No-main-job state is explicit and guided into Job Market selection.
