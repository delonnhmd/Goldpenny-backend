# Step 46.8 — Random Events + Recovery Action Logic
**Status: Complete**

---

## Overview

Step 46.8 adds a minimal, client-side random-events layer and a lightweight recovery-action system to the Gold Penny Expo active gameplay loop. Events fire deterministically (~50% of days), persist across app restarts, and resolve cleanly when the player takes action or dismisses. No backend API calls are introduced in this step — events are presentational and inform the player of daily volatility without altering authoritative server state.

---

## Files Reviewed

| File | Purpose |
|------|---------|
| `src/pages/gameplay/GameDashboardPage.tsx` | Primary integration target (2400+ line page) |
| `src/hooks/useDailyProgression.ts` | Source of `currentGameDay` for event roll trigger |
| `src/hooks/useEconomyState.ts` | Source of `cashOnHand` for recovery action filtering |
| `src/types/gameplay.ts` | `DailySessionStatus`, `PlayerDashboardResponse` |
| `src/types/economy.ts` | `GameplayEconomyState`, `DebtPressureLevel` |
| `src/lib/ui_layout_config.ts` | Section keys, existing render ordering |
| `src/components/gameplay/DailyBriefCard.tsx` | Style/pattern reference |
| `src/components/gameplay/PrimaryDashboardSection.tsx` | Section wrapper pattern |

---

## Files Created

### `src/types/randomEvent.ts`
Core type definitions for the event system.

```typescript
type EventSeverity = 'low' | 'medium' | 'high'
type EventCategory = 'expense' | 'income' | 'debt' | 'life'

interface RandomEventDefinition { /* eventId, category, title, description, effectSummary, cashDelta, expenseDelta, debtDelta, severity */ }
interface ActiveRandomEvent extends RandomEventDefinition { /* sourceDay, isResolved */ }
interface RecoveryActionDefinition { /* recoveryActionId, label, effectSummary, cashCost, cashGain, debtReduction, minCashRequired */ }
interface RandomEventPersistedState { /* eventId, sourceDay, isResolved */ }
```

### `src/lib/gameEvents.ts`
Event pool, recovery action pool, roll function, and affordability filter.

**Event Pool (8 events):**
| ID | Category | Effect | Severity |
|----|----------|--------|----------|
| `unexpected_bill` | expense | -75 xgp cash | medium |
| `extra_shift` | income | +50 xgp cash | low |
| `minor_debt_fee` | debt | +30 xgp debt | low |
| `car_repair` | expense | -120 xgp cash | high |
| `grocery_spike` | expense | -25 xgp cash | low |
| `side_income_surprise` | income | +40 xgp cash | low |
| `missed_opportunity` | life | -15 xgp cash | low |
| `financial_relief` | debt | -40 xgp debt | low |

**Recovery Action Pool (5 actions):**
| ID | Effect | Min Cash |
|----|--------|----------|
| `cut_spending` | +30 xgp (saved) | 0 |
| `rest` | None (morale) | 0 |
| `debt_payment` | -50 xgp cash / -60 xgp debt | 50 |
| `quick_side_hustle` | +45 xgp cash | 0 |
| `skip_optional_expense` | +20 xgp (saved) | 0 |

**`rollDailyEvent(playerId, gameDay)`:** Deterministic non-cryptographic hash using `playerId:gameDay` as seed. Lowest bit = fire/no-fire (~50% chance). Upper bits select pool index. Same player+day always produces the same event or null.

**`getAvailableRecoveryActions(cashOnHand)`:** Filters `RECOVERY_ACTION_POOL` by `minCashRequired ≤ cashOnHand`.

### `src/hooks/useRandomEvent.ts`
Full hook with AsyncStorage persistence, day-change detection, and resolve logic.

- **Storage key:** `goldpenny:gameplay:event:${playerId}`
- **Persisted shape:** `{ eventId, sourceDay, isResolved }` (minimal)
- **`processedDayRef`:** Prevents duplicate roll if hook re-renders within same day
- **`cancelled` flag:** Guards async effect against React Strict Mode double-invocation
- **On day change:** Loads storage → restores event if same day and not resolved → rolls fresh if not found
- **`resolveEvent()`:** Sets state to `null`, marks `isResolved: true` in storage
- **Re-mount safety:** `isResolved: true` in storage prevents re-showing a resolved event after navigation

Exports: `RandomEventContract` interface and `useRandomEvent(playerId, currentGameDay, cashOnHand)` returning `{ activeEvent, availableRecoveryActions, applyRecoveryAction, dismissEvent }`.

### `src/components/gameplay/RandomEventCard.tsx`
UI card component.

- **Props:** `{ event, availableRecoveryActions, onApplyRecoveryAction, onDismiss }`
- **Tone derivation:** `positive` (income), `negative_high` (high severity), `negative_medium` (medium), `negative_low` (low)
- **Tone styles:** green / red / amber / gray
- **Renders:** severity badge, title, description, effect summary (color-coded), up to 3 recovery action buttons, dismiss button

---

## Files Modified

### `src/pages/gameplay/GameDashboardPage.tsx`

**Imports added:**
```typescript
import RandomEventCard from '@/components/gameplay/RandomEventCard';
import { useRandomEvent } from '@/hooks/useRandomEvent';
```

**Hook call added** (after `useDailyProgression`, before render section):
```typescript
const randomEvent = useRandomEvent(
  playerId,
  dailyProgression.currentGameDay,
  economyState.cashOnHand,
);
```

**Render block added** (between `daily_brief` section and `strategic_recommendation` section):
```jsx
{randomEvent.activeEvent && dailySession.sessionStatus === 'active'
  ? wrapSection('random_event',
      <PrimaryDashboardSection
        title="Today's Event"
        summary={`${randomEvent.activeEvent.title} — ${randomEvent.activeEvent.effectSummary}`}
      >
        <RandomEventCard
          event={randomEvent.activeEvent}
          availableRecoveryActions={randomEvent.availableRecoveryActions}
          onApplyRecoveryAction={(action) => {
            randomEvent.applyRecoveryAction(action.recoveryActionId);
            setFeedback({ tone: 'info', message: `${action.label}: ${action.effectSummary}` });
          }}
          onDismiss={randomEvent.dismissEvent}
        />
      </PrimaryDashboardSection>)
  : null}
```

**Visibility rule:** Card renders only when `activeEvent !== null && sessionStatus === 'active'`. Not gated through `isSectionVisible` — intentionally bypasses onboarding gate so events always appear during active play.

---

## Design Decisions

### Client-Side Only (This Step)
Events carry `cashDelta`/`expenseDelta`/`debtDelta` fields as informational display values. They describe what conceptually happened, but do not mutate local React state or make backend API calls. The authoritative backend effects are deferred to a future step where these values can be sent as a settlement payload at day-end.

### Deterministic Roll
Using `playerId:gameDay` as a hash seed ensures that if the player reloads midday, the same event re-rolls. This prevents the event from "changing" between sessions, keeping the experience coherent without needing server storage.

### Recovery Actions Are Presentational
Applying a recovery action dismisses the event and shows a feedback snackbar. No local numeric state mutation occurs. The label and effect summary give the player a sense of agency and information about what they chose. Backend settlement is deferred.

### Affordability Filtering
`debt_payment` requires ≥50 xgp cash. `getAvailableRecoveryActions()` filters in real time from live `cashOnHand`, so the debt_payment button only appears when the player can actually afford it.

### Session Visibility Guard
Events are suppressed when `sessionStatus !== 'active'`. Players who haven't started the day, or who have ended the day, do not see an event card.

---

## Naming Integrity Check

All 4 new files searched for: `nnt-token`, `GNNT`, `NNT`, `nnt_`

**Result: Clean — no legacy naming found.**

---

## Validation

| Check | Result |
|-------|--------|
| `npx tsc --noEmit` | ✅ 0 errors |
| `npx expo lint` | ✅ 0 errors, 12 warnings (all pre-existing) |
| Naming integrity | ✅ Clean |

---

## Deferred to Future Steps

- **Backend wiring:** Send `cashDelta`/`debtDelta` to a server endpoint at day-end to apply authoritative effects
- **Server-side event generation:** Move roll logic to backend so events reflect real economic state (not just local hash)
- **Richer recovery mechanics:** Recovery actions that call `/economy/adjust` or `/debt/reduce` in real time
- **Event history:** Log resolved events so players can review past volatility
- **Event weighting:** Bias event pool based on player's current debt pressure or economic tier
