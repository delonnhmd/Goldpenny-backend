# Step 48.8 — Business Path Hookup (Fruit Shop + Food Truck)

## Summary

Wired the two MVP business paths (Fruit Shop and Food Truck) into the primary gameplay loop. The backend already had full business operation infrastructure via Step 15 player-id routes. This step adds the frontend surface that connects player business state, real-time world-economy signals, and the daily operate action into a primary dashboard card.

---

## Files Created

### `src/types/business.ts`
Canonical business types consumed by the frontend. Source of truth: backend Step 15 routes.

- `BusinessTypeKey` — `'fruit_shop' | 'food_truck'`
- `PlayerBusinessRecord` — per-business state: `business_type`, `is_active`, `level`, `inventory_*_units`, `operating_mode`, `last_operated_on`, `cash_invested_xgp`, `reputation`
- `BusinessProfitSnapshot` — aggregated profit: `latest_daily_profit_xgp`, `trailing_7d_profit_xgp`, `business_type_breakdown[]`
- `PlayerBusinessesResponse` — full response from `GET /business/player/{player_id}`

### `src/lib/api/business.ts`
Frontend API client for the business path.

- `getPlayerBusinesses(playerId)` — calls `GET /business/player/${playerId}` (no auth required, consistent with existing `operate_business` integration)

### `src/components/gameplay/BusinessOperationsCard.tsx`
New interactive primary card rendered once per active business.

**Props:**
- `activeRecord: PlayerBusinessRecord` — the player's active business
- `profitSnapshot: BusinessProfitSnapshot | null` — aggregated profit data
- `margins: BusinessMarginItem | null` — real-time margin signals from economy presentation layer
- `plan: BusinessPlanItem | null` — horizon recommendation from strategic planning layer
- `operatedToday: boolean` — session-persisted action count gate
- `sessionActive: boolean` — day still open
- `isExecuting: boolean` — global executing state
- `onOperate: () => void` — fires `handleOperateBusiness` in the parent

**Display:**
1. Business name + operating mode badge
2. Economy signals row: margin outlook (color-coded), demand outlook, cost pressure (color-coded)
3. Short explainer from margins
4. Horizon recommendation from plan (blue)
5. Top risk + top opportunity bullet from margins
6. Inventory levels (produce / essentials / protein — non-zero only)
7. Latest daily profit / 7-day trailing average from profit snapshot
8. "Run Business Today" / "Operated Today ✓" / "Day ended" states

---

## Files Modified

### `src/pages/gameplay/GameDashboardPage.tsx`

**Imports added:**
- `BusinessOperationsCard` from new component
- `getPlayerBusinesses` from new API module
- `PlayerBusinessesResponse` from new types module

**State added:**
- `playerBusinessesState: SectionState<PlayerBusinessesResponse>` — tracks the player's businesses

**Loader added:**
- `loadPlayerBusinesses` — calls `getPlayerBusinesses(playerId)`, sets `ready` if any `is_active`, `empty` otherwise

**loadAll / refreshAfterAction / handleEndDay** — `loadPlayerBusinesses` added to each Promise.allSettled refresh block and corresponding deps arrays. In `refreshAfterAction`, added at the END of the array to preserve the `results[4]` (progression) and `results[19]` (commitment summary) index references.

**useMemos added (after `businessStatusLabel`):**
- `activeBusinessRecord` — first `is_active` business from `playerBusinessesState.data`
- `businessMarginForActive` — `businessMarginsState.data.items` match on `business_key === activeBusinessRecord.business_type`
- `businessPlanForActive` — `businessPlanState.data.items` match on same key
- `businessOperateSummary` — display summary for `PrimaryDashboardSection` title bar

**Callback added:**
- `handleOperateBusiness` — follows the same pattern as `handleExecuteSelectedAction`:
  - `executeActionGuardRef.current` race guard (existing ref, no new state)
  - `dailySession.canExecuteAction({ action_key: 'operate_business' })` guard
  - Calls `onExecuteAction('operate_business', {})` (which handles onboarding check + backend dispatch)
  - `dailySession.consumeTime()` + `addActionToHistory()` (success + failure paths both recorded)
  - `refreshAfterAction('operate_business')` — triggers full ecosystem refresh
  - Structured error handling with `recordError` + user feedback

**Render:**
`BusinessOperationsCard` is inserted between the `dashboardState.ready` block (player_stats + daily_brief) and the `randomEvent` section. It renders only when `activeBusinessRecord !== null` — i.e., the player has an active business.

---

## Key Design Decisions

1. **No new backend routes.** `operate_business` was already wired to `POST /business/player/${playerId}/operate` in `lib/api/gameplay.ts`. Only `GET /business/player/${playerId}` is new (for business state display).

2. **Economy signals stay canonical.** All margin/demand/cost data is derived from `businessMarginsState` (already loaded via `loadEconomyOverviewWithFallback`) and `businessPlanState` (already loaded in all refresh cycles). Zero new economy data loading.

3. **Session anti-replay is unchanged.** `BALANCE.ACTION_CAPS.operate_business = 1` in `useDailySession` still enforces the daily cap. The `operatedToday` prop is `dailySession.getActionCount('operate_business') >= 1` — persisted across reloads.

4. **`executeActionGuardRef`** is the existing ref at line 525 — no new ref created. Prevents race conditions on double-tap.

5. **Index-safe append to `refreshAfterAction`.** `loadPlayerBusinesses()` appended at end of array, preserving `results[4]` = progression and `results[19]` = commitment summary index references.

6. **Render placement.** Card appears in primary section after Daily Brief but before the Random Event — visible enough to act on without displacing critical engagement surfaces.

---

## Not In Scope (Deferred)

- Business upgrade / level-up flow
- Inventory purchase UI (`buy_inventory` action — backend wired, UI deferred)
- Multi-business support (current card shows first active only)
- Business creation / starter onboarding
- Per-business profit breakdown drill-down
