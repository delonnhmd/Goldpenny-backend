import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_job_market_service.db")

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.debt_credit_log import DebtCreditLog
from app.models.daily_settlement_log import DailySettlementLog
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
from app.services.housing_region_service import assign_player_housing
from app.services.job_market_service import (
    apply_employment_progression,
    compute_daily_job_market_updates,
    compute_job_market_pressure,
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

JOB_SEED = {
    "auto_mechanic": Decimal("4000.00"),
    "aircraft_mechanic": Decimal("6200.00"),
    "banker": Decimal("5100.00"),
    "chef": Decimal("3500.00"),
    "retail": Decimal("2600.00"),
    "delivery": Decimal("3000.00"),
}


class JobMarketServiceTests(unittest.TestCase):
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
                JobDefinitionDB.__table__,
                PlayerEmploymentState.__table__,
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DebtCreditLog.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                StockDailyPrice.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                MacroDailyState.__table__,
            ],
        )

        self.db = self.SessionLocal()

        user = User(
            email=f"job-test-{uuid.uuid4()}@example.com",
            hashed_password="hashed-password",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Job Test Player",
            cash=Decimal("3000.00"),
            debt_xgp=Decimal("150.00"),
            stress=25,
            health=95,
            hours_available=16,
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        self.player = player

        self._seed_job_definitions()
        self._seed_macro_rows()
        self._seed_market_rows()

        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="banker",
                skill_level=3,
                monthly_pay_xgp=Decimal("5100.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_job_definitions(self) -> None:
        for code, pay in JOB_SEED.items():
            self.db.add(
                JobDefinitionDB(
                    job_code=code,
                    title=code.replace("_", " ").title(),
                    base_monthly_pay_xgp=pay,
                    stability_pct=Decimal("0.75"),
                    growth_pct=Decimal("0.60"),
                    stress_pct=Decimal("0.55"),
                    promotion_threshold=100,
                )
            )

    def _seed_macro_rows(self) -> None:
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.4"),
                interest_rate=Decimal("4.2"),
                unemployment_rate=Decimal("5.3"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("53.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Baseline",
                event_summary="Baseline macro conditions.",
            )
        )
        self.db.add(
            MacroDailyState(
                day=2,
                inflation_rate=Decimal("8.2"),
                interest_rate=Decimal("7.8"),
                unemployment_rate=Decimal("10.4"),
                oil_index=Decimal("165.0"),
                consumer_confidence=Decimal("24.0"),
                supply_chain_stress=Decimal("2.2"),
                event_headline="Downturn",
                event_summary="High stress macro day used for layoff tests.",
            )
        )

    def _seed_market_rows(self) -> None:
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

    def _set_employment_job(self, job_code: str, pay: Decimal, skill_level: int = 3) -> None:
        latest = (
            self.db.query(PlayerEmploymentState)
            .filter(PlayerEmploymentState.player_id == self.player.id)
            .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
            .first()
        )
        latest.current_job_code = job_code
        latest.monthly_pay_xgp = pay
        latest.skill_level = skill_level
        latest.employed_flag = True
        latest.job_status = "employed"
        latest.employment_evaluated_flag = False
        self.player.main_job = job_code
        self.db.add(latest)
        self.db.add(self.player)
        self.db.commit()

    def test_compute_job_market_pressure_for_core_job_types(self) -> None:
        for code, pay in JOB_SEED.items():
            self._set_employment_job(code, pay)
            metrics = compute_job_market_pressure(self.db, str(self.player.id), day=1)
            self.assertEqual(metrics["current_job_code"], code)
            self.assertGreaterEqual(metrics["opportunity_score"], 0.70)
            self.assertLessEqual(metrics["opportunity_score"], 1.45)
            self.assertGreaterEqual(metrics["layoff_risk_pct"], 0.0)
            self.assertLessEqual(metrics["layoff_risk_pct"], 35.0)
            self.assertGreaterEqual(metrics["promotion_chance_pct"], 0.0)
            self.assertLessEqual(metrics["promotion_chance_pct"], 20.0)

    def test_layoff_can_occur_under_high_risk_conditions(self) -> None:
        self._set_employment_job("retail", Decimal("2600.00"), skill_level=2)
        self.player.stress = 95
        self.player.health = 68
        self.db.add(self.player)
        self.db.commit()

        layoff_happened = False
        for day in range(2, 80):
            result = apply_employment_progression(self.db, str(self.player.id), day=day, commit=True)
            if result["employment_event"] == "layoff":
                layoff_happened = True
                break

        self.assertTrue(layoff_happened)

    def test_stable_jobs_do_not_layoff_frequently_under_normal_conditions(self) -> None:
        self._set_employment_job("aircraft_mechanic", Decimal("6200.00"), skill_level=5)
        self.player.stress = 20
        self.player.health = 96
        self.db.add(self.player)
        self.db.add(
            MacroDailyState(
                day=3,
                inflation_rate=Decimal("2.3"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.1"),
                oil_index=Decimal("100.0"),
                consumer_confidence=Decimal("56.0"),
                supply_chain_stress=Decimal("0.4"),
                event_headline="Normal Conditions",
                event_summary="Macro normalization row for stable-job test.",
            )
        )
        self.db.commit()

        layoff_count = 0
        for day in range(3, 30):
            result = apply_employment_progression(self.db, str(self.player.id), day=day, commit=True)
            if result["employment_event"] == "layoff":
                layoff_count += 1

        self.assertLessEqual(layoff_count, 1)

    def test_promotion_or_raise_can_occur_when_threshold_met(self) -> None:
        self._set_employment_job("banker", Decimal("5100.00"), skill_level=12)
        self.db.add(
            MacroDailyState(
                day=3,
                inflation_rate=Decimal("2.0"),
                interest_rate=Decimal("3.9"),
                unemployment_rate=Decimal("4.7"),
                oil_index=Decimal("98.0"),
                consumer_confidence=Decimal("61.0"),
                supply_chain_stress=Decimal("0.3"),
                event_headline="Expansion",
                event_summary="Supportive macro row for promotion test.",
            )
        )
        self.db.commit()

        promotion_happened = False
        pay_start = Decimal("5100.00")
        pay_latest = pay_start
        for day in range(3, 140):
            result = apply_employment_progression(self.db, str(self.player.id), day=day, commit=True)
            pay_latest = Decimal(str(result["monthly_pay_after"]))
            if result["employment_event"] == "promotion":
                promotion_happened = True
                break

        self.assertTrue(promotion_happened or pay_latest != pay_start)

    def test_settlement_includes_employment_summary(self) -> None:
        result = settle_player_day(self.db, str(self.player.id))

        self.assertIn("employment_status", result)
        self.assertIn("employment_event", result)
        self.assertIn("layoff_risk_pct", result)
        self.assertIn("promotion_chance_pct", result)
        self.assertIn("wage_adjustment_pct", result)
        self.assertIn("monthly_pay_xgp_after_event", result)

    def test_downtown_vs_suburban_changes_opportunity_score_bounded(self) -> None:
        assign_player_housing(self.db, str(self.player.id), "suburban")
        suburban = compute_job_market_pressure(self.db, str(self.player.id), day=1)

        assign_player_housing(self.db, str(self.player.id), "downtown")
        downtown = compute_job_market_pressure(self.db, str(self.player.id), day=1)

        self.assertGreater(downtown["opportunity_score"], suburban["opportunity_score"])
        self.assertLessEqual(downtown["opportunity_score"], 1.45)

    def test_wage_adjustment_remains_capped_and_decimal_safe(self) -> None:
        self._set_employment_job("banker", Decimal("5100.00"), skill_level=8)
        result = apply_employment_progression(self.db, str(self.player.id), day=2, commit=True)

        self.assertGreaterEqual(result["wage_adjustment_pct"], -0.40)
        self.assertLessEqual(result["wage_adjustment_pct"], 0.50)

        state = (
            self.db.query(PlayerEmploymentState)
            .filter(
                PlayerEmploymentState.player_id == self.player.id,
                PlayerEmploymentState.day == 2,
            )
            .first()
        )
        self.assertIsNotNone(state)
        stored_pay = Decimal(str(state.monthly_pay_xgp))
        self.assertEqual(stored_pay, stored_pay.quantize(Decimal("0.01")))

    def test_daily_job_market_positive_pressure_improves_delivery_opportunity(self) -> None:
        market = compute_daily_job_market_updates(self.db, day=2)
        rows = {row["job_key"]: row for row in market["job_updates"]}

        self.assertGreater(rows["delivery"]["pressure"], 0.0)
        self.assertGreater(rows["delivery"]["opportunity_modifier"], 0.0)

    def test_negative_pressure_increases_layoff_modifier(self) -> None:
        market = compute_daily_job_market_updates(self.db, day=2)
        rows = {row["job_key"]: row for row in market["job_updates"]}

        self.assertLess(rows["retail"]["pressure"], 0.0)
        self.assertGreater(rows["retail"]["layoff_risk_modifier"], 0.0)

    def test_wage_drift_modifier_is_small_and_bounded(self) -> None:
        market = compute_daily_job_market_updates(self.db, day=2)
        for row in market["job_updates"]:
            self.assertGreaterEqual(row["wage_drift_modifier"], -0.01)
            self.assertLessEqual(row["wage_drift_modifier"], 0.01)

    def test_delivery_reacts_more_than_aircraft_mechanic(self) -> None:
        market = compute_daily_job_market_updates(self.db, day=2)
        rows = {row["job_key"]: row for row in market["job_updates"]}

        self.assertGreater(
            abs(rows["delivery"]["pressure"]),
            abs(rows["aircraft_mechanic"]["pressure"]),
        )

    def test_aircraft_mechanic_stays_relatively_stable(self) -> None:
        market = compute_daily_job_market_updates(self.db, day=2)
        rows = {row["job_key"]: row for row in market["job_updates"]}

        self.assertLess(abs(rows["aircraft_mechanic"]["pressure"]), 0.10)


if __name__ == "__main__":
    unittest.main()
