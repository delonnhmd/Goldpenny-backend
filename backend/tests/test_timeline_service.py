from __future__ import annotations

import os
import time
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
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_settlement_log import DailySettlementLog
from app.models.game_state import GameState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_black_swan_event import PlayerBlackSwanEvent
from app.models.player_progression_state import PlayerProgressionState
from app.services.timeline_service import build_player_timeline


class TimelineServiceTests(unittest.TestCase):
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
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerProgressionState.__table__,
                DailyEconomyEvent.__table__,
                PlayerBlackSwanEvent.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.game_state = GameState(current_day=1, day_status="open")
        self.player = Player(
            id=uuid.uuid4(),
            display_name="Timeline Player",
            cash=Decimal("1000.00"),
            debt_xgp=Decimal("0.00"),
            credit_score=650,
            net_worth=Decimal("1000.00"),
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

    def _add_economy_event(
        self,
        *,
        day: int,
        headline: str,
        severity: str,
        summary: str | None = None,
    ) -> None:
        self.db.add(
            DailyEconomyEvent(
                day=day,
                event_key=f"event_{day}_{headline[:8]}",
                headline=headline,
                summary=summary,
                event_category="energy",
                sentiment="negative",
                severity=Decimal(severity),
            )
        )
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
        missed_payment: bool = False,
        distress_score: str = "0.00",
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
                income_xgp=Decimal("0.00"),
                expenses_xgp=Decimal("0.00"),
                debt_payment_due_xgp=Decimal("75.00"),
                debt_payment_missed=missed_payment,
                late_fee_xgp=Decimal("12.00") if missed_payment else Decimal("0.00"),
                distress_score_after=Decimal(distress_score),
                credit_score_after=640,
                summary_json="{}",
            )
        )
        self.db.commit()

    def _add_daily_state(
        self,
        *,
        day: int,
        missed_shift: bool = False,
        stress_end: int = 0,
        health_end: int = 100,
    ) -> None:
        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=day,
                missed_shift=missed_shift,
                did_settlement=True,
                stress_start=20,
                stress_end=stress_end,
                health_start=100,
                health_end=health_end,
                missed_penalty=Decimal("25.00") if missed_shift else Decimal("0.00"),
            )
        )
        self.db.commit()

    def _add_business(self, *, created_day: int = 2) -> PlayerBusiness:
        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="fruit_shop",
            business_name="Fruit Shop",
            created_day=created_day,
            is_active=True,
        )
        self.db.add(business)
        self.db.commit()
        self.db.refresh(business)
        return business

    def _add_business_log(
        self,
        *,
        business: PlayerBusiness,
        day: int,
        net_profit: str,
        inventory_end_units: str = "20.00",
        spoilage: str = "0.00",
    ) -> None:
        self.db.add(
            BusinessDailyLog(
                business_id=business.id,
                player_id=self.player.id,
                day=day,
                business_type=business.business_id,
                region_key="suburban",
                gross_revenue_xgp=Decimal("500.00"),
                input_cost_xgp=Decimal("100.00"),
                labor_cost_xgp=Decimal("0.00"),
                fuel_cost_xgp=Decimal("0.00"),
                maintenance_cost_xgp=Decimal("0.00"),
                spoilage_cost_xgp=Decimal(spoilage),
                overhead_cost_xgp=Decimal("20.00"),
                net_profit_xgp=Decimal(net_profit),
                units_sold=12,
                inventory_start_units=Decimal("24.00"),
                inventory_end_units=Decimal(inventory_end_units),
                demand_signal=Decimal("1.00"),
                demand_score=Decimal("70.00"),
                utilization_pct=Decimal("0.80"),
            )
        )
        self.db.commit()

    def test_timeline_returns_events(self) -> None:
        self._set_day(12)
        self._add_economy_event(day=12, headline="Oil shock increased costs", severity="2.30")

        response = self._client().get(f"/player/{self.player.id}/timeline")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload), 1)
        self.assertEqual(payload[0]["day"], 12)
        for key in ["day", "type", "title", "description", "impact_level", "icon"]:
            self.assertIn(key, payload[0])

    def test_events_are_filtered_not_every_day(self) -> None:
        self._set_day(30)
        for day in range(1, 31):
            self._add_economy_event(day=day, headline=f"Routine day {day}", severity="0.50")

        payload = build_player_timeline(self.db, self.player.id)

        self.assertEqual(payload, [])

    def test_major_events_appear(self) -> None:
        self._set_day(20)
        business = self._add_business(created_day=4)
        self._add_business_log(business=business, day=8, net_profit="600.00")
        self._add_snapshot(day=1, net_worth="-50.00")
        self._add_snapshot(day=9, net_worth="150.00", cash="150.00")
        self._add_daily_state(day=10, missed_shift=True, stress_end=88)
        self._add_settlement(day=12, missed_payment=True)
        self._add_economy_event(day=15, headline="Oil shock increased food and fuel costs", severity="2.40")

        payload = build_player_timeline(self.db, self.player.id)
        titles = {event["title"] for event in payload}

        self.assertIn("First business opened", titles)
        self.assertIn("Business profit spike", titles)
        self.assertIn("First positive net worth", titles)
        self.assertIn("Missed work day", titles)
        self.assertIn("Missed payment", titles)
        self.assertIn("Oil shock increased food and fuel costs", titles)

    def test_black_swan_event_appears_as_high_impact_economy_event(self) -> None:
        self._set_day(22)
        self.db.add(
            PlayerBlackSwanEvent(
                player_id=self.player.id,
                day=22,
                event_type="oil_shock",
                title="Oil Shock Hits the City",
                description="Fuel costs surged across the city.",
                severity_score=Decimal("560.00"),
                payload_json="{}",
            )
        )
        self.db.commit()

        payload = build_player_timeline(self.db, self.player.id)

        self.assertEqual(payload[0]["title"], "Oil Shock Hits the City")
        self.assertEqual(payload[0]["type"], "economy")
        self.assertEqual(payload[0]["impact_level"], "high")
        self.assertEqual(payload[0]["icon"], "alert-triangle")

    def test_ordering_latest_first(self) -> None:
        self._set_day(12)
        self._add_snapshot(day=3, net_worth="100.00", cash="100.00")
        self._add_economy_event(day=7, headline="Major economy shift", severity="2.00")
        self._add_settlement(day=12, missed_payment=True)

        payload = build_player_timeline(self.db, self.player.id)
        days = [event["day"] for event in payload]

        self.assertEqual(days, sorted(days, reverse=True))
        self.assertEqual(days[0], 12)

    def test_no_crash_if_data_missing(self) -> None:
        self._set_day(45)

        response = self._client().get(f"/player/{self.player.id}/timeline")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_performance_acceptable_for_long_runs(self) -> None:
        self._set_day(730)
        for day in range(1, 731):
            self.db.add(
                DailyEconomyEvent(
                    day=day,
                    event_key=f"routine_{day}",
                    headline=f"Routine economy day {day}",
                    event_category="consumer",
                    sentiment="neutral",
                    severity=Decimal("0.40"),
                )
            )
            self.db.add(
                PlayerNetWorthSnapshot(
                    player_id=self.player.id,
                    day=day,
                    cash_xgp=Decimal("100.00"),
                    bank_savings_xgp=Decimal("0.00"),
                    stock_market_value_xgp=Decimal("0.00"),
                    business_value_xgp=Decimal("0.00"),
                    inventory_value_xgp=Decimal("0.00"),
                    total_assets_xgp=Decimal("100.00"),
                    debt_xgp=Decimal("0.00"),
                    net_worth_xgp=Decimal("100.00"),
                )
            )
        self.db.add(
            DailyEconomyEvent(
                day=731,
                event_key="too_future",
                headline="Future event",
                event_category="energy",
                sentiment="negative",
                severity=Decimal("2.50"),
            )
        )
        self.db.commit()

        start = time.perf_counter()
        payload = build_player_timeline(self.db, self.player.id, limit=50)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0)
        self.assertLess(len(payload), 50)
        self.assertLess(len(payload), 730)


if __name__ == "__main__":
    unittest.main()
