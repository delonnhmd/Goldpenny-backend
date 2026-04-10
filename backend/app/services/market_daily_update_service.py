"""Market daily update service.

Generates the next stock market day from macro conditions using simple, tunable
sector formulas plus bounded noise.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
import random

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.macro_daily_state import MacroDailyState
from app.models.stock_daily_price import StockDailyPrice

MOVE_CAP = Decimal("0.06")  # +/- 6% daily cap
NOISE_CAP = Decimal("0.01")  # +/- 1% bounded noise
MIN_PRICE = Decimal("1.0000")
MONEY_4 = Decimal("0.0001")
PCT_4 = Decimal("0.0001")
logger = logging.getLogger(__name__)


class MarketUpdateError(Exception):
    """Base exception for market daily update failures."""


class MarketDataMissingError(MarketUpdateError):
    """Raised when required macro/stock seed data is unavailable."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(MONEY_4, rounding=ROUND_HALF_UP)


def _pct4(value: Decimal) -> Decimal:
    return value.quantize(PCT_4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _macro_impact_for_ticker(ticker: str, macro: MacroDailyState) -> Decimal:
    """Return deterministic macro impact as a daily move fraction."""
    inflation = (_d(macro.inflation_rate) - Decimal("2.0")) / Decimal("100")
    interest = (_d(macro.interest_rate) - Decimal("4.0")) / Decimal("100")
    unemployment = (_d(macro.unemployment_rate) - Decimal("5.0")) / Decimal("100")
    oil = (_d(macro.oil_index) - Decimal("100.0")) / Decimal("100")
    confidence = (_d(macro.consumer_confidence) - Decimal("50.0")) / Decimal("100")
    supply = _d(macro.supply_chain_stress) / Decimal("100")

    # The coefficients are intentionally simple and readable for MVP tuning.
    if ticker == "GPEN":
        return (Decimal("0.60") * oil) + (Decimal("0.10") * confidence) - (Decimal("0.20") * unemployment)
    if ticker == "GPTRANS":
        return (Decimal("-0.70") * oil) + (Decimal("0.20") * confidence) - (Decimal("0.10") * inflation)
    if ticker == "GPBANK":
        return (Decimal("0.35") * confidence) - (Decimal("0.25") * interest) - (Decimal("0.15") * unemployment)
    if ticker == "GPRETAIL":
        return (
            (Decimal("0.45") * confidence)
            - (Decimal("0.40") * inflation)
            - (Decimal("0.20") * unemployment)
            - (Decimal("0.15") * supply)
        )
    if ticker == "GPCONS":
        return (Decimal("0.40") * confidence) - (Decimal("0.45") * inflation) - (Decimal("0.15") * supply)
    if ticker == "GPHEALTH":
        return (Decimal("0.15") * confidence) - (Decimal("0.05") * interest) - (Decimal("0.05") * unemployment)
    if ticker == "GPREAL":
        return (Decimal("0.35") * confidence) - (Decimal("0.60") * interest) - (Decimal("0.20") * unemployment)
    if ticker == "GPAUTO":
        return (
            (Decimal("0.50") * confidence)
            - (Decimal("0.30") * inflation)
            - (Decimal("0.25") * interest)
            - (Decimal("0.10") * oil)
        )
    if ticker == "GPDEF":
        return (Decimal("0.10") * confidence) - (Decimal("0.05") * unemployment) + (Decimal("0.05") * supply)
    if ticker == "GPTECH":
        return (Decimal("0.55") * confidence) - (Decimal("0.40") * interest) - (Decimal("0.10") * inflation)

    # Fallback for unknown tickers: conservative broad-market drift.
    return (Decimal("0.20") * confidence) - (Decimal("0.20") * inflation) - (Decimal("0.10") * interest)


def _noise_for_ticker_day(ticker: str, day: int) -> Decimal:
    """Deterministic bounded noise in [-1%, +1%] using ticker/day seed."""
    rng = random.Random(f"{ticker}:{day}")
    return Decimal(str(rng.uniform(float(-NOISE_CAP), float(NOISE_CAP))))


def _latest_stock_day(db: Session) -> int | None:
    latest_day = db.query(func.max(StockDailyPrice.day)).scalar()
    return int(latest_day) if latest_day is not None else None


def _latest_macro_row(db: Session) -> MacroDailyState:
    latest_macro = db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()
    if latest_macro is None:
        raise MarketDataMissingError("No macro_daily_states rows found.")
    return latest_macro


def _build_stock_daily_price_payload(
    previous_row: StockDailyPrice,
    *,
    day_number: int,
    macro_for_day: MacroDailyState,
) -> dict[str, Decimal | str | int]:
    open_price = _q4(_d(previous_row.close_price))
    macro_impact = _q4(_macro_impact_for_ticker(previous_row.ticker, macro_for_day))
    noise_component = _q4(_noise_for_ticker_day(previous_row.ticker, day_number))

    move_fraction = _clamp(macro_impact + noise_component, -MOVE_CAP, MOVE_CAP)
    close_price = _q4(max(MIN_PRICE, open_price * (Decimal("1.0") + move_fraction)))
    daily_change_pct = _pct4(((close_price - open_price) / open_price) * Decimal("100"))
    return {
        "day": int(day_number),
        "ticker": str(previous_row.ticker),
        "sector": str(previous_row.sector),
        "open_price": open_price,
        "close_price": close_price,
        "daily_change_pct": daily_change_pct,
        "macro_impact": macro_impact,
        "noise_component": noise_component,
    }


def get_or_create_stock_daily_price(
    db: Session,
    *,
    day_number: int,
    ticker: str,
    defaults: dict[str, Decimal | str | int],
    caller: str,
) -> tuple[StockDailyPrice, dict[str, bool]]:
    day_number = int(day_number)
    ticker = str(ticker or "").strip().upper()
    existing = (
        db.query(StockDailyPrice)
        .filter(
            StockDailyPrice.day == day_number,
            StockDailyPrice.ticker == ticker,
        )
        .first()
    )
    if existing is not None:
        logger.info(
            "market.stock_daily_price_resolved_existing",
            extra={
                "day_number": day_number,
                "ticker": ticker,
                "caller": caller,
                "row_existed_already": True,
                "insert_happened": False,
                "upsert_conflict": False,
                "returned_existing": True,
            },
        )
        return existing, {
            "row_existed_already": True,
            "insert_happened": False,
            "upsert_conflict": False,
            "returned_existing": True,
        }

    created = StockDailyPrice(**defaults)
    try:
        with db.begin_nested():
            db.add(created)
            db.flush()
        logger.info(
            "market.stock_daily_price_inserted",
            extra={
                "day_number": day_number,
                "ticker": ticker,
                "caller": caller,
                "row_existed_already": False,
                "insert_happened": True,
                "upsert_conflict": False,
                "returned_existing": False,
            },
        )
        return created, {
            "row_existed_already": False,
            "insert_happened": True,
            "upsert_conflict": False,
            "returned_existing": False,
        }
    except IntegrityError:
        existing = (
            db.query(StockDailyPrice)
            .filter(
                StockDailyPrice.day == day_number,
                StockDailyPrice.ticker == ticker,
            )
            .first()
        )
        if existing is None:
            raise
        logger.info(
            "market.stock_daily_price_conflict_returned_existing",
            extra={
                "day_number": day_number,
                "ticker": ticker,
                "caller": caller,
                "row_existed_already": False,
                "insert_happened": False,
                "upsert_conflict": True,
                "returned_existing": True,
            },
        )
        return existing, {
            "row_existed_already": False,
            "insert_happened": False,
            "upsert_conflict": True,
            "returned_existing": True,
        }


def generate_stock_day_for_day(
    db: Session,
    day_number: int,
    *,
    caller: str = "generate_stock_day_for_day",
) -> dict:
    """Idempotently ensure one stock_daily_prices market day exists."""
    requested_market_day = max(1, int(day_number))
    if requested_market_day <= 1:
        existing_rows = (
            db.query(StockDailyPrice)
            .filter(StockDailyPrice.day == requested_market_day)
            .order_by(StockDailyPrice.ticker.asc())
            .all()
        )
        if existing_rows:
            return {
                "previous_market_day": 0,
                "new_market_day": requested_market_day,
                "requested_market_day": requested_market_day,
                "macro_day_used": 1,
                "number_of_stock_rows_created": 0,
                "number_of_existing_stock_rows": len(existing_rows),
                "number_of_conflicts_resolved": 0,
                "already_exists": True,
            }
        raise MarketDataMissingError("Day 1 stock_daily_prices seed rows are required.")

    latest_macro = _latest_macro_row(db)
    macro_for_day = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day == requested_market_day)
        .first()
    ) or latest_macro
    previous_market_day = requested_market_day - 1
    previous_rows = (
        db.query(StockDailyPrice)
        .filter(StockDailyPrice.day == previous_market_day)
        .order_by(StockDailyPrice.ticker.asc())
        .all()
    )
    if not previous_rows:
        existing_rows = (
            db.query(StockDailyPrice)
            .filter(StockDailyPrice.day == requested_market_day)
            .order_by(StockDailyPrice.ticker.asc())
            .all()
        )
        if existing_rows:
            return {
                "previous_market_day": previous_market_day,
                "new_market_day": requested_market_day,
                "requested_market_day": requested_market_day,
                "macro_day_used": int(macro_for_day.day),
                "number_of_stock_rows_created": 0,
                "number_of_existing_stock_rows": len(existing_rows),
                "number_of_conflicts_resolved": 0,
                "already_exists": True,
            }
        raise MarketDataMissingError(f"No stock rows found for day {previous_market_day}.")

    created_count = 0
    existing_count = 0
    conflict_count = 0
    for previous_row in previous_rows:
        payload = _build_stock_daily_price_payload(
            previous_row,
            day_number=requested_market_day,
            macro_for_day=macro_for_day,
        )
        _, meta = get_or_create_stock_daily_price(
            db,
            day_number=requested_market_day,
            ticker=str(previous_row.ticker),
            defaults=payload,
            caller=caller,
        )
        created_count += 1 if meta["insert_happened"] else 0
        existing_count += 1 if meta["returned_existing"] else 0
        conflict_count += 1 if meta["upsert_conflict"] else 0

    db.commit()
    logger.info(
        "market.stock_day_generation_completed",
        extra={
            "requested_market_day": requested_market_day,
            "previous_market_day": previous_market_day,
            "caller": caller,
            "rows_created": created_count,
            "rows_returned_existing": existing_count,
            "rows_conflicted": conflict_count,
            "macro_day_used": int(macro_for_day.day),
        },
    )
    return {
        "previous_market_day": previous_market_day,
        "new_market_day": requested_market_day,
        "requested_market_day": requested_market_day,
        "macro_day_used": int(macro_for_day.day),
        "number_of_stock_rows_created": created_count,
        "number_of_existing_stock_rows": existing_count,
        "number_of_conflicts_resolved": conflict_count,
        "already_exists": created_count == 0,
    }


def ensure_stock_market_day(
    db: Session,
    target_day: int,
    *,
    caller: str = "ensure_stock_market_day",
) -> dict:
    """Advance stock market rows through *target_day* without duplicating inserts."""
    target_market_day = max(1, int(target_day))
    latest_market_day = _latest_stock_day(db)
    if latest_market_day is None:
        raise MarketDataMissingError("No stock_daily_prices seed rows found.")

    starting_market_day = latest_market_day
    generated_days: list[int] = []
    created_rows = 0
    existing_rows = 0
    conflict_rows = 0
    while latest_market_day < target_market_day:
        next_market_day = latest_market_day + 1
        update = generate_stock_day_for_day(
            db,
            next_market_day,
            caller=caller,
        )
        latest_market_day = int(update["new_market_day"])
        generated_days.append(latest_market_day)
        created_rows += int(update["number_of_stock_rows_created"])
        existing_rows += int(update["number_of_existing_stock_rows"])
        conflict_rows += int(update["number_of_conflicts_resolved"])

    logger.info(
        "market.ensure_stock_market_day_resolved",
        extra={
            "caller": caller,
            "starting_market_day": starting_market_day,
            "target_market_day": target_market_day,
            "latest_market_day": latest_market_day,
            "generated_days": generated_days,
            "created_rows": created_rows,
            "existing_rows": existing_rows,
            "conflict_rows": conflict_rows,
        },
    )
    return {
        "starting_market_day": starting_market_day,
        "target_market_day": target_market_day,
        "latest_market_day": latest_market_day,
        "generated_days": generated_days,
        "number_of_stock_rows_created": created_rows,
        "number_of_existing_stock_rows": existing_rows,
        "number_of_conflicts_resolved": conflict_rows,
    }


def generate_next_stock_day(db: Session) -> dict:
    """Generate the next stock_daily_prices day using the shared idempotent helper."""
    previous_stock_day = _latest_stock_day(db)
    if previous_stock_day is None:
        raise MarketDataMissingError("No stock_daily_prices seed rows found.")

    return generate_stock_day_for_day(
        db,
        previous_stock_day + 1,
        caller="generate_next_stock_day",
    )
