"""seed.py — Standalone database seed script for the Gold Penny backend.

Usage:
    python seed.py

Run this once after `alembic upgrade head` to populate the database with the
canonical starting data.  Every operation is idempotent — running the script
multiple times is safe.

What is seeded
--------------
  - 4 GoodsBasket rows (essentials, protein, produce, convenience)
  - 10 SectorStock rows (energy, tech, retail, finance, etc.)
  - 2 HousingRegion rows (suburban, downtown)
  - 2 BusinessType rows (cafe, convenience_store)
  - 4 DealTemplate rows (co-op deal templates)
  - NPC firms (2 regions × 2 firm types = 4 rows)
  - MacroState for day 1 (if not already present)
  - BasketPriceHistory stub for day 1 per basket (if not already present)

Jobs are NOT seeded to the database — they are defined as Python data
(JOB_CATALOG in app/models/job_definition.py) and served directly from memory.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Make sure we can import from the app package when running from the project
# root (i.e. the directory that contains this file).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()  # ensure DATABASE_URL etc. are in os.environ

from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.engine.basket_engine import get_or_seed_default_baskets
from app.engine.business_engine import get_or_seed_business_types
from app.engine.coop_deal_engine import get_or_seed_default_deal_templates
from app.engine.firm_engine import get_or_seed_npc_firms
from app.engine.housing_engine import get_or_seed_default_housing_regions
from app.engine.macro_engine import get_or_create_macro_state_for_day
from app.engine.stock_engine import get_or_seed_default_sector_stocks
from app.models.basket_price_history import BasketPriceHistory
from app.models.goods_basket import GoodsBasket
from app.models.job_definition import JOB_CATALOG
from app.models.job_definition_db import JobDefinition as JobDefinitionDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_job_definitions(db) -> None:
    """Populate job_definitions from JOB_CATALOG (idempotent)."""
    _JOB_STABILITY_MAP = {
        "auto_mechanic":    {"stability_pct": 0.80, "growth_pct": 0.55, "stress_pct": 0.40},
        "aircraft_mechanic":{"stability_pct": 0.88, "growth_pct": 0.70, "stress_pct": 0.50},
        "banker":           {"stability_pct": 0.82, "growth_pct": 0.75, "stress_pct": 0.65},
        "chef":             {"stability_pct": 0.72, "growth_pct": 0.60, "stress_pct": 0.70},
        "retail_worker":    {"stability_pct": 0.65, "growth_pct": 0.35, "stress_pct": 0.35},
        "delivery_driver":  {"stability_pct": 0.60, "growth_pct": 0.20, "stress_pct": 0.25},
        "rideshare":        {"stability_pct": 0.50, "growth_pct": 0.10, "stress_pct": 0.20},
    }
    for job_code, job in JOB_CATALOG.items():
        existing = (
            db.query(JobDefinitionDB)
            .filter(JobDefinitionDB.job_code == job_code)
            .first()
        )
        if existing:
            print(f"  JobDefinition {job_code}  already exists, skipping")
            continue
        extra = _JOB_STABILITY_MAP.get(job_code, {})
        row = JobDefinitionDB(
            job_code=job_code,
            title=job.name.replace("_", " ").title(),
            base_monthly_pay_xgp=job.monthly_salary,
            stability_pct=extra.get("stability_pct", job.stability),
            growth_pct=extra.get("growth_pct", job.growth),
            stress_pct=extra.get("stress_pct", job.physical_load),
        )
        db.add(row)
    try:
        db.commit()
        print(f"  {len(JOB_CATALOG)} job definition(s) seeded")
    except Exception:
        db.rollback()
        raise


def _seed_macro_day1(db) -> None:
    """Ensure a MacroState row exists for day 1."""
    macro = get_or_create_macro_state_for_day(db, day_number=1)
    print(f"  MacroState day=1  id={macro.id}  (inflation={macro.inflation})")


def _seed_basket_price_history_day1(db) -> None:
    """Insert a day-1 BasketPriceHistory stub for every active basket.

    These rows record the opening price index (100.0 → 100.0, 0% change) so
    chart queries always have at least one data point.
    """
    baskets: list[GoodsBasket] = db.query(GoodsBasket).filter(GoodsBasket.is_active.is_(True)).all()
    for basket in baskets:
        existing = (
            db.query(BasketPriceHistory)
            .filter(
                BasketPriceHistory.basket_id == basket.id,
                BasketPriceHistory.day_number == 1,
            )
            .first()
        )
        if existing:
            print(f"  BasketPriceHistory basket={basket.id} day=1  already exists, skipping")
            continue

        row = BasketPriceHistory(
            basket_id=basket.id,
            day_number=1,
            old_price_index=float(basket.price_index),
            new_price_index=float(basket.price_index),
            change_percent=0.0,
            inflation_used=2.0,
            oil_index_used=100.0,
            consumer_confidence_used=50.0,
            supply_chain_stress_used=0.0,
        )
        try:
            db.add(row)
            db.commit()
            print(f"  BasketPriceHistory basket={basket.id} day=1  created")
        except IntegrityError:
            db.rollback()
            print(f"  BasketPriceHistory basket={basket.id} day=1  already exists (race), skipping")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Gold Penny — database seed")
    print("=" * 60)

    db = SessionLocal()
    try:
        # 1. Goods baskets
        print("\n[1/8] Seeding GoodsBasket rows …")
        baskets = get_or_seed_default_baskets(db)
        print(f"  {len(baskets)} basket(s) ready")

        # 2. Sector stocks
        print("\n[2/8] Seeding SectorStock rows …")
        stocks = get_or_seed_default_sector_stocks(db)
        print(f"  {len(stocks)} stock(s) ready")

        # 3. Housing regions
        print("\n[3/8] Seeding HousingRegion rows …")
        regions = get_or_seed_default_housing_regions(db)
        print(f"  {len(regions)} region(s) ready")

        # 4. Business types
        print("\n[4/8] Seeding BusinessType rows …")
        btypes = get_or_seed_business_types(db)
        print(f"  {len(btypes)} business type(s) ready")

        # 5. Co-op deal templates
        print("\n[5/8] Seeding DealTemplate rows …")
        templates = get_or_seed_default_deal_templates(db)
        print(f"  {len(templates)} deal template(s) ready")

        # 6. NPC firms
        print("\n[6/8] Seeding NPC Firm rows …")
        get_or_seed_npc_firms(db, created_day=1)
        print("  NPC firms ready")

        # 7. Job definitions (feeds the FK target for player_employment_states)
        print("\n[7/8] Seeding JobDefinition rows …")
        _seed_job_definitions(db)

        # 8. MacroState day 1 + basket price history day 1
        print("\n[8/8] Seeding day-1 MacroState and BasketPriceHistory …")
        _seed_macro_day1(db)
        _seed_basket_price_history_day1(db)

    except Exception as exc:
        db.rollback()
        print(f"\nERROR: seed failed — {exc}")
        sys.exit(1)
    finally:
        db.close()

    print("\n" + "=" * 60)
    print("Seed complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
