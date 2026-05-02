from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-jwt"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import player as player_api
from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_black_swan_event import PlayerBlackSwanEvent
from app.models.stock_daily_price import StockDailyPrice
from app.services.black_swan_service import evaluate_black_swan_for_player


class BlackSwanServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                Player.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                StockDailyPrice.__table__,
                DailyEconomyEvent.__table__,
                PlayerBlackSwanEvent.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.player = Player(
            id=uuid.uuid4(),
            display_name="Black Swan Player",
            cash=Decimal("1000.00"),
            debt_xgp=Decimal("0.00"),
            credit_score=650,
            net_worth=Decimal("1000.00"),
            run_status="active",
        )
        self.db.add(self.player)
        self.db.commit()
        self.db.refresh(self.player)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _client(self) -> TestClient:
        app = FastAPI()
        app.include_router(player_api.router, prefix="/player")

        def override_get_db():
            yield self.db

        app.dependency_overrides[player_api.get_db] = override_get_db
        return TestClient(app)

    def _add_macro(
        self,
        *,
        day: int,
        oil: str = "100.00",
        inflation: str = "2.00",
        unemployment: str = "5.00",
        confidence: str = "50.00",
        supply: str = "0.00",
    ) -> None:
        self.db.add(
            MacroDailyState(
                day=day,
                oil_index=Decimal(oil),
                inflation_rate=Decimal(inflation),
                unemployment_rate=Decimal(unemployment),
                consumer_confidence=Decimal(confidence),
                supply_chain_stress=Decimal(supply),
            )
        )
        self.db.commit()

    def _add_high_event(self, *, day: int, headline: str = "Citywide shutdown shock") -> DailyEconomyEvent:
        row = DailyEconomyEvent(
            day=day,
            event_key=f"shock_{day}",
            headline=headline,
            summary="A high-impact event hit several parts of the city.",
            event_category="supply_chain",
            sentiment="negative",
            severity=Decimal("2.90"),
            magnitude=0.9,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_candidate_created_for_oil_move_at_least_five_percent(self) -> None:
        self._add_macro(day=1, oil="100.00")
        self._add_macro(day=2, oil="106.00")

        row = evaluate_black_swan_for_player(self.db, self.player, day_number=2, commit=True)

        self.assertIsNotNone(row)
        self.assertEqual(row.event_type, "oil_shock")
        self.assertEqual(row.day, 2)

    def test_candidate_created_for_inflation_move_at_least_point_two_five(self) -> None:
        self._add_macro(day=1, inflation="2.00")
        self._add_macro(day=2, inflation="2.30")

        row = evaluate_black_swan_for_player(self.db, self.player, day_number=2, commit=True)

        self.assertIsNotNone(row)
        self.assertEqual(row.event_type, "inflation_spike")

    def test_no_candidate_for_small_normal_moves(self) -> None:
        self._add_macro(day=1, oil="100.00", inflation="2.00", unemployment="5.00", confidence="50.00", supply="5.00")
        self._add_macro(day=2, oil="101.00", inflation="2.05", unemployment="5.10", confidence="49.00", supply="6.00")

        row = evaluate_black_swan_for_player(self.db, self.player, day_number=2, commit=True)

        self.assertIsNone(row)
        self.assertEqual(self.db.query(PlayerBlackSwanEvent).count(), 0)

    def test_cooldown_prevents_another_within_fourteen_days(self) -> None:
        self.db.add(
            PlayerBlackSwanEvent(
                player_id=self.player.id,
                day=5,
                event_type="oil_shock",
                title="Old shock",
                description="Old shock.",
                severity_score=Decimal("550.00"),
                payload_json="{}",
            )
        )
        self.db.commit()
        self._add_macro(day=9, oil="100.00")
        self._add_macro(day=10, oil="107.00")

        row = evaluate_black_swan_for_player(self.db, self.player, day_number=10, commit=True)

        self.assertIsNone(row)
        self.assertEqual(self.db.query(PlayerBlackSwanEvent).count(), 1)

    def test_highest_severity_selected_if_multiple_candidates(self) -> None:
        self._add_macro(day=1, oil="100.00")
        self._add_macro(day=2, oil="106.00")
        self._add_high_event(day=2, headline="Port closure freezes deliveries")

        row = evaluate_black_swan_for_player(self.db, self.player, day_number=2, commit=True)

        self.assertIsNotNone(row)
        self.assertEqual(row.title, "Port closure freezes deliveries")
        self.assertEqual(row.event_type, "supply_chain")

    def test_pending_endpoint_returns_unseen_event(self) -> None:
        row = PlayerBlackSwanEvent(
            player_id=self.player.id,
            day=3,
            event_type="oil_shock",
            title="Oil shock hits",
            description="Fuel costs moved sharply.",
            severity_score=Decimal("560.00"),
            payload_json='{"affected_systems":["Fuel"],"what_changed_today":["Oil moved"],"what_this_means":["Plan carefully"]}',
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        response = self._client().get(f"/player/{self.player.id}/black-swan/pending")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(row.id))
        self.assertEqual(payload["push_payload"]["type"], "black_swan")

    def test_seen_endpoint_marks_event_seen(self) -> None:
        row = PlayerBlackSwanEvent(
            player_id=self.player.id,
            day=3,
            event_type="oil_shock",
            title="Oil shock hits",
            description="Fuel costs moved sharply.",
            severity_score=Decimal("560.00"),
            payload_json="{}",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        response = self._client().post(f"/player/{self.player.id}/black-swan/{row.id}/seen")

        self.assertEqual(response.status_code, 200)
        self.db.refresh(row)
        self.assertIsNotNone(row.seen_at)
        self.assertIsNotNone(response.json()["seen_at"])

    def test_retired_player_skipped(self) -> None:
        self.player.run_status = "retired"
        self.db.commit()
        self._add_macro(day=1, oil="100.00")
        self._add_macro(day=2, oil="106.00")

        row = evaluate_black_swan_for_player(self.db, self.player, day_number=2, commit=True)

        self.assertIsNone(row)
        self.assertEqual(self.db.query(PlayerBlackSwanEvent).count(), 0)


if __name__ == "__main__":
    unittest.main()
