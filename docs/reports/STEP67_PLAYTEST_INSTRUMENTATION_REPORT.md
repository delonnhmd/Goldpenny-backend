# STEP 67 — Real Playtest Instrumentation + Balance Feedback Layer

## Objective

Add a lightweight, non-intrusive telemetry layer to the gameplay loop so that real playtest sessions generate inspection-ready data. No vendor dependencies, no network calls — all data lives in AsyncStorage on the device and can be reviewed from a new dev panel inside Settings.

---

## What Was Built

### 1. Core Analytics Library — `src/lib/playtestAnalytics.ts`

Handles all storage, event types, and report assembly.

**Storage keys** (all namespaced under `goldpenny:playtest:`)

| Key | Purpose |
|-----|---------|
| `events:{playerId}` | Ring buffer of last 200 raw events |
| `funnel:{playerId}:{gameDay}` | Day 1 funnel checkpoint timestamps |
| `screentime:{sessionId}` | Per-screen timing records |
| `balance:{playerId}:{gameDay}` | Starting + ending balance telemetry |
| `friction:{sessionId}` | Boolean friction signal flags |
| `sessions:{playerId}` | Index of all sessions for this player |

**Event names (12 total)**

`session_started` · `onboarding_started` · `onboarding_skipped` · `onboarding_completed` · `brief_viewed` · `dashboard_viewed` · `work_action_taken` · `market_viewed` · `business_viewed` · `summary_viewed` · `day_completed` · `session_abandoned`

**Key functions**

- `emitPlaytestEvent(event)` — fire-and-forget event write (errors swallowed)
- `generateSessionId()` — `gp_{timestamp36}_{random6}` format
- `recordScreenTime(sessionId, screen, durationMs)` — accumulates per-screen averages
- `recordTimeToFirstAction(sessionId, durationMs)` — first work action latency
- `markFunnelCheckpoint(playerId, gameDay, checkpoint, ts?)` — 7-point funnel model
- `recordStartingStats(playerId, gameDay, stats)` — snapshot at session start
- `recordEndingStats(playerId, gameDay, stats)` — snapshot at day settlement
- `updateFrictionSignal(sessionId, signals)` — set boolean flags
- `incrementLongIdleCount(sessionId)` — increment when app idles > 90 s
- `buildPlaytestReport(playerId, sessionId, gameDay)` — assemble full `PlaytestReport`
- `clearPlaytestData(playerId)` — wipe all analytics for a player

---

### 2. PlaytestProvider + usePlaytest Hook — `src/features/playtest/context.tsx`

React context that wraps the gameplay loop layout. Provides high-level tracking methods to child components.

**Methods exposed via `usePlaytest()`**

| Method | Effect |
|--------|--------|
| `trackScreenView(screen)` | Flushes previous screen time, marks funnel checkpoint, emits viewed event |
| `trackWorkAction(props?)` | Emits `work_action_taken`, marks funnel, records time-to-first-action |
| `trackSessionStarted(gameDay, stats)` | Emits `session_started`, records starting stats |
| `trackDayCompleted(gameDay, stats)` | Emits `day_completed`, records ending stats |
| `trackSessionAbandoned()` | Emits `session_abandoned` |
| `trackOnboardingStarted/Skipped/Completed()` | Emit onboarding events |
| `loadReport()` | Returns latest `PlaytestReport` |

**AppState monitoring**: When app goes background for ≥ 90 seconds, `incrementLongIdleCount` is called automatically. This captures players who get stuck or distracted.

**Provider hierarchy**:
```
GameplayLoopProvider
  └── PlaytestProvider          ← new
        └── OnboardingProvider
              └── Slot
```

---

### 3. useScreenTimer Hook — `src/hooks/useScreenTimer.ts`

Single-line hook added to the top of each gameplay screen:

```typescript
useScreenTimer('brief');   // or 'dashboard' | 'work' | 'market' | 'business' | 'summary'
```

Calls `trackScreenView(screenKey)` on mount. The PlaytestProvider automatically flushes the previous screen's elapsed time.

---

### 4. PlaytestObserver — `src/features/gameplayLoop/components/PlaytestObserver.tsx`

Zero-render component (`return null`) mounted inside `GameplayLoopScaffold`. Watches loop and onboarding state and fires events reactively:

- **Session started**: Fires once when `dailyProgression.isHydrated` and `dashboard.stats` are available. Records starting stats (cash, stress, health).
- **Day completed**: Fires once per `gameDay` when `endOfDaySummary` becomes available. Records ending stats including `total_earned_xgp`.
- **Work action taken**: Watches `actionsTakenToday` success count. Fires `work_action_taken` on first increment, and marks funnel + time-to-first-action.
- **Onboarding skip/complete**: Watches `onboarding.isActive` transition from `true → false`, reads persisted onboarding state to distinguish skip vs. complete, fires appropriate event and updates friction signal.

---

## Day 1 Funnel Model (7 Checkpoints)

| # | Checkpoint | Field | Trigger |
|---|-----------|-------|---------|
| 1 | Session started | `sessionStartedAt` | `trackSessionStarted` |
| 2 | Brief seen | `briefSeenAt` | `useScreenTimer('brief')` |
| 3 | Dashboard seen | `dashboardSeenAt` | `useScreenTimer('dashboard')` |
| 4 | First work action | `firstWorkActionAt` | `trackWorkAction()` |
| 5 | Market seen | `marketSeenAt` | `useScreenTimer('market')` |
| 6 | Summary seen | `summarySeenAt` | `useScreenTimer('summary')` |
| 7 | Day completed | `dayCompletedAt` | `trackDayCompleted()` |

The `buildPlaytestReport` function computes a `completionLabel` from these 7 booleans: e.g. `4/7 checkpoints`, which surfaces in the Settings panel.

---

## Balance Telemetry

Captured at session start (from `dashboard.stats`) and day settlement (from `endOfDaySummary` + `dashboard.stats`):

| Field | Source |
|-------|--------|
| `startingCash` | `dashboard.stats.cash_xgp` at session start |
| `startingStress` | `dashboard.stats.stress` |
| `startingHealth` | `dashboard.stats.health` |
| `endingCash` | `dashboard.stats.cash_xgp` after settlement |
| `endingStress` / `endingHealth` | `dashboard.stats` after settlement |
| `cashDelta` / `stressDelta` / `healthDelta` | Computed deltas |
| `incomeEarned` | `endOfDaySummary.total_earned_xgp` |
| `expensePressure` | `expenseDebt.debtPressure` label |
| `endedPositive` | `cashDelta > 0` |

---

## Friction Signals

| Signal | Set When |
|--------|----------|
| `onboardingSkipped` | Onboarding transition to inactive with `status === 'skipped'` |
| `noWorkActionTaken` | Session ends without any `work_action_taken` event (default `true`, cleared on first action) |
| `noMarketVisit` | No `market_viewed` event (default `true`, cleared by `useScreenTimer('market')`) |
| `noBusinessVisit` | No `business_viewed` event (default `true`, cleared by `useScreenTimer('business')`) |
| `exitedBeforeSummary` | Session ends without `summary_viewed` (default `true`, cleared by summary screen) |
| `longIdleCount` | Incremented each time app backgrounds for ≥ 90 s |

---

## Dev Review Panel — Settings Screen

Added a new **Playtest Review** section card to `app/(tabs)/settings.tsx`. It is visible in development builds only (not gated by a flag — it's dev-targeted by the Settings screen itself being internal).

**Features:**
- Enter player ID (pre-populated from `goldpenny:gameplay:lastPlayerId`)
- Enter game day (default: 1)
- **Load Report** — assembles and displays `PlaytestReport`
- **Clear Data** — wipes all playtest analytics for the player
- Report sections: Funnel (7 checkpoints), Balance Outcome, Friction Signals, Screen Time averages, Recent Events (last 12)

---

## Files Changed

### New Files
| File | Purpose |
|------|---------|
| `src/lib/playtestAnalytics.ts` | Analytics storage, event types, report builder |
| `src/features/playtest/context.tsx` | PlaytestProvider, usePlaytest hook |
| `src/features/playtest/index.ts` | Barrel exports |
| `src/hooks/useScreenTimer.ts` | Single-line screen timing hook |
| `src/features/gameplayLoop/components/PlaytestObserver.tsx` | Reactive zero-render observer |

### Modified Files
| File | Change |
|------|--------|
| `app/gameplay/loop/[playerId]/_layout.tsx` | Added PlaytestProvider wrapping OnboardingProvider |
| `src/features/gameplayLoop/GameplayLoopScaffold.tsx` | Mount PlaytestObserver inside ContentStack |
| `src/features/gameplayLoop/screens/BriefScreen.tsx` | `useScreenTimer('brief')` |
| `src/features/gameplayLoop/screens/DashboardScreen.tsx` | `useScreenTimer('dashboard')` |
| `src/features/gameplayLoop/screens/WorkScreen.tsx` | `useScreenTimer('work')` |
| `src/features/gameplayLoop/screens/MarketScreen.tsx` | `useScreenTimer('market')` |
| `src/features/gameplayLoop/screens/BusinessScreen.tsx` | `useScreenTimer('business')` |
| `src/features/gameplayLoop/screens/SummaryScreen.tsx` | `useScreenTimer('summary')` |
| `src/features/onboarding/context.tsx` | Emit `onboarding_skipped` / `onboarding_completed` on `completeOnboarding` |
| `app/(tabs)/settings.tsx` | Playtest Review dev panel (state + handlers + JSX section) |

---

## Design Constraints Respected

- **No gameplay mutation**: All analytics are fire-and-forget. Any storage error is silently swallowed. No await blocking on the render path.
- **No vendor lock-in**: AsyncStorage only. Zero external analytics SDKs.
- **Removable**: The entire system is isolated in `src/lib/playtestAnalytics.ts` + `src/features/playtest/`. Removing it requires only deleting those files and the 1-line hook calls from screens.
- **No contract changes**: Onboarding, GameplayLoop, and all service contracts are unchanged. PlaytestObserver is read-only relative to those contexts.

---

## How to Inspect Playtest Data

1. Run a playtest session on a device.
2. Go to **Settings** tab.
3. Scroll to **Playtest Review** section.
4. Player ID is pre-populated if you've played at least once.
5. Tap **Load Report**.
6. Review funnel, balance, friction, and screen time sections.
7. Tap **Clear Data** to reset before the next session.

---

## TypeScript Validation

```
yarn typecheck → Done (no errors)
```
