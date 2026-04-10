import os
import unittest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"

from app.api.gameplay import get_gameplay_actions
from app.api.gameplay import get_gameplay_transaction_history
from app.db.database import Base
from app.engine.rideshare_engine import process_rideshare_action
from app.models.contribution_event import ContributionEvent
from app.models.game_state import GameState
from app.models.gameplay_transaction import GameplayTransaction
from app.models.job_action import JobAction
from app.models.job_definition_db import JobDefinition
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.shift_salary_audit_log import ShiftSalaryAuditLog
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
                GameplayTransaction.__table__,
                ShiftSalaryAuditLog.__table__,
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

    def _houston_datetime(self, year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
        return pytz.timezone("America/Chicago").localize(datetime(year, month, day, hour, minute))

    def test_actions_fetch_auto_resolves_expired_main_shift(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 12, 0)
        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        with patch("app.services.shift_state_service.get_houston_now", return_value=after_shift):
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

        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )
        self.assertIsNotNone(pds)
        self.assertTrue(bool(pds.did_work))
        self.assertGreater(float(pds.salary_earned or 0), 0.0)

        history = get_gameplay_transaction_history(str(self.player.id), day=1, db=self.db)
        salary_rows = [entry for entry in history["transactions"] if entry["category"] == "salary"]
        self.assertEqual(history["day"], 1)
        self.assertGreater(history["total_income"], 0.0)
        self.assertEqual(history["total_expense"], 0.0)
        self.assertEqual(len(salary_rows), 1)
        self.assertGreater(float(salary_rows[0]["amount"]), 0.0)

    def test_expired_shift_finalize_is_idempotent(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 12, 0)
        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        first = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)
        self.db.refresh(self.player)
        cash_after_first = Decimal(str(self.player.cash))
        job_actions_after_first = self.db.query(JobAction).count()
        xgp_tx_after_first = self.db.query(XGPTransaction).count()
        contributions_after_first = self.db.query(ContributionEvent).count()
        tx_logs_after_first = self.db.query(PlayerTransactionLog).count()
        gameplay_tx_after_first = self.db.query(GameplayTransaction).count()
        audit_rows_after_first = self.db.query(ShiftSalaryAuditLog).count()

        second = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)
        self.db.refresh(self.player)

        self.assertEqual(str(first.get("shift_status")), SHIFT_STATUS_COMPLETED)
        self.assertEqual(str(second.get("shift_status")), SHIFT_STATUS_COMPLETED)
        self.assertEqual(Decimal(str(self.player.cash)), cash_after_first)
        self.assertEqual(self.db.query(JobAction).count(), job_actions_after_first)
        self.assertEqual(self.db.query(XGPTransaction).count(), xgp_tx_after_first)
        self.assertEqual(self.db.query(ContributionEvent).count(), contributions_after_first)
        self.assertEqual(self.db.query(PlayerTransactionLog).count(), tx_logs_after_first)
        self.assertEqual(self.db.query(GameplayTransaction).count(), gameplay_tx_after_first)
        self.assertEqual(self.db.query(ShiftSalaryAuditLog).count(), audit_rows_after_first)

    def test_main_shift_hours_do_not_consume_side_income_cap(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 12, 0)
        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )
        with patch("app.services.shift_state_service.get_houston_now", return_value=after_shift):
            resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)
            first = process_rideshare_action(self.db, self.player, trips=5)
            second = process_rideshare_action(self.db, self.player, trips=1)
            work_state = build_work_state_payload(self.db, self.player, now_houston=after_shift)
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
            with patch("app.services.shift_state_service.get_houston_now", return_value=after_shift):
                process_rideshare_action(self.db, self.player, trips=1)

    def test_rideshare_unlocks_when_no_shift_is_scheduled(self) -> None:
        self.player.main_job = None
        self.player.last_settled_day = 0
        self.db.commit()
        self.db.refresh(self.player)

        work_state = build_work_state_payload(self.db, self.player)
        result = process_rideshare_action(self.db, self.player, trips=1)
        post_action_state = build_work_state_payload(self.db, self.player)
        ledger_rows = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
                GameplayTransaction.category == "ride_share",
            )
            .all()
        )

        self.assertTrue(bool(work_state.get("no_shift_scheduled")))
        self.assertTrue(bool(work_state.get("rideshare_available")))
        self.assertIsNotNone(work_state.get("rideshare_state"))
        self.assertTrue(bool(work_state.get("rideshare_state", {}).get("can_rideshare")))
        self.assertEqual(str(work_state.get("rideshare_state", {}).get("status")), "available")
        self.assertGreater(float(post_action_state.get("rideshare_earned_today") or 0), 0.0)
        self.assertEqual(result["trips"], 1)
        self.assertGreaterEqual(len(ledger_rows), 2)
        self.assertTrue(any(float(row.amount) == 0.0 for row in ledger_rows))
        self.assertTrue(any(float(row.amount) > 0.0 for row in ledger_rows))

    def test_rideshare_state_reports_limit_reached_at_cap(self) -> None:
        self.player.main_job = None
        self.db.commit()
        self.db.refresh(self.player)

        process_rideshare_action(self.db, self.player, trips=5)
        process_rideshare_action(self.db, self.player, trips=1)

        state = build_work_state_payload(self.db, self.player)
        rideshare_state = state.get("rideshare_state") or {}

        self.assertEqual(int(rideshare_state.get("trips_today") or 0), 6)
        self.assertEqual(int(rideshare_state.get("max_trips") or 0), 6)
        self.assertFalse(bool(rideshare_state.get("can_rideshare")))
        self.assertEqual(str(rideshare_state.get("status") or ""), "limit_reached")
        self.assertFalse(bool(state.get("rideshare_available")))

    def test_rideshare_state_trips_reset_when_game_day_advances(self) -> None:
        self.player.main_job = None
        self.db.commit()
        self.db.refresh(self.player)

        process_rideshare_action(self.db, self.player, trips=5)
        process_rideshare_action(self.db, self.player, trips=1)

        game_state = self.db.query(GameState).first()
        assert game_state is not None
        game_state.current_day = 2
        self.db.commit()

        next_day_state = build_work_state_payload(self.db, self.player)
        rideshare_state = next_day_state.get("rideshare_state") or {}

        self.assertEqual(int(next_day_state.get("current_game_day") or 0), 2)
        self.assertEqual(int(rideshare_state.get("trips_today") or 0), 0)
        self.assertEqual(int(rideshare_state.get("remaining_trips") or 0), 6)
        self.assertEqual(str(rideshare_state.get("status") or ""), "available")
        self.assertTrue(bool(rideshare_state.get("can_rideshare")))

    def test_player_progress_day_prevents_stale_rideshare_cap_from_global_day_lag(self) -> None:
        self.player.main_job = None
        self.db.commit()
        self.db.refresh(self.player)

        process_rideshare_action(self.db, self.player, trips=5)
        process_rideshare_action(self.db, self.player, trips=1)

        day_one_state = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )
        assert day_one_state is not None
        day_one_state.did_settlement = True
        self.player.last_settled_day = 1
        self.db.commit()

        game_state = self.db.query(GameState).first()
        assert game_state is not None
        game_state.current_day = 1
        self.db.commit()

        work_state = build_work_state_payload(self.db, self.player)
        rideshare_state = work_state.get("rideshare_state") or {}

        self.assertEqual(int(work_state.get("current_game_day") or 0), 2)
        self.assertEqual(int(rideshare_state.get("trips_today") or 0), 0)
        self.assertEqual(int(rideshare_state.get("remaining_trips") or 0), 6)
        self.assertTrue(bool(rideshare_state.get("can_rideshare")))
        self.assertEqual(float(work_state.get("rideshare_earned_today") or 0.0), 0.0)

    def test_salary_transaction_description_is_day_explicit(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 12, 0)
        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )
        resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)

        salary_txn = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
                GameplayTransaction.category == "salary",
            )
            .order_by(GameplayTransaction.timestamp.asc())
            .first()
        )
        assert salary_txn is not None
        self.assertIn("Main job salary for Day 1", str(salary_txn.description))

    def test_completed_shift_posts_salary_audit_and_cash_delta_matches_ledger(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 12, 0)
        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        starting_cash = Decimal(str(self.player.cash))
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        work_state = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)
        self.db.refresh(self.player)

        audit = self.db.query(ShiftSalaryAuditLog).order_by(ShiftSalaryAuditLog.created_at.asc()).first()
        salary_txn = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
                GameplayTransaction.category == "salary",
            )
            .order_by(GameplayTransaction.timestamp.asc())
            .first()
        )

        assert audit is not None
        assert salary_txn is not None
        audit_paid = Decimal(str(audit.final_salary_paid))
        audit_cash_before = Decimal(str(audit.cash_before))
        audit_cash_after = Decimal(str(audit.cash_after))

        self.assertEqual(str(audit.payment_status), "posted")
        self.assertEqual(str(audit.salary_transaction_id), str(salary_txn.id))
        self.assertEqual(str(audit.job_key), "banker")
        self.assertEqual(audit_cash_before, starting_cash)
        self.assertEqual(audit_cash_before + audit_paid, audit_cash_after)
        self.assertEqual(Decimal(str(self.player.cash)), audit_cash_after)
        self.assertEqual(Decimal(str(salary_txn.amount)), audit_paid)
        self.assertTrue(bool(work_state.get("salary_transaction_confirmed")))
        self.assertEqual(str(work_state.get("salary_payment_status")), "posted")
        self.assertIsNotNone(work_state.get("current_shift_salary_audit"))
        self.assertIsNotNone(work_state.get("last_salary_posted"))

    def test_salary_post_failure_preserves_failed_audit_without_cash_mutation(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 12, 0)
        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        starting_cash = Decimal(str(self.player.cash))
        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        with patch(
            "app.services.shift_state_service.record_gameplay_transaction",
            side_effect=RuntimeError("salary ledger unavailable"),
        ):
            work_state = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)

        self.db.refresh(self.player)
        audit = self.db.query(ShiftSalaryAuditLog).order_by(ShiftSalaryAuditLog.created_at.asc()).first()
        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )

        assert audit is not None
        assert pds is not None
        self.assertEqual(str(audit.payment_status), "failed")
        self.assertIn("salary ledger unavailable", str(audit.failure_reason))
        self.assertEqual(Decimal(str(self.player.cash)), starting_cash)
        self.assertEqual(self.db.query(GameplayTransaction).count(), 0)
        self.assertEqual(str(getattr(pds, "salary_transaction_id", "") or ""), "")
        self.assertEqual(str(work_state.get("salary_payment_status")), "failed")
        self.assertFalse(bool(work_state.get("salary_transaction_confirmed")))

    def test_completed_shift_unlocks_rideshare_before_scheduled_shift_window_end(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 9, 0)
        post_shift = self._houston_datetime(2026, 1, 1, 15, 30)

        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        with patch("app.services.shift_state_service.get_houston_now", return_value=post_shift):
            payload = get_gameplay_actions(str(self.player.id), db=self.db)
        self.db.refresh(self.player)

        work_state = payload.get("work_state") or {}
        available_keys = {str(item.get("action_key")) for item in payload.get("available_actions", [])}

        self.assertFalse(bool(self.player.main_shift_active_flag))
        self.assertTrue(bool(work_state.get("shift_completed_today")))
        self.assertFalse(bool(work_state.get("is_on_shift")))
        self.assertEqual(str(work_state.get("work_status")), "off_shift_after_work")
        self.assertEqual(str(work_state.get("current_action_state")), "off_shift_after_work")
        self.assertTrue(bool(work_state.get("rideshare_unlocked")))
        self.assertTrue(bool(work_state.get("rideshare_available")))
        self.assertTrue(bool(work_state.get("can_rideshare")))
        self.assertIsNone(work_state.get("rideshare_block_reason"))
        self.assertEqual(int(work_state.get("trips_today") or 0), 0)
        self.assertEqual(int(work_state.get("trips_remaining") or 0), 6)
        self.assertEqual(int(work_state.get("remaining_time_units") or 0), 10)
        self.assertIn("side_income", available_keys)

    def test_completed_shift_reports_time_blocker_when_no_time_remains(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 9, 0)
        post_shift = self._houston_datetime(2026, 1, 1, 15, 30)

        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=post_shift)
        self.player.hours_available = 0
        self.db.commit()
        self.db.refresh(self.player)

        blocked_state = build_work_state_payload(self.db, self.player, now_houston=post_shift)

        self.assertEqual(str(blocked_state.get("work_status")), "off_shift_after_work")
        self.assertFalse(bool(blocked_state.get("rideshare_available")))
        self.assertEqual(str(blocked_state.get("rideshare_block_reason")), "Not enough time left today for rideshare.")
        self.assertEqual(str((blocked_state.get("rideshare_state") or {}).get("status") or ""), "not_enough_time")
        self.assertEqual(int(blocked_state.get("remaining_time_units") or 0), 0)

    def test_post_shift_rideshare_reports_health_and_stress_blockers(self) -> None:
        shift_start = self._houston_datetime(2026, 1, 1, 9, 0)
        post_shift = self._houston_datetime(2026, 1, 1, 15, 30)

        start_main_shift(
            self.db,
            player=self.player,
            job_name="banker",
            shift_type="standard_shift",
            hours_worked=6,
            now_houston=shift_start,
        )

        resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=post_shift)

        self.player.stress = 96
        self.db.commit()
        self.db.refresh(self.player)
        stress_blocked_state = build_work_state_payload(self.db, self.player, now_houston=post_shift)

        self.assertFalse(bool(stress_blocked_state.get("rideshare_available")))
        self.assertEqual(str(stress_blocked_state.get("rideshare_block_reason")), "Unavailable: stress too high (96/100).")
        self.assertEqual(str((stress_blocked_state.get("rideshare_state") or {}).get("status") or ""), "stress_high")

        self.player.stress = 12
        self.player.health = 12
        self.db.commit()
        self.db.refresh(self.player)
        health_blocked_state = build_work_state_payload(self.db, self.player, now_houston=post_shift)

        self.assertFalse(bool(health_blocked_state.get("rideshare_available")))
        self.assertEqual(str(health_blocked_state.get("rideshare_block_reason")), "Unavailable: health too low (12/100).")
        self.assertEqual(str((health_blocked_state.get("rideshare_state") or {}).get("status") or ""), "health_low")

    def test_weekday_missed_shift_logs_penalty_and_unlock_event(self) -> None:
        after_shift = self._houston_datetime(2026, 1, 1, 19, 5)

        work_state = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=after_shift)
        self.db.refresh(self.player)

        rows = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
            )
            .all()
        )
        categories = {str(row.category) for row in rows}
        descriptions = {str(row.description) for row in rows}
        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )

        self.assertIsNotNone(pds)
        self.assertTrue(bool(work_state.get("missed_shift_today")))
        self.assertTrue(bool(work_state.get("rideshare_available")))
        self.assertEqual(self.player.health, 87)
        self.assertEqual(self.player.stress, 18)
        self.assertTrue(bool(getattr(pds, "missed_shift", False)))
        self.assertTrue({"missed_work", "health_penalty", "ride_share"}.issubset(categories))
        self.assertIn("Rideshare unlocked at 6:00 PM", descriptions)

    def test_weekend_rules_skip_required_shift_and_unlock_rideshare_all_day(self) -> None:
        game_state = self.db.query(GameState).first()
        assert game_state is not None
        game_state.current_day = 3
        self.db.commit()

        weekend_morning = self._houston_datetime(2026, 1, 3, 10, 0)
        work_state = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=weekend_morning)
        self.db.refresh(self.player)

        self.assertTrue(bool(work_state.get("is_weekend")))
        self.assertFalse(bool(work_state.get("missed_shift_today")))
        self.assertTrue(bool(work_state.get("rideshare_unlocked")))
        self.assertTrue(bool(work_state.get("rideshare_available")))

    def test_houston_weekday_truth_uses_local_date_even_when_game_day_maps_to_weekend(self) -> None:
        game_state = self.db.query(GameState).first()
        assert game_state is not None
        game_state.current_day = 3
        self.db.commit()

        thursday_morning = self._houston_datetime(2026, 4, 9, 10, 0)
        work_state = resolve_expired_shift_if_needed(self.db, player=self.player, now_houston=thursday_morning)

        self.assertEqual(str(work_state.get("current_houston_date")), "2026-04-09")
        self.assertEqual(str(work_state.get("current_houston_date_label")), "Apr 9, 2026")
        self.assertEqual(str(work_state.get("day_of_week")), "Thursday")
        self.assertFalse(bool(work_state.get("is_weekend")))
        self.assertEqual(str(work_state.get("phase_status_label")), "Weekday")
        self.assertEqual(str(work_state.get("scheduled_shift_window_label")), "10:00 AM-6:00 PM")

    def test_rollover_market_failure_degrades_work_state_without_crashing(self) -> None:
        self.player.last_survival_resolved_date = self._houston_datetime(2026, 4, 8, 9, 0).date()
        self.db.commit()

        with patch(
            "app.services.shift_state_service._run_houston_auto_rollover_if_needed",
            side_effect=RuntimeError("duplicate key on uq_stock_daily_price_day_ticker"),
        ):
            work_state = resolve_expired_shift_if_needed(
                self.db,
                player=self.player,
                now_houston=self._houston_datetime(2026, 4, 9, 10, 0),
            )

        self.assertIn("market_data", list(work_state.get("degraded_sections") or []))
        self.assertFalse(bool(work_state.get("market_data_available")))
        self.assertIn("Market data temporarily unavailable", str(work_state.get("market_data_message") or ""))
        self.assertEqual(str(work_state.get("day_of_week")), "Thursday")
        self.assertEqual(str(work_state.get("phase_status_label")), "Weekday")


if __name__ == "__main__":
    unittest.main()
