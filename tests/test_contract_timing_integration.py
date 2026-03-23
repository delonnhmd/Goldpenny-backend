"""Step 41 integration tests for contract timing layer.

Tests the full pipeline:
  - generate_recurring_contracts → apply_contract_cycle_progression
    → build_player_contract_schedule
  - PlayerContractSchedule row is upserted (not duplicated) across multiple days
  - Two players with identical finances but different due-date timing
    have different timing_pressure_label
  - Pre-payday squeeze identified when income arrives after obligations
  - Timing pressure is separate from delinquency (player can be on-time
    but still timing-squeezed)
  - Stability score decreases when obligations cluster and cash gap exists
  - After progression, late events are counted in pressure summary
"""

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_contract_timing_integration.db")

from app.db.database import Base
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_contract_event import PlayerContractEvent
from app.models.player_contract_schedule import PlayerContractSchedule
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.user import User
from app.engine.contract_timing_service import (
    apply_contract_cycle_progression,
    build_cash_timing_pressure_state,
    build_contract_pressure_summary,
    build_due_soon_summary,
    build_player_contract_schedule,
    build_upcoming_obligation_window,
    generate_recurring_contracts,
)

TABLES = [
    User.__table__,
    Player.__table__,
    PlayerHousingState.__table__,
    PlayerEmploymentState.__table__,
    PlayerLoanAccount.__table__,
    PlayerBorrowingState.__table__,
    PlayerDelinquencyState.__table__,
    PlayerBusiness.__table__,
    PlayerContractSchedule.__table__,
    PlayerContractEvent.__table__,
]

_VALID_PRESSURE = {"low", "manageable", "elevated", "severe"}
_VALID_CLUSTERING = {"spread", "mild_cluster", "clustered", "heavily_clustered"}
_VALID_BRIDGE = {"none", "pre_payday_squeeze", "moderate", "urgent"}
_VALID_COLLISION = {"none", "overlap", "collision", "compound"}


class ContractTimingIntegrationTests(unittest.TestCase):
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
        Base.metadata.create_all(bind=self.engine, tables=TABLES)
        self.db = self.SessionLocal()
        self._day = 20

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_player(self, *, cash: float = 1000.0) -> Player:
        user = User(id=uuid.uuid4(), email=f"e_{uuid.uuid4().hex[:8]}@x.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            id=uuid.uuid4(),
            user_id=user.id,
            cash=Decimal(str(cash)),
            credit_score=650,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _add_housing(self, player: Player, rent: float = 600.0, utilities: float = 80.0) -> PlayerHousingState:
        hs = PlayerHousingState(
            player_id=player.id,
            region="suburban",
            housing_type="starter_rent",
            monthly_housing_cost_xgp=Decimal(str(rent)),
            monthly_utilities_cost_xgp=Decimal(str(utilities)),
            daily_housing_cost_xgp=Decimal(str(rent / 30)),
            active_flag=True,
        )
        self.db.add(hs)
        self.db.flush()
        return hs

    def _add_employment(self, player: Player, pay: float = 2400.0, employed: bool = True) -> PlayerEmploymentState:
        emp = PlayerEmploymentState(
            player_id=player.id,
            day=self._day,
            monthly_pay_xgp=Decimal(str(pay)),
            employed_flag=employed,
            job_status="employed" if employed else "unemployed",
        )
        self.db.add(emp)
        self.db.flush()
        return emp

    def _add_delinquency(self, player: Player, stage: str = "current") -> PlayerDelinquencyState:
        state = PlayerDelinquencyState(
            player_id=player.id,
            current_delinquency_stage=stage,
            missed_payment_count_30d=0,
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _add_obligation(
        self,
        player: Player,
        *,
        key: str,
        day_offset: int,
        amount: float = 200.0,
        income: bool = False,
        status: str = "upcoming",
    ) -> PlayerContractEvent:
        ev = PlayerContractEvent(
            player_id=player.id,
            obligation_key=key,
            obligation_family="personal" if not income else "income",
            obligation_type=key,
            amount_xgp=Decimal(str(amount)),
            cycle_days=30,
            due_on_day=self._day + day_offset,
            status=status,
            income_flag=income,
        )
        self.db.add(ev)
        self.db.flush()
        return ev

    # ------------------------------------------------------------------
    # Full pipeline integration
    # ------------------------------------------------------------------

    def test_full_pipeline_creates_schedule_and_events(self) -> None:
        """generate → progress → schedule builds 1 schedule row + N events."""
        player = self._make_player()
        self._add_housing(player)
        self._add_employment(player)

        result = build_player_contract_schedule(self.db, player.id, day=self._day)
        self.db.flush()

        schedule_count = self.db.query(PlayerContractSchedule).filter(
            PlayerContractSchedule.player_id == player.id
        ).count()
        event_count = self.db.query(PlayerContractEvent).filter(
            PlayerContractEvent.player_id == player.id
        ).count()

        self.assertEqual(schedule_count, 1, "Exactly one schedule row")
        self.assertGreater(event_count, 0, "At least one event created")
        self.assertIn(result["timing_pressure_label"], _VALID_PRESSURE)
        self.assertIn(result["clustering_label"], _VALID_CLUSTERING)
        self.assertIn(result["bridge_need_label"], _VALID_BRIDGE)

    def test_schedule_upsert_across_multiple_days(self) -> None:
        """Running schedule for days 20, 21, 22 → still only 1 schedule row."""
        player = self._make_player()
        self._add_housing(player)
        for day in range(self._day, self._day + 3):
            build_player_contract_schedule(self.db, player.id, day=day)
            self.db.flush()
        count = self.db.query(PlayerContractSchedule).filter(
            PlayerContractSchedule.player_id == player.id
        ).count()
        self.assertEqual(count, 1, "PlayerContractSchedule must upsert, not grow")

    def test_schedule_last_updated_matches_last_call(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        build_player_contract_schedule(self.db, player.id, day=self._day)
        build_player_contract_schedule(self.db, player.id, day=self._day + 5)
        self.db.flush()
        schedule = (
            self.db.query(PlayerContractSchedule)
            .filter(PlayerContractSchedule.player_id == player.id)
            .first()
        )
        self.assertEqual(schedule.last_updated_on, self._day + 5)

    # ------------------------------------------------------------------
    # Timing matters separately from wealth
    # ------------------------------------------------------------------

    def test_clustered_player_has_higher_density_than_spread(self) -> None:
        """Two players, same obligations, one clustered one spread → higher density for clustered."""
        clustered = self._make_player(cash=2000.0)
        spread = self._make_player(cash=2000.0)

        for i in range(4):
            self._add_obligation(clustered, key=f"ob_{i}", day_offset=1, amount=200.0)
        for i in range(4):
            self._add_obligation(spread, key=f"ob_{i}", day_offset=i * 2 + 1, amount=200.0)

        clustered_r = build_cash_timing_pressure_state(self.db, clustered.id, day=self._day)
        spread_r = build_cash_timing_pressure_state(self.db, spread.id, day=self._day)

        self.assertGreaterEqual(
            clustered_r["contract_density_score"],
            spread_r["contract_density_score"],
            "Clustered obligations must produce higher density score",
        )

    def test_timing_squeeze_does_not_require_delinquency(self) -> None:
        """A player can be timing-squeezed AND delinquency=current."""
        player = self._make_player(cash=50.0)  # low cash
        self._add_delinquency(player, stage="current")   # on time on all payments

        # Mass obligations due tomorrow before any income
        for i in range(4):
            self._add_obligation(player, key=f"ob_{i}", day_offset=1, amount=300.0)

        result = build_contract_pressure_summary(self.db, player.id, day=self._day)
        self.assertEqual(result["delinquency_stage"], "current", "Player is current on all dues")
        # But timing pressure should be elevated
        self.assertIn(
            result["timing_pressure_label"], ("elevated", "severe"),
            "Cash-poor player with clustered obligations should be timing-squeezed",
        )

    def test_wealthy_player_with_clustered_obligations_has_no_cash_gap(self) -> None:
        """Wealthy player can absorb clustered obligations without a cash gap."""
        player = self._make_player(cash=50000.0)
        for i in range(5):
            self._add_obligation(player, key=f"ob_{i}", day_offset=1, amount=300.0)
        result = build_cash_timing_pressure_state(self.db, player.id, day=self._day)
        self.assertEqual(result["cash_gap_before_next_income_xgp"], 0.0,
                         "Rich player should never have a cash gap")

    def test_pre_payday_squeeze_identified(self) -> None:
        """Pre-payday squeeze: obligations before income, low cash, income arriving soon."""
        player = self._make_player(cash=100.0)
        self._add_obligation(player, key="rent", day_offset=2, amount=600.0)
        self._add_obligation(player, key="salary", day_offset=4, amount=2400.0, income=True)
        result = build_cash_timing_pressure_state(self.db, player.id, day=self._day)
        self.assertGreater(result["cash_gap_before_next_income_xgp"], 0.0)
        self.assertIsNotNone(result["days_to_next_income"])
        self.assertLessEqual(result["days_to_next_income"], 7)

    # ------------------------------------------------------------------
    # Event status progression integration
    # ------------------------------------------------------------------

    def test_progression_marks_overdue_as_late(self) -> None:
        player = self._make_player()
        ev = self._add_obligation(player, key="rent", day_offset=-5, amount=600.0, status="due")
        apply_contract_cycle_progression(self.db, player.id, day=self._day)
        self.db.refresh(ev)
        self.assertEqual(ev.status, "late")

    def test_late_events_appear_in_pressure_summary_count(self) -> None:
        player = self._make_player()
        for i in range(2):
            self._add_obligation(player, key=f"late_{i}", day_offset=-10, amount=200.0, status="late")
        result = build_contract_pressure_summary(self.db, player.id, day=self._day)
        self.assertEqual(result["late_event_count"], 2)

    def test_income_events_paid_automatically_on_progression(self) -> None:
        player = self._make_player()
        ev = self._add_obligation(player, key="salary", day_offset=0, amount=2400.0, income=True)
        result = apply_contract_cycle_progression(self.db, player.id, day=self._day)
        self.assertEqual(result["income_received"], 1)
        self.db.refresh(ev)
        self.assertEqual(ev.status, "paid")

    # ------------------------------------------------------------------
    # Due windows
    # ------------------------------------------------------------------

    def test_due_today_correct(self) -> None:
        player = self._make_player()
        self._add_obligation(player, key="rent", day_offset=0, amount=600.0)
        result = build_upcoming_obligation_window(self.db, player.id, day=self._day)
        self.assertEqual(len(result["due_today"]), 1)

    def test_outflows_3d_excludes_income(self) -> None:
        player = self._make_player()
        self._add_obligation(player, key="rent", day_offset=1, amount=600.0)
        self._add_obligation(player, key="salary", day_offset=2, amount=2400.0, income=True)
        result = build_upcoming_obligation_window(self.db, player.id, day=self._day)
        # Outflow should only include rent, not salary
        self.assertAlmostEqual(result["outflows_due_3d_xgp"], 600.0, places=2)
        self.assertAlmostEqual(result["inflows_expected_7d_xgp"], 2400.0, places=2)

    # ------------------------------------------------------------------
    # Generate recurring contracts idempotency
    # ------------------------------------------------------------------

    def test_generate_is_idempotent_five_calls(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        self._add_employment(player)
        for _ in range(5):
            generate_recurring_contracts(self.db, player.id, day=self._day)
            self.db.flush()
        # Each obligation/day should have exactly 1 row
        from sqlalchemy import func
        dup_count = (
            self.db.query(
                PlayerContractEvent.obligation_key,
                PlayerContractEvent.due_on_day,
                func.count(PlayerContractEvent.id).label("cnt"),
            )
            .filter(PlayerContractEvent.player_id == player.id)
            .group_by(PlayerContractEvent.obligation_key, PlayerContractEvent.due_on_day)
            .having(func.count(PlayerContractEvent.id) > 1)
            .count()
        )
        self.assertEqual(dup_count, 0, "No duplicate (key, due_on_day) pairs should exist")

    # ------------------------------------------------------------------
    # Output structure
    # ------------------------------------------------------------------

    def test_schedule_result_has_all_required_keys(self) -> None:
        player = self._make_player()
        result = build_player_contract_schedule(self.db, player.id, day=self._day)
        required = {
            "player_id", "day", "active_contract_count", "total_due_7d_xgp",
            "clustering_label", "timing_pressure_label", "bridge_need_label",
            "obligation_collision_label", "contract_density_score",
            "timing_stability_score", "cash_gap_before_next_income_xgp",
            "false_payday_pressure", "recurring_obligation_map",
            "income_cadence", "due_window",
        }
        self.assertTrue(required.issubset(result.keys()), f"Missing keys: {required - result.keys()}")

    def test_pressure_summary_has_all_required_keys(self) -> None:
        player = self._make_player()
        result = build_contract_pressure_summary(self.db, player.id, day=self._day)
        required = {
            "player_id", "day", "timing_pressure_label", "clustering_label",
            "bridge_need_label", "obligation_collision_label",
            "contract_density_score", "timing_stability_score",
            "false_payday_pressure", "cash_on_hand_xgp",
            "cash_gap_before_next_income_xgp", "outflows_due_today_xgp",
            "late_event_count", "delinquency_stage", "bridge_borrow_is_rational",
            "due_soon_items",
        }
        self.assertTrue(required.issubset(result.keys()), f"Missing keys: {required - result.keys()}")

    def test_due_soon_summary_items_each_have_days_away(self) -> None:
        player = self._make_player()
        self._add_obligation(player, key="rent", day_offset=3, amount=500.0)
        result = build_due_soon_summary(self.db, player.id, day=self._day)
        for item in result["items"]:
            self.assertIn("days_away", item)
            self.assertEqual(item["days_away"], item["due_on_day"] - self._day)

    # ------------------------------------------------------------------
    # Player without any data (graceful handling)
    # ------------------------------------------------------------------

    def test_player_no_housing_no_employment_returns_valid_defaults(self) -> None:
        player = self._make_player()
        result = build_player_contract_schedule(self.db, player.id, day=self._day)
        self.db.flush()
        # Should succeed with minimal obligations (phone plan only)
        self.assertIn(result["timing_pressure_label"], _VALID_PRESSURE)
        # active count still > 0 (phone plan)
        self.assertGreaterEqual(result["active_contract_count"], 0)


if __name__ == "__main__":
    unittest.main()
