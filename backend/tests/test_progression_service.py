import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_progression_service.db")

from app.db.database import Base
from app.engine.progression_service import (
    build_daily_goals,
    build_progression_summary,
    build_weekly_missions,
    evaluate_action_progress,
    evaluate_end_of_day_progress,
)
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


class ProgressionServiceTests(unittest.TestCase):
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
                PlayerCareer.__table__,
                FinancialDistressLog.__table__,
                PlayerProgressionState.__table__,
                PlayerGoalHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_player(
        self,
        *,
        name: str,
        cash_xgp: Decimal = Decimal("1000.00"),
        debt_xgp: Decimal = Decimal("300.00"),
        stress: int = 40,
        health: int = 90,
        main_job: str = "banker",
        include_business: bool = True,
    ) -> Player:
        user = User(email=f"{name.lower()}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=name,
            cash=cash_xgp,
            debt_xgp=debt_xgp,
            stress=stress,
            health=health,
            main_job=main_job,
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        self.db.add(PlayerCareer(player_id=player.id, current_job_key=main_job))
        if include_business:
            self.db.add(
                PlayerBusiness(
                    player_id=player.id,
                    business_id="fruit_shop",
                    region="suburban",
                    level_key="starter",
                    business_level=1,
                    reputation=52,
                    is_active=True,
                    created_day=1,
                )
            )
        self.db.flush()
        return player

    def _seed_daily_state(self, player: Player, *, day: int, cash_start: Decimal, stress_end: int | None = None) -> None:
        self.db.add(
            PlayerDailyState(
                player_id=player.id,
                day_number=day,
                hours_available_start=24,
                hours_available_end=8,
                worked_main_job=True,
                worked_hours=8,
                gross_income_xgp=Decimal("140.00"),
                did_settlement=False,
                stress_start=int(player.stress or 0),
                stress_end=int(player.stress if stress_end is None else stress_end),
                health_start=int(player.health or 90),
                health_end=int(player.health or 90),
                cash_start=cash_start,
                cash_end=Decimal(str(player.cash_xgp)),
            )
        )

    def _seed_settlement(self, player: Player, *, day: int, income_xgp: Decimal, expenses_xgp: Decimal, cash_before: Decimal, cash_after: Decimal, stress_after: int) -> None:
        self.db.add(
            DailySettlementLog(
                player_id=player.id,
                day_number=day,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=max(0, stress_after - 2),
                stress_after=stress_after,
                health_before=90,
                health_after=89,
                cash_before=cash_before,
                cash_after=cash_after,
                income_xgp=income_xgp,
                expenses_xgp=expenses_xgp,
                stock_pnl_xgp=Decimal("0.00"),
                debt_paid_xgp=Decimal("6.00"),
                health_change=-1,
                stress_change=1,
                side_income_net_xgp=Decimal("12.00"),
                business_net_profit_xgp=Decimal("15.00"),
            )
        )

    def test_daily_goals_are_relevant_to_player_state(self) -> None:
        player = self._create_player(name="DailyGoals", include_business=True, stress=48)
        self._seed_daily_state(player, day=1, cash_start=Decimal("900.00"))
        self.db.add(
            JobAction(
                player_id=player.id,
                job_name="Banker",
                job_type="main",
                shift_number=1,
                day=1,
                hours_worked=8,
                base_hourly_pay=Decimal("15.00"),
                productivity=1.0,
                earned_cash=Decimal("120.00"),
                stress_change=3,
                health_change=-1,
                fatigue_change=1.0,
                overtime_penalty_applied=False,
                hours_remaining_after=8,
            )
        )
        business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
            .first()
        )
        self.db.add(
            BusinessDailyLog(
                business_id=business.id,
                player_id=player.id,
                day=1,
                business_type="fruit_shop",
                region_key="suburban",
                gross_revenue_xgp=Decimal("60.00"),
                input_cost_xgp=Decimal("35.00"),
                fuel_cost_xgp=Decimal("0.00"),
                overhead_cost_xgp=Decimal("9.00"),
                spoilage_cost_xgp=Decimal("2.00"),
                net_profit_xgp=Decimal("14.00"),
                demand_score=Decimal("0.9"),
                utilization_pct=Decimal("0.6"),
            )
        )
        self.db.commit()

        payload = build_daily_goals(db=self.db, player_id=str(player.id), as_of_date=date(2026, 1, 1), persist=True)
        self.db.commit()

        self.assertLessEqual(len(payload["daily_goals"]), 3)
        goal_keys = {goal["goal_key"] for goal in payload["daily_goals"]}
        self.assertIn("business_progress_today", goal_keys)
        self.assertIn("productive_actions_2", goal_keys)
        positive_goal = next(goal for goal in payload["daily_goals"] if goal["goal_key"] == "positive_net_cash_today")
        self.assertEqual(positive_goal["status"], "completed")

    def test_weekly_missions_are_bounded_and_strategy_relevant(self) -> None:
        player = self._create_player(name="WeeklyMissions", include_business=False)
        for day in range(1, 4):
            self._seed_settlement(
                player,
                day=day,
                income_xgp=Decimal("180.00"),
                expenses_xgp=Decimal("95.00"),
                cash_before=Decimal("1000.00"),
                cash_after=Decimal("1085.00"),
                stress_after=58,
            )
            self.db.add(
                JobAction(
                    player_id=player.id,
                    job_name="Banker",
                    job_type="main",
                    shift_number=1,
                    day=day,
                    hours_worked=8,
                    base_hourly_pay=Decimal("15.00"),
                    productivity=1.0,
                    earned_cash=Decimal("120.00"),
                    stress_change=2,
                    health_change=-1,
                    fatigue_change=0.8,
                    overtime_penalty_applied=False,
                    hours_remaining_after=8,
                )
            )
        self.db.commit()

        payload = build_weekly_missions(
            db=self.db,
            player_id=str(player.id),
            as_of_date=date(2026, 1, 3),
            persist=True,
        )
        self.db.commit()

        self.assertGreaterEqual(len(payload["weekly_missions"]), 3)
        self.assertLessEqual(len(payload["weekly_missions"]), 5)
        mission_keys = {mission["mission_key"] for mission in payload["weekly_missions"]}
        self.assertIn("weekly_work_shifts", mission_keys)
        self.assertNotIn("weekly_profitable_business_days", mission_keys)

    def test_streak_crediting_does_not_duplicate_for_same_day(self) -> None:
        player = self._create_player(name="StreakDupes", include_business=True)
        self._seed_daily_state(player, day=1, cash_start=Decimal("900.00"))
        self._seed_settlement(
            player,
            day=1,
            income_xgp=Decimal("150.00"),
            expenses_xgp=Decimal("90.00"),
            cash_before=Decimal("1000.00"),
            cash_after=Decimal("1060.00"),
            stress_after=55,
        )
        self.db.add(
            JobAction(
                player_id=player.id,
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
        self.db.commit()

        first = evaluate_end_of_day_progress(self.db, str(player.id), as_of_date=date(2026, 1, 1))
        self.db.commit()
        second = evaluate_end_of_day_progress(self.db, str(player.id), as_of_date=date(2026, 1, 1))
        self.db.commit()

        state = self.db.query(PlayerProgressionState).filter(PlayerProgressionState.player_id == player.id).first()
        self.assertIsNotNone(state)
        self.assertEqual(int(state.login_streak_current or 0), 1)
        self.assertEqual(first["streaks"][0]["current_count"], second["streaks"][0]["current_count"])

    def test_action_progress_updates_after_new_action(self) -> None:
        player = self._create_player(name="ActionProgress", include_business=False, stress=42)
        self._seed_daily_state(player, day=1, cash_start=Decimal("1000.00"))
        self.db.commit()

        before = evaluate_action_progress(self.db, str(player.id), as_of_date=date(2026, 1, 1))
        self.db.add(
            JobAction(
                player_id=player.id,
                job_name="Banker",
                job_type="main",
                shift_number=1,
                day=1,
                hours_worked=8,
                base_hourly_pay=Decimal("15.00"),
                productivity=1.0,
                earned_cash=Decimal("120.00"),
                stress_change=3,
                health_change=-1,
                fatigue_change=1.0,
                overtime_penalty_applied=False,
                hours_remaining_after=8,
            )
        )
        self.db.flush()
        after = evaluate_action_progress(self.db, str(player.id), as_of_date=date(2026, 1, 1))
        self.db.commit()

        before_goal = next(goal for goal in before["daily_goals"] if goal["goal_key"] == "productive_actions_2")
        after_goal = next(goal for goal in after["daily_goals"] if goal["goal_key"] == "productive_actions_2")
        self.assertGreater(after_goal["progress_current"], before_goal["progress_current"])

    def test_weekly_reset_uses_new_week_window(self) -> None:
        player = self._create_player(name="WeekReset", include_business=False)
        self.db.commit()

        first_week = build_weekly_missions(
            db=self.db,
            player_id=str(player.id),
            as_of_date=date(2026, 1, 1),
            persist=True,
        )
        second_week = build_weekly_missions(
            db=self.db,
            player_id=str(player.id),
            as_of_date=date(2026, 1, 8),
            persist=True,
        )
        self.db.commit()

        self.assertEqual(first_week["week_start_day"], 1)
        self.assertEqual(second_week["week_start_day"], 8)

    def test_rewards_are_modest_and_do_not_print_money(self) -> None:
        player = self._create_player(name="RewardBounds", include_business=True, stress=52)
        cash_before = Decimal(str(player.cash_xgp))
        self._seed_daily_state(player, day=1, cash_start=Decimal("800.00"), stress_end=54)
        self._seed_settlement(
            player,
            day=1,
            income_xgp=Decimal("220.00"),
            expenses_xgp=Decimal("110.00"),
            cash_before=cash_before,
            cash_after=cash_before,
            stress_after=54,
        )
        business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
            .first()
        )
        self.db.add(
            BusinessDailyLog(
                business_id=business.id,
                player_id=player.id,
                day=1,
                business_type="fruit_shop",
                region_key="suburban",
                gross_revenue_xgp=Decimal("70.00"),
                input_cost_xgp=Decimal("35.00"),
                fuel_cost_xgp=Decimal("0.00"),
                overhead_cost_xgp=Decimal("10.00"),
                spoilage_cost_xgp=Decimal("2.00"),
                net_profit_xgp=Decimal("23.00"),
                demand_score=Decimal("0.8"),
                utilization_pct=Decimal("0.7"),
            )
        )
        self.db.commit()

        evaluate_end_of_day_progress(self.db, str(player.id), as_of_date=date(2026, 1, 1))
        self.db.commit()
        self.db.refresh(player)
        summary = build_progression_summary(self.db, str(player.id), as_of_date=date(2026, 1, 1), persist=False)

        self.assertEqual(Decimal(str(player.cash_xgp)), cash_before)
        self.assertGreaterEqual(int(player.stress), 0)
        self.assertLessEqual(int(player.stress), 100)
        self.assertLessEqual(float(player.base_productivity_modifier), 1.08)
        self.assertIn("daily_goals", summary)


if __name__ == "__main__":
    unittest.main()
