import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_business_service.db")

from app.db.database import Base
from app.engine.business_service import (
    create_or_get_starter_business,
    day_to_date,
    operate_food_truck,
    operate_fruit_shop,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.user import User


class BusinessServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
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
                PlayerDailyState.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(
            email=f"biz-service-{uuid.uuid4()}@example.com",
            hashed_password="hashed-password",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=str(user.id),
            display_name="Biz Service Test Player",
            cash=Decimal("20000.00"),
            stress=20,
            health=95,
            hours_available=16,
            region="suburban",
        )
        self.db.add(self.player)
        self.db.flush()

        self._seed_macro_and_prices()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_macro_and_prices(self) -> None:
        for day, oil, confidence, stress in [
            (1, Decimal("100.0"), Decimal("52.0"), Decimal("0.5")),
            (2, Decimal("120.0"), Decimal("52.0"), Decimal("0.5")),
            (3, Decimal("120.0"), Decimal("52.0"), Decimal("0.5")),
            (4, Decimal("160.0"), Decimal("45.0"), Decimal("3.5")),
        ]:
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.3"),
                    interest_rate=Decimal("4.2"),
                    unemployment_rate=Decimal("5.1"),
                    oil_index=oil,
                    consumer_confidence=confidence,
                    supply_chain_stress=stress,
                    event_headline="Test macro",
                    event_summary="Seeded for business tests.",
                )
            )

        price_rows = [
            (1, BasketType.produce, Decimal("8.0")),
            (1, BasketType.essentials, Decimal("10.0")),
            (1, BasketType.protein, Decimal("12.0")),
            (2, BasketType.produce, Decimal("14.0")),
            (2, BasketType.essentials, Decimal("14.0")),
            (2, BasketType.protein, Decimal("17.0")),
            (3, BasketType.produce, Decimal("8.0")),
            (3, BasketType.essentials, Decimal("10.0")),
            (3, BasketType.protein, Decimal("12.0")),
            (4, BasketType.produce, Decimal("12.0")),
            (4, BasketType.essentials, Decimal("16.0")),
            (4, BasketType.protein, Decimal("20.0")),
        ]
        for day, basket, price in price_rows:
            self.db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=basket,
                    price_index=price,
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )

    def _new_business(self, business_type: str, region: str = "suburban", reputation: int = 55) -> PlayerBusiness:
        (
            self.db.query(PlayerBusiness)
            .filter(
                PlayerBusiness.player_id == self.player.id,
                PlayerBusiness.business_id == business_type,
                PlayerBusiness.is_active.is_(True),
            )
            .update({"is_active": False}, synchronize_session=False)
        )
        self.db.flush()
        payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player.id),
            business_type=business_type,
            region_key=region,
        )
        business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.id == uuid.UUID(payload["business_id"]))
            .first()
        )
        business.reputation = reputation
        self.db.flush()
        return business

    def test_fruit_shop_higher_produce_basket_price_squeezes_margin(self) -> None:
        day1_shop = self._new_business("fruit_shop")
        day2_shop = self._new_business("fruit_shop")
        day1_shop.inventory_produce_units = Decimal("120")
        day2_shop.inventory_produce_units = Decimal("120")

        low_price_result = operate_fruit_shop(self.db, day1_shop, day_number=1, as_of_date=day_to_date(1), markup_pct=Decimal("0.20"))
        high_price_result = operate_fruit_shop(self.db, day2_shop, day_number=2, as_of_date=day_to_date(2), markup_pct=Decimal("0.20"))

        self.assertLess(high_price_result["net_profit_xgp"], low_price_result["net_profit_xgp"])

    def test_fruit_shop_excessive_markup_reduces_sold_units(self) -> None:
        low_markup_shop = self._new_business("fruit_shop")
        high_markup_shop = self._new_business("fruit_shop")
        low_markup_shop.inventory_produce_units = Decimal("150")
        high_markup_shop.inventory_produce_units = Decimal("150")

        low_markup = operate_fruit_shop(self.db, low_markup_shop, day_number=1, as_of_date=day_to_date(1), markup_pct=Decimal("0.10"))
        high_markup = operate_fruit_shop(self.db, high_markup_shop, day_number=1, as_of_date=day_to_date(1), markup_pct=Decimal("0.40"))

        self.assertLess(high_markup["units_sold"], low_markup["units_sold"])

    def test_fruit_shop_spoilage_removes_remaining_inventory(self) -> None:
        shop = self._new_business("fruit_shop", reputation=40)
        shop.inventory_produce_units = Decimal("60")
        result = operate_fruit_shop(self.db, shop, day_number=4, as_of_date=day_to_date(4), markup_pct=Decimal("0.38"))

        inventory_before = Decimal(str(result["inventory_before"]))
        inventory_after = Decimal(str(result["inventory_after"]))
        units_sold = Decimal(str(result["units_sold"]))
        without_spoilage = inventory_before - units_sold

        self.assertGreater(result["spoilage_loss_xgp"], 0.0)
        self.assertLess(inventory_after, without_spoilage)

    def test_fruit_shop_zero_inventory_logs_no_revenue_and_warning(self) -> None:
        shop = self._new_business("fruit_shop")

        result = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1))

        self.assertEqual(result["status"], "no_inventory")
        self.assertEqual(result["gross_revenue_xgp"], 0.0)
        self.assertEqual(result["actual_units_sold"], 0)
        self.assertEqual(result["restock_warning"], "No usable inventory. Buy stock before operating.")
        self.assertEqual(result["message"], "No usable inventory. Buy stock before operating.")
        log = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == shop.id, BusinessDailyLog.day == 1)
            .first()
        )
        self.assertIsNotNone(log)
        self.assertEqual(float(log.gross_revenue_xgp), 0.0)
        self.assertLess(float(log.net_profit_xgp), 0.0)

    def test_fruit_shop_sales_are_capped_by_produce_inventory(self) -> None:
        shop = self._new_business("fruit_shop")
        shop.inventory_produce_units = Decimal("5")

        result = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1), markup_pct=Decimal("0.20"))

        self.assertEqual(result["actual_units_sold"], 5)
        self.assertGreater(result["lost_sales_units"], 0)
        self.assertLess(float(shop.inventory_produce_units), 5.0)

    def test_fruit_shop_generic_spoilage_is_five_percent_after_sales(self) -> None:
        shop = self._new_business("fruit_shop")
        shop.inventory_produce_units = Decimal("100")

        result = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1), markup_pct=Decimal("0.20"))

        remaining_after_sales = Decimal(str(result["inventory_before"])) - Decimal(str(result["actual_units_sold"]))
        expected_spoilage = remaining_after_sales * Decimal("0.05")
        self.assertGreater(result["spoilage_units"], 0.0)
        self.assertAlmostEqual(result["spoilage_units"], float(expected_spoilage), places=2)
        self.assertLess(Decimal(str(result["inventory_after"])), remaining_after_sales)

    def test_fruit_shop_weekend_and_reputation_increase_demand(self) -> None:
        weekday_shop = self._new_business("fruit_shop", reputation=20)
        weekend_shop = self._new_business("fruit_shop", reputation=80)
        weekday_shop.inventory_produce_units = Decimal("160")
        weekend_shop.inventory_produce_units = Decimal("160")

        weekday_result = operate_fruit_shop(self.db, weekday_shop, day_number=2, as_of_date=day_to_date(2), markup_pct=Decimal("0.20"))
        weekend_result = operate_fruit_shop(self.db, weekend_shop, day_number=3, as_of_date=day_to_date(3), markup_pct=Decimal("0.20"))

        self.assertGreater(weekend_result["demand_signal"], weekday_result["demand_signal"])

    def test_fruit_shop_output_is_deterministic_for_same_inputs(self) -> None:
        # Run in two clean worlds with the same setup and compare outputs.
        def run_once() -> dict:
            local_engine = create_engine("sqlite:///:memory:", future=True)
            local_session = sessionmaker(autocommit=False, autoflush=False, bind=local_engine, future=True)
            Base.metadata.create_all(
                bind=local_engine,
                tables=[
                    User.__table__,
                    Player.__table__,
                    PlayerBusiness.__table__,
                    BusinessDailyLog.__table__,
                    BusinessLedgerEntry.__table__,
                    MacroDailyState.__table__,
                    BasketDailyPrice.__table__,
                    PlayerDailyState.__table__,
                ],
            )
            db = local_session()
            try:
                user = User(email=f"det-{uuid.uuid4()}@example.com", hashed_password="x")
                db.add(user)
                db.flush()
                player = Player(user_id=str(user.id), cash=Decimal("20000.00"), region="suburban", hours_available=16, stress=20, health=95)
                db.add(player)
                db.flush()
                db.add(
                    MacroDailyState(
                        day=1,
                        inflation_rate=Decimal("2.3"),
                        interest_rate=Decimal("4.2"),
                        unemployment_rate=Decimal("5.1"),
                        oil_index=Decimal("100.0"),
                        consumer_confidence=Decimal("52.0"),
                        supply_chain_stress=Decimal("0.5"),
                    )
                )
                db.add(BasketDailyPrice(day=1, basket_type=BasketType.produce, price_index=Decimal("8.0"), daily_change_pct=Decimal("0"), supply_pressure=Decimal("1"), demand_pressure=Decimal("1")))
                payload = create_or_get_starter_business(db=db, player_id=str(player.id), business_type="fruit_shop", region_key="suburban")
                business = db.query(PlayerBusiness).filter(PlayerBusiness.id == uuid.UUID(payload["business_id"])).first()
                business.inventory_produce_units = Decimal("150")
                business.reputation = 60
                db.flush()
                return operate_fruit_shop(db, business, day_number=1, as_of_date=day_to_date(1), markup_pct=Decimal("0.20"))
            finally:
                db.close()
                local_engine.dispose()

        one = run_once()
        two = run_once()
        self.assertEqual(one["units_sold"], two["units_sold"])
        self.assertEqual(one["revenue_xgp"], two["revenue_xgp"])
        self.assertEqual(one["cogs_xgp"], two["cogs_xgp"])
        self.assertEqual(one["net_profit_xgp"], two["net_profit_xgp"])

    def test_food_truck_higher_ingredients_reduce_profit(self) -> None:
        low_cost_truck = self._new_business("food_truck")
        high_cost_truck = self._new_business("food_truck")
        low_cost_truck.inventory_essentials_units = Decimal("120")
        low_cost_truck.inventory_protein_units = Decimal("120")
        high_cost_truck.inventory_essentials_units = Decimal("120")
        high_cost_truck.inventory_protein_units = Decimal("120")

        low_cost = operate_food_truck(self.db, low_cost_truck, day_number=1, as_of_date=day_to_date(1))
        high_cost = operate_food_truck(self.db, high_cost_truck, day_number=4, as_of_date=day_to_date(4))

        self.assertLess(high_cost["net_profit_xgp"], low_cost["net_profit_xgp"])

    def test_food_truck_higher_oil_increases_fuel_cost(self) -> None:
        low_oil_truck = self._new_business("food_truck")
        high_oil_truck = self._new_business("food_truck")
        low_oil_truck.inventory_essentials_units = Decimal("120")
        low_oil_truck.inventory_protein_units = Decimal("120")
        high_oil_truck.inventory_essentials_units = Decimal("120")
        high_oil_truck.inventory_protein_units = Decimal("120")

        low_oil = operate_food_truck(self.db, low_oil_truck, day_number=1, as_of_date=day_to_date(1))
        high_oil = operate_food_truck(self.db, high_oil_truck, day_number=4, as_of_date=day_to_date(4))

        self.assertGreater(high_oil["fuel_cost_xgp"], low_oil["fuel_cost_xgp"])

    def test_food_truck_weekend_and_region_traffic_affects_revenue(self) -> None:
        suburban_weekday = self._new_business("food_truck", region="suburban")
        downtown_weekend = self._new_business("food_truck", region="downtown")
        suburban_weekday.inventory_essentials_units = Decimal("140")
        suburban_weekday.inventory_protein_units = Decimal("140")
        downtown_weekend.inventory_essentials_units = Decimal("140")
        downtown_weekend.inventory_protein_units = Decimal("140")

        weekday_result = operate_food_truck(self.db, suburban_weekday, day_number=2, as_of_date=day_to_date(2))
        weekend_result = operate_food_truck(self.db, downtown_weekend, day_number=3, as_of_date=day_to_date(3))

        self.assertGreater(weekend_result["revenue_xgp"], weekday_result["revenue_xgp"])

    def test_food_truck_inventory_is_consumed_correctly(self) -> None:
        truck = self._new_business("food_truck")
        truck.inventory_essentials_units = Decimal("30")
        truck.inventory_protein_units = Decimal("20")
        before = truck.inventory_essentials_units + truck.inventory_protein_units

        result = operate_food_truck(self.db, truck, day_number=1, as_of_date=day_to_date(1))
        after = Decimal(str(result["inventory_after"]))

        self.assertLessEqual(after, before)
        self.assertGreaterEqual(after, Decimal("0"))

    def test_food_truck_sales_are_capped_by_min_essentials_and_protein(self) -> None:
        truck = self._new_business("food_truck")
        truck.inventory_essentials_units = Decimal("10")
        truck.inventory_protein_units = Decimal("3")

        result = operate_food_truck(self.db, truck, day_number=1, as_of_date=day_to_date(1))

        self.assertEqual(result["actual_units_sold"], 3)
        self.assertGreater(result["lost_sales_units"], 0)
        self.assertEqual(float(truck.inventory_essentials_units), 7.0)
        self.assertEqual(float(truck.inventory_protein_units), 0.0)

    def test_business_operation_includes_labor_and_applies_net_profit_to_cash(self) -> None:
        shop = self._new_business("fruit_shop")
        shop.inventory_produce_units = Decimal("90")
        cash_before = Decimal(str(self.player.cash_xgp))

        result = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1))

        self.assertEqual(result["labor_cost_xgp"], 45.0)
        self.assertEqual(
            Decimal(str(self.player.cash_xgp)).quantize(Decimal("0.01")),
            (cash_before + Decimal(str(result["net_profit_xgp"]))).quantize(Decimal("0.01")),
        )

    def test_low_inventory_warning_appears_after_operation(self) -> None:
        shop = self._new_business("fruit_shop")
        shop.inventory_produce_units = Decimal("50")

        result = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1))

        self.assertIn(
            result["restock_warning"],
            {
                "Urgent: restock before next business day.",
                "Low inventory: restock soon.",
                "No usable inventory. Buy stock before operating.",
            },
        )
        self.assertLessEqual(result["days_of_stock_left"], 3.0)

    def test_business_operation_same_day_is_idempotent(self) -> None:
        shop = self._new_business("fruit_shop")
        shop.inventory_produce_units = Decimal("90")

        first = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1))
        cash_after_first = Decimal(str(self.player.cash_xgp))
        second = operate_fruit_shop(self.db, shop, day_number=1, as_of_date=day_to_date(1))
        cash_after_second = Decimal(str(self.player.cash_xgp))

        log_count = (
            self.db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == shop.id, BusinessDailyLog.day == 1)
            .count()
        )
        self.assertEqual(first["status"], "ran")
        self.assertEqual(second["status"], "already_processed")
        self.assertEqual(first["net_profit_xgp"], second["net_profit_xgp"])
        self.assertEqual(cash_after_first, cash_after_second)
        self.assertEqual(log_count, 1)

    def test_food_truck_output_is_deterministic_for_same_inputs(self) -> None:
        def run_once() -> dict:
            local_engine = create_engine("sqlite:///:memory:", future=True)
            local_session = sessionmaker(autocommit=False, autoflush=False, bind=local_engine, future=True)
            Base.metadata.create_all(
                bind=local_engine,
                tables=[
                    User.__table__,
                    Player.__table__,
                    PlayerBusiness.__table__,
                    BusinessDailyLog.__table__,
                    BusinessLedgerEntry.__table__,
                    MacroDailyState.__table__,
                    BasketDailyPrice.__table__,
                    PlayerDailyState.__table__,
                ],
            )
            db = local_session()
            try:
                user = User(email=f"det-truck-{uuid.uuid4()}@example.com", hashed_password="x")
                db.add(user)
                db.flush()
                player = Player(user_id=str(user.id), cash=Decimal("20000.00"), region="suburban", hours_available=16, stress=20, health=95)
                db.add(player)
                db.flush()
                db.add(
                    MacroDailyState(
                        day=1,
                        inflation_rate=Decimal("2.3"),
                        interest_rate=Decimal("4.2"),
                        unemployment_rate=Decimal("5.1"),
                        oil_index=Decimal("100.0"),
                        consumer_confidence=Decimal("52.0"),
                        supply_chain_stress=Decimal("0.5"),
                    )
                )
                db.add(BasketDailyPrice(day=1, basket_type=BasketType.essentials, price_index=Decimal("10.0"), daily_change_pct=Decimal("0"), supply_pressure=Decimal("1"), demand_pressure=Decimal("1")))
                db.add(BasketDailyPrice(day=1, basket_type=BasketType.protein, price_index=Decimal("12.0"), daily_change_pct=Decimal("0"), supply_pressure=Decimal("1"), demand_pressure=Decimal("1")))
                payload = create_or_get_starter_business(db=db, player_id=str(player.id), business_type="food_truck", region_key="suburban")
                business = db.query(PlayerBusiness).filter(PlayerBusiness.id == uuid.UUID(payload["business_id"])).first()
                business.inventory_essentials_units = Decimal("120")
                business.inventory_protein_units = Decimal("120")
                business.reputation = 60
                db.flush()
                return operate_food_truck(db, business, day_number=1, as_of_date=day_to_date(1))
            finally:
                db.close()
                local_engine.dispose()

        one = run_once()
        two = run_once()
        self.assertEqual(one["units_sold"], two["units_sold"])
        self.assertEqual(one["fuel_cost_xgp"], two["fuel_cost_xgp"])
        self.assertEqual(one["net_profit_xgp"], two["net_profit_xgp"])


if __name__ == "__main__":
    unittest.main()
