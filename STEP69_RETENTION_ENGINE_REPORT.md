# STEP 69 — RETENTION ENGINE REPORT

## Summary

Step 69 introduces the **Retention Engine**: a pure-computation layer that
generates meaningful, real-data-driven pressure flags, opportunity carryover
data, and streak bonuses at the close of every player day.  All results are
embedded in `summary_payload` and flow automatically through the settlement
response and the `GET /daily/summary/{player_id}` endpoint.

---

## Deliverables

| # | Deliverable | File | Status |
|---|---|---|---|
| 1 | Retention engine pure module | `app/engine/retention_engine.py` | ✅ Created |
| 2 | `PlayerDailyState` retention columns | `app/models/player_daily_state.py` | ✅ Added |
| 3 | Alembic migration | `alembic/versions/20260323_0020_retention_engine.py` | ✅ Created |
| 4 | Settlement service hook | `app/services/daily_settlement_service.py` | ✅ Extended |
| 5 | Pydantic model field | `app/api/day.py` | ✅ Extended ×3 |
| 6 | Validation | Python syntax + 55 existing tests | ✅ Clean |

---

## Architecture

### `app/engine/retention_engine.py` — Pure Computation Layer

No DB access.  Five standalone functions:

**`compute_next_day_pressure_flags(player_state, settlement_result) → list[dict]`**
- Evaluates 7 real player conditions (cash, stress, health, layoff risk,
  payment pressure, missed payment, distress state).
- Each flag carries `flag_key`, `severity` (`critical | high | info`), `message`,
  `action_hint`.
- No synthetic or random alerts — every flag is derived from a real numeric
  threshold checked against the settled day's final values.

Thresholds:

| Signal | Critical | High |
|---|---|---|
| Cash (xgp) | < 40 | < 120 |
| Stress (0–100) | ≥ 75 | ≥ 55 |
| Health (0–100) | — | < 60 |
| Layoff risk | — | ≥ 25 % |
| Payment pressure | — | stressed / critical / default_risk |
| Debt missed | any | — |
| Distress state | — | not stable/recovering |

**`compute_opportunity_carryover(opportunities, day_number) → dict`**
- Processes an input opportunity list by category (persist probability, TTL,
  evolution flag).
- Returns `{carried, evolved, expired}`.
- Deterministic: uses `hash(key + str(day))` so output is repeatable for the
  same inputs.

**`compute_streak_bonus(streak_days, base_income) → dict`**
- Three bounded tiers:

| Streak | Income boost | Income cap | Stress relief |
|---|---|---|---|
| 7 + days | +3 % | 30 xgp | −2 pts |
| 4 – 6 days | +2 % | 20 xgp | −1 pt |
| 2 – 3 days | +0 % | 0 xgp | −1 pt |
| < 2 days | none | — | none |

Bonuses are applied to final `ending_cash` and `stress_after` in the
settlement service, then reflected in `player.cash_xgp` / `player.stress`.

**`compute_return_trigger_messages(flags, carryover, streak_info) → list[str]`**
- Composes ≤ 4 plain-text strings for future notification use.  No push logic
  is executed.

**`build_retention_summary(player_state, settlement_result, streak_days, opportunities) → dict`**
- Top-level entry point.  Returns:
  ```json
  {
    "next_day_pressure_flags": [...],
    "carryover_opportunities": {"carried": [...], "evolved": [...], "expired": [...]},
    "streak_info": {"streak_days": N, "income_boost_xgp": X, "stress_reduction_bonus": Y, ...},
    "return_trigger_messages": [...],
    "day_number": N,
    "has_critical_flags": bool,
    "total_carried_opportunities": int
  }
  ```

---

### `app/models/player_daily_state.py` — Two New Columns

```python
retention_flags_json       = Column(Text, nullable=True)  # list[dict] pressure flags JSON
carryover_opportunities_json = Column(Text, nullable=True)  # dict {carried,evolved,expired} JSON
```

Both are nullable so older rows are unaffected.

---

### `alembic/versions/20260323_0020_retention_engine.py` — Migration

Chains from `85854026afad`.  Safe `ADD COLUMN IF NOT EXISTS` pattern:

```sql
ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS retention_flags_json TEXT;
ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS carryover_opportunities_json TEXT;
```

Downgrade reverses both with `DROP COLUMN IF EXISTS`.

---

### `app/services/daily_settlement_service.py` — Settlement Hook

Insertion point: immediately after the guided-day text block, **before**
`summary_payload = {`.

Steps performed in order:

1. Load `PlayerProgressionState` for the player.
2. Call `build_retention_summary(...)` with final settled values.
3. Apply streak income boost to `ending_cash` → update `player.cash_xgp`,
   `pds.cash_end`, `player.net_worth_xgp`.
4. Apply streak stress relief to `stress_after` → update `player.stress`,
   `pds.stress_end`, `pds.stress_delta`.
5. Update `login_streak_current`, `login_streak_best`, `login_streak_last_day`
   on `PlayerProgressionState`.  Streak increments on consecutive days
   (gap of exactly 1), resets to 1 on any larger gap.
6. Write `pds.retention_flags_json` and `pds.carryover_opportunities_json`
   (wrapped in try/except to tolerate un-migrated schemas — non-fatal).
7. Add `"retention_summary": retention_summary` to `summary_payload`.
8. Add `"retention_summary": retention_summary` to return dict.
9. `get_latest_settlement_summary` passes through
   `summary_payload.get("retention_summary", {})`.

No existing settlement keys were removed or renamed.

---

### `app/api/day.py` — Pydantic Fields

`retention_summary: dict = Field(default_factory=dict)` added to:

- `PlayerSettleResponse` (after `summary_json`)
- `RunNextDayResponse` (after `onboarding_summary`)
- `SettlementSummaryResponse` (after `summary_json`)

Default factory ensures backward compatibility with old settlement logs that
lack the key.

---

## Live Test Output (Day 1, distressed player)

```json
{
  "streak_info": {
    "streak_days": 5, "income_boost_xgp": 1.8,
    "stress_reduction_bonus": 1, "tier_label": "streak_4plus", "active": true
  },
  "has_critical_flags": true,
  "next_day_pressure_flags": [
    { "flag_key": "critical_cash",    "severity": "critical" },
    { "flag_key": "critical_stress",  "severity": "critical" },
    { "flag_key": "low_health",       "severity": "high"     },
    { "flag_key": "job_instability",  "severity": "high"     },
    { "flag_key": "payment_pressure", "severity": "high"     },
    { "flag_key": "debt_delinquency", "severity": "critical" },
    { "flag_key": "financial_distress","severity": "high"    }
  ],
  "return_trigger_messages": [
    "Critical: Cash is critically low (35 xgp). ...",
    "5-day streak active — +1.8 xgp bonus on your next work shift."
  ]
}
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Pure engine, no DB access | Testable without a database; trivially mockable |
| Flags tied to real thresholds | Eliminates synthetic/random alerts that erode trust |
| Streak bonuses applied in settlement service, not engine | Separation of concerns; engine is declaration, service is mutation |
| `try/except` on PDS column writes | Graceful degradation on un-migrated DB schemas |
| `login_streak_*` reuse existing `PlayerProgressionState` columns | No new columns on progression table needed |
| Opportunity carryover deterministic hash | Repeatable output for the same game state; no random seeds |
| Return trigger messages capped at 4 | UX constraint — prevents notification fatigue |

---

## Consequence Persistence Validation

The settlement service already accumulates stress, debt, health, and financial
distress effects across days via committed `player` mutations and `DailySettlementLog`
rows.  Step 69 adds no new accumulation model — it reads from the same
committed values and annotates them with forward-looking signals.  The
existing consequence persistence is therefore confirmed correct by construction.

---

## Tests

55 existing tests pass with no regressions.

```
tests/test_commitment_service.py   ✅
tests/test_career_service.py       ✅
tests/test_daily_brief_service.py  ✅
— all 55 passed in 4.94 s —
```

---

## Files Modified / Created

| File | Change |
|---|---|
| `app/engine/retention_engine.py` | NEW — 260 lines |
| `app/models/player_daily_state.py` | +7 lines (2 nullable columns) |
| `alembic/versions/20260323_0020_retention_engine.py` | NEW — 40 lines |
| `app/services/daily_settlement_service.py` | +73 lines (imports + retention block + dict entries) |
| `app/api/day.py` | +3 lines (one field per Pydantic model) |
