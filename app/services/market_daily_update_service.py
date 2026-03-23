"""Market daily update service.

Generates the next stock market day from macro conditions using simple, tunable
sector formulas plus bounded noise.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import random

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.macro_daily_state import MacroDailyState
from app.models.stock_daily_price import StockDailyPrice

MOVE_CAP = Decimal("0.06")  # +/- 6% daily cap
NOISE_CAP = Decimal("0.01")  # +/- 1% bounded noise
MIN_PRICE = Decimal("1.0000")
MONEY_4 = Decimal("0.0001")
PCT_4 = Decimal("0.0001")


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


def generate_next_stock_day(db: Session) -> dict:
    """Generate one new stock_daily_prices day for all tickers.

    Day sequencing:
    - previous stock day = max(stock_daily_prices.day)
    - new stock day      = previous + 1
    - macro used         = macro row for new day if present, else latest macro row
    """
    previous_stock_day = db.query(func.max(StockDailyPrice.day)).scalar()
    if previous_stock_day is None:
        raise MarketDataMissingError("No stock_daily_prices seed rows found.")

    latest_macro = db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()
    if latest_macro is None:
        raise MarketDataMissingError("No macro_daily_states rows found.")

    new_market_day = int(previous_stock_day) + 1
    macro_for_day = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day == new_market_day)
        .first()
    ) or latest_macro

    previous_rows = (
        db.query(StockDailyPrice)
        .filter(StockDailyPrice.day == previous_stock_day)
        .order_by(StockDailyPrice.ticker.asc())
        .all()
    )
    if not previous_rows:
        raise MarketDataMissingError(f"No stock rows found for day {previous_stock_day}.")

    created = 0
    for prev in previous_rows:
        open_price = _q4(_d(prev.close_price))
        macro_impact = _q4(_macro_impact_for_ticker(prev.ticker, macro_for_day))
        noise_component = _q4(_noise_for_ticker_day(prev.ticker, new_market_day))

        move_fraction = _clamp(macro_impact + noise_component, -MOVE_CAP, MOVE_CAP)
        close_price = _q4(max(MIN_PRICE, open_price * (Decimal("1.0") + move_fraction)))
        daily_change_pct = _pct4(((close_price - open_price) / open_price) * Decimal("100"))

        row = StockDailyPrice(
            day=new_market_day,
            ticker=prev.ticker,
            sector=prev.sector,
            open_price=open_price,
            close_price=close_price,
            daily_change_pct=daily_change_pct,
            macro_impact=macro_impact,
            noise_component=noise_component,
        )
        db.add(row)
        created += 1

    db.commit()

    return {
        "previous_market_day": int(previous_stock_day),
        "new_market_day": int(new_market_day),
        "macro_day_used": int(macro_for_day.day),
        "number_of_stock_rows_created": int(created),
    }
