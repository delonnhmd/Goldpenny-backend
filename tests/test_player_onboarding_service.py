import os
import unittest
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_player_onboarding_service.db")

from app.api.day import run_player_next_day_route
from app.api.onboarding import (
    NewPlayerOnboardingRequest,
    create_new_player_onboarding,
    get_onboarding_player_summary,
    load_onboarding_player_state,
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
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition import JOB_CATALOG
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
from app.services.day_progression_service import run_player_next_day
from app.services.player_onboarding_service import (
    OnboardingValidationError,
    create_new_player_profile,
    get_playable_player_summary,
    initialize_starter_player_state,
    load_existing_player_state,
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


class PlayerOnboardingServiceTests(unittest.TestCase):
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
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                JobDefinitionDB.__table__,
                MacroDailyState.__table__,
                StockDailyPrice.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                HousingDailyLog.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                DebtCreditLog.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
            ],
        )

        self.db = self.SessionLocal()
        self._seed_market_primitives()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_market_primitives(self) -> None:
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.2"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.1"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.6"),
                event_headline="Baseline market day",
                event_summary="Starter baseline macro state.",
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

        basket_prices = {
            BasketType.essentials: Decimal("10.0000"),
            BasketType.protein: Decimal("12.0000"),
            BasketType.produce: Decimal("9.0000"),
            BasketType.convenience: Decimal("8.5000"),
        }
        for basket_type, price in basket_prices.items():
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

        for job_code in [
            "auto_mechanic",
            "aircraft_mechanic",
            "banker",
            "chef",
            "retail_worker",
            "delivery_driver",
        ]:
            static = JOB_CATALOG.get(job_code)
            monthly = Decimal(str(static.monthly_salary)) if static is not None else Decimal("2600.00")
            stability = Decimal("0.70")
            growth = Decimal("0.50")
            if static is not None:
                stability = Decimal(str(static.stability))
                growth = Decimal(str(static.growth))

            self.db.add(
                JobDefinitionDB(
                    job_code=job_code,
                    title=job_code.replace("_", " ").title(),
                    base_monthly_pay_xgp=monthly,
                    stability_pct=stability,
                    growth_pct=growth,
                    stress_pct=Decimal("0.50"),
                    promotion_threshold=100,
                )
            )

    def _onboard_player(
        self,
        *,
        display_name: str = "Onboarded Player",
        gender: str = "male",
        region: str = "downtown",
        starter_job_code: str = "banker",
    ) -> str:
        created = create_new_player_profile(
            db=self.db,
            display_name=display_name,
            gender=gender,
            region=region,
            starter_job_code=starter_job_code,
        )
        player = created["player"]

        initialize_starter_player_state(
            db=self.db,
            player_id=player.id,
            region=region,
            starter_job_code=starter_job_code,
        )
        self.db.commit()
        return str(player.id)

    def test_onboarding_creates_playable_starter_player(self) -> None:
        player_id = self._onboard_player(gender="female", region="suburban", starter_job_code="chef")
        summary = get_playable_player_summary(self.db, player_id)

        self.assertEqual(summary["player_id"], player_id)
        self.assertEqual(summary["gender"], "female")
        self.assertEqual(summary["region"], "suburban")
        self.assertIsNotNone(summary["active_housing_summary"])
        self.assertIsNotNone(summary["active_employment_summary"])
        self.assertGreater(summary["cash_xgp"], 0.0)
        self.assertGreaterEqual(summary["credit_score"], 300)

        player = self.db.query(Player).filter(Player.id == UUID(summary["player_id"])).first()
        self.assertIsNotNone(player)
        self.assertEqual(player.gender, "female")

        active_housing_rows = (
            self.db.query(PlayerHousingState)
            .filter(PlayerHousingState.player_id == player.id, PlayerHousingState.active_flag.is_(True))
            .count()
        )
        employment_rows = (
            self.db.query(PlayerEmploymentState)
            .filter(PlayerEmploymentState.player_id == player.id)
            .count()
        )
        self.assertEqual(active_housing_rows, 1)
        self.assertEqual(employment_rows, 1)

    def test_invalid_gender_rejected(self) -> None:
        with self.assertRaises(OnboardingValidationError):
            create_new_player_profile(
                db=self.db,
                display_name="Bad Gender",
                gender="other",
                region="suburban",
                starter_job_code="chef",
            )

    def test_invalid_region_rejected(self) -> None:
        with self.assertRaises(OnboardingValidationError):
            create_new_player_profile(
                db=self.db,
                display_name="Bad Region",
                gender="male",
                region="city_core",
                starter_job_code="chef",
            )

    def test_invalid_starter_job_rejected(self) -> None:
        with self.assertRaises(OnboardingValidationError):
            create_new_player_profile(
                db=self.db,
                display_name="Bad Job",
                gender="male",
                region="suburban",
                starter_job_code="astronaut",
            )

    def test_load_existing_player_state_returns_playable_summary(self) -> None:
        player_id = self._onboard_player(display_name="Loader", starter_job_code="retail_worker")
        payload = load_existing_player_state(self.db, player_id)

        self.assertEqual(payload["player_id"], player_id)
        self.assertTrue(payload["load_ready"])
        self.assertEqual(payload["display_name"], "Loader")
        self.assertIsNotNone(payload["active_housing_summary"])
        self.assertIsNotNone(payload["active_employment_summary"])

    def test_created_player_can_immediately_run_day(self) -> None:
        player_id = self._onboard_player(starter_job_code="banker")
        result = run_player_next_day(self.db, player_id)

        self.assertEqual(result["settled_day"], 1)
        self.assertIn("headline", result)
        self.assertIn("summary", result)
        self.assertIn("macro_tags_json", result)
        self.assertIn("player_impact_json", result)
        self.assertIn("action_hints_json", result)


class OnboardingApiFlowTests(unittest.TestCase):
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
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                JobDefinitionDB.__table__,
                MacroDailyState.__table__,
                StockDailyPrice.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                HousingDailyLog.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                DebtCreditLog.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
            ],
        )

        self.db = self.SessionLocal()

        # Seed minimal market data for /day/run compatibility.
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.1"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.0"),
                oil_index=Decimal("100.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Baseline",
                event_summary="Baseline macro conditions.",
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
            BasketType.essentials: Decimal("10.0"),
            BasketType.protein: Decimal("12.0"),
            BasketType.produce: Decimal("9.0"),
            BasketType.convenience: Decimal("8.0"),
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
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_onboarding_endpoints_and_immediate_gameplay(self) -> None:
        created = create_new_player_onboarding(
            body=NewPlayerOnboardingRequest(
                display_name="TestPlayer1",
                gender="male",
                region="downtown",
                starter_job_code="banker",
            ),
            db=self.db,
        )

        self.assertTrue(created.player_id)
        self.assertEqual(created.gender, "male")
        self.assertEqual(created.region, "downtown")
        self.assertIsNotNone(created.active_housing_summary)
        self.assertIsNotNone(created.active_employment_summary)

        player_id = created.player_id

        summary = get_onboarding_player_summary(player_id=player_id, db=self.db)
        self.assertEqual(summary.player_id, player_id)

        load_payload = load_onboarding_player_state(player_id=player_id, db=self.db)
        self.assertTrue(load_payload.load_ready)
        self.assertEqual(load_payload.player_id, player_id)

        run_payload = run_player_next_day_route(player_id=player_id, db=self.db)
        self.assertEqual(run_payload.settled_day, 1)
        self.assertTrue(run_payload.headline)
        self.assertTrue(run_payload.summary)
        self.assertGreater(len(run_payload.macro_tags_json), 0)
        self.assertIsInstance(run_payload.player_impact_json, dict)
        self.assertGreater(len(run_payload.action_hints_json), 0)

    def test_onboarding_rejects_invalid_gender_region_and_job(self) -> None:
        with self.assertRaises(HTTPException) as invalid_gender:
            create_new_player_onboarding(
                body=NewPlayerOnboardingRequest(
                    display_name="BadTest",
                    gender="other",
                    region="suburban",
                    starter_job_code="chef",
                ),
                db=self.db,
            )
        self.assertEqual(invalid_gender.exception.status_code, 400)

        with self.assertRaises(HTTPException) as invalid_region:
            create_new_player_onboarding(
                body=NewPlayerOnboardingRequest(
                    display_name="BadRegion",
                    gender="male",
                    region="city_core",
                    starter_job_code="chef",
                ),
                db=self.db,
            )
        self.assertEqual(invalid_region.exception.status_code, 400)

        with self.assertRaises(HTTPException) as invalid_job:
            create_new_player_onboarding(
                body=NewPlayerOnboardingRequest(
                    display_name="BadJob",
                    gender="male",
                    region="suburban",
                    starter_job_code="astronaut",
                ),
                db=self.db,
            )
        self.assertEqual(invalid_job.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
