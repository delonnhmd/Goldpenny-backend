import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_economy_presentation_api.db")

from app.api.economy_presentation import (
    get_business_margins,
    get_commute_pressure,
    get_economy_presentation_summary,
    get_future_teasers,
    get_market_overview,
    get_player_explainer,
    get_price_trends,
)
from app.db.database import Base
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


class EconomyPresentationApiTests(unittest.TestCase):
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
        user = User(email=f"eco-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="API Tester",
            cash=Decimal("1100.00"),
            debt_xgp=Decimal("500.00"),
            stress=45,
            health=90,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.7"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.0"),
                oil_index=Decimal("109.0"),
                consumer_confidence=Decimal("51.0"),
                supply_chain_stress=Decimal("0.95"),
                event_headline="Macro",
                event_summary="Macro update.",
            )
        )
        for basket_type, price in {
            BasketType.essentials: Decimal("10.8"),
            BasketType.protein: Decimal("11.4"),
            BasketType.produce: Decimal("10.9"),
            BasketType.convenience: Decimal("10.2"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.40"),
                    supply_pressure=Decimal("1.04"),
                    demand_pressure=Decimal("1.03"),
                )
            )

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("1050"),
                monthly_utilities_cost_xgp=Decimal("130"),
                monthly_transport_base_xgp=Decimal("120"),
                commute_mode="transit",
                business_demand_modifier=Decimal("1.12"),
                side_income_modifier=Decimal("1.08"),
                networking_modifier=Decimal("0.10"),
                active_flag=True,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=1,
                region="downtown",
                housing_cost_xgp=Decimal("35.00"),
                utilities_cost_xgp=Decimal("4.00"),
                commute_hours=Decimal("0.85"),
                commute_fuel_cost_xgp=Decimal("1.20"),
                commute_pressure=Decimal("0.45"),
                stress_delta=1,
                opportunity_modifier=Decimal("1.08"),
                region_stress_delta=Decimal("1.10"),
                region_opportunity_modifier=Decimal("0.09"),
                region_business_demand_modifier=Decimal("0.14"),
                region_side_income_modifier=Decimal("0.08"),
                networking_modifier=Decimal("0.10"),
                opportunity_quality_signal=Decimal("1.13"),
            )
        )

        fruit_business = PlayerBusiness(player_id=self.player.id, business_id="fruit_shop", region="downtown", business_level=1, is_active=True)
        truck_business = PlayerBusiness(player_id=self.player.id, business_id="food_truck", region="downtown", business_level=1, is_active=True)
        self.db.add_all([fruit_business, truck_business])
        self.db.flush()

        self.db.add(
            BusinessDailyLog(
                business_id=fruit_business.id,
                player_id=self.player.id,
                day=1,
                business_type="fruit_shop",
                region_key="downtown",
                gross_revenue_xgp=Decimal("82.0"),
                input_cost_xgp=Decimal("52.0"),
                fuel_cost_xgp=Decimal("0.0"),
                maintenance_cost_xgp=Decimal("0.0"),
                spoilage_cost_xgp=Decimal("3.0"),
                overhead_cost_xgp=Decimal("9.0"),
                net_profit_xgp=Decimal("18.0"),
                units_sold=24,
                inventory_start_units=Decimal("45"),
                inventory_end_units=Decimal("12"),
                demand_signal=Decimal("0.93"),
                demand_score=Decimal("0.93"),
                utilization_pct=Decimal("0.70"),
            )
        )
        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=1,
                hours_before_reset=10,
                hours_after_reset=24,
                stress_before=44,
                stress_after=46,
                health_before=90,
                health_after=89,
                cash_before=Decimal("1100.00"),
                cash_after=Decimal("1112.00"),
                income_xgp=Decimal("180"),
                expenses_xgp=Decimal("168"),
                stock_pnl_xgp=Decimal("0"),
                debt_paid_xgp=Decimal("7"),
                health_change=-1,
                stress_change=2,
            )
        )

    def test_market_overview_route(self) -> None:
        payload = get_market_overview(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        self.assertEqual(payload.player_id, str(self.player.id))
        self.assertTrue(payload.current_market_mood)
        self.assertTrue(payload.short_explainer)

    def test_price_and_margin_routes(self) -> None:
        price_payload = get_price_trends(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        margin_payload = get_business_margins(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        self.assertEqual(len(price_payload.items), 4)
        self.assertEqual(len(margin_payload.items), 2)

    def test_commute_explainer_and_teasers_routes(self) -> None:
        commute_payload = get_commute_pressure(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        explainer_payload = get_player_explainer(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        teaser_payload = get_future_teasers(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)

        self.assertIn("housing", commute_payload.housing_tradeoff_summary.lower())
        self.assertTrue(explainer_payload.why_commute_changed)
        self.assertTrue(all(item.unlock_status == "locked" for item in teaser_payload.teasers))

    def test_summary_route(self) -> None:
        payload = get_economy_presentation_summary(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(payload.player_id, str(self.player.id))
        self.assertEqual(payload.current_day, 1)
        self.assertEqual(payload.market_overview.player_id, str(self.player.id))
        self.assertEqual(payload.commute_pressure.player_id, str(self.player.id))
        self.assertGreaterEqual(len(payload.daily_brief.summary_lines), 1)
        self.assertTrue(payload.supply_chain_summary.short_summary)
        self.assertGreaterEqual(len(payload.player_warnings), 1)


if __name__ == "__main__":
    unittest.main()
