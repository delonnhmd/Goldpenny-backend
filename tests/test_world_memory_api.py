import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_world_memory_api.db")

from app.api.world_memory import (
    get_world_memory_local_pressure_route,
    get_world_memory_narrative_route,
    get_world_memory_patterns_route,
    get_world_memory_snapshot_route,
    get_world_memory_summary_route,
)
from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_world_memory_state import PlayerWorldMemoryState
from app.models.player_world_pattern_history import PlayerWorldPatternHistory
from app.models.user import User


class WorldMemoryApiTests(unittest.TestCase):
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
                PlayerDailyState.__table__,
                FinancialDistressLog.__table__,
                PlayerWorldMemoryState.__table__,
                PlayerWorldPatternHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step30-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="World Memory API Tester",
            cash=Decimal("1020.00"),
            debt_xgp=Decimal("980.00"),
            stress=64,
            health=75,
            region="suburban",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="suburban",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("560"),
                monthly_utilities_cost_xgp=Decimal("110"),
                monthly_transport_base_xgp=Decimal("165"),
                commute_mode="car",
                active_flag=True,
            )
        )

        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            region="suburban",
            business_level=1,
            is_active=True,
        )
        self.db.add(business)
        self.db.flush()

        for day in range(1, 5):
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.70"),
                    interest_rate=Decimal("4.0"),
                    unemployment_rate=Decimal("5.3"),
                    oil_index=Decimal("112") + Decimal(str(day)),
                    consumer_confidence=Decimal("47.5"),
                    supply_chain_stress=Decimal("1.06"),
                    event_headline="Pressure sequence",
                    event_summary="Continuity test sequence.",
                )
            )
            self.db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.produce,
                    price_index=Decimal("11.2"),
                    daily_change_pct=Decimal("0.50"),
                    supply_pressure=Decimal("1.08"),
                    demand_pressure=Decimal("1.05"),
                )
            )
            self.db.add(
                HousingDailyLog(
                    player_id=self.player.id,
                    day=day,
                    region="suburban",
                    housing_cost_xgp=Decimal("18.67"),
                    utilities_cost_xgp=Decimal("3.67"),
                    commute_hours=Decimal("1.30") + Decimal(str(day)) * Decimal("0.06"),
                    commute_fuel_cost_xgp=Decimal("4.20"),
                    commute_pressure=Decimal("1.01") + Decimal(str(day)) * Decimal("0.03"),
                    stress_delta=1,
                    opportunity_modifier=Decimal("0.95"),
                    region_stress_delta=Decimal("0.70"),
                    region_opportunity_modifier=Decimal("-0.04"),
                    region_business_demand_modifier=Decimal("-0.05"),
                    region_side_income_modifier=Decimal("-0.05"),
                    networking_modifier=Decimal("-0.05"),
                    opportunity_quality_signal=Decimal("0.94"),
                )
            )
            self.db.add(
                BusinessDailyLog(
                    business_id=business.id,
                    player_id=self.player.id,
                    day=day,
                    business_type="food_truck",
                    region_key="suburban",
                    gross_revenue_xgp=Decimal("80.00"),
                    input_cost_xgp=Decimal("60.00"),
                    fuel_cost_xgp=Decimal("9.50"),
                    maintenance_cost_xgp=Decimal("1.10"),
                    spoilage_cost_xgp=Decimal("0.00"),
                    overhead_cost_xgp=Decimal("14.00"),
                    net_profit_xgp=Decimal("-4.60"),
                    units_sold=20,
                    inventory_start_units=Decimal("40"),
                    inventory_end_units=Decimal("12"),
                    demand_signal=Decimal("0.78"),
                    demand_score=Decimal("0.78"),
                    utilization_pct=Decimal("0.60"),
                )
            )
            self.db.add(
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=day,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=62 + day - 1,
                    stress_after=64 + day - 1,
                    health_before=76 - day + 1,
                    health_after=75 - day + 1,
                    cash_before=Decimal("1035.00"),
                    cash_after=Decimal("1020.00"),
                    income_xgp=Decimal("160.00"),
                    expenses_xgp=Decimal("195.00"),
                    stock_pnl_xgp=Decimal("0"),
                    debt_paid_xgp=Decimal("10.00"),
                    health_change=-1,
                    stress_change=2,
                )
            )
            self.db.add(
                PlayerDailyState(
                    player_id=self.player.id,
                    day_number=day,
                    overtime_hours=Decimal("1.9"),
                    commute_hours=Decimal("1.30") + Decimal(str(day)) * Decimal("0.06"),
                    sleep_hours=Decimal("5.7"),
                    recovery_hours=Decimal("0.9"),
                    productivity_modifier=Decimal("0.90"),
                )
            )
            self.db.add(
                FinancialDistressLog(
                    player_id=self.player.id,
                    day=day,
                    as_of_date=date(2026, 1, day),
                    debt_payment_due_xgp=Decimal("28.00"),
                    debt_payment_paid_xgp=Decimal("18.00"),
                    debt_payment_missed=False,
                    late_fee_xgp=Decimal("0.00"),
                    accrued_interest_xgp=Decimal("2.80"),
                    credit_score_before=645,
                    credit_score_after=643,
                    credit_score_delta=-2,
                    distress_state_before="stretched",
                    distress_state_after="stretched",
                    distress_score_before=Decimal("54.0"),
                    distress_score_after=Decimal("56.0"),
                )
            )

    def test_snapshot_patterns_and_summary_routes_return_frontend_ready_shapes(self) -> None:
        snapshot = get_world_memory_snapshot_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 4),
            db=self.db,
        )
        patterns = get_world_memory_patterns_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 4),
            db=self.db,
        )
        narrative = get_world_memory_narrative_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 4),
            db=self.db,
        )
        local = get_world_memory_local_pressure_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 4),
            db=self.db,
        )
        summary = get_world_memory_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 4),
            db=self.db,
        )

        self.assertEqual(snapshot.player_id, str(self.player.id))
        self.assertGreaterEqual(len(patterns.items), 1)
        self.assertTrue(narrative.headline)
        self.assertIn("locked", narrative.future_locked_long_response.lower())
        self.assertIn("move", " ".join(local.practical_response_options).lower())
        self.assertEqual(summary.snapshot.player_id, str(self.player.id))
        self.assertEqual(summary.patterns.player_id, str(self.player.id))


if __name__ == "__main__":
    unittest.main()
