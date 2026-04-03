# Step 83 Transparency System

## Summary

Step 83 makes the daily economy easier to understand from both the backend and the player UI.

It adds:

- a dedicated player-facing transaction ledger
- day-level work tracking with salary vs missed-work outcomes
- stricter ride share unlock rules
- visible starter business costs and cash gap messaging

## Transaction Schema

New table: `gameplay_transactions`

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `player_id` | UUID | FK to `players.id` |
| `day` | integer | Gameplay day number |
| `type` | string | `income` or `expense` |
| `category` | string | `salary`, `food`, `gas`, `rent`, `ride_share`, `stress_penalty` |
| `amount` | numeric(14,4) | Positive for income, negative for expense |
| `description` | text | Player-readable explanation |
| `timestamp` | timestamptz | Creation time |

Also added to `player_daily_states`:

- `did_work`
- `shift_start`
- `shift_end`
- `salary_earned`
- `missed_penalty`

## Ledger Write Rules

The following systems now write player-facing ledger rows:

- main shift completion writes `income/salary`
- ride share completion writes `income/ride_share`
- daily settlement writes `expense/food` when food spend exists
- daily settlement writes `expense/gas` when weekly gas or commute fuel exists
- daily settlement writes `expense/rent` for rent and utilities
- daily settlement writes `expense/stress_penalty` for missed scheduled work or life penalty cash loss

Legacy `player_transaction_logs` settlement auditing remains in place, but the Brief screen now reads from `gameplay_transactions`.

## New API

Endpoint:

`GET /gameplay/player/{id}/transactions?day=14`

Response shape:

```json
{
  "player_id": "uuid",
  "day": 14,
  "transactions": [
    {
      "id": "uuid",
      "player_id": "uuid",
      "day": 14,
      "type": "income",
      "category": "salary",
      "amount": 120.0,
      "description": "Banker shift salary",
      "timestamp": "2026-04-02T12:34:56+00:00"
    },
    {
      "id": "uuid",
      "player_id": "uuid",
      "day": 14,
      "type": "expense",
      "category": "food",
      "amount": -18.0,
      "description": "Daily food cost",
      "timestamp": "2026-04-02T12:35:10+00:00"
    }
  ],
  "total_income": 498.53,
  "total_expense": 495.83,
  "net": 2.7
}
```

Behavior:

- defaults to the current gameplay day when `day` is omitted
- returns one resolved day at a time
- totals are derived from ledger rows, not estimated on the client

## Work Tracking Changes

Backend rules:

- if a main shift completes, `did_work = true`
- `shift_start` and `shift_end` are stored
- `salary_earned` is persisted for the day
- if the player has a scheduled main job but does not work, `did_work = false`
- missed work applies a cash penalty and stress increase
- `missed_penalty` is persisted for that day

Frontend Brief screen now shows:

- `WORK STATUS`
- worked state: `Worked` and salary earned
- missed-work state: `Missed work` and penalty amount
- no-shift-scheduled state
- shift-not-finished-yet state

## Ride Share Unlock Fix

Ride share is now allowed only when:

- `shift_active == false`
- and either `shift_completed_today == true` or `no_shift_scheduled == true`

Ride share is rejected when:

- the player is currently inside an active main shift

This is enforced in both the action-hub messaging and the ride share execution path.

## Business Visibility Changes

Starter business costs are now surfaced explicitly:

- Fruit Shop: `500`
- Food Truck: `1200`

When the player has no active business, the Business screen now shows:

- `Start Business`
- business name
- cost
- current cash
- remaining gap needed to unlock

## UI Changes

### Brief screen

Added `Daily Activity`:

- per-transaction list
- total income
- total expense
- net

Added `Work Status`:

- worked vs missed-work summary
- salary earned or penalty paid
- clearer explanation of why the day turned out the way it did

### Business screen

Replaced `No business yet` empty state with starter business cost visibility:

- Fruit Shop card
- Food Truck card
- `You have`
- `Need`

### Daily brief card

The dashboard brief card now accepts optional impact bullets from the dashboard page and renders them below the summary when available.

## Before vs After

### Before

- end of day changed cash with limited explanation
- players could not see a clean list of salary, rent, food, and penalties
- missed work was not clearly represented as a daily tracked outcome
- ride share unlock behavior was easy to misread
- business startup requirements were hidden behind a vague empty state

### After

- every major daily money movement is visible as a ledger row
- the Brief screen explains where cash came from and where it went
- daily work outcome is explicit: worked, missed work, or no scheduled shift
- ride share becomes available only after a valid post-shift state
- starter business requirements are visible before unlock

## Validation Completed

Verified in focused automated checks:

- end-of-day settlement produces visible ledger rows
- completed work produces salary tracking and salary ledger entries
- missed work produces penalty tracking and a stress-penalty ledger entry
- ride share works after shift completion
- ride share also works when no main shift is scheduled
- Expo frontend typecheck passes

Commands run:

```bash
pytest tests/test_shift_state_service.py tests/test_day_progression_services.py tests/test_life_day_progression.py -q
yarn typecheck
```
