# Step 75 — Simplified Structure & Action-First Dashboard

## Summary

Restructured the GoldPenny gameplay loop UI to reduce the number of tabs from 7 to 4, move all player actions into the Dashboard, fold end-of-day settlement into the Brief screen, and remove consultant/jargon language throughout.

---

## Changes Made

### Tab Navigation — 7 → 4 Tabs

**Before:** Brief · Dashboard · Work · Market · Business · Life · Summary

**After:** Brief · Dashboard · Market · Business

Removed tabs: Work, Life, Summary

File: `src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- Removed `work`, `life`, `summary` from `bottomNavItems` array
- Updated onboarding filter (now only `business` is hidden during guided flow)

---

### Dashboard — Now the Main Action Screen

File: `src/features/gameplayLoop/screens/DashboardScreen.tsx`

**Before:** Stats card + 4 navigation buttons (Go To Work / Eat a Meal / Check Market / Housing & Loan)

**After:** Full action screen with 4 sections:

1. **Status** — Cash, net flow, debt, health, stress, debt pressure
2. **Work** — Today's pay + time left stat cards; job selector (Day 1 / switch job); ActionHubPanel with all shift/income actions
3. **Life** — Breakfast / Lunch / Dinner quick-buy buttons (−6 XGP each)
4. **Finance** — Quick loan selector (100 / 200 / 300 / 500 XGP) with +15% repay display

Footer changed: "End Day" button (was "Go To Work" / "Open Summary")

---

### Brief — Now Includes End-of-Day Settlement

File: `src/features/gameplayLoop/screens/BriefScreen.tsx`

**Before:** Day intro with economy chips, headline card, Top Opportunity callout, Top Risk banner

**After:** Cleaner two-state screen:

- **Day active:** DailyBriefCard + Economy Snapshot chips + "Day still active" info banner
- **Day ended:** Same header + Settlement Status chips + Today's Result card (net/earned/spent/stress delta/health delta) + EndOfDaySummaryCard

Footer adapts to session state:
- Active → "Go To Dashboard"
- Ended, no summary → "Run Settlement"
- Settled → "Start Next Day"

Removed: "Why today matters" card, Top Opportunity callout, Top Risk banner, "Most important next action" footer summary, consultant subtitle copy

---

### Summary Tab — Removed

File: `app/gameplay/loop/[playerId]/summary.tsx`

Route now redirects to `/brief`. All settlement content lives in BriefScreen.

---

### Work Tab — Removed

File: `app/gameplay/loop/[playerId]/work.tsx`

Route now redirects to `/dashboard`. All work actions live in DashboardScreen.

---

### Life Tab — Removed

File: `app/gameplay/loop/[playerId]/life.tsx`

Route now redirects to `/dashboard`. All meal/loan actions live in DashboardScreen.

Note: Housing selection (Suburban / Downtown) remains in the LifeScreen component file but is not surfaced in the main navigation. It can be accessed if needed via a direct route. Future step may expose it via a settings/life modal in Dashboard.

---

### Business Screen — Consultant Language Removed

File: `src/features/gameplayLoop/screens/BusinessScreen.tsx`

| Before | After |
|--------|-------|
| Subtitle: "Separate margin quality from cost and risk before operating" | "Revenue, costs, margin, and risk" |
| Footer: "Operate only if margin outlook is worth the time and inventory risk." | "Check margin outlook before operating." |
| Footer (operated): "Business already operated today. Move to summary or another lane." | "Business already operated today." |
| Footer (review): "Review margin and risk signals, then decide whether to operate." | "Review margin and decide whether to operate." |
| Primary CTA (not operating): "Open Summary" → `/summary` | "Open Brief" → `/brief` |
| Stats card subtitle: "Read this before deciding to run operations." | Removed |

---

### BottomNav — Compact Sizing

File: `src/components/layout/BottomNav.tsx`

| Property | Before | After |
|----------|--------|-------|
| `minHeight` | 44 | 36 |
| `paddingVertical` | `theme.spacing.xs` (4px) | `theme.spacing.xxs` (2px) |

With 4 tabs instead of 7, each tab has more horizontal space. Reducing height frees ~12px of vertical content space per screen.

---

## What Was Not Changed

- Core game logic, action execution, settlement flow — unchanged
- MarketScreen — unchanged
- BusinessScreen core cards (margins, plan, operations) — unchanged
- GameplayLoopScaffold shared header ("Today At A Glance" scan card) — unchanged
- Onboarding flow logic — unchanged
- WorkScreen.tsx and LifeScreen.tsx component files are retained (not deleted) so their logic can be referenced; they are just no longer reachable via navigation
- BottomNav label text — unchanged (Brief, Dashboard, Market, Business)

---

## Navigation Map After Step 75

```
/gameplay/loop/[playerId]/brief      → BriefScreen (day intro + end-of-day settlement)
/gameplay/loop/[playerId]/dashboard  → DashboardScreen (stats + work actions + meals + loans)
/gameplay/loop/[playerId]/market     → MarketScreen (unchanged)
/gameplay/loop/[playerId]/business   → BusinessScreen (margins + operate)
/gameplay/loop/[playerId]/work       → redirect → /dashboard
/gameplay/loop/[playerId]/life       → redirect → /dashboard
/gameplay/loop/[playerId]/summary    → redirect → /brief
/gameplay/loop/[playerId]/           → redirect → /brief
```
