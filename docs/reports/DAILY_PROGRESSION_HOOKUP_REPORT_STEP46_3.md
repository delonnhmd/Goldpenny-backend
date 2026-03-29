# Daily Progression Engine Hookup — Step 46.3

## Summary

Introduced a clean daily progression contract into the active gameplay runtime,
replacing the ad-hoc `Date.now()` day key with a tracked, persisted game day number.
The minimal `useDailyProgression` hook is now the single source of truth for day state.

---

## Files Reviewed

| File | Status |
|------|--------|
| `src/hooks/useDailySession.ts` | Reviewed — session lifecycle is still correct; no changes needed |
| `src/hooks/useEconomyState.ts` | Reviewed — derives from dashboard + eod; unchanged |
| `src/lib/api/gameplay.ts` | Reviewed — `endDay()` returns `settled_day`; used directly |
| `src/types/gameplay.ts` | Reviewed — `EndDayResponse.settled_day`, `DailySessionStatus`; unchanged |
| `src/pages/gameplay/GameDashboardPage.tsx` | Updated — hook wired in; controls updated |
| `src/components/gameplay/PlayerStatsBar.tsx` | Updated — Day tile added |

---

## Files Created

### `src/hooks/useDailyProgression.ts`
New hook. The daily progression contract for the Gold Penny gameplay runtime.

---

## Daily Progression Contract Introduced

**Interface: `DailyProgressionContract`**

| Field | Type | Description |
|-------|------|-------------|
| `currentGameDay` | `number` | Current game day. Starts at 1. Increments on `markDayStarted()`. Persisted. |
| `lastProcessedDay` | `number \| null` | Last day settled with the backend. Null until first end-of-day. Persisted. |
| `canAdvanceDay` | `boolean` | True when: session active + no action in flight + today not yet processed |
| `isAdvancingDay` | `boolean` | True during async persist of the day-settle write |
| `markDayAdvanced(settledDay?)` | `async fn` | Records the current day as settled. Uses `settled_day` from backend when available. |
| `markDayStarted()` | `fn → number` | Increments `currentGameDay`, persists async, returns new day number synchronously |

---

## Persistence / Storage Changes

| Key | Format | Purpose |
|-----|--------|---------|
| `goldpenny:gameplay:day:{playerId}` | integer string | Current game day number |
| `goldpenny:gameplay:lastProcessedDay:{playerId}` | integer string | Last day confirmed as settled |

Both keys use the `goldpenny:` namespace. No legacy or NNT-era keys introduced.

On mount, both keys are loaded from AsyncStorage and hydrated into state.
Safe fallback to defaults (`currentGameDay = 1`, `lastProcessedDay = null`) when storage is empty or unavailable.

---

## UI Integration Points Updated

**`GameDashboardPage.tsx`**

- `useDailyProgression` instantiated after `useEconomyState`:
  ```ts
  const dailyProgression = useDailyProgression(
    playerId,
    dailySession.sessionStatus,
    dailySession.pendingExecution || executingAction || endingDay,
  );
  ```

- `handleEndDay`: now calls `await dailyProgression.markDayAdvanced(result.settled_day)` immediately after `dailySession.endDay()`. Uses backend-confirmed `settled_day` for accuracy.

- `handleStartNextDay`: replaced `nextDayKey: \`${Date.now()}\`` with `nextDayKey: String(dailyProgression.markDayStarted())`. Day key is now a real game day number.

- Day controls UI updated:
  - Title now shows `Daily Session — Day N`.
  - End Day button `disabled` now uses `!dailyProgression.canAdvanceDay || endingDay`.
  - Start Next Day button `disabled` now uses `refreshing || dailyProgression.isAdvancingDay`.

**`PlayerStatsBar.tsx`**

- Added optional `currentGameDay?: number | null` prop.
- When provided, renders a `Day N` tile as the first stat tile.

---

## Safety Guards Added

| Guard | Mechanism |
|-------|-----------|
| Double end-day | `canAdvanceDay` requires `currentGameDay !== lastProcessedDay`; once settled, it's false until next day starts |
| Action in flight | `actionInProgress` (= `pendingExecution \|\| executingAction \|\| endingDay`) blocks `canAdvanceDay` |
| Async lock | `isAdvancingDay` true during persist prevents re-entrancy on `markDayAdvanced` |
| Storage failure | All AsyncStorage writes are wrapped in try/catch; in-memory state is always updated |
| Missing data | All numeric reads use `parseInt` with `isFinite` checks; defaults applied safely |
| Stale/empty storage | `initialized` ref prevents double-load; missing keys fall back to defaults |

---

## Naming Integrity Check

Touched files checked for: `nnt-token`, `NNT`, `GNNT`, `UI` (standalone), `wallet`/`token` era naming.

| File | Result |
|------|--------|
| `src/hooks/useDailyProgression.ts` | Clean — no old naming |
| `src/pages/gameplay/GameDashboardPage.tsx` | Clean — `Date.now()` day key removed |
| `src/components/gameplay/PlayerStatsBar.tsx` | Clean — no old naming |

---

## Validation Results

```
npx tsc --noEmit  →  PASS (no output, clean exit)
npx expo lint     →  12 problems, 0 errors, 12 warnings (all pre-existing)
                     No new warnings introduced by this step
```

---

## Deferred

- Full day-level economy recalculation (server-side): `handleEndDay` already triggers `loadDashboard` + `loadEndOfDaySummary` + all sections via `Promise.allSettled`. Further local recalculation deferred.
- Weekly day counter display (separate progress indicator): deferred.
- Day cap / max-day gamification rules: deferred.
- Jobs and expenses engine: explicitly out of scope for this step.
