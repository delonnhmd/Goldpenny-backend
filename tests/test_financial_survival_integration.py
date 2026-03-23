import json
import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_financial_survival_integration.db")

from app.db.database import Base
from app.engine.strategic_planning_service import build_player_strategy_recommendation
from app.engine.world_memory_service import build_player_pattern_summary
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.career_progress_log import CareerProgressLog
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
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_shock_state import PlayerShockState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_world_memory_state import PlayerWorldMemoryState
from app.models.player_world_pattern_history import PlayerWorldPatternHistory
from app.models.region_population_history import RegionPopulationHistory
from app.models.region_population_state import RegionPopulationState
from app.models.side_income_action import SideIncomeAction
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.admin_debug_service import get_full_player_debug_snapshot
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


class FinancialSurvivalIntegrationTests(unittest.TestCase):
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
                PlayerWorldMemoryState.__table__,
                PlayerWorldPatternHistory.__table__,
                RegionPopulationState.__table__,
                RegionPopulationHistory.__table__,
                PlayerShockState.__table__,
                PlayerRecoveryState.__table__,
                PlayerLifeEventHistory.__table__,
                CareerProgressLog.__table__,
                PlayerDelinquencyState.__table__,
                PlayerPaymentHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step36-int-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Step36 Integration Tester",
            cash=Decimal("0.00"),
            debt_xgp=Decimal("3400.00"),
            credit_score=638,
            stress=67,
            health=74,
            hours_available=16,
            region="downtown",
            main_job="delivery_driver",
            productivity_modifier=Decimal("0.92"),
            burnout_risk=Decimal("0.21"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            JobDefinitionDB(
                job_code="delivery_driver",
                title="Delivery Driver",
                base_monthly_pay_xgp=Decimal("1400.00"),
                stability_pct=Decimal("0.58"),
                growth_pct=Decimal("0.42"),
                stress_pct=Decimal("0.66"),
                promotion_threshold=100,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="delivery_driver",
                skill_level=1,
                monthly_pay_xgp=Decimal("1400.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("10.00"),
                productivity_modifier=Decimal("0.92"),
            )
        )
        self.db.add(
            PlayerDailyState(
                player_id=self.player.id,
                day_number=1,
                hours_available_start=16,
                hours_available_end=8,
                worked_main_job=True,
                worked_hours=8,
                side_income_hours=Decimal("1.0"),
                did_settlement=False,
                stress_start=67,
                stress_end=67,
                health_start=74,
                health_end=74,
                cash_start=Decimal("0.0000"),
                cash_end=Decimal("0.0000"),
            )
        )
        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("1160.00"),
                monthly_utilities_cost_xgp=Decimal("170.00"),
                monthly_transport_base_xgp=Decimal("210.00"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            RegionPopulationState(
                region_key="downtown",
                active_population_score=Decimal("78.0"),
                opportunity_density_score=Decimal("81.0"),
                congestion_score=Decimal("75.0"),
                housing_pressure_score=Decimal("80.0"),
                business_competition_score=Decimal("73.0"),
                consumer_flow_score=Decimal("80.0"),
                recent_growth_direction="rising",
                last_updated_on=1,
            )
        )
        self.db.add(
            PlayerShockState(
                player_id=self.player.id,
                shock_risk_score=Decimal("82.0"),
                financial_fragility_score=Decimal("70.0"),
                health_fragility_score=Decimal("62.0"),
                work_disruption_risk_score=Decimal("58.0"),
                recovery_capacity_score=Decimal("36.0"),
                recent_negative_streak=2,
                recent_recovery_support=0,
                recent_pressure_direction="rising",
                last_updated_on=1,
            )
        )

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.8"),
                interest_rate=Decimal("4.2"),
                unemployment_rate=Decimal("5.6"),
                oil_index=Decimal("112.0"),
                consumer_confidence=Decimal("47.0"),
                supply_chain_stress=Decimal("1.0"),
                event_headline="Step36 integration baseline",
                event_summary="Baseline macro for financial survival integration test.",
            )
        )
        for basket_type, price in {
            BasketType.essentials: Decimal("10.4"),
            BasketType.protein: Decimal("12.1"),
            BasketType.produce: Decimal("10.0"),
            BasketType.convenience: Decimal("9.1"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.15"),
                    supply_pressure=Decimal("1.01"),
                    demand_pressure=Decimal("1.01"),
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

    def test_day_run_emits_financial_survival_fields(self) -> None:
        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("financial_survival_summary", result)
        self.assertIn("required_daily_burden_xgp", result)
        self.assertIn("required_monthly_obligation_xgp", result)
        self.assertIn("obligation_load_ratio", result)
        self.assertIn("liquidity_buffer_days", result)
        self.assertIn("payment_pressure_label", result)
        self.assertIn("current_delinquency_stage", result)
        self.assertIn("survival_status_label", result)
        self.assertIn("financial_survival_payment_outcome", result)
        self.assertIn("financial_survival_credit_score_delta", result)
        self.assertIn("financial_survival_practical_actions", result)

        self.assertIn(
            result["current_delinquency_stage"],
            {"current", "stretched", "late", "delinquent", "critical"},
        )

    def test_repeated_pressure_escalates_and_persists_payment_history(self) -> None:
        for _ in range(5):
            self.player.cash = Decimal("0.00")
            self.db.flush()
            run_player_next_day(self.db, str(self.player.id))

        payment_rows = (
            self.db.query(PlayerPaymentHistory)
            .filter(PlayerPaymentHistory.player_id == self.player.id)
            .order_by(PlayerPaymentHistory.day_number.asc())
            .all()
        )
        self.assertGreaterEqual(len(payment_rows), 5)
        outcomes = [str(row.payment_outcome) for row in payment_rows]
        self.assertTrue(any(outcome in {"missed", "delayed", "paid_partial"} for outcome in outcomes))

        delinquency = (
            self.db.query(PlayerDelinquencyState)
            .filter(PlayerDelinquencyState.player_id == self.player.id)
            .first()
        )
        self.assertIsNotNone(delinquency)
        self.assertIn(
            str(delinquency.current_delinquency_stage),
            {"stretched", "late", "delinquent", "critical"},
        )

        latest_settlement = (
            self.db.query(DailySettlementLog)
            .filter(DailySettlementLog.player_id == self.player.id)
            .order_by(DailySettlementLog.day_number.desc())
            .first()
        )
        self.assertIsNotNone(latest_settlement)
        summary = json.loads(latest_settlement.summary_json or "{}")
        self.assertIn("financial_survival_summary", summary)
        self.assertIn("payment_pressure_label", summary)
        self.assertIn("current_delinquency_stage", summary)

    def test_admin_debug_snapshot_exposes_financial_survival_chain(self) -> None:
        run_player_next_day(self.db, str(self.player.id))

        snapshot = get_full_player_debug_snapshot(self.db, str(self.player.id))
        self.assertIn("financial_obligation_profile", snapshot)
        self.assertIn("financial_payment_risk_state", snapshot)
        self.assertIn("financial_delinquency_state", snapshot)
        self.assertIn("financial_credit_impact", snapshot)
        self.assertIn("financial_survival_summary", snapshot)
        self.assertIn("financial_payment_history", snapshot)
        self.assertIn("financial_survival_system_summary", snapshot)

    def test_memory_and_planning_consume_payment_survival_pressure(self) -> None:
        for _ in range(4):
            self.player.cash = Decimal("0.00")
            self.db.flush()
            run_player_next_day(self.db, str(self.player.id))

        patterns = build_player_pattern_summary(self.db, str(self.player.id))
        debug_meta = patterns.get("debug_meta", {})
        self.assertGreater(int(debug_meta.get("payment_stress_days", 0)), 0)

        recommendation = build_player_strategy_recommendation(self.db, str(self.player.id))
        rec_debug = recommendation.get("debug_meta", {})
        self.assertIn("payment_pressure_label", rec_debug)
        self.assertIn("financial_survival_summary", rec_debug)


if __name__ == "__main__":
    unittest.main()
