# Core Logic Freeze Report - Step 57

## Final Statement

Core logic is now frozen.

Future work will focus on UI, UX, and production polish, with only bug fixes, exploit fixes, and minor numeric tuning allowed in the frozen gameplay layer.

## Systems Frozen

The following systems are now treated as structurally frozen:
- player engine
- economy engine
- market engine
- business engine
- event engine
- daily progression orchestration
- settlement accounting
- gameplay persistence and hydration model
- onboarding logic
- guided early-day behavior for the first 3 days

These systems should not receive new mechanics, new structural flows, or casual refactors.

## Allowed Changes

Allowed after freeze:
- bug fixes
- exploit fixes
- small numeric balance adjustments
- wording/copy improvements driven by UI needs
- explicit contract-versioned fixes when a persistence or API defect is proven

Not allowed after freeze:
- new systems
- new mechanics
- new gameplay data flows
- structural rule changes
- casual refactors of canonical logic
- moving backend-owned logic into the frontend

## Locked Contracts

### Canonical gameplay persistence
Locked contract:
- `src/lib/gameplayPersistence.ts`
- canonical key: `goldpenny:gameplay:state:${playerId}`
- payload versioning via `GAMEPLAY_PERSISTENCE_VERSION`

Frozen expectations:
- snapshot shape remains stable
- `currentDay` remains numeric and canonical
- invalid snapshots are discarded rather than trusted
- action counts and session status remain part of the continuity model

### Action canonicalization
Locked contract:
- `src/lib/api/gameplay.ts`
- `canonicalActionKey(...)`

Frozen expectations:
- frontend action canonicalization stays aligned with backend action semantics
- `switch_job` ordering remains protected against accidental remapping to `work_shift`

### Daily execution order
Locked contract:
- `app/services/day_progression_service.py`
- `app/services/daily_settlement_service.py`

Frozen order:
- market catch-up
- event engine
- basket pricing
- job market update
- economy brief build
- population pressure refresh
- player settlement
- post-settlement systems: career, progression, commitment, world memory, onboarding summary
- player Daily Brief generation

This order must not drift unless a verified defect requires a documented fix.

### Settlement accounting
Locked contract:
- `app/services/daily_settlement_service.py`

Frozen expectations:
- one settlement write per player/day
- immutable settlement log semantics
- business contribution enters before player settlement
- summary/reporting fields preserve current meanings

### Onboarding and guided early days
Locked contract:
- `app/engine/onboarding_service.py`
- `app/schemas/onboarding.py`
- `src/types/onboarding.ts`
- `src/lib/api/onboarding.ts`

Frozen expectations:
- backend remains the source of truth for onboarding/guided-day reveal
- frontend remains a presentation layer for those backend decisions
- Day 1 onboarding and Days 2-3 guided reveal stay canonical and persistence-backed

## Guardrails Added

Concise freeze guardrails were added to canonical entry points:
- `app/services/day_progression_service.py`
- `app/services/daily_settlement_service.py`
- `app/engine/onboarding_service.py`
- `src/lib/gameplayPersistence.ts`
- `src/lib/api/gameplay.ts`

These comments mark the areas where future drift would be most dangerous.

## Risky Areas Documented

Highest-sensitivity areas:
- settlement accounting and write-once day close behavior
- progression orchestration order
- action canonicalization and action guard behavior
- persistence/hydration payload shape
- onboarding/guided-day backend reveal rules
- business/day interplay where day-level idempotency matters

Why they are risky:
- small changes can create duplicate rewards, replay bugs, stale hydration, or frontend/backend desync
- many tests assume the current order and payload meanings
- several layers depend on these contracts indirectly through normalized API responses

## Cleanup Performed

### Removed dead legacy path
Deleted unused Expo hooks:
- `src/hooks/useBackend.ts`
- `src/hooks/useWallet.tsx`
- `src/hooks/useRegistration.ts`

These hooks were not referenced by any active app or gameplay route.

### Removed orphaned legacy constants/config
Cleaned:
- unused wallet-era constants from `src/constants/index.ts`
- wallet deep-link query schemes from `app.json`
- wallet-only dependencies from `package.json`
- retained `expo-linking` because `expo-router` still expects it as a peer

### Removed stale generated residue
Deleted stale ESLint cache files under:
- `.expo/cache/eslint/`

This removed old path/name residue from generated artifacts.

### Naming cleanup
Updated active source wording to remove stale wallet/token phrasing in the Settings screen and hook barrel comments.

## Validation Results

### Backend validation
Command:
- `pytest tests/test_day_progression_services.py tests/test_business_daily_operations_service.py tests/test_stock_trading_service.py tests/test_onboarding_service.py tests/test_onboarding_api.py tests/test_onboarding_integration.py`

Result:
- `31 passed`

### Frontend validation
Commands:
- `yarn install`
- `yarn typecheck`
- `yarn lint`

Results:
- lockfile updated successfully
- typecheck passed
- lint passed with the same 6 pre-existing warnings and 0 errors

### Active-source naming integrity
Result:
- no active Expo source matches remained for:
  - `useWallet`
  - `WalletProvider`
  - `WalletConnectUI`
  - `useBackend`
  - `useRegistration`
  - `NNT`
  - `GNNT`
  - `nnt-token`

## Manual Validation Gap

Not completed in this terminal-only step:
- manual gameplay run from Day 1 to Day 5 in a live Expo session

Because Step 57 made only freeze comments, dead-path cleanup, and config cleanup, the main automated checks were rerun successfully. A live device walkthrough can still be done as final human confirmation, but no logic regression was introduced by this step.

## Readiness

Gold Penny is now ready to move into the UI-focused phase.

Core behavior, contracts, and sequencing are locked.

Going forward:
- backend remains canonical for economy and gameplay rules
- frontend remains presentation and interaction orchestration
- changes to frozen logic must be justified as bug fixes, exploit fixes, or tightly scoped numeric tuning only
