import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_world_memory_integration.db")

from app.db.database import Base
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
from app.models.player_commitment_history import PlayerCommitmentHistory
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_goal_history import PlayerGoalHistory
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_world_memory_state import PlayerWorldMemoryState
from app.models.player_world_pattern_history import PlayerWorldPatternHistory
from app.models.side_income_action import SideIncomeAction
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.admin_debug_service import get_economy_debug_snapshot, get_full_player_debug_snapshot
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


class WorldMemoryIntegrationTests(unittest.TestCase):
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
                SideIncomeAction.__table__,
                PlayerProgressionState.__table__,
                PlayerGoalHistory.__table__,
                PlayerCommitmentState.__table__,
                PlayerCommitmentHistory.__table__,
                PlayerWorldMemoryState.__table__,
                PlayerWorldPatternHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"step30-integration-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="World Memory Integration Tester",
            cash=Decimal("1200.00"),
            debt_xgp=Decimal("300.00"),
            stress=28,
            health=92,
            hours_available=16,
            region="suburban",
            main_job="delivery_driver",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.8"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.4"),
                oil_index=Decimal("112.0"),
                consumer_confidence=Decimal("48.0"),
                supply_chain_stress=Decimal("1.05"),
                event_headline="Pressure baseline",
                event_summary="Initial pressure setup for integration test.",
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
            BasketType.essentials: Decimal("10.4"),
            BasketType.protein: Decimal("11.3"),
            BasketType.produce: Decimal("10.9"),
            BasketType.convenience: Decimal("9.9"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.35"),
                    supply_pressure=Decimal("1.03"),
                    demand_pressure=Decimal("1.02"),
                )
            )

        self.db.add(
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
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
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

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_day_run_and_debug_snapshots_include_world_memory_chain(self) -> None:
        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("world_memory_snapshot", result)
        self.assertIn("world_patterns", result)
        self.assertIn("world_narrative", result)
        self.assertIn("local_pressure_summary", result)
        self.assertIn("player_pattern_summary", result)
        self.assertIn("region_memory_summary", result)

        practical = (
            (result.get("local_pressure_summary") or {}).get("practical_response_options") or []
        )
        self.assertTrue(any("move" in str(item).lower() for item in practical))
        self.assertTrue(any("rent closer" in str(item).lower() for item in practical))

        full_debug = get_full_player_debug_snapshot(self.db, str(self.player.id))
        self.assertIn("world_memory_snapshot", full_debug)
        self.assertIn("world_pattern_detection", full_debug)
        self.assertIn("world_narrative", full_debug)
        self.assertIn("world_local_pressure_summary", full_debug)
        self.assertIn("world_player_pattern_summary", full_debug)
        self.assertIn("world_region_memory_summary", full_debug)

        economy_debug = get_economy_debug_snapshot(self.db)
        self.assertIn("world_memory_snapshot", economy_debug)
        self.assertIn("world_pattern_detection", economy_debug)
        self.assertIn("world_narrative", economy_debug)
        self.assertIn("world_local_pressure_summary", economy_debug)
        self.assertIn("world_region_memory_summary", economy_debug)


if __name__ == "__main__":
    unittest.main()
