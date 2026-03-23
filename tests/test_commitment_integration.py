import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_commitment_integration.db")

from app.api.internal import get_internal_player_snapshot
from app.db.database import Base
from app.engine.commitment_service import activate_player_commitment, build_available_commitments
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
from app.models.job_action import JobAction
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_career import PlayerCareer
from app.models.player_commitment_history import PlayerCommitmentHistory
from app.models.player_commitment_state import PlayerCommitmentState
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_goal_history import PlayerGoalHistory
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.side_income_action import SideIncomeAction
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


class CommitmentIntegrationTests(unittest.TestCase):
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
                JobAction.__table__,
                SideIncomeAction.__table__,
                PlayerCareer.__table__,
                CareerProgressLog.__table__,
                PlayerProgressionState.__table__,
                PlayerGoalHistory.__table__,
                PlayerCommitmentState.__table__,
                PlayerCommitmentHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"commitment-int-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Commitment Integration",
            cash=Decimal("1250.00"),
            debt_xgp=Decimal("400.00"),
            credit_score=662,
            stress=30,
            health=95,
            hours_available=16,
            region="suburban",
            main_job="banker",
            required_daily_debt_payment_xgp=Decimal("20.00"),
            distress_score=Decimal("22.00"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.2"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.2"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Commitment baseline",
                event_summary="Baseline macro row for commitment integration tests.",
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
                monthly_pay_xgp=Decimal("3000.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )
        self.db.add(PlayerCareer(player_id=self.player.id, current_job_key="banker"))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_day_run_includes_commitment_summary_payload(self) -> None:
        settle_player_day(self.db, str(self.player.id))
        result = run_player_next_day(self.db, str(self.player.id))

        self.assertIn("commitment_summary", result)
        summary = result["commitment_summary"] or {}
        self.assertIn("active_commitment", summary)
        self.assertIn("player_id", summary)

    def test_active_commitment_updates_and_debug_chain_visible(self) -> None:
        settle_player_day(self.db, str(self.player.id))
        run_player_next_day(self.db, str(self.player.id))

        available = build_available_commitments(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertGreaterEqual(len(available["items"]), 1)
        selected = available["items"][0]["commitment_key"]
        activated = activate_player_commitment(
            db=self.db,
            player_id=str(self.player.id),
            commitment_key=selected,
            duration_days=5,
            as_of_date=date(2026, 1, 1),
        )
        self.assertEqual(activated["status"], "active")
        self.db.commit()

        result = run_player_next_day(self.db, str(self.player.id))
        commitment_summary = result.get("commitment_summary") or {}
        active_commitment = commitment_summary.get("active_commitment") or {}
        self.assertEqual(active_commitment.get("status"), "active")
        self.assertEqual(active_commitment.get("commitment_key"), selected)

        snapshot = get_internal_player_snapshot(player_id=str(self.player.id), db=self.db).model_dump()
        self.assertIn("commitment_state", snapshot)
        self.assertIn("commitment_history", snapshot)
        self.assertIn("commitment_available", snapshot)
        self.assertIn("commitment_summary", snapshot)
        self.assertIn("commitment_feedback", snapshot)
        self.assertIn("commitment_drift_debug", snapshot)
        self.assertIn("commitment_adherence_debug", snapshot)


if __name__ == "__main__":
    unittest.main()
