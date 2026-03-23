import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_business_daily_ops.db")

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
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
from app.services.business_daily_operations_service import (
    create_player_business,
    run_business_day,
    run_player_businesses_for_day,
)
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


class BusinessDailyOperationsServiceTests(unittest.TestCase):
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
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                DebtCreditLog.__table__,
                PlayerEmploymentState.__table__,
                StockDailyPrice.__table__,
                PlayerHousingState.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                HousingDailyLog.__table__,
            ],
        )

        self.db = self.SessionLocal()

        user = User(
            email=f"business-test-{uuid.uuid4()}@example.com",
            hashed_password="hashed-password",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Business Test Player",
            cash=Decimal("2000.00"),
            stress=20,
            health=95,
            hours_available=16,
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        self.player = player

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.2"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.2"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Baseline",
                event_summary="Baseline macro row for tests.",
            )
        )

        self.db.add_all(
            [
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("10.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.protein,
                    price_index=Decimal("12.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.convenience,
                    price_index=Decimal("8.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
            ]
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

        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code=None,
                skill_level=1,
                monthly_pay_xgp=Decimal("3000.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_create_fruit_shop(self) -> None:
        result = create_player_business(self.db, str(self.player.id), "fruit_shop", "suburban", 1)
        self.assertEqual(result["business_type"], "fruit_shop")
        self.assertEqual(result["region"], "suburban")

    def test_create_food_truck(self) -> None:
        create_player_business(self.db, str(self.player.id), "fruit_shop", "suburban", 1)
        result = create_player_business(self.db, str(self.player.id), "food_truck", "downtown", 1)

        self.assertEqual(result["business_type"], "food_truck")
        count = self.db.query(PlayerBusiness).filter(PlayerBusiness.player_id == self.player.id).count()
        self.assertEqual(count, 2)

    def test_run_fruit_shop_day_creates_log_and_ledger(self) -> None:
        business = create_player_business(self.db, str(self.player.id), "fruit_shop", "suburban", 1)
        run_result = run_business_day(self.db, business["business_id"], 1)
        self.db.commit()

        self.assertEqual(run_result["status"], "ran")

        log = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == uuid.UUID(business["business_id"]), BusinessDailyLog.day == 1)
            .first()
        )
        self.assertIsNotNone(log)

        ledger_count = (
            self.db.query(BusinessLedgerEntry)
            .filter(BusinessLedgerEntry.business_id == uuid.UUID(business["business_id"]), BusinessLedgerEntry.day == 1)
            .count()
        )
        self.assertGreaterEqual(ledger_count, 3)

    def test_run_food_truck_day_creates_log_and_ledger(self) -> None:
        business = create_player_business(self.db, str(self.player.id), "food_truck", "downtown", 1)
        run_result = run_business_day(self.db, business["business_id"], 1)
        self.db.commit()

        self.assertEqual(run_result["status"], "ran")

        ledger_rows = (
            self.db.query(BusinessLedgerEntry)
            .filter(BusinessLedgerEntry.business_id == uuid.UUID(business["business_id"]), BusinessLedgerEntry.day == 1)
            .all()
        )
        categories = {row.category for row in ledger_rows}
        self.assertIn("revenue", categories)
        self.assertIn("input_cost", categories)
        self.assertIn("overhead_cost", categories)
        self.assertIn("fuel_cost", categories)

    def test_running_same_business_day_twice_does_not_duplicate(self) -> None:
        business = create_player_business(self.db, str(self.player.id), "fruit_shop", "suburban", 1)
        business_uuid = uuid.UUID(business["business_id"])

        first = run_business_day(self.db, business["business_id"], 1)
        self.db.commit()
        self.db.refresh(self.player)
        cash_after_first = float(self.player.cash_xgp)

        logs_after_first = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == business_uuid, BusinessDailyLog.day == 1)
            .count()
        )
        ledger_after_first = (
            self.db.query(BusinessLedgerEntry)
            .filter(BusinessLedgerEntry.business_id == business_uuid, BusinessLedgerEntry.day == 1)
            .count()
        )

        second = run_business_day(self.db, business["business_id"], 1)
        self.db.commit()
        self.db.refresh(self.player)
        cash_after_second = float(self.player.cash_xgp)

        logs_after_second = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == business_uuid, BusinessDailyLog.day == 1)
            .count()
        )
        ledger_after_second = (
            self.db.query(BusinessLedgerEntry)
            .filter(BusinessLedgerEntry.business_id == business_uuid, BusinessLedgerEntry.day == 1)
            .count()
        )

        self.assertEqual(first["status"], "ran")
        self.assertEqual(second["status"], "already_processed")
        self.assertEqual(cash_after_first, cash_after_second)
        self.assertEqual(logs_after_first, 1)
        self.assertEqual(logs_after_second, 1)
        self.assertEqual(ledger_after_first, ledger_after_second)

    def test_day_progression_includes_business_result(self) -> None:
        create_player_business(self.db, str(self.player.id), "fruit_shop", "suburban", 1)

        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("business_net_xgp", result)
        self.assertIn("total_business_profit_xgp", result)
        self.assertIn("summary_json", result)
        self.assertIn("headline", result)
        self.assertIn("summary", result)
        self.assertIn("macro_tags_json", result)
        self.assertIn("player_impact_json", result)
        self.assertIn("action_hints_json", result)
        self.assertIn("total_business_profit_xgp", result["summary_json"])
        self.assertIn("per_business_results", result["summary_json"])
        self.assertIn("business_summary", result["summary_json"])

    def test_player_cash_changes_after_business_run(self) -> None:
        create_player_business(self.db, str(self.player.id), "food_truck", "suburban", 1)
        cash_before = float(self.player.cash_xgp)

        run_player_businesses_for_day(self.db, str(self.player.id), 1, commit=True)
        self.db.refresh(self.player)

        cash_after = float(self.player.cash_xgp)
        self.assertNotEqual(cash_before, cash_after)

    def test_business_can_lose_money_on_bad_day(self) -> None:
        business = create_player_business(self.db, str(self.player.id), "food_truck", "rural", 1)

        self.db.add(
            MacroDailyState(
                day=2,
                inflation_rate=Decimal("8.5"),
                interest_rate=Decimal("7.5"),
                unemployment_rate=Decimal("9.5"),
                oil_index=Decimal("500.0"),
                consumer_confidence=Decimal("10.0"),
                supply_chain_stress=Decimal("5.0"),
                event_headline="Stress Test",
                event_summary="Very bad macro day for small businesses.",
            )
        )
        self.db.add_all(
            [
                BasketDailyPrice(
                    day=2,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("20.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.3000"),
                    demand_pressure=Decimal("0.8000"),
                ),
                BasketDailyPrice(
                    day=2,
                    basket_type=BasketType.protein,
                    price_index=Decimal("25.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.3500"),
                    demand_pressure=Decimal("0.8000"),
                ),
                BasketDailyPrice(
                    day=2,
                    basket_type=BasketType.produce,
                    price_index=Decimal("18.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.2500"),
                    demand_pressure=Decimal("0.8000"),
                ),
            ]
        )
        self.db.commit()

        run_result = run_business_day(self.db, business["business_id"], 2)
        self.db.commit()

        self.assertLess(run_result["net_profit_xgp"], 0.0)


if __name__ == "__main__":
    unittest.main()
