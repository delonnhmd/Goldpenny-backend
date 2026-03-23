import os
import unittest
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_supply_chain_service.db")

from app.api.economy import get_supply_chain_daily_route
from app.db.database import Base
from app.engine.basket_recipes import BASKET_RECIPES
from app.engine.supply_chain_service import (
    JOB_PRESSURE_MAX,
    JOB_PRESSURE_MIN,
    SupplyChainNotFoundError,
    compute_supply_chain_daily_snapshot,
)
from app.models.macro_daily_state import MacroDailyState


class SupplyChainServiceTests(unittest.TestCase):
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
            ],
        )

        self.db = self.SessionLocal()
        self._seed_macro_states()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_macro_states(self) -> None:
        rows = [
            MacroDailyState(
                day=1,
                inflation_rate=2.2,
                interest_rate=4.1,
                unemployment_rate=5.0,
                oil_index=100.0,
                consumer_confidence=55.0,
                supply_chain_stress=0.5,
                created_at=datetime(2026, 3, 10, 8, 0, 0),
            ),
            MacroDailyState(
                day=2,
                inflation_rate=4.4,
                interest_rate=5.2,
                unemployment_rate=6.2,
                oil_index=160.0,
                consumer_confidence=44.0,
                supply_chain_stress=1.9,
                created_at=datetime(2026, 3, 11, 8, 0, 0),
            ),
            MacroDailyState(
                day=3,
                inflation_rate=4.9,
                interest_rate=6.0,
                unemployment_rate=8.2,
                oil_index=145.0,
                consumer_confidence=34.0,
                supply_chain_stress=2.2,
                created_at=datetime(2026, 3, 12, 8, 0, 0),
            ),
            MacroDailyState(
                day=4,
                inflation_rate=1.8,
                interest_rate=3.6,
                unemployment_rate=4.9,
                oil_index=92.0,
                consumer_confidence=60.0,
                supply_chain_stress=0.3,
                created_at=datetime(2026, 3, 13, 8, 0, 0),
            ),
            MacroDailyState(
                day=5,
                inflation_rate=3.9,
                interest_rate=5.5,
                unemployment_rate=7.0,
                oil_index=152.0,
                consumer_confidence=40.0,
                supply_chain_stress=2.5,
                created_at=datetime(2026, 3, 14, 8, 0, 0),
            ),
        ]
        self.db.add_all(rows)

    def test_successful_daily_snapshot_generation(self) -> None:
        snapshot = compute_supply_chain_daily_snapshot(self.db)
        self.assertIsNotNone(snapshot["macro_state_id"])
        self.assertGreater(len(snapshot["node_snapshots"]), 0)
        self.assertGreater(len(snapshot["basket_supply"]), 0)
        self.assertGreater(len(snapshot["job_pressure"]), 0)
        self.assertIn("debug_meta", snapshot)

    def test_deterministic_output_for_same_macro_state(self) -> None:
        snapshot_a = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 13))
        snapshot_b = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 13))
        self.assertEqual(snapshot_a, snapshot_b)

    def test_node_availability_is_within_clamp_bounds(self) -> None:
        snapshot = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 12))
        for node in snapshot["node_snapshots"]:
            self.assertGreaterEqual(node["availability"], 0.70)
            self.assertLessEqual(node["availability"], 1.10)
            self.assertGreaterEqual(node["severity"], 0.00)

    def test_basket_recipe_weights_sum_to_one(self) -> None:
        for basket_key, recipe in BASKET_RECIPES.items():
            total = sum(float(weight) for weight in recipe.values())
            self.assertAlmostEqual(
                total,
                1.0,
                places=4,
                msg=f"recipe weights invalid for basket={basket_key}",
            )

    def test_basket_supply_multiplier_is_within_clamp_bounds(self) -> None:
        snapshot = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 12))
        for basket in snapshot["basket_supply"]:
            self.assertGreaterEqual(basket["supply_multiplier"], 0.85)
            self.assertLessEqual(basket["supply_multiplier"], 1.10)

    def test_bottleneck_sorting_is_deterministic(self) -> None:
        snapshot = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 14))
        bottlenecks = snapshot["bottlenecks"]
        for idx in range(len(bottlenecks) - 1):
            current = bottlenecks[idx]
            nxt = bottlenecks[idx + 1]
            current_key = (-current["severity"], current["availability"], current["node_key"])
            next_key = (-nxt["severity"], nxt["availability"], nxt["node_key"])
            self.assertLessEqual(current_key, next_key)

    def test_job_pressure_stays_in_bounds(self) -> None:
        snapshot = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 14))
        for row in snapshot["job_pressure"]:
            self.assertGreaterEqual(row["pressure"], float(JOB_PRESSURE_MIN))
            self.assertLessEqual(row["pressure"], float(JOB_PRESSURE_MAX))
            self.assertIn(row["direction"], {"up", "down", "neutral"})

    def test_endpoint_returns_expected_structure(self) -> None:
        response = get_supply_chain_daily_route(as_of_date=date(2026, 3, 14), db=self.db)
        self.assertIsNotNone(response.as_of_date)
        self.assertIsNotNone(response.macro_state_id)
        self.assertGreater(len(response.node_snapshots), 0)
        self.assertGreater(len(response.basket_supply), 0)
        self.assertGreater(len(response.job_pressure), 0)
        self.assertIn("constants_version", response.debug_meta)

    def test_graceful_failure_when_no_macro_state_exists(self) -> None:
        empty_engine = create_engine("sqlite:///:memory:", future=True)
        EmptySession = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=empty_engine,
            future=True,
        )
        Base.metadata.create_all(
            bind=empty_engine,
            tables=[MacroDailyState.__table__],
        )
        empty_db = EmptySession()
        try:
            with self.assertRaises(SupplyChainNotFoundError):
                compute_supply_chain_daily_snapshot(empty_db)

            with self.assertRaises(HTTPException) as exc:
                get_supply_chain_daily_route(as_of_date=None, db=empty_db)
            self.assertEqual(exc.exception.status_code, 404)
        finally:
            empty_db.close()
            empty_engine.dispose()

    def test_macro_condition_changes_shift_supply_chain_results(self) -> None:
        oil_spike = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 11))
        relief = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 13))

        oil_nodes = {row["node_key"]: row for row in oil_spike["node_snapshots"]}
        relief_nodes = {row["node_key"]: row for row in relief["node_snapshots"]}
        self.assertLess(oil_nodes["trucking"]["availability"], relief_nodes["trucking"]["availability"])

        oil_baskets = {row["basket_key"]: row for row in oil_spike["basket_supply"]}
        relief_baskets = {row["basket_key"]: row for row in relief["basket_supply"]}
        self.assertLess(oil_baskets["produce"]["supply_multiplier"], relief_baskets["produce"]["supply_multiplier"])

    def test_produce_often_more_fragile_than_essentials_during_oil_spike(self) -> None:
        oil_spike = compute_supply_chain_daily_snapshot(self.db, as_of_date=date(2026, 3, 11))
        baskets = {row["basket_key"]: row for row in oil_spike["basket_supply"]}
        self.assertLessEqual(
            baskets["produce"]["supply_multiplier"],
            baskets["essentials"]["supply_multiplier"],
        )


if __name__ == "__main__":
    unittest.main()
