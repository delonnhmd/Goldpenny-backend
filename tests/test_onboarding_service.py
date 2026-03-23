import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_onboarding_service.db")

from app.db.database import Base
from app.engine.onboarding_service import (
    build_first_session_dashboard_config,
    build_onboarding_guidance,
    build_onboarding_state,
    evaluate_onboarding_completion,
    skip_onboarding,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_onboarding_state import PlayerOnboardingState
from app.models.side_income_action import SideIncomeAction
from app.models.user import User


class OnboardingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                JobAction.__table__,
                SideIncomeAction.__table__,
                BusinessDailyLog.__table__,
                HousingDailyLog.__table__,
                FinancialDistressLog.__table__,
                PlayerOnboardingState.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"step31-service-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step31 Service",
            cash=Decimal("900.00"),
            debt_xgp=Decimal("350.00"),
            stress=28,
            health=90,
            region="suburban",
            main_job="banker",
        )
        self.db.add(self.player)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_state_initializes_and_hides_advanced_modules(self) -> None:
        state = build_onboarding_state(self.db, str(self.player.id), as_of_date=date(2026, 1, 1))
        config = build_first_session_dashboard_config(self.db, str(self.player.id), as_of_date=date(2026, 1, 1))
        guidance = build_onboarding_guidance(self.db, str(self.player.id), as_of_date=date(2026, 1, 1))

        self.assertEqual(state["onboarding_status"], "in_progress")
        self.assertIn("core_basics", state["visible_modules"])
        self.assertNotIn("economy_deep", state["visible_modules"])
        self.assertIn("commitment", config["hidden_sections"])
        self.assertNotIn("action_history", config["visible_sections"])
        self.assertEqual(guidance["step_key"], state["current_step_key"])

    def test_progress_advances_after_income_action_and_end_day(self) -> None:
        after_welcome = evaluate_onboarding_completion(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="continue_onboarding",
        )
        self.assertIn("welcome_core_premise", after_welcome["completed_step_keys"])

        self.db.add(
            JobAction(
                player_id=self.player.id,
                job_name="Banker",
                job_type="main",
                shift_number=1,
                day=1,
                hours_worked=8,
                base_hourly_pay=Decimal("15.00"),
                productivity=1.0,
                earned_cash=Decimal("120.00"),
                stress_change=2,
                health_change=-1,
                fatigue_change=1.0,
                overtime_penalty_applied=False,
                hours_remaining_after=8,
            )
        )
        self.db.flush()

        after_income = evaluate_onboarding_completion(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="work_shift",
        )
        self.assertIn("read_todays_brief", after_income["completed_step_keys"])
        self.assertIn("first_income_action", after_income["completed_step_keys"])

        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=1,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=28,
                stress_after=30,
                health_before=90,
                health_after=89,
                cash_before=Decimal("900.00"),
                cash_after=Decimal("1010.00"),
                income_xgp=Decimal("120.00"),
                expenses_xgp=Decimal("10.00"),
                stock_pnl_xgp=Decimal("0.00"),
                debt_paid_xgp=Decimal("5.00"),
                health_change=-1,
                stress_change=2,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=1,
                region="suburban",
                housing_cost_xgp=Decimal("20.00"),
                commute_hours=Decimal("1.20"),
                commute_pressure=Decimal("1.05"),
                stress_delta=1,
                opportunity_modifier=Decimal("0.95"),
                utilities_cost_xgp=Decimal("3.00"),
                commute_fuel_cost_xgp=Decimal("2.00"),
                region_stress_delta=Decimal("0.5"),
                region_opportunity_modifier=Decimal("-0.02"),
                region_business_demand_modifier=Decimal("-0.04"),
                region_side_income_modifier=Decimal("-0.03"),
                networking_modifier=Decimal("-0.03"),
                opportunity_quality_signal=Decimal("0.96"),
            )
        )
        self.db.flush()

        after_day = evaluate_onboarding_completion(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="end_day",
        )
        self.assertIn("end_first_day", after_day["completed_step_keys"])
        self.assertEqual(after_day["onboarding_status"], "completed")

    def test_guided_day_two_and_three_stage_reveal(self) -> None:
        self.db.add(
            JobAction(
                player_id=self.player.id,
                job_name="Banker",
                job_type="main",
                shift_number=1,
                day=1,
                hours_worked=8,
                base_hourly_pay=Decimal("15.00"),
                productivity=1.0,
                earned_cash=Decimal("120.00"),
                stress_change=2,
                health_change=-1,
                fatigue_change=1.0,
                overtime_penalty_applied=False,
                hours_remaining_after=8,
            )
        )
        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=1,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=28,
                stress_after=31,
                health_before=90,
                health_after=89,
                cash_before=Decimal("900.00"),
                cash_after=Decimal("1000.00"),
                income_xgp=Decimal("120.00"),
                expenses_xgp=Decimal("20.00"),
                stock_pnl_xgp=Decimal("0.00"),
                debt_paid_xgp=Decimal("5.00"),
                health_change=-1,
                stress_change=3,
            )
        )
        self.db.flush()

        evaluate_onboarding_completion(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="continue_onboarding",
        )
        evaluate_onboarding_completion(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="work_shift",
        )

        evaluate_onboarding_completion(
            self.db,
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            action_key="end_day",
        )

        day_two_guidance = build_onboarding_guidance(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        day_two_config = build_first_session_dashboard_config(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertEqual(day_two_guidance["step_key"], "guided_day_2_pressure")
        self.assertEqual(day_two_guidance["guided_day_number"], 2)
        self.assertIn("recovery_vs_push", day_two_config["visible_sections"])
        self.assertNotIn("market_overview", day_two_config["visible_sections"])

        day_three_guidance = build_onboarding_guidance(self.db, str(self.player.id), as_of_date=date(2026, 1, 3))
        day_three_config = build_first_session_dashboard_config(self.db, str(self.player.id), as_of_date=date(2026, 1, 3))
        self.assertEqual(day_three_guidance["step_key"], "guided_day_3_opportunity")
        self.assertEqual(day_three_guidance["guided_day_number"], 3)
        self.assertIn("market_overview", day_three_config["visible_sections"])
        self.assertEqual(day_three_config["highlighted_action_key"], "explore_opportunity")

    def test_skip_unlocks_full_dashboard(self) -> None:
        skipped = skip_onboarding(self.db, str(self.player.id), as_of_date=date(2026, 1, 1))
        config = build_first_session_dashboard_config(self.db, str(self.player.id), as_of_date=date(2026, 1, 1))

        self.assertEqual(skipped["onboarding_status"], "skipped")
        self.assertEqual(config["hidden_sections"], [])
        self.assertIn("market_overview", config["visible_sections"])
        self.assertIn("commitment", config["visible_sections"])


if __name__ == "__main__":
    unittest.main()
