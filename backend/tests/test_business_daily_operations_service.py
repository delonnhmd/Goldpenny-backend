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
from app.models.game_state import GameState
from app.models.gameplay_transaction import GameplayTransaction
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.api.gameplay import GameplayActionRequest, execute_gameplay_action
from app.services.business_daily_operations_service import (
    BusinessValidationError,
    create_player_business,
    get_supplier_market_items,
    purchase_business_inventory_items,
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
                GameState.__table__,
                GameplayTransaction.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                PlayerDailyState.__table__,
                PlayerTransactionLog.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                DebtCreditLog.__table__,
                PlayerEmploymentState.__table__,
                PlayerProgressionState.__table__,
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
            user_id=str(user.id),
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
            GameState(
                current_day=1,
                day_status="open",
            )
        )

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

    def _create_business(self, business_type: str, region: str = "suburban", tier: int = 1) -> dict:
        return create_player_business(self.db, str(self.player.id), business_type, region, tier)

    def _buy_inventory(self, business_id: str, items: list[dict[str, object]]) -> dict:
        payload = purchase_business_inventory_items(
            self.db,
            str(self.player.id),
            business_id,
            items=items,
        )
        self.db.flush()
        return payload

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

    def test_supplier_item_list_is_filtered_by_business_type(self) -> None:
        fruit_items = get_supplier_market_items(self.db, "fruit_shop", day_number=1)
        truck_items = get_supplier_market_items(self.db, "food_truck", day_number=1)

        self.assertEqual(fruit_items["business_type"], "fruit_shop")
        self.assertEqual(truck_items["business_type"], "food_truck")
        self.assertEqual({item["item_id"] for item in fruit_items["items"]}, {"mango", "orange", "apple", "grape", "banana", "strawberry"})
        self.assertEqual({item["item_id"] for item in truck_items["items"]}, {"bread", "rice", "chicken", "beef", "egg", "cooking_oil"})

    def test_buy_fruit_shop_inventory_updates_cash_and_itemized_inventory(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)
        cash_before = float(self.player.cash_xgp)

        purchase = self._buy_inventory(
            business["business_id"],
            [
                {"item_id": "mango", "quantity": 20},
                {"item_id": "orange", "quantity": 30},
            ],
        )
        self.db.refresh(self.player)

        self.assertEqual(purchase["business_type"], "fruit_shop")
        self.assertGreater(purchase["total_purchase_cost_xgp"], 0.0)
        self.assertLess(float(self.player.cash_xgp), cash_before)
        self.assertEqual({item["item_id"] for item in purchase["inventory_items"]}, {"mango", "orange"})
        self.assertGreater(purchase["inventory_total_units"], 0.0)

    def test_buy_food_truck_inventory_updates_cash_and_itemized_inventory(self) -> None:
        business = self._create_business("food_truck", "downtown", 1)

        purchase = self._buy_inventory(
            business["business_id"],
            [
                {"item_id": "bread", "quantity": 24},
                {"item_id": "chicken", "quantity": 16},
                {"item_id": "cooking_oil", "quantity": 8},
            ],
        )

        self.assertEqual(purchase["business_type"], "food_truck")
        self.assertEqual({item["item_id"] for item in purchase["inventory_items"]}, {"bread", "chicken", "cooking_oil"})
        self.assertGreater(purchase["inventory_estimated_value_xgp"], 0.0)

    def test_inventory_purchase_rejects_insufficient_cash_and_incompatible_items(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)

        with self.assertRaises(BusinessValidationError):
            self._buy_inventory(
                business["business_id"],
                [{"item_id": "beef", "quantity": 10}],
            )

        self.player.cash_xgp = Decimal("5.00")
        self.db.flush()

        with self.assertRaises(BusinessValidationError):
            self._buy_inventory(
                business["business_id"],
                [{"item_id": "mango", "quantity": 100}],
            )

    def test_run_fruit_shop_day_creates_log_and_ledger(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)
        self._buy_inventory(
            business["business_id"],
            [
                {"item_id": "mango", "quantity": 18},
                {"item_id": "orange", "quantity": 24},
                {"item_id": "banana", "quantity": 18},
            ],
        )
        run_result = run_business_day(self.db, business["business_id"], 1)
        self.db.commit()

        self.assertEqual(run_result["status"], "ran")
        self.assertGreater(run_result["labor_cost_xgp"], 0.0)
        self.assertIn("units_sold_by_item", run_result)
        self.assertIn("remaining_inventory_by_item", run_result)

        log = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == uuid.UUID(business["business_id"]), BusinessDailyLog.day == 1)
            .first()
        )
        self.assertIsNotNone(log)
        self.assertGreater(float(log.labor_cost_xgp), 0.0)

        ledger_count = (
            self.db.query(BusinessLedgerEntry)
            .filter(BusinessLedgerEntry.business_id == uuid.UUID(business["business_id"]), BusinessLedgerEntry.day == 1)
            .count()
        )
        self.assertGreaterEqual(ledger_count, 4)

    def test_run_food_truck_day_creates_log_and_ledger(self) -> None:
        business = self._create_business("food_truck", "downtown", 1)
        self._buy_inventory(
            business["business_id"],
            [
                {"item_id": "bread", "quantity": 30},
                {"item_id": "rice", "quantity": 16},
                {"item_id": "chicken", "quantity": 18},
                {"item_id": "egg", "quantity": 12},
                {"item_id": "cooking_oil", "quantity": 10},
            ],
        )
        run_result = run_business_day(self.db, business["business_id"], 1)
        self.db.commit()

        self.assertEqual(run_result["status"], "ran")
        self.assertGreater(run_result["fuel_cost_xgp"], 0.0)
        self.assertGreater(run_result["labor_cost_xgp"], 0.0)

        ledger_rows = (
            self.db.query(BusinessLedgerEntry)
            .filter(BusinessLedgerEntry.business_id == uuid.UUID(business["business_id"]), BusinessLedgerEntry.day == 1)
            .all()
        )
        categories = {row.category for row in ledger_rows}
        self.assertIn("revenue", categories)
        self.assertIn("input_cost", categories)
        self.assertIn("labor_cost", categories)
        self.assertIn("overhead_cost", categories)
        self.assertIn("fuel_cost", categories)

    def test_running_same_business_day_twice_does_not_duplicate(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)
        self._buy_inventory(
            business["business_id"],
            [{"item_id": "apple", "quantity": 40}],
        )
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

    def test_no_inventory_blocks_business_operation_with_restock_message(self) -> None:
        self._create_business("fruit_shop", "suburban", 1)

        result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(action_key="operate_business", parameters={}),
            self.db,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["result"]["business_count_ran"], 0)
        self.assertEqual(result["result"]["blocked_business_count"], 1)
        self.assertEqual(result["result_summary"], "You need to buy inventory before operating.")
        self.assertEqual(result["cash_delta_xgp"], 0.0)

    def test_day_progression_includes_business_result(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)
        self._buy_inventory(
            business["business_id"],
            [{"item_id": "orange", "quantity": 25}],
        )

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
        business = self._create_business("food_truck", "suburban", 1)
        self._buy_inventory(
            business["business_id"],
            [
                {"item_id": "bread", "quantity": 20},
                {"item_id": "beef", "quantity": 10},
                {"item_id": "cooking_oil", "quantity": 8},
            ],
        )
        cash_before = float(self.player.cash_xgp)

        run_player_businesses_for_day(self.db, str(self.player.id), 1, commit=True)
        self.db.refresh(self.player)

        cash_after = float(self.player.cash_xgp)
        self.assertNotEqual(cash_before, cash_after)

    def test_gameplay_execute_supports_operate_business_action_key(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)
        self._buy_inventory(
            business["business_id"],
            [{"item_id": "grape", "quantity": 28}],
        )

        result = execute_gameplay_action(
            str(self.player.id),
            GameplayActionRequest(action_key="operate_business", parameters={}),
            self.db,
        )
        self.db.refresh(self.player)

        self.assertTrue(result["success"])
        self.assertEqual(result["action_key"], "operate_business")
        self.assertEqual(result["time_cost_units"], 2.0)
        self.assertIn("Business operation completed", result["result_summary"])
        self.assertEqual(result["result"]["business_count_ran"], 1)
        self.assertEqual(result["cash_delta_xgp"], result["result"]["cash_delta_business_net_xgp"])
        self.assertEqual(result["updated_state"]["player_state"]["cash"], round(float(self.player.cash_xgp), 2))

        log_count = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.player_id == self.player.id, BusinessDailyLog.day == 1)
            .count()
        )
        self.assertEqual(log_count, 1)

    def test_restock_warning_appears_when_inventory_is_low(self) -> None:
        business = self._create_business("fruit_shop", "suburban", 1)
        self._buy_inventory(
            business["business_id"],
            [{"item_id": "strawberry", "quantity": 4}],
        )

        run_result = run_business_day(self.db, business["business_id"], 1)

        self.assertIn(run_result["restock_warning"], {
            "Urgent: restock before next business day",
            "Low inventory: restock soon",
            "Business cannot operate normally without inventory",
        })
        self.assertLessEqual(float(run_result["estimated_days_of_stock_left"] or 0), 3.0)

    def test_business_can_lose_money_on_bad_day(self) -> None:
        business = self._create_business("food_truck", "rural", 1)
        self._buy_inventory(
            business["business_id"],
            [
                {"item_id": "bread", "quantity": 18},
                {"item_id": "rice", "quantity": 12},
                {"item_id": "beef", "quantity": 10},
                {"item_id": "egg", "quantity": 8},
                {"item_id": "cooking_oil", "quantity": 6},
            ],
        )

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
        self.assertGreaterEqual(run_result["labor_cost_xgp"], 65.0)


if __name__ == "__main__":
    unittest.main()
