# Step 48.7 — Daily Brief + Opportunity Surface Hookup Report

## Summary

Connected the active Gold Penny Expo gameplay UI to the real backend world-state for daily brief and opportunity rendering. Players can now see why prices, pressure, and opportunities changed — driven by canonical backend economy and supply-chain outputs — without any frontend world simulation being introduced.

---

## Files Reviewed

| File | Role |
|---|---|
| `src/pages/gameplay/GameDashboardPage.tsx` | Main gameplay orchestrator — loads, overlays, and renders all economy surfaces |
| `src/components/gameplay/DailyBriefCard.tsx` | Primary player-facing daily brief card |
| `src/components/gameplay/SupplyChainStoryCard.tsx` | Detailed supply-chain signal view (Economy + Market section) |
| `src/components/gameplay/RiskOpportunityPanel.tsx` | Risk/Opportunity component (exists but not rendered in active dashboard) |
| `src/components/gameplay/MarketOverviewCard.tsx` | Market overview (Economy + Market section) |
| `src/components/gameplay/LocalPressureCard.tsx` | Local pressure view (World Memory section) |
| `src/components/gameplay/WorldNarrativeCard.tsx` | World narrative view (World Memory section) |
| `src/types/economyPresentation.ts` | Backend economy presentation type contracts |
| `src/types/supplyChain.ts` | Supply-chain type contracts |
| `src/lib/uiSummaryFormatters.ts` | Section summary line builders (presentation-only) |
| `src/lib/economyPresentationFormatters.ts` | Economy label/color formatters |
| `src/lib/gameplayFormatters.ts` | General gameplay formatters |
| `src/lib/balanceConfig.ts` | Gameplay balance config |
| `goldpenny-backend/app/services/daily_brief_service.py` | Backend daily brief builder — source of `top_bottlenecks`, `top_basket_movers`, `top_job_changes` signals |
| `goldpenny-backend/app/engine/economy_presentation_service.py` | Backend canonical summary composer |

---

## Files Updated

| File | What Changed |
|---|---|
| `src/lib/worldEconomySignalMapper.ts` | **Created** — new centralized backend-to-player signal mapper |
| `src/components/gameplay/DailyBriefCard.tsx` | Added optional `impactBullets` prop; renders "Driving Signals" section |
| `src/pages/gameplay/GameDashboardPage.tsx` | Imported mapper; enhanced overlay function; added `dailyBriefImpactBullets` memo; passed bullets to DailyBriefCard |

---

## Audit Findings

### What Already Existed and Worked

- `DailyBriefCard` renders `headline`, `daily_brief` summary text, `top_opportunities`, and `top_risks` — all already overlaid from Step 48.6 backend bundle.
- `overlayDashboardWithEconomySummary()` merges `player_opportunities` and `player_warnings` from the canonical backend summary into the player dashboard before rendering.
- `SupplyChainStoryCard` shows full supply-chain detail inside the collapsible "Economy + Market" secondary section.
- All three refresh paths (`loadAll`, `refreshAfterAction`, end-day) use `loadEconomyOverviewWithFallback()` with bundle-first + legacy fallback.

### Gap Identified

The backend `DailyEconomyBriefResponse` carries three signal arrays that were not surfaced in the UI:
- `top_bottlenecks` — raw supply-chain node keys under pressure (e.g. `transport_hub`, `produce_market`)
- `top_basket_movers` — basket keys with active cost pressure (e.g. `produce`, `grains`)
- `top_job_changes` — job keys with shifting demand (e.g. `delivery_driver`, `market_stall`)

These are meaningful "why" signals that explain daily price and pressure changes. They were returned by the backend but were not translated into player language or displayed anywhere.

Additionally, `player_opportunities` and `player_warnings` from the backend could be empty on some cycles (particularly early days). The overlay had no fallback beyond the raw legacy dashboard signals.

---

## Daily Brief Contract

Shape consumed by the `DailyBriefCard`:

```typescript
// From backend EconomyPresentationSummaryResponse:
daily_brief: {
  headline: string;              // → dashboard.headline via overlay
  summary_lines: string[];       // → dashboard.daily_brief via buildBundleBrief()
  top_bottlenecks: string[];     // → impactBullets via buildDailyBriefImpactBullets()
  top_basket_movers: string[];   // → impactBullets via buildDailyBriefImpactBullets()
  top_job_changes: string[];     // → impactBullets via buildDailyBriefImpactBullets()
}
player_opportunities: string[]; // → top_opportunities via overlay
player_warnings: string[];      // → top_risks via overlay
```

The `DailyBriefCard` now renders:
1. Headline (from backend brief or player dashboard fallback)
2. Summary text (from `summary_lines`, supply chain `short_summary`, or market explainer)
3. **"Driving Signals" section** (new) — up to 3 impact bullets from bottleneck/basket/job signals
4. Top Opportunities and Top Risks signal grid

---

## Backend-Output-to-Player-Story Mapping Decisions

All mapping logic lives in `src/lib/worldEconomySignalMapper.ts`. No second economy reasoning on the frontend.

### Node key → player label examples
| Backend key | Player label |
|---|---|
| `transport_hub` | Logistics hub |
| `produce_market` | Produce market |
| `fuel_depot` | Fuel supply |
| `grains_warehouse` | Grain stores |

### Node key → opportunity hint examples
| Backend key | Player opportunity hint |
|---|---|
| `transport_hub` | Delivery and logistics shifts are in higher demand |
| `produce_market` | Fresh produce sourcing and fruit business opportunity opening |
| `fuel_depot` | Fuel-light routes and nearby work preferred over long commutes |

### Basket key → player label examples
| Backend key | Player label |
|---|---|
| `produce` | Fresh produce |
| `grains` | Grains and staples |
| `proteins` | Meat and proteins |

### Job key → player label examples
| Backend key | Player label |
|---|---|
| `delivery_driver` | Delivery driver |
| `market_stall` | Market stall operator |
| `food_truck` | Food truck operator |

Unknown backend keys are title-cased from their underscore form automatically (the mapper never silently fails).

---

## UI Surfaces Added / Cleaned

### `DailyBriefCard` — "Driving Signals" section (new)

- Rendered between the summary text and the opportunity/risk signal grid.
- Only appears when `impactBullets` is non-empty (silently omitted when missing).
- Max 3 bullets: one for bottleneck pressure, one for basket price movement, one for job changes.
- Styled consistently with the existing card visual language (subtle background box, uppercase tracking label).
- Mobile-friendly: no separate scroll required; reads quickly.

### `overlayDashboardWithEconomySummary()` — fallback signal enrichment (enhanced)

When `player_opportunities` is empty (e.g. backend sees a quiet day), the overlay now derives opportunity signals from:
1. `top_bottlenecks` → player-facing opportunity hints via mapper
2. `top_job_changes` → job demand shift hints via mapper

When `player_warnings` is empty, the overlay derives warning signals from:
- `top_basket_movers` → basket price pressure captions via mapper

This ensures the DailyBriefCard never shows empty opportunity/risk grids when backend signals exist.

### `worldEconomySignalMapper.ts` — exported functions

| Function | Purpose |
|---|---|
| `buildDailyBriefImpactBullets(daily_brief)` | Produces max 3 player-readable "why" bullets |
| `buildBottleneckOpportunityHints(bottlenecks)` | Bottleneck node → opportunity hint objects |
| `buildJobChangeHints(jobChanges)` | Job key → demand shift hint objects |
| `buildBasketPressureSignals(basketMovers)` | Basket key → cost pressure warning objects |
| `supplyChainJobOpportunityLine(summary)` | Single line from supply chain best job opportunity |

---

## Fallback Behavior Decisions

| Scenario | Behaviour |
|---|---|
| `economyPresentationSummaryState` fails | `overlayDashboardWithEconomySummary(dashboard, null)` returns raw dashboard unchanged |
| `daily_brief` is absent from bundle | `buildDailyBriefImpactBullets(null)` returns `[]`; "Driving Signals" section does not render |
| `player_opportunities` is empty | Overlay derives signals from `top_bottlenecks` + `top_job_changes`; no blank list shown |
| `player_warnings` is empty | Overlay derives signals from `top_basket_movers`; no blank list shown |
| All signal lists empty | DailyBriefCard renders headline + summary + standard empty-state signal lists |
| Backend bundle unavailable entirely | Legacy per-endpoint fallback runs; economy state set to `empty`; DailyBriefCard shows player dashboard fallback text |

In every scenario, the player state is never corrupted and no fake world-state data is invented.

---

## Naming Integrity

No legacy token-era naming (`nnt`, `NNT`, `GNNT`, `xgp token`, wallet-reward naming, or `mock economy`) found in any touched file.

`xgp` (Gold Penny currency unit) is correct and intentional — it is the active in-game currency identifier, not a token-era artefact.

---

## Validation Results

| Check | Result |
|---|---|
| `get_errors` on all 3 changed files | ✅ 0 errors |
| `tsc --noEmit` | ✅ TS_EXIT=0 |
| `expo lint` | ✅ LINT_EXIT=0, 0 errors, 10 pre-existing warnings (unchanged) |
| Backend economy presentation tests | ✅ 10 passed (unchanged from Step 48.6) |
| Naming integrity scan | ✅ Clean |

---

## Deferred Items

- **Visual smoke test**: The "Driving Signals" bullets appear only when `economyPresentationSummaryState` loads correct backend data. Manual verification against a running game cycle is required to confirm the correct backend signals appear in the player-facing brief.
- **`RiskOpportunityPanel` component**: This component exists but is not rendered anywhere in the active dashboard. It duplicates the signal display logic already in `DailyBriefCard`. It should either be removed or promoted to a dedicated section in a future cleanup step.
- **`supplyChainJobOpportunityLine` helper**: This function is exported from the mapper and can be used to add a single-line "best job today" hint to the DailyBriefCard or PlayerStatsBar in a future step if desired.
- **Automated frontend unit tests**: `buildDailyBriefImpactBullets`, `overlayDashboardWithEconomySummary`, and the mapper functions are pure and straightforward to unit test — this remains a suggestion for a dedicated test sweep.

---

## Success Criteria Status

| Criterion | Status |
|---|---|
| Player sees a clear Daily Brief driven by canonical backend world-state | ✅ |
| Bottlenecks and macro changes translate into understandable opportunity/warning signals | ✅ |
| Frontend remains a presenter, not a second economy brain | ✅ |
| UI stays mobile-friendly and uncluttered | ✅ |
| No obvious old token-era naming remains in touched files | ✅ |
| Foundation is ready for the next step | ✅ |
