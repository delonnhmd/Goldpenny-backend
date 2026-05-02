from __future__ import annotations

import json
import os
import unittest
import uuid
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-jwt"

from app.api import player as player_api
from app.db.database import Base
from app.models.game_state import GameState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_progression_state import PlayerProgressionState
from app.services.daily_settlement_service import SettlementValidationError, settle_player_day
from app.services.run_end_service import (
    BANKRUPTCY_WARNING,
    RETIREMENT_INELIGIBLE_REASON,
    evaluate_bankruptcy_for_player,
    get_player_run_status,
    retire_player_run,
    retirement_title_for_net_worth,
)


class RunEndServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                Player.__table__,
                GameState.__table__,
                PlayerBusiness.__table__,
                PlayerProgressionState.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.db.add(GameState(current_day=1, day_status="open"))
        self.player = Player(
            display_name="Run End Player",
            cash=Decimal("1000.00"),
            debt_xgp=Decimal("0.00"),
            credit_score=650,
            missed_payment_streak=0,
            net_worth=Decimal("1000.00"),
        )
        self.db.add(self.player)
        self.db.commit()
        self.db.refresh(self.player)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _client(self) -> TestClient:
        app = FastAPI()
        app.include_router(player_api.router, prefix="/player")

        def override_get_db():
            yield self.db

        app.dependency_overrides[player_api.get_db] = override_get_db
        return TestClient(app)

    def test_player_does_not_bankrupt_from_cash_negative_alone(self) -> None:
        self.player.cash_xgp = Decimal("-1.00")
        self.player.debt_xgp = Decimal("0.00")
        self.player.credit_score = 650
        self.player.missed_payment_streak = 0
        self.db.commit()

        result = evaluate_bankruptcy_for_player(self.db, self.player, day_number=4)

        self.assertFalse(result["triggered"])
        self.assertEqual(self.player.run_status, "active")
        self.assertEqual(result["risk_warnings"], [])

    def test_bankruptcy_requires_all_four_conditions(self) -> None:
        base = {
            "cash_xgp": Decimal("-1.00"),
            "debt_xgp": Decimal("2500.00"),
            "credit_score": 520,
            "missed_payment_streak": 3,
        }
        variants = [
            {**base, "cash_xgp": Decimal("0.00")},
            {**base, "debt_xgp": Decimal("2499.99")},
            {**base, "credit_score": 521},
            {**base, "missed_payment_streak": 2},
        ]
        for idx, values in enumerate(variants):
            with self.subTest(idx=idx):
                player = Player(display_name=f"Variant {idx}", net_worth=Decimal("0.00"), **values)
                self.db.add(player)
                self.db.commit()
                result = evaluate_bankruptcy_for_player(self.db, player, day_number=8)
                self.assertFalse(result["triggered"])
                self.assertEqual(player.run_status, "active")

        self.player.cash_xgp = Decimal("-1.00")
        self.player.debt_xgp = Decimal("2500.00")
        self.player.credit_score = 520
        self.player.missed_payment_streak = 3
        self.player.net_worth_xgp = Decimal("-2501.00")
        self.db.commit()

        result = evaluate_bankruptcy_for_player(self.db, self.player, day_number=8, commit=True)

        self.assertTrue(result["triggered"])
        self.assertEqual(self.player.run_status, "bankrupt")

    def test_bankruptcy_sets_run_status_and_end_summary(self) -> None:
        self.player.cash_xgp = Decimal("-5.00")
        self.player.debt_xgp = Decimal("3000.00")
        self.player.credit_score = 500
        self.player.missed_payment_streak = 3
        self.player.net_worth_xgp = Decimal("-3005.00")
        self.db.add(
            PlayerBusiness(
                player_id=self.player.id,
                business_id="fruit_shop",
                business_level=1,
                is_active=True,
            )
        )
        self.db.add(
            PlayerProgressionState(
                player_id=self.player.id,
                login_streak_best=5,
                productive_day_streak_best=2,
            )
        )
        self.db.commit()

        result = evaluate_bankruptcy_for_player(self.db, self.player, day_number=12, commit=True)
        summary = result["end_state"]["summary"]

        self.assertEqual(self.player.run_status, "bankrupt")
        self.assertIsNotNone(self.player.run_ended_at)
        self.assertEqual(self.player.run_end_day, 12)
        self.assertEqual(self.player.run_end_reason, "bankruptcy")
        self.assertEqual(summary["debt"], 3000.0)
        self.assertEqual(summary["credit_score"], 500)
        self.assertEqual(summary["days_survived"], 12)
        self.assertEqual(summary["businesses_owned"], 1)
        self.assertEqual(summary["land_owned"], 0)
        self.assertEqual(summary["best_streak"], 5)

    def test_bankrupt_player_cannot_settle_another_normal_day(self) -> None:
        self.player.run_status = "bankrupt"
        self.player.run_end_reason = "bankruptcy"
        self.player.run_end_summary_json = json.dumps({"days_survived": 3})
        self.db.commit()

        with self.assertRaises(SettlementValidationError):
            settle_player_day(self.db, str(self.player.id))

    def test_bankruptcy_warning_appears_before_trigger(self) -> None:
        self.player.cash_xgp = Decimal("-1.00")
        self.player.debt_xgp = Decimal("2500.00")
        self.player.credit_score = 520
        self.player.missed_payment_streak = 2
        self.db.commit()

        result = evaluate_bankruptcy_for_player(self.db, self.player, day_number=7)

        self.assertFalse(result["triggered"])
        self.assertEqual(result["risk_warnings"], [BANKRUPTCY_WARNING])
        self.assertEqual(self.player.run_status, "active")

    def test_retirement_blocked_before_day_30(self) -> None:
        self.db.query(GameState).first().current_day = 29
        self.player.net_worth_xgp = Decimal("10000.00")
        self.db.commit()

        result = retire_player_run(self.db, str(self.player.id))

        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], RETIREMENT_INELIGIBLE_REASON)
        self.assertEqual(result["run_status"], "active")

    def test_retirement_blocked_below_net_worth_threshold(self) -> None:
        self.db.query(GameState).first().current_day = 30
        self.player.net_worth_xgp = Decimal("9999.99")
        self.db.commit()

        result = retire_player_run(self.db, str(self.player.id))

        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], RETIREMENT_INELIGIBLE_REASON)
        self.assertEqual(result["run_status"], "active")

    def test_retirement_succeeds_when_eligible(self) -> None:
        self.db.query(GameState).first().current_day = 30
        self.player.cash_xgp = Decimal("12500.00")
        self.player.net_worth_xgp = Decimal("12500.00")
        self.db.commit()

        response = self._client().post(f"/player/{self.player.id}/retire")
        payload = response.json()
        self.db.refresh(self.player)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["eligible"])
        self.assertEqual(payload["run_status"], "retired")
        self.assertEqual(payload["run_end_reason"], "voluntary_retirement")
        self.assertEqual(payload["run_end_summary"]["retirement_title"], "Stable Owner")
        self.assertFalse(payload["can_continue"])
        self.assertEqual(self.player.run_status, "retired")

    def test_retirement_title_works_by_net_worth_threshold(self) -> None:
        self.assertEqual(retirement_title_for_net_worth(Decimal("10000")), "Stable Owner")
        self.assertEqual(retirement_title_for_net_worth(Decimal("50000")), "Independent Operator")
        self.assertEqual(retirement_title_for_net_worth(Decimal("100000")), "Financially Free")

    def test_run_status_endpoint_returns_active_bankrupt_and_retired(self) -> None:
        client = self._client()

        active = client.get(f"/player/{self.player.id}/run-status").json()
        self.assertEqual(active["run_status"], "active")
        self.assertTrue(active["can_continue"])

        self.player.run_status = "bankrupt"
        self.player.run_end_reason = "bankruptcy"
        self.player.run_end_day = 11
        self.player.run_end_summary_json = json.dumps({"days_survived": 11})
        self.db.commit()
        bankrupt = client.get(f"/player/{self.player.id}/run-status").json()
        self.assertEqual(bankrupt["run_status"], "bankrupt")
        self.assertFalse(bankrupt["can_continue"])
        self.assertEqual(bankrupt["run_end_summary"]["days_survived"], 11)

        self.player.run_status = "retired"
        self.player.run_end_reason = "voluntary_retirement"
        self.player.run_end_day = 42
        self.player.run_end_summary_json = json.dumps({"days_survived": 42, "retirement_title": "Stable Owner"})
        self.db.commit()
        retired = client.get(f"/player/{self.player.id}/run-status").json()
        self.assertEqual(retired["run_status"], "retired")
        self.assertFalse(retired["can_continue"])
        self.assertEqual(retired["run_end_reason"], "voluntary_retirement")

    def test_service_run_status_returns_retirement_requirement(self) -> None:
        status = get_player_run_status(self.db, self.player.id)

        self.assertEqual(status["retirement_requirement"]["min_day"], 30)
        self.assertEqual(status["retirement_requirement"]["min_net_worth"], 10000.0)
        self.assertIn("current_day", status["retirement_requirement"])
        self.assertIn("current_net_worth", status["retirement_requirement"])


if __name__ == "__main__":
    unittest.main()
