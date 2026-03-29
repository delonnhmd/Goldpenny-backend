"""Seed script for the first core Alembic-backed schema.

Usage:
    python seed_core_schema.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

from app.db.database import SessionLocal
from app.models.basket_daily_price import BasketDailyPrice
from app.models.enums import BasketType
from app.models.job_definition_db import JobDefinition
from app.models.macro_daily_state import MacroDailyState
from app.models.stock_daily_price import StockDailyPrice


JOBS = [
    {
        "job_code": "auto_mechanic",
        "title": "Auto Mechanic",
        "base_monthly_pay_xgp": 4000,
        "stability_pct": 80,
        "growth_pct": 55,
        "stress_pct": 40,
        "promotion_threshold": 120,
    },
    {
        "job_code": "aircraft_mechanic",
        "title": "Aircraft Mechanic",
        "base_monthly_pay_xgp": 6200,
        "stability_pct": 88,
        "growth_pct": 70,
        "stress_pct": 55,
        "promotion_threshold": 150,
    },
    {
        "job_code": "banker",
        "title": "Banker",
        "base_monthly_pay_xgp": 5100,
        "stability_pct": 82,
        "growth_pct": 75,
        "stress_pct": 60,
        "promotion_threshold": 140,
    },
    {
        "job_code": "chef",
        "title": "Chef",
        "base_monthly_pay_xgp": 3500,
        "stability_pct": 72,
        "growth_pct": 60,
        "stress_pct": 65,
        "promotion_threshold": 110,
    },
    {
        "job_code": "retail_worker",
        "title": "Retail Worker",
        "base_monthly_pay_xgp": 2600,
        "stability_pct": 65,
        "growth_pct": 35,
        "stress_pct": 45,
        "promotion_threshold": 90,
    },
    {
        "job_code": "delivery_driver",
        "title": "Delivery Driver",
        "base_monthly_pay_xgp": 3000,
        "stability_pct": 60,
        "growth_pct": 20,
        "stress_pct": 35,
        "promotion_threshold": 95,
    },
]

BASKET_DAY1 = [
    {
        "basket_type": BasketType.essentials,
        "price_index": 100.0,
        "daily_change_pct": 0.0,
        "supply_pressure": 1.00,
        "demand_pressure": 1.00,
    },
    {
        "basket_type": BasketType.protein,
        "price_index": 102.0,
        "daily_change_pct": 0.0,
        "supply_pressure": 1.02,
        "demand_pressure": 1.00,
    },
    {
        "basket_type": BasketType.produce,
        "price_index": 101.0,
        "daily_change_pct": 0.0,
        "supply_pressure": 1.01,
        "demand_pressure": 1.00,
    },
    {
        "basket_type": BasketType.convenience,
        "price_index": 98.0,
        "daily_change_pct": 0.0,
        "supply_pressure": 0.99,
        "demand_pressure": 1.00,
    },
]

STOCK_DAY1 = [
    {"ticker": "GPEN", "sector": "energy", "open_price": 45.0, "close_price": 45.8, "macro_impact": 0.20, "noise_component": 1.58},
    {"ticker": "GPTECH", "sector": "technology", "open_price": 62.0, "close_price": 63.4, "macro_impact": 0.30, "noise_component": 1.96},
    {"ticker": "GPRETAIL", "sector": "retail", "open_price": 39.0, "close_price": 38.6, "macro_impact": -0.10, "noise_component": -0.93},
    {"ticker": "GPHEALTH", "sector": "healthcare", "open_price": 58.0, "close_price": 58.5, "macro_impact": 0.15, "noise_component": 0.71},
    {"ticker": "GPBANK", "sector": "finance", "open_price": 54.0, "close_price": 54.2, "macro_impact": 0.12, "noise_component": 0.25},
    {"ticker": "GPAUTO", "sector": "automotive", "open_price": 42.0, "close_price": 41.3, "macro_impact": -0.18, "noise_component": -1.49},
    {"ticker": "GPTRANS", "sector": "transport", "open_price": 36.0, "close_price": 35.9, "macro_impact": -0.08, "noise_component": -0.20},
    {"ticker": "GPREAL", "sector": "real_estate", "open_price": 48.0, "close_price": 47.6, "macro_impact": -0.11, "noise_component": -0.72},
    {"ticker": "GPDEF", "sector": "defense", "open_price": 67.0, "close_price": 68.1, "macro_impact": 0.25, "noise_component": 1.39},
    {"ticker": "GPCONS", "sector": "consumer", "open_price": 33.0, "close_price": 33.5, "macro_impact": 0.10, "noise_component": 1.42},
]


def main() -> None:
    db = SessionLocal()
    try:
        # 1) Job definitions.
        for row in JOBS:
            existing = (
                db.query(JobDefinition)
                .filter(JobDefinition.job_code == row["job_code"])
                .first()
            )
            if existing is None:
                db.add(JobDefinition(**row))

        # 2) Macro day 1.
        macro = db.query(MacroDailyState).filter(MacroDailyState.day == 1).first()
        if macro is None:
            db.add(
                MacroDailyState(
                    day=1,
                    inflation_rate=2.2,
                    interest_rate=4.0,
                    unemployment_rate=5.1,
                    oil_index=100.0,
                    consumer_confidence=52.0,
                    supply_chain_stress=8.0,
                    event_headline="Stable Opening Conditions",
                    event_summary="The economy opens near baseline with mild supply friction.",
                )
            )

        # 3) Basket day 1 rows.
        for row in BASKET_DAY1:
            existing = (
                db.query(BasketDailyPrice)
                .filter(
                    BasketDailyPrice.day == 1,
                    BasketDailyPrice.basket_type == row["basket_type"],
                )
                .first()
            )
            if existing is None:
                db.add(BasketDailyPrice(day=1, **row))

        # 4) Stock day 1 rows.
        for row in STOCK_DAY1:
            existing = (
                db.query(StockDailyPrice)
                .filter(StockDailyPrice.day == 1, StockDailyPrice.ticker == row["ticker"])
                .first()
            )
            if existing is None:
                open_price = float(row["open_price"])
                close_price = float(row["close_price"])
                pct = ((close_price - open_price) / open_price) * 100.0
                db.add(
                    StockDailyPrice(
                        day=1,
                        ticker=row["ticker"],
                        sector=row["sector"],
                        open_price=open_price,
                        close_price=close_price,
                        daily_change_pct=round(pct, 4),
                        macro_impact=row["macro_impact"],
                        noise_component=row["noise_component"],
                    )
                )

        db.commit()

        print("Core seed complete:")
        print(f"  jobs={db.query(JobDefinition).count()}")
        print(f"  macro_rows={db.query(MacroDailyState).count()}")
        print(f"  basket_rows={db.query(BasketDailyPrice).count()}")
        print(f"  stock_rows={db.query(StockDailyPrice).count()}")
    except Exception as exc:
        db.rollback()
        print(f"Seed failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

