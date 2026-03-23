import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_simulation_service.db")

from app.db.database import Base
from app.engine.simulation_service import run_economy_scenario_sweep, run_player_scenario_simulation
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
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
from app.models.side_income_action import SideIncomeAction
from app.models.stock_daily_price import StockDailyPrice
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


class SimulationServiceTests(unittest.TestCase):
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
                FinancialDistressLog.__table__,
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
                SideIncomeAction.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"sim-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Sim Player",
            cash=Decimal("1100.00"),
            debt_xgp=Decimal("700.00"),
            stress=26,
            health=93,
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
                unemployment_rate=Decimal("5.3"),
                oil_index=Decimal("102.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Simulation baseline",
                event_summary="Step 21 simulation seed.",
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
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("3200.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_simulation_run_is_deterministic_and_non_mutating(self) -> None:
        cash_before = float(self.player.cash_xgp)
        settled_before = self.player.last_settled_day
        settlements_before = self.db.query(DailySettlementLog).count()

        first = run_player_scenario_simulation(
            db=self.db,
            player_id=str(self.player.id),
            days=3,
            scenario_key="neutral_baseline",
        )
        second = run_player_scenario_simulation(
            db=self.db,
            player_id=str(self.player.id),
            days=3,
            scenario_key="neutral_baseline",
        )

        self.db.refresh(self.player)

        self.assertEqual(first["final_cash_xgp"], second["final_cash_xgp"])
        self.assertEqual(first["final_net_worth_xgp"], second["final_net_worth_xgp"])
        self.assertEqual(first["avg_stress"], second["avg_stress"])
        self.assertEqual(first["avg_health"], second["avg_health"])

        self.assertEqual(float(self.player.cash_xgp), cash_before)
        self.assertEqual(self.player.last_settled_day, settled_before)
        self.assertEqual(self.db.query(DailySettlementLog).count(), settlements_before)

    def test_simulation_summary_shape_and_flags(self) -> None:
        payload = run_player_scenario_simulation(
            db=self.db,
            player_id=str(self.player.id),
            days=4,
            scenario_key="debt_spiral",
        )

        self.assertIn("scenario_key", payload)
        self.assertIn("final_cash_xgp", payload)
        self.assertIn("final_net_worth_xgp", payload)
        self.assertIn("exploit_flags", payload)
        self.assertIn("telemetry_summary", payload)
        self.assertIn("debug_meta", payload)
        self.assertIn("strategy_classification", payload)
        self.assertIn("business_mode_outcomes", payload)
        self.assertIn("upgrade_roi_signals", payload)
        self.assertIn("weekly_summary_snapshots", payload)
        self.assertGreaterEqual(payload["missed_payments"], 0)

    def test_step22_preset_runs_and_returns_strategy_outputs(self) -> None:
        payload = run_player_scenario_simulation(
            db=self.db,
            player_id=str(self.player.id),
            days=8,
            scenario_key="confidence_rebound_path",
        )
        self.assertEqual(payload["scenario_key"], "confidence_rebound_path")
        self.assertIn(payload["strategy_classification"], {
            "stable_worker",
            "hustler",
            "entrepreneur",
            "overextended",
            "recovery_mode",
            "career_builder",
            "high_risk_operator",
        })
        self.assertIsInstance(payload["weekly_summary_snapshots"], list)

    def test_step22_presets_produce_distinct_paths(self) -> None:
        conservative = run_player_scenario_simulation(
            db=self.db,
            player_id=str(self.player.id),
            days=8,
            scenario_key="conservative_worker_path",
        )
        high_risk = run_player_scenario_simulation(
            db=self.db,
            player_id=str(self.player.id),
            days=8,
            scenario_key="downtown_high_risk_path",
        )

        conservative_signature = (
            conservative["final_cash_xgp"],
            conservative["avg_stress"],
            conservative["final_distress_state"],
        )
        high_risk_signature = (
            high_risk["final_cash_xgp"],
            high_risk["avg_stress"],
            high_risk["final_distress_state"],
        )
        self.assertNotEqual(conservative_signature, high_risk_signature)

    def test_scenario_sweep_runs_without_corrupting_live_state(self) -> None:
        settlements_before = self.db.query(DailySettlementLog).count()
        sweep = run_economy_scenario_sweep(
            db=self.db,
            player_id=str(self.player.id),
            days=2,
            scenario_keys=["neutral_baseline", "oil_shock"],
        )

        self.assertEqual(len(sweep["runs"]), 2)
        self.assertEqual(sweep["scenarios_run"], ["neutral_baseline", "oil_shock"])
        self.assertEqual(self.db.query(DailySettlementLog).count(), settlements_before)


if __name__ == "__main__":
    unittest.main()
