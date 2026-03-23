import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_personal_shock_integration.db")

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
from app.models.player_commitment_history import PlayerCommitmentHistory
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_goal_history import PlayerGoalHistory
from app.models.player_housing_state import PlayerHousingState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState
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


class PersonalShockIntegrationTests(unittest.TestCase):
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
                PlayerProgressionState.__table__,
                PlayerGoalHistory.__table__,
                PlayerCommitmentState.__table__,
                PlayerCommitmentHistory.__table__,
                CareerProgressLog.__table__,
                PlayerWorldMemoryState.__table__,
                PlayerWorldPatternHistory.__table__,
                RegionPopulationState.__table__,
                RegionPopulationHistory.__table__,
                PlayerShockState.__table__,
                PlayerRecoveryState.__table__,
                PlayerLifeEventHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step35-int-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Step35 Integration Tester",
            cash=Decimal("980.00"),
            debt_xgp=Decimal("1100.00"),
            stress=64,
            health=74,
            hours_available=16,
            region="downtown",
            main_job="delivery_driver",
            productivity_modifier=Decimal("0.91"),
            burnout_risk=Decimal("0.22"),
        )
        self.db.add(self.player)
        self.db.flush()

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
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="delivery_driver",
                skill_level=1,
                monthly_pay_xgp=Decimal("2900.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("10.00"),
                productivity_modifier=Decimal("0.91"),
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
                side_income_hours=Decimal("2.0"),
                did_settlement=False,
                stress_start=64,
                stress_end=64,
                health_start=74,
                health_end=74,
                cash_start=Decimal("980.0000"),
                cash_end=Decimal("980.0000"),
            )
        )
        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("980.00"),
                monthly_utilities_cost_xgp=Decimal("150.00"),
                monthly_transport_base_xgp=Decimal("195.00"),
                commute_mode="car",
                active_flag=True,
            )
        )

        self.db.add(
            RegionPopulationState(
                region_key="downtown",
                active_population_score=Decimal("76.0"),
                opportunity_density_score=Decimal("79.0"),
                congestion_score=Decimal("74.0"),
                housing_pressure_score=Decimal("78.0"),
                business_competition_score=Decimal("72.0"),
                consumer_flow_score=Decimal("80.0"),
                recent_growth_direction="rising",
                last_updated_on=1,
            )
        )

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.9"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.4"),
                oil_index=Decimal("112.0"),
                consumer_confidence=Decimal("48.0"),
                supply_chain_stress=Decimal("1.05"),
                event_headline="Step35 integration baseline",
                event_summary="Baseline macro for personal shock integration test.",
            )
        )
        for basket_type, price in {
            BasketType.essentials: Decimal("10.5"),
            BasketType.protein: Decimal("11.6"),
            BasketType.produce: Decimal("10.9"),
            BasketType.convenience: Decimal("9.8"),
        }.items():
            self.db.add(
                BasketDailyPrice(
                    day=1,
                    basket_type=basket_type,
                    price_index=price,
                    daily_change_pct=Decimal("0.20"),
                    supply_pressure=Decimal("1.02"),
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

    def test_day_run_exposes_personal_shock_outputs_and_debug_chain(self) -> None:
        # Run multiple days so world-memory/planning can consume personal patterns.
        last_result = None
        for _ in range(4):
            last_result = run_player_next_day(self.db, str(self.player.id))
        assert last_result is not None

        self.assertIn("personal_shock_summary", last_result)
        self.assertIn("personal_shock_impacts", last_result)
        self.assertIn("personal_shock_recent_event", last_result)
        self.assertIn("personal_shock_recovery_state", last_result)
        self.assertIn("personal_shock_profile", last_result)
        self.assertIn("personal_shock_risk_state", last_result)
        self.assertIn("personal_shock_practical_actions", last_result)

        debug_snapshot = get_full_player_debug_snapshot(self.db, str(self.player.id))
        self.assertIn("personal_shock_profile", debug_snapshot)
        self.assertIn("personal_shock_risk_state", debug_snapshot)
        self.assertIn("personal_recent_life_event", debug_snapshot)
        self.assertIn("personal_recovery_state", debug_snapshot)
        self.assertIn("personal_resilience_summary", debug_snapshot)
        self.assertIn("personal_shock_summary", debug_snapshot)

        recommendation = build_player_strategy_recommendation(self.db, str(self.player.id))
        self.assertIn("debug_meta", recommendation)
        self.assertIn("shock_risk_score", recommendation["debug_meta"])

        player_patterns = build_player_pattern_summary(self.db, str(self.player.id))
        self.assertIn("dominant_player_pattern", player_patterns)
        self.assertIn("suggested_correction", player_patterns)


if __name__ == "__main__":
    unittest.main()
