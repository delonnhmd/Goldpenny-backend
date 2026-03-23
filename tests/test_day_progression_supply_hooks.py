import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_day_progression_supply_hooks.db")

from app.services.day_progression_service import run_player_next_day
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


class DayProgressionSupplyHooksTests(unittest.TestCase):
    def _run_world_once(self) -> dict:
        engine = create_engine("sqlite:///:memory:", future=True)
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            future=True,
        )
        Base.metadata.create_all(
            bind=engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                DebtCreditLog.__table__,
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
        db = SessionLocal()
        try:
            user = User(
                email=f"supply-hooks-{uuid.uuid4()}@example.com",
                hashed_password="hashed",
            )
            db.add(user)
            db.flush()

            player = Player(
                user_id=user.id,
                display_name="Supply Hooks Player",
                cash=Decimal("1000.00"),
                debt_xgp=Decimal("150.00"),
                stress=22,
                health=94,
                hours_available=16,
                region="suburban",
                main_job="delivery_driver",
            )
            db.add(player)
            db.flush()

            db.add(
                MacroDailyState(
                    day=1,
                    inflation_rate=Decimal("4.6"),
                    interest_rate=Decimal("5.1"),
                    unemployment_rate=Decimal("6.4"),
                    oil_index=Decimal("152.0"),
                    consumer_confidence=Decimal("42.0"),
                    supply_chain_stress=Decimal("1.8"),
                )
            )

            for ticker, sector in TICKER_SECTOR.items():
                db.add(
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
                BasketType.convenience: Decimal("8.0000"),
            }.items():
                db.add(
                    BasketDailyPrice(
                        day=1,
                        basket_type=basket_type,
                        price_index=price,
                        daily_change_pct=Decimal("0.0000"),
                        supply_pressure=Decimal("1.0000"),
                        demand_pressure=Decimal("1.0000"),
                    )
                )

            db.add(
                JobDefinitionDB(
                    job_code="delivery_driver",
                    title="Delivery Driver",
                    base_monthly_pay_xgp=Decimal("2900.00"),
                    stability_pct=Decimal("0.62"),
                    growth_pct=Decimal("0.45"),
                    stress_pct=Decimal("0.65"),
                    promotion_threshold=100,
                )
            )
            db.add(
                PlayerEmploymentState(
                    player_id=player.id,
                    day=1,
                    current_job_code="delivery_driver",
                    skill_level=1,
                    monthly_pay_xgp=Decimal("2900.00"),
                    employed_flag=True,
                    job_status="employed",
                    layoff_risk_pct=Decimal("8.00"),
                    productivity_modifier=Decimal("1.0000"),
                )
            )

            db.commit()
            return run_player_next_day(db, str(player.id))
        finally:
            db.close()
            engine.dispose()

    def test_day_run_includes_supply_chain_transmission_outputs(self) -> None:
        result = self._run_world_once()
        self.assertIn("basket_pricing_summary", result)
        self.assertIn("job_market_summary", result)
        self.assertIn("daily_economy_brief", result)
        self.assertIn("top_bottlenecks", result)
        self.assertIn("top_basket_movers", result)
        self.assertIn("top_job_changes", result)
        self.assertTrue(result["economy_headline"])
        self.assertGreater(len(result["economy_summary_lines"]), 0)

    def test_day_run_transmission_outputs_are_deterministic_for_same_seed(self) -> None:
        one = self._run_world_once()
        two = self._run_world_once()

        self.assertEqual(one["basket_pricing_summary"]["basket_updates"], two["basket_pricing_summary"]["basket_updates"])
        self.assertEqual(one["job_market_summary"]["job_updates"], two["job_market_summary"]["job_updates"])
        self.assertEqual(one["daily_economy_brief"]["headline"], two["daily_economy_brief"]["headline"])
        self.assertEqual(one["top_bottlenecks"], two["top_bottlenecks"])


if __name__ == "__main__":
    unittest.main()
