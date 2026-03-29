import os
import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_event_catalog_expansion.db")

from app.db.database import Base
from app.engine.event_catalog import EVENT_CATALOG, EVENT_CATALOG_BY_KEY
from app.engine.event_service import run_daily_event_engine
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_economy_event_log import DailyEconomyEventLog
from app.models.macro_daily_state import MacroDailyState


class EventCatalogExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                MacroDailyState.__table__,
                DailyEconomyEvent.__table__,
                DailyEconomyEventLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_macro_days(self, days: int) -> None:
        for day in range(1, days + 1):
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.4") + Decimal(str(day % 5)) * Decimal("0.04"),
                    interest_rate=Decimal("4.0") + Decimal(str(day % 4)) * Decimal("0.03"),
                    unemployment_rate=Decimal("5.2") + Decimal(str(day % 3)) * Decimal("0.05"),
                    oil_index=Decimal("102.0") + Decimal(str(day % 7)) * Decimal("1.2"),
                    consumer_confidence=Decimal("53.0") - Decimal(str(day % 6)) * Decimal("0.6"),
                    supply_chain_stress=Decimal("0.6") + Decimal(str(day % 5)) * Decimal("0.04"),
                    event_headline="Catalog expansion seed",
                    event_summary="Seeded macro for event variety tests.",
                )
            )
        self.db.flush()

    def _run_sequence(self, days: int) -> list[str]:
        self._seed_macro_days(days)
        keys: list[str] = []
        for day in range(1, days + 1):
            row = run_daily_event_engine(self.db, day)
            keys.append(str(row["event_key"]))
        return keys

    def test_catalog_size_and_categories_are_expanded(self) -> None:
        self.assertGreaterEqual(len(EVENT_CATALOG), 40)
        self.assertLessEqual(len(EVENT_CATALOG), 60)
        categories = {row.category for row in EVENT_CATALOG}
        self.assertIn("energy", categories)
        self.assertIn("supply_chain", categories)
        self.assertIn("consumer", categories)
        self.assertIn("labor", categories)
        self.assertIn("financial", categories)
        self.assertIn("recovery", categories)

    def test_chain_references_remain_valid(self) -> None:
        for template in EVENT_CATALOG:
            for key in template.next_possible_events:
                self.assertIn(key, EVENT_CATALOG_BY_KEY)
            for key in template.escalation_events:
                self.assertIn(key, EVENT_CATALOG_BY_KEY)
            for key in template.recovery_events:
                self.assertIn(key, EVENT_CATALOG_BY_KEY)

    def test_multi_day_event_variety_is_deterministic_and_less_repetitive(self) -> None:
        first = self._run_sequence(45)

        # Re-run in a clean world and verify deterministic ordering.
        self.tearDown()
        self.setUp()
        second = self._run_sequence(45)

        self.assertEqual(first, second)
        self.assertGreaterEqual(len(set(first)), 15)
        for idx in range(1, len(first)):
            self.assertNotEqual(first[idx], first[idx - 1], f"Unexpected back-to-back repeat at day {idx + 1}")

        rows = self.db.query(DailyEconomyEvent).order_by(DailyEconomyEvent.day.asc()).all()
        self.assertTrue(all((row.chain_position or 0) <= 10 for row in rows))


if __name__ == "__main__":
    unittest.main()

