import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"

from app.db.database import Base
from app.engine.business_service import create_or_get_starter_business
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.gameplay_transaction import GameplayTransaction
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
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.daily_settlement_service import settle_player_day
from app.services.day_progression_service import run_player_next_day


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


class LifeDayProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()

        user = User(email=f"life-day-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            cash=Decimal("4200.00"),
            debt_xgp=Decimal("1200.00"),
            stress=28,
            health=91,
            hours_available=16,
            region="suburban",
            productivity_modifier=Decimal("0.92"),
            base_productivity_modifier=Decimal("0.92"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.1"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.4"),
                oil_index=Decimal("108.0"),
                consumer_confidence=Decimal("50.0"),
                supply_chain_stress=Decimal("0.8"),
                event_headline="Test baseline",
                event_summary="Life progression baseline row.",
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

        for basket_type, price in {
            BasketType.essentials: Decimal("10.0000"),
            BasketType.protein: Decimal("12.0000"),
            BasketType.produce: Decimal("9.0000"),
            BasketType.convenience: Decimal("8.4000"),
        }.items():
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

        self.db.add(
            JobDefinitionDB(
                job_code="retail_worker",
                title="Retail Worker",
                base_monthly_pay_xgp=Decimal("2800.00"),
                stability_pct=Decimal("0.68"),
                growth_pct=Decimal("0.45"),
                stress_pct=Decimal("0.60"),
                promotion_threshold=100,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="retail_worker",
                skill_level=1,
                monthly_pay_xgp=Decimal("2800.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        business_payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player.id),
            business_type="food_truck",
            region_key="suburban",
        )
        business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.id == uuid.UUID(business_payload["business_id"]))
            .first()
        )
        business.inventory_essentials_units = Decimal("180.0")
        business.inventory_protein_units = Decimal("130.0")
        business.reputation = 68

        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                hours_available_start=16,
                hours_available_end=10,
                worked_main_job=True,
                worked_hours=8,
                side_income_hours=Decimal("4.0000"),
                did_settlement=False,
                stress_start=28,
                stress_end=34,
                health_start=91,
                health_end=90,
                cash_start=Decimal("4200.0000"),
                cash_end=Decimal("4250.0000"),
            )
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_day_run_includes_life_outputs(self) -> None:
        result = run_player_next_day(self.db, str(self.player.id))
        for key in [
            "life_summary",
            "time_budget_summary",
            "productivity_modifier",
            "burnout_risk",
            "medical_event_risk",
            "medical_cost_xgp",
            "missed_work_penalty_xgp",
            "overtime_hours",
            "sleep_hours",
            "recovery_hours",
            "commute_hours",
            "region_stress_delta",
        ]:
            self.assertIn(key, result)

    def test_settlement_summary_includes_life_fields(self) -> None:
        result = settle_player_day(self.db, str(self.player.id))
        summary = result.get("summary_json", {})

        self.assertIn("total_hours_used", result)
        self.assertIn("productivity_modifier", result)
        self.assertIn("medical_cost_xgp", result)
        self.assertIn("missed_work_penalty_xgp", result)
        self.assertIn("life_summary", result)
        self.assertIn("time_budget_summary", result)
        self.assertIn("burnout_risk", summary)
        self.assertIn("medical_event_risk", summary)

    def test_settlement_log_persists_life_snapshot_fields(self) -> None:
        settle_player_day(self.db, str(self.player.id))
        log = (
            self.db.query(DailySettlementLog)
            .filter(DailySettlementLog.player_id == self.player.id, DailySettlementLog.day_number == 1)
            .first()
        )
        self.assertIsNotNone(log)
        self.assertGreaterEqual(float(log.total_hours_used or 0), 0.0)
        self.assertGreaterEqual(float(log.productivity_modifier or 0), 0.70)
        self.assertLessEqual(float(log.productivity_modifier or 0), 1.05)

    def test_settlement_persists_work_tracking_and_salary_ledger(self) -> None:
        settle_player_day(self.db, str(self.player.id))
        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )
        salary_rows = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
                GameplayTransaction.category == "salary",
            )
            .all()
        )

        self.assertIsNotNone(pds)
        self.assertTrue(bool(pds.did_work))
        self.assertGreater(float(pds.salary_earned or 0), 0.0)
        self.assertEqual(float(pds.missed_penalty or 0), 0.0)
        self.assertEqual(len(salary_rows), 1)
        self.assertGreater(float(salary_rows[0].amount), 0.0)


if __name__ == "__main__":
    unittest.main()
