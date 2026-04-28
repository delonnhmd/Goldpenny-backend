"""Tests for Phase 3-B-1 cost circuit breaker scaffolding."""

from __future__ import annotations

import json
import os
import unittest
from datetime import date
from unittest.mock import patch

# Pre-set env before importing app.db.database (validator runs at import).
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ.setdefault("FRED_API_KEY", "test-key-not-real")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.game_state import GameState
from app.models.realworld_generation_cost import (
    CostBreakerAlert,
    RealWorldGenerationCost,
)
from app.services.realworld.cost_breaker import CostBreaker
from app.services.realworld.daily_generation_job import run_daily_generation


class _CountingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, today: date):  # noqa: ANN001 - protocol stand-in for this test.
        self.calls += 1
        return None


class CostBreakerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, future=True, autocommit=False, autoflush=False)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                GameState.__table__,
                DailyEconomyEvent.__table__,
                RealWorldGenerationCost.__table__,
                CostBreakerAlert.__table__,
            ],
        )
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_zero_dollar_generation_does_not_trip_breaker(self) -> None:
        breaker = CostBreaker(self.db)

        breaker.record_generation_cost("realworld-2026-04-27-fuel_margin_squeeze", 0.0)

        self.assertEqual(self.db.query(RealWorldGenerationCost).count(), 1)
        self.assertEqual(breaker.monthly_cost_per_mau(), 0.0)
        self.assertFalse(breaker.is_tripped())

    def test_cost_above_hard_threshold_trips_breaker(self) -> None:
        breaker = CostBreaker(self.db)

        breaker.record_generation_cost("realworld-2026-04-27-expensive_ai_event", 21.0)

        self.assertGreater(breaker.monthly_cost_per_mau(), 0.20)
        self.assertTrue(breaker.is_tripped())

    def test_tripped_breaker_uses_static_fallback_without_calling_rule_generator(self) -> None:
        self.db.add(GameState(current_day=100))
        CostBreaker(self.db).record_generation_cost("realworld-2026-04-27-expensive_ai_event", 21.0)
        generator = _CountingGenerator()

        def _fake_static_engine(db, day):
            row = DailyEconomyEvent(
                day=day,
                event_key="static_cost_breaker_fallback",
                headline="Static fallback",
                summary="Static catalog handled the tripped cost breaker.",
                event_category="consumer",
                sentiment="neutral",
                severity=1.0,
                impact_tags_json=json.dumps([]),
                source_type="generated",
                is_realworld_anchored=False,
            )
            db.add(row)
            db.flush()
            return {"event_key": row.event_key}

        with patch("app.engine.event_service.run_daily_event_engine", side_effect=_fake_static_engine):
            with self.assertLogs("app.services.realworld.daily_generation_job", level="ERROR") as logs:
                result = run_daily_generation(
                    date(2026, 4, 27),
                    db=self.db,
                    generator=generator,
                )

        self.assertEqual(result["source"], "static_fallback")
        self.assertEqual(result["event_id"], "static_cost_breaker_fallback")
        self.assertEqual(generator.calls, 0)
        self.assertIn("cost breaker tripped", "\n".join(logs.output))
        self.assertEqual(self.db.query(CostBreakerAlert).count(), 1)
        row = self.db.query(DailyEconomyEvent).filter_by(day=100).one()
        self.assertFalse(row.is_realworld_anchored)


if __name__ == "__main__":
    unittest.main()
