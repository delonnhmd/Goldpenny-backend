import os
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_basket_pricing_service.db")

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.services.basket_pricing_service import compute_daily_basket_price_updates


class BasketPricingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )

        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed_data()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_data(self) -> None:
        self.db.add_all(
            [
                MacroDailyState(
                    day=1,
                    inflation_rate=Decimal("2.2"),
                    interest_rate=Decimal("4.1"),
                    unemployment_rate=Decimal("5.0"),
                    oil_index=Decimal("100.0"),
                    consumer_confidence=Decimal("55.0"),
                    supply_chain_stress=Decimal("0.5"),
                    created_at=datetime(2026, 3, 10, 8, 0, 0),
                ),
                MacroDailyState(
                    day=2,
                    inflation_rate=Decimal("4.8"),
                    interest_rate=Decimal("5.6"),
                    unemployment_rate=Decimal("6.9"),
                    oil_index=Decimal("162.0"),
                    consumer_confidence=Decimal("39.0"),
                    supply_chain_stress=Decimal("2.1"),
                    created_at=datetime(2026, 3, 11, 8, 0, 0),
                ),
                MacroDailyState(
                    day=3,
                    inflation_rate=Decimal("1.8"),
                    interest_rate=Decimal("3.7"),
                    unemployment_rate=Decimal("4.9"),
                    oil_index=Decimal("92.0"),
                    consumer_confidence=Decimal("61.0"),
                    supply_chain_stress=Decimal("0.3"),
                    created_at=datetime(2026, 3, 12, 8, 0, 0),
                ),
            ]
        )

        self.db.add_all(
            [
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("10.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.protein,
                    price_index=Decimal("12.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.convenience,
                    price_index=Decimal("8.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
            ]
        )

    def test_supply_multiplier_below_one_creates_positive_supply_pressure(self) -> None:
        result = compute_daily_basket_price_updates(
            self.db,
            day=2,
            persist=False,
            commit=False,
        )
        produce = next(row for row in result["basket_updates"] if row["basket_key"] == "produce")
        self.assertLess(produce["supply_multiplier"], 1.0)
        self.assertGreater(produce["drivers"]["supply_component"], 0.0)
        self.assertGreater(produce["daily_change"], 0.0)

    def test_produce_moves_more_than_essentials_under_disruption(self) -> None:
        result = compute_daily_basket_price_updates(
            self.db,
            day=2,
            persist=False,
            commit=False,
        )
        essentials = next(row for row in result["basket_updates"] if row["basket_key"] == "essentials")
        produce = next(row for row in result["basket_updates"] if row["basket_key"] == "produce")
        self.assertGreater(abs(produce["daily_change"]), abs(essentials["daily_change"]))

    def test_basket_daily_change_is_capped_to_five_percent(self) -> None:
        result = compute_daily_basket_price_updates(
            self.db,
            day=2,
            persist=False,
            commit=False,
        )
        for row in result["basket_updates"]:
            self.assertGreaterEqual(row["daily_change"], -0.05)
            self.assertLessEqual(row["daily_change"], 0.05)

    def test_basket_pricing_is_deterministic_for_same_day(self) -> None:
        one = compute_daily_basket_price_updates(self.db, day=2, persist=False, commit=False)
        two = compute_daily_basket_price_updates(self.db, day=2, persist=False, commit=False)
        self.assertEqual(one, two)

    def test_persisted_rows_are_idempotent_for_same_day(self) -> None:
        first = compute_daily_basket_price_updates(self.db, day=2, persist=True, commit=True)
        second = compute_daily_basket_price_updates(self.db, day=2, persist=True, commit=True)

        count = (
            self.db.query(BasketDailyPrice)
            .filter(BasketDailyPrice.day == 2)
            .count()
        )
        self.assertEqual(count, 4)
        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])


if __name__ == "__main__":
    unittest.main()
