# Step 48.9 — Stock Market Hookup (10 Sector Stocks)

## Summary

Hooked the Expo gameplay dashboard to the canonical daily-close stock market path already present in the backend.

Important backend finding: there are two stock route families in the codebase. The active gameplay-safe path is the `StockDailyPrice` + `StockTradingService` system used by daily progression, daily settlement, daily brief, and net-worth calculations. The Expo hookup uses only that path:

- `GET /stocks/quotes`
- `GET /stocks/portfolio/{player_id}`
- `POST /stocks/buy`
- `POST /stocks/sell`

The parallel `sector-list` route family was intentionally not used after audit because it is not the active daily progression / portfolio source of truth.

---

## Files Reviewed

### Frontend
- `PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx`
- `PFT/pft-expo/src/lib/api/gameplay.ts`
- `PFT/pft-expo/src/types/gameplay.ts`
- `PFT/pft-expo/src/components/gameplay/PlayerStatsBar.tsx`
- `PFT/pft-expo/src/lib/api/economyPresentation.ts`
- `PFT/pft-expo/src/lib/gameplayFormatters.ts`
- `PFT/pft-expo/src/lib/economySafety.ts`

### Backend
- `app/api/stocks.py`
- `app/api/portfolio.py`
- `app/services/stock_trading_service.py`
- `app/services/market_daily_update_service.py`
- `app/services/day_progression_service.py`
- `app/services/daily_settlement_service.py`
- `app/services/daily_brief_service.py`
- `app/engine/stock_engine.py`
- `tests/test_day_progression_services.py`
- `tests/test_admin_debug_service.py`

---

## Files Updated

### Created
- `PFT/pft-expo/src/types/stocks.ts`
- `PFT/pft-expo/src/lib/api/stocks.ts`
- `PFT/pft-expo/src/components/gameplay/StockMarketCard.tsx`
- `STOCK_MARKET_HOOKUP_REPORT_STEP48_9.md`

### Modified
- `PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx`
- `PFT/pft-expo/src/types/business.ts` (minor lint cleanup only)

---

## Minimal Stock / Portfolio Contract Introduced

### `src/types/stocks.ts`

Introduced a minimal app-facing stock model:

- `StockMarketItem`
  - `stock_id`
  - `stock_name`
  - `sector_key`
  - `current_price`
  - `previous_close`
  - `daily_change_pct`
  - `latest_day`
  - `sector_signal_summary`
  - `volatility_label`
  - `can_trade`
  - `holdings_quantity`
  - `holdings_cost_basis`
  - `holdings_market_value`
  - `holdings_unrealized_pnl`

- `StockPortfolioSummary`
  - `available_cash_xgp`
  - `total_market_value_xgp`
  - `total_cost_basis_xgp`
  - `total_unrealized_pnl_xgp`
  - `total_portfolio_value_xgp`
  - `holdings_count`

- `StockMarketSnapshotResponse`
  - `player_id`
  - `latest_day`
  - `stocks[]`
  - `portfolio`

- `StockTradeExecutionResponse`
  - minimal buy/sell execution summary for user feedback and refresh flow

The contract stays deliberately small and app-facing. No intraday fields, no order book, no watchlist, no derived simulation state.

---

## Backend World-State to Stock Mapping Decisions

### Canonical pricing path used
The Expo app now derives stock UI state from:

1. `GET /stocks/quotes`
   - authoritative current daily close
   - authoritative `daily_change_pct`
   - authoritative market day
   - authoritative sector key

2. `GET /stocks/portfolio/{player_id}`
   - authoritative holdings
   - authoritative available cash
   - authoritative market value
   - authoritative unrealized P&L

### Why this path was chosen
This path is the one actively used by:

- `market_daily_update_service.py`
- `day_progression_service.py`
- `daily_settlement_service.py`
- `daily_brief_service.py`
- `stock_trading_service.py`

That makes it the correct gameplay-facing stock source of truth.

### Canonical movement behavior preserved
No frontend pricing logic was added.
The backend still owns:

- daily-only price updates
- macro-driven sector movement
- bounded daily movement cap (`±6%`)
- bounded deterministic noise
- latest close selection for trade execution

### Frontend-only display mapping kept minimal
The frontend adds only small display helpers:

- `previous_close` derived from canonical `current_price` and canonical `daily_change_pct`
- fixed display labels for the 10 fictional tickers
- `sector_signal_summary` generated as UI copy from canonical sector + canonical daily move
- `volatility_label` bucketed from canonical daily move magnitude only

This is presentation logic, not a second stock engine.

---

## Trade Rules Added

### Backend-enforced rules relied on
The Expo app now trades through canonical backend mutation routes that already enforce:

- integer share quantity only
- positive quantity only
- latest available close price only
- sufficient cash required for buys
- sufficient holdings required for sells
- `0.3%` transaction fee
- atomic DB write / rollback behavior

### Frontend safety rules added
`GameDashboardPage.tsx` now adds:

- `stockTradeGuardRef` to block rapid duplicate taps
- `pendingStockTrade` state to disable buttons during an in-flight trade
- day-active gating: no trading after day end
- gameplay-mutation gating: blocks trade while another gameplay update is in progress
- positive whole-number validation on requested share quantity
- no client-sent price field, so stale UI cannot force an outdated execution price

### Trade UX scope kept tight
The UI supports only:

- `Buy 1`
- `Sell 1`
- `Sell All`

No watchlists, leverage, margin, options, alerts, or intraday behavior were added.

---

## UI Surfaces Added / Cleaned

### `src/components/gameplay/StockMarketCard.tsx`
New mobile-friendly stock market card showing:

- portfolio summary (`cash`, `market value`, `unrealized P&L`)
- latest market day reminder
- all 10 fictional stocks
- current price
- daily change
- concise sector signal summary
- holdings quantity / value / unrealized P&L
- simple trade buttons (`Buy 1`, `Sell 1`, `Sell All`)

### `src/pages/gameplay/GameDashboardPage.tsx`
Added:

- `stockMarketState`
- `loadStockMarket()` loader
- `handleTradeStock()` guarded trade mutation flow
- stock market primary dashboard section render
- stock reload on full refresh, post-action refresh, and end-day refresh
- dashboard reload after each stock trade so Daily Brief and cash/net-worth surfaces stay coherent

Placement:
- Stock Market renders in the primary gameplay stack after the business section and before random events / strategy / action hub

---

## Persistence / Anti-Replay Decisions

No new frontend persistence keys were added.

Reason:
- stock holdings and trade execution are already canonical in backend state
- stock prices are canonical backend daily closes
- replay safety is better handled by backend mutation semantics plus frontend tap guards than by duplicating local trade state

Derived portfolio summaries are recomputed from canonical backend responses on load / refresh.

This keeps storage aligned with existing Gold Penny / PFT practice: do not persist derived copies when the backend already owns the truth.

---

## Naming Integrity Findings

Touched files were checked for active runtime naming leftovers such as:

- `nnt-token`
- `UI` legacy naming
- `NNT`
- `GNNT`
- token-era wallet / reward naming
- stale placeholder market naming

Findings:
- No token-era naming was introduced in the touched stock files
- Added stock labels stay in Gold Penny domain (`GP Energy`, `GP Tech`, etc.)
- No runtime-relevant stale naming remained in touched stock files

---

## Validation Results

### Static validation
Ran from `PFT/pft-expo`:

- `npx tsc --noEmit` → `TS_EXIT=0`
- `npx expo lint` → `LINT_EXIT=0`

Repo still has pre-existing lint warnings in unrelated files:
- `src/hooks/useBackend.ts`
- `src/lib/api/progression.ts`
- `src/types/consumerBorrowing.ts`
- `src/types/financialSurvival.ts`

These were not introduced by the stock hookup.

### Editor diagnostics
No TypeScript/editor errors remained in:

- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/lib/api/stocks.ts`
- `src/components/gameplay/StockMarketCard.tsx`
- `src/types/stocks.ts`

### Runtime smoke coverage
Completed:
- stock list render path now compiles cleanly
- buy/sell routes are wired to canonical backend prices only
- dashboard refresh after trade keeps cash / holdings / Daily Brief coherent
- duplicate rapid-tap exploit is guarded in the UI

Not completed:
- manual interactive Expo smoke test was not run from the device/simulator in this session
- live end-to-end trade execution against a running backend was not manually exercised here

---

## Deferred Items

Explicitly deferred to keep scope tight:

- custom quantity picker
- order previews
- trade history UI
- portfolio charts
- watchlists
- alerts
- leverage / margin / shorting
- dividends
- real market APIs
- blockchain / token logic
- richer stock-specific Daily Brief formatter layer

---

## Outcome

The player can now:

- view the 10 fictional sector stocks
- see daily-close prices and daily change
- see holdings and portfolio summary
- buy and sell against canonical backend prices
- refresh portfolio/cash/dashboard state coherently after trades

The stock market layer stays minimal, daily-close only, backend-canonical, and ready for the final core-logic closeout step.
