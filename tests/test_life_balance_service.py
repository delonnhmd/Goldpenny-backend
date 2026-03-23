import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_life_balance_service.db")

from app.db.database import Base
from app.engine.life_balance_service import (
    apply_life_consequences_for_player,
    compute_burnout_and_medical_risk,
    compute_daily_health_update,
    compute_daily_stress_update,
    compute_daily_time_budget,
    compute_productivity_modifier,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.user import User


class LifeBalanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"life-test-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            cash=Decimal("950.00"),
            debt_xgp=Decimal("1800.00"),
            stress=58,
            health=82,
            hours_available=16,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="fruit_shop",
            business_name="Fresh Cart",
            region="downtown",
            level_key="starter",
            business_level=1,
            is_active=True,
        )
        self.db.add(business)
        self.db.flush()

        self.db.add(
            BusinessDailyLog(
                business_id=business.id,
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                business_type="fruit_shop",
                region_key="downtown",
                gross_revenue_xgp=Decimal("26.0000"),
                input_cost_xgp=Decimal("28.0000"),
                fuel_cost_xgp=Decimal("0.0000"),
                maintenance_cost_xgp=Decimal("0.0000"),
                spoilage_cost_xgp=Decimal("3.0000"),
                overhead_cost_xgp=Decimal("10.0000"),
                net_profit_xgp=Decimal("-15.0000"),
                units_sold=12,
                inventory_start_units=Decimal("40.0000"),
                inventory_end_units=Decimal("25.0000"),
                demand_signal=Decimal("18.0000"),
                demand_score=Decimal("18.0000"),
                utilization_pct=Decimal("30.0000"),
                reputation_before=50,
                reputation_after=49,
            )
        )
        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                hours_available_start=16,
                hours_available_end=16,
                worked_main_job=True,
                worked_hours=11,
                side_income_hours=Decimal("5.0000"),
                recovery_hours=Decimal("0.5000"),
                did_settlement=False,
                stress_start=58,
                stress_end=58,
                health_start=82,
                health_end=82,
                cash_start=Decimal("950.0000"),
                cash_end=Decimal("950.0000"),
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_time_budget_tracks_overtime_and_sleep_floor(self) -> None:
        budget = compute_daily_time_budget(
            as_of_date=date(2026, 1, 1),
            region_key="suburban",
            job_hours=Decimal("12"),
            business_hours=Decimal("7"),
            side_income_hours=Decimal("5"),
            recovery_hours=Decimal("1"),
        )
        self.assertGreater(float(budget["overtime_hours"]), 0.0)
        self.assertGreaterEqual(float(budget["sleep_hours"]), 4.0)
        self.assertLessEqual(float(budget["total_hours_used"]), 24.0)

    def test_stress_drivers_increase_with_overtime_and_low_sleep(self) -> None:
        stressed = compute_daily_stress_update(
            stress_before=Decimal("52"),
            overtime_hours=Decimal("4"),
            sleep_hours=Decimal("4.5"),
            recovery_hours=Decimal("0.5"),
            debt_pressure_score=Decimal("0.7"),
            business_net_profit_xgp=Decimal("-40"),
            job_pressure=Decimal("-0.20"),
            layoff_risk_pct=Decimal("19"),
            region_key="downtown",
        )
        rested = compute_daily_stress_update(
            stress_before=Decimal("52"),
            overtime_hours=Decimal("0"),
            sleep_hours=Decimal("8"),
            recovery_hours=Decimal("2.0"),
            debt_pressure_score=Decimal("0.1"),
            business_net_profit_xgp=Decimal("10"),
            job_pressure=Decimal("0.10"),
            layoff_risk_pct=Decimal("4"),
            region_key="suburban",
        )
        self.assertGreater(stressed["stress_delta"], rested["stress_delta"])
        self.assertGreaterEqual(stressed["stress_after"], 0)
        self.assertLessEqual(stressed["stress_after"], 100)

    def test_health_moves_slower_than_stress(self) -> None:
        health = compute_daily_health_update(
            health_before=Decimal("80"),
            stress_after=Decimal("86"),
            sleep_hours=Decimal("5"),
            recovery_hours=Decimal("0.5"),
            overtime_hours=Decimal("4"),
            medical_event_triggered=False,
            burnout_event_triggered=True,
        )
        self.assertGreaterEqual(health["health_delta"], -6)
        self.assertLessEqual(health["health_delta"], 3)
        self.assertGreaterEqual(health["health_after"], 0)
        self.assertLessEqual(health["health_after"], 100)

    def test_productivity_is_bounded_and_sensitive(self) -> None:
        weak = compute_productivity_modifier(
            stress=Decimal("90"),
            health=Decimal("52"),
            sleep_hours=Decimal("4.5"),
        )
        strong = compute_productivity_modifier(
            stress=Decimal("30"),
            health=Decimal("92"),
            sleep_hours=Decimal("7.5"),
        )
        self.assertLess(weak, strong)
        self.assertGreaterEqual(float(weak), 0.70)
        self.assertLessEqual(float(strong), 1.05)

    def test_burnout_and_medical_risk_are_bounded(self) -> None:
        risks = compute_burnout_and_medical_risk(
            stress=Decimal("92"),
            health=Decimal("43"),
            sleep_hours=Decimal("4.2"),
            overtime_hours=Decimal("5.5"),
            previous_burnout_risk=Decimal("0.20"),
            previous_medical_event_risk=Decimal("0.08"),
        )
        self.assertGreaterEqual(float(risks["burnout_risk"]), 0.0)
        self.assertLessEqual(float(risks["burnout_risk"]), 0.40)
        self.assertGreaterEqual(float(risks["medical_event_risk"]), 0.0)
        self.assertLessEqual(float(risks["medical_event_risk"]), 0.20)

    def test_apply_life_consequences_is_deterministic_for_same_day(self) -> None:
        first = apply_life_consequences_for_player(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        second = apply_life_consequences_for_player(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )

        self.assertEqual(first["medical_cost_xgp"], second["medical_cost_xgp"])
        self.assertEqual(first["missed_work_penalty_xgp"], second["missed_work_penalty_xgp"])
        self.assertEqual(first["stress"], second["stress"])
        self.assertEqual(first["health"], second["health"])
        self.assertTrue(bool(second["already_processed"]))


if __name__ == "__main__":
    unittest.main()
