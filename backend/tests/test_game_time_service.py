from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import game_time
from app.services.game_time_service import (
    GAME_TIMEZONE,
    get_game_time_payload,
    get_next_morning_brief_at,
    get_next_settlement_at,
)


class GameTimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tz = ZoneInfo(GAME_TIMEZONE)

    def test_next_settlement_before_midnight_is_next_local_midnight(self) -> None:
        now = datetime(2026, 4, 29, 22, 30, 0, tzinfo=self.tz)

        result = get_next_settlement_at(now)

        self.assertEqual(result, datetime(2026, 4, 30, 0, 0, 0, tzinfo=self.tz))
        self.assertIsNotNone(result.tzinfo)

    def test_next_settlement_exact_midnight_returns_following_midnight(self) -> None:
        now = datetime(2026, 4, 30, 0, 0, 0, tzinfo=self.tz)

        result = get_next_settlement_at(now)

        self.assertEqual(result, datetime(2026, 5, 1, 0, 0, 0, tzinfo=self.tz))
        self.assertIsNotNone(result.tzinfo)

    def test_next_morning_brief_before_7am_returns_today_7am(self) -> None:
        now = datetime(2026, 4, 29, 6, 30, 0, tzinfo=self.tz)

        result = get_next_morning_brief_at(now)

        self.assertEqual(result, datetime(2026, 4, 29, 7, 0, 0, tzinfo=self.tz))
        self.assertIsNotNone(result.tzinfo)

    def test_next_morning_brief_after_7am_returns_tomorrow_7am(self) -> None:
        now = datetime(2026, 4, 29, 8, 30, 0, tzinfo=self.tz)

        result = get_next_morning_brief_at(now)

        self.assertEqual(result, datetime(2026, 4, 30, 7, 0, 0, tzinfo=self.tz))
        self.assertIsNotNone(result.tzinfo)

    def test_payload_uses_timezone_aware_dst_safe_seconds(self) -> None:
        now = datetime(2026, 3, 8, 1, 30, 0, tzinfo=self.tz)

        payload = get_game_time_payload(now)
        next_brief = datetime.fromisoformat(payload["next_morning_brief_at"])
        expected_seconds = int(
            (
                next_brief.astimezone(timezone.utc)
                - now.astimezone(timezone.utc)
            ).total_seconds()
        )

        self.assertIsNotNone(datetime.fromisoformat(payload["server_now"]).tzinfo)
        self.assertIsNotNone(datetime.fromisoformat(payload["next_settlement_at"]).tzinfo)
        self.assertIsNotNone(next_brief.tzinfo)
        self.assertEqual(payload["seconds_until_morning_brief"], expected_seconds)

    def test_game_time_endpoint_returns_required_fields(self) -> None:
        app = FastAPI()
        app.include_router(game_time.router)
        client = TestClient(app)

        response = client.get("/game-time")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in [
            "server_now",
            "timezone",
            "next_settlement_at",
            "next_morning_brief_at",
            "seconds_until_settlement",
            "seconds_until_morning_brief",
        ]:
            self.assertIn(key, payload)
        self.assertEqual(payload["timezone"], GAME_TIMEZONE)
        self.assertGreater(payload["seconds_until_settlement"], 0)
        self.assertGreater(payload["seconds_until_morning_brief"], 0)


if __name__ == "__main__":
    unittest.main()
