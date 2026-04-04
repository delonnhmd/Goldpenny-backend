# Step 84 Missed Shift And Rideshare System

## Summary

Step 84 removes the old "dead day" failure mode.

Players can now skip a weekday shift without breaking the loop, see the consequence clearly, and keep playing with ride share once the scheduled work window is over.

This step adds:

- fixed weekday shift windows per main job
- missed-shift detection with health and stress consequences instead of a hidden cash punishment
- post-shift rideshare unlocks based on backend schedule rules
- weekend behavior that feels different from weekdays
- lightweight meal tracking so truly inactive days get a survival penalty
- frontend work and rideshare copy that explains what is happening

## Shift Rules

Houston time (`America/Chicago`) is the source of truth for shift windows.

Job schedule map:

| Job | Start | End |
| --- | --- | --- |
| `banker` | `10:00` | `18:00` |
| `chef` | `09:00` | `17:00` |
| `retail` | `10:00` | `18:00` |
| `delivery` | `08:00` | `16:00` |
| `auto_mechanic` | `08:00` | `17:00` |
| `aircraft_mechanic` | `06:00` | `14:00` |

Backend work-state payload now exposes:

- `day_of_week`
- `is_weekend`
- `shift_required_today`
- `scheduled_shift_start`
- `scheduled_shift_end`
- `scheduled_shift_start_label`
- `scheduled_shift_end_label`
- `scheduled_shift_window_label`
- `missed_shift_today`
- `rideshare_unlock_time_label`

## Daily State Updates

Added to `player_daily_states`:

- `missed_shift`
- `meals_recorded`
- `survival_penalty_applied`

These fields make the new missed-shift and idle-day rules idempotent, so repeated dashboard fetches do not duplicate penalties.

## Missed Shift Logic

On weekday days with a main job:

- if there is no active shift
- and the player did not work
- and Houston time is past the scheduled shift end

the backend now:

- marks `missed_shift = true`
- keeps salary at `0`
- writes a zero-amount `expense/missed_work` ledger row
- writes a zero-amount `expense/health_penalty` ledger row
- applies `health -= 5`
- applies `stress += 6`

Ledger examples:

- `Missed shift (Banker 10:00 AM-6:00 PM) - no salary earned`
- `Health -5, Stress +6`

The old ordinary "missed work cash penalty" is no longer injected by settlement for skipping a normal weekday shift. The existing `missed_work_penalty_xgp` field still remains for life-balance burnout or medical-event penalties.

## Survival Penalty

If the player records no meals and has no meaningful day activity:

- no main-work progress
- no side-income work
- no business work
- no already-applied missed-shift penalty

settlement now applies:

- `health -= 5`
- `stress += 4`

and writes:

- `expense/health_penalty`
- description: `No meals or activity - Health -5, Stress +4`

Meal tracking is intentionally lightweight. `eat_meal` now increments `meals_recorded` for the current day and does not introduce a more complex meal subsystem.

## Rideshare Unlock Conditions

Ride share is now backend-controlled with these rules:

- always blocked while `shift_active == true`
- unlocked when `shift_active == false` and one of the following is true:
- current Houston time is at or past the scheduled shift end
- the gameplay day is Saturday or Sunday
- the player has no main job

Important behavior change:

- finishing a shift early does not unlock ride share early
- weekday ride share waits for the scheduled shift window to end

The backend also writes one zero-amount ride-share visibility event when the unlock state becomes visible, for example:

- `Rideshare unlocked at 6:00 PM`
- `Rideshare available all day (weekend)`
- `Rideshare available all day (no required shift)`

## Weekend Behavior

Weekend detection is based on gameplay day mapped from the 2026 game epoch.

On Saturday and Sunday:

- no required main shift
- no missed-shift penalty
- ride share is available all day
- the UI explains that the day is a weekend

Main-job actions were not redesigned, but the required-shift rule is removed on weekends so the flow feels different and side income is open immediately.

## UI Updates

### Brief Screen

`Work Status` now shows three clear states:

- worked: `Worked`, the scheduled window, and earned salary
- missed: `Missed shift`, `No salary earned`, and `Health -5 / Stress +6`
- weekend: `Weekend`, `No required shift`, and `Ride Share available all day`

`Daily Activity` continues to show the ledger, which now includes:

- missed shift explanation
- health/stress consequence rows
- rideshare unlock visibility rows

### Dashboard Screen

Shift window display is now driven from backend schedule metadata instead of a hardcoded `9:00 AM - 5:00 PM`.

Ride share status text now matches the rule set:

- before unlock: `Available after 6:00 PM (shift end)`
- after unlock: `Available now`
- weekend: `Available all day (weekend)`

The action hub also now blocks late weekday clock-ins after a missed shift and explains why.

## Before vs After

### Before

- skipping work on a weekday could feel opaque or break the intended flow
- ride share depended on "shift completed" logic instead of the scheduled work window
- weekends behaved too much like weekdays
- the UI could show stale or misleading rideshare copy
- no simple survival consequence existed for a truly inactive day

### After

- players can skip work and still continue the day
- the missed-shift consequence is visible and understandable
- ride share unlocks when the backend says the shift window is over
- weekends clearly remove the required shift pressure
- fully idle days now have a small, visible survival consequence

## Validation Completed

Verified with focused regression coverage:

- weekday skipped shift logs missed-work and health-penalty events
- weekday skipped shift unlocks ride share after the scheduled end
- completed work does not unlock ride share before the scheduled end
- weekend days unlock ride share all day with no missed-shift penalty
- no-activity days apply the survival penalty
- Expo typecheck passes with the new work-state fields

Commands run:

```bash
pytest tests/test_shift_state_service.py tests/test_day_progression_services.py tests/test_life_day_progression.py -q
yarn typecheck
```
