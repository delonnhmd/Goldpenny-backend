import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_commitment_service.db")

from app.db.database import Base
from app.engine.commitment_service import (
    CommitmentValidationError,
    activate_player_commitment,
    build_available_commitments,
    build_commitment_completion_or_failure,
    detect_commitment_drift,
    evaluate_commitment_progress,
    get_player_active_commitment,
)
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


class CommitmentServiceTests(unittest.TestCase):
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
        user = User(email=f"step29-service-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step 29 Service Tester",
            cash=Decimal("980.00"),
            debt_xgp=Decimal("1450.00"),
            stress=69,
            health=72,
            region="suburban",
            productivity_modifier=Decimal("0.90"),
            distress_score=Decimal("59.0"),
            required_daily_debt_payment_xgp=Decimal("31.0"),
            main_job="retail_worker",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.7"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.4"),
                oil_index=Decimal("112.0"),
                consumer_confidence=Decimal("49.0"),
                supply_chain_stress=Decimal("1.05"),
                event_headline="Pressure day",
                event_summary="Costs remained elevated.",
            )
        )
        for basket_type, value in {
            BasketType.essentials: Decimal("10.8"),
            BasketType.protein: Decimal("11.3"),
            BasketType.produce: Decimal("11.1"),
            BasketType.convenience: Decimal("10.4"),
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
                day=1,
                region="suburban",
                housing_cost_xgp=Decimal("18.67"),
                utilities_cost_xgp=Decimal("3.60"),
                commute_hours=Decimal("1.62"),
                commute_fuel_cost_xgp=Decimal("4.25"),
                region_stress_delta=Decimal("0.80"),
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
                input_cost_xgp=Decimal("58.00"),
                fuel_cost_xgp=Decimal("8.40"),
                maintenance_cost_xgp=Decimal("1.20"),
                overhead_cost_xgp=Decimal("14.00"),
                net_profit_xgp=Decimal("0.40"),
                units_sold=21,
                inventory_start_units=Decimal("40"),
                inventory_end_units=Decimal("12"),
                demand_signal=Decimal("0.79"),
                demand_score=Decimal("0.79"),
                utilization_pct=Decimal("0.63"),
            )
        )

        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=1,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=67,
                stress_after=69,
                health_before=73,
                health_after=72,
                cash_before=Decimal("1015.00"),
                cash_after=Decimal("980.00"),
                income_xgp=Decimal("168.00"),
                expenses_xgp=Decimal("203.00"),
                stock_pnl_xgp=Decimal("0"),
                debt_paid_xgp=Decimal("12.00"),
                health_change=-1,
                stress_change=2,
                housing_cost_daily_xgp=Decimal("18.67"),
            )
        )
        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                overtime_hours=Decimal("2.1"),
                commute_hours=Decimal("1.62"),
                sleep_hours=Decimal("5.4"),
                recovery_hours=Decimal("0.9"),
                productivity_modifier=Decimal("0.90"),
            )
        )
        self.db.add(
            FinancialDistressLog(
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                debt_payment_due_xgp=Decimal("31.00"),
                debt_payment_paid_xgp=Decimal("12.00"),
                debt_payment_missed=False,
                late_fee_xgp=Decimal("0.00"),
                accrued_interest_xgp=Decimal("2.90"),
                credit_score_before=650,
                credit_score_after=647,
                credit_score_delta=-3,
                distress_state_before="stretched",
                distress_state_after="stretched",
                distress_score_before=Decimal("56.0"),
                distress_score_after=Decimal("59.0"),
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
                promotion_progress=Decimal("0.30"),
            )
        )
        self.db.add(
            JobAction(
                player_id=self.player.id,
                job_name="retail_worker",
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
                fuel_cost_xgp=Decimal("5.0"),
                wear_cost_xgp=Decimal("1.5"),
                maintenance_cost_xgp=Decimal("0.0"),
                net_income_xgp=Decimal("15.5"),
                stress_change=1,
                health_change=0,
                hours_before=8,
                hours_after=6,
                oil_index_used=112.0,
            )
        )

    def test_available_commitments_derived_from_step28_plans(self) -> None:
        payload = build_available_commitments(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertEqual(payload["player_id"], str(self.player.id))
        self.assertGreaterEqual(len(payload["items"]), 3)
        self.assertLessEqual(len(payload["items"]), 4)
        keys = {item["commitment_key"] for item in payload["items"]}
        self.assertTrue(any(key in keys for key in {"stabilize_finances", "push_income", "reduce_stress"}))

    def test_activate_commitment_and_single_active_enforced(self) -> None:
        available = build_available_commitments(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        selected_key = available["items"][0]["commitment_key"]
        activated = activate_player_commitment(
            db=self.db,
            player_id=str(self.player.id),
            commitment_key=selected_key,
            duration_days=5,
            as_of_date=date(2026, 1, 1),
        )
        self.assertEqual(activated["status"], "active")
        self.assertEqual(activated["commitment_key"], selected_key)
        with self.assertRaises(CommitmentValidationError):
            activate_player_commitment(
                db=self.db,
                player_id=str(self.player.id),
                commitment_key=selected_key,
                duration_days=5,
                as_of_date=date(2026, 1, 1),
            )

    def test_adherence_updates_and_drift_detection(self) -> None:
        activate_player_commitment(
            db=self.db,
            player_id=str(self.player.id),
            commitment_key="reduce_stress",
            duration_days=3,
            as_of_date=date(2026, 1, 1),
        )
        progress = evaluate_commitment_progress(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="work_shift",
        )
        self.assertIn("adherence_delta", progress)
        self.assertIn("momentum_delta", progress)
        drift = detect_commitment_drift(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertIn(drift["drift_level"], {"low", "moderate", "high", "none"})
        self.assertIn("corrective_suggestion", drift)

    def test_completion_applies_modest_reward_and_history(self) -> None:
        available = build_available_commitments(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        selected_key = available["items"][0]["commitment_key"]
        activate_player_commitment(
            db=self.db,
            player_id=str(self.player.id),
            commitment_key=selected_key,
            duration_days=3,
            as_of_date=date(2026, 1, 1),
        )
        state = (
            self.db.query(PlayerCommitmentState)
            .filter(PlayerCommitmentState.player_id == self.player.id)
            .first()
        )
        self.assertIsNotNone(state)
        assert state is not None
        state.adherence_score = Decimal("82.0")
        state.target_end_day = 1
        stress_before = int(self.player.stress)

        completion = build_commitment_completion_or_failure(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertEqual(completion["final_status"], "completed")
        self.assertTrue(completion["reward_summary"])
        self.assertEqual(int(self.player.stress), max(0, stress_before - 1))
        history = get_player_active_commitment(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertEqual(history["status"], "inactive")
        history_rows = (
            self.db.query(PlayerCommitmentHistory)
            .filter(PlayerCommitmentHistory.player_id == self.player.id)
            .all()
        )
        self.assertGreaterEqual(len(history_rows), 1)


if __name__ == "__main__":
    unittest.main()
