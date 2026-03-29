# STEP74 — Action-First Gameplay + Remove Duplication + Housing, Food, Loan Systems

## Summary

Step 74 delivers three major upgrades to the GoldPenny gameplay loop:
1. **Action-First UI** — every screen leads with what the player can *do*, not passive stats.
2. **Signal Deduplication** — Opportunity and Risk signals now live only in the Brief screen; all other screens have been cleaned.
3. **Survival Systems** — Housing selection, Food (meals), and Emergency Loans are now fully playable.

---

## Part 1: Backend — New Action Handlers (`app/api/gameplay.py`)

### `eat_meal`
- **Cost**: 6 XGP (configured via `MEAL_COSTS` dict for breakfast / lunch / dinner)
- **Effect**: +5 health, −3 stress
- **Guard**: raises HTTP 422 if `player.cash < meal_cost`
- **Preview**: returns cost, health gain, stress change

### `quick_loan`
- **Amount**: 100–500 XGP (clamped in backend)
- **Interest**: 15% flat — player receives `loan_amount`, owes `loan_amount × 1.15`
- **Effect**: +loan_amount to `player.cash`, +loan_amount×1.15 to `player.debt_xgp`, +5 stress
- **Preview**: returns loan amount, repayment amount, stress cost

### `select_housing`
- **Options**: `suburban` or `downtown`
- **Effect**: updates `player.region` and `player.housing_region_id`
- **Returns**: full `HOUSING_INFO` dict for the chosen region (rent, gas, stress modifier)

---

## Part 2: Frontend Context (`src/features/gameplayLoop/context.tsx`)

Three new methods added to `GameplayLoopContextValue` and implemented via `executeAction`:

| Method | Action Key | Params |
|---|---|---|
| `eatMeal(mealType)` | `eat_meal` | `{ meal_type }` |
| `takeLoan(amount)` | `quick_loan` | `{ loan_amount }` — clamped 100–500 |
| `selectHousing(housingType)` | `select_housing` | `{ housing_type }` |

---

## Part 3: Signal Deduplication

`GameplayOpportunityCallout` and `GameplayWarningBanner` signals were removed from all non-Brief screens. Signals now live **only in BriefScreen** which is the designated signal hub.

| Screen | Change |
|---|---|
| **DashboardScreen** | Removed `PlayerStatsBar`, opportunity/risk callouts, "Most important next action" row |
| **WorkScreen** | Removed `leadTradeoff` (Best Setup Right Now) and `leadWarning` (Watch Before Acting) callouts |
| **MarketScreen** | Removed `topOpportunity` and `topWarning` callouts; simplified basket section title |
| **BusinessScreen** | Removed `topUpside` opportunity callout; kept warning only for `pressured`/`high` margin |

---

## Part 4: Action-First Dashboard (`src/features/gameplayLoop/screens/DashboardScreen.tsx`)

Complete rewrite. The new Dashboard:
- Shows 4 quick-action buttons as the **primary content**: Go To Work, Eat a Meal, Check Market, Housing / Loan
- Uses `GameplayCompactMetricRows` for a compact 6-metric status grid (cash, flow, debt, health, stress, pressure)
- Shows contextual warnings only when `cash < 50` or `stress >= 70`
- Footer: "Check Market" secondary + "Go To Work" primary — no more summary text filler

---

## Part 5: New Life Screen (`src/features/gameplayLoop/screens/LifeScreen.tsx`)

New screen routing to `app/gameplay/loop/[playerId]/life.tsx`.

**Housing Section**
- Two housing cards: Suburban (rent 80 XGP/wk, gas 40 XGP/wk, −2 stress) vs Downtown (rent 140 XGP/wk, gas 20 XGP/wk, +5 stress)
- Active home shows "Current home" label; inactive shows "Move here" button → calls `loop.selectHousing()`
- Current housing read from `stats.region_key`

**Food Section**
- Three buttons: Breakfast / Lunch / Dinner — each costs 6 XGP, calls `loop.eatMeal()`
- Disabled when `cash < 6` or action in progress; shows "Not enough cash" warning banner

**Loan Section**
- Amount selector: 100 / 200 / 300 / 500 XGP (active amount shown as PrimaryButton)
- Live repayment preview: "You will receive X XGP and owe Y XGP (+15% flat)"
- Borrow button calls `loop.takeLoan(amount)`
- Warning banner when existing debt > 200 XGP

**Footer**: "Back To Work" primary + "Open Dashboard" secondary

---

## Part 6: Navigation Changes

### `src/features/onboarding/context.tsx`
- Added `'life'` to `OnboardingRouteKey` union type
- Added `if (route === 'life') return 'Life'` to `navLabel()`
- Excluded `'life'` from `GuidedRouteKey` (same as `'business'`) — Life tab is hidden during onboarding

### `src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- Added `{ key: 'life', label: 'Life' }` to `bottomNavItems`
- Added `item.key === 'life'` to onboarding filter (hides Life tab during guided flow)

---

## Part 7: Compact Header

`src/components/layout/TopBar.tsx`:
- Title font: `headingLg` (22px) → `headingMd` (18px)
- Header padding: `paddingVertical: spacing.md` (12px) → `spacing.sm` (8px)

This reduces the persistent header height across all gameplay screens, giving more space to content.

---

## Files Modified

| File | Change Type |
|---|---|
| `goldpenny-backend/app/api/gameplay.py` | +3 execute handlers, +3 preview handlers |
| `PFT/pft-expo/src/features/gameplayLoop/context.tsx` | +3 context methods |
| `PFT/pft-expo/src/features/gameplayLoop/screens/DashboardScreen.tsx` | Full rewrite — action-first |
| `PFT/pft-expo/src/features/gameplayLoop/screens/WorkScreen.tsx` | Removed duplicate callouts, plain language stats |
| `PFT/pft-expo/src/features/gameplayLoop/screens/MarketScreen.tsx` | Removed duplicate signals |
| `PFT/pft-expo/src/features/gameplayLoop/screens/BusinessScreen.tsx` | Removed duplicate opportunity callout |
| `PFT/pft-expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx` | Added Life nav item, onboarding filter |
| `PFT/pft-expo/src/features/onboarding/context.tsx` | Added `'life'` to route key type |
| `PFT/pft-expo/src/components/layout/TopBar.tsx` | Compact header (smaller font + padding) |

## Files Created

| File | Purpose |
|---|---|
| `PFT/pft-expo/src/features/gameplayLoop/screens/LifeScreen.tsx` | Housing / Food / Loan screen |
| `PFT/pft-expo/app/gameplay/loop/[playerId]/life.tsx` | Expo Router route for Life tab |

---

## Gameplay Economy Rules Applied

| Action | Cost | Effect |
|---|---|---|
| Eat meal (any) | 6 XGP | +5 health, −3 stress |
| Quick loan 100 | 0 XGP cost | +100 cash, +115 debt, +5 stress |
| Quick loan 200 | 0 XGP cost | +200 cash, +230 debt, +5 stress |
| Quick loan 300 | 0 XGP cost | +300 cash, +345 debt, +5 stress |
| Quick loan 500 | 0 XGP cost | +500 cash, +575 debt, +5 stress |
| Move to Suburban | 0 XGP | rent 80/wk, gas 40/wk, −2 stress/wk |
| Move to Downtown | 0 XGP | rent 140/wk, gas 20/wk, +5 stress/wk |
