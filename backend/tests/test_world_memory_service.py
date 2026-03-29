import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_world_memory_service.db")

from app.db.database import Base
from app.engine.world_memory_service import (
    decay_world_memory,
    detect_recurring_patterns,
    update_world_memory,
)
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


class WorldMemoryServiceTests(unittest.TestCase):
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
        user = User(email=f"step30-service-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="World Memory Service Tester",
            cash=Decimal("900.00"),
            debt_xgp=Decimal("1500.00"),
            stress=74,
            health=67,
            region="downtown",
            main_job="delivery_driver",
            productivity_modifier=Decimal("0.88"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("940"),
                monthly_utilities_cost_xgp=Decimal("140"),
                monthly_transport_base_xgp=Decimal("200"),
                commute_mode="car",
                active_flag=True,
            )
        )

        fruit_business = PlayerBusiness(
            player_id=self.player.id,
            business_id="fruit_shop",
            region="downtown",
            business_level=1,
            operating_mode="aggressive_markup",
            is_active=True,
        )
        truck_business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            region="downtown",
            business_level=1,
            operating_mode="premium_menu",
            is_active=True,
        )
        self.db.add_all([fruit_business, truck_business])
        self.db.flush()

        for day in range(1, 6):
            as_of = date(2026, 1, day)
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.70") + Decimal(str(day)) * Decimal("0.08"),
                    interest_rate=Decimal("4.00"),
                    unemployment_rate=Decimal("5.10"),
                    oil_index=Decimal("110.0") + Decimal(str(day)),
                    consumer_confidence=Decimal("47.8") - Decimal(str(day)) * Decimal("0.2"),
                    supply_chain_stress=Decimal("1.02") + Decimal(str(day)) * Decimal("0.03"),
                    event_headline=f"Pressure day {day}",
                    event_summary="Persistent pressure sequence.",
                )
            )
            self.db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.produce,
                    price_index=Decimal("11.0") + Decimal(str(day)) * Decimal("0.25"),
                    daily_change_pct=Decimal("0.45"),
                    supply_pressure=Decimal("1.10"),
                    demand_pressure=Decimal("1.05"),
                )
            )
            self.db.add(
                HousingDailyLog(
                    player_id=self.player.id,
                    day=day,
                    region="downtown",
                    housing_cost_xgp=Decimal("31.33"),
                    utilities_cost_xgp=Decimal("4.67"),
                    commute_hours=Decimal("1.20") + Decimal(str(day)) * Decimal("0.08"),
                    commute_fuel_cost_xgp=Decimal("4.50") + Decimal(str(day)) * Decimal("0.10"),
                    commute_pressure=Decimal("1.02") + Decimal(str(day)) * Decimal("0.04"),
                    stress_delta=2,
                    opportunity_modifier=Decimal("1.08"),
                    region_stress_delta=Decimal("0.95"),
                    region_opportunity_modifier=Decimal("0.08"),
                    region_business_demand_modifier=Decimal("0.10"),
                    region_side_income_modifier=Decimal("0.09"),
                    networking_modifier=Decimal("0.10"),
                    opportunity_quality_signal=Decimal("1.08"),
                )
            )
            self.db.add(
                BusinessDailyLog(
                    business_id=fruit_business.id,
                    player_id=self.player.id,
                    day=day,
                    business_type="fruit_shop",
                    region_key="downtown",
                    gross_revenue_xgp=Decimal("64.00"),
                    input_cost_xgp=Decimal("49.00"),
                    fuel_cost_xgp=Decimal("0.00"),
                    maintenance_cost_xgp=Decimal("0.00"),
                    spoilage_cost_xgp=Decimal("7.00"),
                    overhead_cost_xgp=Decimal("12.00"),
                    net_profit_xgp=Decimal("-4.00"),
                    units_sold=20,
                    inventory_start_units=Decimal("45"),
                    inventory_end_units=Decimal("14"),
                    demand_signal=Decimal("0.79"),
                    demand_score=Decimal("0.79"),
                    utilization_pct=Decimal("0.62"),
                )
            )
            self.db.add(
                BusinessDailyLog(
                    business_id=truck_business.id,
                    player_id=self.player.id,
                    day=day,
                    business_type="food_truck",
                    region_key="downtown",
                    gross_revenue_xgp=Decimal("78.00"),
                    input_cost_xgp=Decimal("57.00"),
                    fuel_cost_xgp=Decimal("10.20"),
                    maintenance_cost_xgp=Decimal("1.30"),
                    spoilage_cost_xgp=Decimal("0.00"),
                    overhead_cost_xgp=Decimal("15.00"),
                    net_profit_xgp=Decimal("-5.50"),
                    units_sold=21,
                    inventory_start_units=Decimal("40"),
                    inventory_end_units=Decimal("10"),
                    demand_signal=Decimal("0.81"),
                    demand_score=Decimal("0.81"),
                    utilization_pct=Decimal("0.64"),
                )
            )
            self.db.add(
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=day,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=70 + day - 1,
                    stress_after=72 + day - 1,
                    health_before=69 - day + 1,
                    health_after=68 - day + 1,
                    cash_before=Decimal("950.00") - Decimal(str(day - 1)) * Decimal("18.00"),
                    cash_after=Decimal("932.00") - Decimal(str(day - 1)) * Decimal("18.00"),
                    income_xgp=Decimal("162.00"),
                    expenses_xgp=Decimal("204.00"),
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
                    overtime_hours=Decimal("2.1"),
                    commute_hours=Decimal("1.20") + Decimal(str(day)) * Decimal("0.08"),
                    sleep_hours=Decimal("5.5"),
                    recovery_hours=Decimal("0.8"),
                    productivity_modifier=Decimal("0.88"),
                )
            )
            self.db.add(
                FinancialDistressLog(
                    player_id=self.player.id,
                    day=day,
                    as_of_date=as_of,
                    debt_payment_due_xgp=Decimal("31.00"),
                    debt_payment_paid_xgp=Decimal("18.00"),
                    debt_payment_missed=False,
                    late_fee_xgp=Decimal("0.00"),
                    accrued_interest_xgp=Decimal("3.10"),
                    credit_score_before=650 - day,
                    credit_score_after=649 - day,
                    credit_score_delta=-1,
                    distress_state_before="stretched",
                    distress_state_after="stretched",
                    distress_score_before=Decimal("56.0") + Decimal(str(day - 1)),
                    distress_score_after=Decimal("57.0") + Decimal(str(day - 1)),
                )
            )

    def test_detect_recurring_patterns_finds_multi_system_persistence(self) -> None:
        payload = detect_recurring_patterns(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 5),
        )
        self.assertEqual(payload["player_id"], str(self.player.id))
        self.assertGreaterEqual(len(payload["items"]), 4)

        keys = {item["pattern_key"] for item in payload["items"]}
        self.assertIn("commute_congestion_building", keys)
        categories = {item["category"] for item in payload["items"]}
        self.assertTrue({"macro", "commute", "business", "life"}.issubset(categories))

    def test_update_world_memory_persists_snapshot_and_pattern_rows(self) -> None:
        snapshot = update_world_memory(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 5),
        )
        self.assertEqual(snapshot["player_id"], str(self.player.id))
        self.assertGreater(snapshot["macro_pressure_score"], 0)
        self.assertGreater(snapshot["commute_pressure_score"], 0)
        self.assertGreaterEqual(len(snapshot["dominant_patterns"]), 1)

        state = (
            self.db.query(PlayerWorldMemoryState)
            .filter(PlayerWorldMemoryState.player_id == self.player.id)
            .first()
        )
        self.assertIsNotNone(state)
        history_count = (
            self.db.query(PlayerWorldPatternHistory)
            .filter(PlayerWorldPatternHistory.player_id == self.player.id)
            .count()
        )
        self.assertGreater(history_count, 0)

    def test_decay_transitions_old_patterns_out_of_active(self) -> None:
        update_world_memory(self.db, str(self.player.id), as_of_date=date(2026, 1, 5))
        decay_payload = decay_world_memory(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 12),
            active_pattern_keys=set(),
        )
        self.assertGreater(decay_payload["decayed_rows"], 0)

        rows = (
            self.db.query(PlayerWorldPatternHistory)
            .filter(PlayerWorldPatternHistory.player_id == self.player.id)
            .all()
        )
        statuses = {str(row.status) for row in rows}
        self.assertTrue("fading" in statuses or "resolved" in statuses)


if __name__ == "__main__":
    unittest.main()
