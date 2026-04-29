from __future__ import annotations

import os
import unittest

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-jwt")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import notifications
from app.db.database import Base, get_db
from app.models.player import Player
from app.models.player_push_token import PlayerPushToken
from app.services import notification_service


class NotificationApiTests(unittest.TestCase):
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
            ],
        )
        self.db = self.SessionLocal()
        self.player = Player(display_name="Push Tester")
        self.db.add(self.player)
        self.db.commit()
        self.db.refresh(self.player)

        self.app = FastAPI()
        self.app.include_router(notifications.router, prefix="/notifications")

        def _override_db():
            try:
                yield self.db
            finally:
                pass

        self.app.dependency_overrides[get_db] = _override_db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_register_token_creates_player_push_token(self) -> None:
        response = self.client.post(
            "/notifications/register-token",
            json={
                "player_id": str(self.player.id),
                "push_token": "ExponentPushToken[test-token]",
                "platform": "ios",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["player_id"], str(self.player.id))
        self.assertEqual(payload["platform"], "ios")

        rows = self.db.query(PlayerPushToken).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].push_token, "ExponentPushToken[test-token]")

    def test_register_token_is_idempotent_by_push_token(self) -> None:
        request = {
            "player_id": str(self.player.id),
            "push_token": "ExponentPushToken[test-token]",
            "platform": "ios",
        }

        first = self.client.post("/notifications/register-token", json=request)
        second = self.client.post("/notifications/register-token", json={**request, "platform": "android"})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(self.db.query(PlayerPushToken).count(), 1)
        self.assertEqual(second.json()["token_id"], first.json()["token_id"])
        self.assertEqual(second.json()["platform"], "android")

    def test_test_endpoint_sends_to_all_player_tokens(self) -> None:
        self.db.add_all(
            [
                PlayerPushToken(
                    player_id=self.player.id,
                    push_token="ExponentPushToken[token-1]",
                    platform="ios",
                ),
                PlayerPushToken(
                    player_id=self.player.id,
                    push_token="ExponentPushToken[token-2]",
                    platform="android",
                ),
            ]
        )
        self.db.commit()

        calls: list[dict] = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "data": [
                        {"status": "ok", "id": "ticket-1"},
                        {"status": "ok", "id": "ticket-2"},
                    ]
                }

        def fake_post(url: str, json: list[dict], timeout: float) -> FakeResponse:
            calls.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse()

        original_post = notification_service.httpx.post
        notification_service.httpx.post = fake_post
        try:
            response = self.client.post(
                "/notifications/test",
                json={
                    "player_id": str(self.player.id),
                    "title": "Test",
                    "body": "Push is working",
                },
            )
        finally:
            notification_service.httpx.post = original_post

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tokens"], 2)
        self.assertEqual(payload["sent"], 2)
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(calls[0]["url"], notification_service.EXPO_PUSH_SEND_URL)
        self.assertEqual(len(calls[0]["json"]), 2)


if __name__ == "__main__":
    unittest.main()
