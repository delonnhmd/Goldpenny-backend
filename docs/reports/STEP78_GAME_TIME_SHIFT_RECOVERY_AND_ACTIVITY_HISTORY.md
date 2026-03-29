# STEP78_GAME_TIME_SHIFT_RECOVERY_AND_ACTIVITY_HISTORY

## Summary
Step 78 was implemented in the Dashboard flow to make daily gameplay feel time-based and routine-driven.

## Houston Time Integration
- Added Houston/Central time as the active in-game clock reference (`America/Chicago`).
- Added helper formatters for:
  - current clock (`formatHoustonNow`)
  - date (`formatHoustonDate`)
  - activity timestamps (`formatHoustonTimestamp`)
- Added a **Game Time / Houston Clock** card that shows:
  - Current day
  - Current time (CT)
  - Date
  - Phase/status (`Before shift`, `On shift`, `After shift`, `End of day`)
  - Shift window (`9:00 AM - 5:00 PM (Houston)`)
  - Timer mode (`Real-time mode` or `Accelerated testing mode`)

## Shift Timer and Auto Clock-out
- Added shift runtime state:
  - `activeShift`
  - `autoClockingOut`
- Added shift metadata/constants:
  - `SHIFT_START_HOUR = 9`
  - `SHIFT_END_HOUR = 17`
  - full shift duration (`8h`) and short dev timer mode (`EXPO_PUBLIC_SHIFT_TIMER_SECONDS`, defaults to 90s in dev/short mode)
- Clock-in rules:
  - Requires shift action availability
  - Requires daily session still active
  - Requires action guard pass (time/action caps/etc.)
  - Enforces shift window unless short mode override is active
- Auto clock-out behavior:
  - Countdown runs live while on shift
  - On timer end, work action is executed automatically
  - Shift completion/failure note is recorded in timeline
  - Shift state is cleared and post-shift actions unlock
- End-day button is now disabled while shift is active/auto-clocking-out.

## Ride Share Gating and Tracking
- Added side-income derivations from `actionsTakenToday`:
  - `rideshareTripsToday`
  - `rideshareEarnedToday`
  - cap from balance config (`BALANCE.ACTION_CAPS.side_income`)
- Added strict ride-share availability checks:
  - Blocked during active shift
  - Blocked during shift hours (9 AM-5 PM) unless short mode is active
  - Requires side-income action availability and guard pass
- Replaced vague/technical blocker messages with gameplay messages (including mapping away from `Not authenticated`).
- Added **Post-Shift Ride Share** card with:
  - Status text
  - Trips today (`x / cap`)
  - Ride-share earnings today
  - Time cost per trip
  - Action button with runtime-disabled state

## Recovery Actions Added
- Added visible **Recovery Actions** card on Dashboard.
- Added direct action list:
  - Watch TV
  - Watch Movie
  - Read Book
  - Jogging
  - Eat Meal
  - Rest
- Each action row shows:
  - Time cost
  - Stress delta
  - Health delta
  - Skill delta
- Recovery actions are blocked during active/auto-clocking-out shift.

## Daily Activity History Structure
- Added `TimelineNote` support for local timeline events (clock-in, timer end, completion outcomes).
- Built merged current-day timeline:
  - Existing `dailySession.actionsTakenToday`
  - Local timeline notes
- Sorted and rendered in chronological order in **Activity History** card.
- Includes time label + title + detail for each event.
- Covers work, ride share, recovery, meals, and finance/debt events from action history.

## Dashboard Structure After Step 78
Dashboard now exposes the requested action-first routine view:
- Game time
- Status
- Work/shift state with timer and clock-in
- Ride-share state + trips + earnings
- Recovery list
- Activity history
- Finance actions

## Files Changed
- `src/features/gameplayLoop/screens/DashboardScreen.tsx`

## Validation Results
### Completed
- `npx eslint src/features/gameplayLoop/screens/DashboardScreen.tsx` passed.
- Verified new Dashboard sections and state wiring in code:
  - Houston clock card
  - Shift countdown and auto clock-out logic
  - Ride-share gating + counters + earnings display
  - Visible recovery list
  - Live activity history merge

### Repository-wide Typecheck Status
- `yarn typecheck` currently fails due **pre-existing unrelated errors** outside Step 78 scope:
  - `src/features/gameplayLoop/screens/WorkScreen.tsx` (`onPreviewAction` vs `onExecuteAction` mismatch)
  - `src/pages/gameplay/GameDashboardPage.tsx` prop mismatch errors
- No type/lint errors were reported for the updated `DashboardScreen.tsx` file itself.
