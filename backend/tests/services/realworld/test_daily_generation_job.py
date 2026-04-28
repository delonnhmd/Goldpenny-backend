"""Tests for the daily real-world generation cron (Phase 3-B-1, task 4).

Five scenarios per spec:
- Happy path: rule generator returns an event, row lands with new fields populated.
- Idempotency: run twice, exactly one row exists.
- Fallback one: rule returns None, yesterday's row exists, today gets the
  "Quiet Day —" prefix and the boilerplate summary.
- Fallback two: rule returns None and yesterday is empty, the static catalog
  is invoked. (Mocked at the import-site of run_daily_event_engine to avoid
  pulling the full engine fixture chain.)
- Logging: ``source`` is recorded on each run.
"""

from __future__ import annotations

import json
import logging
import os
import unittest
from datetime import date, datetime, timezone
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
from app.services.realworld.daily_generation_job import run_daily_generation
from app.services.realworld.rule_generator import RULE_TO_CATEGORY, RealWorldEvent


_FIXED_CLOCK = datetime(2026, 4, 27, 4, 0, 0, tzinfo=timezone.utc)


def _make_event(rule_slug: str = "fuel_margin_squeeze") -> RealWorldEvent:
    return RealWorldEvent(
        event_id=f"realworld-2026-04-27-{rule_slug}",
        generated_at=_FIXED_CLOCK,
        source_summary="FRED DCOILWTICO moved +8.0% DoD (2026-04-25 → 2026-04-26).",
        source_urls=["https://fred.stlouisfed.org/series/DCOILWTICO"],
        event_name="Fuel Margin Squeeze",
        narrative="Oil moved +8.0% overnight; small operators feel it first.",
        affected_sectors=["energy", "transportation", "food"],
        magnitude=0.5,
        duration_days=3,
        severity=1.3,
        tone="negative",
    )


class _StubGenerator:
    """Stand-in for RuleBasedEventGenerator in tests."""

    def __init__(self, event: RealWorldEvent | None) -> None:
        self._event = event
        self.calls: list[date] = []

    def generate(self, today: date) -> RealWorldEvent | None:
        self.calls.append(today)
        return self._event


class _BaseJobTest(unittest.TestCase):
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
        # Fix the global game day at 100; cron runs always target this slot.
        self.db.add(GameState(current_day=100))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()


# ---------------------------------------------------------------------------
# Tier 1: rule generator wins.
# ---------------------------------------------------------------------------


class HappyPathTests(_BaseJobTest):
    def test_rule_event_lands_with_all_new_fields_populated(self) -> None:
        gen = _StubGenerator(_make_event())
        result = run_daily_generation(date(2026, 4, 27), db=self.db, generator=gen)

        self.assertEqual(result["source"], "rule")
        self.assertEqual(result["event_id"], "realworld-2026-04-27-fuel_margin_squeeze")
        self.assertEqual(result["target_date"], "2026-04-27")
        self.assertIn("duration_ms", result)

        rows = self.db.query(DailyEconomyEvent).all()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.day, 100)
        self.assertTrue(row.is_realworld_anchored)
        self.assertEqual(row.headline, "Fuel Margin Squeeze")
        self.assertEqual(row.summary, "Oil moved +8.0% overnight; small operators feel it first.")
        self.assertEqual(row.event_category, "energy")
        self.assertEqual(row.sentiment, "negative")
        self.assertEqual(float(row.severity), 1.3)
        self.assertEqual(row.source_summary, "FRED DCOILWTICO moved +8.0% DoD (2026-04-25 → 2026-04-26).")
        self.assertEqual(row.source_urls, ["https://fred.stlouisfed.org/series/DCOILWTICO"])
        self.assertEqual(row.affected_sectors, ["energy", "transportation", "food"])
        self.assertEqual(row.duration_days, 3)
        self.assertAlmostEqual(row.magnitude, 0.5)
        # impact_tags_json is built from affected_sectors + magnitude + tone direction.
        tags = json.loads(row.impact_tags_json)
        self.assertEqual(len(tags), 3)
        self.assertEqual({t["tag"] for t in tags}, {"energy", "transportation", "food"})
        self.assertTrue(all(t["direction"] == "down" for t in tags))   # negative → down
        self.assertTrue(all(t["magnitude"] == 0.5 for t in tags))

    def test_each_rule_slug_persists_registered_static_catalog_category(self) -> None:
        for offset, (rule_slug, expected_category) in enumerate(RULE_TO_CATEGORY.items()):
            with self.subTest(rule_slug=rule_slug):
                self.db.query(DailyEconomyEvent).delete()
                self.db.query(GameState).delete()
                self.db.add(GameState(current_day=100 + offset))
                self.db.commit()

                run_daily_generation(
                    date(2026, 4, 27),
                    db=self.db,
                    generator=_StubGenerator(_make_event(rule_slug)),
                )

                row = self.db.query(DailyEconomyEvent).filter_by(day=100 + offset).one()
                self.assertEqual(row.event_category, expected_category)

    def test_unmapped_rule_slug_fails_loudly_on_persistence(self) -> None:
        with self.assertRaisesRegex(ValueError, "has no event-category mapping"):
            run_daily_generation(
                date(2026, 4, 27),
                db=self.db,
                generator=_StubGenerator(_make_event("synthetic_unmapped_rule")),
            )
        self.assertEqual(self.db.query(DailyEconomyEvent).count(), 0)


# ---------------------------------------------------------------------------
# Idempotency.
# ---------------------------------------------------------------------------


class IdempotencyTests(_BaseJobTest):
    def test_running_twice_creates_only_one_row(self) -> None:
        gen = _StubGenerator(_make_event())
        first = run_daily_generation(date(2026, 4, 27), db=self.db, generator=gen)
        second = run_daily_generation(date(2026, 4, 27), db=self.db, generator=gen)

        self.assertEqual(first["source"], "rule")
        self.assertEqual(second["source"], "skipped_idempotent")
        self.assertEqual(self.db.query(DailyEconomyEvent).count(), 1)
        # Generator was only invoked on the first run.
        self.assertEqual(len(gen.calls), 1)


# ---------------------------------------------------------------------------
# Tier 2: yesterday fallback.
# ---------------------------------------------------------------------------


class YesterdayFallbackTests(_BaseJobTest):
    def test_yesterday_realworld_row_is_carried_forward_with_quiet_day_prefix(self) -> None:
        # Seed yesterday (day=99) with a real-world-anchored row.
        yesterday = DailyEconomyEvent(
            day=99,
            event_key="realworld-2026-04-26-fuel_margin_squeeze",
            headline="Fuel Margin Squeeze",
            summary="Yesterday's narrative.",
            event_category="energy",
            sentiment="negative",
            severity=1.3,
            impact_tags_json=json.dumps([{"tag": "energy", "direction": "down", "magnitude": 0.5}]),
            source_type="generated",
            is_realworld_anchored=True,
            source_summary="Yesterday's source summary.",
            source_urls=["https://fred.stlouisfed.org/series/DCOILWTICO"],
            generated_at=_FIXED_CLOCK,
            affected_sectors=["energy", "transportation"],
            duration_days=3,
            magnitude=0.5,
        )
        self.db.add(yesterday)
        self.db.commit()

        result = run_daily_generation(
            date(2026, 4, 27), db=self.db, generator=_StubGenerator(None)
        )
        self.assertEqual(result["source"], "yesterday_fallback")

        today = self.db.query(DailyEconomyEvent).filter_by(day=100).one()
        self.assertTrue(today.is_realworld_anchored)
        self.assertEqual(today.headline, "Quiet Day — Fuel Margin Squeeze")
        self.assertEqual(
            today.summary,
            "The world is quiet today; yesterday's pressure is still working through your city.",
        )
        # Carried-over metadata.
        self.assertEqual(today.source_urls, ["https://fred.stlouisfed.org/series/DCOILWTICO"])
        self.assertEqual(today.affected_sectors, ["energy", "transportation"])
        self.assertAlmostEqual(today.magnitude, 0.5)


# ---------------------------------------------------------------------------
# Tier 3: static catalog fallback.
# ---------------------------------------------------------------------------


class StaticFallbackTests(_BaseJobTest):
    def test_static_catalog_invoked_when_rule_and_yesterday_are_empty(self) -> None:
        # We don't want to drag the full event_engine fixture chain into this
        # unit test — patch run_daily_event_engine at its import site inside
        # the fallback path to simulate the static catalog producing a row.
        def _fake_static_engine(db, day):
            row = DailyEconomyEvent(
                day=day,
                event_key="static_oil_crisis_v1",
                headline="Refinery outage",
                summary="An East Coast refinery went offline overnight.",
                event_category="energy",
                sentiment="negative",
                severity=1.4,
                impact_tags_json=json.dumps([]),
                source_type="generated",
                is_realworld_anchored=False,
            )
            db.add(row)
            db.flush()
            return {"event_key": row.event_key}

        with patch("app.engine.event_service.run_daily_event_engine", side_effect=_fake_static_engine):
            result = run_daily_generation(
                date(2026, 4, 27), db=self.db, generator=_StubGenerator(None)
            )

        self.assertEqual(result["source"], "static_fallback")
        self.assertEqual(result["event_id"], "static_oil_crisis_v1")
        row = self.db.query(DailyEconomyEvent).filter_by(day=100).one()
        self.assertFalse(row.is_realworld_anchored)
        self.assertEqual(row.event_key, "static_oil_crisis_v1")

    def test_static_catalog_failure_is_logged_critical_not_raised(self) -> None:
        with patch(
            "app.engine.event_service.run_daily_event_engine",
            side_effect=RuntimeError("catalog blew up"),
        ):
            result = run_daily_generation(
                date(2026, 4, 27), db=self.db, generator=_StubGenerator(None)
            )
        self.assertEqual(result["source"], "error_static_failed")
        self.assertEqual(self.db.query(DailyEconomyEvent).count(), 0)


# ---------------------------------------------------------------------------
# Logging.
# ---------------------------------------------------------------------------


class LoggingTests(_BaseJobTest):
    def test_source_is_logged_on_every_run(self) -> None:
        gen = _StubGenerator(_make_event())
        with self.assertLogs("app.services.realworld.daily_generation_job", level="INFO") as cap:
            result = run_daily_generation(date(2026, 4, 27), db=self.db, generator=gen)
        self.assertEqual(result["source"], "rule")
        joined = "\n".join(cap.output)
        self.assertIn("source=rule", joined)
        self.assertIn("target_date=2026-04-27", joined)
        self.assertIn("event_id=realworld-2026-04-27-fuel_margin_squeeze", joined)
        self.assertIn("duration_ms=", joined)

    def test_no_gamestate_logs_error_and_returns_sentinel(self) -> None:
        # Wipe GameState so the job has nowhere to anchor.
        self.db.query(GameState).delete()
        self.db.commit()

        with self.assertLogs("app.services.realworld.daily_generation_job", level="ERROR"):
            result = run_daily_generation(
                date(2026, 4, 27), db=self.db, generator=_StubGenerator(_make_event())
            )
        self.assertEqual(result["source"], "error_no_gamestate")
        self.assertEqual(self.db.query(DailyEconomyEvent).count(), 0)


if __name__ == "__main__":
    unittest.main()
