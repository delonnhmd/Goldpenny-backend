import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_onboarding_integration.db")

from app.db.database import Base
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition import JOB_CATALOG
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_business import PlayerBusiness
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_onboarding_state import PlayerOnboardingState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.admin_debug_service import get_full_player_debug_snapshot
from app.services.day_progression_service import run_player_next_day
from app.engine.onboarding_service import build_first_session_dashboard_config, build_onboarding_guidance


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


class OnboardingIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                PlayerBusiness.__table__,
                JobDefinitionDB.__table__,
                MacroDailyState.__table__,
                StockDailyPrice.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                HousingDailyLog.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                DebtCreditLog.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerOnboardingState.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed_market()
        self._seed_player()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_market(self) -> None:
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.2"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.1"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.6"),
                event_headline="Baseline market day",
                event_summary="Starter baseline macro state.",
            )
        )

        for ticker, sector in TICKER_SECTOR.items():
            self.db.add(
                StockDailyPrice(
                    day=1,
                    ticker=ticker,
                    sector=sector,
                    open_price=Decimal("50.0000"),
                    close_price=Decimal("50.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    macro_impact=Decimal("0.0000"),
                    noise_component=Decimal("0.0000"),
                )
            )

        basket_prices = {
            BasketType.essentials: Decimal("10.0000"),
            BasketType.protein: Decimal("12.0000"),
            BasketType.produce: Decimal("9.0000"),
            BasketType.convenience: Decimal("8.5000"),
        }
        for basket_type, price in basket_prices.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )

        static = JOB_CATALOG.get("banker")
        self.db.add(
            JobDefinitionDB(
                job_code="banker",
                title="Banker",
                base_monthly_pay_xgp=Decimal(str(static.monthly_salary if static else 3200)),
                stability_pct=Decimal("0.82"),
                growth_pct=Decimal("0.75"),
                stress_pct=Decimal("0.60"),
                promotion_threshold=100,
            )
        )

    def _seed_player(self) -> None:
        user = User(email=f"step31-int-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step31 Integration",
            gender="female",
            region="suburban",
            cash=Decimal("850.00"),
            bank_savings_xgp=Decimal("120.00"),
            debt_xgp=Decimal("250.00"),
            credit_score=640,
            net_worth=Decimal("720.00"),
            health=88,
            stress=24,
            hours_available=16,
            skill_level=1,
            main_job="banker",
            has_active_housing=True,
            housing_region_id="suburban",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="suburban",
                housing_type="starter_rent",
                daily_housing_cost_xgp=Decimal("18.00"),
                commute_modifier=Decimal("1.1"),
                stress_modifier=1,
                opportunity_modifier=Decimal("0.95"),
                active_flag=True,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("5100.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
                opportunity_score=Decimal("1.0000"),
            )
        )
        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                hours_available_start=16,
                hours_available_end=16,
                worked_main_job=False,
                worked_hours=0,
                gross_income_xgp=Decimal("0.00"),
                did_settlement=False,
                stress_start=24,
                stress_end=24,
                health_start=88,
                health_end=88,
                cash_start=Decimal("850.00"),
                cash_end=Decimal("850.00"),
                housing_region_id="suburban",
            )
        )

    def test_day_run_includes_onboarding_summary_payload(self) -> None:
        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("onboarding_summary", result)
        summary = result["onboarding_summary"] or {}
        self.assertIn("state", summary)
        self.assertIn("guidance", summary)
        self.assertIn("dashboard_config", summary)
        self.assertIn("unlock_schedule", summary)
        self.assertIn("hidden_sections", summary["dashboard_config"])

        day_two_guidance = build_onboarding_guidance(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        day_two_config = build_first_session_dashboard_config(self.db, str(self.player.id), as_of_date=date(2026, 1, 2))
        self.assertEqual(day_two_guidance["guided_day_number"], 2)
        self.assertIn("recovery_vs_push", day_two_config["visible_sections"])

    def test_admin_debug_snapshot_includes_onboarding_driver_chain(self) -> None:
        run_player_next_day(self.db, str(self.player.id))
        snapshot = get_full_player_debug_snapshot(self.db, str(self.player.id))

        self.assertIn("onboarding_state", snapshot)
        self.assertIn("onboarding_guidance", snapshot)
        self.assertIn("onboarding_dashboard_config", snapshot)
        self.assertIn("onboarding_unlock_schedule", snapshot)
        self.assertIn("onboarding_completion_debug", snapshot)

    def test_no_action_starter_days_do_not_generate_passive_salary(self) -> None:
        starting_cash = float(self.player.cash_xgp)
        ending_cash_values: list[float] = []

        for _ in range(5):
            result = run_player_next_day(self.db, str(self.player.id))
            ending_cash_values.append(float(result["ending_cash_xgp"]))
            self.assertEqual(result["income_xgp"], 0.0)

        self.db.refresh(self.player)
        self.assertTrue(all(cash <= starting_cash for cash in ending_cash_values))
        self.assertLess(float(self.player.cash_xgp), starting_cash)


if __name__ == "__main__":
    unittest.main()
