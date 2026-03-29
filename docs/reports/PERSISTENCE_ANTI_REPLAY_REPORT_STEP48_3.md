# Step 48.3 - Persistence Anti-Replay Pass

## Scope

Harden the active Gold Penny local persistence flow so gameplay day/session/event continuity restores from canonical saved state, avoids hydration-order bugs, and resists replay caused by stale or partial local payloads.

## Files Reviewed

- `src/hooks/useDailySession.ts`
- `src/hooks/useDailyProgression.ts`
- `src/hooks/useRandomEvent.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/lib/apiClient.ts`
- `app/gameplay/index.tsx`
- `app/(tabs)/settings.tsx`
- `src/lib/gameplayRuntimeState.ts`
- `src/lib/gameEvents.ts`
- `src/types/randomEvent.ts`

## Files Updated

- `src/lib/gameplayPersistence.ts`
- `src/hooks/useDailyProgression.ts`
- `src/hooks/useDailySession.ts`
- `src/hooks/useRandomEvent.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`

## Canonical Persisted Payload

Step 48.3 introduces a single canonical gameplay snapshot stored under:

- `goldpenny:gameplay:state:${playerId}`

Payload shape:

```ts
interface PersistedGameplayState {
  version: 1;
  playerId: string;
  currentDay: number;
  lastProcessedDay: number | null;
  session: {
    currentDay: number;
    remainingTimeUnits: number;
    actionCounts: Record<string, number>;
    sessionStatus: 'active' | 'ended';
    totalTimeUnits: number;
  } | null;
  randomEvent: {
    eventId: string;
    sourceDay: number;
    isResolved: boolean;
  } | null;
}
```

Notes:

- This payload stores only canonical local continuity state.
- Dashboard, economy, debt, and job display values are still restored from backend gameplay data and recomputed after hydration rather than persisted locally.
- UI labels, summaries, and display-only derived strings are intentionally not persisted.

## Replay Risks Found

### 1. Split-key hydration race

Before this step, current day, last processed day, daily session, and random event state were persisted under separate keys and hydrated independently. That allowed mixed restore states from different points in time.

### 2. Premature restore during default day

`GameDashboardPage` initialized the daily session immediately from `useDailyProgression.currentGameDay`, even before progression hydration had completed. That created a restore window where default day `1` could temporarily drive session initialization.

### 3. Action markers derived from volatile history

Daily action counts were reconstructed from restored counts plus in-memory action history. That made cap enforcement depend on a derived path rather than a canonical once-per-day marker.

### 4. Event continuity written outside canonical gameplay state

Random event continuity used its own key and could restore independently from the active gameplay day/session snapshot.

### 5. Legacy payload acceptance was too permissive

Older gameplay keys were still the active persistence model. There was no single versioned shape to validate and migrate.

## Changes Implemented

### 1. Added a versioned canonical gameplay snapshot helper

`src/lib/gameplayPersistence.ts` now owns:

- the canonical snapshot shape
- version field
- validation and sanitization
- serialized write queue per player snapshot
- legacy read fallback and migration into the canonical snapshot key

### 2. Switched active gameplay writes to the canonical snapshot

The active gameplay runtime no longer writes day, session, and random event continuity to separate gameplay keys.

Current active gameplay writes now target only:

- `goldpenny:gameplay:state:${playerId}`

### 3. Added old-read / new-write migration behavior

Legacy keys are now read only for backward compatibility:

- `goldpenny:gameplay:day:${playerId}`
- `goldpenny:gameplay:lastProcessedDay:${playerId}`
- `goldpenny:gameplay:session:${playerId}`
- `goldpenny:gameplay:event:${playerId}`

Behavior:

- read canonical snapshot first
- if missing or invalid, read legacy gameplay keys
- build a canonical snapshot from legacy values
- write the canonical snapshot to the new Gold Penny key
- do not resume writing to legacy gameplay keys

### 4. Hardened day progression hydration and start-next-day writes

`useDailyProgression` now:

- hydrates from the canonical snapshot
- exposes `isHydrated`
- persists `currentDay` and `lastProcessedDay` through the canonical snapshot helper
- clears stale session/event continuity when starting a new day
- makes `markDayStarted()` async so the next-day flow can await canonical snapshot update before continuing

### 5. Hardened session restore and canonical action markers

`useDailySession` now:

- restores only when the canonical snapshot day matches the requested day
- validates and sanitizes persisted action counts
- uses canonical `actionCounts` state as the local once-per-day marker source
- increments action markers on successful action history writes instead of reconstructing them from volatile in-memory history
- blocks action execution while gameplay day/session restore is still in progress

### 6. Hardened event continuity and recovery replay protection

`useRandomEvent` now:

- hydrates from the canonical gameplay snapshot
- waits until gameplay hydration and day/session alignment are complete before restoring or rolling events
- writes event continuity into the canonical snapshot
- marks resolved events in the canonical snapshot so reload does not resurface them
- applies a day guard so stale writes from an older day cannot overwrite a newer gameplay snapshot

### 7. Gated dashboard hydration ordering

`GameDashboardPage` now:

- waits for daily progression hydration before initializing the daily session
- only enables random event continuity once progression hydration is complete and the session day matches the hydrated gameplay day
- awaits async next-day persistence before resetting the local session

## Hydration Validation Improvements

Validation now checks:

- payload version
- player ownership
- required numeric fields
- positive day values
- session day coherence with root `currentDay`
- finite numeric time-unit values
- valid session status
- valid event shape and day markers
- bounded numeric action counts

Invalid canonical snapshots are rejected safely and cleared before fallback/migration logic runs.

## Derived State Rehydration

Display-only and derived gameplay state is not trusted from local persistence.

After hydration:

- economy summaries are recomputed from canonical runtime state plus backend dashboard data
- job/income summaries are recomputed from canonical runtime state plus backend snapshots
- warning and summary labels continue to derive from live canonical state instead of saved UI strings

## Legacy Key Handling Decisions

- Legacy gameplay continuity keys remain read-only fallback inputs for backward compatibility.
- New gameplay continuity writes use only the canonical Gold Penny snapshot key.
- `app/gameplay/index.tsx` already followed the same pattern for player ID restore: read legacy fallback, write canonical key.
- Settings/admin persistence remains separate because it is device-local configuration, not gameplay continuity state.

## Naming Integrity Findings

- No new `nnt-token` / `NNT` / `GNNT` / token-era gameplay naming was introduced in touched files.
- The new active gameplay continuity key uses the Gold Penny namespace: `goldpenny:gameplay:state:${playerId}`.
- Legacy gameplay keys remain only as migration inputs inside `src/lib/gameplayPersistence.ts`.

## Validation

### TypeScript

`npx tsc --noEmit`

Result: passed.

### Lint

`npx expo lint`

Result: passed with the existing 10 warnings and 0 errors.

## Verification Notes

Code-path verification completed for:

- canonical day/session/event restore ordering
- next-day snapshot clearing
- resolved event replay suppression
- action-marker persistence surviving reloads
- legacy read / new canonical write behavior

Interactive app-run verification was not executed in this step, so live tap-through confirmation still remains advisable.

## Deferred Risks

- If AsyncStorage itself is unavailable or fails at write time, in-memory gameplay can still continue even though replay resistance across app restarts becomes weaker for that failure window.
- Backend-side idempotency remains valuable for true cross-device or transport-level replay resistance; this step only hardens local device persistence.
- Admin override values still live outside the gameplay snapshot because they are configuration inputs rather than gameplay continuity state.