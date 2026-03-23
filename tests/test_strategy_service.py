import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_strategy_service.db")

from app.db.database import Base
from app.engine.player_strategy_service import classify_player_strategy
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.user import User


class PlayerStrategyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                DailySettlementLog.__table__,
                PlayerDailyState.__table__,
                FinancialDistressLog.__table__,
                CareerProgressLog.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.entrepreneur = self._seed_player("Entrepreneur")
        self.recovery = self._seed_player("Recovery")
        self._seed_entrepreneur_window(self.entrepreneur.id)
        self._seed_recovery_window(self.recovery.id)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player(self, name: str) -> Player:
        user = User(email=f"{name.lower()}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=name,
            cash=Decimal("2500.00"),
            debt_xgp=Decimal("700.00"),
            stress=30,
            health=92,
            hours_available=16,
            region="downtown",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _add_settlement(
        self,
        *,
        player_id,
        day: int,
        income_xgp: Decimal,
        side_income_net_xgp: Decimal,
        business_net_profit_xgp: Decimal,
        stress_after: int,
        health_after: int,
    ) -> None:
        self.db.add(
            DailySettlementLog(
                player_id=player_id,
                day_number=day,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=max(0, stress_after - 1),
                stress_after=stress_after,
                health_before=min(100, health_after + 1),
                health_after=health_after,
                cash_before=Decimal("1000.00"),
                cash_after=Decimal("1020.00"),
                income_xgp=income_xgp,
                expenses_xgp=Decimal("80.00"),
                stock_pnl_xgp=Decimal("0.00"),
                debt_paid_xgp=Decimal("5.00"),
                health_change=-1,
                stress_change=1,
                side_income_net_xgp=side_income_net_xgp,
                business_net_profit_xgp=business_net_profit_xgp,
            )
        )

    def _add_daily_state(self, *, player_id, day: int, job_hours: Decimal, side_hours: Decimal, business_hours: Decimal) -> None:
        self.db.add(
            PlayerDailyState(
                player_id=player_id,
                day_number=day,
                hours_available_start=24,
                hours_available_end=8,
                worked_main_job=True,
                worked_hours=int(job_hours),
                gross_income_xgp=Decimal("120.00"),
                did_settlement=True,
                stress_start=30,
                stress_end=32,
                health_start=93,
                health_end=92,
                cash_start=Decimal("1000.00"),
                cash_end=Decimal("1020.00"),
                job_hours=job_hours,
                side_income_hours=side_hours,
                business_hours=business_hours,
                overtime_hours=Decimal("1.0"),
            )
        )

    def _seed_entrepreneur_window(self, player_id) -> None:
        for day in range(1, 8):
            self._add_settlement(
                player_id=player_id,
                day=day,
                income_xgp=Decimal("250.00"),
                side_income_net_xgp=Decimal("25.00"),
                business_net_profit_xgp=Decimal("150.00"),
                stress_after=36,
                health_after=90,
            )
            self._add_daily_state(
                player_id=player_id,
                day=day,
                job_hours=Decimal("4.0"),
                side_hours=Decimal("2.0"),
                business_hours=Decimal("6.0"),
            )
            self.db.add(
                FinancialDistressLog(
                    player_id=player_id,
                    day=day,
                    debt_payment_due_xgp=Decimal("8.00"),
                    debt_payment_paid_xgp=Decimal("8.00"),
                    debt_payment_missed=False,
                    distress_score_before=Decimal("22.0"),
                    distress_score_after=Decimal("24.0"),
                )
            )
            self.db.add(
                CareerProgressLog(
                    player_id=player_id,
                    day_number=day,
                    training_hours=Decimal("0.50"),
                )
            )

    def _seed_recovery_window(self, player_id) -> None:
        for day in range(1, 8):
            self._add_settlement(
                player_id=player_id,
                day=day,
                income_xgp=Decimal("110.00"),
                side_income_net_xgp=Decimal("20.00"),
                business_net_profit_xgp=Decimal("-10.00"),
                stress_after=82,
                health_after=68,
            )
            self._add_daily_state(
                player_id=player_id,
                day=day,
                job_hours=Decimal("6.0"),
                side_hours=Decimal("3.0"),
                business_hours=Decimal("1.0"),
            )
            self.db.add(
                FinancialDistressLog(
                    player_id=player_id,
                    day=day,
                    debt_payment_due_xgp=Decimal("15.00"),
                    debt_payment_paid_xgp=Decimal("0.00"),
                    debt_payment_missed=True,
                    distress_score_before=Decimal("78.0"),
                    distress_score_after=Decimal("82.0"),
                )
            )
            self.db.add(
                CareerProgressLog(
                    player_id=player_id,
                    day_number=day,
                    training_hours=Decimal("0.00"),
                )
            )

    def test_classification_is_deterministic_for_same_state(self) -> None:
        first = classify_player_strategy(self.db, str(self.entrepreneur.id), lookback_days=7)
        second = classify_player_strategy(self.db, str(self.entrepreneur.id), lookback_days=7)
        self.assertEqual(first["strategy_classification"], second["strategy_classification"])
        self.assertEqual(first["classification_drivers"], second["classification_drivers"])

    def test_classifies_entrepreneur_path(self) -> None:
        payload = classify_player_strategy(self.db, str(self.entrepreneur.id), lookback_days=7)
        self.assertEqual(payload["strategy_classification"], "entrepreneur")
        self.assertGreater(payload["classification_drivers"]["business_income_share"], 0.45)

    def test_classifies_recovery_mode_under_high_distress(self) -> None:
        payload = classify_player_strategy(self.db, str(self.recovery.id), lookback_days=7)
        self.assertEqual(payload["strategy_classification"], "recovery_mode")
        self.assertGreaterEqual(payload["classification_drivers"]["avg_distress"], 75.0)
        self.assertGreaterEqual(payload["classification_drivers"]["missed_payments"], 3)


if __name__ == "__main__":
    unittest.main()

