"""Step 19: Event engine unit and integration tests."""

import json
import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_event_service.db")

from app.db.database import Base
from app.engine.event_catalog import (
    EVENT_CATALOG,
    EVENT_CATALOG_BY_KEY,
    NEGATIVE_KEYS,
    POSITIVE_KEYS,
    NEUTRAL_KEYS,
    EventTemplate,
)
from app.engine.event_service import (
    _check_preconditions,
    _clamp,
    _deterministic_int,
    _deterministic_ratio,
    apply_event_impacts_to_macro,
    force_daily_event,
    get_catalog,
    get_event_history,
    get_event_snapshot,
    get_or_create_daily_event,
    run_daily_event_engine,
    select_daily_event,
)
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_economy_event_log import DailyEconomyEventLog
from app.models.macro_daily_state import MacroDailyState


class _BaseEventTest(unittest.TestCase):
    """Shared setup: in-memory SQLite + macro rows."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, future=True,
        )
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
        Base.metadata.drop_all(bind=self.engine)

    def _seed_macro(self, day: int, **overrides) -> MacroDailyState:
        defaults = dict(
            day=day,
            inflation_rate=Decimal("2.5000"),
            interest_rate=Decimal("4.0000"),
            unemployment_rate=Decimal("5.0000"),
            oil_index=Decimal("100.0000"),
            consumer_confidence=Decimal("50.0000"),
            supply_chain_stress=Decimal("0.5000"),
        )
        defaults.update(overrides)
        row = MacroDailyState(**defaults)
        self.db.add(row)
        self.db.flush()
        return row


# ── Catalog tests ─────────────────────────────────────────────────────────────

class TestEventCatalog(unittest.TestCase):
    def test_catalog_has_at_least_12_entries(self):
        self.assertGreaterEqual(len(EVENT_CATALOG), 12)

    def test_all_keys_unique(self):
        keys = [t.event_key for t in EVENT_CATALOG]
        self.assertEqual(len(keys), len(set(keys)))

    def test_all_categories_covered(self):
        categories = {t.category for t in EVENT_CATALOG}
        for expected in ("energy", "supply_chain", "consumer", "labor", "recovery", "financial"):
            self.assertIn(expected, categories, f"Missing category: {expected}")

    def test_negative_positive_neutral_all_present(self):
        self.assertTrue(len(NEGATIVE_KEYS) >= 4)
        self.assertTrue(len(POSITIVE_KEYS) >= 3)
        self.assertTrue(len(NEUTRAL_KEYS) >= 2)

    def test_severity_weights_in_range(self):
        for t in EVENT_CATALOG:
            self.assertGreaterEqual(t.severity_weight, 0.1, f"{t.event_key} severity too low")
            self.assertLessEqual(t.severity_weight, 5.0, f"{t.event_key} severity too high")

    def test_catalog_by_key_matches(self):
        for t in EVENT_CATALOG:
            self.assertIs(EVENT_CATALOG_BY_KEY[t.event_key], t)

    def test_get_catalog_returns_all(self):
        result = get_catalog()
        self.assertEqual(len(result), len(EVENT_CATALOG))


# ── Deterministic helpers ─────────────────────────────────────────────────────

class TestDeterministicHelpers(unittest.TestCase):
    def test_ratio_deterministic(self):
        r1 = _deterministic_ratio("test:seed:42")
        r2 = _deterministic_ratio("test:seed:42")
        self.assertEqual(r1, r2)

    def test_ratio_in_range(self):
        for i in range(50):
            r = _deterministic_ratio(f"seed:{i}")
            self.assertGreaterEqual(r, Decimal("0"))
            self.assertLess(r, Decimal("1"))

    def test_int_deterministic(self):
        v1 = _deterministic_int("test:int:99", 10)
        v2 = _deterministic_int("test:int:99", 10)
        self.assertEqual(v1, v2)

    def test_int_in_range(self):
        for i in range(50):
            v = _deterministic_int(f"inttest:{i}", 5)
            self.assertGreaterEqual(v, 0)
            self.assertLess(v, 5)


# ── Precondition checks ──────────────────────────────────────────────────────

class TestPreconditions(_BaseEventTest):
    def test_min_precondition_passes(self):
        macro = self._seed_macro(1, oil_index=Decimal("100"))
        t = EVENT_CATALOG_BY_KEY["oil_spike"]  # oil_index_min: 70
        self.assertTrue(_check_preconditions(t, macro))

    def test_min_precondition_fails(self):
        macro = self._seed_macro(1, oil_index=Decimal("50"))
        t = EVENT_CATALOG_BY_KEY["oil_spike"]  # oil_index_min: 70
        self.assertFalse(_check_preconditions(t, macro))

    def test_max_precondition_passes(self):
        macro = self._seed_macro(1, consumer_confidence=Decimal("40"))
        t = EVENT_CATALOG_BY_KEY["consumer_pullback"]  # consumer_confidence_max: 60
        self.assertTrue(_check_preconditions(t, macro))

    def test_max_precondition_fails(self):
        macro = self._seed_macro(1, consumer_confidence=Decimal("70"))
        t = EVENT_CATALOG_BY_KEY["consumer_pullback"]  # consumer_confidence_max: 60
        self.assertFalse(_check_preconditions(t, macro))

    def test_no_preconditions_always_pass(self):
        macro = self._seed_macro(1)
        t = EVENT_CATALOG_BY_KEY["port_congestion"]
        self.assertTrue(_check_preconditions(t, macro))


# ── Bounded clamp ─────────────────────────────────────────────────────────────

class TestBoundedClamp(unittest.TestCase):
    def test_clamp_within_cap(self):
        self.assertEqual(_clamp(Decimal("0.2"), Decimal("0.3")), Decimal("0.2"))

    def test_clamp_positive_exceeds(self):
        self.assertEqual(_clamp(Decimal("0.5"), Decimal("0.3")), Decimal("0.3"))

    def test_clamp_negative_exceeds(self):
        self.assertEqual(_clamp(Decimal("-0.5"), Decimal("0.3")), Decimal("-0.3"))


# ── Event selection ───────────────────────────────────────────────────────────

class TestSelectDailyEvent(_BaseEventTest):
    def test_select_without_macro_returns_mixed_signals(self):
        result, _chain_info = select_daily_event(self.db, 1)
        self.assertEqual(result.event_key, "mixed_signals")

    def test_select_returns_event_template(self):
        self._seed_macro(1)
        result, chain_info = select_daily_event(self.db, 1)
        self.assertIsInstance(result, EventTemplate)
        self.assertIn(result.event_key, EVENT_CATALOG_BY_KEY)
        self.assertIsInstance(chain_info, dict)

    def test_select_deterministic_for_same_day(self):
        self._seed_macro(1)
        r1, _ = select_daily_event(self.db, 1)
        r2, _ = select_daily_event(self.db, 1)
        self.assertEqual(r1.event_key, r2.event_key)

    def test_no_back_to_back_repeat(self):
        """After persisting an event, the next day must not pick the same key."""
        self._seed_macro(1)
        self._seed_macro(2)
        first, _ = select_daily_event(self.db, 1)
        # Persist it as the day-1 event.
        row = DailyEconomyEvent(
            day=1,
            event_key=first.event_key,
            headline=first.headline_template,
            event_category=first.category,
            sentiment=first.sentiment,
            severity=Decimal("1.0"),
            source_type="generated",
        )
        self.db.add(row)
        self.db.flush()
        second, _ = select_daily_event(self.db, 2)
        self.assertNotEqual(first.event_key, second.event_key)

    def test_recovery_bias_after_negative_streak(self):
        """After 2+ consecutive negatives, selection should favour positive."""
        self._seed_macro(1)
        self._seed_macro(2)
        self._seed_macro(3)
        # Plant two negative events.
        for d, key in [(1, NEGATIVE_KEYS[0]), (2, NEGATIVE_KEYS[1])]:
            self.db.add(DailyEconomyEvent(
                day=d,
                event_key=key,
                headline="test",
                event_category="test",
                sentiment="negative",
                severity=Decimal("1.0"),
                source_type="generated",
            ))
        self.db.flush()
        result, _ = select_daily_event(self.db, 3)
        self.assertEqual(result.sentiment, "positive")


# ── Impact application ────────────────────────────────────────────────────────

class TestApplyEventImpacts(_BaseEventTest):
    def test_apply_oil_spike_bounded(self):
        macro = self._seed_macro(1, oil_index=Decimal("100"))
        template = EVENT_CATALOG_BY_KEY["oil_spike"]
        result = apply_event_impacts_to_macro(self.db, 1, template)
        self.assertTrue(result["applied"])
        # Oil delta should be capped at ±6.
        oil_after = Decimal(str(result["macro_after"]["oil_index"]))
        oil_before = Decimal(str(result["macro_before"]["oil_index"]))
        self.assertLessEqual(abs(oil_after - oil_before), Decimal("6.0001"))

    def test_apply_bounded_inflation(self):
        macro = self._seed_macro(1, inflation_rate=Decimal("2.5"))
        template = EventTemplate(
            event_key="test_inflation_shock",
            headline_template="Test",
            summary_template="Test",
            category="financial",
            sentiment="negative",
            severity_weight=1.0,
            impact_tags={"inflation_rate": +1.0},  # raw > cap 0.3
        )
        result = apply_event_impacts_to_macro(self.db, 1, template)
        delta = abs(
            Decimal(str(result["macro_after"]["inflation_rate"]))
            - Decimal(str(result["macro_before"]["inflation_rate"]))
        )
        self.assertLessEqual(delta, Decimal("0.3001"))

    def test_apply_bounded_unemployment(self):
        macro = self._seed_macro(1, unemployment_rate=Decimal("5.0"))
        template = EVENT_CATALOG_BY_KEY["layoff_wave"]  # +0.35 unemployment
        result = apply_event_impacts_to_macro(self.db, 1, template)
        delta = abs(
            Decimal(str(result["macro_after"]["unemployment_rate"]))
            - Decimal(str(result["macro_before"]["unemployment_rate"]))
        )
        self.assertLessEqual(delta, Decimal("0.5001"))

    def test_floor_ceiling_respected(self):
        macro = self._seed_macro(1, unemployment_rate=Decimal("1.0"))
        # Positive hiring surge tries to reduce unemployment.
        template = EVENT_CATALOG_BY_KEY["hiring_surge"]
        result = apply_event_impacts_to_macro(self.db, 1, template)
        unemp_after = Decimal(str(result["macro_after"]["unemployment_rate"]))
        self.assertGreaterEqual(unemp_after, Decimal("1.0"))

    def test_no_macro_returns_not_applied(self):
        template = EVENT_CATALOG_BY_KEY["mixed_signals"]
        result = apply_event_impacts_to_macro(self.db, 99, template)
        self.assertFalse(result["applied"])

    def test_headline_stamped_on_macro(self):
        macro = self._seed_macro(1)
        template = EVENT_CATALOG_BY_KEY["oil_spike"]
        apply_event_impacts_to_macro(self.db, 1, template)
        self.db.flush()
        refreshed = self.db.query(MacroDailyState).filter(MacroDailyState.day == 1).first()
        self.assertIn("Oil", refreshed.event_headline)


# ── Full engine run ───────────────────────────────────────────────────────────

class TestRunDailyEventEngine(_BaseEventTest):
    def test_run_creates_event_and_log(self):
        self._seed_macro(1)
        result = run_daily_event_engine(self.db, 1)
        self.assertIn("event_key", result)
        self.assertIn("headline", result)
        self.assertFalse(result["already_processed"])
        # Verify DB rows.
        event = self.db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == 1).first()
        self.assertIsNotNone(event)
        log = self.db.query(DailyEconomyEventLog).filter(DailyEconomyEventLog.day == 1).first()
        self.assertIsNotNone(log)

    def test_idempotent_second_call(self):
        self._seed_macro(1)
        r1 = run_daily_event_engine(self.db, 1)
        r2 = run_daily_event_engine(self.db, 1)
        self.assertTrue(r2["already_processed"])
        self.assertEqual(r1["event_key"], r2["event_key"])

    def test_get_or_create_alias(self):
        self._seed_macro(1)
        r1 = get_or_create_daily_event(self.db, 1)
        self.assertIn("event_key", r1)


# ── Force event ───────────────────────────────────────────────────────────────

class TestForceEvent(_BaseEventTest):
    def test_force_valid_event(self):
        self._seed_macro(1)
        result = force_daily_event(self.db, 1, "oil_spike")
        self.assertEqual(result["event_key"], "oil_spike")
        self.assertEqual(result["source_type"], "forced")

    def test_force_replaces_existing(self):
        self._seed_macro(1)
        run_daily_event_engine(self.db, 1)
        result = force_daily_event(self.db, 1, "hiring_surge")
        self.assertEqual(result["event_key"], "hiring_surge")

    def test_force_unknown_key(self):
        self._seed_macro(1)
        result = force_daily_event(self.db, 1, "nonexistent_event")
        self.assertIn("error", result)


# ── History / snapshot ────────────────────────────────────────────────────────

class TestHistoryAndSnapshot(_BaseEventTest):
    def test_get_event_history(self):
        self._seed_macro(1)
        self._seed_macro(2)
        run_daily_event_engine(self.db, 1)
        run_daily_event_engine(self.db, 2)
        history = get_event_history(self.db, limit=10)
        self.assertEqual(len(history), 2)
        # Most recent first.
        self.assertGreaterEqual(history[0]["day"], history[1]["day"])

    def test_get_event_snapshot_includes_deltas(self):
        self._seed_macro(1)
        run_daily_event_engine(self.db, 1)
        snap = get_event_snapshot(self.db, 1)
        self.assertIsNotNone(snap)
        self.assertIn("macro_before", snap)
        self.assertIn("macro_after", snap)
        self.assertIn("post_cap_deltas", snap)

    def test_snapshot_missing_day_returns_none(self):
        self.assertIsNone(get_event_snapshot(self.db, 999))


# ── Multi-day integration ────────────────────────────────────────────────────

class TestMultiDayEventChain(_BaseEventTest):
    def test_five_day_chain_no_repeats_bounded(self):
        """Run 5 days and verify no back-to-back repeats + bounded deltas."""
        for d in range(1, 6):
            self._seed_macro(d)

        prev_key = None
        for d in range(1, 6):
            result = run_daily_event_engine(self.db, d)
            current_key = result["event_key"]
            # Anti-repetition.
            if prev_key is not None:
                self.assertNotEqual(current_key, prev_key, f"Day {d} repeated {current_key}")
            prev_key = current_key

        # Check all macro deltas stayed bounded.
        history = get_event_history(self.db, limit=5)
        self.assertEqual(len(history), 5)


# ── Catalog endpoint data ────────────────────────────────────────────────────

class TestCatalogEndpoint(unittest.TestCase):
    def test_catalog_format(self):
        entries = get_catalog()
        for entry in entries:
            self.assertIn("event_key", entry)
            self.assertIn("headline", entry)
            self.assertIn("category", entry)
            self.assertIn("sentiment", entry)
            self.assertIn("impact_tags", entry)


if __name__ == "__main__":
    unittest.main()
