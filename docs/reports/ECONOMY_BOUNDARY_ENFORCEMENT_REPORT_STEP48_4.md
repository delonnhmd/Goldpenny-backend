# Step 48.4 - Economy Boundary Enforcement

## Scope

Harden the active Gold Penny economy runtime so cash, debt, income, expense, event, recovery, and day-budget math remain finite, bounded, and coherent under invalid backend data, partial hydration, and edge-case input timing.

## Files Reviewed

- `src/lib/api/gameplay.ts`
- `src/lib/gameplayRuntimeState.ts`
- `src/hooks/useEconomyState.ts`
- `src/hooks/useExpenseDebt.ts`
- `src/hooks/useJobIncome.ts`
- `src/hooks/useDailySession.ts`
- `src/hooks/useRandomEvent.ts`
- `src/lib/gameEvents.ts`
- `src/lib/balanceConfig.ts`
- `src/lib/gameplayFormatters.ts`
- `src/pages/gameplay/GameDashboardPage.tsx`

## Files Updated

- `src/lib/economySafety.ts`
- `src/lib/balanceConfig.ts`
- `src/lib/gameplayFormatters.ts`
- `src/lib/gameplayRuntimeState.ts`
- `src/hooks/useEconomyState.ts`
- `src/lib/gameEvents.ts`
- `src/hooks/useRandomEvent.ts`
- `src/lib/api/gameplay.ts`
- `src/hooks/useDailySession.ts`

## Invalid Math Risks Found

### 1. API normalization accepted malformed numbers too easily

Gameplay API normalization previously converted values with permissive `Number(...)` fallback logic, which could hide invalid backend values and allow unsafe numbers into canonical runtime state.

### 2. Canonical runtime extraction trusted normalized data too loosely

`createGameplayCanonicalState(...)` still rebuilt core economy values with direct `Number(...)` coercion, which meant bad or partial inputs could re-enter the canonical runtime layer even after API normalization.

### 3. Derived economy logic treated unknown values as ordinary numeric zero

`deriveEconomyStatus(...)` used `(netCashFlow ?? 0)`, which treated missing end-of-day cash flow like a real break-even number instead of an unknown pending state.

### 4. Event and recovery definitions were not explicitly bounded

Random event and recovery payload constants were centralized, but nothing validated them before those values were surfaced to runtime logic.

### 5. Recovery action acceptance did not re-check local affordability

The event hook exposed only currently affordable recovery actions, but handler-level validation did not reject invalid or stale recovery action IDs before resolving the event.

### 6. Day-budget normalization could round upward

Daily total time normalization used rounding rather than a shared bounded floor-based helper, which could overgrant time units from noisy inputs.

## Invariants Enforced

The runtime now enforces these practical invariants:

- canonical numeric economy values must be finite
- `currentDay` must be a positive bounded integer-like value
- `debtAmount` must not be negative in frontend canonical state
- `expenseAmount` and `incomeAmount` must not be negative in frontend canonical state
- `cashOnHand` and `netWorthAmount` may be negative if provided, but are bounded to a sane absolute range
- percentage-like stats such as `stress` and `health` are clamped to `0..100`
- `credit_score` is clamped to `300..850`
- time-cost values are clamped to the configured action range
- preview/action/event deltas are clamped to sane finite ranges
- net cash flow is derived safely from canonical income/expense when a reported value is missing or suspicious

## Caps, Floors, and Normalization Added

### Shared safety limits

Added in `src/lib/balanceConfig.ts`:

- `MAX_ABSOLUTE_XGP`
- `MAX_ABSOLUTE_DELTA_XGP`
- `MIN_PERCENTAGE_STAT`
- `MAX_PERCENTAGE_STAT`
- `MIN_CREDIT_SCORE`
- `MAX_CREDIT_SCORE`
- `MIN_TIME_COST_UNITS`
- `MAX_TIME_COST_UNITS`
- `MAX_GAME_DAY`
- `MAX_NET_CASHFLOW_MISMATCH_XGP`

### Shared helper layer

Added in `src/lib/economySafety.ts`:

- `normalizeFiniteNumber(...)`
- `normalizeMoneyValue(...)`
- `normalizeOptionalMoneyValue(...)`
- `clampDeltaRange(...)`
- `normalizePercentageStat(...)`
- `normalizeCreditScore(...)`
- `normalizeCurrentDay(...)`
- `normalizeTimeUnits(...)`
- `normalizeTimeCostUnits(...)`
- `safeNetCashFlowCalculation(...)`

## Helper Centralization Decisions

Boundary logic was centralized rather than duplicated.

Applied at these layers:

- API ingress in `src/lib/api/gameplay.ts`
- canonical runtime extraction in `src/lib/gameplayRuntimeState.ts`
- derived economy classification in `src/hooks/useEconomyState.ts`
- display formatter safety in `src/lib/gameplayFormatters.ts`
- event and recovery definition sanitation in `src/lib/gameEvents.ts`
- local recovery validation in `src/hooks/useRandomEvent.ts`
- daily time-budget normalization in `src/hooks/useDailySession.ts`

## Persistence and Hydration Interaction Notes

- Step 48.3 canonical gameplay persistence remains the source of local day/session/event continuity.
- This step ensures invalid persisted numeric values cannot poison runtime economy display logic because runtime extraction and formatter paths now normalize all economy-facing numbers again.
- Derived economy outputs continue to recompute from canonical runtime state rather than trusting saved display strings.

## Action-Order and Mutation Safety Notes

- Action execution time costs are clamped at the API normalization layer before they are written into local action history.
- End-of-day summary numbers now normalize earned, spent, and net values with mismatch protection.
- Recovery action acceptance now rechecks local affordability and active-event validity before resolving the event.
- Day-budget normalization now uses a bounded helper that avoids accidental upward rounding.

## Naming Integrity Findings

- No `nnt-token`, `NNT`, or `GNNT` runtime naming leakage was introduced in the touched economy files.
- No old token-era wallet or reward naming needed runtime correction in this step.
- A generic `UI` word appears only in existing non-legacy descriptive comments and not as stale naming context that affects runtime behavior.

## Validation Results

### TypeScript

`npx tsc --noEmit`

Result: passed.

### Lint

`npx expo lint`

Result: passed with the existing 10 warnings and 0 errors.

## Deferred Risks

- Frontend normalization can bound or sanitize invalid backend values, but it cannot prove backend correctness; true economic integrity still benefits from server-side validation and idempotency.
- Action result payloads still depend on backend contract shape, so newly introduced backend fields would need to be added to the normalization layer before they influence local UI summaries.
- Interactive device-level verification of rapid reloads around work, day-end, and recovery flows was not run in this environment; this step was validated through code-path hardening and static checks.