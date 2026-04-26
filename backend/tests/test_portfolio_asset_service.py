import json
import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "postgresql://tester:tester@localhost:5432/goldpenny_test")

from app.api.portfolio import get_player_portfolio_summary_route
from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.enums import BasketType
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.portfolio_asset_service import (
    build_deterministic_slot_address,
    calculate_inventory_value_for_business,
    estimate_business_value,
    estimate_land_current_value,
    get_player_portfolio_asset_summary,
)


class PortfolioAssetServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
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
                BasketDailyPrice.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                PlayerStockHolding.__table__,
                StockDailyPrice.__table__,
            ],
        )

        self.db = self.SessionLocal()
        self._seed_world()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_world(self) -> None:
        user = User(
            email=f"portfolio-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=str(user.id),
            display_name="Portfolio Test Player",
            cash=Decimal("1200.00"),
            debt_xgp=Decimal("500.00"),
            credit_score=640,
            health=90,
            stress=20,
            hours_available=16,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        for basket_type, price in {
            BasketType.produce: Decimal("110.0000"),
            BasketType.essentials: Decimal("120.0000"),
            BasketType.protein: Decimal("90.0000"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=14,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )

        self.fruit_business = PlayerBusiness(
            id=uuid.uuid4(),
            player_id=self.player.id,
            business_id="fruit_shop",
            region="downtown",
            reputation=24,
            cash_invested_xgp=Decimal("500.00"),
            inventory_items_json=json.dumps({
                "mango": {
                    "quantity": 10,
                    "avg_unit_cost": 1.25,
                },
                "orange": {
                    "quantity": 5,
                    "avg_unit_cost": 0.80,
                },
            }),
            created_day=1,
            is_active=True,
            last_operated_day=14,
        )
        self.generic_business = PlayerBusiness(
            id=uuid.uuid4(),
            player_id=self.player.id,
            business_id="food_truck",
            region="industrial",
            reputation=10,
            cash_invested_xgp=Decimal("1200.00"),
            inventory_produce_units=Decimal("10.0000"),
            inventory_essentials_units=Decimal("8.0000"),
            inventory_protein_units=Decimal("4.0000"),
            created_day=2,
            is_active=True,
            last_operated_day=14,
        )
        self.db.add_all([self.fruit_business, self.generic_business])
        self.db.flush()

        fruit_profits = [Decimal("20.00"), Decimal("15.00"), Decimal("10.00")]
        for offset, profit in enumerate(fruit_profits):
            self.db.add(
                BusinessDailyLog(
                    business_id=self.fruit_business.id,
                    player_id=self.player.id,
                    day=14 - offset,
                    gross_revenue_xgp=Decimal("80.0000"),
                    input_cost_xgp=Decimal("30.0000"),
                    labor_cost_xgp=Decimal("45.0000"),
                    fuel_cost_xgp=Decimal("0.0000"),
                    maintenance_cost_xgp=Decimal("0.0000"),
                    spoilage_cost_xgp=Decimal("0.0000"),
                    overhead_cost_xgp=Decimal("8.0000"),
                    net_profit_xgp=profit,
                    units_sold=20,
                    inventory_start_units=Decimal("20.0000"),
                    inventory_end_units=Decimal("10.0000"),
                    demand_signal=Decimal("1.0000"),
                    demand_score=Decimal("1.0000"),
                    utilization_pct=Decimal("0.8000"),
                    reputation_before=24,
                    reputation_after=24,
                )
            )

        negative_profits = [Decimal("-30.00"), Decimal("-20.00"), Decimal("-10.00")]
        for offset, profit in enumerate(negative_profits):
            self.db.add(
                BusinessDailyLog(
                    business_id=self.generic_business.id,
                    player_id=self.player.id,
                    day=14 - offset,
                    gross_revenue_xgp=Decimal("90.0000"),
                    input_cost_xgp=Decimal("55.0000"),
                    labor_cost_xgp=Decimal("65.0000"),
                    fuel_cost_xgp=Decimal("5.5000"),
                    maintenance_cost_xgp=Decimal("0.0000"),
                    spoilage_cost_xgp=Decimal("0.0000"),
                    overhead_cost_xgp=Decimal("14.0000"),
                    net_profit_xgp=profit,
                    units_sold=18,
                    inventory_start_units=Decimal("25.0000"),
                    inventory_end_units=Decimal("12.0000"),
                    demand_signal=Decimal("1.0000"),
                    demand_score=Decimal("1.0000"),
                    utilization_pct=Decimal("0.7000"),
                    reputation_before=10,
                    reputation_after=10,
                )
            )

        self.db.add(
            PlayerStockHolding(
                player_id=self.player.id,
                stock_id="GPTECH",
                shares_owned=5,
                average_cost_basis=Decimal("20.0000"),
                total_cost_basis=Decimal("100.0000"),
            )
        )
        self.db.add(
            StockDailyPrice(
                day=14,
                ticker="GPTECH",
                sector="technology",
                open_price=Decimal("22.0000"),
                close_price=Decimal("24.0000"),
                daily_change_pct=Decimal("1.5000"),
                macro_impact=Decimal("0.0000"),
                noise_component=Decimal("0.0000"),
            )
        )

    def test_inventory_value_from_itemized_inventory(self) -> None:
        value = calculate_inventory_value_for_business(self.db, self.fruit_business, day=14)
        self.assertEqual(value, Decimal("16.50"))

    def test_inventory_value_fallback_from_generic_inventory(self) -> None:
        value = calculate_inventory_value_for_business(self.db, self.generic_business, day=14)
        self.assertEqual(value, Decimal("26.32"))

    def test_business_value_includes_startup_cost(self) -> None:
        value = estimate_business_value(self.db, self.fruit_business, day=14)
        self.assertGreaterEqual(value, Decimal("300.00"))

    def test_business_value_includes_avg_7_day_profit_multiplier(self) -> None:
        value = estimate_business_value(self.db, self.fruit_business, day=14)
        expected_minimum = Decimal("300.00") + Decimal("16.50") + Decimal("120.00") + Decimal("300.00")
        self.assertEqual(value, expected_minimum)

    def test_business_value_includes_reputation_bonus(self) -> None:
        value = estimate_business_value(self.db, self.fruit_business, day=14)
        self.assertEqual(
            value - Decimal("300.00") - Decimal("16.50") - Decimal("300.00"),
            Decimal("120.00"),
        )

    def test_negative_profit_does_not_drop_below_safe_floor(self) -> None:
        inventory_value = calculate_inventory_value_for_business(self.db, self.generic_business, day=14)
        value = estimate_business_value(self.db, self.generic_business, day=14)
        safe_floor = Decimal("600.00") + (inventory_value * Decimal("0.50"))
        self.assertGreaterEqual(value, safe_floor)

    def test_land_current_value_formula_clamps_correctly(self) -> None:
        self.assertEqual(
            estimate_land_current_value(Decimal("1000.00"), Decimal("200.00"), "downtown"),
            Decimal("1750.00"),
        )
        self.assertEqual(
            estimate_land_current_value(Decimal("1000.00"), Decimal("-100.00"), "suburban"),
            Decimal("750.00"),
        )

    def test_portfolio_total_assets_formula_is_correct(self) -> None:
        payload = get_player_portfolio_asset_summary(self.db, str(self.player.id))
        expected = (
            Decimal("1200.00")
            + Decimal("120.00")
            + Decimal(str(payload["business_value"]))
            + Decimal(str(payload["inventory_value"]))
        )
        self.assertEqual(Decimal(str(payload["total_assets"])), expected)

    def test_net_worth_subtracts_debt(self) -> None:
        payload = get_player_portfolio_asset_summary(self.db, str(self.player.id))
        self.assertEqual(
            Decimal(str(payload["net_worth"])),
            Decimal(str(payload["total_assets"])) - Decimal(str(payload["debt"])),
        )

    def test_portfolio_endpoint_does_not_crash_when_stocks_are_missing(self) -> None:
        self.db.query(PlayerStockHolding).delete()
        self.db.query(StockDailyPrice).delete()
        self.db.commit()

        response = get_player_portfolio_summary_route(player_id=str(self.player.id), db=self.db)
        self.assertEqual(response.player_id, str(self.player.id))
        self.assertEqual(response.stock_holdings_value, 0.0)

    def test_owned_slot_address_is_deterministic(self) -> None:
        first = build_deterministic_slot_address("downtown:3:4", "downtown")
        second = build_deterministic_slot_address("downtown:3:4", "downtown")
        self.assertEqual(first, second)
        self.assertIn(first, {
            "1203 Market Line Ave",
            "88 Riverfront Plaza",
            "410 Central Trade St",
            "726 Commerce Row",
            "51 Skyline Market Blvd",
        })


if __name__ == "__main__":
    unittest.main()
