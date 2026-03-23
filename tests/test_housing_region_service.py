import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_housing_region_service.db")

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
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
from app.services.daily_settlement_service import settle_player_day
from app.services.housing_region_service import (
    assign_player_housing,
    compute_housing_effects_for_day,
    get_business_region_demand_modifier,
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


class HousingRegionServiceTests(unittest.TestCase):
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
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DebtCreditLog.__table__,
                PlayerEmploymentState.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                MacroDailyState.__table__,
                StockDailyPrice.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
            ],
        )

        self.db = self.SessionLocal()

        self.player_suburban = self._seed_player("suburban")
        self.player_downtown = self._seed_player("downtown")
        self._seed_shared_market()
        self._seed_player_employment(self.player_suburban.id)
        self._seed_player_employment(self.player_downtown.id)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player(self, region: str) -> Player:
        user = User(
            email=f"housing-{region}-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=f"Housing {region}",
            cash=Decimal("2000.00"),
            region=region,
            health=95,
            stress=20,
            hours_available=16,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_shared_market(self) -> None:
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

    def _seed_player_employment(self, player_id) -> None:
        self.db.add(
            PlayerEmploymentState(
                player_id=player_id,
                day=1,
                current_job_code=None,
                skill_level=1,
                monthly_pay_xgp=Decimal("3000.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

    def test_assign_suburban_housing(self) -> None:
        result = assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        self.assertEqual(result["region"], "suburban")
        self.assertEqual(result["housing_type"], "starter_rent")
        self.assertTrue(result["active_flag"])

    def test_assign_downtown_housing(self) -> None:
        result = assign_player_housing(self.db, str(self.player_suburban.id), "downtown")
        self.assertEqual(result["region"], "downtown")
        self.assertGreater(result["daily_housing_cost_xgp"], 0)

    def test_only_one_active_housing_state_per_player(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        assign_player_housing(self.db, str(self.player_suburban.id), "downtown")

        active_count = (
            self.db.query(PlayerHousingState)
            .filter(
                PlayerHousingState.player_id == self.player_suburban.id,
                PlayerHousingState.active_flag.is_(True),
            )
            .count()
        )
        total_count = (
            self.db.query(PlayerHousingState)
            .filter(PlayerHousingState.player_id == self.player_suburban.id)
            .count()
        )
        self.assertEqual(active_count, 1)
        self.assertEqual(total_count, 2)

    def test_settlement_includes_housing_cost_and_writes_log(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "downtown")
        result = settle_player_day(self.db, str(self.player_suburban.id))

        self.assertIn("housing_cost_xgp", result)
        self.assertIn("housing_region", result)
        self.assertIn("housing_cost_daily_xgp", result)
        self.assertIn("utilities_cost_daily_xgp", result)
        self.assertIn("commute_hours", result)
        self.assertIn("commute_fuel_cost_xgp", result)
        self.assertIn("region_stress_delta", result)
        self.assertIn("region_opportunity_modifier", result)
        self.assertIn("region_business_demand_modifier", result)
        self.assertIn("region_side_income_modifier", result)
        self.assertIn("networking_modifier", result)
        self.assertIn("opportunity_quality_signal", result)
        self.assertEqual(result["housing_region"], "downtown")
        self.assertGreater(result["housing_cost_xgp"], 0)

        log = (
            self.db.query(HousingDailyLog)
            .filter(
                HousingDailyLog.player_id == self.player_suburban.id,
                HousingDailyLog.day == 1,
            )
            .first()
        )
        self.assertIsNotNone(log)

    def test_compute_housing_effects_idempotent_per_day(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")

        first = compute_housing_effects_for_day(self.db, str(self.player_suburban.id), 1)
        self.db.commit()
        second = compute_housing_effects_for_day(self.db, str(self.player_suburban.id), 1)
        self.db.commit()

        count = (
            self.db.query(HousingDailyLog)
            .filter(
                HousingDailyLog.player_id == self.player_suburban.id,
                HousingDailyLog.day == 1,
            )
            .count()
        )

        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])
        self.assertEqual(count, 1)
        self.assertIn("commute_hours", first)
        self.assertIn("commute_fuel_cost_xgp", first)
        self.assertIn("region_business_demand_modifier", first)
        self.assertIn("region_side_income_modifier", first)

    def test_downtown_vs_suburban_expense_stress_profile_differs(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        assign_player_housing(self.db, str(self.player_downtown.id), "downtown")

        suburban = settle_player_day(self.db, str(self.player_suburban.id))
        downtown = settle_player_day(self.db, str(self.player_downtown.id))

        self.assertGreater(downtown["housing_cost_xgp"], suburban["housing_cost_xgp"])
        self.assertGreaterEqual(downtown["stress_change"], suburban["stress_change"])

    def test_region_modifies_business_demand_behavior_bounded(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        suburban_mod = get_business_region_demand_modifier(
            self.db, str(self.player_suburban.id), "food_truck"
        )

        assign_player_housing(self.db, str(self.player_suburban.id), "downtown")
        downtown_mod = get_business_region_demand_modifier(
            self.db, str(self.player_suburban.id), "food_truck"
        )

        self.assertGreater(float(downtown_mod), float(suburban_mod))
        self.assertGreaterEqual(float(suburban_mod), 0.88)
        self.assertLessEqual(float(downtown_mod), 1.20)

    def test_suburban_commute_exceeds_downtown_for_active_day(self) -> None:
        assign_player_housing(self.db, str(self.player_suburban.id), "suburban")
        assign_player_housing(self.db, str(self.player_downtown.id), "downtown")

        row_sub = (
            self.db.query(PlayerDailyState)
            .filter(PlayerDailyState.player_id == self.player_suburban.id, PlayerDailyState.day_number == 1)
            .first()
        )
        row_down = (
            self.db.query(PlayerDailyState)
            .filter(PlayerDailyState.player_id == self.player_downtown.id, PlayerDailyState.day_number == 1)
            .first()
        )
        if row_sub is None:
            row_sub = PlayerDailyState(player_id=self.player_suburban.id, day_number=1, worked_hours=8)
            self.db.add(row_sub)
        else:
            row_sub.worked_hours = 8
        if row_down is None:
            row_down = PlayerDailyState(player_id=self.player_downtown.id, day_number=1, worked_hours=8)
            self.db.add(row_down)
        else:
            row_down.worked_hours = 8
        self.db.flush()

        sub_effect = compute_housing_effects_for_day(self.db, str(self.player_suburban.id), 1)
        down_effect = compute_housing_effects_for_day(self.db, str(self.player_downtown.id), 1)
        self.db.commit()

        self.assertGreater(sub_effect["commute_hours"], down_effect["commute_hours"])
        self.assertGreaterEqual(down_effect["region_stress_delta"], sub_effect["region_stress_delta"])


if __name__ == "__main__":
    unittest.main()
