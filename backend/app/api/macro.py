"""
Macro API router — /macro prefix.

Endpoints:
  GET  /macro/state                          — current macro state for today's game day
  POST /macro/admin/state                    — create/update macro state for a specific day
  POST /macro/admin/apply-daily-basket-update — apply basket price update for a day
  GET  /macro/basket-history                 — basket price index change history
  GET  /macro/current-basket-prices          — all active baskets with current prices + sensitivities

Economic intent:
  Macro state is global — one shared world economy.
  Basket prices are the first visible output of the economy engine.
  Daily capped movement prevents unrealistic chaos.
  Different baskets react differently to the same macro conditions.
  This router exposes the first true inflation layer of the game.

Auth:
  All /admin/* endpoints are unprotected in MVP (no admin role system yet).
  Public endpoints require no auth so the frontend can always read price state.

Sample flow documented here for reference:
  Day 6:
    1. Admin calls POST /daily/admin/advance-day → day becomes 6
    2. MacroState for day 6 is auto-created with defaults
    3. Admin calls POST /macro/admin/state with {day_number:6, oil_index:120, supply_chain_stress:30}
    4. Admin calls POST /macro/admin/apply-daily-basket-update with {day_number:6}
    5. Produce and protein baskets rise more than essentials due to higher sensitivities
    6. Players now pay more XGP to buy those baskets
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.engine.daily_engine import get_or_create_game_state
from app.engine.macro_engine import (
    apply_daily_basket_price_update,
    get_or_create_macro_state_for_day,
    serialize_basket_price_history,
    serialize_macro_state,
)
from app.models.basket_price_history import BasketPriceHistory
from app.models.goods_basket import GoodsBasket
from app.models.macro_state import MacroState

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


class MacroStateResponse(BaseModel):
    """API response shape for a single MacroState row."""

    id: int
    day_number: int
    inflation: float
    interest_rate: float
    unemployment: float
    oil_index: float
    consumer_confidence: float
    supply_chain_stress: float
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class AdminMacroUpdateRequest(BaseModel):
    """Request body for POST /macro/admin/state.

    All macro fields are optional — only provided fields are updated.
    Validation ranges are economic sanity guards to prevent absurd inputs
    that would break the deterministic price formula.
    """

    day_number: int = Field(..., ge=1, description="In-game day number to set macro state for")

    inflation: Optional[float] = Field(
        None,
        ge=-10.0,
        le=20.0,
        description="Annual inflation rate %. Normal: 2.0. Can be negative (deflation).",
    )
    interest_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=25.0,
        description="Central bank interest rate %. Normal: 4.0.",
    )
    unemployment: Optional[float] = Field(
        None,
        ge=0.0,
        le=50.0,
        description="Unemployment rate %. Normal: 5.0.",
    )
    oil_index: Optional[float] = Field(
        None,
        gt=0.0,
        description="Oil/energy price index. Baseline: 100.0. Must be positive.",
    )
    consumer_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Consumer confidence index. 0=panic, 50=neutral, 100=euphoric.",
    )
    supply_chain_stress: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Supply chain disruption score. 0=none, 100=severe.",
    )


class BasketUpdateRequest(BaseModel):
    """Request body for POST /macro/admin/apply-daily-basket-update."""

    day_number: int = Field(..., ge=1, description="In-game day number to apply basket update for")


class BasketPriceHistoryItem(BaseModel):
    """API response shape for a single BasketPriceHistory row."""

    id: str
    basket_id: str
    day_number: int
    old_price_index: float
    new_price_index: float
    change_percent: float
    change_percent_display: float  # e.g. 1.25 means +1.25%
    inflation_used: float
    oil_index_used: float
    consumer_confidence_used: float
    supply_chain_stress_used: float
    notes: Optional[str]
    created_at: Optional[str]


class CurrentBasketPriceItem(BaseModel):
    """API response shape for GET /macro/current-basket-prices."""

    basket_id: str
    display_name: str
    base_price: float
    price_index: float
    current_unit_price: float
    # Sensitivity metadata — useful for frontier/beta features display
    inflation_sensitivity: float
    oil_sensitivity: float
    confidence_sensitivity: float
    supply_chain_sensitivity: float
    seasonality_factor: float


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/state",
    response_model=MacroStateResponse,
    summary="Get macro state for the current global game day",
)
def get_macro_state(db: Session = Depends(get_db)):
    """
    Return the macroeconomic state for the current in-game day.

    If no MacroState row exists yet for today, one is auto-created with
    default values (stable baseline economy).

    This endpoint is public — no auth required.  All players see the same
    global macro state.
    """
    game_state = get_or_create_game_state(db)
    current_day = int(game_state.current_day)
    macro = get_or_create_macro_state_for_day(db, current_day)
    return MacroStateResponse(**serialize_macro_state(macro))


@router.post(
    "/admin/state",
    response_model=MacroStateResponse,
    summary="[Admin] Create or update macro state for a specific day",
)
def admin_set_macro_state(
    body: AdminMacroUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Create or update the macro state for a specific in-game day.

    **TEMPORARY — no admin auth yet.**  This endpoint is internal-only for MVP.

    If a MacroState row already exists for the requested day, it is updated
    in place.  If not, a new row is created starting from defaults.

    Only fields included in the request body are applied; unspecified fields
    retain their current (or default) values.

    Use this endpoint to test economy conditions before an event engine exists.
    Example: raise oil_index before applying basket update to simulate an oil shock.
    """
    macro = get_or_create_macro_state_for_day(db, body.day_number)

    # Apply only the fields that were explicitly provided.
    if body.inflation is not None:
        macro.inflation = body.inflation
    if body.interest_rate is not None:
        macro.interest_rate = body.interest_rate
    if body.unemployment is not None:
        macro.unemployment = body.unemployment
    if body.oil_index is not None:
        macro.oil_index = body.oil_index
    if body.consumer_confidence is not None:
        macro.consumer_confidence = body.consumer_confidence
    if body.supply_chain_stress is not None:
        macro.supply_chain_stress = body.supply_chain_stress

    db.commit()
    db.refresh(macro)
    return MacroStateResponse(**serialize_macro_state(macro))


@router.post(
    "/admin/apply-daily-basket-update",
    response_model=list[BasketPriceHistoryItem],
    summary="[Admin] Apply basket price index update for a specific day",
)
def admin_apply_basket_update(
    body: BasketUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Apply the daily basket price update for the given in-game day.

    **TEMPORARY — no admin auth yet.**

    What this does:
      1. Loads the MacroState for the specified day (auto-creates if missing).
      2. For each active GoodsBasket, calculates the daily price change using
         that basket's macro sensitivity weights.
      3. Updates basket.price_index (change capped at ±5%).
      4. Creates a BasketPriceHistory audit row per basket.
      5. Commits atomically.

    Idempotent: if called a second time for the same day, baskets that already
    have a history row are skipped.  The existing rows are returned unchanged.
    This prevents the price change from compounding on repeated calls.

    Different baskets react differently to the same macro conditions:
      - Produce and protein are more volatile (higher oil + supply sensitivity).
      - Essentials are more stable.
      - Convenience is labor and inflation sensitive.
    """
    try:
        history_rows = apply_daily_basket_price_update(db, body.day_number)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return [BasketPriceHistoryItem(**serialize_basket_price_history(row)) for row in history_rows]


@router.get(
    "/basket-history",
    response_model=list[BasketPriceHistoryItem],
    summary="Get basket price index change history",
)
def get_basket_history(
    basket_id: Optional[str] = Query(None, description="Filter by basket ID (e.g. 'produce')"),
    day_number: Optional[int] = Query(None, description="Filter by exact in-game day"),
    limit: int = Query(default=50, ge=1, le=500, description="Maximum rows to return"),
    db: Session = Depends(get_db),
):
    """
    Return basket price history rows, newest first.

    Optional filters:
      - basket_id: return only rows for the specified basket
      - day_number: return only rows for the specified in-game day

    Maximum 500 rows per request.  Use for frontend charting and economic debugging.
    """
    query = db.query(BasketPriceHistory)

    if basket_id is not None:
        query = query.filter(BasketPriceHistory.basket_id == basket_id)
    if day_number is not None:
        query = query.filter(BasketPriceHistory.day_number == day_number)

    rows = query.order_by(BasketPriceHistory.day_number.desc()).limit(limit).all()
    return [BasketPriceHistoryItem(**serialize_basket_price_history(row)) for row in rows]


@router.get(
    "/current-basket-prices",
    response_model=list[CurrentBasketPriceItem],
    summary="Get all active baskets with current prices and macro sensitivity info",
)
def get_current_basket_prices(db: Session = Depends(get_db)):
    """
    Return all active GoodsBaskets with their current price state and
    macro sensitivity metadata.

    current_unit_price = base_price × (price_index / 100).

    This endpoint is macro-facing and exposes richer economic detail than
    /baskets/list.  Use it to show players how the economy is affecting their
    cost of living and which categories are under the most pressure.

    This endpoint is public — no auth required.
    """
    baskets = (
        db.query(GoodsBasket)
        .filter(GoodsBasket.is_active.is_(True))
        .order_by(GoodsBasket.id)
        .all()
    )

    result = []
    for basket in baskets:
        base_price = float(basket.base_price)
        price_index = float(basket.price_index)
        current_unit_price = round(base_price * (price_index / 100.0), 2)

        result.append(
            CurrentBasketPriceItem(
                basket_id=basket.id,
                display_name=basket.display_name,
                base_price=base_price,
                price_index=price_index,
                current_unit_price=current_unit_price,
                inflation_sensitivity=float(basket.inflation_sensitivity),
                oil_sensitivity=float(basket.oil_sensitivity),
                confidence_sensitivity=float(basket.confidence_sensitivity),
                supply_chain_sensitivity=float(basket.supply_chain_sensitivity),
                seasonality_factor=float(basket.seasonality_factor),
            )
        )

    return result
