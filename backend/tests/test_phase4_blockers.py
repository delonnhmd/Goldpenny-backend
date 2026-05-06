"""Tests for Phase 4 blocker fix pass.

Covers:
  Block 1: Map slot purchase deducts backend cash and respects run_status.
  Block 2: Portfolio summary does not double-count inventory; aligns with net worth.
  Block 3: execute_gameplay_action is blocked for bankrupt/retired players.
"""

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

from app.db.database import Base, get_db
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.enums import BasketType
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.user import User
from app.services import portfolio_asset_service


# ─────────────────────────────────────────────────────────────────────────────
# Block 1 + Block 3: API-level tests (slot purchase, action enforcement)
# ─────────────────────────────────────────────────────────────────────────────


class GameplayBlockerApiTests(unittest.TestCase):
    """API tests for the slot-purchase endpoint and run_status enforcement."""

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine, future=True, autocommit=False, autoflush=False
        )
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerTransactionLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        # Import router lazily so model registry is fully resolved first.
        from app.api import gameplay

        self.app = FastAPI()
        self.app.include_router(gameplay.router, prefix="/gameplay")

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

    def _make_player(
        self,
        *,
        cash: Decimal = Decimal("1000.00"),
        run_status: str = "active",
    ) -> Player:
        user = User(email=f"u-{uuid.uuid4()}@example.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=str(user.id),
            display_name="Block Tester",
            cash=cash,
            run_status=run_status,
        )
        self.db.add(player)
        self.db.commit()
        self.db.refresh(player)
        return player

    # ── Block 1: slot purchase ───────────────────────────────────────────────

    def test_slot_purchase_deducts_backend_cash(self) -> None:
        player = self._make_player(cash=Decimal("500.00"))
        response = self.client.post(
            f"/gameplay/player/{player.id}/map/purchase_slot",
            json={
                "tile_key": "downtown:lot-3",
                "district_key": "downtown",
                "price_xgp": 200,
                "address": "1203 Market Line Ave",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["cash_before_xgp"], 500.0)
        self.assertEqual(body["cash_after_xgp"], 300.0)
        self.assertEqual(body["price_xgp"], 200.0)

        self.db.expire_all()
        refreshed = self.db.query(Player).filter(Player.id == player.id).first()
        self.assertEqual(Decimal(str(refreshed.cash)).quantize(Decimal("0.01")), Decimal("300.00"))

    def test_slot_purchase_fails_when_insufficient_cash(self) -> None:
        player = self._make_player(cash=Decimal("50.00"))
        response = self.client.post(
            f"/gameplay/player/{player.id}/map/purchase_slot",
            json={
                "tile_key": "downtown:lot-3",
                "district_key": "downtown",
                "price_xgp": 200,
            },
        )
        self.assertEqual(response.status_code, 402)
        self.db.expire_all()
        refreshed = self.db.query(Player).filter(Player.id == player.id).first()
        # Cash unchanged.
        self.assertEqual(Decimal(str(refreshed.cash)).quantize(Decimal("0.01")), Decimal("50.00"))

    def test_slot_purchase_blocked_for_bankrupt_player(self) -> None:
        player = self._make_player(cash=Decimal("1000.00"), run_status="bankrupt")
        response = self.client.post(
            f"/gameplay/player/{player.id}/map/purchase_slot",
            json={"tile_key": "x", "district_key": "downtown", "price_xgp": 100},
        )
        self.assertEqual(response.status_code, 409)

    # ── Block 3: action enforcement ──────────────────────────────────────────

    def test_execute_action_blocked_for_bankrupt(self) -> None:
        player = self._make_player(run_status="bankrupt")
        response = self.client.post(
            f"/gameplay/player/{player.id}/actions/execute",
            json={"action_key": "work_shift", "parameters": {}},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("bankrupt", response.json().get("detail", "").lower())

    def test_execute_action_blocked_for_retired(self) -> None:
        player = self._make_player(run_status="retired")
        response = self.client.post(
            f"/gameplay/player/{player.id}/actions/execute",
            json={"action_key": "work_shift", "parameters": {}},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("retired", response.json().get("detail", "").lower())


# ─────────────────────────────────────────────────────────────────────────────
# Block 2: Portfolio inventory double-count fix
# ─────────────────────────────────────────────────────────────────────────────


class PortfolioInventoryAlignmentTests(unittest.TestCase):
    """Portfolio summary must not count inventory both inside business_value
    and again as inventory_value.
    """

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            bind=self.engine, future=True, autocommit=False, autoflush=False
        )
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BasketDailyPrice.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"u-{uuid.uuid4()}@example.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=str(user.id),
            display_name="Portfolio Tester",
            cash=Decimal("500.00"),
            debt_xgp=Decimal("0"),
            net_worth=Decimal("500.00"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.business = PlayerBusiness(
            id=uuid.uuid4(),
            player_id=self.player.id,
            business_id="fruit_shop",
            business_name="Fruit Shop",
            region="suburban",
            business_level=1,
            reputation=50,
            inventory_produce_units=Decimal("100"),
            inventory_essentials_units=Decimal("0"),
            inventory_protein_units=Decimal("0"),
            created_day=1,
            last_operated_day=1,
            is_active=True,
        )
        self.db.add(self.business)

        self.db.add(
            BasketDailyPrice(
                day=1,
                basket_type=BasketType.produce,
                price_index=Decimal("100.00"),
                daily_change_pct=Decimal("0"),
                supply_pressure=Decimal("1"),
                demand_pressure=Decimal("1"),
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_total_assets_does_not_double_count_inventory(self) -> None:
        summary = portfolio_asset_service.get_player_portfolio_asset_summary(
            self.db, self.player.id
        )
        cash = Decimal(str(summary["cash"]))
        stocks = Decimal(str(summary["stock_holdings_value"]))
        business_value = Decimal(str(summary["business_value"]))
        inventory_value = Decimal(str(summary["inventory_value"]))
        total_assets = Decimal(str(summary["total_assets"]))

        # V1 rule: total_assets = cash + stocks + business_value (excl inv) + inventory_value.
        expected_total = (cash + stocks + business_value + inventory_value).quantize(Decimal("0.01"))
        self.assertEqual(total_assets.quantize(Decimal("0.01")), expected_total)

        # business_value must EXCLUDE inventory in the V1 portfolio path.
        # Compute business_value with inventory included via the same helper to ensure
        # the portfolio path is using inventory_value=0.
        from app.services.portfolio_asset_service import (
            calculate_inventory_value_for_business,
            estimate_business_value,
        )

        inventory_calc = calculate_inventory_value_for_business(
            self.db, self.business, day=1
        )
        business_value_with_inv = estimate_business_value(
            self.db, self.business, day=1, inventory_value=inventory_calc
        )
        business_value_without_inv = estimate_business_value(
            self.db, self.business, day=1, inventory_value=Decimal("0")
        )
        self.assertGreater(business_value_with_inv, business_value_without_inv)
        # Reported business_value matches the WITHOUT-inventory variant.
        self.assertEqual(
            Decimal(str(summary["business_value"])).quantize(Decimal("0.01")),
            business_value_without_inv.quantize(Decimal("0.01")),
        )

    def test_inventory_value_reported_separately_and_positive(self) -> None:
        summary = portfolio_asset_service.get_player_portfolio_asset_summary(
            self.db, self.player.id
        )
        self.assertGreater(Decimal(str(summary["inventory_value"])), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
