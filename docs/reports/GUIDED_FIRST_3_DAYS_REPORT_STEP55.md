# Guided First 3 Days Report - Step 55

## Goal

Extend the first-session onboarding into a controlled first 3 in-game days without creating a fake tutorial mode. The early experience should stay tied to real backend state, reveal complexity gradually, reduce early punishment, and make the end of each day easier to understand.

## Day Design

### Day 1: Core loop
- Teach the real first-day loop: welcome, read the Daily Brief, take one income action, end the day.
- Hide advanced systems that would overload a first-time player.
- Keep guidance anchored in the mobile footer above the thumb dock.

### Day 2: Pressure and stability
- Introduce the idea that bills, debt, and recovery matter.
- Reveal planning and progression signals without opening the full economy surface area.
- Highlight recovery-vs-push decisions using real player state.

### Day 3: Opportunity and judgment
- Introduce the economy/opportunity layer after the player has already seen the daily loop and pressure.
- Highlight one safe next action rather than encouraging aggressive expansion.
- Keep mature modules deferred until after the guided window.

## Implementation

### Backend-owned guided days
The existing onboarding system remains the source of truth. Step 55 extends it into a backend-guided Day 1-3 coordinator instead of creating a second beginner ruleset.

Files updated:
- `app/engine/onboarding_service.py`
- `app/schemas/onboarding.py`
- `app/api/day.py`
- `app/services/daily_settlement_service.py`
- `app/engine/personal_shock_service.py`

Key changes:
- Added guided-day state fields: `guided_experience_active`, `guided_day_number`, `guided_phase`, `guided_label`.
- Kept Day 2 and Day 3 under guided reveal even after Day 1 onboarding is marked complete.
- Added backend-selected `highlighted_action_key` so the client can emphasize the right lower-dock action.
- Staged module reveal across the first 3 days instead of fully unlocking the dashboard immediately.

### Early pressure softening
Early-day smoothing is applied in the canonical backend personal shock logic.

Changes:
- Reduced event chance during days 1-3.
- Shifted weight toward lighter shocks and away from moderate/heavy outcomes.
- Exposed debug metadata for guided early-day behavior.

This keeps the real economy path intact while reducing early death spirals.

### End-of-day readability
The settlement layer now returns guided teaching summaries for the first 3 days based on real settlement data.

Added summary fields:
- `guided_day_number`
- `guided_learning_title`
- `guided_earned_summary`
- `guided_spent_summary`
- `guided_change_summary`
- `guided_watch_tomorrow`

These are generated from actual earned, spent, net, burden, and stress signals rather than client-side tutorial text.

## Frontend Changes

Files updated:
- `src/types/onboarding.ts`
- `src/lib/api/onboarding.ts`
- `src/types/gameplay.ts`
- `src/lib/api/gameplay.ts`
- `src/components/gameplay/OnboardingBanner.tsx`
- `src/components/gameplay/EndOfDaySummaryCard.tsx`
- `src/pages/gameplay/GameDashboardPage.tsx`
- `src/lib/gameEvents.ts`

Key changes:
- Continued footer guidance through Day 2 and Day 3 using backend guided state.
- Used backend `highlighted_action_key` to drive dock emphasis.
- Updated the banner to support guided pressure/opportunity messaging.
- Added a guided lesson box to the end-of-day summary card for days 1-3.
- Suppressed high-severity local random event overlays during days 1-3 as a secondary UI smoothing layer.

## Canonical Behavior Preserved

Step 55 does not introduce:
- a fake tutorial economy
- a separate beginner progression system
- client-owned onboarding truth
- shortcut unlocks that bypass the canonical day progression path

The guided experience remains interruption-safe because it is derived from persisted backend onboarding/day state and the existing progression bundle.

## Validation

Automated validation completed:
- `pytest tests/test_onboarding_service.py tests/test_onboarding_api.py tests/test_onboarding_integration.py`
- Result: `10 passed`
- `npm run typecheck`
- Result: passed
- `npm run lint`
- Result: passed with 6 pre-existing warnings and no new errors

Additional checks completed:
- Touched-file diagnostics returned no new static errors.
- Naming-integrity scan found no active token/wallet-era residue in touched runtime files.

## Test Coverage Added or Updated

Files updated:
- `tests/test_onboarding_service.py`
- `tests/test_onboarding_api.py`
- `tests/test_onboarding_integration.py`

Coverage includes:
- Day 2 staged reveal and pressure guidance
- Day 3 staged reveal and opportunity guidance
- dashboard highlighted action behavior
- API/state shape updates for guided-day fields
- integration of progression into guided-day config

## Risks and Limits

Not completed in this terminal-only workflow:
- Manual first-time user playthrough through Day 3 in the running mobile app
- Manual reload/background-resume validation during the guided Day 1-3 flow

Those scenarios are partially covered indirectly by the existing persistence path and the onboarding/integration tests, but they were not executed as a hands-on UI session in this step.

## Outcome

Step 55 now provides a controlled first 3 days that:
- teach the real loop in sequence
- reveal complexity gradually
- reduce early punishment without mutating the core economy
- improve end-of-day interpretation
- keep guidance mobile-first and backend-driven
