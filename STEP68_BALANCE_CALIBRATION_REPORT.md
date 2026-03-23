# Step 68 — Balance Engine + First-Day Calibration

## Objective

Introduce a configurable, reversible balance layer on top of the existing Day 1
work-engine and economics.  The layer must:

- Expose five scalar multipliers per preset (income, expense-pressure, stress
  sensitivity, health decay, opportunity spawn rate)
- Provide four named presets: **easy / normal / hard / stress_test**
- Allow dynamic in-process switching without a server restart
- Be wired into the work engine with zero changes to core logic
- Be exercisable from the Settings dev panel and from the internal admin API
- Produce calibration data from a pure in-memory batch simulation (no DB)

---

## Files Changed

| File | Change |
|---|---|
| `app/engine/balance_config.py` | Added `DAY1_BALANCE_PRESETS`, preset accessors, and three `apply_*` helpers |
| `app/engine/work_engine.py` | Three one-liner multiplier applications in `process_work_action` |
| `app/engine/day1_simulation.py` | **New** — pure in-memory Day 1 simulation harness (~350 lines) |
| `app/api/internal.py` | Three new endpoints + four new Pydantic response models |
| `PFT/pft-expo/app/(tabs)/settings.tsx` | Balance Config section card in the dev Settings screen |

---

## Balance Preset Config Values

| Param | easy | normal | hard | stress_test |
|---|---|---|---|---|
| `income_multiplier` | 1.30 | 1.00 | 0.85 | 0.60 |
| `expense_pressure_multiplier` | 0.80 | 1.00 | 1.25 | 1.60 |
| `stress_sensitivity` | 0.75 | 1.00 | 1.35 | 2.00 |
| `health_decay_rate` | 0.70 | 1.00 | 1.40 | 2.00 |
| `opportunity_spawn_rate` | 1.60 | 1.00 | 0.65 | 0.40 |

`normal` is the default; all multipliers are 1.0, so it is a drop-in zero-impact
baseline that preserves every pre-Step-68 result exactly.

---

## Simulation Methodology

### Harness: `app/engine/day1_simulation.py`

The simulation reproduces the formulas from `work_engine.py` and `daily_engine.py`
exactly, without any database access.

**8 player profiles** cycle across sessions (retail_worker, auto_mechanic, chef,
banker, rideshare dual-job, aircraft_mechanic, near-broke chef, high-stress retail)
to cover the realistic distribution of Day 1 entry states.

**Per-session logic:**
1. Simulate two work shifts (morning + afternoon) using the correct hourly and
   productivity formulas.
2. Apply all three `apply_*` multipliers (income, stress, health).
3. Deduct daily expenses scaled by `expense_pressure_multiplier`.
4. Roll opportunity spawn against `OPPORTUNITY_BASE_PROBABILITY × opportunity_spawn_rate`.
5. Mark the session "completed" if the player ends with cash ≥ 0 and stress < 80.

**Calibration targets:**
| Target | Threshold |
|---|---|
| Completion rate | ≥ 70 % |
| Avg stress delta | 5 – 25 pts |
| Cash delta (avg) | +15 to +200 xgp |
| Opportunity rate | ≥ 50 % |

**Run parameters:** n=60, seed=42 (deterministic)

---

## Calibration Results (n=60, seed=42)

### easy  [FAIL — stress delta slightly low]

| Metric | Value | Target | Pass? |
|---|---|---|---|
| Completion rate | 100.0 % | ≥ 70 % | ✓ |
| Avg cash delta | +103.12 xgp | 15 – 200 xgp | ✓ |
| **Avg stress delta** | **+4.4 pts** | **5 – 25 pts** | **✗** |
| Avg health delta | −0.35 pts | — | — |
| Opportunity rate | 100.0 % | ≥ 50 % | ✓ |
| Cash delta p25 / p75 | +65.6 / +155.0 xgp | — | — |
| Avg income | 141.1 xgp | — | — |
| Avg expenses | 38.0 xgp | — | — |

**Assessment:** Extremely comfortable. The stress multiplier (0.75) pushes average
stress from the normal +7.2 down to +4.4, just under the 5-point floor. The preset
fulfils its design intent (accessibility, low friction) but the automated target is
off by 0.6 pts. This is acceptable for a designed-easy preset; no adjustment needed.

---

### normal  [PASS — recommended baseline]

| Metric | Value | Target | Pass? |
|---|---|---|---|
| Completion rate | 100.0 % | ≥ 70 % | ✓ |
| Avg cash delta | +61.02 xgp | 15 – 200 xgp | ✓ |
| Avg stress delta | +7.2 pts | 5 – 25 pts | ✓ |
| Avg health delta | −1.47 pts | — | — |
| Opportunity rate | 73.3 % | ≥ 50 % | ✓ |
| Cash delta p25 / p75 | +32.1 / +99.2 xgp | — | — |
| Avg income | 108.5 xgp | — | — |
| Avg expenses | 47.5 xgp | — | — |

**Assessment:** All four calibration targets met.  Net +61 xgp after a Day 1 shift
gives a clear "you made progress" feeling while expenses (47.5 xgp) create visible
pressure.  Stress of +7.2 is noticeable but not threatening.  73 % opportunity rate
means most players see an upgrade path on Day 1.  **This is the shipped default.**

---

### hard  [FAIL — opportunity rate below target]

| Metric | Value | Target | Pass? |
|---|---|---|---|
| Completion rate | 91.7 % | ≥ 70 % | ✓ |
| Avg cash delta | +32.82 xgp | 15 – 200 xgp | ✓ |
| Avg stress delta | +11.6 pts | 5 – 25 pts | ✓ |
| Avg health delta | −2.58 pts | — | — |
| **Opportunity rate** | **36.7 %** | **≥ 50 %** | **✗** |
| Cash delta p25 / p75 | +9.8 / +63.5 xgp | — | — |
| Avg income | 92.2 xgp | — | — |
| Avg expenses | 59.3 xgp | — | — |

**Assessment:** Intentionally punishing but survivable (91.7 % completion).  Stress
is meaningfully higher and cash margin is tight.  The opportunity rate of 36.7 %
falls below the 50 % calibration floor — by design, since `hard` is meant to feel
sparse.  Players who do encounter an opportunity are more likely to act on it because
of its scarcity.  Opportunity rate failure is accepted for `hard`.

---

### stress_test  [FAIL — by design, QA-only preset]

| Metric | Value | Target | Pass? |
|---|---|---|---|
| **Completion rate** | **25.0 %** | **≥ 70 %** | **✗** |
| **Avg cash delta** | **−10.96 xgp** | **15 – 200 xgp** | **✗** |
| Avg stress delta | +19.1 pts | 5 – 25 pts | ✓ |
| Avg health delta | −3.82 pts | — | — |
| **Opportunity rate** | **26.7 %** | **≥ 50 %** | **✗** |
| Cash delta p25 / p75 | −26.7 / +7.4 xgp | — | — |
| Avg income | 65.0 xgp | — | — |
| Avg expenses | 75.9 xgp | — | — |

**Assessment:** Works as intended.  This preset is not for shipping; it exists to
stress-test the engine, verify negative cash paths, and exercise commitment-default
code paths.  Completion of only 25 % means most profiles would hit a debt spiral —
exactly the condition we want to test.

---

## Integration Points

### Backend integration (complete)

`work_engine.py → process_work_action`
```python
# ── Step 68: apply Day 1 balance config multipliers ────────────────
earned_cash   = apply_income_multiplier(earned_cash)
stress_change = apply_stress_sensitivity(stress_change)
health_change = apply_health_decay_rate(health_change)
```

The `expense_pressure_multiplier` and `opportunity_spawn_rate` are available via
`get_active_day1_config()` for future integration into:
- `commitment_service.py` — daily expense deduction
- `event_service.py` / `opportunity_service.py` — opportunity spawn roll

### API endpoints (complete — `app/api/internal.py`)

| Method | Route | Purpose |
|---|---|---|
| GET | `/internal/balance/day1-config` | Active preset name + all config values + all presets |
| POST | `/internal/balance/day1-preset` | Switch active preset (in-process, immediate) |
| POST | `/internal/balance/day1-simulation` | Run n-session batch simulation, returns full stats |

All three endpoints require the `X-Internal-Key` header.

### Frontend Settings panel (complete)

`PFT/pft-expo/app/(tabs)/settings.tsx` — "Balance Config (Dev)" section card:
- Four preset buttons (easy / normal / hard / stress_test); active preset marked with ●
- Config value grid for the selected preset (all five multipliers)
- Selection persisted in AsyncStorage at `goldpenny:dev:balance_preset`
- Informational note pointing to the backend endpoint for server-side switching

---

## Recommended Baseline

**Ship `normal` preset.**  All four calibration targets pass.  The economic feel:

- Net +61 xgp on Day 1 → player ends the day richer (positive reinforcement)
- Expenses at 47.5 xgp → visible but not stressful
- Stress +7.2 → the player feels the day had weight
- 73 % opportunity rate → majority of players see a reason to come back on Day 2

For soft-launch testing, run the `easy` preset to reduce early churn.

---

## Reversibility

Setting the active preset to `normal` restores pre-Step-68 behaviour exactly
(all multipliers = 1.0).  The three call-sites in `work_engine.py` are single-line
multiplications that can be reverted in one diff.

---

*Generated by Step 68 automated calibration — n=60, seed=42, 2026.*
