import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_progression_api.db")

from app.api.progression import (
    get_daily_goals_route,
    get_progression_summary_route,
    get_streaks_route,
    get_weekly_missions_route,
    refresh_progression_route,
)
from app.db.database import Base
from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_goal_history import PlayerGoalHistory
from app.models.player_progression_state import PlayerProgressionState
from app.models.side_income_action import SideIncomeAction
from app.models.user import User


class ProgressionApiTests(unittest.TestCase):
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
                JobAction.__table__,
                SideIncomeAction.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                CareerProgressLog.__table__,
                FinancialDistressLog.__table__,
                PlayerCareer.__table__,
                PlayerProgressionState.__table__,
                PlayerGoalHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"progression-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Progression API",
            cash=Decimal("1100.00"),
            debt_xgp=Decimal("500.00"),
            stress=46,
            health=91,
            main_job="banker",
            region="suburban",
        )
        self.db.add(self.player)
        self.db.flush()
        self.db.add(PlayerCareer(player_id=self.player.id, current_job_key="banker"))
        self.db.flush()

        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="fruit_shop",
            region="suburban",
            level_key="starter",
            business_level=1,
            reputation=50,
            is_active=True,
            created_day=1,
        )
        self.db.add(business)
        self.db.flush()

        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                hours_available_start=24,
                hours_available_end=8,
                worked_main_job=True,
                worked_hours=8,
                gross_income_xgp=Decimal("120.00"),
                did_settlement=False,
                stress_start=44,
                stress_end=46,
                health_start=92,
                health_end=91,
                cash_start=Decimal("1000.00"),
                cash_end=Decimal("1100.00"),
            )
        )
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
            BusinessDailyLog(
                business_id=business.id,
                player_id=self.player.id,
                day=1,
                business_type="fruit_shop",
                region_key="suburban",
                gross_revenue_xgp=Decimal("50.00"),
                input_cost_xgp=Decimal("27.00"),
                fuel_cost_xgp=Decimal("0.00"),
                overhead_cost_xgp=Decimal("9.00"),
                spoilage_cost_xgp=Decimal("2.00"),
                net_profit_xgp=Decimal("12.00"),
                demand_score=Decimal("0.8"),
                utilization_pct=Decimal("0.7"),
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_daily_goals_endpoint_returns_frontend_ready_payload(self) -> None:
        payload = get_daily_goals_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(payload.player_id, str(self.player.id))
        self.assertLessEqual(len(payload.daily_goals), 3)
        persisted = (
            self.db.query(PlayerGoalHistory)
            .filter(PlayerGoalHistory.player_id == self.player.id, PlayerGoalHistory.goal_scope == "daily")
            .count()
        )
        self.assertGreaterEqual(persisted, 1)

    def test_summary_endpoint_returns_goals_missions_and_streaks(self) -> None:
        payload = get_progression_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(payload.player_id, str(self.player.id))
        self.assertLessEqual(len(payload.daily_goals), 3)
        self.assertLessEqual(len(payload.weekly_missions), 5)
        self.assertGreaterEqual(len(payload.streaks), 1)
        self.assertTrue(bool(payload.motivational_summary))

    def test_refresh_endpoint_updates_action_progress(self) -> None:
        before = get_progression_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.db.add(
            JobAction(
                player_id=self.player.id,
                job_name="Banker",
                job_type="main",
                shift_number=2,
                day=1,
                hours_worked=4,
                base_hourly_pay=Decimal("15.00"),
                productivity=1.0,
                earned_cash=Decimal("60.00"),
                stress_change=1,
                health_change=0,
                fatigue_change=0.5,
                overtime_penalty_applied=False,
                hours_remaining_after=4,
            )
        )
        self.db.flush()
        refreshed = refresh_progression_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        streaks = get_streaks_route(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        missions = get_weekly_missions_route(player_id=str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)

        before_goal = next(goal for goal in before.daily_goals if goal.goal_key == "productive_actions_2")
        after_goal = next(goal for goal in refreshed.daily_goals if goal.goal_key == "productive_actions_2")
        self.assertGreaterEqual(after_goal.progress_current, before_goal.progress_current)
        self.assertGreaterEqual(len(streaks.streaks), 1)
        self.assertGreaterEqual(len(missions.weekly_missions), 1)


if __name__ == "__main__":
    unittest.main()
