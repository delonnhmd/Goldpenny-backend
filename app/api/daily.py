"""
Daily API router — /daily prefix.

Endpoints:
  GET  /daily/state              — global game day state
  GET  /daily/player-state       — authenticated player's state for current day
  POST /daily/settle             — settle the current day (once per day)
  GET  /daily/history            — recent settlement logs for player
  POST /daily/admin/advance-day  — manual admin: advance global day by 1

Auth: all player-facing endpoints require a valid JWT.
      The admin endpoint has no separate auth in MVP — add role checks in a
      future step once an admin role system exists.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import SessionLocal
from app.engine.daily_engine import (
    advance_global_day,
    get_or_create_game_state,
    get_or_create_player_daily_state,
    run_player_end_of_day_settlement,
)
from app.engine.needs_engine import (
    build_needs_summary,
    calculate_daily_needs_score,
    calculate_needs_based_settlement_modifiers,
)
from app.models.daily_settlement_log import DailySettlementLog
from app.models.player import Player

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# DB session dependency
# ─────────────────────────────────────────────────────────────────────────────


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────


class GameStateResponse(BaseModel):
    current_day: int
    day_status: str
    day_started_at: Optional[str]

    class Config:
        from_attributes = True


class PlayerDailyStateResponse(BaseModel):
    day_number: int
    hours_available_start: int
    hours_available_end: int
    worked_main_job: bool
    did_settlement: bool
    stress_start: int
    stress_end: int
    health_start: int
    health_end: int
    cash_start: float
    cash_end: float
    # Step 6: basket totals and needs evaluation
    essentials_units: float
    protein_units: float
    produce_units: float
    convenience_units: float
    total_spent_xgp: float
    needs_score: float
    needs_tier: Optional[str]
    needs_evaluated: bool
    food_quality_score: float
    survival_coverage_score: float
    # Step 7: housing cost snapshot for today
    housing_cost_paid: float
    housing_region_id: Optional[str]
    # Step 8: side-income totals for the current day
    side_income_hours: float
    side_income_gross_xgp: float
    side_income_fuel_cost_xgp: float
    side_income_net_xgp: float


class DailySettlementResponse(BaseModel):
    message: str
    day_number: int
    hours_before_reset: int
    hours_after_reset: int
    stress_before: int
    stress_after: int
    stress_recovery: int
    # Step 6: needs-based stress modifier (positive = penalty, negative = relief)
    stress_penalty_from_needs: int
    health_before: int
    health_after: int
    health_recovery: int
    # Step 6: needs-based health modifier
    health_modifier_from_needs: int
    # Step 6: needs evaluation results
    needs_score: float
    needs_tier: str
    food_quality_modifier: int
    cash_before: float
    cash_after: float
    did_settlement: bool
    # Step 7: housing cost fields
    housing_region_id: Optional[str]
    housing_cost_paid: float
    housing_paid: bool
    housing_stress_modifier: int
    # Step 8: side-income snapshot included in settlement output
    side_income_hours: float
    side_income_gross_xgp: float
    side_income_fuel_cost_xgp: float
    side_income_net_xgp: float


class DailyHistoryItem(BaseModel):
    day_number: int
    hours_before_reset: int
    hours_after_reset: int
    stress_before: int
    stress_after: int
    health_before: int
    health_after: int
    cash_before: float
    cash_after: float
    recovery_applied: bool
    # Step 6: needs quality recorded at settlement time
    needs_score: float
    needs_tier: Optional[str]
    stress_penalty_from_needs: int
    health_modifier_from_needs: int
    food_quality_modifier: int
    # Step 7: housing fields recorded at settlement time
    housing_region_id: Optional[str]
    housing_cost_paid: float
    housing_stress_modifier: int
    # Step 8: side-income settlement snapshot
    side_income_hours: float
    side_income_gross_xgp: float
    side_income_fuel_cost_xgp: float
    side_income_net_xgp: float
    summary_json: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class NeedsPreviewResponse(BaseModel):
    """Response for GET /daily/needs-preview — read-only, no DB mutation."""
    day_number: int
    basket_units: dict
    survival_coverage_score: float
    food_quality_score: float
    needs_score: float
    needs_tier: str
    projected_stress_penalty_from_needs: int
    projected_health_modifier_from_needs: int
    projected_food_quality_modifier: int
    message: str  # human-readable hint


class AdvanceDayResponse(BaseModel):
    message: str
    current_day: int
    day_status: str
    day_started_at: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: resolve authenticated player from user
# ─────────────────────────────────────────────────────────────────────────────


def _get_player(db: Session, user) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player profile not found.")
    return player


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/state", response_model=GameStateResponse, summary="Get global game day state")
def get_game_state(db: Session = Depends(get_db)):
    """
    Return the current global in-game day and its status.

    If no GameState row exists yet, one is automatically initialized (day 1, open).
    This endpoint is public — no auth required.
    """
    state = get_or_create_game_state(db)
    started_at = None
    if state.day_started_at is not None:
        started_at = state.day_started_at.isoformat()
    elif state.real_world_timestamp is not None:
        started_at = state.real_world_timestamp.isoformat()
    return GameStateResponse(
        current_day=int(state.current_day),
        day_status=getattr(state, "day_status", "open") or "open",
        day_started_at=started_at,
    )


@router.get(
    "/player-state",
    response_model=PlayerDailyStateResponse,
    summary="Get authenticated player's daily state for current day",
)
def get_player_daily_state(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the authenticated player's daily state for the current in-game day.

    If no row exists yet for today, one is created automatically using the
    player's current vitals as the start-of-day snapshot.
    """
    player = _get_player(db, current_user)
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)

    pds = get_or_create_player_daily_state(db, player, current_day)

    return PlayerDailyStateResponse(
        day_number=pds.day_number,
        hours_available_start=int(pds.hours_available_start),
        hours_available_end=int(pds.hours_available_end),
        worked_main_job=bool(pds.worked_main_job),
        did_settlement=bool(pds.did_settlement),
        stress_start=int(pds.stress_start),
        stress_end=int(pds.stress_end),
        health_start=int(pds.health_start),
        health_end=int(pds.health_end),
        cash_start=float(pds.cash_start),
        cash_end=float(pds.cash_end),
        essentials_units=float(getattr(pds, "essentials_units", 0) or 0),
        protein_units=float(getattr(pds, "protein_units", 0) or 0),
        produce_units=float(getattr(pds, "produce_units", 0) or 0),
        convenience_units=float(getattr(pds, "convenience_units", 0) or 0),
        total_spent_xgp=float(getattr(pds, "total_spent_xgp", 0) or 0),
        needs_score=float(getattr(pds, "needs_score", 0) or 0),
        needs_tier=getattr(pds, "needs_tier", None),
        needs_evaluated=bool(getattr(pds, "needs_evaluated", False)),
        food_quality_score=float(getattr(pds, "food_quality_score", 0) or 0),
        survival_coverage_score=float(getattr(pds, "survival_coverage_score", 0) or 0),
        housing_cost_paid=float(getattr(pds, "housing_cost_paid", 0) or 0),
        housing_region_id=getattr(pds, "housing_region_id", None),
        side_income_hours=float(getattr(pds, "side_income_hours", 0) or 0),
        side_income_gross_xgp=float(getattr(pds, "side_income_gross_xgp", 0) or 0),
        side_income_fuel_cost_xgp=float(getattr(pds, "side_income_fuel_cost_xgp", 0) or 0),
        side_income_net_xgp=float(getattr(pds, "side_income_net_xgp", 0) or 0),
    )


@router.post(
    "/settle",
    response_model=DailySettlementResponse,
    summary="Settle the current in-game day (once per day)",
)
def settle_day(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Close out the player's current in-game day.

    What settlement does:
      - Calculates and applies stress recovery (partial — not full reset)
      - Adjusts health lightly based on stress level and rest hours
      - Resets hours_available to 24 for the next day
      - Creates an immutable DailySettlementLog row
      - Marks the player's PlayerDailyState as settled

    Rules enforced:
      - A player can only settle once per in-game day (idempotent).
      - Settlement applies recurring daily systems (e.g. housing) and records
        the resulting cash_before/cash_after snapshot.
      - Hours only reset through settlement, never automatically.

    Returns a full summary of changes applied.
    """
    player = _get_player(db, current_user)

    try:
        result = run_player_end_of_day_settlement(db, player)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return DailySettlementResponse(message="Daily settlement completed", **result)


@router.get(
    "/history",
    response_model=list[DailyHistoryItem],
    summary="Recent daily settlement logs for authenticated player",
)
def get_settlement_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the most recent daily settlement logs for the authenticated player.

    Default: 20 entries.  Maximum: 100.  Results are newest-first.
    """
    player = _get_player(db, current_user)
    logs = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == player.id)
        .order_by(DailySettlementLog.day_number.desc())
        .limit(limit)
        .all()
    )

    response_items: list[DailyHistoryItem] = []
    for log in logs:
        side_income_gross_xgp = 0.0
        side_income_fuel_cost_xgp = 0.0
        try:
            payload = json.loads(log.summary_json or "{}")
            side_summary = payload.get("side_income_summary") or {}
            side_income_gross_xgp = float(side_summary.get("side_income_gross_xgp", 0) or 0)
            side_income_fuel_cost_xgp = float(side_summary.get("side_income_fuel_cost_xgp", 0) or 0)
        except Exception:
            pass

        response_items.append(
            DailyHistoryItem(
                day_number=log.day_number,
                hours_before_reset=log.hours_before_reset,
                hours_after_reset=log.hours_after_reset,
                stress_before=log.stress_before,
                stress_after=log.stress_after,
                health_before=log.health_before,
                health_after=log.health_after,
                cash_before=float(log.cash_before),
                cash_after=float(log.cash_after),
                recovery_applied=bool(log.recovery_applied),
                needs_score=float(getattr(log, "needs_score", 0) or 0),
                needs_tier=getattr(log, "needs_tier", None),
                stress_penalty_from_needs=int(getattr(log, "stress_penalty_from_needs", 0) or 0),
                health_modifier_from_needs=int(getattr(log, "health_modifier_from_needs", 0) or 0),
                food_quality_modifier=int(getattr(log, "food_quality_modifier", 0) or 0),
                housing_region_id=getattr(log, "housing_region_id", None),
                housing_cost_paid=float(getattr(log, "housing_cost_paid", 0) or 0),
                housing_stress_modifier=int(getattr(log, "housing_stress_modifier", 0) or 0),
                side_income_hours=float(getattr(log, "side_income_hours", 0) or 0),
                side_income_gross_xgp=side_income_gross_xgp,
                side_income_fuel_cost_xgp=side_income_fuel_cost_xgp,
                side_income_net_xgp=float(getattr(log, "side_income_net_xgp", 0) or 0),
                summary_json=log.summary_json,
                created_at=log.created_at.isoformat() if log.created_at else None,
            )
        )

    return response_items


@router.post(
    "/admin/advance-day",
    response_model=AdvanceDayResponse,
    summary="[Admin] Advance the global game day by 1",
)
def admin_advance_day(db: Session = Depends(get_db)):
    """
    Increment the global in-game day by 1 and open the new day.

    **TEMPORARY — no admin auth yet.**
    This endpoint is internal-only for MVP.  A role-based auth guard should be
    added in a future step once an admin role system exists.

    This does NOT auto-settle any players.  Each player must call
    POST /daily/settle individually to close their own day.
    """
    state = advance_global_day(db)

    # Step 13: expire any open co-op deals whose window has passed.
    from app.engine.coop_deal_engine import expire_open_deals as _expire_deals
    _expire_deals(db, int(state.current_day))

    # Step 14: run daily NPC firm P&L, balance snapshots, distress, job openings, market share.
    from app.engine.firm_engine import run_daily_firm_cycle as _firm_cycle
    _firm_cycle(db, int(state.current_day))

    started_at = None
    if state.day_started_at is not None:
        started_at = state.day_started_at.isoformat()
    return AdvanceDayResponse(
        message=f"Global day advanced to {state.current_day}.",
        current_day=int(state.current_day),
        day_status=getattr(state, "day_status", "open") or "open",
        day_started_at=started_at,
    )


@router.get(
    "/needs-preview",
    response_model=NeedsPreviewResponse,
    summary="Preview how today's basket purchases would affect settlement",
)
def get_needs_preview(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return a needs-quality preview based on the player's basket purchases so far today.

    Read-only — does NOT mutate any DB state.  The player can call this
    endpoint any time during the day to see:
      - What needs tier they are currently on track for
      - What stress/health modifier they would receive if they settled now
      - Which baskets they are missing

    Useful for frontend feedback messages such as:
      "You need more essentials today."
      "Your food mix is weak — add protein or produce for better recovery."
      "Excellent balance! You're set for a great night."

    Basket units are read from the player's current-day PlayerDailyState.
    If no baskets have been bought yet, all scores will be 0 and tier = 'poor'.
    """
    player = _get_player(db, current_user)
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)

    pds = get_or_create_player_daily_state(db, player, current_day)

    essentials_units  = float(getattr(pds, "essentials_units",  0) or 0)
    protein_units     = float(getattr(pds, "protein_units",     0) or 0)
    produce_units     = float(getattr(pds, "produce_units",     0) or 0)
    convenience_units = float(getattr(pds, "convenience_units", 0) or 0)

    needs_result  = calculate_daily_needs_score(
        essentials_units, protein_units, produce_units, convenience_units
    )
    needs_summary = build_needs_summary(
        essentials_units, protein_units, produce_units, convenience_units,
        needs_result,
        calculate_needs_based_settlement_modifiers(
            needs_result["needs_tier"], needs_result["needs_score"]
        ),
    )
    modifiers = needs_summary  # build_needs_summary includes modifier keys

    # Build a simple human-readable hint for the frontend.
    tier = needs_result["needs_tier"]
    HINTS = {
        "poor":      "You have bought very little today. Add essentials to avoid settlement penalties.",
        "weak":      "Needs coverage is weak. Buying essentials and protein would improve recovery.",
        "adequate":  "Adequate coverage. Adding protein or produce would push you to 'good'.",
        "good":      "Good balance today! Your recovery will be slightly boosted at settlement.",
        "excellent": "Excellent food mix! You will receive maximum recovery benefit at settlement.",
    }
    hint = HINTS.get(tier, "Buy some baskets to cover your daily needs.")

    return NeedsPreviewResponse(
        day_number=current_day,
        basket_units={
            "essentials":  round(essentials_units, 4),
            "protein":     round(protein_units, 4),
            "produce":     round(produce_units, 4),
            "convenience": round(convenience_units, 4),
        },
        survival_coverage_score=needs_result["survival_coverage_score"],
        food_quality_score=needs_result["food_quality_score"],
        needs_score=needs_result["needs_score"],
        needs_tier=tier,
        projected_stress_penalty_from_needs=int(modifiers.get("stress_penalty_from_needs", 0)),
        projected_health_modifier_from_needs=int(modifiers.get("health_modifier_from_needs", 0)),
        projected_food_quality_modifier=int(modifiers.get("food_quality_modifier", 0)),
        message=hint,
    )
