"""Basket pricing transmission layer for Step 14.

Computes basket daily price moves from macro + supply-chain signals.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.supply_chain_service import (
    SupplyChainError,
    SupplyChainNotFoundError,
    compute_supply_chain_daily_snapshot,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState

logger = logging.getLogger(__name__)

Q4 = Decimal("0.0001")
Q6 = Decimal("0.000001")

ONE = Decimal("1.00")
ZERO = Decimal("0.00")

MAX_DAILY_MOVE = Decimal("0.05")
MIN_DAILY_MOVE = Decimal("-0.05")

SUPPLY_COMPONENT_SCALE = Decimal("0.35")

BASKET_SUPPLY_SENSITIVITY: dict[str, Decimal] = {
    "essentials": Decimal("0.45"),
    "protein": Decimal("0.65"),
    "produce": Decimal("0.85"),
    "convenience": Decimal("0.55"),
}

BASKET_INFLATION_SENSITIVITY: dict[str, Decimal] = {
    "essentials": Decimal("0.0080"),
    "protein": Decimal("0.0095"),
    "produce": Decimal("0.0105"),
    "convenience": Decimal("0.0090"),
}

BASKET_OIL_SENSITIVITY: dict[str, Decimal] = {
    "essentials": Decimal("0.0025"),
    "protein": Decimal("0.0035"),
    "produce": Decimal("0.0048"),
    "convenience": Decimal("0.0032"),
}

DEFAULT_BASKET_INDEX: dict[str, Decimal] = {
    "essentials": Decimal("10.0000"),
    "protein": Decimal("12.0000"),
    "produce": Decimal("9.0000"),
    "convenience": Decimal("8.0000"),
}

BASKET_ORDER = (
    BasketType.essentials,
    BasketType.protein,
    BasketType.produce,
    BasketType.convenience,
)


class BasketPricingError(Exception):
    """Base exception for basket pricing compute."""


class BasketPricingNotFoundError(BasketPricingError):
    """Raised when macro/supply prerequisites are missing."""


class BasketPricingValidationError(BasketPricingError):
    """Raised for invalid request arguments."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _q6(value: Decimal) -> Decimal:
    return value.quantize(Q6, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


def _macro_for_request(db: Session, as_of_date: date | None, day: int | None) -> MacroDailyState | None:
    if day is not None:
        return (
            db.query(MacroDailyState)
            .filter(MacroDailyState.day <= int(day))
            .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
            .first()
        )
    if as_of_date is not None:
        row = (
            db.query(MacroDailyState)
            .filter(func.date(MacroDailyState.created_at) <= as_of_date.isoformat())
            .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
            .first()
        )
        if row is not None:
            return row
    return (
        db.query(MacroDailyState)
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )


def _previous_basket_row(db: Session, basket_type: BasketType, day: int) -> BasketDailyPrice | None:
    return (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day < int(day),
        )
        .order_by(BasketDailyPrice.day.desc(), BasketDailyPrice.created_at.desc())
        .first()
    )


def _existing_basket_rows_for_day(db: Session, day: int) -> dict[str, BasketDailyPrice]:
    rows = (
        db.query(BasketDailyPrice)
        .filter(BasketDailyPrice.day == int(day))
        .all()
    )
    return {_basket_type_key(getattr(row, "basket_type", None)): row for row in rows}


def _basket_type_key(value: object) -> str:
    if isinstance(value, BasketType):
        return str(value.value)
    return str(value or "").strip().lower()


def _specific_component(
    basket_key: str,
    inflation_pressure: Decimal,
    confidence_weakness: Decimal,
    confidence_support: Decimal,
    supply_stress_pressure: Decimal,
) -> Decimal:
    if basket_key == "produce":
        value = (supply_stress_pressure * Decimal("0.0040")) + (confidence_weakness * Decimal("0.0020"))
    elif basket_key == "protein":
        value = (supply_stress_pressure * Decimal("0.0020")) + (confidence_weakness * Decimal("0.0010"))
    elif basket_key == "convenience":
        value = (
            (confidence_weakness * Decimal("0.0030"))
            + (inflation_pressure * Decimal("0.0010"))
            - (confidence_support * Decimal("0.0010"))
        )
    else:
        value = (supply_stress_pressure * Decimal("0.0010")) - (confidence_support * Decimal("0.0020"))
    return _clamp(_q6(value), Decimal("-0.0100"), Decimal("0.0150"))


def _demand_pressure(confidence_weakness: Decimal, confidence_support: Decimal) -> Decimal:
    pressure = Decimal("1.00") + (confidence_support * Decimal("0.05")) - (
        confidence_weakness * Decimal("0.05")
    )
    return _clamp(_q4(pressure), Decimal("0.90"), Decimal("1.10"))


def compute_daily_basket_price_updates(
    db: Session,
    as_of_date: date | None = None,
    *,
    day: int | None = None,
    persist: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    """Compute basket daily pricing updates from supply-chain + macro inputs."""
    if day is not None and int(day) <= 0:
        raise BasketPricingValidationError("day must be greater than 0.")

    try:
        macro = _macro_for_request(db, as_of_date=as_of_date, day=day)
        if macro is None:
            raise BasketPricingNotFoundError("No macro state available for basket pricing.")

        target_day = int(day) if day is not None else int(macro.day)
        if target_day <= 0:
            raise BasketPricingValidationError("resolved target day must be greater than 0.")

        supply_snapshot = compute_supply_chain_daily_snapshot(
            db,
            as_of_date=as_of_date if day is None else None,
            macro_day=int(macro.day),
        )
        supply_by_basket = {
            str(row["basket_key"]): row for row in supply_snapshot.get("basket_supply", [])
        }

        normalized = supply_snapshot.get("debug_meta", {}).get("normalized_macro_inputs", {})
        inflation_pressure = _d(normalized.get("inflation_pressure", 0))
        oil_pressure = _d(normalized.get("oil_pressure", 0))
        confidence_weakness = _d(normalized.get("confidence_weakness", 0))
        confidence_support = _d(normalized.get("confidence_support", 0))
        supply_stress_pressure = _d(normalized.get("supply_stress_pressure", 0))

        existing_rows = _existing_basket_rows_for_day(db, target_day)
        already_processed = len(existing_rows) == len(BASKET_ORDER)
        created_rows = 0

        basket_updates: list[dict[str, Any]] = []

        for basket_type in BASKET_ORDER:
            basket_key = _basket_type_key(basket_type)
            existing_row = existing_rows.get(basket_key)
            previous_row = _previous_basket_row(db, basket_type, target_day)

            if previous_row is not None:
                old_index = _q4(_d(previous_row.price_index))
            elif existing_row is not None:
                old_index = _q4(_d(existing_row.price_index))
            else:
                old_index = _q4(DEFAULT_BASKET_INDEX[basket_key])

            supply_row = supply_by_basket.get(basket_key, {})
            supply_multiplier = _q4(_d(supply_row.get("supply_multiplier", ONE)))
            dominant_nodes = list(supply_row.get("dominant_nodes", []))

            inflation_component = _q6(
                inflation_pressure * BASKET_INFLATION_SENSITIVITY[basket_key]
            )
            oil_component = _q6(oil_pressure * BASKET_OIL_SENSITIVITY[basket_key])
            supply_component = _q6(
                (ONE - supply_multiplier)
                * BASKET_SUPPLY_SENSITIVITY[basket_key]
                * SUPPLY_COMPONENT_SCALE
            )
            basket_specific_component = _specific_component(
                basket_key=basket_key,
                inflation_pressure=inflation_pressure,
                confidence_weakness=confidence_weakness,
                confidence_support=confidence_support,
                supply_stress_pressure=supply_stress_pressure,
            )

            raw_change = _q6(
                inflation_component
                + oil_component
                + supply_component
                + basket_specific_component
            )
            daily_change = _clamp(raw_change, MIN_DAILY_MOVE, MAX_DAILY_MOVE)
            computed_new_index = _q4(old_index * (ONE + daily_change))
            computed_daily_change_pct = _q4(daily_change * Decimal("100"))
            demand_pressure = _demand_pressure(
                confidence_weakness=confidence_weakness,
                confidence_support=confidence_support,
            )

            if existing_row is not None:
                final_new_index = _q4(_d(existing_row.price_index))
                final_daily_change = _q6(_d(existing_row.daily_change_pct) / Decimal("100"))
                final_supply_multiplier = _q4(_d(existing_row.supply_pressure))
            else:
                final_new_index = computed_new_index
                final_daily_change = _q6(daily_change)
                final_supply_multiplier = _q4(supply_multiplier)
                if persist:
                    row = BasketDailyPrice(
                        day=target_day,
                        basket_type=basket_type,
                        price_index=final_new_index,
                        daily_change_pct=computed_daily_change_pct,
                        supply_pressure=final_supply_multiplier,
                        demand_pressure=demand_pressure,
                    )
                    db.add(row)
                    created_rows += 1

            basket_updates.append(
                {
                    "basket_key": basket_key,
                    "old_price_index": float(old_index),
                    "new_price_index": float(final_new_index),
                    "daily_change": float(final_daily_change),
                    "supply_multiplier": float(final_supply_multiplier),
                    "dominant_nodes": dominant_nodes[:3],
                    "drivers": {
                        "inflation_component": float(inflation_component),
                        "oil_component": float(oil_component),
                        "supply_component": float(supply_component),
                        "basket_specific_component": float(basket_specific_component),
                    },
                }
            )

        if persist and created_rows > 0:
            db.flush()
            if commit:
                db.commit()

        response_as_of_date = (
            as_of_date
            if as_of_date is not None
            else (macro.created_at.date() if macro.created_at else date.today())
        )
        return {
            "as_of_date": response_as_of_date,
            "macro_state_id": int(macro.id),
            "day": int(target_day),
            "already_processed": bool(already_processed),
            "basket_updates": basket_updates,
            "debug_meta": {
                "constants_version": "basket_pricing_v1",
                "macro_day_used": int(macro.day),
                "created_rows": int(created_rows),
                "supply_component_scale": float(SUPPLY_COMPONENT_SCALE),
                "max_daily_move": float(MAX_DAILY_MOVE),
                "min_daily_move": float(MIN_DAILY_MOVE),
                "supply_chain_snapshot": {
                    "as_of_date": supply_snapshot.get("as_of_date"),
                    "macro_state_id": supply_snapshot.get("macro_state_id"),
                },
                "sensitivity_constants": {
                    "supply": {k: float(v) for k, v in BASKET_SUPPLY_SENSITIVITY.items()},
                    "inflation": {k: float(v) for k, v in BASKET_INFLATION_SENSITIVITY.items()},
                    "oil": {k: float(v) for k, v in BASKET_OIL_SENSITIVITY.items()},
                },
            },
        }
    except (SupplyChainNotFoundError, SupplyChainError) as exc:
        if commit:
            db.rollback()
        raise BasketPricingError(f"Supply-chain dependency failed: {exc}") from exc
    except BasketPricingError:
        if commit:
            db.rollback()
        raise
    except Exception as exc:
        if commit:
            db.rollback()
        logger.exception(
            "basket_pricing.compute_failed",
            extra={
                "day_number": int(day or 0) if day is not None else None,
                "as_of_date": as_of_date.isoformat() if as_of_date is not None else None,
                "persist": bool(persist),
                "commit": bool(commit),
                "failure_type": exc.__class__.__name__,
            },
        )
        raise BasketPricingError("Unexpected basket pricing compute error.") from exc
