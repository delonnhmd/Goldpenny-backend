"""Tests for consumption_behavior_service.py

Coverage:
  1. compute spending creates one basket_consumption_log row
  2. rerun same player/day does not duplicate consumption log
  3. essentials spending is more stable than convenience under pressure
  4. high stress meaningfully changes convenience spending in a bounded way
  5. high housing/debt pressure reduces flexible basket spending
  6. settlement summary includes refined basket spend fields
  7. unemployment / low-cash scenario increases budget pressure and reduces
     flexible consumption
"""

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_consumption.db")

from app.db.database import Base
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business import Business
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.debt_credit_log import DebtCreditLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.game_state import GameState
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.consumption_behavior_service import (
    compute_player_daily_consumption,
    get_player_consumption_summary,
)
from app.services.daily_settlement_service import settle_player_day

JOB_SEED = {
    "retail_worker": Decimal("2600.00"),
    "banker": Decimal("5100.00"),
}

TICKER_SECTOR = {
    "GPEN": "energy",
    "GPTECH": "technology",
    "GPRETAIL": "retail",
    "GPHEALTH": "healthcare",
    "GPBANK": "finance",
    "GPAUTO": "automotive",
    "GPTRANS": "transport",
    "GPREAL": "real_estate",
    "GPDEF": "defense",
    "GPCONS": "consumer",
}


class ConsumptionBehaviorTests(unittest.TestCase):
    # ── 1. Shared test infrastructure ─────────────────────────────────────────

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )

        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                GameState.__table__,
                JobDefinitionDB.__table__,
                Business.__table__,
                PlayerBusiness.__table__,
                PlayerEmploymentState.__table__,
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DebtCreditLog.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                StockDailyPrice.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                MacroDailyState.__table__,
            ],
        )

        db = self.SessionLocal()
        # Seed job definitions needed by settlement
        for job_code, pay in JOB_SEED.items():
            db.add(
                JobDefinitionDB(
                    job_code=job_code,
                    title=job_code.replace("_", " ").title(),
                    base_monthly_pay_xgp=float(pay),
                    promotion_threshold=float(Decimal("0.12")),
                )
            )
        db.commit()
        db.close()

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)

    # ── Helper: create a player ───────────────────────────────────────────────

    def _make_player(
        self,
        *,
        cash_xgp: float = 800.0,
        debt_xgp: float = 0.0,
        stress: int = 20,
        health: int = 80,
        region: str = "suburban",
        has_active_housing: bool = False,
    ) -> tuple:
        """Create a user + player and return (db, player)."""
        db = self.SessionLocal()
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", hashed_password="x")
        db.add(user)
        db.flush()
        player = Player(
            id=uuid.uuid4(),
            user_id=user.id,
            cash=Decimal(str(cash_xgp)),
            debt_xgp=Decimal(str(debt_xgp)),
            stress=stress,
            health=health,
            region=region,
            has_active_housing=has_active_housing,
        )
        db.add(player)
        db.commit()
        return db, player

    def _seed_employment(self, db, player_id, job_code="retail_worker", pay=2600.0, employed=True):
        es = PlayerEmploymentState(
            player_id=player_id,
            day=1,
            current_job_code=job_code,
            employed_flag=employed,
            job_status="employed" if employed else "seeking",
            monthly_pay_xgp=float(pay),
            productivity_modifier=float(Decimal("1.0")),
        )
        db.add(es)
        db.commit()
        return es

    # ── Test 1: compute creates a log row ─────────────────────────────────────

    def test_compute_creates_one_basket_consumption_log_row(self):
        db, player = self._make_player()
        try:
            result = compute_player_daily_consumption(db, player.id, day=1)
            log_count = (
                db.query(BasketConsumptionLog)
                .filter(
                    BasketConsumptionLog.player_id == player.id,
                    BasketConsumptionLog.day == 1,
                )
                .count()
            )
            self.assertEqual(log_count, 1)
            # All four basket outputs must exist
            self.assertIn("essentials_spend_xgp", result)
            self.assertIn("protein_spend_xgp", result)
            self.assertIn("produce_spend_xgp", result)
            self.assertIn("convenience_spend_xgp", result)
            self.assertIn("total_spend_xgp", result)
            self.assertIn("budget_pressure_score", result)
            # Total must equal sum of parts
            expected_total = round(
                result["essentials_spend_xgp"]
                + result["protein_spend_xgp"]
                + result["produce_spend_xgp"]
                + result["convenience_spend_xgp"],
                2,
            )
            self.assertAlmostEqual(result["total_spend_xgp"], expected_total, places=2)
        finally:
            db.close()

    # ── Test 2: idempotency – no duplicate rows on rerun ─────────────────────

    def test_rerun_same_player_day_does_not_duplicate_consumption_log(self):
        db, player = self._make_player()
        try:
            r1 = compute_player_daily_consumption(db, player.id, day=1)
            r2 = compute_player_daily_consumption(db, player.id, day=1)
            log_count = (
                db.query(BasketConsumptionLog)
                .filter(
                    BasketConsumptionLog.player_id == player.id,
                    BasketConsumptionLog.day == 1,
                )
                .count()
            )
            self.assertEqual(log_count, 1, "Second call must not create a duplicate")
            self.assertAlmostEqual(r1["total_spend_xgp"], r2["total_spend_xgp"], places=2)
        finally:
            db.close()

    # ── Test 3: essentials more stable than convenience under budget pressure ─

    def test_essentials_more_stable_than_convenience_under_pressure(self):
        # Comfortable player
        db_ok, player_ok = self._make_player(cash_xgp=2000.0, debt_xgp=0.0)
        r_ok = compute_player_daily_consumption(db_ok, player_ok.id, day=1)
        db_ok.close()

        # Squeezed player: low cash, high debt
        db_sq, player_sq = self._make_player(cash_xgp=50.0, debt_xgp=600.0)
        r_sq = compute_player_daily_consumption(db_sq, player_sq.id, day=1)
        db_sq.close()

        ess_drop = r_ok["essentials_spend_xgp"] - r_sq["essentials_spend_xgp"]
        conv_drop = r_ok["convenience_spend_xgp"] - r_sq["convenience_spend_xgp"]

        # Convenience must drop MORE than essentials under pressure.
        self.assertGreaterEqual(
            conv_drop,
            ess_drop,
            "Convenience should be squeezed harder than essentials under budget pressure",
        )
        # Essentials must not collapse to zero.
        self.assertGreater(r_sq["essentials_spend_xgp"], 0.0)

    # ── Test 4: high stress pushes convenience up, bounded ───────────────────

    def test_high_stress_increases_convenience_spending_bounded(self):
        db_lo, player_lo = self._make_player(stress=5, cash_xgp=1500.0)
        r_lo = compute_player_daily_consumption(db_lo, player_lo.id, day=1)
        db_lo.close()

        db_hi, player_hi = self._make_player(stress=90, cash_xgp=1500.0)
        r_hi = compute_player_daily_consumption(db_hi, player_hi.id, day=1)
        db_hi.close()

        # High-stress player spends more on convenience.
        self.assertGreater(
            r_hi["convenience_spend_xgp"],
            r_lo["convenience_spend_xgp"],
            "High-stress player should spend more on convenience",
        )
        # Modifier must be ≤ 1.30× baseline (bounded sanity check).
        self.assertLessEqual(r_hi["stress_spend_modifier"], 1.31)

    # ── Test 5: housing + debt pressure reduces flexible basket spending ───────

    def test_high_housing_debt_pressure_reduces_flexible_spending(self):
        # Player with no housing pressure and low debt.
        db_ok, player_ok = self._make_player(cash_xgp=1500.0, debt_xgp=0.0)
        r_ok = compute_player_daily_consumption(db_ok, player_ok.id, day=1)
        db_ok.close()

        # Player with heavy housing (downtown) + high debt.
        db_sq, player_sq = self._make_player(
            cash_xgp=200.0,
            debt_xgp=3000.0,
            region="downtown",
            has_active_housing=True,
        )
        r_sq = compute_player_daily_consumption(db_sq, player_sq.id, day=1)
        db_sq.close()

        self.assertGreater(
            r_sq["budget_pressure_score"],
            r_ok["budget_pressure_score"],
            "Downtown + high-debt player should have higher budget pressure",
        )
        # Flexible baskets (protein + produce + convenience) should be lower.
        flexible_ok = r_ok["protein_spend_xgp"] + r_ok["produce_spend_xgp"] + r_ok["convenience_spend_xgp"]
        flexible_sq = r_sq["protein_spend_xgp"] + r_sq["produce_spend_xgp"] + r_sq["convenience_spend_xgp"]
        self.assertGreater(
            flexible_ok,
            flexible_sq,
            "Flexible basket spending should be lower under high pressure",
        )

    # ── Test 6: settlement summary includes refined basket spend fields ───────

    def test_settlement_summary_includes_refined_basket_spend_fields(self):
        db, player = self._make_player(cash_xgp=500.0)
        try:
            # Create minimal game state so settlement can read current_day
            gs = GameState(current_day=1)
            db.add(gs)
            db.commit()

            result = settle_player_day(db, player.id)

            required_keys = [
                "essentials_spend_xgp",
                "protein_spend_xgp",
                "produce_spend_xgp",
                "convenience_spend_xgp",
                "total_basket_spend_xgp",
                "budget_pressure_score",
                "stress_spend_modifier",
                "nutrition_pressure_score",
            ]
            for key in required_keys:
                self.assertIn(key, result, f"Settlement return dict missing: {key}")

            sj = result.get("summary_json", {})
            for key in required_keys:
                self.assertIn(key, sj, f"Settlement summary_json missing: {key}")
        finally:
            db.close()

    # ── Test 7: unemployment + low cash = high pressure + less flexible spend ─

    def test_unemployment_low_cash_increases_pressure_reduces_flexible(self):
        # Employed comfortable player
        db_emp, player_emp = self._make_player(cash_xgp=1200.0)
        self._seed_employment(db_emp, player_emp.id, employed=True)
        r_emp = compute_player_daily_consumption(db_emp, player_emp.id, day=1)
        db_emp.close()

        # Unemployed low-cash player
        db_unemp, player_unemp = self._make_player(cash_xgp=80.0, debt_xgp=200.0)
        self._seed_employment(db_unemp, player_unemp.id, employed=False, pay=0.0)
        r_unemp = compute_player_daily_consumption(db_unemp, player_unemp.id, day=1)
        db_unemp.close()

        self.assertGreater(
            r_unemp["budget_pressure_score"],
            r_emp["budget_pressure_score"],
            "Unemployed low-cash player should have higher budget pressure",
        )
        flexible_emp = r_emp["protein_spend_xgp"] + r_emp["produce_spend_xgp"] + r_emp["convenience_spend_xgp"]
        flexible_unemp = r_unemp["protein_spend_xgp"] + r_unemp["produce_spend_xgp"] + r_unemp["convenience_spend_xgp"]
        self.assertGreater(
            flexible_emp,
            flexible_unemp,
            "Employed player should have higher flexible basket spending than unemployed",
        )


if __name__ == "__main__":
    unittest.main()
