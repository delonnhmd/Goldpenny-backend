import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_onboarding_api.db")

from app.api.onboarding import (
    OnboardingAdvanceRequest,
    advance_onboarding_route,
    complete_onboarding_route,
    get_onboarding_dashboard_config_route,
    get_onboarding_guidance_route,
    get_onboarding_state_route,
    get_onboarding_unlock_schedule_route,
    refresh_onboarding_route,
    skip_onboarding_route,
)
from app.db.database import Base
from app.models.daily_settlement_log import DailySettlementLog
from app.models.job_action import JobAction
from app.models.player import Player
from app.models.player_onboarding_state import PlayerOnboardingState
from app.models.user import User


class OnboardingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                DailySettlementLog.__table__,
                JobAction.__table__,
                PlayerOnboardingState.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"step31-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step31 API",
            cash=Decimal("920.00"),
            debt_xgp=Decimal("300.00"),
            stress=30,
            health=92,
            region="suburban",
            main_job="banker",
        )
        self.db.add(self.player)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_state_guidance_config_unlock_routes_return_frontend_ready_shapes(self) -> None:
        state = get_onboarding_state_route(str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        guidance = get_onboarding_guidance_route(str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        config = get_onboarding_dashboard_config_route(str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)
        unlock = get_onboarding_unlock_schedule_route(str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)

        self.assertEqual(state.player_id, str(self.player.id))
        self.assertTrue(state.current_step_key)
        self.assertEqual(guidance.step_key, state.current_step_key)
        self.assertEqual(state.guided_day_number, 1)
        self.assertGreaterEqual(len(config.visible_sections), 1)
        self.assertGreaterEqual(len(unlock.items), 1)

    def test_advance_refresh_and_skip_flow(self) -> None:
        welcome = advance_onboarding_route(
            str(self.player.id),
            request=OnboardingAdvanceRequest(action_key="continue_onboarding"),
            as_of_date=date(2026, 1, 1),
            db=self.db,
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
        self.db.flush()

        advanced = advance_onboarding_route(
            str(self.player.id),
            request=OnboardingAdvanceRequest(action_key="work_shift"),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        refreshed = refresh_onboarding_route(
            str(self.player.id),
            request=OnboardingAdvanceRequest(action_key="work_shift"),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        skipped = skip_onboarding_route(str(self.player.id), as_of_date=date(2026, 1, 1), db=self.db)

        self.assertEqual(welcome.state.current_step_key, "read_todays_brief")
        self.assertEqual(advanced.player_id, str(self.player.id))
        self.assertEqual(refreshed.player_id, str(self.player.id))
        self.assertEqual(skipped.state.onboarding_status, "skipped")
        self.assertEqual(skipped.dashboard_config.hidden_sections, [])

    def test_complete_route_marks_completed_state(self) -> None:
        payload = complete_onboarding_route(
            str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(payload.state.onboarding_status, "completed")
        self.assertIn("commitment", payload.dashboard_config.visible_sections)


if __name__ == "__main__":
    unittest.main()
