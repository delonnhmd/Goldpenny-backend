"""
Basket Engine — pure helpers and DB-facing basket logic.

Design principles:
  - Pure calculation functions are stateless and unit-testable.
  - DB-facing functions accept a Session and commit atomically.
  - No FastAPI imports; no blockchain calls.
  - No spoilage, nutrition, or inventory complexity in Step 4.

Economic intent:
  Baskets are coarse expense categories representing daily living costs.
  XGP must flow OUT of the player's balance, not only IN.
  Basket spending creates the first real budget pressure and will later
  connect to:
    - health/stress recovery quality (what did you eat today?)
    - inflation demand signals (aggregate spending drives price index)
    - supply-chain / business demand models

Sample daily flow (Step 4 perspective):
  Day 5:
    - player starts with XGP balance
    - player buys 2 essentials units  → XGP decreases by 50
    - player buys 1 produce unit      → XGP decreases by 20
    - daily basket summary shows accumulated totals
    - end-of-day settlement reads daily state for recovery calculations
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.goods_basket import DEFAULT_BASKETS, VALID_BASKET_IDS, GoodsBasket

# ── Daily cap rules ───────────────────────────────────────────────────────────
# MVP: no player should bulk-buy more than 20 units in a single purchase.
# This prevents economy exploits while allowing realistic daily spending.
MAX_UNITS_PER_PURCHASE = 20.0

# ── Basket → PlayerDailyState field name map ──────────────────────────────────
_BASKET_DAILY_FIELD: dict[str, str] = {
    "essentials": "essentials_units",
    "protein": "protein_units",
    "produce": "produce_units",
    "convenience": "convenience_units",
}


# ─────────────────────────────────────────────────────────────────────────────
# Pure helper functions (no DB access, fully deterministic)
# ─────────────────────────────────────────────────────────────────────────────


def calculate_basket_unit_price(base_price: float, price_index: float) -> float:
    """
    Compute the current unit price for a basket.

    Formula:  actual_price = base_price × (price_index / 100)

    A price_index of 100 means no inflation adjustment.
    Values above 100 raise the cost; values below 100 lower it.

    Returns the price rounded to 2 decimal places, minimum 0.
    """
    raw = float(base_price) * (float(price_index) / 100.0)
    return max(0.0, round(raw, 2))


def calculate_basket_total_cost(unit_price: float, quantity: float) -> float:
    """
    Compute the total cost for a basket purchase.

    Formula:  total_cost = unit_price × quantity

    Returns the cost rounded to 2 decimal places.
    The caller is responsible for ensuring quantity is positive.
    """
    return round(float(unit_price) * float(quantity), 2)


def validate_basket_purchase(
    quantity: float,
    balance: float,
    total_cost: float,
    basket_id: str,
) -> tuple[bool, Optional[str]]:
    """
    Validate a basket purchase request before touching the database.

    Returns (True, None) if valid, or (False, reason) if invalid.

    Rules enforced:
      - basket_id must be one of the 4 allowed basket ids
      - quantity must be > 0
      - quantity must not exceed MVP cap (20 units per purchase)
      - total_cost must be > 0
      - player must have sufficient XGP balance (no negative balances)
    """
    if basket_id not in VALID_BASKET_IDS:
        return False, (
            f"Unknown basket '{basket_id}'. "
            f"Valid baskets: {sorted(VALID_BASKET_IDS)}."
        )
    if quantity <= 0:
        return False, "Quantity must be greater than 0."
    if quantity > MAX_UNITS_PER_PURCHASE:
        return False, (
            f"Maximum {MAX_UNITS_PER_PURCHASE} units per purchase. "
            f"Requested: {quantity}."
        )
    if total_cost <= 0:
        return False, "Total cost must be greater than 0."
    if balance < total_cost:
        return False, (
            f"Insufficient XGP balance. "
            f"Required: {total_cost:.2f}, available: {balance:.2f}."
        )
    return True, None


def get_daily_basket_field_name(basket_id: str) -> str:
    """
    Return the PlayerDailyState field name that tracks *basket_id* units.

    Raises ValueError for unknown basket ids.

    Mapping:
      essentials  → essentials_units
      protein     → protein_units
      produce     → produce_units
      convenience → convenience_units
    """
    field = _BASKET_DAILY_FIELD.get(basket_id)
    if field is None:
        raise ValueError(
            f"No daily state field mapping for basket '{basket_id}'. "
            f"Valid baskets: {sorted(VALID_BASKET_IDS)}."
        )
    return field


def build_basket_purchase_summary(
    basket_id: str,
    display_name: str,
    quantity: float,
    unit_price: float,
    total_cost: float,
    balance_before: float,
    balance_after: float,
    day_number: int,
) -> dict:
    """
    Build the response dictionary returned by the basket buy endpoint.

    All values are rounded for clean API responses.
    """
    return {
        "basket_id": basket_id,
        "display_name": display_name,
        "quantity": round(quantity, 4),
        "unit_price": round(unit_price, 2),
        "total_cost": round(total_cost, 2),
        "balance_before": round(balance_before, 2),
        "balance_after": round(balance_after, 2),
        "day_number": day_number,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DB-facing helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_or_seed_default_baskets(db: Session) -> list[GoodsBasket]:
    """
    Ensure the 4 default GoodsBasket rows exist, creating any that are missing.

    Safe to call on every startup — existing rows are not modified.
    Returns all active baskets after seeding.
    """
    for seed in DEFAULT_BASKETS:
        existing = db.query(GoodsBasket).filter(GoodsBasket.id == seed["basket_id"]).first()
        if existing is None:
            row = GoodsBasket(
                id=seed["basket_id"],
                display_name=seed["display_name"],
                base_price=seed["base_price"],
                price_index=seed["price_index"],
                is_active=True,
            )
            db.add(row)

    db.commit()
    return db.query(GoodsBasket).filter(GoodsBasket.is_active.is_(True)).all()
