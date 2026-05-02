"""Phase 3-C Push Scheduling: scheduler dispatcher tests."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-jwt")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.player import Player
from app.models.player_notification_log import PlayerNotificationLog
from app.models.player_push_token import PlayerPushToken
from app.services import daily_loop_notifications_service as dispatcher
from app.services import notification_service


GAME_TZ = ZoneInfo("America/Chicago")


class DailyLoopNotificationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, future=True, autocommit=False, autoflush=False)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                Player.__table__,
                PlayerPushToken.__table__,
                PlayerNotificationLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        self.sent_messages: list[list[dict]] = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"data": [{"status": "ok", "id": "ticket"}]}

        def fake_post(url, json, timeout):  # noqa: ANN001
            self.sent_messages.append(json)
            return FakeResponse()

        self._original_post = notification_service.httpx.post
        notification_service.httpx.post = fake_post

        self._brief = datetime(2026, 5, 1, 7, 0, tzinfo=GAME_TZ)
        self._settlement = datetime(2026, 5, 2, 0, 0, tzinfo=GAME_TZ)

    def tearDown(self) -> None:
        notification_service.httpx.post = self._original_post
        self.db.close()
        self.engine.dispose()

    # ── helpers ───────────────────────────────────────────────────────────
    def _make_player(self, *, run_status: str = "active", with_token: bool = True) -> Player:
        player = Player(display_name="Push Player", run_status=run_status)
        self.db.add(player)
        self.db.commit()
        self.db.refresh(player)
        if with_token:
            self.db.add(
                PlayerPushToken(
                    player_id=player.id,
                    push_token=f"ExponentPushToken[{player.id}]",
                    platform="ios",
                )
            )
            self.db.commit()
        return player

    def _patch_clock(self, server_now: datetime) -> None:
        dispatcher.get_server_now = lambda: server_now  # type: ignore[assignment]
        dispatcher.get_next_morning_brief_at = lambda now=None: self._brief  # type: ignore[assignment]
        dispatcher.get_next_settlement_at = lambda now=None: self._settlement  # type: ignore[assignment]
        dispatcher.get_game_time_payload = lambda: {  # type: ignore[assignment]
            "server_now": server_now.isoformat(),
            "timezone": "America/Chicago",
            "next_settlement_at": self._settlement.isoformat(),
            "next_morning_brief_at": self._brief.isoformat(),
            "seconds_until_settlement": 0,
            "seconds_until_morning_brief": 0,
        }

    # ── tests ─────────────────────────────────────────────────────────────
    def test_morning_brief_sends_inside_window(self) -> None:
        player = self._make_player()
        self._patch_clock(self._brief + timedelta(minutes=2))

        summary = dispatcher.run_daily_loop_notifications(db=self.db)

        self.assertIn("MORNING_BRIEF_READY", summary["due_types"])
        results = summary["results"]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[0]["skipped"])
        self.assertEqual(results[0]["notification_type"], "MORNING_BRIEF_READY")

        log_rows = self.db.query(PlayerNotificationLog).all()
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(log_rows[0].player_id, player.id)
        self.assertEqual(log_rows[0].notification_type, "MORNING_BRIEF_READY")
        self.assertEqual(log_rows[0].status, "sent")

        self.assertEqual(len(self.sent_messages), 1)
        msg = self.sent_messages[0][0]
        self.assertEqual(msg["data"], {"screen": "Life", "type": "daily_brief"})

    def test_settlement_reminder_sends_30_minutes_before_settlement(self) -> None:
        self._make_player()
        # 30 minutes before settlement is the window start; pick the moment.
        self._patch_clock(self._settlement - timedelta(minutes=30))

        summary = dispatcher.run_daily_loop_notifications(db=self.db)
        self.assertIn("SETTLEMENT_REMINDER", summary["due_types"])
        self.assertEqual(summary["sent"], 1)

        log = self.db.query(PlayerNotificationLog).one()
        self.assertEqual(log.notification_type, "SETTLEMENT_REMINDER")
        msg = self.sent_messages[0][0]
        self.assertEqual(msg["data"], {"screen": "Summary", "type": "settlement_reminder"})

    def test_duplicate_push_is_blocked(self) -> None:
        self._make_player()
        self._patch_clock(self._brief + timedelta(minutes=1))

        first = dispatcher.run_daily_loop_notifications(db=self.db)
        second = dispatcher.run_daily_loop_notifications(db=self.db)

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(self.db.query(PlayerNotificationLog).count(), 1)
        self.assertEqual(len(self.sent_messages), 1)

    def test_bankrupt_player_does_not_receive_push(self) -> None:
        self._make_player(run_status="bankrupt")
        self._patch_clock(self._brief + timedelta(minutes=1))

        summary = dispatcher.run_daily_loop_notifications(db=self.db)

        self.assertEqual(summary["players_considered"], 0)
        self.assertEqual(summary["results"], [])
        self.assertEqual(self.db.query(PlayerNotificationLog).count(), 0)
        self.assertEqual(self.sent_messages, [])

    def test_retired_player_does_not_receive_push(self) -> None:
        self._make_player(run_status="retired")
        self._patch_clock(self._brief + timedelta(minutes=1))

        summary = dispatcher.run_daily_loop_notifications(db=self.db)
        self.assertEqual(summary["players_considered"], 0)
        self.assertEqual(self.db.query(PlayerNotificationLog).count(), 0)

    def test_player_without_token_is_skipped(self) -> None:
        self._make_player(with_token=False)
        self._patch_clock(self._brief + timedelta(minutes=1))

        summary = dispatcher.run_daily_loop_notifications(db=self.db)
        # Active but no token: counted as considered, no result row.
        self.assertEqual(summary["players_considered"], 1)
        self.assertEqual(summary["results"], [])
        self.assertEqual(self.db.query(PlayerNotificationLog).count(), 0)
        self.assertEqual(self.sent_messages, [])

    def test_push_payload_contains_screen_and_type(self) -> None:
        self._make_player()
        self._patch_clock(self._brief + timedelta(minutes=1))

        summary = dispatcher.run_daily_loop_notifications(db=self.db)
        result = summary["results"][0]
        self.assertEqual(result["payload"]["data"]["screen"], "Life")
        self.assertEqual(result["payload"]["data"]["type"], "daily_brief")
        self.assertEqual(result["payload"]["title"], "New Day Ready")

    def test_scheduler_continues_if_one_player_push_fails(self) -> None:
        bad = self._make_player()
        good = self._make_player()
        self._patch_clock(self._brief + timedelta(minutes=1))

        original_send = notification_service.send_push_notification
        bad_id = str(bad.id)

        def flaky_send(player_id, *args, **kwargs):  # noqa: ANN001
            if str(player_id) == bad_id:
                raise RuntimeError("boom")
            return original_send(player_id, *args, **kwargs)

        notification_service.send_push_notification = flaky_send
        try:
            summary = dispatcher.run_daily_loop_notifications(db=self.db)
        finally:
            notification_service.send_push_notification = original_send

        # Two players considered; the good one should still have a sent log.
        self.assertEqual(summary["players_considered"], 2)
        good_logs = (
            self.db.query(PlayerNotificationLog)
            .filter(PlayerNotificationLog.player_id == good.id)
            .all()
        )
        self.assertEqual(len(good_logs), 1)
        self.assertEqual(good_logs[0].status, "sent")
        # Bad player either has a failed log or none, but the run did not crash.
        bad_logs = (
            self.db.query(PlayerNotificationLog)
            .filter(PlayerNotificationLog.player_id == bad.id)
            .all()
        )
        for row in bad_logs:
            self.assertNotEqual(row.status, "sent")


if __name__ == "__main__":
    unittest.main()
