"""
Baskets API router — /baskets prefix.

Endpoints:
  GET  /baskets/list            — list active goods baskets with current prices
  POST /baskets/buy             — authenticated player buys basket units with XGP
  GET  /baskets/history         — recent basket purchases for authenticated player
  GET  /baskets/daily-summary   — player's basket consumption totals for current day

Economic design:
  Baskets are coarse expense categories (essentials, protein, produce, convenience)
  representing daily living costs.  XGP must leave the player's balance, not
  only enter it.  Basket spending is the first mandatory outflow and creates
  the budget pressure that makes the game feel like a real financial simulation.

  Every purchase:
    1. deducts XGP from player.cash
    2. writes an immutable XGPTransaction row (direction="out")
    3. writes an immutable BasketPurchase row (audit log)
    4. writes a ContributionEvent row (future analytics / PFT scoring)
    5. increments the player's PlayerDailyState basket unit totals

  No fake purchases, no free consumption, no negative balances.
"""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.database import get_db
from app.services.consumption_behavior_service import (
    ConsumptionError,
    ConsumptionNotFoundError,
    compute_player_daily_consumption,
    get_latest_basket_prices_for_day,
    get_player_consumption_summary,
)
from app.engine.basket_engine import (
    build_basket_purchase_summary,
    calculate_basket_total_cost,
    calculate_basket_unit_price,
    get_daily_basket_field_name,
    get_or_seed_default_baskets,
    validate_basket_purchase,
)
from app.engine.daily_engine import get_or_create_game_state, get_or_create_player_daily_state
from app.models.basket_purchase import BasketPurchase
from app.models.contribution_event import ContributionEvent
from app.models.goods_basket import GoodsBasket
from app.models.player import Player
from app.models.xgp_transaction import XGPTransaction

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────


class BasketListItem(BaseModel):
    basket_id: str
    display_name: str
    base_price: float
    price_index: float
    current_unit_price: float
    is_active: bool


class BasketBuyRequest(BaseModel):
    basket_id: str = Field(..., description="One of: essentials, protein, produce, convenience")
    quantity: float = Field(..., gt=0, le=20, description="Units to purchase (max 20 per request)")


class DailyTotals(BaseModel):
    essentials_units: float
    protein_units: float
    produce_units: float
    convenience_units: float
    total_spent_xgp: float


class BasketBuyResponse(BaseModel):
    message: str
    day_number: int
    basket_id: str
    display_name: str
    quantity: float
    unit_price: float
    total_cost: float
    balance_before: float
    balance_after: float
    daily_totals: DailyTotals


class BasketHistoryItem(BaseModel):
    basket_id: str
    quantity: float
    unit_price: float
    total_cost: float
    day_number: int
    created_at: Optional[str]


class DailyBasketSummaryResponse(BaseModel):
    day_number: int
    essentials_units: float
    protein_units: float
    produce_units: float
    convenience_units: float
    total_spent_xgp: float


class ConsumptionResponse(BaseModel):
    player_id: str
    day: int
    essentials_spend_xgp: float
    protein_spend_xgp: float
    produce_spend_xgp: float
    convenience_spend_xgp: float
    total_spend_xgp: float
    budget_pressure_score: float
    stress_spend_modifier: float
    nutrition_pressure_score: float


class BasketPriceRow(BaseModel):
    day: int
    price_index: float
    daily_change_pct: float
    supply_pressure: float
    demand_pressure: float


class LatestBasketPricesResponse(BaseModel):
    essentials: BasketPriceRow
    protein: BasketPriceRow
    produce: BasketPriceRow
    convenience: BasketPriceRow


# ─────────────────────────────────────────────────────────────────────────────
# Helper: resolve authenticated player
# ─────────────────────────────────────────────────────────────────────────────


def _get_player(db: Session, user) -> Player:
    player = db.query(Player).filter(Player.user_id == str(user.id)).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player profile not found.")
    return player


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/list",
    response_model=list[BasketListItem],
    summary="List active goods baskets with current prices",
)
def list_baskets(db: Session = Depends(get_db)):
    """
    Return all active goods baskets with their current unit prices.

    Default baskets are seeded automatically if the table is empty.
    Current unit price = base_price × (price_index / 100).

    This endpoint is public — no authentication required.
    """
    baskets = get_or_seed_default_baskets(db)
    return [
        BasketListItem(
            basket_id=b.id,
            display_name=b.display_name,
            base_price=float(b.base_price),
            price_index=float(b.price_index),
            current_unit_price=calculate_basket_unit_price(
                float(b.base_price), float(b.price_index)
            ),
            is_active=bool(b.is_active),
        )
        for b in baskets
    ]


@router.post(
    "/buy",
    response_model=BasketBuyResponse,
    summary="Buy basket units with XGP (authenticated)",
)
def buy_basket(
    request: BasketBuyRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Purchase units from a goods basket, deducting XGP from the player's balance.

    What this endpoint does (atomically):
      1. Looks up the basket and validates it is active
      2. Calculates the unit price from base_price × price_index
      3. Validates the purchase (quantity, balance, basket id)
      4. Deducts XGP from player.cash
      5. Writes an immutable BasketPurchase row
      6. Writes an XGPTransaction row (direction="out", type="basket_purchase")
      7. Writes a ContributionEvent row (type="basket_purchase")
      8. Updates PlayerDailyState basket unit totals and total_spent_xgp
      9. Commits atomically — rolls back on any failure

    Rules enforced:
      - Player must have sufficient XGP balance (no negative balances created)
      - Quantity must be > 0 and ≤ 20 per purchase
      - Basket must exist and be active
      - All writes are atomic
    """
    player = _get_player(db, current_user)

    # ── Look up basket ────────────────────────────────────────────────────────
    basket = db.query(GoodsBasket).filter(GoodsBasket.id == request.basket_id).first()
    if basket is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Basket '{request.basket_id}' not found. "
                "Call GET /baskets/list to see available baskets."
            ),
        )
    if not basket.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Basket '{request.basket_id}' is not currently available.",
        )

    # ── Pricing ───────────────────────────────────────────────────────────────
    unit_price = calculate_basket_unit_price(float(basket.base_price), float(basket.price_index))
    total_cost = calculate_basket_total_cost(unit_price, request.quantity)

    # ── Validation ────────────────────────────────────────────────────────────
    balance_now = round(float(player.cash), 4)
    valid, reason = validate_basket_purchase(
        quantity=request.quantity,
        balance=balance_now,
        total_cost=total_cost,
        basket_id=request.basket_id,
    )
    if not valid:
        raise HTTPException(status_code=400, detail=reason)

    # ── Current game day ──────────────────────────────────────────────────────
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)

    # ── Current day state ─────────────────────────────────────────────────────
    pds = get_or_create_player_daily_state(db, player, current_day)

    try:
        # ── 1. Deduct XGP ─────────────────────────────────────────────────────
        balance_before = round(float(player.cash), 4)
        player.cash = round(balance_before - total_cost, 4)
        balance_after = round(float(player.cash), 4)

        # ── 2. BasketPurchase row (immutable audit record) ─────────────────────
        purchase = BasketPurchase(
            player_id=player.id,
            basket_id=request.basket_id,
            day_number=current_day,
            quantity=request.quantity,
            unit_price=unit_price,
            total_cost=total_cost,
            balance_before=balance_before,
            balance_after=balance_after,
        )
        db.add(purchase)
        db.flush()  # give purchase.id before building the XGP tx reference

        # ── 3. XGP transaction ledger (direction="out") ───────────────────────
        xgp_tx = XGPTransaction(
            player_id=player.id,
            transaction_type="basket_purchase",
            direction="out",
            amount=round(total_cost, 4),
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="basket_purchase",
            reference_id=str(purchase.id),
            description=f"{basket.display_name} purchase",
        )
        db.add(xgp_tx)

        # ── 4. Contribution event (raw for analytics / future PFT scoring) ────
        # Basket spending is stored even if it does not directly increase rewards,
        # because aggregate demand data is needed for inflation and supply systems.
        contribution = ContributionEvent(
            player_id=player.id,
            event_type="basket_purchase",
            xgp_value=round(total_cost, 4),
            event_units=float(request.quantity),
            metadata_json=json.dumps({
                "basket_id": request.basket_id,
                "day_number": current_day,
                "unit_price": unit_price,
                "quantity": request.quantity,
            }),
        )
        db.add(contribution)

        # ── 5. Update PlayerDailyState ─────────────────────────────────────────
        # Accumulate — do not overwrite — so multiple purchases per day stack.
        daily_field = get_daily_basket_field_name(request.basket_id)
        current_units = float(getattr(pds, daily_field) or 0)
        setattr(pds, daily_field, round(current_units + float(request.quantity), 4))

        current_spent = float(getattr(pds, "total_spent_xgp", 0) or 0)
        pds.total_spent_xgp = round(current_spent + total_cost, 4)
        pds.cash_end = balance_after

        # ── 6. Atomic commit ───────────────────────────────────────────────────
        db.commit()
        db.refresh(player)
        db.refresh(pds)

    except Exception:
        db.rollback()
        raise

    return BasketBuyResponse(
        message="Basket purchase completed",
        day_number=current_day,
        basket_id=request.basket_id,
        display_name=basket.display_name,
        quantity=request.quantity,
        unit_price=unit_price,
        total_cost=total_cost,
        balance_before=balance_before,
        balance_after=balance_after,
        daily_totals=DailyTotals(
            essentials_units=float(pds.essentials_units or 0),
            protein_units=float(pds.protein_units or 0),
            produce_units=float(pds.produce_units or 0),
            convenience_units=float(pds.convenience_units or 0),
            total_spent_xgp=float(pds.total_spent_xgp or 0),
        ),
    )


@router.get(
    "/history",
    response_model=list[BasketHistoryItem],
    summary="Recent basket purchases for authenticated player",
)
def get_basket_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the most recent basket purchases for the authenticated player.

    Default: 20 entries.  Maximum: 100.  Results are newest-first (by day, then created_at).
    """
    player = _get_player(db, current_user)
    rows = (
        db.query(BasketPurchase)
        .filter(BasketPurchase.player_id == player.id)
        .order_by(BasketPurchase.day_number.desc(), BasketPurchase.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        BasketHistoryItem(
            basket_id=r.basket_id,
            quantity=float(r.quantity),
            unit_price=float(r.unit_price),
            total_cost=float(r.total_cost),
            day_number=r.day_number,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.get(
    "/daily-summary",
    response_model=DailyBasketSummaryResponse,
    summary="Authenticated player's basket consumption totals for current day",
)
def get_daily_basket_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the authenticated player's accumulated basket purchase totals for today.

    If no purchases have been made yet, all units will be 0.
    The PlayerDailyState row is created automatically if it does not yet exist.

    This data is used by:
      - The frontend to show a daily spending dashboard
      - Future recovery quality calculations (what did you eat today?)
      - Future inflation demand aggregation
    """
    player = _get_player(db, current_user)
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)

    pds = get_or_create_player_daily_state(db, player, current_day)

    return DailyBasketSummaryResponse(
        day_number=current_day,
        essentials_units=float(pds.essentials_units or 0),
        protein_units=float(pds.protein_units or 0),
        produce_units=float(pds.produce_units or 0),
        convenience_units=float(pds.convenience_units or 0),
        total_spent_xgp=float(pds.total_spent_xgp or 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Consumption behavior routes
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/player/{player_id}/consumption",
    response_model=ConsumptionResponse,
    summary="Latest computed consumption log for a player",
)
def get_player_consumption(
    player_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Return the most recently logged basket consumption for the given player.

    Returns 404 if no consumption log exists yet.
    Call POST /baskets/player/{player_id}/compute first.
    """
    try:
        data = get_player_consumption_summary(db, player_id)
        return ConsumptionResponse(**data)
    except ConsumptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConsumptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/player/{player_id}/compute",
    response_model=ConsumptionResponse,
    summary="Compute and log daily basket consumption for a player",
)
def compute_consumption(
    player_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Compute the player's daily basket consumption for the current game day.

    Idempotent — running twice for the same player/day returns the
    existing record without creating a duplicate log entry.

    Spending reacts to:
    - player cash / debt / housing pressure
    - employment status
    - stress level
    - region (downtown costs more)
    - current basket price indexes
    """
    try:
        game_state = get_or_create_game_state(db)
        current_day = int(game_state.current_day)
        data = compute_player_daily_consumption(db, player_id, current_day)
        return ConsumptionResponse(**data)
    except ConsumptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConsumptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/prices/latest",
    response_model=LatestBasketPricesResponse,
    summary="Latest basket price indexes for all 4 baskets",
)
def get_latest_basket_prices(
    db: Session = Depends(get_db),
):
    """
    Return the most recent price index for each basket type.

    Uses the current game day as the reference point.
    Falls back to built-in defaults if no price rows exist yet.
    """
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)
    prices = get_latest_basket_prices_for_day(db, current_day)
    return LatestBasketPricesResponse(
        essentials=BasketPriceRow(**prices["essentials"]),
        protein=BasketPriceRow(**prices["protein"]),
        produce=BasketPriceRow(**prices["produce"]),
        convenience=BasketPriceRow(**prices["convenience"]),
    )
