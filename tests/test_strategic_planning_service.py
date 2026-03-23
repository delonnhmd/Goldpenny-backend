import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_strategic_planning_service.db")

from app.db.database import Base
from app.engine.strategic_planning_service import (
    build_debt_vs_growth_analysis,
    build_housing_tradeoff_analysis,
    build_locked_future_path_preparation,
    build_recovery_vs_push_analysis,
    build_short_horizon_plan_options,
    build_strategic_planning_summary,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing_state import PlayerHousingState
from app.models.user import User


class StrategicPlanningServiceTests(unittest.TestCase):
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
                CareerProgressLog.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step28-service-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step 28 Tester",
            cash=Decimal("920.00"),
            debt_xgp=Decimal("1580.00"),
            stress=74,
            health=66,
            region="suburban",
            main_job="retail_worker",
            productivity_modifier=Decimal("0.88"),
            distress_score=Decimal("66.0"),
            required_daily_debt_payment_xgp=Decimal("32.0"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add_all(
            [
                MacroDailyState(
                    day=1,
                    inflation_rate=Decimal("2.1"),
                    interest_rate=Decimal("4.0"),
                    unemployment_rate=Decimal("5.6"),
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
                    oil_index=Decimal("118.0"),
                    consumer_confidence=Decimal("47.0"),
                    supply_chain_stress=Decimal("1.15"),
                    event_headline="Pressure",
                    event_summary="Costs rose under supply stress.",
                ),
            ]
        )

        self.db.add_all(
            [
                BasketDailyPrice(day=1, basket_type=BasketType.essentials, price_index=Decimal("10.0"), daily_change_pct=Decimal("0.20"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=1, basket_type=BasketType.protein, price_index=Decimal("10.2"), daily_change_pct=Decimal("0.10"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=1, basket_type=BasketType.produce, price_index=Decimal("9.8"), daily_change_pct=Decimal("0.05"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=1, basket_type=BasketType.convenience, price_index=Decimal("10.1"), daily_change_pct=Decimal("0.15"), supply_pressure=Decimal("1.00"), demand_pressure=Decimal("1.00")),
                BasketDailyPrice(day=2, basket_type=BasketType.essentials, price_index=Decimal("10.9"), daily_change_pct=Decimal("0.90"), supply_pressure=Decimal("1.05"), demand_pressure=Decimal("1.03")),
                BasketDailyPrice(day=2, basket_type=BasketType.protein, price_index=Decimal("11.8"), daily_change_pct=Decimal("1.10"), supply_pressure=Decimal("1.06"), demand_pressure=Decimal("1.03")),
                BasketDailyPrice(day=2, basket_type=BasketType.produce, price_index=Decimal("11.4"), daily_change_pct=Decimal("1.50"), supply_pressure=Decimal("1.12"), demand_pressure=Decimal("1.05")),
                BasketDailyPrice(day=2, basket_type=BasketType.convenience, price_index=Decimal("10.6"), daily_change_pct=Decimal("0.50"), supply_pressure=Decimal("1.03"), demand_pressure=Decimal("1.06")),
            ]
        )

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="suburban",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("560"),
                monthly_utilities_cost_xgp=Decimal("108"),
                monthly_transport_base_xgp=Decimal("170"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=2,
                region="suburban",
                housing_cost_xgp=Decimal("18.67"),
                utilities_cost_xgp=Decimal("3.60"),
                commute_hours=Decimal("1.70"),
                commute_fuel_cost_xgp=Decimal("4.40"),
                commute_pressure=Decimal("1.25"),
                stress_delta=1,
                opportunity_modifier=Decimal("0.95"),
                region_stress_delta=Decimal("0.80"),
                region_opportunity_modifier=Decimal("-0.05"),
                region_business_demand_modifier=Decimal("-0.06"),
                region_side_income_modifier=Decimal("-0.05"),
                networking_modifier=Decimal("-0.05"),
                opportunity_quality_signal=Decimal("0.93"),
            )
        )

        fruit_business = PlayerBusiness(
            player_id=self.player.id,
            business_id="fruit_shop",
            region="suburban",
            business_level=1,
            operating_mode="aggressive_markup",
            is_active=True,
        )
        truck_business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            region="suburban",
            business_level=1,
            operating_mode="premium_menu",
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
                    gross_revenue_xgp=Decimal("62.00"),
                    input_cost_xgp=Decimal("47.00"),
                    fuel_cost_xgp=Decimal("0.00"),
                    maintenance_cost_xgp=Decimal("0.00"),
                    spoilage_cost_xgp=Decimal("6.00"),
                    overhead_cost_xgp=Decimal("11.00"),
                    net_profit_xgp=Decimal("-2.00"),
                    units_sold=20,
                    inventory_start_units=Decimal("45.00"),
                    inventory_end_units=Decimal("16.00"),
                    demand_signal=Decimal("0.80"),
                    demand_score=Decimal("0.80"),
                    utilization_pct=Decimal("0.60"),
                ),
                BusinessDailyLog(
                    business_id=truck_business.id,
                    player_id=self.player.id,
                    day=2,
                    business_type="food_truck",
                    region_key="suburban",
                    gross_revenue_xgp=Decimal("84.00"),
                    input_cost_xgp=Decimal("55.00"),
                    fuel_cost_xgp=Decimal("9.20"),
                    maintenance_cost_xgp=Decimal("1.20"),
                    spoilage_cost_xgp=Decimal("0.00"),
                    overhead_cost_xgp=Decimal("14.00"),
                    net_profit_xgp=Decimal("4.60"),
                    units_sold=22,
                    inventory_start_units=Decimal("40.00"),
                    inventory_end_units=Decimal("11.00"),
                    demand_signal=Decimal("0.82"),
                    demand_score=Decimal("0.82"),
                    utilization_pct=Decimal("0.64"),
                ),
            ]
        )

        self.db.add_all(
            [
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=1,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=70,
                    stress_after=72,
                    health_before=68,
                    health_after=67,
                    cash_before=Decimal("980.00"),
                    cash_after=Decimal("955.00"),
                    income_xgp=Decimal("168.00"),
                    expenses_xgp=Decimal("193.00"),
                    stock_pnl_xgp=Decimal("0.00"),
                    debt_paid_xgp=Decimal("12.00"),
                    health_change=-1,
                    stress_change=2,
                ),
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=2,
                    hours_before_reset=7,
                    hours_after_reset=24,
                    stress_before=72,
                    stress_after=74,
                    health_before=67,
                    health_after=66,
                    cash_before=Decimal("955.00"),
                    cash_after=Decimal("920.00"),
                    income_xgp=Decimal("170.00"),
                    expenses_xgp=Decimal("205.00"),
                    stock_pnl_xgp=Decimal("0.00"),
                    debt_paid_xgp=Decimal("11.00"),
                    health_change=-1,
                    stress_change=2,
                ),
            ]
        )

        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=2,
                overtime_hours=Decimal("2.4"),
                commute_hours=Decimal("1.7"),
                sleep_hours=Decimal("5.2"),
                recovery_hours=Decimal("0.8"),
                productivity_modifier=Decimal("0.88"),
            )
        )

        self.db.add(
            FinancialDistressLog(
                player_id=self.player.id,
                day=2,
                as_of_date=date(2026, 1, 2),
                debt_payment_due_xgp=Decimal("32.00"),
                debt_payment_paid_xgp=Decimal("20.00"),
                debt_payment_missed=False,
                late_fee_xgp=Decimal("0.00"),
                accrued_interest_xgp=Decimal("4.00"),
                credit_score_before=640,
                credit_score_after=636,
                credit_score_delta=-4,
                distress_state_before="stretched",
                distress_state_after="distressed",
                distress_score_before=Decimal("58.0"),
                distress_score_after=Decimal("66.0"),
                borrowing_cost_modifier=Decimal("1.12"),
                opportunity_access_penalty=Decimal("0.08"),
                business_risk_penalty=Decimal("0.07"),
                career_progress_penalty=Decimal("0.04"),
            )
        )

        self.db.add_all(
            [
                CareerProgressLog(
                    player_id=self.player.id,
                    day_number=1,
                    training_hours=Decimal("0.5"),
                    skill_before=Decimal("2.1"),
                    skill_after=Decimal("2.2"),
                    skill_delta=Decimal("0.1"),
                    performance_score=Decimal("0.72"),
                    trailing_performance_score=Decimal("0.70"),
                    promotion_progress=Decimal("0.36"),
                ),
                CareerProgressLog(
                    player_id=self.player.id,
                    day_number=2,
                    training_hours=Decimal("0.4"),
                    skill_before=Decimal("2.2"),
                    skill_after=Decimal("2.3"),
                    skill_delta=Decimal("0.1"),
                    performance_score=Decimal("0.70"),
                    trailing_performance_score=Decimal("0.69"),
                    promotion_progress=Decimal("0.38"),
                ),
            ]
        )

    def test_short_horizon_plans_are_state_driven_and_deterministic(self) -> None:
        payload_a = build_short_horizon_plan_options(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        payload_b = build_short_horizon_plan_options(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        keys_a = [item["plan_key"] for item in payload_a["options"]]
        keys_b = [item["plan_key"] for item in payload_b["options"]]

        self.assertEqual(keys_a, keys_b)
        self.assertGreaterEqual(len(keys_a), 3)
        self.assertLessEqual(len(keys_a), 4)
        self.assertTrue(any(key in {"stabilize_finances", "housing_optimization"} for key in keys_a))

    def test_housing_tradeoff_emphasizes_commute_vs_cost(self) -> None:
        payload = build_housing_tradeoff_analysis(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertEqual(payload["current_region"], "suburban")
        self.assertIn("higher housing cost", payload["closer_housing_cost_pressure"])
        self.assertIn("time", payload["expected_time_delta_label"].lower())
        self.assertIn("move or rent closer", payload["short_recommendation"].lower())

    def test_debt_vs_growth_reflects_distress_and_liquidity(self) -> None:
        payload = build_debt_vs_growth_analysis(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        by_key = {item["option_key"]: item for item in payload["items"]}
        self.assertIn("pay_down_debt", by_key)
        self.assertGreater(by_key["pay_down_debt"]["defensive_score"], by_key["pay_down_debt"]["growth_score"])
        self.assertIn(by_key["pay_down_debt"]["liquidity_risk"], {"low", "moderate", "high"})

    def test_recovery_vs_push_uses_life_pressure_chain(self) -> None:
        payload = build_recovery_vs_push_analysis(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertIn(payload["current_pressure_level"], {"moderate", "high"})
        self.assertTrue(payload["recommendation_summary"])
        self.assertIn("recovery", payload["recommendation_summary"].lower())

    def test_future_preparation_stays_locked(self) -> None:
        payload = build_locked_future_path_preparation(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertGreaterEqual(len(payload["items"]), 3)
        self.assertTrue(all(item["unlock_status"] == "locked" for item in payload["items"]))
        self.assertIn("move_or_rent_closer", payload["debug_meta"]["current_practical_solutions"])

    def test_summary_contains_all_sections(self) -> None:
        payload = build_strategic_planning_summary(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertEqual(payload["player_id"], str(self.player.id))
        self.assertIn("plans", payload)
        self.assertIn("housing_tradeoff", payload)
        self.assertIn("recommendation", payload)
        self.assertIn("future_preparation", payload)


if __name__ == "__main__":
    unittest.main()
