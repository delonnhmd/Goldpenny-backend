import json
import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_financial_distress_integration.db")

from app.api.internal import get_internal_player_snapshot
from app.db.database import Base
from app.engine.life_balance_service import compute_daily_stress_update
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
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


class FinancialDistressIntegrationTests(unittest.TestCase):
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
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                DebtCreditLog.__table__,
                FinancialDistressLog.__table__,
                PlayerEmploymentState.__table__,
                JobDefinitionDB.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                StockDailyPrice.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                PlayerHousingState.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerStockHolding.__table__,
                HousingDailyLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(
            email=f"fd-int-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Distress Integration",
            cash=Decimal("0.00"),
            debt_xgp=Decimal("2400.00"),
            credit_score=640,
            stress=62,
            health=85,
            hours_available=16,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.1"),
                interest_rate=Decimal("4.2"),
                unemployment_rate=Decimal("5.8"),
                oil_index=Decimal("109.0"),
                consumer_confidence=Decimal("47.0"),
                supply_chain_stress=Decimal("0.8"),
                event_headline="Stressful baseline",
                event_summary="Baseline for Step 20 integration tests.",
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

        self.db.add_all(
            [
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("10.2000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.protein,
                    price_index=Decimal("12.5000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.2000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.convenience,
                    price_index=Decimal("8.3000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
            ]
        )

        self.db.add(
            JobDefinitionDB(
                job_code="retail_worker",
                title="Retail Worker",
                base_monthly_pay_xgp=Decimal("1200.00"),
                stability_pct=Decimal("0.60"),
                growth_pct=Decimal("0.35"),
                stress_pct=Decimal("0.55"),
                promotion_threshold=100,
            )
        )

        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="retail_worker",
                skill_level=1,
                monthly_pay_xgp=Decimal("1200.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("12.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_day_run_includes_financial_distress_summary_fields(self) -> None:
        settle_player_day(self.db, str(self.player.id))
        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("financial_distress_summary", result)
        self.assertIn("debt_payment_due_xgp", result)
        self.assertIn("debt_payment_paid_xgp", result)
        self.assertIn("debt_payment_missed", result)
        self.assertIn("late_fee_xgp", result)
        self.assertIn("accrued_interest_xgp", result)
        self.assertIn("distress_state", result)
        self.assertIn("distress_score", result)
        self.assertIn("borrowing_cost_modifier", result)
        self.assertIn("opportunity_access_penalty", result)
        self.assertIn("recovery_actions_applied", result)
        self.assertIn(result["distress_state"], {"stable", "stretched", "distressed", "critical"})

    def test_settlement_persists_step20_debt_credit_distress_fields(self) -> None:
        settle_player_day(self.db, str(self.player.id))

        log = (
            self.db.query(DailySettlementLog)
            .filter(DailySettlementLog.player_id == self.player.id, DailySettlementLog.day_number == 1)
            .first()
        )
        self.assertIsNotNone(log)
        self.assertIsNotNone(log.debt_payment_due_xgp)
        self.assertIsNotNone(log.debt_payment_paid_xgp)
        self.assertIsNotNone(log.late_fee_xgp)
        self.assertIsNotNone(log.accrued_interest_xgp)
        self.assertIsNotNone(log.credit_score_before)
        self.assertIsNotNone(log.credit_score_after)
        self.assertIsNotNone(log.distress_state_before)
        self.assertIsNotNone(log.distress_state_after)

        summary = json.loads(log.summary_json or "{}")
        self.assertIn("financial_distress_summary", summary)
        self.assertIn("debt_payment_due_xgp", summary)
        self.assertIn("debt_payment_paid_xgp", summary)
        self.assertIn("distress_state_after", summary)

        self.assertGreaterEqual(float(log.debt_payment_due_xgp), 0.0)
        self.assertGreaterEqual(float(log.late_fee_xgp), 0.0)
        self.assertGreaterEqual(float(log.accrued_interest_xgp), 0.0)

    def test_admin_debug_snapshot_shows_distress_chain(self) -> None:
        settle_player_day(self.db, str(self.player.id))

        snapshot = get_internal_player_snapshot(player_id=str(self.player.id), db=self.db)
        payload = snapshot.model_dump()

        self.assertIn("latest_financial_distress_summary", payload)
        self.assertIn("location_chain", payload)
        self.assertIn("from_financial_distress", payload["location_chain"])
        self.assertIn("distress_state", payload["player_profile"])
        self.assertIn("distress_score", payload["player_profile"])

    def test_life_stress_reflects_distress_synergy(self) -> None:
        baseline = compute_daily_stress_update(
            stress_before=Decimal("50"),
            overtime_hours=Decimal("1.0"),
            sleep_hours=Decimal("7.0"),
            recovery_hours=Decimal("1.5"),
            debt_pressure_score=Decimal("0.2"),
            business_net_profit_xgp=Decimal("0"),
            job_pressure=Decimal("0.00"),
            layoff_risk_pct=Decimal("6"),
            region_key="suburban",
            distress_score=Decimal("10"),
            distress_state="stable",
        )
        distressed = compute_daily_stress_update(
            stress_before=Decimal("50"),
            overtime_hours=Decimal("1.0"),
            sleep_hours=Decimal("7.0"),
            recovery_hours=Decimal("1.5"),
            debt_pressure_score=Decimal("0.2"),
            business_net_profit_xgp=Decimal("0"),
            job_pressure=Decimal("0.00"),
            layoff_risk_pct=Decimal("6"),
            region_key="suburban",
            distress_score=Decimal("86"),
            distress_state="critical",
        )

        self.assertGreater(distressed["stress_delta"], baseline["stress_delta"])


if __name__ == "__main__":
    unittest.main()
