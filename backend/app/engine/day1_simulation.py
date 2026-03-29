"""Step 68 — Day 1 pure in-memory batch simulation.

This module contains a fully deterministic, DB-free simulation harness for
calibrating the Day 1 player experience.  It mirrors the formulas from
work_engine.py and daily_engine.py exactly so that preset changes produce the
same effects in simulation as they do in a live session.

Design rules
------------
- No database access.  No FastAPI imports.
- All randomness is seeded so runs are reproducible.
- The simulation uses JOB_CATALOG directly for realistic salary figures.
- Typical Day 1 expense estimates are parameterised (not hardcoded) so the
  expense_pressure_multiplier preset value has an observable effect.

Public surface
--------------
    simulate_day1_session(config, profile, seed)
        → Day1SimResult for a single session

    run_day1_batch_simulation(config, *, n_sessions, seed)
        → Day1BatchResult with aggregate metrics

    describe_batch_result(batch_result)
        → human-readable summary string

    calibrate_presets()
        → dict mapping preset_name → Day1BatchResult (runs all 4 presets)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from app.engine.balance_config import (
    DAY1_BALANCE_PRESETS,
    apply_health_decay_rate,
    apply_income_multiplier,
    apply_stress_sensitivity,
)
from app.models.job_definition import JOB_CATALOG

# ── Calibration targets ───────────────────────────────────────────────────────
COMPLETION_RATE_TARGET = 0.70   # ≥70 % of sessions should "complete" Day 1
MAX_TARGET_STRESS_GAIN = 25     # stress delta should not exceed this on average
MIN_TARGET_STRESS_GAIN = 5      # stress delta should be at least this (noticeable)
CASH_DELTA_MIN = 15.0           # minimum acceptable average cash delta
CASH_DELTA_MAX = 200.0          # maximum acceptable average cash delta (avoids trivial)
MIN_OPPORTUNITY_RATE = 0.50     # at least 50 % of sessions show an opportunity

# ── Typical Day 1 expense constants (pre-multiplier) ─────────────────────────
# These represent the realistic daily obligation load a new player faces:
# rent amortised per day + basic food/transport costs.
TYPICAL_DAILY_EXPENSE_BASE = 48.0   # xgp / day (pre-multiplier)

# Opportunity surfaces as a probabilistic event based on spawn_rate compared
# to a uniform draw in [0, 1].  A spawn_rate of 1.0 yields ~60 % base rate.
OPPORTUNITY_BASE_PROBABILITY = 0.60

# ── Typical starting-player profiles ─────────────────────────────────────────
# Each profile represents a segment of the expected Day 1 player cohort.
PLAYER_PROFILES: list[dict] = [
    # Entry-level worker, average stats
    {"job": "retail_worker", "starting_cash": 500.0, "stress": 20, "health": 85, "skill": 0, "fatigue": 0.0},
    # Auto mechanic, slightly stressed
    {"job": "auto_mechanic", "starting_cash": 400.0, "stress": 30, "health": 80, "skill": 1, "fatigue": 10.0},
    # Chef, high stress, average health
    {"job": "chef", "starting_cash": 350.0, "stress": 35, "health": 75, "skill": 0, "fatigue": 5.0},
    # Banker, mentally loaded, good cash cushion
    {"job": "banker", "starting_cash": 600.0, "stress": 25, "health": 90, "skill": 2, "fatigue": 0.0},
    # Retail + rideshare (two shifts), tight cash
    {"job": "retail_worker", "starting_cash": 250.0, "stress": 15, "health": 90, "skill": 0, "fatigue": 0.0,
     "side_job": "rideshare"},
    # Aircraft mechanic, well-resourced
    {"job": "aircraft_mechanic", "starting_cash": 700.0, "stress": 20, "health": 85, "skill": 3, "fatigue": 0.0},
    # Chef, near-broke
    {"job": "chef", "starting_cash": 150.0, "stress": 40, "health": 70, "skill": 0, "fatigue": 20.0},
    # Retail, high health but high stress
    {"job": "retail_worker", "starting_cash": 300.0, "stress": 45, "health": 80, "skill": 0, "fatigue": 0.0},
]


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class Day1SimResult:
    """Outcome of a single simulated Day 1 session."""
    preset_name: str
    job: str
    starting_cash: float
    ending_cash: float
    cash_delta: float
    starting_stress: int
    ending_stress: int
    stress_delta: int
    starting_health: int
    ending_health: int
    health_delta: int
    income_earned: float
    expenses_paid: float
    completed: bool            # positive cash delta AND stress < threshold
    had_opportunity: bool
    # Per-shift detail
    shifts: list[dict] = field(default_factory=list)


@dataclass
class Day1BatchResult:
    """Aggregated metrics from a batch simulation run."""
    preset_name: str
    n_sessions: int
    completion_rate: float
    avg_cash_delta: float
    avg_stress_delta: float
    avg_health_delta: float
    avg_income_earned: float
    avg_expenses_paid: float
    opportunity_rate: float
    # Spread / percentiles
    min_cash_delta: float
    max_cash_delta: float
    p25_cash_delta: float
    p75_cash_delta: float
    # Calibration pass/fail
    meets_completion_target: bool
    meets_stress_target: bool
    meets_cash_target: bool
    meets_opportunity_target: bool
    calibration_pass: bool
    sessions: list[Day1SimResult] = field(default_factory=list)


# ── Pure formula helpers (mirrors work_engine.py + daily_engine.py) ───────────

def _calc_productivity(stress: int, health: int, fatigue: float, skill: int) -> float:
    raw = (
        1.0
        - 0.004 * float(stress)
        - 0.003 * float(100 - health)
        - 0.002 * float(fatigue)
        + 0.01 * float(skill)
    )
    return max(0.45, min(1.10, raw))


def _calc_earned_cash(job_name: str, hours: int, productivity: float) -> float:
    job = JOB_CATALOG[job_name]
    hourly = job.monthly_salary / 30 / 8
    return hourly * hours * productivity


def _calc_stress_gain(job_name: str, hours: int, shift_number: int, overtime: bool) -> int:
    job = JOB_CATALOG[job_name]
    gain = job.base_stress + round(hours * 0.6)
    if overtime:
        gain += 2
    if shift_number == 2:
        gain = round(gain * 1.35)
    return gain


def _calc_health_loss(hours: int, shift_number: int, overtime: bool) -> int:
    if hours < 4:
        loss = 0
    elif hours < 8:
        loss = 1
    else:
        loss = 2
    if overtime:
        loss += 1
    if shift_number == 2:
        loss += 1
    return loss


def _calc_stress_recovery(stress: int, hours_remaining: int, worked: bool) -> int:
    recovery = 4
    if hours_remaining >= 8:
        recovery += 2
    if hours_remaining >= 12:
        recovery += 1
    if worked:
        recovery -= 1
    return min(max(2, min(8, recovery)), stress)


def _calc_health_recovery(health: int, stress: int, hours_remaining: int) -> int:
    if stress >= 95:
        return -2
    if stress >= 85:
        return -1
    if hours_remaining >= 8 and stress < 70:
        return 1
    return 0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Single session simulation ─────────────────────────────────────────────────

def simulate_day1_session(
    config: dict[str, float],
    profile: dict,
    preset_name: str = "unknown",
    *,
    seed: int | None = None,
) -> Day1SimResult:
    """Simulate one Day 1 session against *config* for the given *profile*.

    Parameters
    ----------
    config:
        A Day 1 balance config dict (from DAY1_BALANCE_PRESETS or
        get_active_day1_config()).
    profile:
        Player profile dict with keys: job, starting_cash, stress, health,
        skill, fatigue.  Optional key 'side_job' triggers a second shift.
    preset_name:
        Label for the result object only.
    seed:
        If provided, seeds the RNG for reproducibility.
    """
    rng = random.Random(seed)

    cash = float(profile["starting_cash"])
    stress = int(profile["stress"])
    health = int(profile["health"])
    skill = int(profile.get("skill", 0))
    fatigue = float(profile.get("fatigue", 0.0))
    main_job = profile["job"]
    side_job: str | None = profile.get("side_job")

    starting_cash = cash
    starting_stress = stress
    starting_health = health
    shifts: list[dict] = []
    total_income = 0.0
    total_hours_worked = 0

    # ── Main job shift (8 hours) ───────────────────────────────────────────
    main_hours = 8
    total_hours_after_main = total_hours_worked + main_hours
    overtime_main = total_hours_after_main > 8

    prod_main = _calc_productivity(stress, health, fatigue, skill)
    earned_main = _calc_earned_cash(main_job, main_hours, prod_main)
    stress_gain_main = _calc_stress_gain(main_job, main_hours, shift_number=1, overtime=overtime_main)
    health_loss_main = _calc_health_loss(main_hours, shift_number=1, overtime=overtime_main)

    # Apply balance multipliers
    earned_main = apply_income_multiplier(earned_main, config)
    stress_gain_main = apply_stress_sensitivity(stress_gain_main, config)
    health_loss_main = apply_health_decay_rate(health_loss_main, config)

    fatigue += main_hours * 0.8
    fatigue = _clamp(fatigue, 0.0, 100.0)
    total_hours_worked += main_hours

    cash += earned_main
    stress = int(_clamp(stress + stress_gain_main, 0, 100))
    health = int(_clamp(health - health_loss_main, 0, 100))
    total_income += earned_main

    shifts.append({
        "job": main_job,
        "shift": 1,
        "hours": main_hours,
        "earned": round(earned_main, 2),
        "stress_gain": stress_gain_main,
        "health_loss": health_loss_main,
    })

    # ── Optional side job shift (4 hours) ──────────────────────────────────
    if side_job and fatigue < 90:
        side_hours = 4
        total_hours_after_side = total_hours_worked + side_hours
        overtime_side = total_hours_after_side > 8

        prod_side = _calc_productivity(stress, health, fatigue, skill) * 0.85  # shift 2 penalty
        earned_side = _calc_earned_cash(side_job, side_hours, prod_side)
        stress_gain_side = _calc_stress_gain(side_job, side_hours, shift_number=2, overtime=overtime_side)
        health_loss_side = _calc_health_loss(side_hours, shift_number=2, overtime=overtime_side)

        earned_side = apply_income_multiplier(earned_side, config)
        stress_gain_side = apply_stress_sensitivity(stress_gain_side, config)
        health_loss_side = apply_health_decay_rate(health_loss_side, config)

        fatigue += side_hours * 0.8 * 1.4
        fatigue = _clamp(fatigue, 0.0, 100.0)
        total_hours_worked += side_hours

        cash += earned_side
        stress = int(_clamp(stress + stress_gain_side, 0, 100))
        health = int(_clamp(health - health_loss_side, 0, 100))
        total_income += earned_side

        shifts.append({
            "job": side_job,
            "shift": 2,
            "hours": side_hours,
            "earned": round(earned_side, 2),
            "stress_gain": stress_gain_side,
            "health_loss": health_loss_side,
        })

    # ── End-of-day settlement ──────────────────────────────────────────────
    hours_remaining = max(0, 16 - total_hours_worked)   # 16 waking hours budget

    # Expenses (scaled by config multiplier)
    expense_mult = config.get("expense_pressure_multiplier", 1.0)
    # Add small per-session noise (±5 xgp) for realistic spread
    noise = rng.uniform(-5.0, 5.0)
    daily_expenses = round((TYPICAL_DAILY_EXPENSE_BASE + noise) * expense_mult, 2)
    cash -= daily_expenses

    # Daily recovery
    stress_recovery = _calc_stress_recovery(stress, hours_remaining, worked=True)
    stress = int(_clamp(stress - stress_recovery, 0, 100))

    health_adj = _calc_health_recovery(health, stress, hours_remaining)
    health = int(_clamp(health + health_adj, 0, 100))

    # ── Opportunity spawn ──────────────────────────────────────────────────
    spawn_rate = config.get("opportunity_spawn_rate", 1.0)
    effective_prob = min(0.98, OPPORTUNITY_BASE_PROBABILITY * spawn_rate)
    had_opportunity = rng.random() < effective_prob

    # ── Completion check ───────────────────────────────────────────────────
    cash_delta = cash - starting_cash
    stress_delta = stress - starting_stress
    completed = cash_delta > 0 and stress < 80

    return Day1SimResult(
        preset_name=preset_name,
        job=main_job,
        starting_cash=starting_cash,
        ending_cash=round(cash, 2),
        cash_delta=round(cash_delta, 2),
        starting_stress=starting_stress,
        ending_stress=stress,
        stress_delta=stress_delta,
        starting_health=starting_health,
        ending_health=health,
        health_delta=health - starting_health,
        income_earned=round(total_income, 2),
        expenses_paid=round(daily_expenses, 2),
        completed=completed,
        had_opportunity=had_opportunity,
        shifts=shifts,
    )


# ── Batch simulation ──────────────────────────────────────────────────────────

def run_day1_batch_simulation(
    config: dict[str, float],
    *,
    preset_name: str = "unknown",
    n_sessions: int = 60,
    seed: int = 42,
) -> Day1BatchResult:
    """Run *n_sessions* simulated Day 1 sessions and return aggregate metrics.

    Sessions cycle through PLAYER_PROFILES so all profile types are
    represented evenly.  A fixed *seed* ensures identical results for the same
    config, making before/after comparisons reliable.
    """
    if n_sessions < 1:
        raise ValueError("n_sessions must be at least 1.")

    sessions: list[Day1SimResult] = []
    for i in range(n_sessions):
        profile = PLAYER_PROFILES[i % len(PLAYER_PROFILES)]
        result = simulate_day1_session(
            config,
            profile,
            preset_name=preset_name,
            seed=seed + i,
        )
        sessions.append(result)

    n = len(sessions)
    cash_deltas = sorted(s.cash_delta for s in sessions)
    stress_deltas = [s.stress_delta for s in sessions]
    health_deltas = [s.health_delta for s in sessions]

    def _avg(vals: list[float | int]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _percentile(sorted_vals: list[float], pct: float) -> float:
        idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * pct)))
        return sorted_vals[idx]

    completion_rate = sum(1 for s in sessions if s.completed) / n
    avg_cash_delta = _avg(cash_deltas)
    avg_stress_delta = _avg(stress_deltas)
    avg_health_delta = _avg(health_deltas)
    avg_income = _avg([s.income_earned for s in sessions])
    avg_expenses = _avg([s.expenses_paid for s in sessions])
    opportunity_rate = sum(1 for s in sessions if s.had_opportunity) / n

    # Calibration pass / fail per target
    meets_completion = completion_rate >= COMPLETION_RATE_TARGET
    meets_stress = MIN_TARGET_STRESS_GAIN <= avg_stress_delta <= MAX_TARGET_STRESS_GAIN
    meets_cash = CASH_DELTA_MIN <= avg_cash_delta <= CASH_DELTA_MAX
    meets_opportunity = opportunity_rate >= MIN_OPPORTUNITY_RATE
    calibration_pass = meets_completion and meets_stress and meets_cash and meets_opportunity

    return Day1BatchResult(
        preset_name=preset_name,
        n_sessions=n,
        completion_rate=round(completion_rate, 4),
        avg_cash_delta=round(avg_cash_delta, 2),
        avg_stress_delta=round(avg_stress_delta, 2),
        avg_health_delta=round(avg_health_delta, 2),
        avg_income_earned=round(avg_income, 2),
        avg_expenses_paid=round(avg_expenses, 2),
        opportunity_rate=round(opportunity_rate, 4),
        min_cash_delta=round(cash_deltas[0], 2),
        max_cash_delta=round(cash_deltas[-1], 2),
        p25_cash_delta=round(_percentile(cash_deltas, 0.25), 2),
        p75_cash_delta=round(_percentile(cash_deltas, 0.75), 2),
        meets_completion_target=meets_completion,
        meets_stress_target=meets_stress,
        meets_cash_target=meets_cash,
        meets_opportunity_target=meets_opportunity,
        calibration_pass=calibration_pass,
        sessions=sessions,
    )


# ── Multi-preset calibration sweep ───────────────────────────────────────────

def calibrate_presets(
    *,
    n_sessions: int = 60,
    seed: int = 42,
) -> dict[str, Day1BatchResult]:
    """Run all 4 presets and return a dict of batch results.

    Useful for producing the STEP68 calibration report.  Each preset is run
    with the same seed and session count for fair comparison.
    """
    return {
        name: run_day1_batch_simulation(
            config,
            preset_name=name,
            n_sessions=n_sessions,
            seed=seed,
        )
        for name, config in DAY1_BALANCE_PRESETS.items()
    }


# ── Human-readable summary ────────────────────────────────────────────────────

def describe_batch_result(r: Day1BatchResult) -> str:
    """Return a compact multi-line summary of a batch result for reports."""
    status = "PASS" if r.calibration_pass else "FAIL"
    lines = [
        f"Preset: {r.preset_name}  [{status}]  n={r.n_sessions}",
        f"  completion_rate:    {r.completion_rate:.1%}  {'✓' if r.meets_completion_target else '✗'}  (target ≥{COMPLETION_RATE_TARGET:.0%})",
        f"  avg_cash_delta:     {r.avg_cash_delta:+.2f} xgp  {'✓' if r.meets_cash_target else '✗'}  (target {CASH_DELTA_MIN:.0f}–{CASH_DELTA_MAX:.0f})",
        f"  avg_stress_delta:   {r.avg_stress_delta:+.1f}  {'✓' if r.meets_stress_target else '✗'}  (target {MIN_TARGET_STRESS_GAIN}–{MAX_TARGET_STRESS_GAIN})",
        f"  avg_health_delta:   {r.avg_health_delta:+.2f}",
        f"  opportunity_rate:   {r.opportunity_rate:.1%}  {'✓' if r.meets_opportunity_target else '✗'}  (target ≥{MIN_OPPORTUNITY_RATE:.0%})",
        f"  cash_delta p25/p75: {r.p25_cash_delta:+.2f} / {r.p75_cash_delta:+.2f}",
        f"  avg income:         {r.avg_income_earned:.2f}  avg expenses: {r.avg_expenses_paid:.2f}",
    ]
    return "\n".join(lines)
