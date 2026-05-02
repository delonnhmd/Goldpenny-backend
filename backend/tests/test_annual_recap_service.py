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
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_settlement_log import DailySettlementLog
from app.models.game_state import GameState
from app.models.gameplay_transaction import GameplayTransaction
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing import PlayerHousing
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState
from app.services.annual_recap_service import annual_recap_title, build_player_annual_recap


class AnnualRecapServiceTests(unittest.TestCase):
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
                GameState.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                GameplayTransaction.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerBusiness.__table__,
                PlayerHousing.__table__,
                PlayerProgressionState.__table__,
                DailyEconomyEvent.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.game_state = GameState(current_day=1, day_status="open")
        self.player = Player(
            id=uuid.uuid4(),
            display_name="Annual Recap Player",
            cash=Decimal("1800.00"),
            debt_xgp=Decimal("2400.00"),
            credit_score=650,
            net_worth=Decimal("12500.00"),
        )
        self.db.add_all([self.game_state, self.player])
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

    def _set_day(self, day_number: int) -> None:
        self.game_state.current_day = day_number
        self.db.commit()

    def _add_snapshot(
        self,
        *,
        day: int,
        net_worth: str,
        cash: str = "0.00",
        debt: str = "0.00",
    ) -> None:
        self.db.add(
            PlayerNetWorthSnapshot(
                player_id=self.player.id,
                day=day,
                cash_xgp=Decimal(cash),
                bank_savings_xgp=Decimal("0.00"),
                stock_market_value_xgp=Decimal("0.00"),
                business_value_xgp=Decimal("0.00"),
                inventory_value_xgp=Decimal("0.00"),
                total_assets_xgp=Decimal(cash),
                debt_xgp=Decimal(debt),
                net_worth_xgp=Decimal(net_worth),
            )
        )
        self.db.commit()

    def _add_settlement(
        self,
        *,
        day: int,
        income: str,
        expenses: str,
        credit_score_after: int = 650,
        missed_payment: bool = False,
    ) -> None:
        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=day,
                hours_before_reset=0,
                hours_after_reset=24,
                stress_before=0,
                stress_after=0,
                health_before=100,
                health_after=100,
                cash_before=Decimal("0.00"),
                cash_after=Decimal("0.00"),
                income_xgp=Decimal(income),
                expenses_xgp=Decimal(expenses),
                debt_payment_missed=missed_payment,
                credit_score_after=credit_score_after,
                summary_json="{}",
            )
        )
        self.db.commit()

    def test_recap_unavailable_before_threshold_unless_debug_mode(self) -> None:
        self._set_day(29)
        client = self._client()

        unavailable = client.get(f"/player/{self.player.id}/annual-recap?year=1")
        debug_unavailable = client.get(f"/player/{self.player.id}/annual-recap?year=1&debug=true")

        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(debug_unavailable.status_code, 409)

        self._set_day(30)
        debug_response = client.get(f"/player/{self.player.id}/annual-recap?year=1&debug=true")

        self.assertEqual(debug_response.status_code, 200)
        self.assertEqual(debug_response.json()["days_survived"], 30)

    def test_recap_payload_returns_required_fields_without_event_history(self) -> None:
        self._set_day(365)
        self._add_snapshot(day=1, net_worth="0.00", cash="0.00", debt="0.00")
        self._add_snapshot(day=365, net_worth="12500.00", cash="1800.00", debt="2400.00")
        self._add_settlement(day=365, income="42000.00", expenses="31000.00", credit_score_after=650)
        self.db.add(
            PlayerBusiness(
                player_id=self.player.id,
                business_id="fruit_shop",
                created_day=120,
                is_active=True,
            )
        )
        self.db.add(
            PlayerHousing(
                player_id=self.player.id,
                housing_key="suburban_owned",
                region="suburban",
                occupancy_type="own",
                status="active",
                daily_cost=Decimal("0.00"),
                move_in_day=200,
                property_value=Decimal("8000.00"),
            )
        )
        self.db.add(
            PlayerProgressionState(
                player_id=self.player.id,
                login_streak_best=18,
                positive_cash_flow_streak_best=12,
            )
        )
        self.db.commit()

        payload = self._client().get(f"/player/{self.player.id}/annual-recap?year=1").json()

        for key in [
            "year",
            "days_survived",
            "starting_net_worth",
            "ending_net_worth",
            "net_worth_change",
            "cash",
            "debt",
            "credit_score",
            "businesses_owned",
            "land_owned",
            "best_streak",
            "total_income",
            "total_expenses",
            "biggest_win",
            "biggest_loss",
            "top_event",
            "title",
        ]:
            self.assertIn(key, payload)

        self.assertEqual(payload["year"], 1)
        self.assertEqual(payload["days_survived"], 365)
        self.assertEqual(payload["businesses_owned"], 1)
        self.assertEqual(payload["land_owned"], 1)
        self.assertEqual(payload["best_streak"], 18)
        self.assertEqual(payload["total_income"], 42000.0)
        self.assertEqual(payload["total_expenses"], 31000.0)
        self.assertEqual(payload["top_event"], "No major event recorded yet")

    def test_title_rules_work(self) -> None:
        self.assertEqual(annual_recap_title(Decimal("-1.00"), Decimal("0.00")), "Still Fighting")
        self.assertEqual(annual_recap_title(Decimal("0.00"), Decimal("0.00")), "Survivor")
        self.assertEqual(annual_recap_title(Decimal("1.00"), Decimal("10000.00")), "Survivor Turned Owner")
        self.assertEqual(annual_recap_title(Decimal("1.00"), Decimal("50000.00")), "Independent Operator")
        self.assertEqual(annual_recap_title(Decimal("1.00"), Decimal("100000.00")), "Financially Free")

    def test_net_worth_change_calculated_correctly(self) -> None:
        self._set_day(365)
        self._add_snapshot(day=1, net_worth="100.00")
        self._add_snapshot(day=365, net_worth="1250.00")

        payload = build_player_annual_recap(self.db, self.player.id, year=1)

        self.assertEqual(payload["starting_net_worth"], 100.0)
        self.assertEqual(payload["ending_net_worth"], 1250.0)
        self.assertEqual(payload["net_worth_change"], 1150.0)

    def test_top_event_uses_highest_severity_event_when_present(self) -> None:
        self._set_day(365)
        self.db.add_all(
            [
                DailyEconomyEvent(
                    day=4,
                    event_key="small_event",
                    headline="Minor supply delay",
                    event_category="supply_chain",
                    sentiment="negative",
                    severity=Decimal("0.50"),
                ),
                DailyEconomyEvent(
                    day=90,
                    event_key="oil_shock",
                    headline="Oil shock increased food and fuel costs",
                    event_category="energy",
                    sentiment="negative",
                    severity=Decimal("2.40"),
                ),
            ]
        )
        self.db.commit()

        payload = build_player_annual_recap(self.db, self.player.id, year=1)

        self.assertEqual(payload["top_event"], "Oil shock increased food and fuel costs")


if __name__ == "__main__":
    unittest.main()
