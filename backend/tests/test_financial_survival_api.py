import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_financial_survival_api.db")

from app.api.financial_survival import (
    get_credit_impact_route,
    get_delinquency_state_route,
    get_financial_survival_system_summary_route,
    get_obligation_profile_route,
    get_payment_history_route,
    get_payment_risk_route,
    get_survival_summary_route,
)
from app.db.database import Base
from app.engine.financial_survival_service import apply_daily_financial_survival
from app.models.business_daily_log import BusinessDailyLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState
from app.models.user import User


class FinancialSurvivalApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                FinancialDistressLog.__table__,
                PlayerShockState.__table__,
                PlayerDelinquencyState.__table__,
                PlayerPaymentHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step36-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step36 API Tester",
            cash=Decimal("160.00"),
            debt_xgp=Decimal("2900.00"),
            credit_score=642,
            stress=71,
            health=70,
            region="downtown",
            main_job="delivery_driver",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("1120.00"),
                monthly_utilities_cost_xgp=Decimal("160.00"),
                monthly_transport_base_xgp=Decimal("205.00"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="delivery_driver",
                skill_level=1,
                monthly_pay_xgp=Decimal("1800.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("9.0"),
                productivity_modifier=Decimal("0.95"),
            )
        )
        self.db.add(
            PlayerShockState(
                player_id=self.player.id,
                shock_risk_score=Decimal("78.0"),
                financial_fragility_score=Decimal("69.0"),
                health_fragility_score=Decimal("63.0"),
                work_disruption_risk_score=Decimal("56.0"),
                recovery_capacity_score=Decimal("38.0"),
                recent_negative_streak=2,
                recent_recovery_support=0,
                recent_pressure_direction="rising",
                last_updated_on=1,
                last_updated_date=date(2026, 1, 1),
            )
        )
        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            business_type="food_truck",
            region="downtown",
            is_active=True,
            active_flag=True,
            tier=1,
            operating_mode="standard_menu",
        )
        self.db.add(business)
        self.db.flush()
        self.db.add(
            BusinessDailyLog(
                business_id=business.id,
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                business_type="food_truck",
                region_key="downtown",
                gross_revenue_xgp=Decimal("71.00"),
                input_cost_xgp=Decimal("55.00"),
                fuel_cost_xgp=Decimal("9.00"),
                overhead_cost_xgp=Decimal("24.00"),
                net_profit_xgp=Decimal("-17.00"),
                units_sold=19,
                inventory_start_units=Decimal("42"),
                inventory_end_units=Decimal("18"),
                demand_signal=Decimal("0.70"),
                demand_score=Decimal("0.70"),
                utilization_pct=Decimal("0.55"),
            )
        )

        # Seed at least one payment outcome so credit-impact/history routes are populated.
        apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.player.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )

    def test_financial_survival_routes_return_frontend_ready_shapes(self) -> None:
        obligation = get_obligation_profile_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            db=self.db,
        )
        risk = get_payment_risk_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            db=self.db,
        )
        delinquency = get_delinquency_state_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            db=self.db,
        )
        credit = get_credit_impact_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            db=self.db,
        )
        summary = get_survival_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            db=self.db,
        )
        history = get_payment_history_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            limit=20,
            db=self.db,
        )
        system = get_financial_survival_system_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            day_number=1,
            db=self.db,
        )

        self.assertEqual(obligation.player_id, str(self.player.id))
        self.assertEqual(risk.player_id, str(self.player.id))
        self.assertEqual(delinquency.player_id, str(self.player.id))
        self.assertEqual(summary.player_id, str(self.player.id))
        self.assertEqual(history.player_id, str(self.player.id))
        self.assertEqual(system.player_id, str(self.player.id))
        self.assertIn(
            delinquency.current_delinquency_stage,
            {"current", "stretched", "late", "delinquent", "critical"},
        )
        self.assertGreaterEqual(credit.credit_score_after, 300)
        self.assertLessEqual(credit.credit_score_after, 850)
        self.assertGreaterEqual(obligation.required_daily_burden_xgp, 0.0)
        self.assertGreaterEqual(obligation.liquidity_buffer_days, 0.0)
        self.assertTrue(isinstance(system.payment_history.entries, list))


if __name__ == "__main__":
    unittest.main()
