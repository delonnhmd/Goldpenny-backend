"""
Daily Engine — pure helpers and DB-facing settlement logic.

Design principles:
  - Pure calculation functions are stateless and testable in isolation.
  - DB-facing functions accept a Session and commit atomically.
  - No FastAPI imports; no blockchain calls.
  - Settlement is idempotent: calling it twice for the same day raises ValueError.

Daily lifecycle:
  Day 1:
    - player starts with 24 hours
    - player works 8 hours → stress rises, health may drop, hours consumed
    - player calls POST /daily/settle
      → stress partially recovers
      → health adjusts slightly
      → hours reset to 24
      → next day begins
  Day 2:
    - player carries some stress forward (not fully recovered)
    - health may have recovered +1 if conditions were good
    - 24 fresh hours available
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.engine.needs_engine import (
    build_needs_summary,
    calculate_daily_needs_score,
    calculate_needs_based_settlement_modifiers,
)
from app.models.daily_settlement_log import DailySettlementLog
from app.models.game_state import GameState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState

# Step 7: housing engine imported inside the settlement function to avoid
# circular imports (housing_engine → xgp_transaction → player → ...).


# ─────────────────────────────────────────────────────────────────────────────
# Pure helper functions (stateless, no DB access)
# ─────────────────────────────────────────────────────────────────────────────


def clamp_stat(value: float, min_value: float, max_value: float) -> float:
    """Return *value* clamped to [min_value, max_value]."""
    return max(min_value, min(max_value, value))


def calculate_stress_recovery(
    current_stress: float,
    hours_remaining: int,
    worked_today: bool,
) -> int:
    """
    Determine how much stress is reduced at end of day.

    Recovery rules:
      - Base recovery: 4 points
      - hours_remaining >= 8:  +2 bonus
      - hours_remaining >= 12: +1 additional bonus (stacks with the above)
      - worked_today is True:  -1 penalty (work takes a toll even during rest)
      - Minimum recovery: 2   (sleep always helps a little)
      - Maximum recovery: 8   (diminishing returns even with perfect rest)

    Stress does NOT fully disappear automatically — some stress carries into the
    next day.  A player with high remaining hours and no work recovers the most.
    """
    recovery = 4

    if hours_remaining >= 8:
        recovery += 2
    if hours_remaining >= 12:
        recovery += 1

    if worked_today:
        recovery -= 1

    # Clamp to [2, 8]
    recovery = max(2, min(8, recovery))

    # Cannot recover more stress than the player actually has.
    return min(recovery, int(current_stress))


def calculate_health_recovery(
    current_health: float,
    current_stress: float,
    hours_remaining: int,
) -> int:
    """
    Determine end-of-day health adjustment (positive = gain, negative = loss).

    Light rules only — no medical system yet:
      - If enough rest AND stress is manageable: +1 health
      - High stress causes health damage:
          stress >= 85: -1
          stress >= 95: -2 (replaces the -1, not stacked)
      - Otherwise: 0 change

    The caller is responsible for clamping the result into [0, 100].
    """
    if current_stress >= 95:
        return -2
    if current_stress >= 85:
        return -1
    if hours_remaining >= 8 and current_stress < 70:
        return 1
    return 0


def calculate_next_day_hours() -> int:
    """
    Return the number of available hours to grant at the start of the next day.

    Always 24 for MVP.  In future steps this can be reduced by illness,
    housing conditions, or active events.
    """
    return 24


# ─────────────────────────────────────────────────────────────────────────────
# DB-facing helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_or_create_game_state(db: Session) -> GameState:
    """
    Fetch the singleton GameState row, creating it if none exists.

    GameState is treated as a singleton in MVP — one row tracks global time.
    Only one active row is expected.  If the table is empty, day 1 is initialized.
    """
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    if state is None:
        state = GameState(
            current_day=1,
            day_status="open",
            day_started_at=datetime.now(tz=timezone.utc),
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def get_or_create_player_daily_state(
    db: Session,
    player: Player,
    day_number: int,
) -> PlayerDailyState:
    """
    Fetch the PlayerDailyState row for *player* on *day_number*, creating it
    if it does not yet exist.

    Initialization uses current player vitals so the *_start columns accurately
    reflect what the player's stats were at the beginning of this day.
    """
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == day_number,
        )
        .first()
    )
    if pds is None:
        cash_value = round(float(player.cash or 0), 4)
        pds = PlayerDailyState(
            player_id=player.id,
            day_number=day_number,
            hours_available_start=int(player.hours_available),
            hours_available_end=int(player.hours_available),
            worked_main_job=False,
            did_settlement=False,
            stress_start=int(player.stress),
            stress_end=int(player.stress),
            health_start=int(player.health),
            health_end=int(player.health),
            cash_start=cash_value,
            cash_end=cash_value,
        )
        db.add(pds)
        db.commit()
        db.refresh(pds)
    return pds


def can_player_settle_day(
    player: Player,
    current_day: int,
) -> tuple[bool, Optional[str]]:
    """
    Return (True, None) if the player may settle today, or (False, reason).

    Rule: a player can only settle each in-game day once.  The last_settled_day
    field on Player tracks which day was most recently closed.
    """
    try:
        last_settled = player.last_settled_day
    except AttributeError:
        last_settled = None

    if last_settled is not None and int(last_settled) == int(current_day):
        return False, (
            f"You have already settled day {current_day}. "
            "Wait for the global day to advance before settling again."
        )
    return True, None


def run_player_end_of_day_settlement(db: Session, player: Player) -> dict:
    """
    Core settlement function.  Applies end-of-day recovery rules to *player*,
    writes audit records, and resets daily hours.

    Steps:
      1.  Fetch global game state → current_day
      2.  Verify player has not already settled today (idempotency guard)
      3.  Get/create PlayerDailyState for this day
      4.  Base stress and health recovery calculation
      5.  Step 6: Daily needs evaluation from basket purchases
      6.  Capture before-values for the audit log (before housing deducts cash)
      7.  Step 7: Apply daily housing cost (deducts XGP, adds HousingPayment +
          XGPTransaction to session — NOT yet committed)
      8.  Mutate player vitals with combined base + needs + housing modifiers
      9.  Update PlayerDailyState end-of-day snapshot (needs + housing fields)
      10. Build summary JSON (needs + housing breakdown)
      11. Write DailySettlementLog (immutable audit row)
      12. Commit atomically — rolls back on any failure
      13. Return summary dict

    Design rule: XGP balance is only modified by housing cost (Step 7+).
    All other settlement changes are vitals only (stress / health / hours).
    """
    try:
        # ── 1. Global day ──────────────────────────────────────────────────
        game_state = get_or_create_game_state(db)
        current_day = int(game_state.current_day)

        # ── 2. Idempotency guard ───────────────────────────────────────────
        can_settle, reason = can_player_settle_day(player, current_day)
        if not can_settle:
            raise ValueError(reason)

        # ── 3. Player daily state ──────────────────────────────────────────
        pds = get_or_create_player_daily_state(db, player, current_day)

        # ── 4. Base recovery calculation ───────────────────────────────────
        hours_remaining = int(player.hours_available)
        worked_today = bool(pds.worked_main_job)

        stress_recovery = calculate_stress_recovery(
            current_stress=float(player.stress),
            hours_remaining=hours_remaining,
            worked_today=worked_today,
        )
        health_recovery = calculate_health_recovery(
            current_health=float(player.health),
            current_stress=float(player.stress),
            hours_remaining=hours_remaining,
        )

        # ── 5. Step 6: Daily needs evaluation ─────────────────────────────
        # Read current-day basket totals from the player's daily state.
        # These accumulate whenever the player calls POST /baskets/buy.
        # Default to 0 safely so settlement never fails on zero-purchase days.
        essentials_units  = float(getattr(pds, "essentials_units",  0) or 0)
        protein_units     = float(getattr(pds, "protein_units",     0) or 0)
        produce_units     = float(getattr(pds, "produce_units",     0) or 0)
        convenience_units = float(getattr(pds, "convenience_units", 0) or 0)

        needs_result = calculate_daily_needs_score(
            essentials_units, protein_units, produce_units, convenience_units
        )
        needs_modifiers = calculate_needs_based_settlement_modifiers(
            needs_result["needs_tier"], needs_result["needs_score"]
        )

        stress_penalty   = int(needs_modifiers["stress_penalty_from_needs"])
        health_modifier  = int(needs_modifiers["health_modifier_from_needs"])
        food_quality_mod = int(needs_modifiers["food_quality_modifier"])

        # ── 6. Capture before-values (snapshot BEFORE housing deducts cash) ──
        hours_before  = hours_remaining
        stress_before = int(player.stress)
        health_before = int(player.health)
        cash_before   = round(float(player.cash or 0), 4)

        # ── 7. Step 7: Apply daily housing cost ───────────────────────────
        # Imported here to prevent circular dependency at module load time.
        # This call mutates player.cash and adds HousingPayment + XGPTransaction
        # objects to the session WITHOUT committing — all writes happen atomically
        # in the commit at step 12.
        from app.engine.housing_engine import apply_daily_housing_cost
        housing_result      = apply_daily_housing_cost(db, player, current_day)
        housing_region_id   = housing_result["region_id"]
        housing_amount_paid = housing_result["amount"]
        housing_paid        = housing_result["paid"]
        housing_stress_mod  = int(housing_result["stress_modifier"])

        # Capture post-housing cash balance for the settlement log.
        cash_after = round(float(player.cash or 0), 4)

        # ── 8. Mutate player vitals (base + needs + housing modifiers) ─────
        # Stress formula:
        #   new = current - base_recovery + needs_penalty + housing_modifier
        #   negative values in needs_penalty / housing_modifier = bonus relief
        # Health formula:
        #   new = current + base_recovery + needs_health_modifier
        #   housing does NOT directly modify health in Step 7.
        next_hours = calculate_next_day_hours()

        new_stress = int(clamp_stat(
            stress_before - stress_recovery + stress_penalty + housing_stress_mod,
            0, 100,
        ))
        new_health = int(clamp_stat(health_before + health_recovery + health_modifier, 0, 100))

        player.stress = new_stress
        player.health = new_health
        player.hours_available = next_hours
        player.last_settled_day = current_day

        # Reset daily work counters for the next day.
        player.main_job_hours_today = 0
        player.side_job_hours_today = 0
        player.total_hours_worked_today = 0
        player.work_actions_today = 0

        # ── 9. Update PlayerDailyState end snapshot + needs + housing ──────
        pds.hours_available_end = next_hours
        pds.stress_end = new_stress
        pds.health_end = new_health
        pds.cash_end = cash_after
        pds.did_settlement = True
        # Step 6 needs fields.
        pds.needs_score             = needs_result["needs_score"]
        pds.needs_tier              = needs_result["needs_tier"]
        pds.needs_evaluated         = True
        pds.food_quality_score      = needs_result["food_quality_score"]
        pds.survival_coverage_score = needs_result["survival_coverage_score"]
        # Step 7 housing fields.
        pds.housing_cost_paid = housing_amount_paid
        pds.housing_region_id = housing_region_id

        # Step 8 side-income snapshot for this settled day.
        side_income_hours = float(getattr(pds, "side_income_hours", 0) or 0)
        side_income_gross_xgp = float(getattr(pds, "side_income_gross_xgp", 0) or 0)
        side_income_fuel_cost_xgp = float(getattr(pds, "side_income_fuel_cost_xgp", 0) or 0)
        side_income_net_xgp = float(getattr(pds, "side_income_net_xgp", 0) or 0)

        # ── 10. Build summary JSON (needs + housing breakdown) ─────────────
        needs_summary = build_needs_summary(
            essentials_units, protein_units, produce_units, convenience_units,
            needs_result, needs_modifiers,
        )
        housing_summary = {
            "region_id":       housing_region_id,
            "amount_paid":     housing_amount_paid,
            "paid":            housing_paid,
            "stress_modifier": housing_stress_mod,
        }
        side_income_summary = {
            "side_income_hours": round(side_income_hours, 4),
            "side_income_gross_xgp": round(side_income_gross_xgp, 4),
            "side_income_fuel_cost_xgp": round(side_income_fuel_cost_xgp, 4),
            "side_income_net_xgp": round(side_income_net_xgp, 4),
        }
        summary_payload = {
            "worked_today":    worked_today,
            "stress_recovery": stress_recovery,
            "health_recovery": health_recovery,
            "hours_reset":     next_hours,
            "current_day":     current_day,
            "needs_summary":   needs_summary,
            "housing_summary": housing_summary,
            "side_income_summary": side_income_summary,
        }
        # ── 11. Write immutable audit log ──────────────────────────────────
        log = DailySettlementLog(
            player_id=player.id,
            day_number=current_day,
            hours_before_reset=hours_before,
            hours_after_reset=next_hours,
            stress_before=stress_before,
            stress_after=new_stress,
            health_before=health_before,
            health_after=new_health,
            cash_before=cash_before,
            cash_after=cash_after,
            recovery_applied=True,
            # Step 6 needs quality fields.
            needs_score=needs_result["needs_score"],
            needs_tier=needs_result["needs_tier"],
            food_quality_modifier=food_quality_mod,
            stress_penalty_from_needs=stress_penalty,
            health_modifier_from_needs=health_modifier,
            # Step 7 housing fields.
            housing_region_id=housing_region_id,
            housing_cost_paid=housing_amount_paid,
            housing_stress_modifier=housing_stress_mod,
            # Step 8 side-income fields.
            side_income_hours=round(side_income_hours, 4),
            side_income_net_xgp=round(side_income_net_xgp, 4),
            summary_json=json.dumps(summary_payload),
        )
        db.add(log)

        # ── 12. Atomic commit ──────────────────────────────────────────────
        # Commits in one transaction: player vitals + player.cash (housing),
        # PDS snapshot, DailySettlementLog, HousingPayment, XGPTransaction.
        db.commit()
        db.refresh(player)

        # ── 13. Return summary ─────────────────────────────────────────────
        return {
            "day_number":                current_day,
            "hours_before_reset":        hours_before,
            "hours_after_reset":         next_hours,
            "stress_before":             stress_before,
            "stress_after":              new_stress,
            "stress_recovery":           stress_recovery,
            "stress_penalty_from_needs": stress_penalty,
            "health_before":             health_before,
            "health_after":              new_health,
            "health_recovery":           health_recovery,
            "health_modifier_from_needs": health_modifier,
            "needs_score":               needs_result["needs_score"],
            "needs_tier":                needs_result["needs_tier"],
            "food_quality_modifier":     food_quality_mod,
            "cash_before":               cash_before,
            "cash_after":                cash_after,
            "did_settlement":            True,
            # Step 7 housing fields.
            "housing_region_id":       housing_region_id,
            "housing_cost_paid":       housing_amount_paid,
            "housing_paid":            housing_paid,
            "housing_stress_modifier": housing_stress_mod,
            # Step 8 side-income fields.
            "side_income_hours":         round(side_income_hours, 4),
            "side_income_gross_xgp":     round(side_income_gross_xgp, 4),
            "side_income_fuel_cost_xgp": round(side_income_fuel_cost_xgp, 4),
            "side_income_net_xgp":       round(side_income_net_xgp, 4),
        }

    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def advance_global_day(db: Session) -> GameState:
    """
    Increment the global game day by 1 and mark the new day as open.

    For MVP this is triggered manually via POST /daily/admin/advance-day.
    It does NOT auto-settle players — each player must call POST /daily/settle
    individually before or after the day advances.

    Step 5 addition:
      After incrementing the day, a MacroState row is auto-created for the new
      day using default baseline values.  This ensures the macro layer is ready
      immediately after day advance without requiring a separate admin call.

      The basket price update is NOT automatically applied here — that remains a
      separate explicit admin call (POST /macro/admin/apply-daily-basket-update)
      so that admins can adjust macro conditions first, then trigger the update.

    Future steps can wire this into a scheduled job or economy settlement loop.
    """
    state = get_or_create_game_state(db)
    state.current_day = int(state.current_day) + 1
    state.day_started_at = datetime.now(tz=timezone.utc)
    state.day_status = "open"
    db.commit()
    db.refresh(state)

    # Step 5: ensure MacroState exists for the new day.
    # Import here to avoid circular imports (macro_engine → daily_engine → loop).
    try:
        from app.engine.macro_engine import get_or_create_macro_state_for_day
        get_or_create_macro_state_for_day(db, int(state.current_day))
    except Exception:
        pass  # Non-fatal: macro state can be created fresh via /macro/state

    return state
