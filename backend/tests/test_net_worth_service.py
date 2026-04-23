import os
import unittest
import uuid
import json
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_net_worth_service.db")

from app.api.portfolio import (
    compute_player_snapshot_route,
    get_latest_player_snapshot_route,
    get_player_allocation_route,
    get_player_snapshot_history_route,
)
from app.db.database import Base
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.gameplay_transaction import GameplayTransaction
from app.models.game_state import GameState
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
from app.services.net_worth_service import (
    compute_player_net_worth_snapshot,
    get_player_net_worth_history,
)

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


class NetWorthServiceTests(unittest.TestCase):
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
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                DebtCreditLog.__table__,
                PlayerEmploymentState.__table__,
                JobDefinitionDB.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                GameplayTransaction.__table__,
                GameState.__table__,
                StockDailyPrice.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                PlayerHousingState.__table__,
                PlayerStockHolding.__table__,
                PlayerTransactionLog.__table__,
                HousingDailyLog.__table__,
                PlayerNetWorthSnapshot.__table__,
            ],
        )

        self.db = self.SessionLocal()
        self._seed_player_world()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player_world(self) -> None:
        user = User(
            email=f"net-worth-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=str(user.id),
            display_name="Net Worth Test Player",
            cash=Decimal("1000.00"),
            bank_savings_xgp=Decimal("200.00"),
            debt_xgp=Decimal("300.00"),
            credit_score=650,
            net_worth_xgp=Decimal("900.00"),
            stress=22,
            health=92,
            hours_available=16,
            region="downtown",
            main_job="banker",
        )
        self.db.add(player)
        self.db.flush()
        self.player = player

        self.db.add(
            JobDefinitionDB(
                job_code="banker",
                title="Banker",
                base_monthly_pay_xgp=Decimal("5100.00"),
                stability_pct=Decimal("0.82"),
                growth_pct=Decimal("0.75"),
                stress_pct=Decimal("0.65"),
                promotion_threshold=100,
            )
        )

        self.db.add(
            PlayerEmploymentState(
                player_id=player.id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("5100.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
                job_status="employed",
            )
        )

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.3000"),
                interest_rate=Decimal("4.2000"),
                unemployment_rate=Decimal("5.1000"),
                oil_index=Decimal("101.0000"),
                consumer_confidence=Decimal("53.0000"),
                supply_chain_stress=Decimal("0.6000"),
                event_headline="Baseline day",
                event_summary="Seeded baseline for tests.",
            )
        )
        self.db.add(
            GameState(
                current_day=1,
                day_status="open",
            )
        )

        for basket_type, price in {
            BasketType.essentials: Decimal("10.0000"),
            BasketType.protein: Decimal("12.0000"),
            BasketType.produce: Decimal("9.0000"),
            BasketType.convenience: Decimal("8.0000"),
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
            PlayerStockHolding(
                player_id=player.id,
                stock_id="GPTECH",
                shares_owned=10,
                average_cost_basis=Decimal("48.0000"),
                total_cost_basis=Decimal("480.0000"),
            )
        )

        business_id = uuid.uuid4()
        self.db.add(
            PlayerBusiness(
                id=business_id,
                player_id=player.id,
                business_id="food_truck",
                region="downtown",
                business_level=1,
                reputation=52,
                cash_reserve_xgp=Decimal("150.00"),
                cash_invested_xgp=Decimal("1200.00"),
                inventory_essentials_units=Decimal("12.0000"),
                inventory_protein_units=Decimal("8.0000"),
                inventory_items_json=json.dumps({
                    "bread": {
                        "quantity": 12,
                        "avg_unit_cost": 0.48,
                        "retail_price": 1.20,
                        "suggested_retail_price": 1.20,
                        "spoilage_rate": 0.05,
                        "demand_weight": 1.0,
                        "basket_link": "essentials",
                        "unit_label": "pack",
                        "economy_sensitivity": 0.8,
                    },
                    "chicken": {
                        "quantity": 8,
                        "avg_unit_cost": 1.35,
                        "retail_price": 3.00,
                        "suggested_retail_price": 3.00,
                        "spoilage_rate": 0.07,
                        "demand_weight": 1.12,
                        "basket_link": "protein",
                        "unit_label": "tray",
                        "economy_sensitivity": 1.08,
                    },
                    "cooking_oil": {
                        "quantity": 5,
                        "avg_unit_cost": 0.82,
                        "retail_price": 1.60,
                        "suggested_retail_price": 1.60,
                        "spoilage_rate": 0.02,
                        "demand_weight": 0.72,
                        "basket_link": "convenience",
                        "unit_label": "bottle",
                        "economy_sensitivity": 1.12,
                    },
                }),
                created_day=1,
                is_active=True,
            )
        )
        self.db.add(
            BusinessDailyLog(
                business_id=business_id,
                player_id=player.id,
                day=1,
                gross_revenue_xgp=Decimal("88.0000"),
                input_cost_xgp=Decimal("51.0000"),
                fuel_cost_xgp=Decimal("9.0000"),
                spoilage_cost_xgp=Decimal("1.0000"),
                overhead_cost_xgp=Decimal("16.0000"),
                net_profit_xgp=Decimal("11.0000"),
                demand_score=Decimal("1.0100"),
                utilization_pct=Decimal("0.8400"),
            )
        )

    def test_snapshot_creation_for_player(self) -> None:
        snapshot = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)
        self.assertEqual(snapshot["day"], 1)
        self.assertGreater(snapshot["total_assets_xgp"], 0.0)

        count = (
            self.db.query(PlayerNetWorthSnapshot)
            .filter(PlayerNetWorthSnapshot.player_id == self.player.id, PlayerNetWorthSnapshot.day == 1)
            .count()
        )
        self.assertEqual(count, 1)

    def test_stock_holdings_affect_stock_market_value_xgp(self) -> None:
        snapshot = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)
        self.assertAlmostEqual(snapshot["stock_market_value_xgp"], 500.00, places=2)

    def test_debt_reduces_net_worth(self) -> None:
        snapshot = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)
        self.assertAlmostEqual(
            snapshot["net_worth_xgp"],
            snapshot["total_assets_xgp"] - snapshot["debt_xgp"],
            places=2,
        )

    def test_business_value_contributes_when_business_logs_exist(self) -> None:
        snapshot = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)
        self.assertGreater(snapshot["business_value_xgp"], 0.0)
        self.assertGreater(snapshot["inventory_value_xgp"], 0.0)
        self.assertAlmostEqual(
            snapshot["total_assets_xgp"],
            snapshot["cash_xgp"]
            + snapshot["bank_savings_xgp"]
            + snapshot["stock_market_value_xgp"]
            + snapshot["business_value_xgp"]
            + snapshot["inventory_value_xgp"],
            places=2,
        )

    def test_rerun_same_player_day_does_not_duplicate_snapshot(self) -> None:
        first = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)
        second = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)

        count = (
            self.db.query(PlayerNetWorthSnapshot)
            .filter(PlayerNetWorthSnapshot.player_id == self.player.id, PlayerNetWorthSnapshot.day == 1)
            .count()
        )
        self.assertEqual(count, 1)
        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])

    def test_history_returns_ordered_snapshots(self) -> None:
        compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)

        self.db.add(
            StockDailyPrice(
                day=2,
                ticker="GPTECH",
                sector="technology",
                open_price=Decimal("50.0000"),
                close_price=Decimal("55.0000"),
                daily_change_pct=Decimal("10.0000"),
                macro_impact=Decimal("1.0000"),
                noise_component=Decimal("0.0000"),
            )
        )
        self.player.cash_xgp = Decimal("1030.00")
        self.db.commit()

        compute_player_net_worth_snapshot(self.db, str(self.player.id), day=2)

        history = get_player_net_worth_history(self.db, str(self.player.id), limit=30)
        self.assertEqual(history["count"], 2)
        self.assertEqual(history["snapshots"][0]["day"], 2)
        self.assertEqual(history["snapshots"][1]["day"], 1)

    def test_day_run_and_portfolio_routes_include_snapshot_fields(self) -> None:
        computed_snapshot = compute_player_net_worth_snapshot(self.db, str(self.player.id), day=1)
        self.assertIn("net_worth_xgp", computed_snapshot)
        self.assertIn("total_assets_xgp", computed_snapshot)
        self.assertIn("stock_market_value_xgp", computed_snapshot)
        self.assertIn("business_value_xgp", computed_snapshot)
        self.assertIn("inventory_value_xgp", computed_snapshot)
        self.assertIn("debt_xgp", computed_snapshot)
        self.assertIn("allocation_json", computed_snapshot)

        computed = compute_player_snapshot_route(player_id=str(self.player.id), day=None, db=self.db)
        self.assertEqual(computed.player_id, str(self.player.id))
        self.assertGreater(computed.inventory_value_xgp, 0.0)

        latest = get_latest_player_snapshot_route(player_id=str(self.player.id), db=self.db)
        self.assertEqual(latest.player_id, str(self.player.id))
        self.assertGreater(latest.inventory_value_xgp, 0.0)

        history = get_player_snapshot_history_route(player_id=str(self.player.id), limit=30, db=self.db)
        self.assertGreaterEqual(history.count, 1)
        self.assertEqual(history.snapshots[0].day, latest.day)

        allocation = get_player_allocation_route(player_id=str(self.player.id), db=self.db)
        self.assertIn("cash", allocation.allocation_json)
        self.assertIn("savings", allocation.allocation_json)
        self.assertIn("stocks", allocation.allocation_json)
        self.assertIn("business", allocation.allocation_json)
        self.assertIn("inventory", allocation.allocation_json)
        self.assertIn("debt", allocation.allocation_json)
        self.assertIn("net_worth", allocation.allocation_json)


if __name__ == "__main__":
    unittest.main()
