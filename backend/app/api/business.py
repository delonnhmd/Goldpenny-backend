"""Business API — Step 7 (legacy) + Step 10 (small business system).

Step 7 routes (legacy, old models):
GET  /business/definitions      — Static business type catalog
GET  /business/my               — Authenticated: player's businesses
GET  /business/inventory/{id}   — Authenticated: inventory for a business
GET  /business/history          — Authenticated: action history (newest first)
POST /business/start            — Authenticated: start a new business
POST /business/buy-inventory    — Authenticated: purchase input stock
POST /business/operate          — Authenticated: run the business for the day
POST /business/upgrade          — Authenticated: advance tier
POST /business/close            — Authenticated: close a business

Step 10 routes (new small-business system):
GET  /business/types            — Available BusinessType catalog (DB-backed)
POST /business/open             — Open a new small business (deducts startup cost)
GET  /business/me               — Player's active small business status
POST /business/run              — Operate business for today (inputs → profit/loss)
GET  /business/op-history       — Business operation log, newest first
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.engine.business_engine import (
    BusinessEngine,
    calculate_business_input_cost,
    calculate_business_revenue,
    get_or_seed_business_types,
    process_business_operation,
    validate_business_operation,
)
from app.engine import business_balance_engine as _balance
from app.models.business_action import BusinessAction
from app.models.business_definition import BUSINESS_CATALOG
from app.models.business_operation import BusinessOperation
from app.models.business_type import BusinessType
from app.models.game_state import GameState
from app.models.goods_basket import GoodsBasket
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.user import User
from app.services.business_daily_operations_service import (
    BusinessNotFoundError,
    BusinessOperationsError,
    BusinessValidationError,
    create_or_get_starter_business,
    create_player_business,
    get_business_daily_history,
    get_business_profit_snapshot,
    get_player_businesses,
    get_player_business_logs,
    get_player_business_summary,
    purchase_business_upgrade,
    purchase_business_inventory,
    run_business_operations_for_player,
    run_player_businesses_for_day,
    set_business_operating_mode,
)
from app.services.daily_settlement_service import SettlementNotFoundError, get_next_player_day

router = APIRouter()
_engine = BusinessEngine()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_player_or_404(user: User, db: Session) -> Player:
    player = db.query(Player).filter(Player.user_id == user.id).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player profile not found.",
        )
    return player


def _raise_business_service_http_error(exc: Exception) -> None:
    if isinstance(exc, (BusinessNotFoundError, SettlementNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BusinessValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, BusinessOperationsError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected business service error.")


# ── Request bodies ────────────────────────────────────────────────────────────

class StartBusinessRequest(BaseModel):
    business_type: str
    business_name: str = Field(..., min_length=1, max_length=120)


class BuyInventoryRequest(BaseModel):
    business_id: str
    basket_name: str
    quantity: int = Field(..., ge=1)


class BusinessIdRequest(BaseModel):
    business_id: str


class CreateBusinessRequest(BaseModel):
    player_id: str
    business_type: str
    region: str
    tier: int = Field(1, ge=1)


# ── GET /business/definitions ─────────────────────────────────────────────────

@router.get("/definitions")
def get_definitions() -> list[dict]:
    """Return the static catalog of all available business types."""
    return [
        {
            "name": d.name,
            "display_name": d.display_name,
            "startup_cost": d.startup_cost,
            "daily_overhead": d.daily_overhead,
            "base_customer_demand": d.base_customer_demand,
            "spoilage_risk": d.spoilage_risk,
            "fuel_sensitivity": d.fuel_sensitivity,
            "labor_intensity": d.labor_intensity,
            "health_stress_impact": d.health_stress_impact,
            "required_input_baskets": d.required_input_baskets,
            "revenue_multiplier": d.revenue_multiplier,
            "max_daily_operations": d.max_daily_operations,
            "upgrade_path": d.upgrade_path,
            "time_cost_hours": d.time_cost_hours,
            "stress_change_per_op": d.stress_change_per_op,
            "health_change_per_op": d.health_change_per_op,
            "input_consumption": d.input_consumption,
            "upgrade_costs": d.upgrade_costs,
        }
        for d in BUSINESS_CATALOG.values()
    ]


# ── GET /business/my ──────────────────────────────────────────────────────────

@router.get("/my")
def get_my_businesses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return all businesses owned by the authenticated player."""
    player = _get_player_or_404(current_user, db)
    return _engine.get_player_businesses(player.id, db)


# ── GET /business/inventory/{business_id} ─────────────────────────────────────

@router.get("/inventory/{business_id}")
def get_inventory(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return inventory rows for a player-owned business."""
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.get_business_inventory(business_id, player.id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── GET /business/history ─────────────────────────────────────────────────────

@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return business action history for the authenticated player, newest first."""
    player = _get_player_or_404(current_user, db)
    rows = (
        db.query(BusinessAction)
        .filter(BusinessAction.player_id == player.id)
        .order_by(BusinessAction.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "business_id": str(r.business_id),
            "day": r.day,
            "action_type": r.action_type,
            "input_cost": float(r.input_cost),
            "overhead_cost": float(r.overhead_cost),
            "fuel_cost": float(r.fuel_cost),
            "revenue_generated": float(r.revenue_generated),
            "units_sold": r.units_sold,
            "spoiled_units": r.spoiled_units,
            "stress_change": r.stress_change,
            "health_change": r.health_change,
            "time_spent": r.time_spent,
            "net_profit": float(r.net_profit),
            "demand_factor": r.demand_factor,
            "efficiency_factor": r.efficiency_factor,
            "margin_modifier": r.margin_modifier,
            "economy_pressure": r.economy_pressure,
            "player_condition_penalty": r.player_condition_penalty,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── POST /business/start ──────────────────────────────────────────────────────

@router.post("/start")
def start_business(
    body: StartBusinessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Start a new business. Deducts startup cost from player cash."""
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.start_business(player, body.business_type, body.business_name, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── POST /business/buy-inventory ──────────────────────────────────────────────

@router.post("/buy-inventory")
def buy_inventory(
    body: BuyInventoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Purchase input inventory for a business. Deducts from player cash."""
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.buy_business_inventory(
            player, body.business_id, body.basket_name, body.quantity, db
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── POST /business/operate ────────────────────────────────────────────────────

@router.post("/operate")
def operate_business(
    body: BusinessIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Run the business for today. Consumes inventory, generates revenue, affects player stats."""
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.operate_business(player, body.business_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── POST /business/upgrade ────────────────────────────────────────────────────

@router.post("/upgrade")
def upgrade_business(
    body: BusinessIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Upgrade the business to the next tier. Deducts upgrade cost from player cash."""
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.upgrade_business(player, body.business_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── POST /business/close ──────────────────────────────────────────────────────

@router.post("/close")
def close_business(
    body: BusinessIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Permanently close a business."""
    player = _get_player_or_404(current_user, db)
    try:
        return _engine.close_business(player, body.business_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 10 — Small Business System Routes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class OpenBusinessRequest(BaseModel):
    business_id: str   # "fruit_shop" | "food_truck"


# ── GET /business/types ───────────────────────────────────────────────────────

@router.get("/types")
def get_business_types(db: Session = Depends(get_db)) -> dict:
    """Return all active BusinessType definitions from the DB.

    Includes live basket input cost estimates so the frontend can show
    what each business costs to run per day under current market conditions.
    """
    types = get_or_seed_business_types(db)
    items = []
    for bt in types:
        live_cost = calculate_business_input_cost(db, bt)
        items.append({
            "business_id":            bt.business_id,
            "display_name":           bt.display_name,
            "input_produce_units":    bt.input_produce_units,
            "input_essentials_units": bt.input_essentials_units,
            "input_protein_units":    bt.input_protein_units,
            "base_revenue":           float(bt.base_revenue),
            "hours_required":         bt.hours_required,
            "stress_change":          bt.stress_change,
            "startup_cost":           float(bt.startup_cost),
            "estimated_input_cost":   live_cost,
        })
    return {"count": len(items), "business_types": items}


# ── POST /business/open ───────────────────────────────────────────────────────

@router.post("/open")
def open_business(
    body: OpenBusinessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Start a new small business.

    Deducts startup_cost from player cash and creates a PlayerBusiness record.

    Rules:
      - Player must not already have an active PlayerBusiness (one per player).
      - Player must have enough cash to cover startup_cost.
      - Creates an XGPTransaction for the startup payment.
    """
    from app.engine.macro_engine import get_or_create_macro_state_for_day
    from app.models.xgp_transaction import XGPTransaction
    import json as _json

    player = _get_player_or_404(current_user, db)

    # Check business type exists
    btype = (
        db.query(BusinessType)
        .filter(BusinessType.business_id == body.business_id, BusinessType.is_active.is_(True))
        .first()
    )
    if btype is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business type '{body.business_id}' not found or inactive.",
        )

    # One business per player guard
    existing = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already own an active business ({existing.business_id}). Close it before opening another.",
        )

    startup_cost = float(btype.startup_cost)
    balance_before = round(float(player.cash), 4)
    if balance_before < startup_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not enough cash. Startup costs {startup_cost:.2f} XGP, you have {balance_before:.2f} XGP.",
        )

    # Get current game day
    state = db.query(GameState).order_by(GameState.id.asc()).first()
    current_day = int(state.current_day) if state else 0

    balance_after = round(balance_before - startup_cost, 4)
    player.cash = balance_after

    pb = PlayerBusiness(
        player_id=player.id,
        business_id=body.business_id,
        business_level=1,
        created_day=current_day,
        is_active=True,
    )
    db.add(pb)
    db.flush()

    # XGPTransaction for startup cost
    xgp_tx = XGPTransaction(
        player_id=player.id,
        transaction_type="business_startup",
        direction="out",
        amount=startup_cost,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type="player_business",
        reference_id=str(pb.id),
        description=f"Business startup — {btype.display_name} on day {current_day}",
    )
    db.add(xgp_tx)

    db.commit()

    return {
        "message": f"Business '{btype.display_name}' opened successfully.",
        "business_id":    body.business_id,
        "display_name":   btype.display_name,
        "startup_cost":   startup_cost,
        "balance_before": balance_before,
        "balance_after":  balance_after,
        "created_day":    current_day,
    }


# ── GET /business/me ──────────────────────────────────────────────────────────

@router.get("/me")
def get_my_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's active small business, if any.

    Also returns live input cost estimate and the current macro revenue estimate
    so the player can make an informed decision about whether to operate today.
    """
    from app.engine.macro_engine import get_or_create_macro_state_for_day

    player = _get_player_or_404(current_user, db)

    pb = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
        .first()
    )
    if pb is None:
        return {"has_business": False, "business": None}

    btype = (
        db.query(BusinessType)
        .filter(BusinessType.business_id == pb.business_id)
        .first()
    )

    state = db.query(GameState).order_by(GameState.id.asc()).first()
    current_day = int(state.current_day) if state else 0
    macro = get_or_create_macro_state_for_day(db, current_day)

    live_input_cost = calculate_business_input_cost(db, btype) if btype else 0.0
    # Step 11 — build estimated balancing values for the UI
    fixed_overhead  = _balance.calculate_fixed_overhead(btype) if btype else 0.0
    times_today     = int(pb.times_operated_today or 0)
    if pb.last_operated_day != current_day:
        times_today = 0   # would reset on next run
    demand_mult     = _balance.calculate_demand_multiplier(
        btype,
        consumer_confidence=float(macro.consumer_confidence),
        unemployment=float(macro.unemployment),
    ) if btype else 1.0
    sat_mult        = _balance.calculate_saturation_penalty_multiplier(
        btype, times_operated_today=times_today,
    ) if btype else 1.0
    macro_mod       = _balance.calculate_macro_margin_modifier(
        btype,
        oil_index=float(macro.oil_index),
        inflation=float(macro.inflation),
        input_cost_xgp=live_input_cost,
        base_revenue_xgp=float(btype.base_revenue) if btype else 0.0,
    ) if btype else 0.0
    final_mult      = _balance.calculate_final_margin_multiplier(
        demand_mult, sat_mult, macro_mod,
    ) if btype else 1.0
    est_revenue     = round(float(btype.base_revenue) * final_mult, 4) if btype else 0.0
    est_profit      = round(est_revenue - live_input_cost - fixed_overhead, 4)

    return {
        "has_business": True,
        "business": {
            "business_id":          pb.business_id,
            "display_name":         btype.display_name if btype else pb.business_id,
            "business_level":       pb.business_level,
            "created_day":          pb.created_day,
            "last_operated_day":    pb.last_operated_day,
            "operated_today":       pb.last_operated_day == current_day,
            "times_operated_today": int(pb.times_operated_today or 0),
            "lifetime_business_runs": int(pb.lifetime_business_runs or 0),
            "is_active":            pb.is_active,
            "hours_required":       btype.hours_required if btype else None,
            "stress_change":        btype.stress_change if btype else None,
            # Live cost / revenue estimates including Step 11 balancing
            "estimated_input_cost":                live_input_cost,
            "estimated_fixed_overhead":            fixed_overhead,
            "estimated_demand_multiplier":         demand_mult,
            "estimated_saturation_penalty":        sat_mult,
            "estimated_macro_margin_modifier":     macro_mod,
            "estimated_final_margin_multiplier":   final_mult,
            "estimated_revenue":                   est_revenue,
            "estimated_profit":                    est_profit,
        },
    }


# ── POST /business/run ────────────────────────────────────────────────────────

@router.post("/run")
def run_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Operate the player's small business for today.

    Consumes basket inputs at live market prices, generates macro-adjusted
    revenue, and records the full operation in the audit log.

    Returns profit/loss, input cost, revenue, hours used, and cash balance.
    Raises 400 if: no active business, already operated today, not enough
    hours, or not enough cash for inputs.
    """
    player = _get_player_or_404(current_user, db)

    pb = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
        .first()
    )
    if pb is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You don't have an active business. Use POST /business/open to start one.",
        )

    btype = (
        db.query(BusinessType)
        .filter(BusinessType.business_id == pb.business_id, BusinessType.is_active.is_(True))
        .first()
    )
    if btype is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Business type '{pb.business_id}' is no longer active.",
        )

    try:
        result = process_business_operation(db=db, player=player, player_business=pb, business_type=btype)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"message": "Business operation completed.", **result}


# ── GET /business/op-history ──────────────────────────────────────────────────

@router.get("/op-history")
def get_operation_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the authenticated player's BusinessOperation log, newest first."""
    player = _get_player_or_404(current_user, db)

    ops = (
        db.query(BusinessOperation)
        .filter(BusinessOperation.player_id == player.id)
        .order_by(BusinessOperation.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "count": len(ops),
        "operations": [
            {
                "id":                            str(op.id),
                "business_id":                   op.business_id,
                "day_number":                    op.day_number,
                "hours_used":                    op.hours_used,
                "produce_units":                 op.produce_units,
                "essentials_units":              op.essentials_units,
                "protein_units":                 op.protein_units,
                "input_cost_xgp":               float(op.input_cost_xgp),
                "fixed_overhead_xgp":           float(op.fixed_overhead_xgp),
                "revenue_xgp":                  float(op.revenue_xgp),
                "profit_xgp":                   float(op.profit_xgp),
                "demand_multiplier":            float(op.demand_multiplier),
                "saturation_penalty_multiplier": float(op.saturation_penalty_multiplier),
                "macro_margin_modifier":         float(op.macro_margin_modifier),
                "final_margin_multiplier":       float(op.final_margin_multiplier),
                "stress_change":                op.stress_change,
                "balance_before":               float(op.balance_before),
                "balance_after":                float(op.balance_after),
                "created_at":                   op.created_at.isoformat() if op.created_at else None,
            }
            for op in ops
        ],
    }


# ── GET /business/preview-run ────────────────────────────────────────────────────

@router.get("/preview-run")
def preview_business_run(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Preview current-day business profitability WITHOUT mutating the database.

    Shows the player exactly what running their business right now would produce:
      - estimated input cost at live basket prices
      - fixed overhead
      - demand multiplier (macro demand conditions)
      - saturation penalty (based on how many times run today already)
      - macro margin modifier (oil, inflation, input pressure)
      - final margin multiplier (combined)
      - estimated adjusted revenue
      - estimated profit (may be negative)

    Frontend use-cases:
      • "Running again today is less profitable" (saturation_penalty < 1.0)
      • "Oil pressure is hurting food truck margin" (macro_margin_modifier < 0)
      • Show live estimate before committing to the run

    Raises 400 if player has no active business.
    Does NOT write anything to the database.
    """
    from app.engine.macro_engine import get_or_create_macro_state_for_day

    player = _get_player_or_404(current_user, db)

    pb = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
        .first()
    )
    if pb is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You don't have an active business. Use POST /business/open to start one.",
        )

    btype = (
        db.query(BusinessType)
        .filter(BusinessType.business_id == pb.business_id, BusinessType.is_active.is_(True))
        .first()
    )
    if btype is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Business type '{pb.business_id}' is no longer active.",
        )

    state = db.query(GameState).order_by(GameState.id.asc()).first()
    current_day = int(state.current_day) if state else 0
    macro = get_or_create_macro_state_for_day(db, current_day)

    live_input_cost = calculate_business_input_cost(db, btype)
    base_revenue    = float(btype.base_revenue)

    # Times already operated today (reset-aware)
    times_today = int(pb.times_operated_today or 0)
    if pb.last_operated_day != current_day:
        times_today = 0  # counter would reset at next actual run

    fixed_overhead = _balance.calculate_fixed_overhead(btype)
    demand_mult    = _balance.calculate_demand_multiplier(
        btype,
        consumer_confidence=float(macro.consumer_confidence),
        unemployment=float(macro.unemployment),
    )
    sat_mult       = _balance.calculate_saturation_penalty_multiplier(
        btype, times_operated_today=times_today,
    )
    macro_mod      = _balance.calculate_macro_margin_modifier(
        btype,
        oil_index=float(macro.oil_index),
        inflation=float(macro.inflation),
        input_cost_xgp=live_input_cost,
        base_revenue_xgp=base_revenue,
    )
    final_mult     = _balance.calculate_final_margin_multiplier(demand_mult, sat_mult, macro_mod)
    est_revenue    = round(base_revenue * final_mult, 4)
    est_profit     = round(est_revenue - live_input_cost - fixed_overhead, 4)

    # Readable explanation hints for the frontend
    hints = []
    if times_today > 0:
        hints.append(
            f"Running again today ({times_today} run(s) already): "
            f"saturation penalty = {sat_mult:.2f}x"
        )
    if macro_mod < -0.05:
        hints.append(
            f"Macro pressure compressing margin by {abs(macro_mod):.2f} "
            f"(oil={float(macro.oil_index):.1f}, inflation={float(macro.inflation):.1f}%)"
        )
    if est_profit < 0:
        hints.append("Estimated profit is negative — this run would be a loss.")

    return {
        "business_id":                   btype.business_id,
        "display_name":                  btype.display_name,
        "day_number":                    current_day,
        "times_operated_today":          times_today,
        "input_cost_xgp":               live_input_cost,
        "fixed_overhead_xgp":           fixed_overhead,
        "demand_multiplier":            demand_mult,
        "saturation_penalty_multiplier": sat_mult,
        "macro_margin_modifier":         macro_mod,
        "final_margin_multiplier":       final_mult,
        "estimated_revenue_xgp":        est_revenue,
        "estimated_profit_xgp":         est_profit,
        "hints":                         hints,
    }


# Step 15: Business Daily Operations MVP routes


@router.post("/create")
def create_business(body: CreateBusinessRequest, db: Session = Depends(get_db)) -> dict:
    """Create a player business for MVP daily operations."""
    try:
        return create_player_business(
            db=db,
            player_id=body.player_id,
            business_type=body.business_type,
            region=body.region,
            tier=body.tier,
        )
    except Exception as exc:
        _raise_business_service_http_error(exc)


@router.get("/player/{player_id}")
def get_player_businesses_for_day_ops(player_id: str, db: Session = Depends(get_db)) -> dict:
    """Return all businesses owned by a player with latest summary values."""
    try:
        businesses = get_player_businesses(db, player_id)
        snapshot = get_business_profit_snapshot(db, player_id)
        return {
            "player_id": str(player_id),
            "businesses": businesses,
            "profit_snapshot": snapshot,
            "starter_options": [
                {
                    "business_type": key,
                    "label": definition.display_name,
                    "cost_xgp": float(definition.startup_cost),
                }
                for key, definition in (
                    ("fruit_shop", BUSINESS_CATALOG["fruit_shop"]),
                    ("food_truck", BUSINESS_CATALOG["food_truck"]),
                )
            ],
        }
    except Exception as exc:
        _raise_business_service_http_error(exc)


@router.post("/run/{player_id}")
def run_player_businesses_route(player_id: str, db: Session = Depends(get_db)) -> dict:
    """Run current unsettled-day business operations for a player."""
    try:
        day = get_next_player_day(db, player_id)
        return run_player_businesses_for_day(db=db, player_id=player_id, day=day, commit=True)
    except Exception as exc:
        _raise_business_service_http_error(exc)


@router.get("/logs/{player_id}")
def get_business_logs_route(
    player_id: str,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """Return latest business daily logs for a player's businesses."""
    try:
        return get_player_business_logs(db=db, player_id=player_id, limit=limit)
    except Exception as exc:
        _raise_business_service_http_error(exc)


class StarterBusinessCreateRequest(BaseModel):
    business_type: str = Field(..., description="fruit_shop or food_truck")
    business_name: str | None = Field(default=None, max_length=120)
    region_key: str | None = Field(default=None, description="suburban | downtown | rural")
    level_key: str = Field(default="starter")


class BusinessInventoryPurchaseRequest(BaseModel):
    business_id: str
    produce_units: float = Field(default=0.0, ge=0.0)
    essentials_units: float = Field(default=0.0, ge=0.0)
    protein_units: float = Field(default=0.0, ge=0.0)
    as_of_date: date | None = None


class BusinessOperateRequest(BaseModel):
    as_of_date: date | None = None


class BusinessModeUpdateRequest(BaseModel):
    business_id: str
    mode_key: str


class BusinessUpgradeRequest(BaseModel):
    business_id: str
    upgrade_key: str


class BusinessModeUpdateResponse(BaseModel):
    player_id: str
    business_id: str
    business_type: str
    old_mode: str
    new_mode: str
    expected_tradeoffs: dict = Field(default_factory=dict)
    debug_meta: dict = Field(default_factory=dict)


class BusinessUpgradeResponse(BaseModel):
    player_id: str
    business_id: str
    upgrade_key: str
    cost_xgp: float
    applied: bool
    expected_effects: dict = Field(default_factory=dict)
    debug_meta: dict = Field(default_factory=dict)


@router.post("/player/{player_id}/starter/create")
def create_starter_business_for_player(
    player_id: str,
    body: StarterBusinessCreateRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create or return a starter business for a player."""
    try:
        payload = create_or_get_starter_business(
            db=db,
            player_id=player_id,
            business_type=body.business_type,
            business_name=body.business_name,
            region_key=body.region_key,
            level_key=body.level_key,
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        _raise_business_service_http_error(exc)


@router.post("/player/{player_id}/inventory/purchase")
def purchase_business_inventory_for_player(
    player_id: str,
    body: BusinessInventoryPurchaseRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Purchase business inventory with cash validation."""
    try:
        payload = purchase_business_inventory(
            db=db,
            player_id=player_id,
            business_id=body.business_id,
            produce_units=body.produce_units,
            essentials_units=body.essentials_units,
            protein_units=body.protein_units,
            as_of_date=body.as_of_date,
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        _raise_business_service_http_error(exc)


@router.post("/player/{player_id}/operate")
def operate_businesses_for_player(
    player_id: str,
    body: BusinessOperateRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Operate all active businesses for a player for the target day."""
    try:
        payload = run_business_operations_for_player(
            db=db,
            player_id=player_id,
            as_of_date=(body.as_of_date if body is not None else None),
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        _raise_business_service_http_error(exc)


@router.post("/player/{player_id}/mode", response_model=BusinessModeUpdateResponse)
def update_business_mode_for_player(
    player_id: str,
    body: BusinessModeUpdateRequest,
    db: Session = Depends(get_db),
) -> BusinessModeUpdateResponse:
    """Update operating mode for a player-owned business."""
    try:
        payload = set_business_operating_mode(
            db=db,
            player_id=player_id,
            business_id=body.business_id,
            mode_key=body.mode_key,
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        _raise_business_service_http_error(exc)


@router.post("/player/{player_id}/upgrade", response_model=BusinessUpgradeResponse)
def purchase_business_upgrade_for_player(
    player_id: str,
    body: BusinessUpgradeRequest,
    db: Session = Depends(get_db),
) -> BusinessUpgradeResponse:
    """Purchase a bounded mini-upgrade for a player-owned business."""
    try:
        payload = purchase_business_upgrade(
            db=db,
            player_id=player_id,
            business_id=body.business_id,
            upgrade_key=body.upgrade_key,
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        _raise_business_service_http_error(exc)


@router.get("/player/{player_id}/history")
def get_business_history_for_player(
    player_id: str,
    limit: int = Query(30, ge=1, le=200),
    business_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Get recent business daily operation history for player."""
    try:
        return get_business_daily_history(
            db=db,
            player_id=player_id,
            business_id=business_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_business_service_http_error(exc)


@router.get("/player/{player_id}/profit-snapshot")
def get_business_profit_snapshot_for_player(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Get compact business profit/value snapshot for player."""
    try:
        return get_business_profit_snapshot(
            db=db,
            player_id=player_id,
            as_of_date=as_of_date,
        )
    except Exception as exc:
        _raise_business_service_http_error(exc)

