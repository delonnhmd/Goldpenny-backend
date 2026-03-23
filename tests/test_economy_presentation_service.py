import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_economy_presentation_service.db")

from app.db.database import Base
from app.engine.economy_presentation_service import (
    build_economy_presentation_summary,
    build_business_margin_summary,
    build_commute_pressure_summary,
    build_future_opportunity_teasers,
    build_market_overview,
    build_price_trend_summary,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_housing_state import PlayerHousingState
from app.models.supply_chain_daily_snapshot import SupplyChainDailySnapshot
from app.models.supply_chain_node_state import SupplyChainNodeState
from app.models.user import User


class EconomyPresentationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                DailySettlementLog.__table__,
                SupplyChainDailySnapshot.__table__,
                SupplyChainNodeState.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"eco-pres-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Presentation Tester",
            cash=Decimal("1300.00"),
            debt_xgp=Decimal("420.00"),
            stress=49,
            health=88,
            region="suburban",
            main_job="retail_worker",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add_all(
            [
                MacroDailyState(
                    day=1,
                    inflation_rate=Decimal("2.2"),
                    interest_rate=Decimal("4.0"),
                    unemployment_rate=Decimal("5.7"),
                    oil_index=Decimal("101.0"),
                    consumer_confidence=Decimal("53.0"),
                    supply_chain_stress=Decimal("0.70"),
                    event_headline="Baseline",
                    event_summary="Baseline day.",
                ),
                MacroDailyState(
                    day=2,
                    inflation_rate=Decimal("2.9"),
                    interest_rate=Decimal("4.1"),
                    unemployment_rate=Decimal("5.4"),
                    oil_index=Decimal("116.0"),
                    consumer_confidence=Decimal("48.0"),
                    supply_chain_stress=Decimal("1.15"),
                    event_headline="Pressure day",
                    event_summary="Costs and supply pressure rose.",
                ),
            ]
        )

        self.db.add_all(
            [
                BasketDailyPrice(day=1, basket_type=BasketType.essentials, price_index=Decimal("10.0"), daily_change_pct=Decimal("0.20"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=1, basket_type=BasketType.protein, price_index=Decimal("10.4"), daily_change_pct=Decimal("0.18"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=1, basket_type=BasketType.produce, price_index=Decimal("9.6"), daily_change_pct=Decimal("-0.05"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=1, basket_type=BasketType.convenience, price_index=Decimal("9.8"), daily_change_pct=Decimal("0.10"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=2, basket_type=BasketType.essentials, price_index=Decimal("10.9"), daily_change_pct=Decimal("0.90"), supply_pressure=Decimal("1.05"), demand_pressure=Decimal("1.03")),
                BasketDailyPrice(day=2, basket_type=BasketType.protein, price_index=Decimal("11.8"), daily_change_pct=Decimal("1.10"), supply_pressure=Decimal("1.06"), demand_pressure=Decimal("1.02")),
                BasketDailyPrice(day=2, basket_type=BasketType.produce, price_index=Decimal("11.2"), daily_change_pct=Decimal("1.60"), supply_pressure=Decimal("1.12"), demand_pressure=Decimal("1.05")),
                BasketDailyPrice(day=2, basket_type=BasketType.convenience, price_index=Decimal("10.4"), daily_change_pct=Decimal("0.60"), supply_pressure=Decimal("1.03"), demand_pressure=Decimal("1.06")),
            ]
        )

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="suburban",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("560"),
                monthly_utilities_cost_xgp=Decimal("110"),
                monthly_transport_base_xgp=Decimal("165"),
                commute_mode="car",
                business_demand_modifier=Decimal("0.93"),
                side_income_modifier=Decimal("0.95"),
                networking_modifier=Decimal("-0.04"),
                active_flag=True,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=2,
                region="suburban",
                housing_cost_xgp=Decimal("18.67"),
                utilities_cost_xgp=Decimal("3.67"),
                commute_hours=Decimal("1.45"),
                commute_fuel_cost_xgp=Decimal("4.20"),
                commute_pressure=Decimal("1.20"),
                stress_delta=1,
                opportunity_modifier=Decimal("0.95"),
                region_stress_delta=Decimal("0.75"),
                region_opportunity_modifier=Decimal("-0.05"),
                region_business_demand_modifier=Decimal("-0.06"),
                region_side_income_modifier=Decimal("-0.04"),
                networking_modifier=Decimal("-0.04"),
                opportunity_quality_signal=Decimal("0.94"),
            )
        )

        fruit_business = PlayerBusiness(
            player_id=self.player.id,
            business_id="fruit_shop",
            region="suburban",
            business_level=1,
            is_active=True,
        )
        truck_business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            region="suburban",
            business_level=1,
            is_active=True,
        )
        self.db.add_all([fruit_business, truck_business])
        self.db.flush()

        self.db.add_all(
            [
                BusinessDailyLog(
                    business_id=fruit_business.id,
                    player_id=self.player.id,
                    day=2,
                    business_type="fruit_shop",
                    region_key="suburban",
                    gross_revenue_xgp=Decimal("68.00"),
                    input_cost_xgp=Decimal("49.00"),
                    fuel_cost_xgp=Decimal("0.00"),
                    maintenance_cost_xgp=Decimal("0.00"),
                    spoilage_cost_xgp=Decimal("4.00"),
                    overhead_cost_xgp=Decimal("9.00"),
                    net_profit_xgp=Decimal("6.00"),
                    units_sold=24,
                    inventory_start_units=Decimal("48.00"),
                    inventory_end_units=Decimal("16.00"),
                    demand_signal=Decimal("0.88"),
                    demand_score=Decimal("0.88"),
                    utilization_pct=Decimal("0.66"),
                ),
                BusinessDailyLog(
                    business_id=truck_business.id,
                    player_id=self.player.id,
                    day=2,
                    business_type="food_truck",
                    region_key="suburban",
                    gross_revenue_xgp=Decimal("72.00"),
                    input_cost_xgp=Decimal("50.00"),
                    fuel_cost_xgp=Decimal("8.80"),
                    maintenance_cost_xgp=Decimal("0.00"),
                    spoilage_cost_xgp=Decimal("0.00"),
                    overhead_cost_xgp=Decimal("14.00"),
                    net_profit_xgp=Decimal("-0.80"),
                    units_sold=19,
                    inventory_start_units=Decimal("40.00"),
                    inventory_end_units=Decimal("9.00"),
                    demand_signal=Decimal("0.78"),
                    demand_score=Decimal("0.78"),
                    utilization_pct=Decimal("0.62"),
                ),
            ]
        )

        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=2,
                hours_before_reset=9,
                hours_after_reset=24,
                stress_before=47,
                stress_after=50,
                health_before=89,
                health_after=88,
                cash_before=Decimal("1300.00"),
                cash_after=Decimal("1272.00"),
                income_xgp=Decimal("170.00"),
                expenses_xgp=Decimal("198.00"),
                stock_pnl_xgp=Decimal("0.00"),
                debt_paid_xgp=Decimal("8.00"),
                health_change=-1,
                stress_change=3,
            )
        )

    def test_market_overview_reflects_macro_directions(self) -> None:
        payload = build_market_overview(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertEqual(payload["macro_trend_labels"]["oil_direction"], "rising")
        self.assertEqual(payload["macro_trend_labels"]["unemployment_direction"], "falling")
        self.assertIn(payload["current_market_mood"], {"mixed", "pressured", "supportive"})

    def test_price_trends_follow_basket_state(self) -> None:
        payload = build_price_trend_summary(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        by_key = {item["basket_key"]: item for item in payload["items"]}
        self.assertEqual(by_key["produce"]["short_term_trend"], "rising")
        self.assertGreater(by_key["produce"]["current_level"], by_key["essentials"]["current_level"] - 1)
        self.assertTrue(by_key["produce"]["primary_driver"])

    def test_business_margin_summary_uses_real_inputs(self) -> None:
        payload = build_business_margin_summary(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        by_key = {item["business_key"]: item for item in payload["items"]}
        self.assertEqual(set(by_key.keys()), {"fruit_shop", "food_truck"})
        self.assertIn(by_key["food_truck"]["cost_pressure"], {"moderate", "high"})
        self.assertGreaterEqual(len(by_key["fruit_shop"]["risk_factors"]), 1)

    def test_commute_pressure_has_housing_tradeoff_and_congestion(self) -> None:
        payload = build_commute_pressure_summary(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertIn("Move or rent closer", " ".join(payload["suggested_current_responses"]))
        self.assertIn("housing", payload["housing_tradeoff_summary"].lower())
        self.assertIn("congestion", payload["estimated_commute_burden"])

    def test_future_teasers_stay_locked(self) -> None:
        payload = build_future_opportunity_teasers(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertGreaterEqual(len(payload["teasers"]), 3)
        self.assertTrue(all(item["unlock_status"] == "locked" for item in payload["teasers"]))

    def test_summary_includes_supply_chain_brief_and_player_signals(self) -> None:
        payload = build_economy_presentation_summary(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertEqual(payload["current_day"], 2)
        self.assertIn("daily_brief", payload)
        self.assertIn("supply_chain_summary", payload)
        self.assertIn("supply_chain_story", payload)
        self.assertIn("player_warnings", payload)
        self.assertIn("player_opportunities", payload)
        self.assertGreaterEqual(len(payload["daily_brief"]["summary_lines"]), 1)


if __name__ == "__main__":
    unittest.main()
