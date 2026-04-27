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

## The Daily Ritual

This is a five-to-twelve-minute mobile session, not a desktop session and not a broad sim-management block.

1. Today's world event is ready before the player wakes up. The existing repo can store one daily economy event in [backend/app/models/daily_economy_event.py], generate deterministic event rows through [backend/app/engine/event_service.py], and turn those rows into a player brief through [backend/app/services/daily_brief_service.py]. The real-world news ingestion layer is not present yet; it belongs in the gaps.
2. The push trigger should fire at the player's chosen local morning time, but this is not implemented. [expo/package.json] does not include `expo-notifications`, [backend/app/models/player_daily_state.py] explicitly calls notification data a future layer, and [expo/src/lib/api/gameplay.ts] only normalizes in-app notification payloads.
3. App open enters the mobile game through [expo/app/(tabs)/index.tsx] and [expo/app/gameplay/index.tsx], then lands in the loop route at [expo/app/gameplay/loop/[playerId]/life.tsx].
4. The brief renders on Life through [expo/src/features/gameplayLoop/screens/LifeScreen.tsx] and [expo/src/components/gameplay/DailyBriefCard.tsx], using dashboard fields normalized in [expo/src/lib/api/gameplay.ts] and sourced from [backend/app/api/gameplay.py].
5. The player sees the immediate state of the life they are protecting: cash, stress, health, and day in [expo/src/components/gameMap/PlayerStatusBar.tsx], plus condition, activity, spending history, work status, debt, housing, and end-day controls in [expo/src/features/gameplayLoop/screens/LifeScreen.tsx].
6. The decision window is 3-7 taps, not an open-ended session. The player chooses work, rideshare, food, travel, job/training, business, inventory, or lot actions in [expo/src/features/gameplayLoop/screens/MapDashboardScreen.tsx], reviews job state in [expo/src/features/gameplayLoop/screens/WorkScreen.tsx], checks assets in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx], and operates or stocks a business in [expo/src/features/gameplayLoop/screens/BusinessScreen.tsx].
7. Every decision runs through [expo/src/features/gameplayLoop/context.tsx] and [backend/app/api/gameplay.py], with work, rideshare, stock, business, housing, and settlement effects delegated to [backend/app/engine/work_engine.py], [backend/app/engine/rideshare_engine.py], [backend/app/engine/stock_engine.py], [backend/app/engine/business_engine.py], [backend/app/engine/housing_engine.py], and [backend/app/engine/daily_engine.py].
8. The player ends the day from [expo/src/features/gameplayLoop/screens/LifeScreen.tsx]. [expo/src/features/gameplayLoop/context.tsx] calls [backend/app/api/gameplay.py], settlement runs through [backend/app/engine/daily_engine.py], and the closeout appears in [expo/src/components/gameplay/EndOfDaySummaryCard.tsx].
9. The close is the player reading earned, spent, net, main gain, main drag, stress/health deltas, warnings, and tomorrow focus in [expo/src/components/gameplay/EndOfDaySummaryCard.tsx], then leaving the app until the next morning brief.

Honest narration finding: I cannot write the promised tomorrow-morning ten-minute player narration yet without faking it, because the repo has a Daily Brief surface and deterministic in-game event engine but no real-world news ingestion service and no Expo push-notification opt-in path. The honest current session is: I open Life, read an in-game brief, check cash/stress/health, tap Map, run a few actions, settle, and read tomorrow focus. The distinctive "oil spiked overnight, my food truck margin is bleeding today" story is the product premise, but it is not wired yet.

## The Running Campaign

The campaign is the player's finance life aging one real day at a time. Wealth trajectory is already measurable through [backend/app/services/net_worth_service.py], [backend/app/engine/wealth_progression_service.py], [backend/app/models/player_net_worth_snapshot.py], [backend/app/models/player_wealth_trend_history.py], and visible net worth in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx]. Business empire shape is already represented by active business state in [backend/app/engine/business_engine.py], operating results in [backend/app/engine/business_balance_engine.py], growth phases in [expo/src/lib/businessSandbox.ts], and the player-facing business screen in [expo/src/features/gameplayLoop/screens/BusinessScreen.tsx].

Survival record is stored through settled days and pressure logs: [backend/app/models/player_daily_state.py], [backend/app/services/daily_settlement_service.py], [backend/app/engine/needs_engine.py], [backend/app/engine/housing_engine.py], [backend/app/engine/retention_engine.py], and financial pressure services exposed through [backend/app/api/finance.py] and [backend/app/api/financial_survival.py]. Portfolio history exists through [backend/app/engine/stock_engine.py], [backend/app/models/stock_price_history.py], [backend/app/api/portfolio.py], and the Portfolio surface in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx].

Milestones the player chases: first 10,000 XGP net worth from [backend/app/services/net_worth_service.py] and [expo/src/features/gameplayLoop/screens/MarketScreen.tsx]; first stage-3 business from [expo/src/lib/businessSandbox.ts] and [expo/src/features/gameplayLoop/screens/BusinessScreen.tsx]; first survived multi-day macro chain from [backend/app/engine/event_service.py] and [backend/app/models/daily_economy_event.py]; first 30-day and 365-day life record from [backend/app/models/player_progression_state.py] and [backend/app/api/progression.py].

Campaign endings are not implemented today. The two soft endings this game should point at are bankruptcy retirement from the current run when net worth and distress stay critical for multiple settled days, and voluntary retirement when the player reaches a durable net-worth target. The data to evaluate those endings exists in [backend/app/engine/wealth_progression_service.py], [backend/app/services/net_worth_service.py], [backend/app/api/finance.py], and [backend/app/models/player_daily_state.py], but no end-state route, modal, or reset flow exists in [expo/app/gameplay/loop/[playerId]/*].

## The Lifelong Run

The headline claim is: "I have lived this finance life for N real-world days alongside reality." The nearest existing foundation is streak data in [backend/app/models/player_progression_state.py], the streak endpoint in [backend/app/api/progression.py], the Expo normalizer in [expo/src/lib/api/progression.ts], and [expo/src/components/gameplay/StreaksCard.tsx]. That is not yet the product-facing line "you've witnessed N consecutive days of the real world," and it is not persistent in [expo/src/components/gameMap/PlayerStatusBar.tsx].

The personal "you survived" timeline should tie a player's run to macro/event history: "survived the 2026 oil shock," "stayed solvent through the supply chain squeeze," "grew net worth during a confidence collapse." The source data exists across [backend/app/models/daily_economy_event.py], [backend/app/api/events.py], [backend/app/services/daily_settlement_service.py], [backend/app/services/net_worth_service.py], and [backend/app/engine/world_memory_service.py]. The shareable timeline surface does not exist in [expo/app/gameplay/loop/[playerId]/*] or [expo/src/features/gameplayLoop/screens/*].

The annual recap card should summarize days lived, starting and ending net worth, best business, worst macro event survived, longest streak, and biggest recovery. The ingredients exist in [backend/app/models/player_daily_state.py], [backend/app/models/player_wealth_trend_history.py], [backend/app/models/daily_economy_event.py], [backend/app/api/progression.py], and [backend/app/api/portfolio.py]. The recap card, export flow, and public share surface do not exist in Expo.

## Must-Open Moment

The must-open moment is the morning brief. Once per day, at the player's chosen local time, a push notification should say one of: "The world moved overnight. Your Gold Penny brief is ready.", "Oil, jobs, and prices shifted. See what hit your life today.", or "Today's economy event is live. Check your businesses before you act." It should deep-link to [expo/app/gameplay/loop/[playerId]/life.tsx], where [expo/src/components/gameplay/DailyBriefCard.tsx] renders the brief.

Opt-in belongs in onboarding, not Settings after the fact. The correct home is the existing onboarding provider and route flow in [expo/src/features/onboarding/context.tsx] plus the gameplay entry in [expo/app/gameplay/index.tsx]. The limit is hard: one push notification per player per day, never more, and no marketing pushes. The notification system does not yet exist in Expo: [expo/package.json] lacks `expo-notifications`, [expo/src/lib/api/gameplay.ts] only handles in-app notifications, and [backend/app/models/player_daily_state.py] marks notification data as a future layer. This is a Phase 3 build item.

## Real-World Event Pipeline

### Sources

Launch with exactly three sources. First, Alpha Vantage Market News & Sentiment for broad financial/business news and ticker/topic tagging; its docs expose market news and sentiment, but its terms make commercial use a written-agreement issue, so launch must use an approved commercial/premium arrangement, not a hobby key. Second, Polygon.io/Massive financial market data and news coverage for U.S. stocks and company-level signals; use a paid business/commercial plan, not a personal/non-pro plan. Third, FRED API for macro anchors such as CPI, unemployment, rates, oil-related series, and recession context; it is an official St. Louis Fed API governed by its API terms.

No fourth source goes into V1. More sources add licensing, dedupe, and moderation load before the loop is proven.

### Cadence

Generation runs once per day globally at 04:00 UTC. All players see the same world event for that real-world day. That keeps cost low, creates shared lore, and lets players compare outcomes against the same event instead of consuming per-player AI.

The existing daily-event storage model is [backend/app/models/daily_economy_event.py], event retrieval lives in [backend/app/api/events.py], and brief generation reads daily events in [backend/app/services/daily_brief_service.py]. The global generation job is not implemented yet.

### Mapping

The AI output is not prose-only. It emits a structured object:

```json
{
  "event_id": "realworld-2026-04-27-oil-margin-squeeze",
  "generated_at": "2026-04-27T04:00:00Z",
  "source_summary": "Oil rose after supply concerns while grocery distributors warned about higher shipping costs.",
  "event_name": "Fuel Margin Squeeze",
  "narrative": "Fuel costs moved against small operators overnight.",
  "affected_sectors": ["energy", "food", "transportation", "consumer"],
  "magnitude": 0.65,
  "duration_days": 3,
  "severity": 1.4,
  "tone": "negative"
}
```

The mapping layer translates that object into fields the current engines already understand: `event_id`/`event_name`/`narrative` map to `event_key`, `headline`, and `summary` in [backend/app/models/daily_economy_event.py]; `tone` maps to `sentiment`; `severity` maps to `severity`; `affected_sectors` and `magnitude` map to `impact_tags_json`. Those impact tags are then consumed through [backend/app/engine/event_service.py], [backend/app/engine/macro_engine.py], [backend/app/engine/economy_engine.py], [backend/app/engine/stock_engine.py], and [backend/app/engine/business_balance_engine.py]. The AI is a content generator for parameters the engines already accept; it is not a parallel game system.

### Fallback

Fallback one: cache yesterday's event and replay it with a quiet-day frame if generation fails: "The world is quiet today; yesterday's pressure is still working through your city." This fits the existing chain language in [backend/app/services/daily_brief_service.py] and chain fields in [backend/app/models/daily_economy_event.py].

Fallback two: maintain a hand-curated bank of 50 generic events as last resort. [backend/app/engine/event_catalog.py] is already a static catalog of economy events and can be the pattern for that bank. Fallback three: AI cost is capped at $0.05-$0.20 per MAU per month. Above that, throttle enrichment and serve cached/static events.

### Safety

Two filters are mandatory between generation and publication. First, an automatic content classifier blocks violence, death, political persuasion, hate, sexual, self-harm, targeted harassment, and sensitive-personal categories before the event reaches [backend/app/models/daily_economy_event.py]. Second, a human reviews the generated event every day for the first six months of operation before it is allowed to publish through [backend/app/api/events.py] and [backend/app/services/daily_brief_service.py].

This is not optional polish. It is launch process. The review queue, reviewer tooling, and staffing decision do not exist in the repo today; they are Phase 3 operational scope and likely a contractor role before a full-time hire.

## Variable Reward

Variable reward comes from daily random events in [expo/src/lib/gameEvents.ts], macro and price movement in [backend/app/engine/macro_engine.py] and [backend/app/engine/economy_engine.py], stock movement in [backend/app/engine/stock_engine.py], rideshare trip outcomes in [backend/app/engine/rideshare_engine.py], and business operating variance in [backend/app/engine/business_balance_engine.py]. The current surprise distribution is small day-to-day deltas most days, occasional positive or negative daily events from [expo/src/lib/gameEvents.ts], and rarer larger swings when macro, stock, rideshare, or business systems stack in the same direction. The rare event the player is chasing is a day where the brief, action results, and settlement all line up: extra income, favorable market/business movement, controlled stress/health, and a visible net-worth jump in [expo/src/features/gameplayLoop/screens/MarketScreen.tsx].

## Cost and Latency Budget

- Brief render time on app open: < 200ms, achieved by pre-generating once daily and serving the result from cache through [backend/app/api/gameplay.py] and [backend/app/services/daily_brief_service.py].
- AI generation cost per global daily event: < $0.50, because generation is one global event per day, not one event per player.
- Per-MAU AI cost cap: $0.05-$0.20/month. Above this, throttle enrichment or fall back to cached/static events from [backend/app/engine/event_catalog.py].

## Gaps the Loop Reveals

- Real-world AI ingestion is absent: [backend/app/engine/event_service.py], [backend/app/engine/event_catalog.py], and [backend/app/models/daily_economy_event.py] support generated/static daily events, but there is no source-ingestion job, no AI generation service, no safety review queue, and no schema fields for `source_summary`, `generated_at`, `affected_sectors`, or `duration_days`.
- Morning push is absent: [expo/package.json] has no `expo-notifications`, [expo/src/lib/api/gameplay.ts] only normalizes in-app notifications, and [backend/app/models/player_daily_state.py] marks notification data as a future layer.
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

This is the loop. Every feature decision until launch is judged against it: does it serve the daily ritual, the running campaign, or the lifelong run, yes or no. Anything that doesn't is out of scope or deferred. The Real-World Event Pipeline is the product's moat — protect it, don't dilute it.
