import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_debt_credit_service.db")

from app.db.database import Base
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.models.user import User
from app.services.debt_credit_service import (
    apply_daily_debt_and_credit,
    compute_daily_debt_obligation,
)


class DebtCreditServiceTests(unittest.TestCase):
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
                PlayerEmploymentState.__table__,
                BasketConsumptionLog.__table__,
                DebtCreditLog.__table__,
            ],
        )

        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_player(
        self,
        *,
        cash_xgp: float,
        debt_xgp: float,
        credit_score: int = 650,
        stress: int = 20,
        health: int = 90,
    ) -> Player:
        user = User(
            email=f"debt-test-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Debt Credit Test",
            cash=Decimal(str(cash_xgp)),
            debt_xgp=Decimal(str(debt_xgp)),
            credit_score=int(credit_score),
            stress=int(stress),
            health=int(health),
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_employment(self, player: Player, *, day: int = 1, employed: bool = True, pay_xgp: float = 3200.0) -> None:
        self.db.add(
            PlayerEmploymentState(
                player_id=player.id,
                day=day,
                current_job_code="retail_worker" if employed else None,
                skill_level=2,
                monthly_pay_xgp=Decimal(str(pay_xgp if employed else 0.0)),
                employed_flag=bool(employed),
                job_status="employed" if employed else "seeking",
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )
        self.db.flush()

    def _seed_budget_pressure(self, player: Player, *, day: int, score: Decimal) -> None:
        self.db.add(
            BasketConsumptionLog(
                player_id=player.id,
                day=day,
                essentials_spend_xgp=Decimal("8.00"),
                protein_spend_xgp=Decimal("4.00"),
                produce_spend_xgp=Decimal("3.00"),
                convenience_spend_xgp=Decimal("1.00"),
                total_spend_xgp=Decimal("16.00"),
                budget_pressure_score=score,
                stress_spend_modifier=Decimal("1.0000"),
                nutrition_pressure_score=Decimal("0.2000"),
            )
        )
        self.db.flush()

    def test_no_debt_player_produces_zero_debt_pressure(self) -> None:
        player = self._create_player(cash_xgp=200.0, debt_xgp=0.0, credit_score=640)
        self._seed_employment(player, employed=True)
        self.db.commit()

        obligation = compute_daily_debt_obligation(self.db, str(player.id), day=1)
        result = apply_daily_debt_and_credit(self.db, str(player.id), day=1)

        self.assertEqual(obligation["payment_due_xgp"], 0.0)
        self.assertEqual(result["payment_due_xgp"], 0.0)
        self.assertEqual(result["payment_made_xgp"], 0.0)
        self.assertEqual(result["interest_added_xgp"], 0.0)
        self.assertEqual(result["payment_status"], "no_debt")
        self.assertFalse(result["delinquency_flag"])
        self.assertEqual(result["credit_score_change"], 0)

    def test_debt_player_creates_one_log_row(self) -> None:
        player = self._create_player(cash_xgp=350.0, debt_xgp=900.0)
        self._seed_employment(player, employed=True, pay_xgp=3600.0)
        self.db.commit()

        result = apply_daily_debt_and_credit(self.db, str(player.id), day=1)

        count = (
            self.db.query(DebtCreditLog)
            .filter(DebtCreditLog.player_id == player.id, DebtCreditLog.day == 1)
            .count()
        )

        self.assertEqual(count, 1)
        self.assertGreater(result["payment_due_xgp"], 0.0)
        self.assertIn(result["payment_status"], {"paid_full", "paid_partial", "missed"})

    def test_rerun_same_player_day_does_not_duplicate_or_double_charge(self) -> None:
        player = self._create_player(cash_xgp=120.0, debt_xgp=600.0)
        self._seed_employment(player, employed=True, pay_xgp=3100.0)
        self.db.commit()

        first = apply_daily_debt_and_credit(self.db, str(player.id), day=1)
        self.db.refresh(player)
        cash_after_first = float(player.cash_xgp)
        debt_after_first = float(player.debt_xgp)

        second = apply_daily_debt_and_credit(self.db, str(player.id), day=1)
        self.db.refresh(player)
        cash_after_second = float(player.cash_xgp)
        debt_after_second = float(player.debt_xgp)

        count = (
            self.db.query(DebtCreditLog)
            .filter(DebtCreditLog.player_id == player.id, DebtCreditLog.day == 1)
            .count()
        )

        self.assertEqual(count, 1)
        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])
        self.assertEqual(cash_after_first, cash_after_second)
        self.assertEqual(debt_after_first, debt_after_second)

    def test_missed_payment_reduces_credit_score(self) -> None:
        player = self._create_player(cash_xgp=0.0, debt_xgp=850.0, credit_score=640)
        self._seed_employment(player, employed=False)
        self._seed_budget_pressure(player, day=1, score=Decimal("0.9700"))
        self.db.commit()

        result = apply_daily_debt_and_credit(self.db, str(player.id), day=1)

        self.assertEqual(result["payment_status"], "missed")
        self.assertLess(result["credit_score_change"], 0)
        self.assertLess(result["ending_credit_score"], result["opening_credit_score"])

    def test_full_payment_is_less_harmful_or_mildly_positive(self) -> None:
        player = self._create_player(cash_xgp=1200.0, debt_xgp=500.0, credit_score=650)
        self._seed_employment(player, employed=True, pay_xgp=4500.0)
        self._seed_budget_pressure(player, day=1, score=Decimal("0.2000"))
        self.db.commit()

        result = apply_daily_debt_and_credit(self.db, str(player.id), day=1)

        self.assertEqual(result["payment_status"], "paid_full")
        self.assertGreaterEqual(result["credit_score_change"], 0)

    def test_credit_score_is_clamped_between_300_and_850(self) -> None:
        low_player = self._create_player(cash_xgp=0.0, debt_xgp=450.0, credit_score=300)
        self._seed_employment(low_player, employed=False)
        self.db.commit()

        low_result = apply_daily_debt_and_credit(self.db, str(low_player.id), day=1)
        self.assertGreaterEqual(low_result["ending_credit_score"], 300)

        high_player = self._create_player(cash_xgp=2000.0, debt_xgp=450.0, credit_score=850)
        self._seed_employment(high_player, employed=True, pay_xgp=5000.0)
        self.db.commit()

        high_result = apply_daily_debt_and_credit(self.db, str(high_player.id), day=1)
        self.assertLessEqual(high_result["ending_credit_score"], 850)

    def test_low_cash_unemployed_increases_missed_or_partial_risk(self) -> None:
        stable = self._create_player(cash_xgp=900.0, debt_xgp=500.0, credit_score=650)
        self._seed_employment(stable, employed=True, pay_xgp=4200.0)
        self._seed_budget_pressure(stable, day=1, score=Decimal("0.2500"))

        distressed = self._create_player(cash_xgp=2.0, debt_xgp=500.0, credit_score=650)
        self._seed_employment(distressed, employed=False)
        self._seed_budget_pressure(distressed, day=1, score=Decimal("0.9600"))
        self.db.commit()

        stable_result = apply_daily_debt_and_credit(self.db, str(stable.id), day=1)
        distressed_result = apply_daily_debt_and_credit(self.db, str(distressed.id), day=1)

        self.assertEqual(stable_result["payment_status"], "paid_full")
        self.assertIn(distressed_result["payment_status"], {"paid_partial", "missed"})


if __name__ == "__main__":
    unittest.main()
