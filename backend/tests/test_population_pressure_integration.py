import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_population_pressure_integration.db")

from app.db.database import Base
from app.engine.business_service import create_or_get_starter_business, day_to_date, operate_food_truck
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
from app.models.region_population_history import RegionPopulationHistory
from app.models.region_population_state import RegionPopulationState
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.admin_debug_service import get_full_player_debug_snapshot
from app.services.day_progression_service import run_player_next_day
from app.services.housing_region_service import assign_player_housing


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


class PopulationPressureIntegrationTests(unittest.TestCase):
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
                RegionPopulationState.__table__,
                RegionPopulationHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player(self, region: str) -> Player:
        user = User(email=f"step34-int-{region}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=f"Step34 Int {region}",
            cash=Decimal("2500.00"),
            debt_xgp=Decimal("300.00"),
            stress=25,
            health=92,
            hours_available=16,
            region=region,
        )
        self.db.add(player)
        self.db.flush()
        self.db.add(
            PlayerEmploymentState(
                player_id=player.id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("4800.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )
        self.db.add(
            PlayerDailyState(
                player_id=player.id,
                day_number=1,
                hours_available_start=16,
                hours_available_end=8,
                worked_main_job=True,
                worked_hours=8,
                side_income_hours=Decimal("2.0"),
                did_settlement=False,
                stress_start=25,
                stress_end=25,
                health_start=92,
                health_end=92,
                cash_start=Decimal("2500.0000"),
                cash_end=Decimal("2500.0000"),
            )
        )
        return player

    def _seed(self) -> None:
        self.player_suburban = self._seed_player("suburban")
        self.player_downtown = self._seed_player("downtown")

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.5"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.2"),
                oil_index=Decimal("110.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.85"),
                event_headline="Step34 integration baseline",
                event_summary="Baseline for integration test.",
            )
        )
        self.db.add(
            JobDefinitionDB(
                job_code="banker",
                title="Banker",
                base_monthly_pay_xgp=Decimal("4800.00"),
                stability_pct=Decimal("0.82"),
                growth_pct=Decimal("0.72"),
                stress_pct=Decimal("0.66"),
                promotion_threshold=100,
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

        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        assign_player_housing(self.db, str(self.player_downtown.id), "downtown")

    def test_day_run_exposes_population_pressure_chain(self) -> None:
        result = run_player_next_day(self.db, str(self.player_downtown.id))
        self.assertIn("population_pressure_summary", result)
        self.assertIn("population_region_heat", result)
        self.assertIn("population_competition_state", result)
        self.assertIn("population_response_summary", result)

        response = result.get("population_response_summary") or {}
        practical = " ".join(response.get("practical_current_responses", [])).lower()
        self.assertIn("move", practical)
        self.assertIn("rent closer", practical)

    def test_admin_debug_exposes_population_drivers(self) -> None:
        run_player_next_day(self.db, str(self.player_suburban.id))
        snapshot = get_full_player_debug_snapshot(self.db, str(self.player_suburban.id))
        self.assertIn("population_region_state", snapshot)
        self.assertIn("population_opportunity_pressure", snapshot)
        self.assertIn("population_competition_state", snapshot)
        self.assertIn("population_region_heat", snapshot)
        self.assertIn("population_response_summary", snapshot)
        self.assertIn("population_pressure_summary", snapshot)

    def test_food_truck_outputs_show_local_sensitivity(self) -> None:
        sub_payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player_suburban.id),
            business_type="food_truck",
            region_key="suburban",
        )
        down_payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player_downtown.id),
            business_type="food_truck",
            region_key="downtown",
        )
        sub_business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.id == uuid.UUID(sub_payload["business_id"]))
            .first()
        )
        down_business = (
            self.db.query(PlayerBusiness)
            .filter(PlayerBusiness.id == uuid.UUID(down_payload["business_id"]))
            .first()
        )
        sub_business.inventory_essentials_units = Decimal("130")
        sub_business.inventory_protein_units = Decimal("130")
        down_business.inventory_essentials_units = Decimal("130")
        down_business.inventory_protein_units = Decimal("130")

        sub_result = operate_food_truck(
            self.db,
            sub_business,
            as_of_date=day_to_date(1),
            day_number=1,
        )
        down_result = operate_food_truck(
            self.db,
            down_business,
            as_of_date=day_to_date(1),
            day_number=1,
        )
        self.assertNotEqual(sub_result["demand_signal"], down_result["demand_signal"])
        self.assertNotEqual(sub_result["revenue_xgp"], down_result["revenue_xgp"])


if __name__ == "__main__":
    unittest.main()
