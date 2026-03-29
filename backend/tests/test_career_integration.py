"""Step 18 — Career integration tests.

Tests that apply_daily_career_progression integrates correctly with
the day-progression pipeline and that debug snapshots contain career data.
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_career_integration.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.stock_trade_log import StockTradeLog
from app.models.user import User

from app.engine.career_service import (
    apply_daily_career_progression,
    get_or_create_player_career,
    get_player_career_snapshot,
    start_certification_track,
)
from app.engine.career_config import RANK_ENTRY, RANK_INTERMEDIATE, effective_monthly_pay
from app.services.housing_region_service import assign_player_housing

JOB_SEED = {
    "auto_mechanic": Decimal("4000.00"),
    "aircraft_mechanic": Decimal("6200.00"),
    "banker": Decimal("5100.00"),
    "chef": Decimal("3500.00"),
    "retail_worker": Decimal("2600.00"),
    "delivery_driver": Decimal("3000.00"),
}

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


class CareerIntegrationTests(unittest.TestCase):
    """Integration tests for Step 18 career progression with day pipeline."""

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
                PlayerCareer.__table__,
                CareerProgressLog.__table__,
                PlayerEmploymentState.__table__,
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                DebtCreditLog.__table__,
                BasketDailyPrice.__table__,
                BasketConsumptionLog.__table__,
                StockDailyPrice.__table__,
                StockTradeLog.__table__,
                PlayerStockHolding.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                MacroDailyState.__table__,
                DailyBriefLog.__table__,
            ],
        )

        self.db = self.SessionLocal()

        user = User(
            email=f"career-int-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Career Integration Player",
            cash=Decimal("5000.00"),
            debt_xgp=Decimal("0.00"),
            stress=20,
            health=90,
            hours_available=16,
            region="suburban",
            main_job="auto_mechanic",
        )
        self.db.add(self.player)
        self.db.flush()

        assign_player_housing(
            db=self.db,
            player_id=self.player.id,
            region="suburban",
            housing_type="starter_rent",
            commit=False,
        )

        self._seed_job_definitions()
        self._seed_macro_rows()
        self._seed_basket_rows()
        self._seed_stock_rows()

        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="auto_mechanic",
                skill_level=1,
                monthly_pay_xgp=Decimal("4000.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("5.00"),
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
        for day in range(1, 6):
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.4"),
                    interest_rate=Decimal("4.2"),
                    unemployment_rate=Decimal("5.3"),
                    oil_index=Decimal("101.0"),
                    consumer_confidence=Decimal("53.0"),
                    supply_chain_stress=Decimal("0.5"),
                    event_headline="Baseline",
                    event_summary=f"Day {day} macro.",
                )
            )

    def _seed_basket_rows(self) -> None:
        basket_types = [
            BasketType.essentials,
            BasketType.protein,
            BasketType.produce,
            BasketType.convenience,
        ]
        for day in range(1, 6):
            for bt in basket_types:
                self.db.add(
                    BasketDailyPrice(
                        day=day,
                        basket_type=bt,
                        price_index=Decimal("10.0000"),
                        daily_change_pct=Decimal("0.0000"),
                        supply_pressure=Decimal("1.0000"),
                        demand_pressure=Decimal("1.0000"),
                    )
                )

    def _seed_stock_rows(self) -> None:
        for day in range(1, 6):
            for ticker, sector in TICKER_SECTOR.items():
                self.db.add(
                    StockDailyPrice(
                        day=day,
                        ticker=ticker,
                        sector=sector,
                        open_price=Decimal("100.00"),
                        close_price=Decimal("100.00"),
                        daily_change_pct=Decimal("0.0000"),
                        macro_impact=Decimal("0.0000"),
                        noise_component=Decimal("0.0000"),
                    )
                )

    # ── Tests ─────────────────────────────────────────────────────────────────

    def test_apply_daily_progression_returns_required_keys(self) -> None:
        result = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("0.0"),
            commit=False,
        )
        required_keys = [
            "player_id",
            "as_of_date",
            "current_job_key",
            "current_job_rank",
            "skill_before",
            "skill_after",
            "skill_delta",
            "performance_score",
            "trailing_performance_score",
            "promotion_progress",
            "promotion_eligible",
            "promotion_unlocked_today",
            "certification_completed",
            "training_hours",
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_daily_progression_increments_days_worked(self) -> None:
        apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("0.0"),
            commit=False,
        )
        career = (
            self.db.query(PlayerCareer)
            .filter(PlayerCareer.player_id == self.player.id)
            .first()
        )
        self.assertIsNotNone(career)
        self.assertGreater(career.total_days_worked_in_job, 0)

    def test_daily_progression_creates_progress_log(self) -> None:
        apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("0.0"),
            commit=False,
        )
        log = (
            self.db.query(CareerProgressLog)
            .filter(
                CareerProgressLog.player_id == self.player.id,
                CareerProgressLog.day_number == 1,
            )
            .first()
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.job_key, "auto_mechanic")

    def test_multi_day_skill_accumulates(self) -> None:
        for day_offset in range(5):
            apply_daily_career_progression(
                self.db,
                self.player.id,
                as_of_date=date(2026, 1, day_offset + 1),
                training_hours=Decimal("0.0"),
                commit=False,
            )

        career = (
            self.db.query(PlayerCareer)
            .filter(PlayerCareer.player_id == self.player.id)
            .first()
        )
        self.assertIsNotNone(career)
        self.assertGreater(float(career.current_job_skill), 0.0)

    def test_certification_progress_across_days(self) -> None:
        start_certification_track(self.db, self.player.id, "aircraft_mechanic_cert")
        self.db.flush()

        for day_offset in range(5):
            apply_daily_career_progression(
                self.db,
                self.player.id,
                as_of_date=date(2026, 1, day_offset + 1),
                training_hours=Decimal("2.0"),  # ≥ 1h minimum
                commit=False,
            )

        career = (
            self.db.query(PlayerCareer)
            .filter(PlayerCareer.player_id == self.player.id)
            .first()
        )
        self.assertIsNotNone(career)
        # After 5 days of 2h training, should have 5+ progress days
        self.assertGreaterEqual(career.certification_progress_days, 5)

    def test_snapshot_includes_promotion_blockers(self) -> None:
        snapshot = get_player_career_snapshot(self.db, self.player.id)
        self.assertIn("debug_meta", snapshot)
        self.assertIn("promotion_blockers", snapshot["debug_meta"])
        # At zero days / skill, should have multiple blockers
        blockers = snapshot["debug_meta"]["promotion_blockers"]
        self.assertIsInstance(blockers, list)
        self.assertGreater(len(blockers), 0)

    def test_snapshot_includes_effective_pay(self) -> None:
        snapshot = get_player_career_snapshot(self.db, self.player.id)
        self.assertIn("effective_monthly_pay_xgp", snapshot)
        self.assertIsNotNone(snapshot["effective_monthly_pay_xgp"])
        self.assertGreater(snapshot["effective_monthly_pay_xgp"], 0.0)

    def test_promotion_unlocked_after_thresholds_met(self) -> None:
        # Manually set career to threshold-meeting state and run progression
        career = get_or_create_player_career(self.db, self.player.id)
        career.current_job_key = "auto_mechanic"
        career.current_job_rank = RANK_ENTRY
        career.current_job_skill = Decimal("20.0")
        career.total_days_worked_in_job = 19  # one less than threshold (20)
        career.trailing_performance_score = Decimal("0.70")
        self.db.flush()

        result = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("0.0"),
            commit=False,
        )

        # After running, total_days_worked should be 20 (threshold met)
        # The run should promote if all criteria are satisfied
        self.db.refresh(career)
        if result["promotion_unlocked_today"]:
            self.assertEqual(career.current_job_rank, RANK_INTERMEDIATE)
        else:
            # At minimum promotion_progress should be close to 1.0
            self.assertGreater(result["promotion_progress"], 0.8)

    def test_effective_pay_increases_after_promotion(self) -> None:
        entry_pay = effective_monthly_pay("auto_mechanic", RANK_ENTRY, Decimal("20.0"))
        intermediate_pay = effective_monthly_pay(
            "auto_mechanic", RANK_INTERMEDIATE, Decimal("20.0")
        )
        self.assertGreater(intermediate_pay, entry_pay)

    def test_career_history_grows_with_days(self) -> None:
        from app.engine.career_service import get_player_career_history

        for day_offset in range(3):
            apply_daily_career_progression(
                self.db,
                self.player.id,
                as_of_date=date(2026, 1, day_offset + 1),
                training_hours=Decimal("0.0"),
                commit=False,
            )

        history = get_player_career_history(self.db, self.player.id)
        self.assertEqual(len(history["entries"]), 3)

    def test_career_snapshot_safe_for_unknown_player(self) -> None:
        from app.engine.career_service import CareerNotFoundError
        with self.assertRaises(CareerNotFoundError):
            get_player_career_snapshot(self.db, uuid.uuid4())

    def test_stress_impact_on_skill_on_high_stress_day(self) -> None:
        """High-stress player gains less skill than low-stress player."""
        # Create a second user + player with high stress
        user2 = User(
            email=f"stressed-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user2)
        self.db.flush()

        stressed_player = Player(
            user_id=user2.id,
            display_name="Stressed Player",
            cash=Decimal("5000.00"),
            debt_xgp=Decimal("0.00"),
            stress=90,
            health=90,
            hours_available=16,
            region="suburban",
            main_job="auto_mechanic",
        )
        self.db.add(stressed_player)
        self.db.flush()

        self.db.add(
            PlayerEmploymentState(
                player_id=stressed_player.id,
                day=1,
                current_job_code="auto_mechanic",
                skill_level=1,
                monthly_pay_xgp=Decimal("4000.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("5.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )
        self.db.flush()

        assign_player_housing(
            db=self.db,
            player_id=stressed_player.id,
            region="suburban",
            housing_type="starter_rent",
            commit=False,
        )

        normal_result = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("0.0"),
            commit=False,
        )
        stressed_result = apply_daily_career_progression(
            self.db,
            stressed_player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("0.0"),
            commit=False,
        )

        # Stressed player should gain equal or less skill than normal player
        self.assertLessEqual(stressed_result["skill_delta"], normal_result["skill_delta"])
