import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_financial_distress_service.db")

from app.db.database import Base
from app.engine.financial_distress_service import (
    apply_daily_financial_distress,
    compute_credit_score_update,
    compute_daily_debt_obligations,
    compute_distress_state,
    get_player_credit_snapshot,
    queue_player_recovery_action,
)
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.user import User


class FinancialDistressServiceTests(unittest.TestCase):
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
                PlayerDailyState.__table__,
                PlayerEmploymentState.__table__,
                BasketConsumptionLog.__table__,
                DebtCreditLog.__table__,
                FinancialDistressLog.__table__,
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
        stress: int = 32,
        health: int = 90,
    ) -> Player:
        user = User(email=f"fd-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Finance Distress Test",
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

    def _seed_employment(self, player: Player, *, day: int = 1, monthly_pay_xgp: float = 3200.0) -> None:
        self.db.add(
            PlayerEmploymentState(
                player_id=player.id,
                day=day,
                current_job_code="retail_worker",
                skill_level=2,
                monthly_pay_xgp=Decimal(str(monthly_pay_xgp)),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )
        self.db.flush()

    def test_compute_daily_debt_obligations_is_bounded_and_payment_plan_reduces_due(self) -> None:
        baseline = compute_daily_debt_obligations(
            total_debt_xgp=Decimal("5000"),
            credit_score=620,
            monthly_income_xgp=Decimal("3200"),
            on_payment_plan=False,
        )
        on_plan = compute_daily_debt_obligations(
            total_debt_xgp=Decimal("5000"),
            credit_score=620,
            monthly_income_xgp=Decimal("3200"),
            debt_payment_due_xgp=Decimal(str(baseline["required_daily_debt_payment_xgp"])),
            on_payment_plan=True,
        )

        self.assertGreater(float(baseline["required_daily_debt_payment_xgp"]), 0.0)
        self.assertLessEqual(float(baseline["required_daily_debt_payment_xgp"]), 120.0)
        self.assertGreaterEqual(float(baseline["debt_utilization_ratio"]), 0.0)
        self.assertLessEqual(float(baseline["debt_utilization_ratio"]), 3.0)
        self.assertLess(
            float(on_plan["required_daily_debt_payment_xgp"]),
            float(baseline["required_daily_debt_payment_xgp"]),
        )

    def test_compute_credit_score_update_penalizes_miss_and_utilization(self) -> None:
        missed = compute_credit_score_update(
            credit_score_before=640,
            debt_utilization_ratio=Decimal("1.40"),
            debt_payment_missed=True,
            underpaid_flag=False,
            distress_score_before=Decimal("68"),
            missed_payment_streak_before=2,
            on_payment_plan=False,
        )
        on_time = compute_credit_score_update(
            credit_score_before=640,
            debt_utilization_ratio=Decimal("0.25"),
            debt_payment_missed=False,
            underpaid_flag=False,
            distress_score_before=Decimal("20"),
            missed_payment_streak_before=0,
            on_payment_plan=False,
        )

        self.assertLess(missed, 0)
        self.assertGreater(on_time, 0)

    def test_apply_daily_financial_distress_is_idempotent_for_same_day(self) -> None:
        player = self._create_player(cash_xgp=1800.0, debt_xgp=900.0, credit_score=650)
        self._seed_employment(player, day=1, monthly_pay_xgp=4200.0)
        self.db.commit()

        first = apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            as_of_date=date(2026, 1, 1),
        )
        second = apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            as_of_date=date(2026, 1, 1),
        )

        count = (
            self.db.query(FinancialDistressLog)
            .filter(FinancialDistressLog.player_id == player.id, FinancialDistressLog.day == 1)
            .count()
        )

        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])
        self.assertEqual(count, 1)
        self.assertFalse(bool(first["debt_payment_missed"]))
        self.assertEqual(first["credit_score_after"], second["credit_score_after"])
        self.assertEqual(first["distress_score_after"], second["distress_score_after"])

    def test_missed_payment_hurts_credit_and_increases_distress(self) -> None:
        player = self._create_player(cash_xgp=0.0, debt_xgp=2600.0, credit_score=640, stress=74)
        self.db.commit()

        result = apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
            monthly_income_xgp=Decimal("0.00"),
        )

        self.db.refresh(player)

        self.assertTrue(bool(result["debt_payment_missed"]))
        self.assertGreater(float(result["late_fee_xgp"]), 0.0)
        self.assertLess(int(result["credit_score_after"]), int(result["credit_score_before"]))
        self.assertGreater(float(result["distress_score_after"]), float(result["distress_score_before"]))
        self.assertEqual(player.missed_payment_streak, 1)

    def test_recovery_actions_have_tradeoffs_and_help_next_day_due(self) -> None:
        player = self._create_player(cash_xgp=80.0, debt_xgp=1800.0, credit_score=615, stress=70)
        self._seed_employment(player, day=1, monthly_pay_xgp=2600.0)
        self._seed_employment(player, day=2, monthly_pay_xgp=2600.0)
        self._seed_employment(player, day=3, monthly_pay_xgp=2600.0)
        self.db.commit()

        day1 = apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
        )
        queue_player_recovery_action(self.db, str(player.id), "payment_plan_enroll")
        queue_player_recovery_action(self.db, str(player.id), "business_spending_cut")

        day2 = apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            day_number=2,
            available_cash_xgp=Decimal("120.00"),
        )
        day3 = apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            day_number=3,
            available_cash_xgp=Decimal("120.00"),
        )

        self.db.refresh(player)

        self.assertIn("payment_plan_enroll", day2["recovery_actions_applied"])
        self.assertTrue(bool(player.on_payment_plan))
        self.assertLessEqual(float(day3["debt_payment_due_xgp"]), float(day2["debt_payment_due_xgp"]))
        self.assertLessEqual(float(day3["business_risk_penalty"]), 0.35)
        self.assertGreaterEqual(int(day3["credit_score_after"]), 300)
        self.assertLessEqual(int(day3["credit_score_after"]), 850)
        self.assertGreater(float(day1["distress_score_after"]), 0.0)

    def test_distress_state_thresholds_are_deterministic(self) -> None:
        self.assertEqual(compute_distress_state(Decimal("0")), "stable")
        self.assertEqual(compute_distress_state(Decimal("24.9")), "stable")
        self.assertEqual(compute_distress_state(Decimal("25")), "stretched")
        self.assertEqual(compute_distress_state(Decimal("50")), "distressed")
        self.assertEqual(compute_distress_state(Decimal("75")), "critical")

    def test_credit_snapshot_exposes_penalty_signals(self) -> None:
        player = self._create_player(cash_xgp=10.0, debt_xgp=1400.0, credit_score=630)
        self._seed_employment(player, day=1, monthly_pay_xgp=2800.0)
        self.db.commit()

        apply_daily_financial_distress(
            db=self.db,
            player_id=str(player.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
        )

        snapshot = get_player_credit_snapshot(self.db, str(player.id))

        self.assertIn("borrowing_cost_modifier", snapshot)
        self.assertIn("opportunity_access_penalty", snapshot)
        self.assertIn("business_risk_penalty", snapshot)
        self.assertIn("career_progress_penalty", snapshot)
        self.assertIn(snapshot["distress_state"], {"stable", "stretched", "distressed", "critical"})


if __name__ == "__main__":
    unittest.main()
