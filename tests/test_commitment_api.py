import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_commitment_api.db")

from app.api.commitment import (
    activate_commitment_route,
    cancel_commitment_route,
    get_active_commitment_route,
    get_available_commitments_route,
    get_commitment_feedback_route,
    get_commitment_history_route,
    get_commitment_summary_route,
    replace_commitment_route,
)
from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_action import JobAction
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_commitment_history import PlayerCommitmentHistory
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing_state import PlayerHousingState
from app.models.side_income_action import SideIncomeAction
from app.models.user import User
from app.schemas.commitment import CommitmentActivationRequest


class CommitmentApiTests(unittest.TestCase):
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
                DailySettlementLog.__table__,
                PlayerDailyState.__table__,
                FinancialDistressLog.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                CareerProgressLog.__table__,
                JobAction.__table__,
                SideIncomeAction.__table__,
                PlayerCommitmentState.__table__,
                PlayerCommitmentHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step29-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step 29 API Tester",
            cash=Decimal("950.00"),
            debt_xgp=Decimal("1425.00"),
            stress=67,
            health=74,
            region="suburban",
            productivity_modifier=Decimal("0.91"),
            distress_score=Decimal("56.0"),
            required_daily_debt_payment_xgp=Decimal("30.0"),
            main_job="delivery_driver",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.5"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.4"),
                oil_index=Decimal("111.0"),
                consumer_confidence=Decimal("50.0"),
                supply_chain_stress=Decimal("1.03"),
                event_headline="Pressure day",
                event_summary="Costs remained elevated.",
            )
        )
        for basket_type, value in {
            BasketType.essentials: Decimal("10.8"),
            BasketType.protein: Decimal("11.2"),
            BasketType.produce: Decimal("11.0"),
            BasketType.convenience: Decimal("10.3"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=value,
                    daily_change_pct=Decimal("0.40"),
                    supply_pressure=Decimal("1.04"),
                    demand_pressure=Decimal("1.03"),
                )
            )

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="suburban",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("550"),
                monthly_utilities_cost_xgp=Decimal("106"),
                monthly_transport_base_xgp=Decimal("168"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=1,
                region="suburban",
                housing_cost_xgp=Decimal("18.33"),
                utilities_cost_xgp=Decimal("3.53"),
                commute_hours=Decimal("1.58"),
                commute_fuel_cost_xgp=Decimal("4.21"),
                region_stress_delta=Decimal("0.78"),
                region_opportunity_modifier=Decimal("-0.05"),
                region_business_demand_modifier=Decimal("-0.06"),
                region_side_income_modifier=Decimal("-0.05"),
                networking_modifier=Decimal("-0.05"),
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
                gross_revenue_xgp=Decimal("82.00"),
                input_cost_xgp=Decimal("59.00"),
                fuel_cost_xgp=Decimal("8.10"),
                maintenance_cost_xgp=Decimal("1.10"),
                overhead_cost_xgp=Decimal("14.00"),
                net_profit_xgp=Decimal("-0.20"),
                units_sold=21,
                inventory_start_units=Decimal("40"),
                inventory_end_units=Decimal("13"),
                demand_signal=Decimal("0.78"),
                demand_score=Decimal("0.78"),
                utilization_pct=Decimal("0.62"),
            )
        )

        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=1,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=65,
                stress_after=67,
                health_before=75,
                health_after=74,
                cash_before=Decimal("988.00"),
                cash_after=Decimal("950.00"),
                income_xgp=Decimal("158.00"),
                expenses_xgp=Decimal("196.00"),
                stock_pnl_xgp=Decimal("0"),
                debt_paid_xgp=Decimal("15.00"),
                health_change=-1,
                stress_change=2,
                housing_cost_daily_xgp=Decimal("18.33"),
            )
        )
        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                overtime_hours=Decimal("2.0"),
                commute_hours=Decimal("1.58"),
                sleep_hours=Decimal("5.6"),
                recovery_hours=Decimal("0.8"),
                productivity_modifier=Decimal("0.91"),
            )
        )
        self.db.add(
            FinancialDistressLog(
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                debt_payment_due_xgp=Decimal("30.00"),
                debt_payment_paid_xgp=Decimal("15.00"),
                debt_payment_missed=False,
                late_fee_xgp=Decimal("0.00"),
                accrued_interest_xgp=Decimal("2.80"),
                credit_score_before=648,
                credit_score_after=645,
                credit_score_delta=-3,
                distress_state_before="stretched",
                distress_state_after="stretched",
                distress_score_before=Decimal("54.0"),
                distress_score_after=Decimal("56.0"),
            )
        )
        self.db.add(
            CareerProgressLog(
                player_id=self.player.id,
                day_number=1,
                training_hours=Decimal("0.6"),
                skill_before=Decimal("2.0"),
                skill_after=Decimal("2.1"),
                skill_delta=Decimal("0.1"),
                performance_score=Decimal("0.70"),
                trailing_performance_score=Decimal("0.69"),
                promotion_progress=Decimal("0.32"),
            )
        )
        self.db.add(
            JobAction(
                player_id=self.player.id,
                job_name="Delivery Driver",
                job_type="main",
                shift_number=1,
                day=1,
                hours_worked=4,
                base_hourly_pay=Decimal("8.0"),
                productivity=0.9,
                earned_cash=Decimal("28.8"),
                stress_change=2,
                health_change=-1,
                fatigue_change=1.8,
                overtime_penalty_applied=False,
                hours_remaining_after=8,
            )
        )
        self.db.add(
            SideIncomeAction(
                player_id=self.player.id,
                day_number=1,
                side_income_type="ride_share",
                hours_worked=2.0,
                gross_income_xgp=Decimal("22.0"),
                fuel_cost_xgp=Decimal("5.2"),
                wear_cost_xgp=Decimal("1.4"),
                maintenance_cost_xgp=Decimal("0.0"),
                net_income_xgp=Decimal("15.4"),
                stress_change=1,
                health_change=0,
                hours_before=8,
                hours_after=6,
                oil_index_used=111.0,
            )
        )

    def test_available_and_activate_and_active_routes(self) -> None:
        available = get_available_commitments_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(available.player_id, str(self.player.id))
        self.assertGreaterEqual(len(available.items), 3)
        self.assertLessEqual(len(available.items), 4)

        request = CommitmentActivationRequest(
            commitment_key=available.items[0].commitment_key,
            duration_days=5,
        )
        activated = activate_commitment_route(
            player_id=str(self.player.id),
            request=request,
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(activated.status, "active")
        self.assertEqual(activated.commitment_key, request.commitment_key)

        active = get_active_commitment_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(active.status, "active")
        self.assertEqual(active.commitment_key, request.commitment_key)

    def test_summary_feedback_replace_cancel_and_history_routes(self) -> None:
        available = get_available_commitments_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        first = available.items[0].commitment_key
        second = available.items[1].commitment_key
        activate_commitment_route(
            player_id=str(self.player.id),
            request=CommitmentActivationRequest(commitment_key=first, duration_days=3),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )

        summary = get_commitment_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(summary.player_id, str(self.player.id))
        self.assertEqual(summary.active_commitment.status, "active")
        self.assertIn(summary.active_commitment.alignment_label, {"aligned", "mostly_aligned", "drifting", "off_track"})

        feedback = get_commitment_feedback_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertGreaterEqual(len(feedback.items), 1)

        replaced = replace_commitment_route(
            player_id=str(self.player.id),
            request=CommitmentActivationRequest(commitment_key=second, duration_days=5),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(replaced.status, "active")
        self.assertEqual(replaced.commitment_key, second)

        cancelled_summary = cancel_commitment_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(cancelled_summary.active_commitment.status, "inactive")

        history = get_commitment_history_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            limit=20,
            db=self.db,
        )
        self.assertGreaterEqual(len(history.entries), 1)


if __name__ == "__main__":
    unittest.main()
