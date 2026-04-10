# STEP 93F - Leisure Action Limit Fix And Stress Recovery Rules

## Goal

Fix false blocking between leisure/recovery actions and make stress recovery understandable through:

- explicit per-action limits
- an explicit recovery category cap
- passive off-hours recovery
- stronger Houston-local weekend recovery

## Root Cause Of Incorrect Blocking

The incorrect "You already used this action enough times today" blocker was caused by two overlapping problems:

1. The dashboard recovery buttons were not sending distinct backend recovery actions.
   - `Watch TV`, `Watch Movie`, and `Jogging` were effectively routed through generic recovery handling.
   - `Read Book` was previously routed through `study`.

2. The Expo client kept its own local per-day action guard in `useDailySession`.
   - It did not understand the new recovery action keys.
   - Unknown recovery actions defaulted to generic time-cost and generic cap behavior.
   - That made different recovery actions feel like they were sharing one stale exhausted state.

The result was a mixed frontend/backend state where one recovery action could make another valid recovery action look unavailable for the wrong reason.

## New Recovery Limit System

Recovery actions are now modeled as a first-class category with explicit per-action caps.

### Recovery / Leisure Category

Category members:

- `rest`
- `watch_tv`
- `watch_movie`
- `read_book`
- `jogging`

Meals remain visible in the same dashboard section, but dinner is enforced through the meal/survival system instead of the leisure cap.

### Specific Action Caps

- Rest: `2/day`, `-6 stress`
- Watch TV: `1/day`, `-4 stress`
- Watch Movie: `1/day`, `-5 stress`
- Read Book: `2/day`, `-3 stress`
- Jogging: `1/day`, `-3 stress`, `+2 health`
- Eat Meal: `1 dinner resolution via meal system`, `-2 stress`, `+2 health`, `0` time units

### Category Cap

- Recovery / Leisure category cap: `4/day`

### Important Separation

- Dinner is not counted against the recovery category cap.
- Required survival meal handling still works even when recovery category usage is exhausted.

## Exact Blocker Rules

Recovery actions now expose explicit blocker reasons instead of a vague shared message.

Supported blocker texts:

- `Rest daily limit reached`
- `Watch Movie daily limit reached`
- `Recovery category limit reached`
- `Not enough time left today`
- `Meal already completed`
- `Action unavailable during active shift`
- `Day already settled.`

## Passive Stress Recovery Rules

Passive recovery now applies from time away from the main job.

### Weekday Off-Hours Recovery

Rule:

- For every `2 hours` away from main-shift work, recover stress passively.

Formula:

- Normal off-hours block: `-2 stress per 2 hours`
- If rideshare happened during that off-hours block: `-1 stress per 2 hours`
- Weekday passive off-hours recovery cap: `-8 stress/day`

Current implementation uses an `8-hour` weekday off-hours window and converts that window into:

- pure off-hours blocks
- rideshare blocks

That keeps rideshare from counting as full rest while still allowing some passive recovery.

## Weekend Stress Recovery Rules

Weekend recovery now uses Houston-local weekend detection from `America/Chicago`.

Houston-local rule:

- Saturday/Sunday in Houston time receive weekend recovery

Weekend recovery values:

- No rideshare: `-12 stress` (`tier = full`)
- Moderate rideshare: `-8 stress` (`tier = moderate`)
- Heavy rideshare: `-5 stress` (`tier = heavy`)

Heavy rideshare currently starts at `>= 6.0 hours` of rideshare work.

Weekend recovery is reduced by rideshare, but it is not removed.

## Rideshare Interaction

Rideshare is treated as:

- not main-shift work
- not full rest

Effects:

- rideshare still allows some passive off-hours recovery
- rideshare weakens passive recovery instead of canceling it
- weekend recovery still applies on rideshare weekends, but at reduced strength

## Player Visibility Changes

The dashboard recovery section now shows:

- `Recovery actions used`
- `Recovery remaining`
- `Passive off-hours`
- `Weekend recovery`
- per-action remaining uses
- exact per-action block reason when blocked

Examples now visible in UI:

- `Recovery actions remaining today: 2`
- `Watch Movie remaining: 1`
- `Rest daily limit reached`
- `Meal system separate from recovery cap.`

## Before / After Examples

### Before

- Use `Rest` twice.
- Try `Watch Movie`.
- Get a vague blocker like:
  - `You already used this action enough times today.`

The blocker did not explain whether the issue was:

- Rest cap
- category cap
- time
- stale local state

### After

Scenario: `Rest` twice, then `Watch Movie`

- `Rest` hits only its own cap.
- `Watch Movie` stays available if total category usage is still below `4/day`.
- If blocked, the reason is explicit.

Scenario: fifth total recovery action

- The fifth leisure action is blocked with:
  - `Recovery category limit reached`

Scenario: dinner after category cap

- Dinner still succeeds because it is handled by the meal/survival system, not by the leisure cap.

## Files Changed

- `backend/app/services/recovery_service.py`
- `backend/app/services/shift_state_service.py`
- `backend/app/api/gameplay.py`
- `backend/app/engine/life_balance_service.py`
- `backend/app/engine/financial_distress_service.py`
- `backend/app/services/dinner_survival_service.py`
- `backend/tests/test_shift_state_service.py`
- `backend/tests/test_life_balance_service.py`
- `expo/src/hooks/useDailySession.ts`
- `expo/src/lib/balanceConfig.ts`
- `expo/src/features/gameplayLoop/screens/DashboardScreen.tsx`
- `expo/src/features/gameplayLoop/screens/LifeScreen.tsx`
- `expo/src/features/gameplayLoop/context.tsx`
- `expo/src/features/gameplayLoop/mockData.ts`
- `expo/src/types/gameplay.ts`

## Validation Results

Validated behaviors:

- Rest twice does not falsely block Watch Movie before the category cap
- specific daily caps block only that action
- category cap blocks the fifth leisure action with the correct reason
- dinner remains available after recovery category exhaustion
- passive off-hours recovery weakens when rideshare fills off-hours
- weekend recovery stays positive with moderate/heavy rideshare
- recovery state is refreshed after each successful recovery action
- Expo typecheck passes with the new recovery-state payload

Validation commands run:

- `python -m unittest tests.test_shift_state_service tests.test_life_balance_service`
- `yarn typecheck`

## Final Outcome

This step removes hidden leisure-action blocking, makes recovery limits explicit, and adds passive/off-hours/weekend stress relief that better matches the intended life-sim loop.

The result is:

- clearer recovery rules
- no false cross-action blocking
- visible remaining uses
- weekend recovery that still helps even when the player grinds some rideshare
