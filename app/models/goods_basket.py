"""
GoodsBasket — global goods basket definition and current price state.

NOTE: This is NOT the same as app/models/basket.py which is a stock-portfolio
basket (player → stock holdings).  This model represents the 4 NPC/system
expense categories used for daily living costs.

The 4 MVP baskets:
  essentials  — food staples, basic household supplies
  protein     — meat, dairy, eggs, protein sources
  produce     — fruit and vegetables
  convenience — ready meals, takeaway, convenience-store goods

Price = base_price × (price_index / 100).
A price_index of 100 means "normal" cost.
Future inflation and supply-chain systems will adjust price_index over time.

Economic intent:
  Baskets create outward XGP pressure so the economy has both income and
  expenditure.  Without spending, XGP only accumulates and there is no
  budget stress.  Basket costs are the first mandatory living expense.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Numeric, String, func

from app.db.database import Base

# ── Allowed basket_id values ──────────────────────────────────────────────────
VALID_BASKET_IDS = {"essentials", "protein", "produce", "convenience"}

# ── Default seed data ─────────────────────────────────────────────────────────
# Used by get_or_seed_default_baskets() in basket_engine.py.
# base_price in XGP per unit; price_index 100 = normal cost.
#
# Sensitivity fields (Step 5) control how strongly each basket reacts to each
# macro variable.  Values are dimensionless weights used in the price formula:
#   raw_change += ((macro_var - baseline) / 100) * sensitivity
#
# essentials  — stable; people always need basics regardless of conditions
# protein     — volatile; supply chains and oil strongly affect meat/dairy
# produce     — highly seasonal and supply-sensitive; oil matters for transport
# convenience — labor and inflation sensitive; high-margin discretionary goods
DEFAULT_BASKETS = [
    {
        "basket_id": "essentials",
        "display_name": "Essentials Basket",
        "base_price": 25.0,
        "price_index": 100.0,
        "inflation_sensitivity": 0.6,
        "oil_sensitivity": 0.3,
        "confidence_sensitivity": 0.1,
        "supply_chain_sensitivity": 0.4,
        "seasonality_factor": 0.1,
    },
    {
        "basket_id": "protein",
        "display_name": "Protein Basket",
        "base_price": 35.0,
        "price_index": 100.0,
        "inflation_sensitivity": 0.7,
        "oil_sensitivity": 0.4,
        "confidence_sensitivity": 0.1,
        "supply_chain_sensitivity": 0.5,
        "seasonality_factor": 0.2,
    },
    {
        "basket_id": "produce",
        "display_name": "Produce Basket",
        "base_price": 20.0,
        "price_index": 100.0,
        "inflation_sensitivity": 0.5,
        "oil_sensitivity": 0.5,
        "confidence_sensitivity": 0.05,
        "supply_chain_sensitivity": 0.7,
        "seasonality_factor": 0.5,
    },
    {
        "basket_id": "convenience",
        "display_name": "Convenience Basket",
        "base_price": 18.0,
        "price_index": 100.0,
        "inflation_sensitivity": 0.8,
        "oil_sensitivity": 0.2,
        "confidence_sensitivity": 0.2,
        "supply_chain_sensitivity": 0.3,
        "seasonality_factor": 0.05,
    },
]


class GoodsBasket(Base):
    """Global goods basket definition — one row per basket type.

    Singleton-like: only 4 rows expected in MVP.
    Price index is updated by the economy engine in future steps.
    """

    __tablename__ = "goods_baskets"

    id = Column(String(40), primary_key=True)  # uses basket_id as PK for simplicity

    # Human-readable basket name for display in API responses.
    display_name = Column(String(100), nullable=False)

    # Base price in XGP per unit at normal inflation (price_index = 100).
    base_price = Column(Numeric(12, 4), nullable=False)

    # Price multiplier: actual_price = base_price * (price_index / 100).
    # Starts at 100 (= no inflation adjustment).
    # Future economy steps will raise or lower this based on supply/demand.
    price_index = Column(Numeric(8, 4), nullable=False, default=100.0)

    # Inactive baskets are hidden from the list and cannot be purchased.
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Step 5: Macro sensitivity weights ─────────────────────────────────────
    # These weights control how strongly this basket's price reacts to each
    # macroeconomic variable in macro_engine.calculate_basket_daily_change_percent().
    #
    # All sensitivities are dimensionless multipliers in [0, 1].
    # A value of 0 means the basket is completely insensitive to that variable.
    # A value of 1 means maximum sensitivity (full unit-for-unit reaction).
    #
    # Different baskets react differently to the same macro conditions:
    #   essentials   — stable; lower sensitivity across the board
    #   protein      — volatile; oil and supply chain strongly matter
    #   produce      — most seasonal; highest supply_chain_sensitivity
    #   convenience  — inflation and labor sensitive; highest inflation_sensitivity

    # How strongly inflation deviations from 2% move this basket's price.
    inflation_sensitivity = Column(Numeric(6, 4), nullable=False, default=0.6)

    # How strongly oil_index deviations from 100 move this basket's price.
    oil_sensitivity = Column(Numeric(6, 4), nullable=False, default=0.3)

    # How strongly consumer_confidence deviations from 50 move this basket's price.
    # Note: lower confidence pushes prices slightly up (precautionary buying).
    confidence_sensitivity = Column(Numeric(6, 4), nullable=False, default=0.1)

    # How strongly supply_chain_stress (0–100) moves this basket's price.
    supply_chain_sensitivity = Column(Numeric(6, 4), nullable=False, default=0.4)

    # Amplitude of the seasonal sine-wave component for this basket.
    # Produce has the highest factor (0.5); convenience the lowest (0.05).
    seasonality_factor = Column(Numeric(6, 4), nullable=False, default=0.1)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
