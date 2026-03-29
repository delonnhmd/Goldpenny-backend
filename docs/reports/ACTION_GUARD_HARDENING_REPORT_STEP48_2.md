# Step 48.2 - Action Guard Hardening

## Scope

Harden meaningful gameplay action paths against duplicate execution, rapid taps, stale preview state, and invalid action ordering without redesigning the UI or adding new gameplay systems.

## Files Changed

- `src/hooks/useDailyProgression.ts`
- `src/lib/api/gameplay.ts`
- `src/hooks/useBackend.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`

## Changes Implemented

### 1. Closed the next-day start race window

`useDailyProgression.markDayStarted()` no longer releases its synchronous guard via `setTimeout(..., 0)`. The guard now unlocks with `queueMicrotask(...)`, which keeps the day-start lock active through the current event/microtask boundary and reduces rapid double-trigger risk during next-day startup.

### 2. Added synchronous execute-action locking

`GameDashboardPage` now uses `executeActionGuardRef` so the preview modal's execute path cannot apply the same action twice before React state has time to disable the button.

Additional protection was added to verify that the action being executed still matches the latest selected action state. If the preview state has shifted, execution is blocked and the player is asked to review the latest preview.

### 3. Added synchronous commitment locks

Commitment activation and cancellation now share `commitmentGuardRef`, preventing duplicate network mutations caused by rapid taps before `commitmentBusy` propagates through React state.

### 4. Added synchronous onboarding locks

Onboarding advance, skip, and complete handlers now share `onboardingGuardRef`, preventing multiple onboarding state transitions from firing concurrently.

### 5. Added real preview cancellation

The gameplay preview API now accepts optional request init data, allowing `AbortController` signals to be passed from `GameDashboardPage`.

When the preview modal closes or a different action is selected:

- the previous preview request is aborted
- stale payloads are prevented from landing in state
- aborted requests quietly exit without surfacing false errors

This complements the existing request-id invalidation guard rather than replacing it.

### 6. Limited noisy backend console logs to development

The legacy backend helper still contains debug request/response logging, but it now only logs in `__DEV__` builds so production output stays quieter.

## Naming Audit

The touched Step 48.2 gameplay files did not introduce any new stale `NNT` / `GNNT` / `UI` naming leakage.

`src/hooks/useBackend.ts` still contains existing legacy API endpoint shapes such as `/airdrop/nnt` and `/airdrop/gnnt`; these were pre-existing backend contract references and were not renamed in this step.

## Validation

### TypeScript

`npx tsc --noEmit`

Result: passed.

### Lint

`npx expo lint`

Result: passed with the existing 10 warnings and 0 errors.

## Residual Risk

- Random event resolution already had hook-level synchronous protection and was not changed here.
- The legacy backend helper still has unrelated unused-symbol warnings that predate this step.
- This step hardens handler entry points and preview cancellation, but it does not redesign the server contract; server-side idempotency remains valuable for any future network-sensitive mutations.