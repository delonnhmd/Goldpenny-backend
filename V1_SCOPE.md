# SHIPS IN V1

- User auth via `expo/app/auth/*` and backend `auth`: email/password signup, login, password reset, session restore, and create-player flow.
- App entry and support routes: `expo/app/index.tsx`, `expo/app/(tabs)/index.tsx`, `expo/app/(tabs)/settings.tsx`, and `expo/app/account/index.tsx`.
- Core gameplay routes under `expo/app/gameplay/*` and `expo/app/gameplay/loop/[playerId]/*`: map, dashboard, work, life, brief, market, business, summary, and existing wallet shell with no payout actions.
- Map-first gameplay UI in `expo/src/features/gameplayLoop`: `GameplayLoopScaffold`, `MapDashboardScreen`, map nodes, detail sheet, bottom nav, and player status surfaces.
- Backend player lifecycle APIs: `onboarding`, `player`, `gameplay`, `daily`, `day`, `briefs`, `jobs`, `side_income`, `guided_sandbox`, `soft_launch`, and `internal`.
- Work and time systems: main job shifts, salary posting, rideshare trips, per-job progression, day settlement, time budget, and end-of-day summary.
- Life pressure systems: needs, baskets, health, housing, debt, consumer borrowing, financial survival, personal shocks, and recovery.
- Economy systems already wired into gameplay: macro state, basket prices, economy presentation, daily events, supply chain pressure, population pressure, contract timing, and debt behavior.
- Wealth and business systems: stocks, portfolio, market, business ownership, marketplace listings, co-op deals, firm/job openings, net worth, wealth progression, reputation, commitment, and world memory.
- Soft-launch operations: invite/access controls, feedback/issue reporting, QA settings, admin/debug endpoints, backend compile checks, and Expo typecheck.

# DOES NOT SHIP IN V1

- `expo/app/referral/` - deleted; referral growth is not part of V1 retention validation.
- `expo/app/claim/` - deleted; token claim UI is pre-crypto scope creep.
- `/rewards` router and token/reward claim backend stack - deleted; claim tables, claim models, reward claim engine, wallet-link model, token config, and claim docs are removed.
- `expo/app/post/` - frozen; empty legacy social/post route with no V1 player loop.
- `expo/app/leaderboard/` - frozen; empty ladder route with no scoring, cohort, or reward contract yet.
- `expo/app/admin/` - frozen; empty mobile admin route duplicating Settings and backend internal tools.
- `expo/app/user/` - does not ship; empty legacy profile route with no current entry point.
- `expo/web-bridge/` - does not ship as a player feature; future token/web bridge stays on hold before crypto.
- Forecasting and strategic-planning expansion - no new V1 work; existing internal APIs may remain, but no new player-facing planning depth before launch.
- New simulation depth - no new formulas, macro systems, or economic layers before V1 retention is proven.
- Crypto, on-chain payouts, token marketing, airdrops, and wallet actions - no V1 release.

This document is law until launch. Changes require deleting something else of equal weight.
