"""
Macro Engine — deterministic global price movement logic for Step 5.

Design principles:
  - All calculation functions are pure and stateless.  Same inputs → same outputs.
  - NO randomness anywhere in this file.  Price movement is deterministic so that
    admins can reproduce results and players cannot exploit timing.
  - DB-facing functions accept a Session and commit atomically.
  - No FastAPI imports.

Economic model:
  MacroState → per-basket sensitivity weights → daily % change (capped ±5%)
  → updated GoodsBasket.price_index → player purchase costs change.

  This is the first true inflation layer of the Gold Penny game.
  Macro state is global — one shared world economy.  All players see the same
  basket price indexes.  Basket prices move once per day maximum.

  Example flow (Day 6):
    1. Admin advances global day to 6.
    2. MacroState for day 6 is auto-created with defaults.
    3. Admin sets oil_index=120, supply_chain_stress=30.
    4. Admin calls POST /macro/admin/apply-daily-basket-update.
    5. Produce and protein baskets rise more than essentials.
    6. Players now pay more XGP to buy those baskets.
"""

from __future__ import annotations

import math
from typing import Optional

from sqlalchemy.orm import Session

from app.models.basket_price_history import BasketPriceHistory
from app.models.goods_basket import GoodsBasket
from app.models.macro_state import MacroState

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Daily basket price movement is hard-capped to prevent unrealistic chaos.
MAX_DAILY_CHANGE: float = 0.05   # +5%
MIN_DAILY_CHANGE: float = -0.05  # -5%

# Macro variable baselines — movement is measured relative to these.
INFLATION_BASELINE: float = 2.0    # 2% is considered neutral inflation
OIL_BASELINE: float = 100.0        # 100 is the "normal" oil index
CONFIDENCE_MIDPOINT: float = 50.0  # 50 = neutral consumer confidence

# Minimum price index floor — a basket price index cannot fall below this.
MIN_PRICE_INDEX: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# DB-facing helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_or_create_macro_state_for_day(db: Session, day_number: int) -> MacroState:
    """
    Fetch the active MacroState row for *day_number*, creating one with safe
    defaults if none exists.

    MVP rule: one active row per day is sufficient.  If multiple rows somehow
    exist for the same day, the most recently created one is used.

    Default macro values represent a stable baseline economy:
      inflation=2.0, interest_rate=4.0, unemployment=5.0,
      oil_index=100.0, consumer_confidence=50.0, supply_chain_stress=0.0
    """
    macro = (
        db.query(MacroState)
        .filter(MacroState.day_number == day_number, MacroState.is_active.is_(True))
        .order_by(MacroState.id.desc())
        .first()
    )
    if macro is None:
        macro = MacroState(
            day_number=day_number,
            inflation=2.0,
            interest_rate=4.0,
            unemployment=5.0,
            oil_index=100.0,
            consumer_confidence=50.0,
            supply_chain_stress=0.0,
            is_active=True,
        )
        db.add(macro)
        db.commit()
        db.refresh(macro)
    return macro


# ─────────────────────────────────────────────────────────────────────────────
# Pure calculation functions (stateless, no DB access)
# ─────────────────────────────────────────────────────────────────────────────


def calculate_seasonality_adjustment(
    day_number: int,
    seasonality_factor: float,
    basket_id: str,
) -> float:
    """
    Return a small deterministic seasonal price component for *basket_id*.

    Uses a 30-day sine cycle to approximate monthly supply variation.
    The produce basket (seasonality_factor=0.5) shows the strongest seasonal
    swings; convenience (0.05) is almost flat.

    Formula:
        adjustment = sin(2π × day_number / 30) × 0.04 × seasonality_factor

    The constant 0.04 keeps the seasonal peak well within the ±5% daily cap
    even for produce, while adding a perceptible rhythm over weeks of play.

    All inputs are deterministic — no randomness, no external state.
    """
    # 30-day cycle: one full wave per in-game month.
    cycle_radians = 2.0 * math.pi * day_number / 30.0
    raw_seasonal = math.sin(cycle_radians) * 0.04 * float(seasonality_factor)
    return raw_seasonal


def calculate_basket_daily_change_percent(
    basket: GoodsBasket,
    macro: MacroState,
    day_number: int,
) -> float:
    """
    Calculate how much this basket's price index should change today, expressed
    as a decimal fraction.

    This is a simplified macro price engine.  The formula combines four weighted
    macro components plus a seasonal adjustment, then hard-clamps the result to
    the ±5% daily cap.

    Component breakdown
    -------------------
    inflation_component:
        Deviation of inflation from the 2% baseline, scaled by the basket's
        inflation sensitivity.  Higher inflation relative to baseline raises
        all basket prices; deflation lowers them.

    oil_component:
        Deviation of the oil index from 100 (baseline), scaled by the basket's
        oil sensitivity.  Oil affects transport and refrigeration costs most
        strongly for produce and protein baskets.

    confidence_component:
        When consumer confidence drops below 50, prices tend to rise slightly
        (precautionary buying, hoarding, reduced efficiency).  Higher confidence
        exerts mild downward pressure.  Scaled by the basket's confidence
        sensitivity.

    supply_chain_component:
        Pure positive pressure: any non-zero supply chain stress raises prices.
        Produce and protein are most sensitive because of perishability and
        distribution complexity.

    seasonality_component:
        A deterministic sine-wave adjustment.  Small for most baskets but
        notable for produce (highest seasonality_factor).

    All components are summed into raw_change, then clamped to [-0.05, +0.05].
    Returning 0.0125 means the basket price index will rise by 1.25% today.
    Returning -0.03 means it will fall by 3%.

    Determinism guarantee:
        Same macro inputs + same basket sensitivities + same day_number
        will ALWAYS produce the same output.  No hidden randomness.
    """
    inflation = float(macro.inflation)
    oil_index = float(macro.oil_index)
    consumer_confidence = float(macro.consumer_confidence)
    supply_chain_stress = float(macro.supply_chain_stress)

    inflation_sensitivity = float(basket.inflation_sensitivity)
    oil_sensitivity = float(basket.oil_sensitivity)
    confidence_sensitivity = float(basket.confidence_sensitivity)
    supply_chain_sensitivity = float(basket.supply_chain_sensitivity)
    seasonality_factor = float(basket.seasonality_factor)

    # Component 1: inflation deviation from normal (2%)
    # Example: inflation=4.0 → (4-2)/100 = 0.02 × 0.6 = 0.012 (+1.2% for essentials)
    inflation_component = ((inflation - INFLATION_BASELINE) / 100.0) * inflation_sensitivity

    # Component 2: oil price deviation from baseline (100)
    # Example: oil_index=120 → (120-100)/100 = 0.2 × 0.5 = 0.1 → capped at 0.05
    oil_component = ((oil_index - OIL_BASELINE) / 100.0) * oil_sensitivity

    # Component 3: confidence below midpoint pushes prices up
    # Example: consumer_confidence=30 → (50-30)/100 = 0.2 × 0.1 = 0.02 (+2%)
    confidence_component = ((CONFIDENCE_MIDPOINT - consumer_confidence) / 100.0) * confidence_sensitivity

    # Component 4: supply chain stress is always upward pressure when present
    # Example: supply_chain_stress=40 → 40/100 = 0.4 × 0.7 = 0.28 → capped at 0.05
    supply_chain_component = (supply_chain_stress / 100.0) * supply_chain_sensitivity

    # Component 5: seasonal sine-wave (deterministic, 30-day cycle)
    seasonality_component = calculate_seasonality_adjustment(
        day_number=day_number,
        seasonality_factor=seasonality_factor,
        basket_id=basket.id,
    )

    raw_change = (
        inflation_component
        + oil_component
        + confidence_component
        + supply_chain_component
        + seasonality_component
    )

    # Hard cap: basket price index cannot change by more than ±5% in a single day.
    # This prevents unrealistic chaos while still allowing meaningful pressure.
    clamped = max(MIN_DAILY_CHANGE, min(MAX_DAILY_CHANGE, raw_change))
    return round(clamped, 6)


# ─────────────────────────────────────────────────────────────────────────────
# Apply daily price update (DB-facing, idempotent)
# ─────────────────────────────────────────────────────────────────────────────


def apply_daily_basket_price_update(
    db: Session,
    day_number: int,
) -> list[BasketPriceHistory]:
    """
    Apply basket price index changes for *day_number* and write history rows.

    This function is idempotent: if BasketPriceHistory rows already exist for
    ALL active baskets on *day_number*, the function returns the existing rows
    without modifying any basket.

    Steps:
      1. Get/create MacroState for the day.
      2. Load all active GoodsBaskets.
      3. For each basket:
         a. Check whether a history row already exists — if so, skip it.
         b. Calculate change percent via calculate_basket_daily_change_percent().
         c. Compute new_price_index = old × (1 + change), floor at MIN_PRICE_INDEX.
         d. Update basket.price_index in place.
         e. Create BasketPriceHistory row capturing macro snapshot.
      4. Commit atomically.
      5. Return created (or existing) history rows.

    Idempotency design:
      Per-basket idempotency: if a history row exists for (basket_id, day_number),
      that basket is skipped.  This means partial updates are possible if the
      system crashed mid-run, and a second call will complete the remaining baskets.

    Raises:
      RuntimeError if no active baskets exist (should not happen in a seeded DB).
    """
    macro = get_or_create_macro_state_for_day(db, day_number)
    baskets = db.query(GoodsBasket).filter(GoodsBasket.is_active.is_(True)).all()

    if not baskets:
        raise RuntimeError("No active GoodsBasket rows found.  Run startup seeding first.")

    created_rows: list[BasketPriceHistory] = []
    updated_count = 0

    for basket in baskets:
        # Idempotency check: if history already exists for this basket+day, skip.
        existing = (
            db.query(BasketPriceHistory)
            .filter(
                BasketPriceHistory.basket_id == basket.id,
                BasketPriceHistory.day_number == day_number,
            )
            .first()
        )
        if existing is not None:
            created_rows.append(existing)
            continue

        old_index = float(basket.price_index)
        change_percent = calculate_basket_daily_change_percent(basket, macro, day_number)

        # Apply the change and enforce the floor.
        new_index = round(old_index * (1.0 + change_percent), 4)
        new_index = max(MIN_PRICE_INDEX, new_index)

        # Persist the updated price index on the basket row.
        basket.price_index = new_index

        # Create the immutable audit history row.
        history_row = BasketPriceHistory(
            basket_id=basket.id,
            day_number=day_number,
            old_price_index=old_index,
            new_price_index=new_index,
            change_percent=change_percent,
            inflation_used=float(macro.inflation),
            oil_index_used=float(macro.oil_index),
            consumer_confidence_used=float(macro.consumer_confidence),
            supply_chain_stress_used=float(macro.supply_chain_stress),
        )
        db.add(history_row)
        created_rows.append(history_row)
        updated_count += 1

    # Commit all basket updates and new history rows atomically.
    db.commit()

    # Refresh newly created rows so callers see populated fields (e.g. created_at).
    for row in created_rows:
        try:
            db.refresh(row)
        except Exception:
            pass  # Already-expired rows from other sessions are safe to skip.

    return created_rows


# ─────────────────────────────────────────────────────────────────────────────
# Serializers (pure, no DB access)
# ─────────────────────────────────────────────────────────────────────────────


def serialize_macro_state(macro: MacroState) -> dict:
    """Return a JSON-friendly dict representation of a MacroState row."""
    return {
        "id": macro.id,
        "day_number": macro.day_number,
        "inflation": float(macro.inflation),
        "interest_rate": float(macro.interest_rate),
        "unemployment": float(macro.unemployment),
        "oil_index": float(macro.oil_index),
        "consumer_confidence": float(macro.consumer_confidence),
        "supply_chain_stress": float(macro.supply_chain_stress),
        "is_active": macro.is_active,
        "created_at": macro.created_at.isoformat() if macro.created_at else None,
        "updated_at": macro.updated_at.isoformat() if macro.updated_at else None,
    }


def serialize_basket_price_history(row: BasketPriceHistory) -> dict:
    """Return a JSON-friendly dict representation of a BasketPriceHistory row."""
    return {
        "id": str(row.id),
        "basket_id": row.basket_id,
        "day_number": row.day_number,
        "old_price_index": float(row.old_price_index),
        "new_price_index": float(row.new_price_index),
        "change_percent": float(row.change_percent),
        "change_percent_display": round(float(row.change_percent) * 100, 4),  # e.g. 1.25 for +1.25%
        "inflation_used": float(row.inflation_used),
        "oil_index_used": float(row.oil_index_used),
        "consumer_confidence_used": float(row.consumer_confidence_used),
        "supply_chain_stress_used": float(row.supply_chain_stress_used),
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
