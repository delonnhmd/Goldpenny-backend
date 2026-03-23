import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_strategic_planning_api.db")

from app.api.strategic_planning import (
    get_business_plan,
    get_debt_vs_growth,
    get_future_preparation,
    get_housing_tradeoff,
    get_recovery_vs_push,
    get_short_horizon_plans,
    get_strategic_planning_summary,
    get_strategy_recommendation,
)
from app.db.database import Base
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


class StrategicPlanningApiTests(unittest.TestCase):
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
        user = User(email=f"step28-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="API Planner",
            cash=Decimal("780.00"),
            debt_xgp=Decimal("1320.00"),
            stress=68,
            health=71,
            region="suburban",
            productivity_modifier=Decimal("0.91"),
            distress_score=Decimal("58.0"),
            required_daily_debt_payment_xgp=Decimal("29.0"),
            main_job="delivery_driver",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.6"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.3"),
                oil_index=Decimal("114.0"),
                consumer_confidence=Decimal("49.0"),
                supply_chain_stress=Decimal("1.08"),
                event_headline="Macro pressure",
                event_summary="Costs remain elevated.",
            )
        )

        for basket_type, price in {
            BasketType.essentials: Decimal("10.9"),
            BasketType.protein: Decimal("11.5"),
            BasketType.produce: Decimal("11.1"),
            BasketType.convenience: Decimal("10.4"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.45"),
                    supply_pressure=Decimal("1.04"),
                    demand_pressure=Decimal("1.03"),
                )
            )

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="suburban",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("540"),
                monthly_utilities_cost_xgp=Decimal("105"),
                monthly_transport_base_xgp=Decimal("165"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=1,
                region="suburban",
                housing_cost_xgp=Decimal("18.00"),
                utilities_cost_xgp=Decimal("3.50"),
                commute_hours=Decimal("1.55"),
                commute_fuel_cost_xgp=Decimal("4.10"),
                commute_pressure=Decimal("1.15"),
                stress_delta=1,
                opportunity_modifier=Decimal("0.95"),
                region_stress_delta=Decimal("0.72"),
                region_opportunity_modifier=Decimal("-0.05"),
                region_business_demand_modifier=Decimal("-0.06"),
                region_side_income_modifier=Decimal("-0.05"),
                networking_modifier=Decimal("-0.05"),
                opportunity_quality_signal=Decimal("0.94"),
            )
        )

        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            region="suburban",
            business_level=1,
            operating_mode="standard_menu",
            is_active=True,
        )
        self.db.add(business)
        self.db.flush()
        self.db.add(
            BusinessDailyLog(
                business_id=business.id,
                player_id=self.player.id,
                day=1,
                business_type="food_truck",
                region_key="suburban",
                gross_revenue_xgp=Decimal("76.00"),
                input_cost_xgp=Decimal("53.00"),
                fuel_cost_xgp=Decimal("8.80"),
                maintenance_cost_xgp=Decimal("0.80"),
                spoilage_cost_xgp=Decimal("0.00"),
                overhead_cost_xgp=Decimal("14.00"),
                net_profit_xgp=Decimal("-0.60"),
                units_sold=20,
                inventory_start_units=Decimal("40"),
                inventory_end_units=Decimal("12"),
                demand_signal=Decimal("0.79"),
                demand_score=Decimal("0.79"),
                utilization_pct=Decimal("0.61"),
            )
        )

        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=1,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=66,
                stress_after=68,
                health_before=72,
                health_after=71,
                cash_before=Decimal("820.00"),
                cash_after=Decimal("780.00"),
                income_xgp=Decimal("160"),
                expenses_xgp=Decimal("200"),
                stock_pnl_xgp=Decimal("0"),
                debt_paid_xgp=Decimal("10"),
                health_change=-1,
                stress_change=2,
            )
        )

        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                overtime_hours=Decimal("2.0"),
                commute_hours=Decimal("1.55"),
                sleep_hours=Decimal("5.4"),
                recovery_hours=Decimal("0.9"),
                productivity_modifier=Decimal("0.91"),
            )
        )

        self.db.add(
            FinancialDistressLog(
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                debt_payment_due_xgp=Decimal("29.00"),
                debt_payment_paid_xgp=Decimal("20.00"),
                debt_payment_missed=False,
                late_fee_xgp=Decimal("0.00"),
                accrued_interest_xgp=Decimal("3.20"),
                credit_score_before=646,
                credit_score_after=642,
                credit_score_delta=-4,
                distress_state_before="stretched",
                distress_state_after="stretched",
                distress_score_before=Decimal("54.0"),
                distress_score_after=Decimal("58.0"),
                borrowing_cost_modifier=Decimal("1.10"),
                opportunity_access_penalty=Decimal("0.07"),
                business_risk_penalty=Decimal("0.06"),
                career_progress_penalty=Decimal("0.03"),
            )
        )

        self.db.add(
            CareerProgressLog(
                player_id=self.player.id,
                day_number=1,
                training_hours=Decimal("0.5"),
                skill_before=Decimal("1.9"),
                skill_after=Decimal("2.0"),
                skill_delta=Decimal("0.1"),
                performance_score=Decimal("0.70"),
                trailing_performance_score=Decimal("0.69"),
                promotion_progress=Decimal("0.34"),
            )
        )

    def test_plans_and_housing_routes(self) -> None:
        plans = get_short_horizon_plans(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        housing = get_housing_tradeoff(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        self.assertEqual(plans.player_id, str(self.player.id))
        self.assertGreaterEqual(len(plans.options), 3)
        self.assertEqual(housing.current_region, "suburban")
        self.assertIn("housing", housing.closer_housing_cost_pressure.lower())

    def test_debt_business_and_recovery_routes(self) -> None:
        debt = get_debt_vs_growth(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        business = get_business_plan(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        recovery = get_recovery_vs_push(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)

        self.assertGreaterEqual(len(debt.items), 3)
        self.assertEqual(len(business.items), 2)
        self.assertIn(recovery.current_pressure_level, {"moderate", "high"})

    def test_recommendation_future_and_summary_routes(self) -> None:
        recommendation = get_strategy_recommendation(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        future = get_future_preparation(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        summary = get_strategic_planning_summary(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)

        self.assertEqual(recommendation.player_id, str(self.player.id))
        self.assertTrue(recommendation.recommended_plan_key)
        self.assertTrue(all(item.unlock_status == "locked" for item in future.items))
        self.assertEqual(summary.player_id, str(self.player.id))
        self.assertEqual(summary.recommendation.recommended_plan_key, recommendation.recommended_plan_key)


if __name__ == "__main__":
    unittest.main()
