import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_economy_telemetry_service.db")

from app.db.database import Base
from app.engine.economy_telemetry_service import (
    compute_balance_flags,
    compute_daily_economy_health_metrics,
    compute_player_viability_metrics,
    get_recent_economy_telemetry,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.models.user import User


class EconomyTelemetryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                PlayerEmploymentState.__table__,
                BusinessDailyLog.__table__,
                DailySettlementLog.__table__,
                FinancialDistressLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        self.player_a = self._create_player(cash=900.0, debt=1200.0, stress=57, health=86, distress=44)
        self.player_b = self._create_player(cash=1300.0, debt=400.0, stress=35, health=92, distress=18)

        for day in (1, 2, 3):
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.20"),
                    interest_rate=Decimal("4.10"),
                    unemployment_rate=Decimal("5.40"),
                    oil_index=Decimal("105.00") + Decimal(str(day)),
                    consumer_confidence=Decimal("50.00") - Decimal(str(day)),
                    supply_chain_stress=Decimal("0.60"),
                    event_headline="Telemetry baseline",
                    event_summary="Step 21 telemetry test seed.",
                )
            )
            self.db.add_all(
                [
                    BasketDailyPrice(
                        day=day,
                        basket_type=BasketType.essentials,
                        price_index=Decimal("10.20") + Decimal(str(day)) * Decimal("0.10"),
                        daily_change_pct=Decimal("0.40") + Decimal(str(day)) * Decimal("0.05"),
                        supply_pressure=Decimal("1.02"),
                        demand_pressure=Decimal("1.01"),
                    ),
                    BasketDailyPrice(
                        day=day,
                        basket_type=BasketType.produce,
                        price_index=Decimal("8.90") + Decimal(str(day)) * Decimal("0.12"),
                        daily_change_pct=Decimal("0.55") + Decimal(str(day)) * Decimal("0.06"),
                        supply_pressure=Decimal("1.03"),
                        demand_pressure=Decimal("1.02"),
                    ),
                ]
            )

        self.db.add_all(
            [
                PlayerEmploymentState(
                    player_id=self.player_a.id,
                    day=3,
                    current_job_code="retail_worker",
                    skill_level=2,
                    monthly_pay_xgp=Decimal("3200.00"),
                    employed_flag=True,
                    opportunity_score=Decimal("1.08"),
                    promotion_chance_pct=Decimal("8.00"),
                    productivity_modifier=Decimal("1.0000"),
                ),
                PlayerEmploymentState(
                    player_id=self.player_b.id,
                    day=3,
                    current_job_code="driver",
                    skill_level=1,
                    monthly_pay_xgp=Decimal("2700.00"),
                    employed_flag=True,
                    opportunity_score=Decimal("0.86"),
                    promotion_chance_pct=Decimal("3.00"),
                    productivity_modifier=Decimal("1.0000"),
                ),
            ]
        )

        self.db.add_all(
            [
                BusinessDailyLog(
                    business_id=uuid.uuid4(),
                    player_id=self.player_a.id,
                    day=3,
                    business_type="food_truck",
                    gross_revenue_xgp=Decimal("120.0000"),
                    input_cost_xgp=Decimal("62.0000"),
                    fuel_cost_xgp=Decimal("9.0000"),
                    spoilage_cost_xgp=Decimal("2.5000"),
                    overhead_cost_xgp=Decimal("18.0000"),
                    net_profit_xgp=Decimal("28.5000"),
                    demand_score=Decimal("1.0600"),
                    utilization_pct=Decimal("0.7200"),
                ),
                BusinessDailyLog(
                    business_id=uuid.uuid4(),
                    player_id=self.player_b.id,
                    day=3,
                    business_type="fruit_shop",
                    gross_revenue_xgp=Decimal("85.0000"),
                    input_cost_xgp=Decimal("48.0000"),
                    fuel_cost_xgp=Decimal("0.0000"),
                    spoilage_cost_xgp=Decimal("4.0000"),
                    overhead_cost_xgp=Decimal("12.0000"),
                    net_profit_xgp=Decimal("21.0000"),
                    demand_score=Decimal("0.9800"),
                    utilization_pct=Decimal("0.6800"),
                ),
            ]
        )

        self.db.add_all(
            [
                DailySettlementLog(
                    player_id=self.player_a.id,
                    day_number=3,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=56,
                    stress_after=58,
                    health_before=87,
                    health_after=86,
                    cash_before=Decimal("950.0000"),
                    cash_after=Decimal("900.0000"),
                    income_xgp=Decimal("120.0000"),
                    expenses_xgp=Decimal("170.0000"),
                    side_income_net_xgp=Decimal("20.0000"),
                    business_net_profit_xgp=Decimal("28.5000"),
                    stock_pnl_xgp=Decimal("0.0000"),
                    debt_paid_xgp=Decimal("10.0000"),
                    health_change=-1,
                    stress_change=2,
                ),
                DailySettlementLog(
                    player_id=self.player_b.id,
                    day_number=3,
                    hours_before_reset=9,
                    hours_after_reset=24,
                    stress_before=34,
                    stress_after=35,
                    health_before=93,
                    health_after=92,
                    cash_before=Decimal("1360.0000"),
                    cash_after=Decimal("1300.0000"),
                    income_xgp=Decimal("95.0000"),
                    expenses_xgp=Decimal("155.0000"),
                    side_income_net_xgp=Decimal("12.0000"),
                    business_net_profit_xgp=Decimal("21.0000"),
                    stock_pnl_xgp=Decimal("0.0000"),
                    debt_paid_xgp=Decimal("8.0000"),
                    health_change=-1,
                    stress_change=1,
                ),
            ]
        )

        self.db.add_all(
            [
                FinancialDistressLog(
                    player_id=self.player_a.id,
                    day=3,
                    debt_payment_due_xgp=Decimal("12.0000"),
                    debt_payment_paid_xgp=Decimal("0.0000"),
                    debt_payment_missed=True,
                    late_fee_xgp=Decimal("5.0000"),
                    accrued_interest_xgp=Decimal("1.0000"),
                    credit_score_before=640,
                    credit_score_after=632,
                    credit_score_delta=-8,
                    distress_state_before="stretched",
                    distress_state_after="distressed",
                    distress_score_before=Decimal("48.0000"),
                    distress_score_after=Decimal("56.0000"),
                ),
                FinancialDistressLog(
                    player_id=self.player_b.id,
                    day=3,
                    debt_payment_due_xgp=Decimal("8.0000"),
                    debt_payment_paid_xgp=Decimal("8.0000"),
                    debt_payment_missed=False,
                    late_fee_xgp=Decimal("0.0000"),
                    accrued_interest_xgp=Decimal("0.3000"),
                    credit_score_before=690,
                    credit_score_after=691,
                    credit_score_delta=1,
                    distress_state_before="stable",
                    distress_state_after="stable",
                    distress_score_before=Decimal("20.0000"),
                    distress_score_after=Decimal("18.0000"),
                ),
            ]
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_player(self, *, cash: float, debt: float, stress: int, health: int, distress: int) -> Player:
        user = User(email=f"telemetry-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            cash=Decimal(str(cash)),
            debt_xgp=Decimal(str(debt)),
            stress=stress,
            health=health,
            distress_score=Decimal(str(distress)),
            required_daily_debt_payment_xgp=Decimal("10.0000"),
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def test_daily_telemetry_is_deterministic_for_same_day(self) -> None:
        first = compute_daily_economy_health_metrics(self.db, as_of_date=date(2026, 1, 3))
        second = compute_daily_economy_health_metrics(self.db, as_of_date=date(2026, 1, 3))

        self.assertEqual(first["basket_volatility_index"], second["basket_volatility_index"])
        self.assertEqual(first["economy_harshness_score"], second["economy_harshness_score"])
        self.assertEqual(first["economy_softness_score"], second["economy_softness_score"])
        self.assertEqual(first["dominant_flags"], second["dominant_flags"])

    def test_harshness_and_softness_scores_are_bounded(self) -> None:
        telemetry = compute_daily_economy_health_metrics(self.db, as_of_date=date(2026, 1, 3))
        self.assertGreaterEqual(telemetry["economy_harshness_score"], 0.0)
        self.assertLessEqual(telemetry["economy_harshness_score"], 100.0)
        self.assertGreaterEqual(telemetry["economy_softness_score"], 0.0)
        self.assertLessEqual(telemetry["economy_softness_score"], 100.0)

    def test_player_viability_metrics_are_bounded(self) -> None:
        snapshot = compute_player_viability_metrics(self.db, str(self.player_a.id), as_of_date=date(2026, 1, 3))
        self.assertGreaterEqual(snapshot["days_cash_cushion"], 0.0)
        self.assertGreaterEqual(snapshot["debt_pressure_ratio"], 0.0)
        self.assertGreaterEqual(snapshot["net_income_stability_score"], 0.0)
        self.assertLessEqual(snapshot["net_income_stability_score"], 100.0)
        self.assertGreaterEqual(snapshot["burnout_danger_score"], 0.0)
        self.assertLessEqual(snapshot["burnout_danger_score"], 100.0)
        self.assertGreaterEqual(snapshot["upward_mobility_score"], 0.0)
        self.assertLessEqual(snapshot["upward_mobility_score"], 100.0)

    def test_balance_flags_have_stable_shape(self) -> None:
        telemetry = compute_daily_economy_health_metrics(self.db, as_of_date=date(2026, 1, 3))
        flags = compute_balance_flags(telemetry)
        self.assertIn("flags", flags)
        self.assertIn("active_flags", flags)
        self.assertIn("debug_meta", flags)

    def test_recent_telemetry_returns_ordered_entries(self) -> None:
        payload = get_recent_economy_telemetry(self.db, days=3, as_of_date=date(2026, 1, 3))
        self.assertEqual(len(payload["entries"]), 3)
        self.assertEqual(payload["entries"][0]["as_of_date"], "2026-01-01")
        self.assertEqual(payload["entries"][2]["as_of_date"], "2026-01-03")


if __name__ == "__main__":
    unittest.main()
