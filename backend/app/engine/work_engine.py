"""
Work engine for Gold Penny â€” all shift business logic lives here.

No FastAPI imports; pure Python + SQLAlchemy only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.engine.balance_config import (
    apply_health_decay_rate,
    apply_income_multiplier,
    apply_stress_sensitivity,
)
from app.models.contribution_event import ContributionEvent
from app.models.game_state import GameState
from app.models.job_action import JobAction
from app.models.job_definition import JOB_CATALOG, MAIN_JOBS, SIDE_JOBS, JobDefinition, resolve_job_definition
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.xgp_transaction import XGPTransaction
from app.services.job_key_service import normalize_job_key, normalize_main_job_key
from app.services.player_daily_state_service import ensure_player_daily_state
from app.services.player_transaction_log_service import record_player_transaction

# â”€â”€ Day limits â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MAX_MAIN_HOURS_PER_DAY = 8
MAX_SIDE_HOURS_PER_DAY = 4
MAX_WORK_ACTIONS_PER_DAY = 2
MIN_HEALTH_TO_WORK = 15
MAX_FATIGUE_FOR_SECOND_SHIFT = 90


@dataclass
class WorkResult:
    """Carries the outcome of a single processed shift."""

    job_name: str
    job_type: str
    shift_number: int
    day: int
    hours_worked: int
    base_hourly_pay: float
    productivity: float
    earned_cash: float
    stress_change: int
    health_change: int
    fatigue_change: float
    overtime_penalty_applied: bool
    hours_remaining_after: int
    # Player snapshot after the shift
    player_cash: float
    player_health: int
    player_stress: int
    player_fatigue: float
    player_total_hours_worked_today: int
    player_work_actions_today: int


class WorkEngine:
    """Processes player work shifts, enforcing all game rules."""

    # â”€â”€ Public entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def process_work_action(
        self,
        db: Session,
        player: Player,
        job_name: str,
        hours_worked: int,
    ) -> WorkResult:
        """
        Validate and apply a work shift for *player*.

        Raises ValueError for any rule violation (caller converts to HTTP 400/403).
        Commits DB changes before returning.
        """
        current_day = self._get_current_day(db)

        # Reset daily counters when a new in-game day begins
        self._maybe_reset_daily_counters(player, current_day)

        job_def = self._load_and_validate_job(player, job_name, hours_worked)
        shift_number = player.work_actions_today + 1

        self._validate_shift_eligibility(player, job_def, hours_worked, shift_number)

        # â”€â”€ Calculations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        base_hourly_pay = job_def.monthly_salary / 30 / 8
        productivity = self._calc_productivity(player, shift_number)
        earned_cash = base_hourly_pay * hours_worked * productivity

        total_hours_after = player.total_hours_worked_today + hours_worked
        overtime_penalty = total_hours_after > 8

        stress_change = self._calc_stress(job_def, hours_worked, shift_number, overtime_penalty)
        health_change = self._calc_health_loss(hours_worked, shift_number, overtime_penalty)
        fatigue_change = self._calc_fatigue(hours_worked, shift_number)

        # ── Step 68: apply Day 1 balance config multipliers ───────────────
        # These are reversible, additive-only adjustments driven by the active
        # preset in balance_config.  The identities are: normal preset = 1.0
        # on all multipliers, so this is a no-op with the default preset.
        earned_cash = apply_income_multiplier(earned_cash)
        stress_change = apply_stress_sensitivity(stress_change)
        health_change = apply_health_decay_rate(health_change)

        # Capture the pre-shift snapshot for the ledger and per-day state row.
        balance_before: float = round(float(player.cash), 4)
        stress_before = int(player.stress)
        health_before = int(player.health)
        hours_before = int(player.hours_available)

        # â”€â”€ Apply to player â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        player.cash = float(player.cash) + earned_cash
        player.stress = self._clamp(int(player.stress) + stress_change, 0, 100)
        player.health = self._clamp(int(player.health) - health_change, 0, 100)
        player.fatigue = self._clamp(float(player.fatigue) + fatigue_change, 0.0, 100.0)
        player.hours_available = max(int(player.hours_available) - hours_worked, 0)
        player.total_hours_worked_today = int(player.total_hours_worked_today) + hours_worked
        player.work_actions_today = int(player.work_actions_today) + 1
        player.last_worked_day = current_day

        if job_def.category == "main":
            player.main_job_hours_today = int(player.main_job_hours_today) + hours_worked
        else:
            player.side_job_hours_today = int(player.side_job_hours_today) + hours_worked

        # â”€â”€ Persist job action record â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        action = JobAction(
            player_id=player.id,
            job_name=job_name,
            job_type=job_def.category,
            shift_number=shift_number,
            day=current_day,
            hours_worked=hours_worked,
            base_hourly_pay=round(base_hourly_pay, 4),
            productivity=round(productivity, 4),
            earned_cash=round(earned_cash, 2),
            stress_change=stress_change,
            health_change=-health_change,       # stored as negative (loss)
            fatigue_change=round(fatigue_change, 4),
            overtime_penalty_applied=overtime_penalty,
            hours_remaining_after=int(player.hours_available),
        )
        db.add(action)
        db.flush()   # gives action.id without committing yet

        # ── XGP transaction ledger ────────────────────────────────────────
        # Every XGP inflow must produce a ledger row.  No balance mutation
        # is allowed without a corresponding XGPTransaction entry.
        balance_after: float = round(float(player.cash), 4)
        xgp_tx = XGPTransaction(
            player_id=player.id,
            transaction_type="job_income",
            direction="in",
            amount=round(earned_cash, 4),
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="job_action",
            reference_id=str(action.id),
            description=f"Main job income — {job_name} shift {shift_number}",
        )
        db.add(xgp_tx)
        record_player_transaction(
            db,
            player=player,
            day=current_day,
            transaction_type="wage_income",
            category="work",
            asset_symbol=None,
            quantity=hours_worked,
            unit_price=round(base_hourly_pay, 4),
            gross_amount=round(earned_cash, 4),
            fee_amount=0,
            net_cash_delta=round(earned_cash, 4),
            resulting_cash_balance=balance_after,
            metadata={
                "job_name": job_name,
                "job_type": job_def.category,
                "shift_number": shift_number,
                "productivity": round(productivity, 4),
            },
        )

        # ── Contribution event (raw input for monthly PFT scoring) ──────────
        # The reward engine reads these rows at epoch close time to build
        # ContributionSnapshot records.  Do NOT compute PFT here.
        import json as _json
        contribution = ContributionEvent(
            player_id=player.id,
            event_type="job_work",
            xgp_value=round(earned_cash, 4),
            event_units=float(hours_worked),
            metadata_json=_json.dumps({
                "job_id": job_name,
                "job_type": job_def.category,
                "day_number": current_day,
                "shift_number": shift_number,
                "productivity_multiplier": round(productivity, 4),
                "base_hourly_pay": round(base_hourly_pay, 4),
                "overtime_penalty": overtime_penalty,
            }),
        )
        db.add(contribution)

        # ── Update lifetime counters on player ───────────────────────────
        # lifetime_xgp_earned was added in Step 1 (monetary constitution).
        try:
            player.lifetime_xgp_earned = round(
                float(player.lifetime_xgp_earned or 0.0) + earned_cash, 4
            )
        except AttributeError:
            pass  # Field not yet present on older DB — safe to skip.
        # ── Step 3: update PlayerDailyState within the same transaction ───────
        # After a successful work shift, record the updated vitals in the
        # per-day state row so the settlement engine has an accurate snapshot.
        self._update_player_daily_state(
            db,
            player,
            current_day,
            job_def.category,
            hours_worked=hours_worked,
            earned_cash=earned_cash,
            balance_before=balance_before,
            stress_before=stress_before,
            health_before=health_before,
            hours_before=hours_before,
        )
        db.commit()
        db.refresh(player)

        return WorkResult(
            job_name=job_name,
            job_type=job_def.category,
            shift_number=shift_number,
            day=current_day,
            hours_worked=hours_worked,
            base_hourly_pay=round(base_hourly_pay, 4),
            productivity=round(productivity, 4),
            earned_cash=round(earned_cash, 2),
            stress_change=stress_change,
            health_change=-health_change,
            fatigue_change=round(fatigue_change, 2),
            overtime_penalty_applied=overtime_penalty,
            hours_remaining_after=int(player.hours_available),
            player_cash=round(float(player.cash), 2),
            player_health=int(player.health),
            player_stress=int(player.stress),
            player_fatigue=round(float(player.fatigue), 2),
            player_total_hours_worked_today=int(player.total_hours_worked_today),
            player_work_actions_today=int(player.work_actions_today),
        )

    # â”€â”€ Day management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _update_player_daily_state(
        self,
        db: Session,
        player: Player,
        current_day: int,
        job_category: str,
        *,
        hours_worked: int,
        earned_cash: float,
        balance_before: float,
        stress_before: int,
        health_before: int,
        hours_before: int,
    ) -> None:
        """Update the PlayerDailyState row for *player* on *current_day*.

        Called inside process_work_action's transaction (before commit) so the
        daily state always reflects the latest vitals after each shift.
        Safe to skip on any error — the work transaction succeeds regardless.
        """
        try:
            pds = ensure_player_daily_state(
                db,
                player=player,
                day_number=current_day,
                defaults={
                    "hours_available_start": hours_before,
                    "hours_available_end": int(player.hours_available),
                    "worked_main_job": (job_category == "main"),
                    "worked_hours": int(hours_worked),
                    "gross_income_xgp": Decimal(str(round(earned_cash, 4))),
                    "did_settlement": False,
                    "stress_start": stress_before,
                    "stress_end": int(player.stress),
                    "health_start": health_before,
                    "health_end": int(player.health),
                    "cash_start": Decimal(str(balance_before)),
                    "cash_end": round(float(player.cash or 0), 4),
                },
            )
            # Update end-of-shift snapshot values.
            if job_category == "main":
                pds.worked_main_job = True
            pds.worked_hours = int(getattr(pds, "worked_hours", 0) or 0) + int(hours_worked)
            pds.gross_income_xgp = Decimal(str(round(float(getattr(pds, "gross_income_xgp", 0) or 0) + earned_cash, 4)))
            pds.hours_available_end = int(player.hours_available)
            pds.stress_end = int(player.stress)
            pds.health_end = int(player.health)
            pds.cash_end = round(float(player.cash or 0), 4)
        except Exception:
            pass  # Non-critical — do not break the work transaction.

    def _get_current_day(self, db: Session) -> int:
        state = db.query(GameState).order_by(GameState.id.asc()).first()
        return int(state.current_day) if state is not None else 1

    def _maybe_reset_daily_counters(self, player: Player, current_day: int) -> None:
        """Reset all daily work counters when a new in-game day starts."""
        if player.last_worked_day != current_day:
            player.main_job_hours_today = 0
            player.side_job_hours_today = 0
            player.total_hours_worked_today = 0
            player.work_actions_today = 0
            player.hours_available = 24

    # â”€â”€ Validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _load_and_validate_job(
        self,
        player: Player,
        job_name: str,
        hours_worked: int,
    ) -> JobDefinition:
        canonical_job_name = normalize_job_key(job_name, allow_aliases=True)
        job_def = resolve_job_definition(canonical_job_name)
        if job_def is None:
            raise ValueError(f"Unknown job: '{job_name}'. Valid jobs: {sorted(JOB_CATALOG)}")

        if hours_worked < 1:
            raise ValueError("hours_worked must be at least 1.")

        if job_def.category == "main":
            if hours_worked > MAX_MAIN_HOURS_PER_DAY:
                raise ValueError(
                    f"Main job shifts cannot exceed {MAX_MAIN_HOURS_PER_DAY} hours. "
                    f"Requested: {hours_worked}."
                )
            player_main_job = normalize_main_job_key(player.main_job, allow_aliases=True)
            if not player_main_job:
                raise ValueError("No main job is assigned yet. Choose a job before starting a shift.")
            if player_main_job and player_main_job != canonical_job_name:
                raise ValueError(
                    f"Your assigned main job is '{player_main_job}', not '{canonical_job_name}'."
                )
        else:  # side
            if hours_worked > MAX_SIDE_HOURS_PER_DAY:
                raise ValueError(
                    f"Side job shifts cannot exceed {MAX_SIDE_HOURS_PER_DAY} hours. "
                    f"Requested: {hours_worked}."
                )
            if player.side_job and player.side_job != job_name:
                raise ValueError(
                    f"Your assigned side job is '{player.side_job}', not '{canonical_job_name}'."
                )

        return job_def

    def _validate_shift_eligibility(
        self,
        player: Player,
        job_def: JobDefinition,
        hours_worked: int,
        shift_number: int,
    ) -> None:
        # Global daily action cap
        if int(player.work_actions_today) >= MAX_WORK_ACTIONS_PER_DAY:
            raise ValueError("You have already completed the maximum of 2 work actions today.")

        # Health floor
        if int(player.health) <= MIN_HEALTH_TO_WORK:
            raise ValueError(
                f"Health is too low to work ({player.health}/100). "
                f"Minimum required: {MIN_HEALTH_TO_WORK + 1}."
            )

        # Second-shift fatigue block
        if shift_number == 2 and float(player.fatigue) >= MAX_FATIGUE_FOR_SECOND_SHIFT:
            raise ValueError(
                f"Fatigue is too high for a second shift ({player.fatigue:.1f}/100). "
                f"Must be below {MAX_FATIGUE_FOR_SECOND_SHIFT}."
            )

        # Category-specific daily hour caps
        if job_def.category == "main":
            if int(player.main_job_hours_today) > 0:
                raise ValueError("You have already worked your main job shift today.")
            if int(player.main_job_hours_today) + hours_worked > MAX_MAIN_HOURS_PER_DAY:
                raise ValueError(
                    f"Main job hour cap is {MAX_MAIN_HOURS_PER_DAY} hours/day. "
                    f"You already worked {player.main_job_hours_today} main-job hours."
                )
        else:
            if int(player.side_job_hours_today) > 0:
                raise ValueError("You have already worked your side job shift today.")
            if int(player.side_job_hours_today) + hours_worked > MAX_SIDE_HOURS_PER_DAY:
                raise ValueError(
                    f"Side job hour cap is {MAX_SIDE_HOURS_PER_DAY} hours/day. "
                    f"You already worked {player.side_job_hours_today} side-job hours."
                )

        # Available hours check
        if hours_worked > int(player.hours_available):
            raise ValueError(
                f"Not enough available hours. "
                f"Requested {hours_worked}h but only {player.hours_available}h remaining today."
            )

    # â”€â”€ Stat calculations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _calc_productivity(self, player: Player, shift_number: int) -> float:
        """
        Base productivity before second-shift penalty, clamped, then penalty applied.
        """
        raw = (
            1.0
            - 0.004 * float(player.stress)
            - 0.003 * (100.0 - float(player.health))
            - 0.002 * float(player.fatigue)
            + 0.01 * float(player.skill_level)
        )
        clamped = self._clamp(raw, 0.45, 1.10)
        if shift_number == 2:
            clamped *= 0.85
        return clamped

    def _calc_stress(
        self,
        job_def: JobDefinition,
        hours_worked: int,
        shift_number: int,
        overtime_penalty: bool,
    ) -> int:
        gain = job_def.base_stress + round(hours_worked * 0.6)
        if overtime_penalty:
            gain += 2
        if shift_number == 2:
            gain = round(gain * 1.35)
        return gain

    def _calc_health_loss(
        self,
        hours_worked: int,
        shift_number: int,
        overtime_penalty: bool,
    ) -> int:
        if hours_worked < 4:
            loss = 0
        elif hours_worked < 8:
            loss = 1
        else:
            loss = 2
        if overtime_penalty:
            loss += 1
        if shift_number == 2:
            loss += 1
        return loss

    def _calc_fatigue(self, hours_worked: int, shift_number: int) -> float:
        gain = hours_worked * 0.8
        if shift_number == 2:
            gain *= 1.4
        return gain

    # â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2 — standalone pure helper functions
#
# These functions are deliberately decoupled from the WorkEngine class so they
# can be unit-tested without a database session.  The WorkEngine internals call
# equivalent logic via its own methods, but these public functions expose the
# same calculations for external callers (e.g. API dry-run, tests, CLI tools).
#
# Economic design:
#   - Work earns XGP (off-chain gameplay currency).
#   - Earning XGP costs health, stress, and available hours.
#   - There is no direct XGP→PFT conversion.
#   - Contribution events produced here will feed Step 1 PFT scoring later.
# ═══════════════════════════════════════════════════════════════════════════════


def calculate_productivity(health: float, stress: float) -> float:
    """Compute a player's work productivity modifier for a shift.

    Formula
    -------
        productivity = 1.0 - 0.004 × stress - 0.003 × (100 - health)

    Clamped to [0.55, 1.05].  A fully healthy, unstressed player scores
    1.0 and can marginally exceed it through skill bonuses elsewhere.

    Parameters
    ----------
    health:
        Player health (0–100). Lower health reduces productivity.
    stress:
        Player stress (0–100). Higher stress reduces productivity.

    Returns
    -------
    float
        Productivity multiplier, clamped to [0.55, 1.05].
    """
    raw = 1.0 - 0.004 * max(0.0, stress) - 0.003 * (100.0 - max(0.0, min(100.0, health)))
    return round(max(0.55, min(1.05, raw)), 4)


def calculate_hourly_rate(base_salary_monthly: float) -> float:
    """Derive the per-hour XGP rate from a monthly salary figure.

    Assumes 30-day months and 8-hour working days:
        hourly_rate = monthly_salary / 30 / 8

    Parameters
    ----------
    base_salary_monthly:
        Gross monthly salary in XGP units.

    Returns
    -------
    float
        XGP earned per hour worked.
    """
    if base_salary_monthly <= 0:
        return 0.0
    return round(base_salary_monthly / 30.0 / 8.0, 4)


def calculate_work_effects(
    job_id: str,
    hours_worked: int,
    health: float,
    stress: float,
    skill_level: float = 1.0,
) -> dict:
    """Compute the full set of outcomes for one work shift.

    This is the authoritative calculation for XGP earned and stat changes.
    It mirrors the WorkEngine internals but is fully self-contained and
    does not touch the database.

    Parameters
    ----------
    job_id:
        Key into JOB_CATALOG (e.g. ``"banker"``).
    hours_worked:
        Number of hours in this shift (positive integer).
    health:
        Player health before the shift (0–100).
    stress:
        Player stress before the shift (0–100).
    skill_level:
        Player skill level.  1.0 baseline; higher values give a small XGP
        bonus, lower values a small penalty.  Clipped to [1, 20].

    Returns
    -------
    dict with keys:
        base_hourly_rate      (float)  — XGP per hour at this job
        productivity_multiplier (float) — health/stress modifier [0.55, 1.05]
        skill_multiplier        (float) — skill bonus [0.80, 1.25]
        earned_xgp              (float) — total XGP for the shift
        stress_change           (int)   — positive = stress increase
        health_change           (int)   — negative = health loss

    Raises
    ------
    ValueError
        If ``job_id`` is not found in JOB_CATALOG.
    """
    job_def = JOB_CATALOG.get(job_id)
    if job_def is None:
        raise ValueError(
            f"Unknown job_id '{job_id}'. Valid options: {sorted(JOB_CATALOG)}"
        )

    hours_worked = max(1, int(hours_worked))

    # Productivity from current vitals.
    productivity = calculate_productivity(health, stress)

    # Hourly rate from monthly salary definition.
    hourly_rate = calculate_hourly_rate(job_def.monthly_salary)

    # Skill multiplier: +5 % per level above 1, bounded.
    raw_skill_mult = 1.0 + (max(1.0, float(skill_level)) - 1.0) * 0.05
    skill_multiplier = round(max(0.80, min(1.25, raw_skill_mult)), 4)

    # XGP earned — always non-negative.
    earned_xgp = max(0.0, hourly_rate * hours_worked * productivity * skill_multiplier)

    # Stress change: job base + proportional hours effect.
    stress_change = round(
        job_def.base_stress * hours_worked / 8.0 + hours_worked * 0.5
    )
    stress_change = max(0, min(stress_change, 30))  # sensible cap per shift

    # Health change: only significant for long shifts.
    if hours_worked >= 10:
        health_change = -2
    elif hours_worked >= 6:
        health_change = -1
    else:
        health_change = 0

    return {
        "base_hourly_rate": hourly_rate,
        "productivity_multiplier": productivity,
        "skill_multiplier": skill_multiplier,
        "earned_xgp": round(earned_xgp, 4),
        "stress_change": stress_change,
        "health_change": health_change,
    }


def validate_work_action(
    hours_requested: int,
    hours_available: int,
    already_worked_today: bool,
    max_daily_main_job_hours: int = 8,
) -> tuple[bool, str | None]:
    """Validate a main-job work request before any DB state is touched.

    This is the anti-exploit gate for the main shift.  It is intentionally
    strict: the backend economy depends on no player being able to grind
    unlimited XGP in a single day.

    Parameters
    ----------
    hours_requested:
        Number of hours the player wants to work.
    hours_available:
        Remaining availability in the player's day.
    already_worked_today:
        ``True`` if the player has already used their main-job shift today.
    max_daily_main_job_hours:
        Cap on main-job hours per day (default: 8).

    Returns
    -------
    (True, None)
        Request is valid.
    (False, reason_string)
        Request is invalid; ``reason_string`` explains why.
    """
    if hours_requested <= 0:
        return False, "hours_requested must be at least 1."

    if hours_requested > max_daily_main_job_hours:
        return (
            False,
            f"Main job shifts are capped at {max_daily_main_job_hours} hours per day. "
            f"Requested {hours_requested} hours.",
        )

    if hours_requested > hours_available:
        return (
            False,
            f"Not enough daily hours remaining. "
            f"Requested {hours_requested} h but only {hours_available} h available.",
        )

    if already_worked_today:
        return (
            False,
            "You have already worked your main job shift today. "
            "Main job is limited to one shift per in-game day.",
        )

    return True, None
