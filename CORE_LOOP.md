# CORE LOOP

## Existing Mechanics

Note: `backend/app/services/forecasting_planning_service.py` is not present in the repo. The existing planning layer is `backend/app/engine/forecasting_planning_service.py`, and `V1_SCOPE.md` freezes forecasting/planning expansion, so it is inventory only.

- [backend/app/services/daily_brief_service.py] — Player receives a day-specific economy headline, short brief, and action hints.
- [backend/app/services/guided_sandbox_service.py] — Player receives day 1-5 nudges: work a shift, buy food, review jobs, inspect business, visit bank/save.
- [backend/app/engine/forecasting_planning_service.py] — Player can be shown projections and scenario comparisons, but this is not a V1 loop driver.
- [backend/app/engine/basket_engine.py] — Player buys baskets/meals with validated unit price, total cost, and affordability.
- [backend/app/engine/business_balance_engine.py] — Player business outcomes reflect demand, saturation, overhead, margin pressure, spoilage, reputation, and streak.
- [backend/app/engine/business_engine.py] — Player starts, operates, upgrades, inventories, and closes businesses.
- [backend/app/engine/coop_deal_engine.py] — Player creates, joins, completes, or expires co-op deals with role qualification and payout splits.
- [backend/app/engine/daily_engine.py] — Player settles the day, gets recovery/pressure changes, and advances to the next day.
- [backend/app/engine/day_engine.py] — Player day state tracks actions taken, earned amount, and reset work limits.
- [backend/app/engine/economy_engine.py] — Player-facing economy factors update daily from macro state and price factors.
- [backend/app/engine/firm_engine.py] — Player sees job-market pressure through NPC firms, openings, wages, distress, and market share.
- [backend/app/engine/housing_balance_engine.py] — Player housing pressure reflects affordability, maintenance, mortgage, stress, delinquency, and burden.
- [backend/app/engine/housing_engine.py] — Player selects housing, pays housing costs, manages housing debt, and sees housing history.
- [backend/app/engine/macro_engine.py] — Player economy changes through inflation, employment, basket prices, seasonality, and macro history.
- [backend/app/engine/marketplace_engine.py] — Player lists and buys market items with listing fees, transaction fees, expiry, and trade history.
- [backend/app/engine/needs_engine.py] — Player food and daily needs affect survival score and settlement modifiers.
- [backend/app/engine/retention_engine.py] — Player receives pressure flags, action hints, return-trigger messages, and computed streak bonus.
- [backend/app/engine/rideshare_engine.py] — Player chooses rideshare trips with oil-sensitive pay, duration, stress, health, time cost, and seeded trip variance.
- [backend/app/engine/settlement_engine.py] — Player settlement hooks can reconcile market transactions.
- [backend/app/engine/stock_engine.py] — Player buys and sells sector stocks, pays trade fees, and sees portfolio value move with daily prices.
- [backend/app/engine/work_engine.py] — Player works limited shifts for wages, XP, stress, health, time cost, and career progress.
- [backend/app/api/gameplay.py] — Player sees recommended, available, and blocked actions, previews tradeoffs, executes actions, ends the day, and retrieves summaries.
- [expo/src/lib/businessSandbox.ts] — Player sees business listings, lot demand, growth phases, active business profile, location modifiers, and next-stage labels.
- [expo/src/lib/gameEvents.ts] — Player can receive deterministic daily random events such as bills, extra shift, grocery spike, relief, or side-income surprise.
- [expo/src/lib/playtestAnalytics.ts] — Player sessions are measured for brief seen, work action, market seen, day completed, business viewed, friction, and first-action timing.
- [expo/app/(tabs)/index.tsx] — Player app entry redirects into gameplay.
- [expo/app/(tabs)/settings.tsx] — Player/operator can manage backend override, diagnostics, balance preset, updates, and playtest report.
- [expo/app/account/index.tsx] — Player manages account, linked player profile, create-player path, and logout.
- [expo/app/auth/login.tsx] — Player signs in with email and password.
- [expo/app/auth/signup.tsx] — Player creates an account.
- [expo/app/auth/create-player.tsx] — Player links or creates a player profile before gameplay.
- [expo/app/auth/forgot-password.tsx] — Player requests password recovery.
- [expo/app/auth/reset-password.tsx] — Player completes password reset.
- [expo/app/gameplay/index.tsx] — Player is routed to the current gameplay loop.
- [expo/app/gameplay/[playerId].tsx] — Player ID route verifies ownership and redirects into the loop.
- [expo/app/gameplay/loop/[playerId]/_layout.tsx] — Player loop is wrapped with gameplay, playtest, and onboarding providers.
- [expo/app/gameplay/loop/[playerId]/brief.tsx] — Player brief route redirects to Life.
- [expo/app/gameplay/loop/[playerId]/business.tsx] — Player opens the Business screen.
- [expo/app/gameplay/loop/[playerId]/dashboard.tsx] — Player dashboard route redirects to Work.
- [expo/app/gameplay/loop/[playerId]/index.tsx] — Player loop index redirects to Life.
- [expo/app/gameplay/loop/[playerId]/life.tsx] — Player sees Daily Brief, cash/stress/health/debt, food, housing, loans, activity, and day settlement controls.
- [expo/app/gameplay/loop/[playerId]/map.tsx] — Player opens the map-first action surface.
- [expo/app/gameplay/loop/[playerId]/market.tsx] — Player opens Portfolio and stocks.
- [expo/app/gameplay/loop/[playerId]/summary.tsx] — Player summary route currently redirects to Life.
- [expo/app/gameplay/loop/[playerId]/wallet.tsx] — Player wallet route renders Portfolio.
- [expo/app/gameplay/loop/[playerId]/work.tsx] — Player opens work status, job market, and training.
- [expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx] — Player sees the shared status bar, bottom nav, provider loading/error states, and summary auto-open attempt.
- [expo/src/features/gameplayLoop/navigation.ts] — Player navigates between Map, Life, Work, Business, and Portfolio.
- [expo/src/components/gameMap/PlayerStatusBar.tsx] — Player sees cash, stress, health, and day on the shared HUD.
- [expo/src/components/gameplay/DailyBriefCard.tsx] — Player sees animated Daily Brief headline, summary, and impact bullets.
- [expo/src/components/gameplay/EndOfDaySummaryCard.tsx] — Player sees earned/spent/net, settlement breakdown, main gain/loss, pressure deltas, warnings, and tomorrow focus.
- [expo/src/features/gameplayLoop/screens/LifeScreen.tsx] — Player reads the brief, checks condition and transactions, buys food/borrows/selects housing, runs settlement, and starts next day.
- [expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx] — Player taps map nodes for work, rideshare, food, travel, job/training, business placement, inventory, and lot actions.
- [expo/src/features/gameplayLoop/screens/WorkScreen.tsx] — Player checks work status, salary state, shift availability, job board, and training.
- [expo/src/features/gameplayLoop/screens/BusinessScreen.tsx] — Player reviews starter businesses, opens map site selection, operates business, buys inventory, and sees operating results.
- [expo/src/features/gameplayLoop/screens/MarketScreen.tsx] — Player checks cash, stocks, land, business, inventory, debt, net worth, basket prices, and buys/sells stocks.
- [expo/src/features/gameplayLoop/screens/SummaryScreen.tsx] — Player can run settlement and view closeout if rendered, but the active route redirects to Life.

## 60-Second Loop

Action: Open the app through [expo/app/(tabs)/index.tsx] and [expo/app/gameplay/index.tsx], land in Life via [expo/app/gameplay/loop/[playerId]/life.tsx], read the Daily Brief from [expo/src/components/gameplay/DailyBriefCard.tsx], then tap Map in [expo/src/features/gameplayLoop/navigation.ts] and choose one concrete action in [expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx].

Reward: The action executes through [expo/src/features/gameplayLoop/context.tsx] and [backend/app/api/gameplay.py], then the player immediately sees cash, stress, health, day, and transaction movement in [expo/src/components/gameMap/PlayerStatusBar.tsx] and [expo/src/features/gameplayLoop/screens/LifeScreen.tsx].

Hook: The app points the player toward the next settlement or next day through [expo/src/features/gameplayLoop/screens/LifeScreen.tsx], [expo/src/components/gameplay/EndOfDaySummaryCard.tsx], [backend/app/engine/daily_engine.py], and [backend/app/services/daily_brief_service.py].

## Daily Loop

Action: Across one in-game day, the player checks the brief in [expo/src/features/gameplayLoop/screens/LifeScreen.tsx], performs work/rideshare/food/travel/business actions from [expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx], reviews job state in [expo/src/features/gameplayLoop/screens/WorkScreen.tsx], checks net worth or stocks in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx], then taps Run Settlement in [expo/src/features/gameplayLoop/screens/LifeScreen.tsx].

Reward: The climactic moment is End Day settlement: [expo/src/features/gameplayLoop/context.tsx] calls [backend/app/api/gameplay.py], which calls [backend/app/engine/daily_engine.py], and the result is shown through [expo/src/components/gameplay/EndOfDaySummaryCard.tsx] as earned, spent, net, biggest gain, biggest loss, deltas, warnings, and tomorrow focus.

Hook: Starting the next day in [expo/src/features/gameplayLoop/screens/LifeScreen.tsx] reloads the next Daily Brief from [backend/app/services/daily_brief_service.py] and the next guided nudge from [backend/app/services/guided_sandbox_service.py].

## Weekly Loop

Action: Over seven in-game days, the primary weekly stake is net worth: the player grows or defends cash, stocks, land, business value, inventory, and debt position shown in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx], using work from [backend/app/engine/work_engine.py], rideshare from [backend/app/engine/rideshare_engine.py], stocks from [backend/app/engine/stock_engine.py], business operations from [backend/app/engine/business_engine.py], and housing/debt decisions from [backend/app/engine/housing_engine.py].

Reward: The weekly reward is seeing asset mix and net worth improve or survive pressure in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx], with supporting business stage signals from [expo/src/lib/businessSandbox.ts] and [expo/src/features/gameplayLoop/screens/BusinessScreen.tsx].

Hook: The player returns to protect the weekly net-worth line from daily macro, price, job, business, and housing pressure generated by [backend/app/engine/macro_engine.py], [backend/app/engine/economy_engine.py], [backend/app/engine/stock_engine.py], [backend/app/engine/business_balance_engine.py], and [backend/app/engine/housing_balance_engine.py].

Supporting weekly stakes: business growth phase in [expo/src/lib/businessSandbox.ts], career/training progress in [expo/src/features/gameplayLoop/screens/WorkScreen.tsx], and sector exposure in [backend/app/engine/stock_engine.py].

## Must-Open Moment

The must-open moment is the End Day reveal: after the player taps Run Settlement in [expo/src/features/gameplayLoop/screens/LifeScreen.tsx], the app should make the player want to see the settlement result from [expo/src/components/gameplay/EndOfDaySummaryCard.tsx] and the next Daily Brief from [backend/app/services/daily_brief_service.py].

## Variable Reward

Variable reward comes from daily random events in [expo/src/lib/gameEvents.ts], macro and price movement in [backend/app/engine/macro_engine.py] and [backend/app/engine/economy_engine.py], stock movement in [backend/app/engine/stock_engine.py], rideshare trip outcomes in [backend/app/engine/rideshare_engine.py], and business operating variance in [backend/app/engine/business_balance_engine.py]. The current surprise distribution is small day-to-day deltas most days, occasional positive or negative daily events from [expo/src/lib/gameEvents.ts], and rarer larger swings when macro, stock, rideshare, or business systems stack in the same direction. The rare event the player is chasing is a day where the brief, action results, and settlement all line up: extra income, favorable market/business movement, controlled stress/health, and a visible net-worth jump in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx].

## Gaps the Loop Reveals

- Streak is computed but not surfaced: [backend/app/engine/retention_engine.py] has streak bonus logic, but [expo/src/components/gameMap/PlayerStatusBar.tsx] and [expo/src/features/gameplayLoop/screens/LifeScreen.tsx] do not show a daily streak counter.
- No anticipation timer is visible: [expo/src/features/gameplayLoop/screens/LifeScreen.tsx], [expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx], and [expo/src/components/gameMap/PlayerStatusBar.tsx] do not show a countdown to settlement, next day, salary, or next brief.
- No persistent ladder exists on every screen: [expo/src/components/gameMap/PlayerStatusBar.tsx] shows cash/stress/health/day, but not career rank, business stage, or wealth percentile.
- The summary route does not carry the climax: [expo/src/features/gameplayLoop/screens/SummaryScreen.tsx] exists, but [expo/app/gameplay/loop/[playerId]/summary.tsx] redirects to Life.
- The End Day reveal is still card-based: [expo/src/components/gameplay/EndOfDaySummaryCard.tsx] is strong, but the loop climax is not a dedicated full-screen moment in the active route tree.
- Weekly progression is under-surfaced: [expo/src/lib/api/gameplay.ts] has weekly summary access, but [expo/src/features/gameplayLoop/navigation.ts] and [expo/src/features/gameplayLoop/screens/MarketScreen.tsx] do not make a week-over-week net-worth race explicit.
- Variable reward is split across cards: [expo/src/components/gameplay/DailyBriefCard.tsx], [expo/src/features/gameplayLoop/screens/MarketScreen.tsx], [expo/src/features/gameplayLoop/screens/BusinessScreen.tsx], and [expo/src/features/gameplayLoop/screens/LifeScreen.tsx] show outcomes, but no single surface packages the surprise moment.
- Dashboard is not a loop anchor: [expo/src/features/gameplayLoop/screens/DashboardScreen.tsx] exists, but [expo/app/gameplay/loop/[playerId]/dashboard.tsx] redirects to Work.
- Forecasting is not a V1 loop driver: [backend/app/engine/forecasting_planning_service.py] exists, but `V1_SCOPE.md` freezes forecasting/planning expansion.

## Commitment Line

This is the loop. Every feature decision until launch is judged against it: does it serve the 60-second / daily / weekly loop, yes or no. Anything that doesn't is out of scope or deferred.
