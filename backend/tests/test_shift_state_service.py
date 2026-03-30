import os
import unittest
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"

from app.api.gameplay import get_gameplay_actions
from app.db.database import Base
from app.engine.rideshare_engine import process_rideshare_action
from app.models.contribution_event import ContributionEvent
from app.models.game_state import GameState
from app.models.job_action import JobAction
from app.models.job_definition_db import JobDefinition
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.side_income_action import SideIncomeAction
from app.models.user import User
from app.models.xgp_transaction import XGPTransaction
from app.services.shift_state_service import (
    SHIFT_STATUS_COMPLETED,
    build_work_state_payload,
    get_houston_now,
    resolve_expired_shift_if_needed,
    start_main_shift,
)


class ShiftStateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                GameState.__table__,
                MacroState.__table__,
                JobDefinition.__table__,
                PlayerDailyState.__table__,
                PlayerEmploymentState.__table__,
                JobAction.__table__,
                SideIncomeAction.__table__,
                XGPTransaction.__table__,
                ContributionEvent.__table__,
                PlayerTransactionLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"shift-state-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.db.add(
            JobDefinition(
                job_code="banker",
                title="Banker",
                base_monthly_pay_xgp=Decimal("5100.00"),
                stability_pct=Decimal("82.00"),
                growth_pct=Decimal("75.00"),
                stress_pct=Decimal("70.00"),
                promotion_threshold=100,
            )
        )
        self.db.add(
            GameState(
                current_day=1,
                day_status="open",
            )
        )
        self.db.add(
            MacroState(
                day_number=1,
                inflation=Decimal("2.0"),
                interest_rate=Decimal("4.0"),
                unemployment=Decimal("6.0"),
                oil_index=Decimal("110.0"),
                consumer_confidence=Decimal("48.0"),
                supply_chain_stress=Decimal("0.0"),
                is_active=True,
            )
        )

        self.player = Player(
            user_id=user.id,
            display_name="Shift State Player",
            main_job="banker",
            cash=Decimal("1000.00"),
            stress=12,
            health=92,
            fatigue=5.0,
            hours_available=16,
            skill_level=1,
            region="suburban",
            rideshare_reliability=Decimal("0.95"),
        )
        self.db.add(self.player)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _start_expired_shift(self) -> None:
        past_start = get_houston_now() - timedelta(hours=7)
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=past_start,
        )
        self.db.refresh(self.player)

    def test_actions_fetch_auto_resolves_expired_main_shift(self) -> None:
        self._start_expired_shift()

        payload = get_gameplay_actions(str(self.player.id), db=self.db)
        self.db.refresh(self.player)

        available_keys = {str(item.get("action_key")) for item in payload.get("available_actions", [])}
        work_state = payload.get("work_state") or {}

        self.assertFalse(bool(self.player.main_shift_active_flag))
        self.assertEqual(self.player.main_shift_status, SHIFT_STATUS_COMPLETED)
        self.assertEqual(str(work_state.get("shift_status")), SHIFT_STATUS_COMPLETED)
        self.assertTrue(bool(work_state.get("rideshare_available")))
        self.assertIn("side_income", available_keys)
        self.assertEqual(self.db.query(JobAction).count(), 1)
        self.assertGreater(float(self.player.cash), 1000.0)

    def test_expired_shift_finalize_is_idempotent(self) -> None:
        self._start_expired_shift()

        first = resolve_expired_shift_if_needed(self.db, player=self.player)
        self.db.refresh(self.player)
        cash_after_first = Decimal(str(self.player.cash))
        job_actions_after_first = self.db.query(JobAction).count()
        xgp_tx_after_first = self.db.query(XGPTransaction).count()
        contributions_after_first = self.db.query(ContributionEvent).count()
        tx_logs_after_first = self.db.query(PlayerTransactionLog).count()

        second = resolve_expired_shift_if_needed(self.db, player=self.player)
        self.db.refresh(self.player)

        self.assertEqual(str(first.get("shift_status")), SHIFT_STATUS_COMPLETED)
        self.assertEqual(str(second.get("shift_status")), SHIFT_STATUS_COMPLETED)
        self.assertEqual(Decimal(str(self.player.cash)), cash_after_first)
        self.assertEqual(self.db.query(JobAction).count(), job_actions_after_first)
        self.assertEqual(self.db.query(XGPTransaction).count(), xgp_tx_after_first)
        self.assertEqual(self.db.query(ContributionEvent).count(), contributions_after_first)
        self.assertEqual(self.db.query(PlayerTransactionLog).count(), tx_logs_after_first)

    def test_main_shift_hours_do_not_consume_side_income_cap(self) -> None:
        self._start_expired_shift()
        resolve_expired_shift_if_needed(self.db, player=self.player)

        first = process_rideshare_action(self.db, self.player, trips=5)
        second = process_rideshare_action(self.db, self.player, trips=1)
        work_state = build_work_state_payload(self.db, self.player)
        daily_state = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )

        self.assertEqual(first["trips"], 5)
        self.assertEqual(second["trips"], 1)
        self.assertIsNotNone(daily_state)
        self.assertEqual(round(float(daily_state.main_shift_hours_today), 4), 6.0)
        self.assertEqual(round(float(daily_state.side_income_hours), 4), 6.0)
        self.assertEqual(int(self.player.main_job_hours_today), 6)
        self.assertEqual(int(self.player.side_job_hours_today), 6)
        self.assertFalse(bool(work_state.get("rideshare_available")))

        with self.assertRaises(ValueError):
            process_rideshare_action(self.db, self.player, trips=1)


if __name__ == "__main__":
    unittest.main()
