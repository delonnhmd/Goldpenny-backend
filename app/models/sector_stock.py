"""app/models/sector_stock.py — Step 9: Fictional sector-linked stocks.

These are NOT real tickers.  They are in-game assets that react to the macro
economy layer (MacroState) via deterministic sensitivity coefficients.

Economic context:
  Stocks are the first investment layer — optional, risky, and useful for
  wealth growth.  The 0.3% transaction fee prevents overtrading exploits.
  Sector diversification matters: tech reacts differently to oil than energy.
  Players must choose between liquidity (cash) and investment risk (stocks).

Seeding is idempotent (get_or_seed_default_stocks in stock_engine.py).
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class SectorStock(Base):
    """Master definition and live price for one fictional sector stock."""

    __tablename__ = "sector_stocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Stable short identifier used throughout the codebase.
    # e.g. "gp_energy", "gp_tech"
    stock_id = Column(String(40), unique=True, nullable=False, index=True)

    # Frontend-facing name.
    display_name = Column(String(80), nullable=False)

    # Sector label.  Matches MacroState sensitivity mapping.
    # e.g. "energy" | "tech" | "retail" | "health" | "bank" | "auto" |
    #      "transport" | "real_estate" | "defense" | "consumer"
    sector_type = Column(String(40), nullable=False, index=True)

    # Live price — updated once per day by apply_daily_stock_price_update().
    # All trades use this price; no intraday movement.
    current_price = Column(Numeric(12, 4), nullable=False, default=100.0)

    # Only active stocks are tradable and appear in /stocks/sector-list.
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Macro sensitivity coefficients ────────────────────────────────────────
    # These determine how strongly each macro variable moves the price each day.
    # Positive value = macro increase raises price.
    # Negative value = macro increase lowers price.
    # Formula in stock_engine.py::calculate_stock_daily_change_percent.
    confidence_sensitivity    = Column(Numeric(8, 4), nullable=False, default=0.0)
    inflation_sensitivity     = Column(Numeric(8, 4), nullable=False, default=0.0)
    oil_sensitivity           = Column(Numeric(8, 4), nullable=False, default=0.0)
    unemployment_sensitivity  = Column(Numeric(8, 4), nullable=False, default=0.0)
    interest_rate_sensitivity = Column(Numeric(8, 4), nullable=False, default=0.0)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ── Canonical seed data ───────────────────────────────────────────────────────
# Used by get_or_seed_default_stocks().
# Sensitivities are calibrated so different sectors feel meaningfully different.
DEFAULT_SECTOR_STOCKS: list[dict] = [
    {
        "stock_id": "gp_energy",
        "display_name": "GP Energy",
        "sector_type": "energy",
        "current_price": 100.0,
        "confidence_sensitivity":    0.10,
        "inflation_sensitivity":     0.20,
        "oil_sensitivity":           0.80,   # energy stocks love high oil
        "unemployment_sensitivity": -0.10,
        "interest_rate_sensitivity": -0.05,
    },
    {
        "stock_id": "gp_tech",
        "display_name": "GP Tech",
        "sector_type": "tech",
        "current_price": 100.0,
        "confidence_sensitivity":    0.60,   # tech rides confidence waves
        "inflation_sensitivity":    -0.20,
        "oil_sensitivity":          -0.10,
        "unemployment_sensitivity": -0.30,
        "interest_rate_sensitivity": -0.25,  # rate-sensitive growth stock
    },
    {
        "stock_id": "gp_retail",
        "display_name": "GP Retail",
        "sector_type": "retail",
        "current_price": 100.0,
        "confidence_sensitivity":    0.70,   # retail needs confident consumers
        "inflation_sensitivity":    -0.30,
        "oil_sensitivity":          -0.20,
        "unemployment_sensitivity": -0.50,
        "interest_rate_sensitivity": -0.10,
    },
    {
        "stock_id": "gp_health",
        "display_name": "GP Health",
        "sector_type": "health",
        "current_price": 100.0,
        "confidence_sensitivity":    0.20,
        "inflation_sensitivity":    -0.05,
        "oil_sensitivity":           0.00,
        "unemployment_sensitivity": -0.05,
        "interest_rate_sensitivity": -0.05,
    },
    {
        "stock_id": "gp_bank",
        "display_name": "GP Bank",
        "sector_type": "bank",
        "current_price": 100.0,
        "confidence_sensitivity":    0.30,
        "inflation_sensitivity":     0.10,
        "oil_sensitivity":           0.00,
        "unemployment_sensitivity": -0.40,
        "interest_rate_sensitivity": 0.25,   # banks profit on higher rates
    },
    {
        "stock_id": "gp_auto",
        "display_name": "GP Auto",
        "sector_type": "auto",
        "current_price": 100.0,
        "confidence_sensitivity":    0.35,
        "inflation_sensitivity":    -0.15,
        "oil_sensitivity":          -0.20,
        "unemployment_sensitivity": -0.25,
        "interest_rate_sensitivity": -0.20,
    },
    {
        "stock_id": "gp_transport",
        "display_name": "GP Transport",
        "sector_type": "transport",
        "current_price": 100.0,
        "confidence_sensitivity":    0.30,
        "inflation_sensitivity":    -0.10,
        "oil_sensitivity":          -0.60,   # transport is highly oil-sensitive
        "unemployment_sensitivity": -0.30,
        "interest_rate_sensitivity": -0.05,
    },
    {
        "stock_id": "gp_real_estate",
        "display_name": "GP Real Estate",
        "sector_type": "real_estate",
        "current_price": 100.0,
        "confidence_sensitivity":    0.35,
        "inflation_sensitivity":    -0.05,
        "oil_sensitivity":           0.00,
        "unemployment_sensitivity": -0.20,
        "interest_rate_sensitivity": -0.50,  # real estate hates high rates
    },
    {
        "stock_id": "gp_defense",
        "display_name": "GP Defense",
        "sector_type": "defense",
        "current_price": 100.0,
        "confidence_sensitivity":    0.10,
        "inflation_sensitivity":     0.05,
        "oil_sensitivity":           0.05,
        "unemployment_sensitivity": -0.05,
        "interest_rate_sensitivity": -0.05,
    },
    {
        "stock_id": "gp_consumer",
        "display_name": "GP Consumer",
        "sector_type": "consumer",
        "current_price": 100.0,
        "confidence_sensitivity":    0.50,
        "inflation_sensitivity":    -0.20,
        "oil_sensitivity":          -0.10,
        "unemployment_sensitivity": -0.30,
        "interest_rate_sensitivity": -0.10,
    },
]
