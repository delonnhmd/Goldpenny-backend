# Step 48.6 - Backend Economy / Supply-Chain Integration Patch

## Goal

Patch the active Expo gameplay loop so economy-facing UI consumes canonical backend economy and supply-chain outputs instead of drifting into a second app-side world simulation.

## Outcome

Step 48.6 is implemented.

The Expo gameplay dashboard now hydrates economy surfaces from the backend summary bundle first, then falls back to legacy per-endpoint economy loaders if the summary call is unavailable. Backend-generated daily brief, warning, opportunity, and supply-chain story signals now drive the player-facing economy view.

## Audit Summary

### Frontend economy sources before patch

- Expo already consumed backend presentation slices for market overview, price trends, business margins, commute pressure, explainer, and future teasers.
- Expo did not use the canonical backend summary endpoint.
- Expo had supply-chain API/types present but unused.
- Expo still stitched together economy-facing copy locally via presentation helpers such as the economy summary line and dashboard brief rendering.

### What remains local UI-only

- Presentation summarization and section status labels.
- Safe display fallback when backend summary is unavailable.
- UI composition of existing cards and onboarding visibility logic.

### What now comes from backend

- Daily brief headline and summary lines.
- Supply-chain summary and story.
- Player-facing backend warnings.
- Player-facing backend opportunities.
- Canonical market, price, business, commute, explainer, and teaser payloads when summary loading succeeds.

## Canonical Mobile Payload

The backend summary contract was extended to provide a mobile-facing bundle with these fields:

- `current_day`
- `market_overview`
- `price_trends`
- `business_margins`
- `commute_pressure`
- `explainer`
- `future_teasers`
- `daily_brief`
- `supply_chain_summary`
- `supply_chain_story`
- `settlement_summary`
- `player_warnings`
- `player_opportunities`

This gives the Expo app one authoritative economy packet while keeping the old slice endpoints available for soft degradation.

## Files Changed

### Backend

- `app/schemas/economy_presentation.py`
  - Extended `EconomyPresentationSummaryResponse` with daily brief, supply-chain, settlement, warnings, and opportunity fields.
- `app/engine/economy_presentation_service.py`
  - Added summary composition for supply-chain story/summary, daily brief, settlement digest, and backend-generated warning/opportunity lists.
- `tests/test_economy_presentation_service.py`
  - Added service assertions for summary bundle composition.
- `tests/test_economy_presentation_api.py`
  - Added API assertions for the new summary fields.

### Frontend

- `PFT/pft-expo/src/types/economyPresentation.ts`
  - Extended the summary contract to match backend.
- `PFT/pft-expo/src/types/supplyChain.ts`
  - Corrected supply-chain typings to match the active backend schema.
- `PFT/pft-expo/src/lib/uiSummaryFormatters.ts`
  - Kept formatter logic presentation-only while allowing supply-chain short summary to enrich display text.
- `PFT/pft-expo/src/components/gameplay/SupplyChainStoryCard.tsx`
  - Added a gameplay card for supply-chain summary, shortage story, warnings, and opportunities.
- `PFT/pft-expo/src/pages/gameplay/GameDashboardPage.tsx`
  - Added bundle-first economy hydration.
  - Added overlay logic so backend brief/opportunity/warning signals replace duplicated local assumptions where appropriate.
  - Added soft fallback to legacy endpoints.
  - Rendered the new supply-chain story card in the economy section.

## Integration Details

### Bundle-first hydration

The gameplay page now loads `getEconomyPresentationSummary(playerId)` first and uses that payload to hydrate:

- market overview
- price trends
- business margins
- commute pressure
- economy explainer
- future teasers
- daily brief overlay
- supply-chain story card

### Soft fallback behavior

If the summary request fails:

- the app logs a warning
- legacy economy endpoints are fetched in parallel
- the player dashboard remains usable
- canonical local player/session state is not mutated or corrupted
- the summary state is downgraded to `empty` instead of remaining in a hard UI error state

### Double-simulation prevention

Frontend economy logic now stays in the presentation layer.

The app still derives display text and status labels, but the world-economy signals themselves come from backend summary fields instead of a second frontend-only economy interpretation.

## Supply-Chain to Opportunity Mapping

The integration now exposes backend supply-chain outputs directly in gameplay surfaces:

- bottleneck highlights appear in the new supply-chain card
- job opportunity hints appear in the new supply-chain card
- practical current actions appear in the new supply-chain card
- backend warning/opportunity strings feed the Daily Brief overlay

This preserves the backend as the source of truth for mappings such as transport, processing, retail, and related shortage pressure. The frontend now presents those mappings instead of inventing alternatives.

## Naming / Architecture Integrity Check

Inspected touched areas for:

- old placeholder economy assumptions
- mock or temporary economy logic
- duplicate frontend economy derivation
- stale domain naming

Result:

- no new `nnt-token` or unrelated UI leftovers were introduced in touched Step 48.6 files
- supply-chain types were aligned to current backend schema to remove stale assumptions
- gameplay economy refreshes now route through a canonical summary loader instead of fragmented page-only logic

## Validation

### Passed

- Backend tests:
  - `pytest tests/test_economy_presentation_service.py tests/test_economy_presentation_api.py`
  - Result: `10 passed`
- Frontend TypeScript:
  - `PFT/pft-expo/node_modules/.bin/tsc.cmd --noEmit`
  - Result: passed
- Frontend lint:
  - `PFT/pft-expo/node_modules/.bin/expo.cmd lint`
  - Result: passed with 10 pre-existing warnings and 0 errors

### Not fully automated in this step

- Gameplay route smoke test
- Manual Daily Brief / world-economy visual smoke test

There is no existing automated Expo gameplay smoke harness wired into this step, so these remain manual verification items.

## Success Criteria Check

- Expo app consumes canonical backend economy/supply-chain outputs: yes
- No parallel frontend-only world simulation remains where backend should be authoritative: yes, within touched gameplay economy surfaces
- Daily Brief and opportunity signals are driven by backend state: yes
- Gameplay loop stays stable if backend is temporarily unavailable: yes, through bundle fallback behavior

## Remaining Manual Follow-up

1. Open the gameplay route in the Expo app and verify the Daily Brief uses backend brief/opportunity content.
2. Verify the Supply Chain Pulse card appears with summary/story data on a day with recorded supply-chain state.
3. Verify temporary summary endpoint failure still shows the legacy economy cards without corrupting player progress.