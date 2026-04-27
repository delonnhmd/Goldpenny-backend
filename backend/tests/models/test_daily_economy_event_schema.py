"""Schema tests for DailyEconomyEvent (Phase 3-B-1, task 2).

Covers:
- Existing static-event row loads with new fields null.
- Real-world-anchored row round-trips through the ORM.
- The Phase 3-B-1 migration upgrade()/downgrade() run cleanly.
"""

from __future__ import annotations

import importlib.util
import os
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# database.py validates DATABASE_URL at import time and rejects sqlite. We
# only need Base.metadata, not a live connection — give it a syntactically
# valid postgres URL it'll never actually dial out to.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"

from app.db.database import Base
from app.models.daily_economy_event import DailyEconomyEvent


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260427_0029_realworld_event_fields.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("realworld_migration", _MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _BaseSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, future=True, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=self.engine, tables=[DailyEconomyEvent.__table__])
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()


class StaticRowBackwardCompatTests(_BaseSchemaTest):
    def test_static_row_loads_with_new_fields_null(self) -> None:
        # Insert a row that mimics what the existing static catalog produces:
        # the 3-B-1 fields are not set explicitly.
        row = DailyEconomyEvent(
            id=uuid.uuid4(),
            day=1,
            event_key="oil_spike_v1",
            headline="Refinery outage rocks gas prices",
            summary="An East Coast refinery went offline overnight.",
            event_category="energy",
            sentiment="negative",
            severity=1.5,
            source_type="generated",
        )
        self.db.add(row)
        self.db.commit()
        self.db.expire_all()

        loaded = self.db.query(DailyEconomyEvent).filter_by(day=1).one()
        self.assertFalse(loaded.is_realworld_anchored)
        self.assertIsNone(loaded.source_summary)
        self.assertIsNone(loaded.source_urls)
        self.assertIsNone(loaded.generated_at)
        self.assertIsNone(loaded.affected_sectors)
        self.assertIsNone(loaded.duration_days)
        self.assertIsNone(loaded.magnitude)


class RealWorldRowRoundTripTests(_BaseSchemaTest):
    def test_realworld_row_round_trips(self) -> None:
        generated = datetime(2026, 4, 27, 4, 0, tzinfo=timezone.utc)
        row = DailyEconomyEvent(
            id=uuid.uuid4(),
            day=42,
            event_key="realworld-2026-04-27-fuel_squeeze",
            headline="Fuel Margin Squeeze",
            summary="Oil moved +6.2% overnight; small operators feel it first.",
            event_category="energy",
            sentiment="negative",
            severity=1.4,
            source_type="generated",
            is_realworld_anchored=True,
            source_summary="WTI crude up 6.2% day-over-day per FRED DCOILWTICO.",
            source_urls=["https://fred.stlouisfed.org/series/DCOILWTICO"],
            generated_at=generated,
            affected_sectors=["energy", "transportation", "food"],
            duration_days=3,
            magnitude=0.62,
        )
        self.db.add(row)
        self.db.commit()
        self.db.expire_all()

        loaded = self.db.query(DailyEconomyEvent).filter_by(day=42).one()
        self.assertTrue(loaded.is_realworld_anchored)
        self.assertEqual(loaded.source_summary, "WTI crude up 6.2% day-over-day per FRED DCOILWTICO.")
        self.assertEqual(loaded.source_urls, ["https://fred.stlouisfed.org/series/DCOILWTICO"])
        # SQLite doesn't preserve tz; compare wallclock fields instead of full equality.
        self.assertEqual(loaded.generated_at.replace(tzinfo=None), generated.replace(tzinfo=None))
        self.assertEqual(loaded.affected_sectors, ["energy", "transportation", "food"])
        self.assertEqual(loaded.duration_days, 3)
        self.assertAlmostEqual(loaded.magnitude, 0.62)


class MigrationUpgradeDowngradeTests(unittest.TestCase):
    """Smoke-test the Phase 3-B-1 migration in isolation against a SQLite DB.

    The full alembic chain isn't runnable on SQLite (older migrations use
    Postgres-only constructs), so we stand up a minimal pre-migration
    daily_economy_events table by hand, then exercise upgrade()/downgrade()
    via Alembic's runtime Operations context.
    """

    NEW_COLUMNS = {
        "is_realworld_anchored",
        "source_summary",
        "source_urls",
        "generated_at",
        "affected_sectors",
        "duration_days",
        "magnitude",
    }

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        # Minimal pre-migration table — just enough columns that add_column /
        # drop_column have something to operate on.
        with self.engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE daily_economy_events ("
                    "id VARCHAR(36) PRIMARY KEY,"
                    "day INTEGER NOT NULL,"
                    "event_key VARCHAR(80) NOT NULL,"
                    "headline VARCHAR(300) NOT NULL,"
                    "event_category VARCHAR(40) NOT NULL,"
                    "sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral',"
                    "severity NUMERIC(6,4) NOT NULL DEFAULT 1.0,"
                    "source_type VARCHAR(30) NOT NULL DEFAULT 'generated'"
                    ")"
                )
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def _columns(self) -> set[str]:
        return {c["name"] for c in inspect(self.engine).get_columns("daily_economy_events")}

    def test_upgrade_adds_columns_and_downgrade_removes_them(self) -> None:
        migration = _load_migration_module()
        before = self._columns()
        self.assertFalse(self.NEW_COLUMNS & before, "pre-migration table should not contain new columns")

        with self.engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        after_up = self._columns()
        self.assertTrue(
            self.NEW_COLUMNS.issubset(after_up),
            f"upgrade should add all new columns, got {sorted(after_up)}",
        )

        with self.engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()
        after_down = self._columns()
        self.assertFalse(
            self.NEW_COLUMNS & after_down,
            f"downgrade should remove all new columns, got {sorted(after_down)}",
        )
        # Original columns still present.
        self.assertIn("event_key", after_down)
        self.assertIn("severity", after_down)


if __name__ == "__main__":
    unittest.main()
