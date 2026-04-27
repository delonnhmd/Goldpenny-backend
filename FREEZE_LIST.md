# V1 Freeze List

No further commits to frozen systems are allowed until V1 launch unless another system of equal or greater weight is deleted first.

## Repo Audit

### Expo app routes

| Route | V1 required? | Decision |
|---|---:|---|
| `expo/app/index.tsx` | Yes | Ships as session restore entry. |
| `expo/app/(tabs)/index.tsx` | Yes | Ships as mobile home redirect into gameplay. |
| `expo/app/(tabs)/settings.tsx` | Yes | Ships for backend URL, support, and QA overrides. |
| `expo/app/auth/*` | Yes | Ships email/password auth, signup, reset, and player creation. |
| `expo/app/gameplay/index.tsx` | Yes | Ships player selection and gameplay entry. |
| `expo/app/gameplay/[playerId].tsx` | Yes | Ships legacy-compatible gameplay route. |
| `expo/app/gameplay/loop/[playerId]/*` | Yes | Ships map, dashboard, work, life, brief, market, business, summary, and wallet shell views. |
| `expo/app/account/index.tsx` | Yes | Ships account status and support surface already linked from gameplay. |
| `expo/app/admin/` | No | Frozen: empty route folder; internal/admin APIs already exist elsewhere. |
| `expo/app/leaderboard/` | No | Frozen: empty route folder; no V1 scoring surface or retention loop exists yet. |
| `expo/app/post/` | No | Frozen: empty route folder; legacy post/social feed work is not V1 gameplay. |
| `expo/app/user/` | No | Hold only; empty legacy profile route, not one of the three active freezes because it has no current entry point. |
| `expo/app/referral/` | No | Cut in `delete referral`. |
| `expo/app/claim/` | No | Cut in `delete claim`. |

### Expo feature directories

| Feature directory | V1 required? | Decision |
|---|---:|---|
| `expo/src/features/auth` | Yes | Ships account auth context and session state. |
| `expo/src/features/onboarding` | Yes | Ships first-player setup and profile creation. |
| `expo/src/features/gameplayLoop` | Yes | Ships the primary V1 mobile loop. |
| `expo/src/features/softLaunch` | Yes | Ships invite/access and feedback support. |
| `expo/src/features/playtest` | Yes | Ships internal QA support only, not player marketing. |

### Backend API routers

| Router | V1 required? | Decision |
|---|---:|---|
| `auth`, `onboarding`, `player`, `gameplay`, `daily`, `day`, `briefs`, `jobs`, `side_income` | Yes | Core account, player, day, brief, work, and rideshare loop. |
| `baskets`, `macro`, `economy`, `economy_presentation`, `events`, `personal_shocks` | Yes | Core economic pressure and player event content. |
| `finance`, `debt`, `consumer_borrowing`, `financial_survival`, `housing`, `health` | Yes | Core life pressure, debt, survival, and housing loop. |
| `stocks`, `portfolio`, `market` | Yes | V1 financial progression and sector market surface. |
| `business`, `marketplace`, `deals` | Yes | V1 business, async trade, and co-op deal surfaces already implemented. |
| `career`, `progression`, `commitment`, `wealth_progression`, `reputation_trust`, `world_memory` | Yes | V1 progression and retention support. |
| `guided_sandbox`, `soft_launch`, `internal` | Yes | Guided first-run, soft-launch gates, and operator support. |
| `population_pressure`, `contract_timing`, `debt_behavior`, `supply_chain` | Yes | Existing simulation pressure used by V1 systems; no new depth work before launch. |
| `forecasting`, `strategic_planning`, `strategy` | Hold | Existing advice/planning APIs may remain, but no new V1 scope without deletion elsewhere. |
| `rewards` | No | Cut in `delete claim` with token/reward claim system. |

### Major backend modules

| Module group | V1 required? | Decision |
|---|---:|---|
| Work/day lifecycle engines and services | Yes | `work_engine`, `daily_engine`, `day_engine`, `settlement_engine`, `shift_state_service`. |
| Needs, basket, macro, and event engines | Yes | `needs_engine`, `basket_engine`, `macro_engine`, `event_service`, `daily_brief_service`. |
| Housing, debt, borrowing, and survival services | Yes | `housing_engine`, `financial_survival_service`, `consumer_borrowing_service`, `debt_credit_service`. |
| Business, marketplace, firm, and co-op modules | Yes | `business_engine`, `marketplace_engine`, `firm_engine`, `coop_deal_engine`. |
| Progression, reputation, wealth, and world memory modules | Yes | Retention support that already feeds gameplay and summaries. |
| Supply chain and population pressure modules | Yes | Existing pressure inputs; freeze new expansion, not current reads. |
| Web bridge | Hold | Future token/web surface; no new V1 work unless another surface is cut. |
| Token/reward claim modules | No | Deleted with `/rewards` router and claim tables. |

## Frozen Systems

1. `expo/app/post/` - frozen because it is an empty legacy social/post route with no V1 player loop.
2. `expo/app/leaderboard/` - frozen because it is an empty ladder route with no scoring, cohort, or reward contract yet.
3. `expo/app/admin/` - frozen because it is an empty mobile admin route and duplicates Settings/internal backend support.
