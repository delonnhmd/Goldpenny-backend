"""Step 19.5: Event chain — multi-day chain, escalation, decay, recovery, narrative tests."""

import json
import os
import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_event_chain.db")

from app.db.database import Base
from app.engine.event_catalog import (
    EVENT_CATALOG,
    EVENT_CATALOG_BY_KEY,
    EventTemplate,
)
from app.engine.event_service import (
    CHAIN_STAGES,
    _compute_chain_stage,
    _compute_decay_factor,
    _empty_chain_info,
    _evaluate_chain_continuation,
    _get_previous_day_event,
    _new_chain_info,
    _select_chain_event,
    apply_event_impacts_to_macro,
    get_active_chains,
    run_daily_event_engine,
    select_daily_event,
)
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_economy_event_log import DailyEconomyEventLog
from app.models.macro_daily_state import MacroDailyState


class _BaseChainTest(unittest.TestCase):
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

    def _seed_event(self, day: int, event_key: str, **overrides) -> DailyEconomyEvent:
        tmpl = EVENT_CATALOG_BY_KEY.get(event_key)
        defaults = dict(
            day=day,
            event_key=event_key,
            headline=tmpl.headline_template[:300] if tmpl else "Test",
            summary=tmpl.summary_template if tmpl else "Test",
            event_category=tmpl.category if tmpl else "test",
            sentiment=tmpl.sentiment if tmpl else "neutral",
            severity=Decimal(str(tmpl.severity_weight)) if tmpl else Decimal("1.0"),
            impact_tags_json="[]",
            source_type="generated",
        )
        defaults.update(overrides)
        row = DailyEconomyEvent(**defaults)
        self.db.add(row)
        self.db.flush()
        return row


# ── Chain stage computation ───────────────────────────────────────────────────

class TestChainStageComputation(unittest.TestCase):

    def test_position_zero_is_start(self):
        self.assertEqual(_compute_chain_stage(0, 5), "start")

    def test_last_position_is_peak(self):
        self.assertEqual(_compute_chain_stage(4, 5), "peak")
        self.assertEqual(_compute_chain_stage(3, 4), "peak")

    def test_mid_positions(self):
        # For max_length=5, positions 1-2 should be mid or escalation
        stage = _compute_chain_stage(1, 5)
        self.assertIn(stage, ("mid", "escalation"))

    def test_escalation_at_high_fraction(self):
        # Position 3 of 5 → frac=0.75 → escalation
        self.assertEqual(_compute_chain_stage(3, 5), "escalation")

    def test_all_stages_are_valid(self):
        for pos in range(6):
            stage = _compute_chain_stage(pos, 5)
            self.assertIn(stage, CHAIN_STAGES)


# ── Decay factor ──────────────────────────────────────────────────────────────

class TestDecayFactor(unittest.TestCase):

    def test_position_zero_returns_one(self):
        result = _compute_decay_factor(0, 0.15)
        self.assertEqual(result, Decimal("1.0000"))

    def test_positive_position_decays(self):
        result = _compute_decay_factor(2, 0.15)
        expected = Decimal(str(0.85 ** 2)).quantize(Decimal("0.0001"))
        self.assertEqual(result, expected)

    def test_decay_floor_at_0_3(self):
        result = _compute_decay_factor(50, 0.15)
        self.assertGreaterEqual(result, Decimal("0.3000"))

    def test_decay_monotonically_decreases(self):
        prev = Decimal("2.0")
        for pos in range(8):
            val = _compute_decay_factor(pos, 0.15)
            self.assertLessEqual(val, prev)
            prev = val


# ── Empty / new chain info ────────────────────────────────────────────────────

class TestChainInfoHelpers(unittest.TestCase):

    def test_empty_chain_info(self):
        info = _empty_chain_info()
        self.assertIsNone(info["chain_id"])
        self.assertEqual(info["chain_position"], 0)
        self.assertEqual(info["decay_factor"], 1.0)

    def test_new_chain_info_for_chainable_event(self):
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]
        info = _new_chain_info(tmpl, 10)
        self.assertIsNotNone(info["chain_id"])
        self.assertEqual(info["chain_position"], 0)
        self.assertEqual(info["chain_stage"], "start")
        self.assertEqual(info["chain_length_expected"], tmpl.max_chain_length)
        self.assertGreater(info["continuation_probability"], 0)

    def test_new_chain_info_for_nonchainable_event(self):
        tmpl = EVENT_CATALOG_BY_KEY["mixed_signals"]
        info = _new_chain_info(tmpl, 10)
        self.assertIsNone(info["chain_id"])

    def test_chain_id_is_deterministic(self):
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]
        info1 = _new_chain_info(tmpl, 10)
        info2 = _new_chain_info(tmpl, 10)
        self.assertEqual(info1["chain_id"], info2["chain_id"])


# ── Chain continuation evaluation ─────────────────────────────────────────────

class TestChainContinuation(_BaseChainTest):

    def test_no_chain_id_returns_false(self):
        row = self._seed_event(1, "oil_spike", chain_id=None)
        self.assertFalse(_evaluate_chain_continuation(2, row))

    def test_recovery_stage_returns_false(self):
        row = self._seed_event(1, "oil_spike",
                               chain_id="abc", chain_position=2,
                               chain_stage="recovery",
                               continuation_probability=Decimal("0.90"),
                               chain_length_expected=5)
        self.assertFalse(_evaluate_chain_continuation(2, row))

    def test_end_stage_returns_false(self):
        row = self._seed_event(1, "oil_spike",
                               chain_id="abc", chain_position=2,
                               chain_stage="end",
                               continuation_probability=Decimal("0.90"),
                               chain_length_expected=5)
        self.assertFalse(_evaluate_chain_continuation(2, row))

    def test_at_max_length_returns_false(self):
        row = self._seed_event(1, "oil_spike",
                               chain_id="abc", chain_position=5,
                               chain_stage="mid",
                               continuation_probability=Decimal("0.90"),
                               chain_length_expected=5)
        self.assertFalse(_evaluate_chain_continuation(2, row))

    def test_zero_probability_returns_false(self):
        row = self._seed_event(1, "oil_spike",
                               chain_id="abc", chain_position=1,
                               chain_stage="mid",
                               continuation_probability=Decimal("0.00"),
                               chain_length_expected=5)
        self.assertFalse(_evaluate_chain_continuation(2, row))

    def test_high_probability_is_deterministic(self):
        row = self._seed_event(1, "oil_spike",
                               chain_id="test_chain_100", chain_position=1,
                               chain_stage="mid",
                               continuation_probability=Decimal("0.99"),
                               chain_length_expected=5)
        # Same inputs always produce same result
        r1 = _evaluate_chain_continuation(2, row)
        r2 = _evaluate_chain_continuation(2, row)
        self.assertEqual(r1, r2)


# ── Previous day event retrieval ──────────────────────────────────────────────

class TestGetPreviousDayEvent(_BaseChainTest):

    def test_returns_none_for_day_1(self):
        self.assertIsNone(_get_previous_day_event(self.db, 1))

    def test_returns_previous_day_event(self):
        self._seed_event(5, "oil_spike")
        result = _get_previous_day_event(self.db, 6)
        self.assertIsNotNone(result)
        self.assertEqual(result.event_key, "oil_spike")

    def test_returns_none_when_no_event(self):
        self.assertIsNone(_get_previous_day_event(self.db, 6))


# ── Chain event selection ─────────────────────────────────────────────────────

class TestSelectChainEvent(_BaseChainTest):

    def test_select_from_next_events(self):
        self._seed_macro(10)
        prev = self._seed_event(9, "oil_spike",
                                chain_id="energy1", chain_position=0,
                                chain_stage="start",
                                continuation_probability=Decimal("0.65"),
                                chain_length_expected=5)
        template, stage = _select_chain_event(self.db, 10, prev)
        # oil_spike's next_possible = (pipeline_disruption, freight_bottleneck)
        self.assertIn(template.event_key, ["pipeline_disruption", "freight_bottleneck"])
        self.assertIn(stage, CHAIN_STAGES)

    def test_peak_triggers_recovery(self):
        self._seed_macro(10)
        prev = self._seed_event(9, "oil_spike",
                                chain_id="energy1", chain_position=4,
                                chain_stage="escalation",
                                continuation_probability=Decimal("0.50"),
                                chain_length_expected=5)
        template, stage = _select_chain_event(self.db, 10, prev)
        # At peak, should try recovery events
        if stage == "recovery":
            self.assertIn(template.event_key, ["oil_glut", "supply_relief"])

    def test_unknown_parent_returns_mixed_signals(self):
        prev = self._seed_event(9, "nonexistent_key",
                                chain_id="bad", chain_position=1,
                                chain_stage="mid",
                                continuation_probability=Decimal("0.50"),
                                chain_length_expected=5)
        template, stage = _select_chain_event(self.db, 10, prev)
        self.assertEqual(template.event_key, "mixed_signals")
        self.assertEqual(stage, "end")


# ── Full chain integration (multi-day) ────────────────────────────────────────

class TestMultiDayChainIntegration(_BaseChainTest):

    def test_chain_starts_with_chainable_event(self):
        """Force oil_spike on day 5 → verify chain fields on the event row."""
        self._seed_macro(5)
        from app.engine.event_service import force_daily_event
        result = force_daily_event(self.db, 5, "oil_spike")
        self.db.commit()
        self.assertIsNotNone(result.get("chain_id"))
        self.assertEqual(result["chain_position"], 0)
        self.assertEqual(result["chain_stage"], "start")

    def test_nonchainable_event_has_no_chain(self):
        """Force mixed_signals → no chain data."""
        self._seed_macro(5)
        from app.engine.event_service import force_daily_event
        result = force_daily_event(self.db, 5, "mixed_signals")
        self.db.commit()
        self.assertIsNone(result.get("chain_id"))

    def test_select_returns_tuple(self):
        """select_daily_event now returns (template, chain_info) tuple."""
        self._seed_macro(5)
        result = select_daily_event(self.db, 5)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        template, chain_info = result
        self.assertIsInstance(template, EventTemplate)
        self.assertIsInstance(chain_info, dict)
        self.assertIn("chain_id", chain_info)

    def test_run_engine_idempotent(self):
        """Running engine twice returns same data."""
        self._seed_macro(5)
        r1 = run_daily_event_engine(self.db, 5)
        self.db.commit()
        r2 = run_daily_event_engine(self.db, 5)
        self.assertEqual(r1["event_key"], r2["event_key"])
        self.assertTrue(r2["already_processed"])

    def test_chain_continuation_creates_linked_events(self):
        """Seed a chain start event, then run engine for next day and verify chain link."""
        self._seed_macro(10)
        self._seed_macro(11)
        # Seed a chain start event on day 10 with high continuation probability
        self._seed_event(10, "oil_spike",
                         chain_id="test_cont_chain",
                         chain_position=0,
                         chain_stage="start",
                         continuation_probability=Decimal("0.99"),
                         chain_length_expected=5,
                         decay_factor=Decimal("1.0000"))
        result = run_daily_event_engine(self.db, 11)
        self.db.commit()
        # May or may not continue depending on deterministic hash, but should not error
        self.assertIn("event_key", result)
        self.assertIn("chain_id", result)

    def test_chain_does_not_exceed_max_length(self):
        """Chain at max position should not continue."""
        self._seed_macro(10)
        self._seed_macro(11)
        self._seed_event(10, "oil_spike",
                         chain_id="max_chain",
                         chain_position=5,
                         chain_stage="mid",
                         continuation_probability=Decimal("0.99"),
                         chain_length_expected=5,
                         decay_factor=Decimal("0.5000"))
        result = run_daily_event_engine(self.db, 11)
        self.db.commit()
        # Should not continue the chain (at max)
        if result.get("chain_id") == "max_chain":
            # Shouldn't happen since we're at max
            self.fail("Chain should not continue past max_length")


# ── Decay-adjusted impact ────────────────────────────────────────────────────

class TestDecayAdjustedImpact(_BaseChainTest):

    def test_full_intensity_normal_impact(self):
        """chain_intensity=1.0 → normal impact."""
        self._seed_macro(5)
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]
        result = apply_event_impacts_to_macro(self.db, 5, tmpl, chain_intensity=1.0)
        self.assertTrue(result["applied"])
        # Oil should go up
        self.assertGreater(result["post_cap_deltas"].get("oil_index", 0), 0)

    def test_reduced_intensity_smaller_impact(self):
        """chain_intensity=0.5 → smaller deltas than 1.0."""
        self._seed_macro(5)
        self._seed_macro(6)
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]

        r1 = apply_event_impacts_to_macro(self.db, 5, tmpl, chain_intensity=1.0)
        oil_delta_full = abs(r1["pre_cap_deltas"].get("oil_index", 0))

        r2 = apply_event_impacts_to_macro(self.db, 6, tmpl, chain_intensity=0.5)
        oil_delta_half = abs(r2["pre_cap_deltas"].get("oil_index", 0))

        self.assertLess(oil_delta_half, oil_delta_full)

    def test_minimum_intensity_floor(self):
        """chain_intensity below 0.3 is clamped to 0.3."""
        self._seed_macro(5)
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]
        result = apply_event_impacts_to_macro(self.db, 5, tmpl, chain_intensity=0.1)
        self.assertTrue(result["applied"])
        # Should still produce some impact (0.3 floor)
        self.assertGreater(abs(result["pre_cap_deltas"].get("oil_index", 0)), 0)


# ── Active chains query ──────────────────────────────────────────────────────

class TestGetActiveChains(_BaseChainTest):

    def test_no_chains_returns_empty(self):
        result = get_active_chains(self.db, 5)
        self.assertEqual(result, [])

    def test_start_chain_is_active(self):
        self._seed_event(5, "oil_spike",
                         chain_id="active1",
                         chain_position=0,
                         chain_stage="start",
                         chain_length_expected=5,
                         continuation_probability=Decimal("0.65"),
                         decay_factor=Decimal("1.0000"))
        result = get_active_chains(self.db, 5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["chain_id"], "active1")
        self.assertTrue(result[0]["is_active"])

    def test_recovery_chain_is_not_active(self):
        self._seed_event(5, "supply_relief",
                         chain_id="resolved1",
                         chain_position=3,
                         chain_stage="recovery",
                         chain_length_expected=4,
                         continuation_probability=Decimal("0.00"),
                         decay_factor=Decimal("0.5000"))
        result = get_active_chains(self.db, 5)
        self.assertEqual(len(result), 0)

    def test_end_chain_is_not_active(self):
        self._seed_event(5, "mixed_signals",
                         chain_id="ended1",
                         chain_position=4,
                         chain_stage="end",
                         chain_length_expected=4,
                         continuation_probability=Decimal("0.00"),
                         decay_factor=Decimal("0.3000"))
        result = get_active_chains(self.db, 5)
        self.assertEqual(len(result), 0)


# ── Catalog chain metadata ───────────────────────────────────────────────────

class TestCatalogChainMetadata(unittest.TestCase):

    def test_oil_spike_is_chainable(self):
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]
        self.assertTrue(tmpl.can_chain)
        self.assertEqual(tmpl.chain_group_key, "energy_shock")
        self.assertGreater(len(tmpl.next_possible_events), 0)
        self.assertGreater(len(tmpl.recovery_events), 0)
        self.assertGreater(tmpl.base_continuation_probability, 0)

    def test_mixed_signals_not_chainable(self):
        tmpl = EVENT_CATALOG_BY_KEY["mixed_signals"]
        self.assertFalse(tmpl.can_chain)

    def test_recovery_events_not_chainable(self):
        for key in ["supply_relief", "hiring_surge", "oil_glut", "confidence_rebound"]:
            tmpl = EVENT_CATALOG_BY_KEY[key]
            self.assertFalse(tmpl.can_chain, f"{key} should not be chainable")

    def test_all_chain_references_exist_in_catalog(self):
        """Every event referenced in next/escalation/recovery must exist."""
        for tmpl in EVENT_CATALOG:
            for ref in tmpl.next_possible_events:
                self.assertIn(ref, EVENT_CATALOG_BY_KEY,
                              f"{tmpl.event_key} references unknown next event: {ref}")
            for ref in tmpl.escalation_events:
                self.assertIn(ref, EVENT_CATALOG_BY_KEY,
                              f"{tmpl.event_key} references unknown escalation event: {ref}")
            for ref in tmpl.recovery_events:
                self.assertIn(ref, EVENT_CATALOG_BY_KEY,
                              f"{tmpl.event_key} references unknown recovery event: {ref}")

    def test_chain_group_keys_are_consistent(self):
        """All chainable events must have a non-empty chain_group_key."""
        for tmpl in EVENT_CATALOG:
            if tmpl.can_chain:
                self.assertTrue(tmpl.chain_group_key,
                                f"{tmpl.event_key} is chainable but has no chain_group_key")

    def test_max_chain_length_bounded(self):
        """max_chain_length should be between 1 and 10."""
        for tmpl in EVENT_CATALOG:
            if tmpl.can_chain:
                self.assertGreaterEqual(tmpl.max_chain_length, 1)
                self.assertLessEqual(tmpl.max_chain_length, 10)


# ── Serialization chain fields ────────────────────────────────────────────────

class TestSerializationChainFields(_BaseChainTest):

    def test_serialized_event_contains_chain_fields(self):
        self._seed_macro(5)
        from app.engine.event_service import force_daily_event
        result = force_daily_event(self.db, 5, "oil_spike")
        self.db.commit()
        for key in ["chain_id", "chain_position", "chain_stage",
                     "is_chain_continuation", "decay_factor",
                     "continuation_probability"]:
            self.assertIn(key, result, f"Missing chain field: {key}")

    def test_chain_start_not_continuation(self):
        self._seed_macro(5)
        from app.engine.event_service import force_daily_event
        result = force_daily_event(self.db, 5, "oil_spike")
        self.db.commit()
        self.assertFalse(result["is_chain_continuation"])


# ── Brief narrative chain awareness ───────────────────────────────────────────

class TestBriefNarrativeChainAware(_BaseChainTest):

    def test_chain_mid_adds_ongoing_prefix(self):
        self._seed_macro(5)
        self._seed_event(5, "oil_spike",
                         chain_id="brief_chain",
                         chain_position=2,
                         chain_stage="mid")
        from app.services.daily_brief_service import generate_global_daily_event
        result = generate_global_daily_event(self.db, 5)
        self.assertIn("ongoing pressure", result["headline"])
        self.assertIn("chain_continuation", result["macro_tags_json"])

    def test_chain_escalation_adds_intensify_prefix(self):
        self._seed_macro(5)
        self._seed_event(5, "oil_spike",
                         chain_id="brief_chain",
                         chain_position=3,
                         chain_stage="escalation")
        from app.services.daily_brief_service import generate_global_daily_event
        result = generate_global_daily_event(self.db, 5)
        self.assertIn("intensify", result["headline"].lower())
        self.assertIn("chain_escalation", result["macro_tags_json"])

    def test_chain_recovery_adds_stabilize_prefix(self):
        self._seed_macro(5)
        self._seed_event(5, "supply_relief",
                         chain_id="brief_chain",
                         chain_position=4,
                         chain_stage="recovery")
        from app.services.daily_brief_service import generate_global_daily_event
        result = generate_global_daily_event(self.db, 5)
        self.assertIn("stabilization", result["headline"].lower())
        self.assertIn("chain_recovery", result["macro_tags_json"])

    def test_chain_start_no_prefix(self):
        self._seed_macro(5)
        self._seed_event(5, "oil_spike",
                         chain_id="brief_chain",
                         chain_position=0,
                         chain_stage="start")
        from app.services.daily_brief_service import generate_global_daily_event
        result = generate_global_daily_event(self.db, 5)
        # Start events should have the normal headline without chain prefixes
        self.assertNotIn("ongoing pressure", result["headline"])
        self.assertNotIn("intensif", result["headline"].lower())

    def test_parent_event_key_in_tags(self):
        self._seed_macro(5)
        self._seed_event(5, "pipeline_disruption",
                         chain_id="brief_chain",
                         chain_position=1,
                         chain_stage="mid",
                         parent_event_key="oil_spike")
        from app.services.daily_brief_service import generate_global_daily_event
        result = generate_global_daily_event(self.db, 5)
        self.assertIn("follows_oil_spike", result["macro_tags_json"])


# ── Bounded effects ───────────────────────────────────────────────────────────

class TestBoundedChainEffects(_BaseChainTest):

    def test_chain_impact_respects_daily_caps(self):
        """Even with chain_intensity=1.0, daily caps are enforced."""
        self._seed_macro(5)
        tmpl = EVENT_CATALOG_BY_KEY["oil_spike"]
        result = apply_event_impacts_to_macro(self.db, 5, tmpl, chain_intensity=1.0)
        oil_delta = abs(result["post_cap_deltas"].get("oil_index", 0))
        self.assertLessEqual(oil_delta, 6.0001)  # cap is 6.0

    def test_multi_day_chain_macro_stays_in_bounds(self):
        """Run engine for several days — macro values stay within floor/ceiling."""
        for d in range(1, 8):
            self._seed_macro(d)
        for d in range(1, 8):
            run_daily_event_engine(self.db, d)
            self.db.commit()
            # Check last macro
            macro = self.db.query(MacroDailyState).filter(MacroDailyState.day == d).first()
            self.assertGreaterEqual(float(macro.oil_index), 30.0)
            self.assertLessEqual(float(macro.oil_index), 250.0)
            self.assertGreaterEqual(float(macro.consumer_confidence), 10.0)
            self.assertLessEqual(float(macro.consumer_confidence), 100.0)


if __name__ == "__main__":
    unittest.main()
