from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-jwt")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import player as player_api
from app.db.database import Base, get_db
from app.models.player import Player
from app.models.user import User


class PlayerByUserIdApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            future=True,
            autocommit=False,
            autoflush=False,
        )
        Base.metadata.create_all(bind=self.engine, tables=[User.__table__, Player.__table__])
        self.db = self.SessionLocal()

        self.app = FastAPI()
        self.app.include_router(player_api.router, prefix="/player")

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

    def _make_player(self) -> tuple[User, Player]:
        user = User(email=f"user-{uuid.uuid4()}@example.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=str(user.id),
            display_name="Linked Player",
            region="suburban",
            cash=Decimal("1234.50"),
            bank_savings_xgp=Decimal("25.00"),
            debt_xgp=Decimal("10.00"),
            credit_score=710,
            net_worth=Decimal("1249.50"),
            health=91,
            stress=12,
            hours_available=24,
            account_created_day=1,
        )
        self.db.add(player)
        self.db.commit()
        self.db.refresh(player)
        return user, player

    def test_get_player_by_user_id_returns_linked_profile(self) -> None:
        user, player = self._make_player()

        response = self.client.get(f"/player/by-user-id/{user.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(player.id))
        self.assertEqual(payload["user_id"], str(user.id))
        self.assertEqual(payload["display_name"], "Linked Player")
        self.assertEqual(payload["cash_xgp"], 1234.5)
        self.assertEqual(payload["health"], 91)
        self.assertEqual(payload["run_status"], "active")

    def test_get_player_by_user_id_returns_404_when_missing(self) -> None:
        response = self.client.get(f"/player/by-user-id/{uuid.uuid4()}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Player profile not found.")


if __name__ == "__main__":
    unittest.main()
