import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_consumer_borrowing_api.db")

from app.api.consumer_borrowing import (
    accept_borrowing_offer_route,
    get_borrowing_history_route,
    get_borrowing_options_route,
    get_borrowing_pressure_summary_route,
    get_borrowing_risk_summary_route,
    get_borrowing_system_summary_route,
    get_eligibility_profile_route,
    get_liquidity_state_route,
    get_loan_accounts_route,
)
from app.db.database import Base
from app.schemas.consumer_borrowing import BorrowingDecisionRequest
from app.models.business_daily_log import BusinessDailyLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState
from app.models.user import User


class ConsumerBorrowingApiTests(unittest.TestCase):
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
                PlayerBorrowingState.__table__,
                PlayerLoanAccount.__table__,
                PlayerBorrowingHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step37-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step37 API Tester",
            cash=Decimal("118.00"),
            debt_xgp=Decimal("1260.00"),
            credit_score=708,
            stress=46,
            health=84,
            region="downtown",
            main_job="delivery_driver",
            required_daily_debt_payment_xgp=Decimal("18.00"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("1020.00"),
                monthly_utilities_cost_xgp=Decimal("136.00"),
                monthly_transport_base_xgp=Decimal("168.00"),
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
                monthly_pay_xgp=Decimal("3160.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("9.0"),
                productivity_modifier=Decimal("1.00"),
            )
        )
        self.db.add(
            PlayerShockState(
                player_id=self.player.id,
                shock_risk_score=Decimal("38.0"),
                financial_fragility_score=Decimal("30.0"),
                health_fragility_score=Decimal("27.0"),
                work_disruption_risk_score=Decimal("24.0"),
                recovery_capacity_score=Decimal("74.0"),
                recent_negative_streak=0,
                recent_recovery_support=2,
                recent_pressure_direction="stable",
                last_updated_on=1,
                last_updated_date=date(2026, 1, 1),
            )
        )
        self.db.add(
            PlayerDelinquencyState(
                player_id=self.player.id,
                current_delinquency_stage="current",
                missed_payment_count_30d=0,
                late_payment_count_30d=0,
                days_under_payment_stress=0,
                last_missed_obligation_type=None,
                credit_pressure_score=Decimal("21.0"),
                financial_distress_score=Decimal("25.0"),
                last_updated_on=1,
                last_updated_date=date(2026, 1, 1),
                stage_debug_json="{}",
            )
        )
        self.db.add(
            PlayerPaymentHistory(
                player_id=self.player.id,
                day_number=1,
                as_of_date=date(2026, 1, 1),
                payment_outcome="paid_full",
                required_daily_burden_xgp=Decimal("34.00"),
                obligation_load_ratio=Decimal("0.78"),
                liquidity_buffer_days=Decimal("5.20"),
                total_due_xgp=Decimal("34.00"),
                total_paid_xgp=Decimal("34.00"),
                unpaid_amount_xgp=Decimal("0.00"),
                late_fee_xgp=Decimal("0.00"),
                credit_score_before=708,
                credit_score_after=708,
                credit_score_delta=0,
                delinquency_stage_before="current",
                delinquency_stage_after="current",
                survival_status_label="current",
                payment_pressure_label="manageable",
                full_pay_feasible=True,
                partial_pay_feasible=True,
                stress_impact_delta=Decimal("0.0"),
                due_obligations_json="[]",
                practical_actions_json="[]",
                summary_json="{}",
                debug_json="{}",
            )
        )
        self.db.add(
            FinancialDistressLog(
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                debt_payment_due_xgp=Decimal("18.00"),
                debt_payment_paid_xgp=Decimal("18.00"),
                debt_payment_missed=False,
                late_fee_xgp=Decimal("0.00"),
                accrued_interest_xgp=Decimal("1.10"),
                credit_score_before=708,
                credit_score_after=708,
                credit_score_delta=0,
                distress_state_before="stable",
                distress_state_after="stable",
                distress_score_before=Decimal("24.0"),
                distress_score_after=Decimal("24.0"),
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
                gross_revenue_xgp=Decimal("74.00"),
                input_cost_xgp=Decimal("56.00"),
                fuel_cost_xgp=Decimal("9.00"),
                overhead_cost_xgp=Decimal("20.00"),
                net_profit_xgp=Decimal("-11.00"),
                units_sold=18,
                inventory_start_units=Decimal("40"),
                inventory_end_units=Decimal("18"),
                demand_signal=Decimal("0.71"),
                demand_score=Decimal("0.71"),
                utilization_pct=Decimal("0.56"),
            )
        )

    def test_consumer_borrowing_routes_return_expected_shapes(self) -> None:
        eligibility = get_eligibility_profile_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            db=self.db,
        )
        liquidity = get_liquidity_state_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            db=self.db,
        )
        options = get_borrowing_options_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            include_locked=False,
            db=self.db,
        )
        risk = get_borrowing_risk_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            db=self.db,
        )
        pressure = get_borrowing_pressure_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            db=self.db,
        )

        self.assertEqual(eligibility.player_id, str(self.player.id))
        self.assertEqual(liquidity.player_id, str(self.player.id))
        self.assertEqual(options.player_id, str(self.player.id))
        self.assertEqual(risk.player_id, str(self.player.id))
        self.assertEqual(pressure.player_id, str(self.player.id))
        self.assertGreaterEqual(eligibility.borrowing_access_score, 0.0)
        self.assertLessEqual(eligibility.borrowing_access_score, 100.0)
        self.assertTrue(pressure.practical_current_actions)

    def test_accept_offer_and_history_routes(self) -> None:
        options = get_borrowing_options_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            include_locked=False,
            db=self.db,
        )
        self.assertGreater(len(options.items), 0)
        offer_key = str(options.items[0].offer_key)

        decision = accept_borrowing_offer_route(
            player_id=str(self.player.id),
            request=BorrowingDecisionRequest(offer_key=offer_key, principal_requested_xgp=90.0),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            db=self.db,
        )
        loans = get_loan_accounts_route(
            player_id=str(self.player.id),
            include_closed=False,
            db=self.db,
        )
        history = get_borrowing_history_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            limit=20,
            db=self.db,
        )
        summary = get_borrowing_system_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 2),
            day_number=2,
            db=self.db,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.player_id, str(self.player.id))
        self.assertGreater(len(loans.entries), 0)
        self.assertGreater(len(history.entries), 0)
        self.assertEqual(summary.player_id, str(self.player.id))
        self.assertTrue(summary.pressure_summary.short_recommendation)
        self.assertIn(
            summary.risk_summary.risk_label,
            {"locked", "trap_like", "dangerous", "risky_but_manageable", "stabilizing_if_disciplined"},
        )


if __name__ == "__main__":
    unittest.main()
