# STEP 92 - Per-Job Skill, XP, Promotion, and Salary Preview (Safe Mode)

## Scope and Safety Guarantee
- This patch adds independent per-job progression tracks (XP, level, promotion tier, salary preview).
- Live shift execution, clock-in/clock-out flow, and payroll transaction posting remain unchanged.
- XP progression writes are isolated and non-blocking relative to shift finalization.

## Per-Job Progression Model

New table: `player_job_progressions`

Fields:
- `player_id`
- `job_key`
- `skill_level`
- `xp_total`
- `xp` (in-level XP)
- `xp_to_next_level`
- `promotion_tier`
- `shifts_completed`
- `last_worked_at`
- `created_at`, `updated_at`

Uniqueness:
- `UNIQUE(player_id, job_key)` to enforce one progression track per job per player.

## XP Rules (Safe Mode)
- XP is awarded only after successful main-shift completion.
- Current MVP amount: `10 XP` per completed shift.
- No XP granted at clock-in.
- XP write failure does not block payroll or shift completion.

## Level Thresholds
- Level 1: 0 XP
- Level 2: 100 XP
- Level 3: 250 XP
- Level 4: 450 XP
- Level 5: 700 XP
- Level 6: 1000 XP
- Level 7: 1350 XP
- Level 8: 1750 XP
- Level 9: 2200 XP
- Level 10: 2700 XP

## Promotion Tiers
- Level 1-2: Junior
- Level 3-4: Intermediate
- Level 5-6: Senior
- Level 7-8: Lead
- Level 9-10: Expert

## Salary Preview Logic
- Preview only (does not change live payroll).
- Base salary is derived from canonical job config/catalog.
- Estimated growth uses `+3%` per level step.
- UI language is explicitly estimated/projection.

## Backend Changes

### New model and migration
- Added `backend/app/models/player_job_progression.py`
- Added migration `backend/alembic/versions/20260407_0026_player_job_progression_tracks.py`

### New progression service
- Added `backend/app/services/player_job_progression_service.py`
- Provides:
  - get/create progression row
  - level/tier resolution from XP
  - fixed XP award on shift completion
  - per-job snapshot + lookup map
  - safe defaults for UI when row is missing

### Career integration
- `backend/app/engine/career_service.py`
  - Creates progression row when:
    - certification completes and unlocks a job
    - player switches to a job

### Shift completion integration
- `backend/app/services/shift_state_service.py`
  - Awards per-job XP during `finalize_active_main_shift(...)`
  - Keeps payroll/shift finalization isolated from progression failures
  - Exposes:
    - `current_job_progression`
    - `career_job_progression`
    - `job_progression_feedback` (on finalized shift response)
    - per-job progression fields inside job market rows

### API payload additions
- `backend/app/api/gameplay.py`
  - Dashboard `job_progress` now prefers current per-job progression snapshot when available.
- `backend/app/api/career.py`
  - New endpoint: `GET /career/player/{player_id}/job-progression`
- `backend/app/schemas/career.py`
  - Added progression response schemas.

## Frontend Changes

### Type + normalization support
- Updated `expo/src/types/gameplay.ts` with:
  - `JobProgressionTrackSnapshot`
  - `JobProgressionFeedbackSnapshot`
  - extended `JobProgressSnapshot`
  - new `work_state`/`job_market` progression fields
- Updated `expo/src/lib/api/gameplay.ts`:
  - normalizes:
    - `current_job_progression`
    - `career_job_progression`
    - `job_progression_feedback`
    - job-level progression fields in job market rows

### UI additions
- Updated `expo/src/features/gameplayLoop/components/JobMarketPanel.tsx`:
  - Current Job Progress card:
    - job, level, tier
    - XP bar and XP to next
    - shifts completed
    - next-level salary estimate
  - Career Progression (All Jobs) list:
    - per-job level/tier/xp state
    - locked requirement visibility
  - Per-job cards now include progression and salary preview details when available.

- Updated `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`:
  - Uses progression tier and safe-mode level cap defaults
  - Adds salary preview metric card
  - Shows progression feedback text after shift finalization when available

## Safe-Mode Boundaries Preserved
- No changes to work action payload contract for `work_shift`.
- No changes to clock-in/clock-out state machine behavior.
- No changes to shift duration logic.
- No changes to payroll posting/transaction formulas.

## Migration Notes
- Apply migration:
  - `20260407_0026_player_job_progression_tracks`
- Existing players:
  - rows are created lazily when switching jobs, completing training, or completing shifts.
- Missing progression row at shift completion:
  - row is auto-created, XP applied, payroll unaffected.

## Before / After Examples

Before:
- Job skill visibility was not per-job and progression was not surfaced.
- No dedicated per-job XP/tier preview in Job Market.

After:
- `Delivery` can be Level 4 while `Chef` remains Level 1 for the same player.
- Switching jobs loads that job's own saved progression.
- Shift completion grants per-job XP and can trigger level-up/tier feedback.
- Salary preview is visible as estimate while live payroll remains unchanged.

## Validation Results

Completed:
- Backend syntax check:
  - `python -m compileall backend/app` passed.
- Frontend type safety:
  - `yarn typecheck` passed.
- Manual data-path validation by inspection:
  - progression fields are now normalized and rendered.

Not completed in this environment:
- Full backend test suite (`pytest -q`) could not run due environment DB config (`DATABASE_URL` requires PostgreSQL URI, sqlite rejected during collection).
