import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_business_day_progression.db")

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


class BusinessDayProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
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

        user = User(email=f"biz-day-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Business Day Player",
            cash=Decimal("5000.00"),
            debt_xgp=Decimal("100.00"),
            stress=18,
            health=95,
            hours_available=16,
            region="suburban",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.2"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.2"),
                oil_index=Decimal("102.0"),
                consumer_confidence=Decimal("55.0"),
                supply_chain_stress=Decimal("0.6"),
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
            BasketType.produce: Decimal("8.0000"),
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
                player_id=self.player.id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("5100.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        business_payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player.id),
            business_type="fruit_shop",
            region_key="suburban",
        )
        business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.id == uuid.UUID(business_payload["business_id"]))
            .first()
        )
        business.inventory_produce_units = Decimal("150.0")
        business.reputation = 70

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_day_run_includes_step15_business_summary_fields(self) -> None:
        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("business_summary", result)
        self.assertIn("fruit_shop_result", result)
        self.assertIn("food_truck_result", result)
        self.assertIn("side_income_result", result)
        self.assertIn("business_net_profit_xgp", result)
        self.assertIn("maintenance_cost_xgp", result)
        self.assertIn("spoilage_loss_xgp", result)

    def test_settlement_summary_includes_business_component_totals(self) -> None:
        result = settle_player_day(self.db, str(self.player.id))
        summary = result.get("summary_json", {})

        for key in [
            "business_revenue_xgp",
            "business_cogs_xgp",
            "business_overhead_xgp",
            "business_spoilage_loss_xgp",
            "business_fuel_cost_xgp",
            "business_maintenance_cost_xgp",
            "business_net_profit_xgp",
        ]:
            self.assertIn(key, summary)

    def test_net_worth_snapshot_reflects_business_effects(self) -> None:
        result = run_player_next_day(self.db, str(self.player.id))
        self.assertIn("business_value_xgp", result)
        self.assertGreaterEqual(float(result["business_value_xgp"]), 0.0)

        snapshots = (
            self.db.query(PlayerNetWorthSnapshot)
            .filter(PlayerNetWorthSnapshot.player_id == self.player.id)
            .all()
        )
        self.assertGreaterEqual(len(snapshots), 1)


if __name__ == "__main__":
    unittest.main()

