import os
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://tester:tester@localhost:5432/goldpenny_test")

from app.api import auth as auth_api  # noqa: E402
from app.api.auth import (  # noqa: E402
    CreatePlayerProfileRequest,
    LoginRequest,
    RegisterRequest,
    create_player_profile,
    get_session_state,
    login,
    register,
)
from app.db.database import Base  # noqa: E402
from app.models.daily_brief_log import DailyBriefLog  # noqa: E402
from app.models.daily_settlement_log import DailySettlementLog  # noqa: E402
from app.models.player import Player  # noqa: E402
from app.models.player_daily_state import PlayerDailyState  # noqa: E402
from app.models.player_employment_state import PlayerEmploymentState  # noqa: E402
from app.models.player_housing_state import PlayerHousingState  # noqa: E402
from app.models.user import User  # noqa: E402


class AuthAccountFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_signup_login_and_session_restore_require_explicit_fresh_player_creation(self) -> None:
        email = f"step95-{uuid.uuid4()}@example.com"
        password = "password123"

        with patch.object(auth_api, "get_password_hash", return_value="hashed::password123"), patch.object(
            auth_api,
            "verify_password",
            side_effect=lambda provided, hashed: hashed == f"hashed::{provided}",
        ):
            signup = register(RegisterRequest(email=email, password=password), db=self.db)
            self.assertIsNone(signup.player_profile)
            self.assertEqual(self.db.query(Player).count(), 0)

            login_result = login(LoginRequest(email=email, password=password), db=self.db)
            self.assertIsNone(login_result.player_profile)
            self.assertEqual(self.db.query(Player).count(), 0)

            user = self.db.query(User).filter(User.email == email).one()
            created = create_player_profile(
                CreatePlayerProfileRequest(display_name=None),
                current_user=user,
                db=self.db,
            )

            self.assertIsNotNone(created.player_profile)
            created_profile = created.player_profile
            assert created_profile is not None
            self.assertEqual(self.db.query(Player).count(), 1)
            self.assertEqual(self.db.query(PlayerEmploymentState).count(), 0)
            self.assertEqual(self.db.query(PlayerDailyState).count(), 1)

            player = self.db.query(Player).filter(Player.user_id == str(user.id)).one()
            self.assertEqual(str(player.id), str(created_profile.id))
            self.assertIsNone(player.main_job)
            self.assertEqual(player.region, "suburban")
            self.assertEqual(float(player.cash), 150.0)
            self.assertEqual(float(player.debt_xgp), 235.0)
            self.assertEqual(int(player.health), 76)
            self.assertEqual(int(player.stress), 38)
            self.assertIsNone(player.last_settled_day)

            daily_state = self.db.query(PlayerDailyState).filter(PlayerDailyState.player_id == player.id).one()
            self.assertEqual(daily_state.day_number, 1)
            self.assertFalse(bool(daily_state.worked_main_job))
            self.assertFalse(bool(daily_state.did_settlement))

            restored_login = login(LoginRequest(email=email, password=password), db=self.db)
            self.assertIsNotNone(restored_login.player_profile)
            self.assertEqual(str(restored_login.player_profile.id), str(created_profile.id))
            self.assertEqual(self.db.query(Player).count(), 1)

            session = get_session_state(current_user=user, db=self.db)
            self.assertIsNotNone(session.player_profile)
            self.assertEqual(str(session.player_profile.id), str(created_profile.id))


if __name__ == "__main__":
    unittest.main()
