import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_balance_report_service.db")

from app.db.database import Base
from app.engine.balance_report_service import (
    build_balance_report,
    build_player_strategy_report,
    build_system_dominance_report,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.side_income_action import SideIncomeAction
from app.models.user import User


class BalanceReportServiceTests(unittest.TestCase):
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
                PlayerDailyState.__table__,
                PlayerHousingState.__table__,
                SideIncomeAction.__table__,
                HousingDailyLog.__table__,
                BusinessDailyLog.__table__,
                DailySettlementLog.__table__,
                FinancialDistressLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        self.players = [self._create_player(stress=48 + i * 8, health=90 - i * 3, distress=28 + i * 12) for i in range(3)]

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.3"),
                interest_rate=Decimal("4.2"),
                unemployment_rate=Decimal("5.7"),
                oil_index=Decimal("108.0"),
                consumer_confidence=Decimal("49.0"),
                supply_chain_stress=Decimal("0.7"),
                event_headline="Balance report baseline",
                event_summary="Step 21 report seed.",
            )
        )

        self.db.add_all(
            [
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("10.4"),
                    daily_change_pct=Decimal("0.8"),
                    supply_pressure=Decimal("1.03"),
                    demand_pressure=Decimal("1.04"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.3"),
                    daily_change_pct=Decimal("0.7"),
                    supply_pressure=Decimal("1.02"),
                    demand_pressure=Decimal("1.01"),
                ),
            ]
        )

        for idx, player in enumerate(self.players):
            self.db.add(
                PlayerEmploymentState(
                    player_id=player.id,
                    day=1,
                    current_job_code="banker" if idx < 2 else "driver",
                    skill_level=2,
                    monthly_pay_xgp=Decimal("3400.00"),
                    employed_flag=True,
                    opportunity_score=Decimal("1.02") if idx < 2 else Decimal("0.88"),
                    promotion_chance_pct=Decimal("6.0"),
                    productivity_modifier=Decimal("1.0000"),
                )
            )

            self.db.add(
                BusinessDailyLog(
                    business_id=uuid.uuid4(),
                    player_id=player.id,
                    day=1,
                    business_type="food_truck" if idx < 2 else "fruit_shop",
                    gross_revenue_xgp=Decimal("130.0000") if idx < 2 else Decimal("80.0000"),
                    input_cost_xgp=Decimal("52.0000") if idx < 2 else Decimal("44.0000"),
                    fuel_cost_xgp=Decimal("8.0000") if idx < 2 else Decimal("0.0000"),
                    spoilage_cost_xgp=Decimal("2.0000"),
                    overhead_cost_xgp=Decimal("14.0000"),
                    net_profit_xgp=Decimal("54.0000") if idx < 2 else Decimal("12.0000"),
                    units_sold=24,
                    demand_score=Decimal("1.1000") if idx < 2 else Decimal("0.9200"),
                    utilization_pct=Decimal("0.8200") if idx < 2 else Decimal("0.6100"),
                )
            )

            self.db.add(
                DailySettlementLog(
                    player_id=player.id,
                    day_number=1,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=player.stress,
                    stress_after=player.stress,
                    health_before=player.health,
                    health_after=player.health,
                    cash_before=Decimal("1000.0000"),
                    cash_after=Decimal("1010.0000"),
                    income_xgp=Decimal("110.0000"),
                    expenses_xgp=Decimal("95.0000"),
                    side_income_net_xgp=Decimal("22.0000"),
                    business_net_profit_xgp=Decimal("54.0000") if idx < 2 else Decimal("12.0000"),
                    stock_pnl_xgp=Decimal("0.0000"),
                    debt_paid_xgp=Decimal("9.0000"),
                    stress_change=1,
                    health_change=0,
                    region_key="downtown" if idx < 2 else "suburban",
                )
            )

            self.db.add(
                FinancialDistressLog(
                    player_id=player.id,
                    day=1,
                    debt_payment_due_xgp=Decimal("9.0000"),
                    debt_payment_paid_xgp=Decimal("9.0000"),
                    debt_payment_missed=False,
                    late_fee_xgp=Decimal("0.0000"),
                    accrued_interest_xgp=Decimal("0.2000"),
                    credit_score_before=640,
                    credit_score_after=641,
                    credit_score_delta=1,
                    distress_state_before="stretched",
                    distress_state_after="stretched",
                    distress_score_before=Decimal("38.0000"),
                    distress_score_after=Decimal("36.0000"),
                )
            )

        self.db.commit()
        self.target_player = self.players[0]

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_player(self, *, stress: int, health: int, distress: int) -> Player:
        user = User(email=f"balance-report-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            cash=Decimal("1000.00"),
            debt_xgp=Decimal("900.00"),
            stress=stress,
            health=health,
            distress_score=Decimal(str(distress)),
            required_daily_debt_payment_xgp=Decimal("9.0000"),
            region="downtown",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def test_balance_report_returns_stable_structure(self) -> None:
        report = build_balance_report(self.db, as_of_date=date(2026, 1, 1))

        self.assertIn("top_system_risks", report)
        self.assertIn("dominant_jobs", report)
        self.assertIn("dominant_businesses", report)
        self.assertIn("weak_recovery_areas", report)
        self.assertIn("high_volatility_areas", report)
        self.assertIn("suggested_tuning_targets", report)
        self.assertIn("debug_meta", report)

    def test_system_dominance_detects_controlled_food_truck_bias(self) -> None:
        dominance = build_system_dominance_report(self.db, as_of_date=date(2026, 1, 1))
        business_names = [name for name, _value in dominance["dominant_businesses"]]
        self.assertIn("food_truck", business_names)

    def test_player_strategy_report_has_viability_and_flags(self) -> None:
        strategy = build_player_strategy_report(self.db, str(self.target_player.id), as_of_date=date(2026, 1, 1))
        self.assertIn("days_cash_cushion", strategy)
        self.assertIn("debt_pressure_ratio", strategy)
        self.assertIn("active_exploit_flags", strategy)
        self.assertIn("debug_meta", strategy)


if __name__ == "__main__":
    unittest.main()
