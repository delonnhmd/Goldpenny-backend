"""API tests for real-world operator visibility endpoints."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone

# Pre-set env before importing app.db.database (validator runs at import).
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ["INTERNAL_API_KEY"] = "test-internal-key"
os.environ.setdefault("FRED_API_KEY", "test-key-not-real")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin_realworld
from app.db.database import Base, get_db
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.game_state import GameState
from app.models.realworld_generation_cost import CostBreakerAlert, RealWorldGenerationCost


class AdminRealworldTodayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
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
        self.app = FastAPI()
        self.app.include_router(admin_realworld.router, prefix="/admin")

        def _override_db():
            try:
                yield self.db
            finally:
                pass

        self.app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_today_returns_expected_fields_when_event_exists(self) -> None:
        self.db.add(GameState(current_day=100))
        generated_at = datetime(2026, 4, 27, 4, 0, 0, tzinfo=timezone.utc)
        yesterday = DailyEconomyEvent(
            day=99,
            event_key="realworld-2026-04-26-quiet",
            headline="Quiet Day - Fuel Margin Squeeze",
            summary="Yesterday's pressure is still working through the city.",
            event_category="energy",
            sentiment="negative",
            severity=1.3,
            impact_tags_json=json.dumps([]),
            source_type="generated",
            is_realworld_anchored=True,
            source_summary="Yesterday source.",
            source_urls=["https://fred.stlouisfed.org/series/DCOILWTICO"],
            generated_at=generated_at,
            affected_sectors=["energy"],
            duration_days=3,
            magnitude=0.5,
        )
        today = DailyEconomyEvent(
            day=100,
            event_key="realworld-2026-04-27-fuel_margin_squeeze",
            headline="Fuel Margin Squeeze",
            summary="Oil moved +8.0% overnight; small operators feel it first.",
            event_category="energy",
            sentiment="negative",
            severity=1.3,
            impact_tags_json=json.dumps(
                [{"tag": "energy", "direction": "down", "magnitude": 0.5}]
            ),
            source_type="generated",
            is_realworld_anchored=True,
            source_summary="FRED DCOILWTICO moved +8.0% DoD.",
            source_urls=["https://fred.stlouisfed.org/series/DCOILWTICO"],
            generated_at=generated_at,
            affected_sectors=["energy", "transportation", "food"],
            duration_days=3,
            magnitude=0.5,
        )
        self.db.add_all([yesterday, today])
        self.db.commit()

        response = self.client.get(
            "/admin/realworld/today",
            headers={"X-Internal-Key": "test-internal-key"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["current_day"], 100)
        self.assertEqual(payload["today_event"]["event_key"], today.event_key)
        self.assertEqual(payload["today_event"]["headline"], "Fuel Margin Squeeze")
        self.assertEqual(payload["today_event"]["source_urls"], today.source_urls)
        self.assertEqual(payload["yesterday_event"]["event_key"], yesterday.event_key)
        self.assertEqual(payload["breaker"]["hard_breaker_threshold"], 0.2)
        self.assertFalse(payload["breaker"]["is_tripped"])
        self.assertGreaterEqual(len(payload["recent_generation_logs"]), 2)
        self.assertEqual(payload["recent_generation_logs"][0]["source"], "rule")

    def test_today_returns_empty_state_when_no_event_exists(self) -> None:
        self.db.add(GameState(current_day=100))
        self.db.commit()

        response = self.client.get(
            "/admin/realworld/today",
            headers={"X-Internal-Key": "test-internal-key"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["current_day"], 100)
        self.assertIsNone(payload["today_event"])
        self.assertIsNone(payload["yesterday_event"])
        self.assertEqual(payload["recent_generation_logs"], [])
        self.assertIn("monthly_cost_per_mau", payload["breaker"])

    def test_today_requires_internal_key(self) -> None:
        response = self.client.get("/admin/realworld/today")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Invalid internal API key.")


if __name__ == "__main__":
    unittest.main()
