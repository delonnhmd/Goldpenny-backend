import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_housing_region_integration.db")

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
from app.services.housing_region_service import (
    assign_player_housing,
    compute_housing_effects_for_day,
    get_business_region_demand_modifier,
    get_job_region_opportunity_modifier,
    get_side_income_region_modifier,
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


class HousingRegionIntegrationTests(unittest.TestCase):
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

        self.player_suburban = self._seed_player("suburban")
        self.player_downtown = self._seed_player("downtown")
        self._seed_macro_and_prices()
        self._seed_employment(self.player_suburban.id)
        self._seed_employment(self.player_downtown.id)
        self._seed_day_state(self.player_suburban.id, worked_hours=8, side_income_hours=Decimal("2.0"))
        self._seed_day_state(self.player_downtown.id, worked_hours=8, side_income_hours=Decimal("2.0"))

        # Give one player an active business so downstream settlement/day summaries include business context.
        biz_payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player_downtown.id),
            business_type="fruit_shop",
            region_key="downtown",
        )
        biz = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.id == uuid.UUID(biz_payload["business_id"]))
            .first()
        )
        biz.inventory_produce_units = Decimal("120.0")
        biz.reputation = 65

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player(self, region: str) -> Player:
        user = User(email=f"housing-int-{region}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=f"Integration {region}",
            cash=Decimal("3500.00"),
            debt_xgp=Decimal("600.00"),
            stress=24,
            health=92,
            hours_available=16,
            region=region,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_macro_and_prices(self) -> None:
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.4"),
                interest_rate=Decimal("4.2"),
                unemployment_rate=Decimal("5.6"),
                oil_index=Decimal("112.0"),
                consumer_confidence=Decimal("51.0"),
                supply_chain_stress=Decimal("0.7"),
                event_headline="Integration baseline",
                event_summary="Baseline for region integration tests.",
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

    def _seed_employment(self, player_id) -> None:
        self.db.add(
            PlayerEmploymentState(
                player_id=player_id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("5100.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

    def _seed_day_state(self, player_id, *, worked_hours: int, side_income_hours: Decimal) -> None:
        self.db.add(
            PlayerDailyState(
                player_id=player_id,
                day_number=1,
                hours_available_start=16,
                hours_available_end=max(0, 16 - worked_hours - int(side_income_hours)),
                worked_main_job=worked_hours > 0,
                worked_hours=worked_hours,
                side_income_hours=side_income_hours,
                did_settlement=False,
                stress_start=24,
                stress_end=24,
                health_start=92,
                health_end=92,
                cash_start=Decimal("3500.0000"),
                cash_end=Decimal("3500.0000"),
            )
        )

    def test_suburban_vs_downtown_effects_and_bounds(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        assign_player_housing(self.db, str(self.player_downtown.id), "downtown")

        suburban = compute_housing_effects_for_day(self.db, str(self.player_suburban.id), 1)
        downtown = compute_housing_effects_for_day(self.db, str(self.player_downtown.id), 1)
        self.db.commit()

        self.assertLess(suburban["housing_cost_daily_xgp"], downtown["housing_cost_daily_xgp"])
        self.assertGreater(suburban["commute_hours"], downtown["commute_hours"])
        self.assertGreater(downtown["region_stress_delta"], suburban["region_stress_delta"])

        for row in [suburban, downtown]:
            self.assertGreaterEqual(float(row["region_opportunity_modifier"]), -0.15)
            self.assertLessEqual(float(row["region_opportunity_modifier"]), 0.15)
            self.assertGreaterEqual(float(row["region_business_demand_modifier"]), -0.15)
            self.assertLessEqual(float(row["region_business_demand_modifier"]), 0.20)
            self.assertGreaterEqual(float(row["region_side_income_modifier"]), -0.10)
            self.assertLessEqual(float(row["region_side_income_modifier"]), 0.15)

    def test_region_modifiers_flow_to_job_business_and_side_income(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        sub_job = get_job_region_opportunity_modifier(self.db, str(self.player_suburban.id))
        sub_food = get_business_region_demand_modifier(self.db, str(self.player_suburban.id), "food_truck")
        sub_side = get_side_income_region_modifier(self.db, str(self.player_suburban.id))

        assign_player_housing(self.db, str(self.player_suburban.id), "downtown")
        down_job = get_job_region_opportunity_modifier(self.db, str(self.player_suburban.id))
        down_food = get_business_region_demand_modifier(self.db, str(self.player_suburban.id), "food_truck")
        down_side = get_side_income_region_modifier(self.db, str(self.player_suburban.id))

        self.assertGreater(float(down_job), float(sub_job))
        self.assertGreater(float(down_food), float(sub_food))
        self.assertGreater(float(down_side), float(sub_side))

    def test_settlement_includes_housing_and_commute_costs_and_life_time_budget(self) -> None:
        assign_player_housing(self.db, str(self.player_downtown.id), "downtown")
        result = settle_player_day(self.db, str(self.player_downtown.id))

        self.assertIn("housing_cost_daily_xgp", result)
        self.assertIn("utilities_cost_daily_xgp", result)
        self.assertIn("commute_fuel_cost_xgp", result)
        self.assertIn("region_stress_delta", result)
        self.assertIn("region_side_income_modifier", result)
        self.assertGreaterEqual(float(result["commute_hours"]), 0.0)
        self.assertGreaterEqual(float(result["commute_fuel_cost_xgp"]), 0.0)

        pds = (
            self.db.query(PlayerDailyState)
            .filter(PlayerDailyState.player_id == self.player_downtown.id, PlayerDailyState.day_number == 1)
            .first()
        )
        self.assertIsNotNone(pds)
        self.assertGreaterEqual(float(pds.commute_hours or 0), 0.0)
        self.assertGreaterEqual(float(pds.total_hours_used or 0), float(pds.commute_hours or 0))

        log = (
            self.db.query(DailySettlementLog)
            .filter(DailySettlementLog.player_id == self.player_downtown.id, DailySettlementLog.day_number == 1)
            .first()
        )
        self.assertIsNotNone(log)
        self.assertGreaterEqual(float(log.housing_cost_daily_xgp or 0), 0.0)
        self.assertGreaterEqual(float(log.utilities_cost_daily_xgp or 0), 0.0)
        self.assertGreaterEqual(float(log.commute_fuel_cost_xgp or 0), 0.0)

    def test_day_run_exposes_housing_region_summary(self) -> None:
        assign_player_housing(self.db, str(self.player_downtown.id), "downtown")
        result = run_player_next_day(self.db, str(self.player_downtown.id))

        self.assertIn("housing_region_summary", result)
        self.assertIn("region_key", result)
        self.assertIn("housing_cost_daily_xgp", result)
        self.assertIn("utilities_cost_daily_xgp", result)
        self.assertIn("commute_hours", result)
        self.assertIn("commute_fuel_cost_xgp", result)
        self.assertIn("region_business_demand_modifier", result)
        self.assertIn("region_side_income_modifier", result)
        self.assertIn("networking_modifier", result)


if __name__ == "__main__":
    unittest.main()
