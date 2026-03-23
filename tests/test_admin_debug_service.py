import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_admin_debug_service.db")

from app.api.day import run_player_next_day_route
from app.api.internal import (
    MacroScenarioRequest,
    PlayerResetRequest,
    PlayerScenarioRequest,
    force_internal_macro_scenario,
    force_internal_player_scenario,
    get_internal_economy_snapshot,
    get_internal_player_snapshot,
    reset_internal_player_state,
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
from app.models.stock_trade_log import StockTradeLog
from app.models.user import User


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


class AdminDebugServiceTests(unittest.TestCase):
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
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                StockDailyPrice.__table__,
                StockTradeLog.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                DebtCreditLog.__table__,
                HousingDailyLog.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
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
            email=f"internal-debug-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Debug Player",
            gender="male",
            region="downtown",
            cash=Decimal("1200.00"),
            bank_savings_xgp=Decimal("220.00"),
            debt_xgp=Decimal("650.00"),
            credit_score=645,
            net_worth_xgp=Decimal("770.00"),
            health=89,
            stress=34,
            hours_available=16,
            main_job="delivery_driver",
        )
        self.db.add(player)
        self.db.flush()
        self.player = player

        self.db.add(
            JobDefinitionDB(
                job_code="delivery_driver",
                title="Delivery Driver",
                base_monthly_pay_xgp=Decimal("2900.00"),
                stability_pct=Decimal("0.62"),
                growth_pct=Decimal("0.45"),
                stress_pct=Decimal("0.65"),
                promotion_threshold=100,
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
                event_summary="Starter macro state.",
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
            BasketType.produce: Decimal("9.0000"),
            BasketType.convenience: Decimal("8.5000"),
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
            PlayerHousingState(
                player_id=player.id,
                region="downtown",
                housing_type="starter_rent",
                daily_housing_cost_xgp=Decimal("35.00"),
                commute_modifier=Decimal("0.9200"),
                stress_modifier=2,
                opportunity_modifier=Decimal("1.0900"),
                active_flag=True,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=player.id,
                day=1,
                current_job_code="delivery_driver",
                skill_level=1,
                monthly_pay_xgp=Decimal("2900.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("8.00"),
                productivity_modifier=Decimal("1.0000"),
                opportunity_score=Decimal("1.0000"),
                promotion_chance_pct=Decimal("0.00"),
                wage_adjustment_pct=Decimal("0.00"),
                employment_evaluated_flag=False,
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
                cash_reserve_xgp=Decimal("120.00"),
                created_day=1,
                is_active=True,
            )
        )
        self.db.add(
            BusinessDailyLog(
                business_id=business_id,
                player_id=player.id,
                day=1,
                gross_revenue_xgp=Decimal("75.0000"),
                input_cost_xgp=Decimal("42.0000"),
                fuel_cost_xgp=Decimal("8.0000"),
                spoilage_cost_xgp=Decimal("1.5000"),
                overhead_cost_xgp=Decimal("15.0000"),
                net_profit_xgp=Decimal("8.5000"),
                demand_score=Decimal("1.0100"),
                utilization_pct=Decimal("0.8200"),
            )
        )

        self.db.add(
            BasketConsumptionLog(
                player_id=player.id,
                day=1,
                essentials_spend_xgp=Decimal("8.20"),
                protein_spend_xgp=Decimal("3.90"),
                produce_spend_xgp=Decimal("2.70"),
                convenience_spend_xgp=Decimal("4.20"),
                total_spend_xgp=Decimal("19.00"),
                budget_pressure_score=Decimal("0.6100"),
                stress_spend_modifier=Decimal("1.0500"),
                nutrition_pressure_score=Decimal("0.3800"),
            )
        )
        self.db.add(
            DebtCreditLog(
                player_id=player.id,
                day=1,
                opening_debt_xgp=Decimal("650.00"),
                payment_due_xgp=Decimal("8.13"),
                payment_made_xgp=Decimal("8.13"),
                interest_added_xgp=Decimal("0.21"),
                ending_debt_xgp=Decimal("642.08"),
                payment_status="paid_full",
                opening_credit_score=645,
                credit_score_change=1,
                ending_credit_score=646,
                delinquency_flag=False,
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=player.id,
                day=1,
                region="downtown",
                housing_cost_xgp=Decimal("35.00"),
                commute_pressure=Decimal("0.9000"),
                stress_delta=3,
                opportunity_modifier=Decimal("1.0900"),
            )
        )
        self.db.add(
            DailySettlementLog(
                player_id=player.id,
                day_number=1,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=34,
                stress_after=38,
                health_before=89,
                health_after=88,
                cash_before=Decimal("1200.0000"),
                cash_after=Decimal("1140.0000"),
                income_xgp=Decimal("96.0000"),
                expenses_xgp=Decimal("156.0000"),
                stock_pnl_xgp=Decimal("0.0000"),
                debt_paid_xgp=Decimal("8.1300"),
                health_change=-1,
                stress_change=4,
                summary_json='{"employment_status":"employed","employment_event":"none","layoff_risk_pct":8.0}',
            )
        )
        self.db.add(
            DailyBriefLog(
                player_id=player.id,
                day=1,
                headline="Fuel costs rise modestly",
                summary="You handled debt, but transport pressure remains elevated.",
                macro_tags_json='["oil_up","transport_pressure"]',
                player_impact_json='{"biggest_pressure":"fuel costs","system_changed_most":"macro"}',
                action_hints_json='["Preserve cash for fuel-sensitive spending."]',
            )
        )
        self.db.add(
            PlayerStockHolding(
                player_id=player.id,
                stock_id="GPTECH",
                shares_owned=5,
                average_cost_basis=Decimal("49.5000"),
                total_cost_basis=Decimal("247.5000"),
            )
        )

    def test_full_player_snapshot_returns_all_major_sections(self) -> None:
        snapshot = get_internal_player_snapshot(player_id=str(self.player.id), db=self.db)
        payload = snapshot.model_dump()

        self.assertIn("player_profile", payload)
        self.assertIn("active_housing_summary", payload)
        self.assertIn("active_employment_summary", payload)
        self.assertIn("latest_consumption_summary", payload)
        self.assertIn("latest_debt_credit_summary", payload)
        self.assertIn("latest_settlement_summary", payload)
        self.assertIn("location_chain", payload)
        self.assertIn("latest_daily_brief", payload)
        self.assertIn("latest_portfolio_summary", payload)
        self.assertIn("latest_business_summary", payload)
        self.assertIn("active_job_pressure", payload["latest_job_summary"])
        self.assertIn("active_job_opportunity_modifier", payload["latest_job_summary"])
        self.assertIn("active_job_wage_drift_modifier", payload["latest_job_summary"])
        self.assertIn("active_job_layoff_risk_modifier", payload["latest_job_summary"])
        self.assertEqual(payload["player_profile"]["player_id"], str(self.player.id))
        self.assertIn("housing_state", payload["location_chain"])
        self.assertIn("daily_housing_effect", payload["location_chain"])

    def test_economy_snapshot_returns_latest_macro_basket_and_stock_sections(self) -> None:
        snapshot = get_internal_economy_snapshot(db=self.db)
        payload = snapshot.model_dump()

        self.assertIsNotNone(payload["latest_macro_state"])
        self.assertEqual(payload["latest_basket_day"], 1)
        self.assertGreater(len(payload["latest_basket_daily_prices"]), 0)
        self.assertEqual(payload["latest_stock_day"], 1)
        self.assertGreater(payload["latest_stock_daily_prices_summary"]["row_count"], 0)
        self.assertIn("latest_supply_chain_daily", payload)
        self.assertIn("latest_basket_pricing_daily", payload)
        self.assertIn("latest_job_market_daily", payload)
        self.assertIn("latest_daily_economy_brief", payload)
        self.assertIn("top_bottlenecks", payload)
        self.assertIn("top_basket_movers", payload)
        self.assertIn("top_job_pressure_movers", payload)
        self.assertIn("aggregate_counts", payload)

    def test_forcing_oil_spike_changes_macro_in_expected_direction(self) -> None:
        response = force_internal_macro_scenario(
            body=MacroScenarioRequest(scenario_name="oil_spike"),
            db=self.db,
        )
        payload = response.model_dump()

        self.assertEqual(payload["scenario_name"], "oil_spike")
        self.assertGreater(
            payload["after_macro"]["oil_index"],
            payload["before_macro"]["oil_index"],
        )

    def test_forcing_low_cash_changes_player_cash_downward(self) -> None:
        response = force_internal_player_scenario(
            player_id=str(self.player.id),
            body=PlayerScenarioRequest(scenario_name="low_cash"),
            db=self.db,
        )
        payload = response.model_dump()

        self.assertLessEqual(
            payload["after_player_summary"]["cash_xgp"],
            payload["before_player_summary"]["cash_xgp"],
        )

    def test_forcing_high_debt_increases_player_debt(self) -> None:
        response = force_internal_player_scenario(
            player_id=str(self.player.id),
            body=PlayerScenarioRequest(scenario_name="high_debt"),
            db=self.db,
        )
        payload = response.model_dump()

        self.assertGreater(
            payload["after_player_summary"]["debt_xgp"],
            payload["before_player_summary"]["debt_xgp"],
        )

    def test_reset_player_returns_playable_player_and_day_run_still_works(self) -> None:
        reset_response = reset_internal_player_state(
            player_id=str(self.player.id),
            body=PlayerResetRequest(preserve_profile=True),
            db=self.db,
        )
        reset_payload = reset_response.model_dump()

        self.assertTrue(reset_payload["reset_complete"])
        self.assertEqual(reset_payload["player_id"], str(self.player.id))
        playable = reset_payload["playable_summary"]
        self.assertEqual(playable["player_id"], str(self.player.id))
        self.assertIsNotNone(playable["active_housing_summary"])
        self.assertIsNotNone(playable["active_employment_summary"])

        day_result = run_player_next_day_route(player_id=str(self.player.id), db=self.db)
        self.assertEqual(day_result.settled_day, 1)
        self.assertIn("opening_debt_xgp", day_result.summary_json)
        self.assertTrue(day_result.headline)
        self.assertTrue(day_result.summary)


if __name__ == "__main__":
    unittest.main()
