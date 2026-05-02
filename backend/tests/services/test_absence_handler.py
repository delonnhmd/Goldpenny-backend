"""Phase 3-C Player Absence Handling tests."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-jwt")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.services import absence_handler_service as absence


GAME_TZ = ZoneInfo(absence.GAME_TIMEZONE)


def _at(year: int, month: int, day: int, hour: int = 9) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=GAME_TZ)


class AbsenceHandlerTests(unittest.TestCase):
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
            tables=[Player.__table__, PlayerBusiness.__table__],
        )
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _make_player(
        self,
        *,
        run_status: str = "active",
        anchor: datetime | None = None,
        health: int = 100,
        stress: int = 0,
        cash: float = 1000.0,
        required_daily_debt: float = 0.0,
    ) -> Player:
        player = Player(
            display_name="Absentee",
            run_status=run_status,
            health=health,
            stress=stress,
            cash=cash,
            required_daily_debt_payment_xgp=required_daily_debt,
        )
        if anchor is not None:
            player.last_settlement_at = anchor
            player.last_seen_at = anchor
        self.db.add(player)
        self.db.commit()
        self.db.refresh(player)
        return player

    def _make_business(self, player: Player, *, produce: float = 100.0) -> PlayerBusiness:
        biz = PlayerBusiness(
            player_id=player.id,
            business_id="fruit_shop",
            inventory_produce_units=produce,
            inventory_essentials_units=0,
            inventory_protein_units=0,
        )
        self.db.add(biz)
        self.db.commit()
        self.db.refresh(biz)
        return biz

    # ── tests ─────────────────────────────────────────────────────────────
    def test_no_missed_days_returns_zero_summary(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        # Same calendar day → zero missed.
        summary = absence.run_absence_check(self.db, player, server_now=anchor + timedelta(hours=2))
        self.assertEqual(summary["missed_days"], 0)
        self.assertEqual(summary["health_change"], 0)
        self.assertEqual(summary["stress_change"], 0)
        self.assertEqual(summary["warnings"], [])
        self.assertEqual(player.health, 100)

    def test_one_missed_day_applies_light_penalty(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        # Two calendar days later → 1 missed full day in between.
        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 3))
        self.assertEqual(summary["missed_days"], 1)
        self.assertEqual(summary["health_change"], -absence.HEALTH_LOSS_PER_DAY)
        self.assertEqual(summary["stress_change"], absence.STRESS_GAIN_PER_DAY)
        self.assertEqual(player.health, 100 - absence.HEALTH_LOSS_PER_DAY)
        self.assertEqual(player.stress, absence.STRESS_GAIN_PER_DAY)

    def test_three_missed_days_applies_stronger_penalty(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        # Five days later → 3 missed full days.
        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 5))
        self.assertEqual(summary["missed_days"], 3)
        self.assertEqual(summary["health_change"], -3 * absence.HEALTH_LOSS_PER_DAY)
        self.assertEqual(summary["stress_change"], 3 * absence.STRESS_GAIN_PER_DAY)
        # Stronger than 1-day case.
        single_day_loss = absence.HEALTH_LOSS_PER_DAY
        self.assertGreater(abs(summary["health_change"]), single_day_loss)

    def test_business_inventory_spoils_during_absence(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        biz = self._make_business(player, produce=100.0)

        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 4))
        self.assertEqual(summary["missed_days"], 2)
        self.assertGreater(summary["inventory_spoilage"], 0.0)
        # 100 * (0.9)^2 = 81 → ~19 spoiled.
        self.db.refresh(biz)
        remaining = float(biz.inventory_produce_units)
        self.assertAlmostEqual(remaining, 81.0, delta=0.01)
        self.assertTrue(any("spoiled" in w for w in summary["warnings"]))

    def test_work_is_not_auto_run(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        cash_before = float(player.cash)
        absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 4))
        # No work auto-run: only the bills/debt path can change cash, and
        # this player has no debt → cash unchanged.
        self.assertEqual(float(player.cash), cash_before)
        # Work counters untouched.
        self.assertEqual(player.work_actions_today, 0)
        self.assertEqual(player.total_hours_worked_today, 0)

    def test_business_is_not_auto_run(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        biz = self._make_business(player, produce=100.0)
        ops_before = biz.times_operated_today
        runs_before = biz.lifetime_business_runs

        absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 4))
        self.db.refresh(biz)
        self.assertEqual(biz.times_operated_today, ops_before)
        self.assertEqual(biz.lifetime_business_runs, runs_before)

    def test_bankrupt_player_is_skipped(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor, run_status="bankrupt")
        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 5))
        self.assertEqual(summary["missed_days"], 0)
        self.assertEqual(summary["skipped_reason"], "bankrupt")
        self.assertEqual(player.health, 100)
        self.assertEqual(player.stress, 0)

    def test_retired_player_is_skipped(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor, run_status="retired")
        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 5))
        self.assertEqual(summary["skipped_reason"], "retired")
        self.assertEqual(player.health, 100)

    def test_summary_appears_in_gameplay_bundle_payload_shape(self) -> None:
        # The bundle shape contract is exercised here by checking that
        # the dict carries every key the frontend normalizes.
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor)
        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 3))
        for key in (
            "missed_days",
            "health_change",
            "stress_change",
            "cash_change",
            "inventory_spoilage",
            "warnings",
        ):
            self.assertIn(key, summary)

    def test_bills_pressure_deducts_cash_when_owed(self) -> None:
        anchor = _at(2026, 5, 1)
        player = self._make_player(anchor=anchor, required_daily_debt=20.0, cash=500.0)
        summary = absence.run_absence_check(self.db, player, server_now=_at(2026, 5, 4))
        self.assertEqual(summary["missed_days"], 2)
        self.assertEqual(summary["cash_change"], -40.0)
        self.assertAlmostEqual(float(player.cash), 460.0, places=2)


if __name__ == "__main__":
    unittest.main()
