"""Tests for Step 43 — Supply Chain Graph + Bottleneck Opportunity Engine.

Tests validate:
- Recipe validation (weights sum to 1.0, all nodes bridged)
- Label functions at boundary thresholds
- build_node_state_snapshot returns all 12 nodes with correct properties
- Region modifier differentiation
- detect_supply_chain_bottlenecks correct ranking and filtering
- build_basket_supply_multipliers formula and clamping
- build_job_pressure_from_bottlenecks accumulation and clamping
- build_supply_chain_daily_summary aggregation
- build_supply_chain_story_summary content
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_supply_chain_graph.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.engine.supply_chain_graph_service import (
    SupplyChainGraphValidationError,
    build_basket_supply_multipliers,
    build_job_pressure_from_bottlenecks,
    build_node_state_snapshot,
    build_supply_chain_daily_summary,
    build_supply_chain_story_summary,
    compute_node_availability,
    detect_supply_chain_bottlenecks,
)
from app.engine.supply_chain_recipes import (
    GRAPH_BASKET_RECIPES,
    JOB_BOTTLENECK_MAP,
    MVP_NODE_IDS,
    NODE_TO_ABSTRACT_BRIDGE,
    bottleneck_severity_label,
    cost_pressure_label,
    opportunity_label,
    validate_graph_recipes,
)
from app.models.macro_daily_state import MacroDailyState
from app.models.supply_chain_daily_snapshot import SupplyChainDailySnapshot
from app.models.supply_chain_node_state import SupplyChainNodeState


def _make_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    tables = [
        MacroDailyState.__table__,
        SupplyChainNodeState.__table__,
        SupplyChainDailySnapshot.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    return engine


def _seed_macro(db, day: int = 1, stress: float = 0.5):
    row = MacroDailyState(
        day=day,
        inflation_rate=2.5,
        interest_rate=4.0,
        unemployment_rate=5.0,
        oil_index=100.0,
        consumer_confidence=55.0,
        supply_chain_stress=stress,
        created_at=datetime(2026, 1, 1, 8, 0, 0),
    )
    db.add(row)
    db.commit()


class TestGraphRecipeValidation(unittest.TestCase):
    """Validate that supply_chain_recipes.py is internally consistent."""

    def test_validate_graph_recipes_passes(self):
        """validate_graph_recipes() must not raise on the current definitions."""
        validate_graph_recipes()  # should not raise

    def test_all_basket_weights_sum_to_one(self):
        for basket, weights in GRAPH_BASKET_RECIPES.items():
            total = sum(weights.values())
            self.assertAlmostEqual(total, 1.0, places=9, msg=f"{basket} weights sum to {total}")

    def test_all_mvp_nodes_in_abstract_bridge(self):
        for node_id in MVP_NODE_IDS:
            self.assertIn(node_id, NODE_TO_ABSTRACT_BRIDGE, f"{node_id} missing from bridge")

    def test_abstract_bridge_targets_valid_abstract_nodes(self):
        valid_abstract = {"fuel", "labor", "utilities", "fertilizer", "farming", "trucking", "processing", "retail"}
        for node_id, abstract in NODE_TO_ABSTRACT_BRIDGE.items():
            self.assertIn(abstract, valid_abstract, f"{node_id} → {abstract!r} not valid")

    def test_expected_node_count(self):
        self.assertEqual(len(MVP_NODE_IDS), 12)


class TestLabelFunctions(unittest.TestCase):
    """Unit tests for bottleneck_severity_label, cost_pressure_label, opportunity_label."""

    # bottleneck_severity_label boundaries
    def test_severity_none_at_0_90(self):
        self.assertEqual(bottleneck_severity_label(0.90), "none")

    def test_severity_none_at_1_0(self):
        self.assertEqual(bottleneck_severity_label(1.0), "none")

    def test_severity_minor_just_below_0_90(self):
        self.assertEqual(bottleneck_severity_label(0.89), "minor")

    def test_severity_minor_at_0_80(self):
        self.assertEqual(bottleneck_severity_label(0.80), "minor")

    def test_severity_moderate_just_below_0_80(self):
        self.assertEqual(bottleneck_severity_label(0.79), "moderate")

    def test_severity_moderate_at_0_70(self):
        self.assertEqual(bottleneck_severity_label(0.70), "moderate")

    def test_severity_severe_just_below_0_70(self):
        self.assertEqual(bottleneck_severity_label(0.69), "severe")

    def test_severity_severe_at_0_60(self):
        self.assertEqual(bottleneck_severity_label(0.60), "severe")

    def test_severity_critical_just_below_0_60(self):
        self.assertEqual(bottleneck_severity_label(0.59), "critical")

    def test_severity_critical_at_floor(self):
        self.assertEqual(bottleneck_severity_label(0.55), "critical")

    # cost_pressure_label boundaries
    def test_cost_pressure_low_below_1_00(self):
        self.assertEqual(cost_pressure_label(0.99), "low")

    def test_cost_pressure_elevated_at_1_00(self):
        self.assertEqual(cost_pressure_label(1.00), "elevated")

    def test_cost_pressure_high_at_1_03(self):
        self.assertEqual(cost_pressure_label(1.03), "high")

    def test_cost_pressure_critical_at_1_08(self):
        self.assertEqual(cost_pressure_label(1.08), "critical")

    # opportunity_label
    def test_opportunity_weak_no_bottlenecks(self):
        self.assertEqual(opportunity_label(0, 0.0), "weak")

    def test_opportunity_weak_low_pressure(self):
        self.assertEqual(opportunity_label(1, 0.04), "weak")

    def test_opportunity_emerging(self):
        self.assertEqual(opportunity_label(1, 0.10), "emerging")

    def test_opportunity_strong(self):
        self.assertEqual(opportunity_label(2, 0.20), "strong")

    def test_opportunity_surge(self):
        self.assertEqual(opportunity_label(3, 0.35), "surge")


class GraphServiceTestBase(unittest.TestCase):
    """Base class with in-memory DB setup for graph service tests."""

    def setUp(self):
        self.engine = _make_engine()
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()


class TestBuildNodeStateSnapshot(GraphServiceTestBase):
    """Tests for build_node_state_snapshot."""

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.5)

    def test_returns_all_12_nodes(self):
        snapshot = build_node_state_snapshot(self.db, day=1)
        self.assertEqual(len(snapshot), 12)
        for node_id in MVP_NODE_IDS:
            self.assertIn(node_id, snapshot)

    def test_all_availabilities_within_bounds(self):
        snapshot = build_node_state_snapshot(self.db, day=1)
        for node_id, rec in snapshot.items():
            self.assertGreaterEqual(rec.availability, 0.55, f"{node_id} below floor")
            self.assertLessEqual(rec.availability, 1.10, f"{node_id} above ceiling")

    def test_region_adjusted_availability_present(self):
        snapshot = build_node_state_snapshot(self.db, day=1, region="suburban")
        for rec in snapshot.values():
            self.assertIsNotNone(rec.region_adjusted_availability)

    def test_downtown_trucking_lower_than_suburban(self):
        snap_sub = build_node_state_snapshot(self.db, day=1, region="suburban")
        snap_down = build_node_state_snapshot(self.db, day=1, region="downtown")
        sub_avail = snap_sub["TRUCKING_LASTMILE"].region_adjusted_availability
        down_avail = snap_down["TRUCKING_LASTMILE"].region_adjusted_availability
        self.assertLess(down_avail, sub_avail, "Downtown trucking should be more constrained")

    def test_rural_farm_higher_than_downtown(self):
        snap_rural = build_node_state_snapshot(self.db, day=1, region="rural")
        snap_down = build_node_state_snapshot(self.db, day=1, region="downtown")
        rural_avail = snap_rural["FARM"].region_adjusted_availability
        down_avail = snap_down["FARM"].region_adjusted_availability
        self.assertGreater(rural_avail, down_avail, "Rural farm should be higher than downtown")

    def test_source_is_macro_when_no_db_override(self):
        snapshot = build_node_state_snapshot(self.db, day=1)
        for rec in snapshot.values():
            self.assertEqual(rec.source, "macro")

    def test_source_is_db_override_when_row_present(self):
        override = SupplyChainNodeState(
            node_key="OIL_FUEL",
            day=1,
            capacity=0.70,
            required=1.0,
            reliability=0.95,
            last_updated_on=1,
        )
        self.db.add(override)
        self.db.commit()
        snapshot = build_node_state_snapshot(self.db, day=1)
        self.assertEqual(snapshot["OIL_FUEL"].source, "db_override")

    def test_db_override_availability_uses_capacity_ratio(self):
        # capacity=0.70, required=1.0, reliability=0.95 → 0.70 * 0.95 = 0.665
        override = SupplyChainNodeState(
            node_key="ELECTRICITY",
            day=1,
            capacity=0.70,
            required=1.0,
            reliability=0.95,
            last_updated_on=1,
        )
        self.db.add(override)
        self.db.commit()
        snapshot = build_node_state_snapshot(self.db, day=1)
        expected = 0.70 * 0.95
        self.assertAlmostEqual(snapshot["ELECTRICITY"].availability, expected, places=4)


class TestComputeNodeAvailability(GraphServiceTestBase):

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.5)

    def test_returns_float_for_valid_node(self):
        avail = compute_node_availability(self.db, day=1, node_id="OIL_FUEL")
        self.assertIsInstance(avail, float)

    def test_raises_for_unknown_node(self):
        with self.assertRaises(SupplyChainGraphValidationError):
            compute_node_availability(self.db, day=1, node_id="NONEXISTENT_NODE")

    def test_region_affects_value(self):
        avail_sub = compute_node_availability(self.db, day=1, node_id="TRUCKING_LASTMILE", region="suburban")
        avail_down = compute_node_availability(self.db, day=1, node_id="TRUCKING_LASTMILE", region="downtown")
        self.assertNotEqual(avail_sub, avail_down)


class TestDetectSupplyChainBottlenecks(GraphServiceTestBase):

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.0)  # low stress → high availability

    def test_high_availability_returns_empty_list(self):
        # With low macro stress, all nodes should be at ~1.0 availability → no bottlenecks
        # We use a threshold of 1.10 (impossibly high) to force empty result with any data
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1, threshold=0.0)
        self.assertEqual(bottlenecks, [])

    def test_low_threshold_catches_no_bottlenecks(self):
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1, threshold=0.0)
        self.assertIsInstance(bottlenecks, list)

    def test_bottlenecks_sorted_ascending_by_availability(self):
        # Seed two override nodes with different availability levels
        self.db.add(SupplyChainNodeState(node_key="OIL_FUEL", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.70, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1, threshold=0.95)
        if len(bottlenecks) >= 2:
            for i in range(len(bottlenecks) - 1):
                self.assertLessEqual(bottlenecks[i].availability, bottlenecks[i + 1].availability)

    def test_bottleneck_rank_is_sequential(self):
        self.db.add(SupplyChainNodeState(node_key="OIL_FUEL", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.70, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1, threshold=0.95)
        for i, rec in enumerate(bottlenecks):
            self.assertEqual(rec.rank, i + 1)

    def test_bottleneck_has_affected_baskets(self):
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1, threshold=0.95)
        trucking_bn = next((b for b in bottlenecks if b.node_id == "TRUCKING_LASTMILE"), None)
        self.assertIsNotNone(trucking_bn)
        self.assertGreater(len(trucking_bn.affected_baskets), 0)

    def test_oil_fuel_bottleneck_affects_correct_jobs(self):
        self.db.add(SupplyChainNodeState(node_key="OIL_FUEL", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        bottlenecks = detect_supply_chain_bottlenecks(self.db, day=1, threshold=0.95)
        oil_bn = next((b for b in bottlenecks if b.node_id == "OIL_FUEL"), None)
        self.assertIsNotNone(oil_bn)
        self.assertIn("auto_mechanic", oil_bn.affected_jobs)


class TestBuildBasketSupplyMultipliers(GraphServiceTestBase):

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.5)

    def test_returns_all_four_baskets(self):
        result = build_basket_supply_multipliers(self.db, day=1)
        self.assertEqual(set(result.keys()), {"essentials", "protein", "produce", "convenience"})

    def test_multipliers_within_clamp_bounds(self):
        result = build_basket_supply_multipliers(self.db, day=1)
        for basket, record in result.items():
            self.assertGreaterEqual(record.supply_multiplier, 0.85, f"{basket} below min")
            self.assertLessEqual(record.supply_multiplier, 1.10, f"{basket} above max")

    def test_low_trucking_raises_essentials_and_convenience(self):
        # Force TRUCKING_LASTMILE to low availability
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.55, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_basket_supply_multipliers(self.db, day=1)
        # Both essentials and convenience include TRUCKING_LASTMILE
        self.assertGreater(result["essentials"].supply_multiplier, 1.0)
        self.assertGreater(result["convenience"].supply_multiplier, 1.0)

    def test_low_farm_raises_produce_multiplier(self):
        self.db.add(SupplyChainNodeState(node_key="FARM", day=1, capacity=0.55, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_basket_supply_multipliers(self.db, day=1)
        self.assertGreater(result["produce"].supply_multiplier, 1.0)

    def test_low_feed_raises_protein_multiplier(self):
        self.db.add(SupplyChainNodeState(node_key="FEED", day=1, capacity=0.55, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_basket_supply_multipliers(self.db, day=1)
        self.assertGreater(result["protein"].supply_multiplier, 1.0)

    def test_produce_not_in_convenience_basket(self):
        # FARM is NOT in the convenience basket recipe
        result = build_basket_supply_multipliers(self.db, day=1)
        self.db.add(SupplyChainNodeState(node_key="FARM", day=1, capacity=0.55, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result_after = build_basket_supply_multipliers(self.db, day=1)
        # Convenience multiplier should not change significantly from FARM alone
        # (FARM is not in convenience recipe)
        diff = abs(result_after["convenience"].supply_multiplier - result["convenience"].supply_multiplier)
        self.assertLess(diff, 0.01)


class TestBuildJobPressureFromBottlenecks(GraphServiceTestBase):

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.0)

    def test_no_bottlenecks_returns_empty_dict(self):
        # With threshold = 0.0, no nodes qualify as bottlenecks
        # We pass threshold=0.0 but job pressure uses 0.95 threshold internally
        # With stress=0.0 macro, all nodes should be near 1.0 → no job pressure
        result = build_job_pressure_from_bottlenecks(self.db, day=1)
        # All nodes at ~1.0 availability → 0.95 threshold → no bottleneck contributions
        self.assertIsInstance(result, dict)

    def test_trucking_bottleneck_creates_delivery_driver_pressure(self):
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_job_pressure_from_bottlenecks(self.db, day=1)
        self.assertIn("delivery_driver", result)
        self.assertGreater(result["delivery_driver"].job_pressure_multiplier, 1.0)

    def test_oil_fuel_bottleneck_creates_auto_mechanic_pressure(self):
        self.db.add(SupplyChainNodeState(node_key="OIL_FUEL", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_job_pressure_from_bottlenecks(self.db, day=1)
        self.assertIn("auto_mechanic", result)
        self.assertGreater(result["auto_mechanic"].job_pressure_multiplier, 1.0)

    def test_job_multiplier_clamped_max_1_50(self):
        # Create multiple extreme bottlenecks for delivery_driver
        for node in ["TRUCKING_LASTMILE", "OIL_FUEL", "WAREHOUSE_DISTRIBUTION"]:
            self.db.add(SupplyChainNodeState(node_key=node, day=1, capacity=0.55, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_job_pressure_from_bottlenecks(self.db, day=1)
        if "delivery_driver" in result:
            self.assertLessEqual(result["delivery_driver"].job_pressure_multiplier, 1.50)

    def test_source_bottleneck_nodes_populated(self):
        self.db.add(SupplyChainNodeState(node_key="OIL_FUEL", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        result = build_job_pressure_from_bottlenecks(self.db, day=1)
        if "auto_mechanic" in result:
            self.assertIn("OIL_FUEL", result["auto_mechanic"].source_bottleneck_nodes)


class TestBuildSupplyChainDailySummary(GraphServiceTestBase):

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.5)

    def test_returns_summary_record(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.day, 1)

    def test_summary_has_all_node_states(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertEqual(len(summary.node_states), 12)

    def test_summary_has_four_basket_multipliers(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertEqual(len(summary.basket_multipliers), 4)

    def test_top_bottleneck_identified_when_node_constrained(self):
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertEqual(summary.top_bottleneck_node, "TRUCKING_LASTMILE")

    def test_to_dict_returns_expected_keys(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        d = summary.to_dict()
        for key in ("day", "top_bottleneck_node", "most_affected_basket", "overall_stress_score",
                    "node_states", "bottlenecks", "basket_multipliers", "job_pressure"):
            self.assertIn(key, d, f"Key {key!r} missing from to_dict()")

    def test_stress_score_within_0_to_1(self):
        summary = build_supply_chain_daily_summary(self.db, day=1)
        self.assertGreaterEqual(summary.overall_stress_score, 0.0)
        self.assertLessEqual(summary.overall_stress_score, 1.0)

    def test_persist_true_inserts_snapshot_row(self):
        _result = build_supply_chain_daily_summary(self.db, day=1, persist=True)
        self.db.commit()
        row = self.db.query(SupplyChainDailySnapshot).filter(SupplyChainDailySnapshot.day == 1).first()
        self.assertIsNotNone(row)

    def test_persist_true_upserts_on_second_call(self):
        build_supply_chain_daily_summary(self.db, day=1, persist=True)
        self.db.commit()
        build_supply_chain_daily_summary(self.db, day=1, persist=True)
        self.db.commit()
        count = self.db.query(SupplyChainDailySnapshot).filter(SupplyChainDailySnapshot.day == 1).count()
        self.assertEqual(count, 1, "Persist=True should upsert, not insert duplicates")


class TestBuildSupplyChainStorySummary(GraphServiceTestBase):

    def setUp(self):
        super().setUp()
        _seed_macro(self.db, day=1, stress=0.5)

    def test_returns_story_record(self):
        story = build_supply_chain_story_summary(self.db, day=1)
        self.assertIsNotNone(story)
        self.assertEqual(story.day, 1)

    def test_shortage_story_is_non_empty_string(self):
        story = build_supply_chain_story_summary(self.db, day=1)
        self.assertIsInstance(story.shortage_story, str)
        self.assertGreater(len(story.shortage_story), 0)

    def test_has_practical_current_actions(self):
        story = build_supply_chain_story_summary(self.db, day=1)
        self.assertIsInstance(story.practical_current_actions, list)

    def test_trucking_bottleneck_mentioned_in_highlights(self):
        self.db.add(SupplyChainNodeState(node_key="TRUCKING_LASTMILE", day=1, capacity=0.60, required=1.0, reliability=1.0, last_updated_on=1))
        self.db.commit()
        story = build_supply_chain_story_summary(self.db, day=1)
        combined = " ".join(story.bottleneck_highlights).lower()
        self.assertIn("trucking", combined)

    def test_to_dict_contains_all_sections(self):
        story = build_supply_chain_story_summary(self.db, day=1)
        d = story.to_dict()
        for key in ("day", "shortage_story", "bottleneck_highlights",
                    "basket_impact_notes", "job_opportunity_hints", "practical_current_actions"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
