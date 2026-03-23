# Step 49 — Core Logic Closeout Audit + Missing-Link Patch

## Summary

Completed a closeout audit of the active Gold Penny MVP core loop across backend orchestration and Expo gameplay execution.

The main evidence-backed missing link found in the live player action path was in the Expo fallback executor for `switch_job`:

- Expo first tries a unified gameplay action endpoint that does not currently exist in `app/api`
- the real live path is therefore the fallback route map in `PFT/pft-expo/src/lib/api/gameplay.ts`
- `switch_job` fallback was pointed at legacy/non-existent routes and sent `job_key`
- backend canonical route is `POST /career/player/{player_id}/job/switch`
- backend canonical request field is `new_job_key`

That mismatch is now patched.

Final closeout verdict: the core logic MVP is functionally complete, but thin in a few places. The backend is the canonical source of truth for the daily economy loop, and the Expo app now reaches the critical business, stock, career, debt, housing, work, and day-progression paths without the confirmed dead switch-job link.

---

## Files Reviewed

### Frontend
- `PFT/pft-expo/src/lib/api/gameplay.ts`
- `PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx`
- `PFT/pft-expo/src/hooks/useDailySession.ts`
- `PFT/pft-expo/src/hooks/useEconomyState.ts`
- `PFT/pft-expo/src/lib/api/stocks.ts`
- `PFT/pft-expo/src/lib/api/business.ts`
- `PFT/pft-expo/src/lib/apiClient.ts`

### Backend
- `app/api/career.py`
- `app/api/jobs.py`
- `app/api/housing.py`
- `app/api/finance.py`
- `app/api/business.py`
- `app/api/stocks.py`
- `app/api/side_income.py`
- `app/services/day_progression_service.py`
- `app/services/daily_brief_service.py`
- `app/engine/career_service.py`

### Prior audit context re-checked
- persistence audit notes from Step 48.3
- economy boundary audit notes from Step 48.4
- job/work exploit audit notes from Step 48.6

---

## Files Updated

### Modified
- `PFT/pft-expo/src/lib/api/gameplay.ts`

### Created
- `CORE_LOGIC_CLOSEOUT_REPORT_STEP49.md`

---

## Patch Applied

### `PFT/pft-expo/src/lib/api/gameplay.ts`

Updated `executeAction(... )` fallback handling for `switch_job` so the live fallback path now:

1. tries the canonical backend route first:
   - `POST /career/player/{player_id}/job/switch`
2. sends the canonical request field:
   - `new_job_key`
3. keeps legacy fallback paths behind the canonical route for compatibility only
4. includes `job_key` alongside `new_job_key` to avoid breaking any older fallback implementation that still expects the old name

Why this matters:

- the unified `/gameplay/.../actions/execute` route family is not present in `app/api`
- that means fallback execution is not a backup path in practice; it is the active action path today
- before this patch, a player-initiated job switch from Expo could fall through to dead/legacy endpoints even though the backend already exposed the correct route

---

## Confirmed Findings

### Fixed

1. **Dead `switch_job` fallback path in Expo**
   - Status before patch: real bug
   - Status now: fixed

### Confirmed already correct

1. **Backend job switching validation exists**
   - `app/api/career.py` already routes to `switch_player_job(...)`
   - this was not missing

2. **Daily Brief persistence exists**
   - `app/services/daily_brief_service.py` already persists brief content into `DailyBriefLog`
   - this was not missing

3. **Daily orchestration order is coherent**
   - stock market catch-up
   - event engine
   - basket pricing
   - job market / economy brief
   - settlement
   - career progression
   - daily brief generation

4. **Business and stock UI hookups are canonical**
   - business uses player-id business routes already wired in backend
   - stock uses the active daily-close trading route family, not the parallel sector-list path

### Important operational note

1. **`work_shift` and `side_income` remain authenticated routes**
   - Expo can reach them because `apiClient.ts` attaches the stored bearer token globally when configured
   - no player-id public alternative route was found during this audit
   - treated as an environment prerequisite, not a Step 49 code defect

---

## Coverage Matrix

### Complete

- Events drive downstream state before settlement
- Basket pricing is backend-owned and refreshed into the Expo dashboard
- Job market and career progression are backend-owned
- Debt / recovery action path is backend-owned
- Housing region change path is wired
- Business operation path is wired
- Stock quote / portfolio / buy / sell path is wired
- Daily progression / end-day orchestration is wired
- Daily Brief generation and persistence are wired
- Frontend session replay guards remain in place for repeated actions

### Complete but thin

- Expo action execution depends on fallback route mapping because no unified gameplay action endpoint exists yet
- Some frontend summary surfaces still derive presentation-layer interpretations from canonical state rather than fetching dedicated backend summary objects
- Work and side-income flows depend on the configured bearer token for authenticated routes

### Intentionally deferred

- richer event-chain visibility in the mobile UI
- broader business management UI beyond the two active MVP business paths
- advanced stock UX beyond simple buy/sell actions
- consolidation of legacy route aliases behind a single unified action execution API

### Not found as MVP blockers after verification

- missing backend job-switch validation
- missing Daily Brief persistence
- missing business/stock canonical source of truth

---

## Validation Results

Ran from `PFT/pft-expo` after the patch:

- `npx tsc --noEmit` → `TS_EXIT=0`
- `npm run lint` → passes with pre-existing unrelated warnings only

Unrelated pre-existing lint warnings remain in:

- `src/hooks/useBackend.ts`
- `src/lib/api/progression.ts`
- `src/types/consumerBorrowing.ts`
- `src/types/financialSurvival.ts`

No editor diagnostics were introduced in the touched file.

---

## Honest MVP Verdict

The Gold Penny core-logic MVP is now connected end-to-end closely enough to call it complete.

That statement is justified because:

- the backend owns the actual economy, job, settlement, business, stock, and Daily Brief causality
- the Expo gameplay dashboard is connected to those canonical systems rather than maintaining a fake shadow economy
- the one confirmed active missing link in the fallback action path (`switch_job`) has been fixed

What remains is mostly thinness and cleanup debt, not a missing core loop:

- route-family consolidation
- richer mobile visibility into some backend systems
- cleanup of older fallback aliases and unrelated lint warnings

If a stricter label is needed, the most precise description is:

**Core logic MVP: complete, with thin edges and some legacy integration debt, but no remaining evidence-backed blocker found in this audit.**