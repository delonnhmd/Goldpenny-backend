import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_weekly_strategy_service.db")

from app.db.database import Base
from app.engine.weekly_strategy_service import (
    build_economy_weekly_summary,
    build_player_weekly_strategy_summary,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.user import User


class WeeklyStrategyServiceTests(unittest.TestCase):
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
                DailyEconomyEvent.__table__,
                BasketDailyPrice.__table__,
                MacroDailyState.__table__,
                JobDefinitionDB.__table__,
                PlayerEmploymentState.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.player = self._seed_player()
        self._seed_job_defs()
        self._seed_player_week()
        self._seed_economy_week()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player(self) -> Player:
        user = User(email=f"weekly-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name="Weekly Strategy",
            cash=Decimal("1800.00"),
            debt_xgp=Decimal("900.00"),
            stress=40,
            health=90,
            hours_available=16,
            region="downtown",
            main_job="banker",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_job_defs(self) -> None:
        self.db.add_all(
            [
                JobDefinitionDB(
                    job_code="banker",
                    title="Banker",
                    base_monthly_pay_xgp=Decimal("5200.00"),
                    stability_pct=Decimal("0.82"),
                    growth_pct=Decimal("0.72"),
                    stress_pct=Decimal("0.62"),
                    promotion_threshold=100,
                ),
                JobDefinitionDB(
                    job_code="chef",
                    title="Chef",
                    base_monthly_pay_xgp=Decimal("3300.00"),
                    stability_pct=Decimal("0.62"),
                    growth_pct=Decimal("0.58"),
                    stress_pct=Decimal("0.74"),
                    promotion_threshold=100,
                ),
            ]
        )

    def _seed_player_week(self) -> None:
        for day in range(1, 8):
            self.db.add(
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=day,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=45 + day,
                    stress_after=46 + day,
                    health_before=90 - day,
                    health_after=89 - day,
                    cash_before=Decimal("1500.00"),
                    cash_after=Decimal("1520.00"),
                    income_xgp=Decimal("210.00"),
                    expenses_xgp=Decimal("180.00"),
                    stock_pnl_xgp=Decimal("0.00"),
                    debt_paid_xgp=Decimal("7.00"),
                    health_change=-1,
                    stress_change=1,
                    side_income_net_xgp=Decimal("125.00"),
                    business_net_profit_xgp=Decimal("20.00"),
                    housing_cost_daily_xgp=Decimal("34.00"),
                    utilities_cost_daily_xgp=Decimal("7.00"),
                    commute_fuel_cost_xgp=Decimal("5.00"),
                    business_cogs_xgp=Decimal("24.00"),
                    business_overhead_xgp=Decimal("12.00"),
                    business_fuel_cost_xgp=Decimal("4.00"),
                )
            )
            self.db.add(
                PlayerDailyState(
                    player_id=self.player.id,
                    day_number=day,
                    hours_available_start=24,
                    hours_available_end=7,
                    worked_main_job=True,
                    worked_hours=5,
                    gross_income_xgp=Decimal("210.00"),
                    did_settlement=True,
                    stress_start=44 + day,
                    stress_end=46 + day,
                    health_start=91 - day,
                    health_end=89 - day,
                    cash_start=Decimal("1500.00"),
                    cash_end=Decimal("1520.00"),
                    job_hours=Decimal("5.0"),
                    side_income_hours=Decimal("4.0"),
                    business_hours=Decimal("1.0"),
                    overtime_hours=Decimal("1.5"),
                )
            )
            self.db.add(
                FinancialDistressLog(
                    player_id=self.player.id,
                    day=day,
                    debt_payment_due_xgp=Decimal("12.00"),
                    debt_payment_paid_xgp=Decimal("10.00"),
                    debt_payment_missed=(day % 3 == 0),
                    distress_score_before=Decimal(str(30 + day)),
                    distress_score_after=Decimal(str(32 + day)),
                )
            )
            self.db.add(
                CareerProgressLog(
                    player_id=self.player.id,
                    day_number=day,
                    skill_before=Decimal(str(20 + day)),
                    skill_after=Decimal(str(20.8 + day)),
                    skill_delta=Decimal("0.8"),
                    training_hours=Decimal("2.0"),
                )
            )

    def _seed_economy_week(self) -> None:
        event_keys = [
            "oil_spike",
            "pipeline_disruption",
            "retail_slump",
            "supply_relief",
            "confidence_rebound",
            "credit_tightening",
            "hiring_surge",
        ]
        sentiments = ["negative", "negative", "negative", "positive", "positive", "negative", "positive"]
        categories = ["energy", "energy", "consumer", "recovery", "recovery", "financial", "recovery"]

        for day in range(1, 8):
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.4") + Decimal(str(day)) * Decimal("0.02"),
                    interest_rate=Decimal("4.0") + Decimal(str(day)) * Decimal("0.01"),
                    unemployment_rate=Decimal("5.1"),
                    oil_index=Decimal("100.0") + Decimal(str(day)) * Decimal("1.5"),
                    consumer_confidence=Decimal("50.0") - Decimal(str(day)) * Decimal("0.4"),
                    supply_chain_stress=Decimal("0.5") + Decimal(str(day)) * Decimal("0.03"),
                    event_headline="Weekly summary seed",
                    event_summary="Macro row for weekly summary test.",
                )
            )

            self.db.add(
                DailyEconomyEvent(
                    day=day,
                    event_key=event_keys[day - 1],
                    headline=f"Event {day}",
                    summary="Seed event",
                    event_category=categories[day - 1],
                    sentiment=sentiments[day - 1],
                    severity=Decimal("1.0"),
                    impact_tags_json="[]",
                    source_type="generated",
                )
            )

            self.db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.0") + Decimal(str(day)) * Decimal("0.35"),
                    daily_change_pct=Decimal("0.0200"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )
            self.db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("10.0") + Decimal(str(day)) * Decimal("0.05"),
                    daily_change_pct=Decimal("0.0100"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )

            self.db.add(
                PlayerEmploymentState(
                    player_id=self.player.id,
                    day=day,
                    current_job_code="banker" if day % 2 else "chef",
                    skill_level=1,
                    monthly_pay_xgp=Decimal("3000.00"),
                    employed_flag=True,
                    opportunity_score=Decimal("1.05") if day % 2 else Decimal("0.98"),
                    layoff_risk_pct=Decimal("8.00"),
                    productivity_modifier=Decimal("1.0"),
                )
            )

    def test_player_weekly_summary_reflects_real_state(self) -> None:
        payload = build_player_weekly_strategy_summary(db=self.db, player_id=str(self.player.id))
        self.assertEqual(payload["player_id"], str(self.player.id))
        self.assertEqual(payload["dominant_income_source"], "side_income")
        self.assertIn(payload["distress_trend"], {"rising", "stable"})
        self.assertEqual(payload["career_trend"], "rising")
        self.assertTrue(len(payload["suggested_next_moves"]) >= 1)

    def test_economy_weekly_summary_is_deterministic_and_structured(self) -> None:
        first = build_economy_weekly_summary(db=self.db)
        second = build_economy_weekly_summary(db=self.db)
        self.assertEqual(first, second)
        self.assertIn("dominant_event_chains", first)
        self.assertIn("top_basket_movers", first)
        self.assertIn("strongest_jobs", first)
        self.assertIn("volatility_tone", first)
        self.assertGreaterEqual(len(first["dominant_event_chains"]), 1)
        self.assertTrue(any(row["basket_type"] == "produce" for row in first["top_basket_movers"]))


if __name__ == "__main__":
    unittest.main()

