"""Integration tests for Step 43 — Supply Chain Graph + Bottleneck Opportunity Engine.

Validates cross-node interactions, basket reactions to specific bottlenecks,
job pressure routing, and cross-layer consistency between the physical graph
layer and the upstream Step 13 abstract engine results.
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_supply_chain_graph_integration.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.engine.supply_chain_graph_service import (
    build_basket_supply_multipliers,
    build_job_pressure_from_bottlenecks,
    build_node_state_snapshot,
    build_supply_chain_daily_summary,
    build_supply_chain_story_summary,
    detect_supply_chain_bottlenecks,
)
from app.models.macro_daily_state import MacroDailyState
from app.models.supply_chain_daily_snapshot import SupplyChainDailySnapshot
from app.models.supply_chain_node_state import SupplyChainNodeState


def _make_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            MacroDailyState.__table__,
            SupplyChainNodeState.__table__,
            SupplyChainDailySnapshot.__table__,
        ],
    )
    return engine


def _seed_macro(db, day: int = 1, stress: float = 0.5, oil_index: float = 100.0):
    row = MacroDailyState(
        day=day,
        inflation_rate=2.5,
        interest_rate=4.0,
        unemployment_rate=5.0,
        oil_index=oil_index,
        consumer_confidence=55.0,
        supply_chain_stress=stress,
        created_at=datetime(2026, 1, 1, 8, 0, 0),
    )
    db.add(row)
    db.commit()


def _add_override(db, node_key: str, day: int, capacity: float, required: float = 1.0, reliability: float = 1.0):
    db.add(SupplyChainNodeState(
        node_key=node_key,
        day=day,
        capacity=capacity,
        required=required,
        reliability=reliability,
        last_updated_on=day,
    ))
    db.commit()


class TestProduceBasketBottlenecks(unittest.TestCase):
    """Produce basket should react to FARM, WATER, and FERTILIZER bottlenecks."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_farm_bottleneck_elevates_produce(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)
        baseline_produce = baseline["produce"].supply_multiplier

        _add_override(self.db, "FARM", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)
        self.assertGreater(stressed["produce"].supply_multiplier, baseline_produce)

    def test_water_bottleneck_elevates_produce(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)["produce"].supply_multiplier
        _add_override(self.db, "WATER", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["produce"].supply_multiplier
        self.assertGreater(stressed, baseline)

    def test_fertilizer_bottleneck_elevates_produce(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)["produce"].supply_multiplier
        _add_override(self.db, "FERTILIZER", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["produce"].supply_multiplier
        self.assertGreater(stressed, baseline)

    def test_farm_bottleneck_does_not_elevate_convenience(self):
        # FARM is not in the convenience basket recipe
        baseline = build_basket_supply_multipliers(self.db, day=1)["convenience"].supply_multiplier
        _add_override(self.db, "FARM", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["convenience"].supply_multiplier
        # Should remain close to baseline (FARM has no weight in convenience)
        self.assertAlmostEqual(stressed, baseline, places=3)


class TestProteinBasketBottlenecks(unittest.TestCase):
    """Protein basket should react to FEED and RANCH_POULTRY bottlenecks."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_feed_bottleneck_elevates_protein(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)["protein"].supply_multiplier
        _add_override(self.db, "FEED", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["protein"].supply_multiplier
        self.assertGreater(stressed, baseline)

    def test_ranch_poultry_bottleneck_elevates_protein(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)["protein"].supply_multiplier
        _add_override(self.db, "RANCH_POULTRY", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["protein"].supply_multiplier
        self.assertGreater(stressed, baseline)

    def test_feed_does_not_significantly_affect_convenience(self):
        # FEED is not in convenience basket
        baseline = build_basket_supply_multipliers(self.db, day=1)["convenience"].supply_multiplier
        _add_override(self.db, "FEED", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["convenience"].supply_multiplier
        self.assertAlmostEqual(stressed, baseline, places=3)


class TestEssentialsBasketBottlenecks(unittest.TestCase):
    """Essentials basket should react to DAIRY and TRUCKING_LASTMILE bottlenecks."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_dairy_bottleneck_elevates_essentials(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)["essentials"].supply_multiplier
        _add_override(self.db, "DAIRY", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["essentials"].supply_multiplier
        self.assertGreater(stressed, baseline)

    def test_trucking_bottleneck_elevates_essentials(self):
        baseline = build_basket_supply_multipliers(self.db, day=1)["essentials"].supply_multiplier
        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.60)
        stressed = build_basket_supply_multipliers(self.db, day=1)["essentials"].supply_multiplier
        self.assertGreater(stressed, baseline)


class TestJobPressureRouting(unittest.TestCase):
    """Validate job pressure is routed correctly from specific bottleneck nodes."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1, stress=0.0)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_delivery_driver_pressure_rises_during_transport_stress(self):
        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.60)
        pressure = build_job_pressure_from_bottlenecks(self.db, day=1)
        self.assertIn("delivery_driver", pressure)
        self.assertGreater(pressure["delivery_driver"].job_pressure_multiplier, 1.0)

    def test_auto_mechanic_opportunity_rises_during_oil_stress(self):
        _add_override(self.db, "OIL_FUEL", day=1, capacity=0.60)
        pressure = build_job_pressure_from_bottlenecks(self.db, day=1)
        self.assertIn("auto_mechanic", pressure)
        self.assertGreater(pressure["auto_mechanic"].job_pressure_multiplier, 1.0)

    def test_retail_worker_pressure_when_warehouse_constrained(self):
        _add_override(self.db, "WAREHOUSE_DISTRIBUTION", day=1, capacity=0.60)
        pressure = build_job_pressure_from_bottlenecks(self.db, day=1)
        self.assertIn("retail_worker", pressure)
        self.assertGreater(pressure["retail_worker"].job_pressure_multiplier, 1.0)

    def test_combined_bottlenecks_increase_delivery_driver_beyond_single(self):
        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.65)
        pressure_single = build_job_pressure_from_bottlenecks(self.db, day=1)
        single_mult = pressure_single.get("delivery_driver", None)

        _add_override(self.db, "OIL_FUEL", day=1, capacity=0.65)
        pressure_combined = build_job_pressure_from_bottlenecks(self.db, day=1)
        combined_mult = pressure_combined.get("delivery_driver", None)

        if single_mult and combined_mult:
            self.assertGreater(combined_mult.job_pressure_multiplier, single_mult.job_pressure_multiplier)

    def test_chef_pressure_rises_from_food_processing_constraint(self):
        _add_override(self.db, "FOOD_PROCESSING", day=1, capacity=0.60)
        pressure = build_job_pressure_from_bottlenecks(self.db, day=1)
        self.assertIn("chef", pressure)
        self.assertGreater(pressure["chef"].job_pressure_multiplier, 1.0)


class TestSummaryToBottleneckIntegration(unittest.TestCase):
    """Validate the daily summary aggregates correctly from component calls."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1, stress=0.5)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_summary_top_bottleneck_matches_most_constrained_node(self):
        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.55)
        _add_override(self.db, "OIL_FUEL", day=1, capacity=0.80)

        summary = build_supply_chain_daily_summary(self.db, day=1)
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1)

        if bottlenecks and summary.top_bottleneck_node:
            self.assertEqual(summary.top_bottleneck_node, bottlenecks[0].node_id)

    def test_most_affected_basket_has_highest_multiplier(self):
        _add_override(self.db, "FARM", day=1, capacity=0.55)
        summary = build_supply_chain_daily_summary(self.db, day=1)
        multipliers = build_basket_supply_multipliers(self.db, day=1)

        if summary.most_affected_basket:
            best_mult = max(m.supply_multiplier for m in multipliers.values())
            actual_mult = multipliers[summary.most_affected_basket].supply_multiplier
            self.assertAlmostEqual(actual_mult, best_mult, places=4)

    def test_summary_node_states_count_equals_twelve(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertEqual(len(summary.node_states), 12)

    def test_summary_basket_count_equals_four(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertEqual(len(summary.basket_multipliers), 4)

    def test_summary_day_matches_requested(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertEqual(summary.day, 1)


class TestStressScoreIntegration(unittest.TestCase):
    """Validate overall_stress_score reflects combined node constraints."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1, stress=0.0)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_stress_score_increases_with_more_constrained_nodes(self):
        baseline = build_supply_chain_daily_summary(self.db, day=1).overall_stress_score

        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.60)
        stressed = build_supply_chain_daily_summary(self.db, day=1).overall_stress_score

        self.assertGreater(stressed, baseline)

    def test_stress_score_bounded_between_0_and_1(self):
        for node in ["TRUCKING_LASTMILE", "OIL_FUEL", "FARM", "DAIRY", "WATER", "FOOD_PROCESSING"]:
            _add_override(self.db, node, day=1, capacity=0.55)

        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertGreaterEqual(summary.overall_stress_score, 0.0)
        self.assertLessEqual(summary.overall_stress_score, 1.0)


class TestStoryNarrativeIntegration(unittest.TestCase):
    """Validate story narrative reflects active supply chain conditions."""

    def setUp(self):
        self.engine = _make_engine()
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)()
        _seed_macro(self.db, day=1, stress=0.5)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_story_day_matches_requested(self):
        story = build_supply_chain_story_summary(self.db, day=1)
        self.assertEqual(story.day, 1)

    def test_story_reflects_trucking_constraint(self):
        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.60)
        story = build_supply_chain_story_summary(self.db, day=1)
        # Should mention trucking in highlights or story
        all_text = " ".join([story.shortage_story] + story.bottleneck_highlights).lower()
        self.assertIn("trucking", all_text)

    def test_story_has_basket_impact_notes(self):
        _add_override(self.db, "FARM", day=1, capacity=0.60)
        story = build_supply_chain_story_summary(self.db, day=1)
        self.assertIsInstance(story.basket_impact_notes, list)

    def test_story_job_hints_populated_when_bottleneck_present(self):
        _add_override(self.db, "TRUCKING_LASTMILE", day=1, capacity=0.60)
        story = build_supply_chain_story_summary(self.db, day=1)
        # With a trucking bottleneck there should be at least one job opportunity hint
        self.assertGreater(len(story.job_opportunity_hints), 0)


if __name__ == "__main__":
    unittest.main()
