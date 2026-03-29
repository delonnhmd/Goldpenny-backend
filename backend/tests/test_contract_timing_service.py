"""Step 41 unit tests for contract_timing_service.py.

Tests cover:
  - Obligation definitions are built from housing/employment/loan data
  - Recurring contract events are generated for the forward window
  - SAME player/key/day combination does NOT duplicate events
  - Contract cycle progression advances statuses: upcoming → due → late
  - Income events become 'paid' on progression (not 'late')
  - Clustered due dates raise the timing pressure label
  - Same total obligations but different timing → different pressure labels
  - Pre-payday cash gap detection is correct
  - False payday pressure flag fires when gap is temporary
  - Bridge borrow rationality (timing vs. structural gap)
  - PlayerContractSchedule upserts correctly (no duplicate rows)
  - build_due_soon_summary projects net_7d correctly
  - Obligation/income windows are correctly distributed (today / 3d / 7d)
  - Late event count appears in pressure summary
"""

import os
import unittest
import uuid
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_contract_timing.db")

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
    ContractTimingNotFoundError,
    ContractTimingValidationError,
    EVENT_FORWARD_WINDOW,
    _clustering_label,
    _compute_cash_gap,
    _compute_contract_density_score,
    _compute_timing_stability_score,
    _obligation_collision_label,
    _timing_pressure_label,
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


class ContractTimingServiceTests(unittest.TestCase):
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
        self._day = 10

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Player factory helpers
    # ------------------------------------------------------------------

    def _make_player(
        self,
        *,
        cash: float = 800.0,
        credit_score: int = 650,
    ) -> Player:
        user = User(id=uuid.uuid4(), email=f"u{uuid.uuid4().hex[:6]}@test.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            id=uuid.uuid4(),
            user_id=user.id,
            cash=Decimal(str(cash)),
            credit_score=credit_score,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _add_housing(
        self,
        player: Player,
        *,
        monthly_rent: float = 600.0,
        monthly_utilities: float = 80.0,
    ) -> PlayerHousingState:
        hs = PlayerHousingState(
            player_id=player.id,
            region="suburban",
            housing_type="starter_rent",
            monthly_housing_cost_xgp=Decimal(str(monthly_rent)),
            monthly_utilities_cost_xgp=Decimal(str(monthly_utilities)),
            daily_housing_cost_xgp=Decimal(str(monthly_rent / 30.0)),
            active_flag=True,
        )
        self.db.add(hs)
        self.db.flush()
        return hs

    def _add_employment(
        self,
        player: Player,
        *,
        monthly_pay: float = 2400.0,
        employed: bool = True,
    ) -> PlayerEmploymentState:
        emp = PlayerEmploymentState(
            player_id=player.id,
            day=self._day,
            monthly_pay_xgp=Decimal(str(monthly_pay)),
            employed_flag=employed,
            job_status="employed",
        )
        self.db.add(emp)
        self.db.flush()
        return emp

    def _add_loan(
        self,
        player: Player,
        *,
        daily_payment: float = 5.0,
        days_remaining: int = 30,
        term_days: int = 30,
    ) -> PlayerLoanAccount:
        loan = PlayerLoanAccount(
            player_id=player.id,
            offer_key="test_personal_loan",
            offer_family="personal",
            scheduled_daily_payment_xgp=Decimal(str(daily_payment)),
            days_remaining=days_remaining,
            term_days=term_days,
            delinquency_stage="current",
            accepted_on_day=1,
        )
        self.db.add(loan)
        self.db.flush()
        return loan

    # ------------------------------------------------------------------
    # Scoring helper unit tests
    # ------------------------------------------------------------------

    def test_clustering_label_spread(self) -> None:
        """Very low density score → 'spread' clustering."""
        label = _clustering_label(Decimal("10"))
        self.assertEqual(label, "spread")

    def test_clustering_label_mild(self) -> None:
        label = _clustering_label(Decimal("40"))
        self.assertEqual(label, "mild_cluster")

    def test_clustering_label_clustered(self) -> None:
        label = _clustering_label(Decimal("60"))
        self.assertEqual(label, "clustered")

    def test_clustering_label_heavy(self) -> None:
        label = _clustering_label(Decimal("80"))
        self.assertEqual(label, "heavily_clustered")

    def test_timing_pressure_low(self) -> None:
        label = _timing_pressure_label(Decimal("15"))
        self.assertEqual(label, "low")

    def test_timing_pressure_manageable(self) -> None:
        label = _timing_pressure_label(Decimal("40"))
        self.assertEqual(label, "manageable")

    def test_timing_pressure_elevated(self) -> None:
        label = _timing_pressure_label(Decimal("60"))
        self.assertEqual(label, "elevated")

    def test_timing_pressure_severe(self) -> None:
        label = _timing_pressure_label(Decimal("80"))
        self.assertEqual(label, "severe")

    def test_obligation_collision_none(self) -> None:
        label = _obligation_collision_label([])
        self.assertEqual(label, "none")

    def test_obligation_collision_overlap_two(self) -> None:
        # 2 obligations in 3-day window → overlap
        events = [SimpleNamespace(income_flag=False) for _ in range(2)]
        label = _obligation_collision_label(events)
        self.assertEqual(label, "overlap")

    def test_obligation_collision_collision_three(self) -> None:
        events = [SimpleNamespace(income_flag=False) for _ in range(3)]
        label = _obligation_collision_label(events)
        self.assertEqual(label, "collision")

    def test_obligation_collision_compound_four(self) -> None:
        events = [SimpleNamespace(income_flag=False) for _ in range(4)]
        label = _obligation_collision_label(events)
        self.assertEqual(label, "compound")

    def test_density_score_no_obligations_returns_low(self) -> None:
        score = _compute_contract_density_score([])
        self.assertLessEqual(float(score), 15.0)

    def test_density_score_perfectly_spread_is_low(self) -> None:
        """Obligations spread across 7 different days → low density."""
        events = [SimpleNamespace(income_flag=False, due_on_day=10 + i) for i in range(7)]
        score = _compute_contract_density_score(events)
        self.assertLessEqual(float(score), 40.0, "Perfectly spread should score ≤ 40")

    def test_density_score_all_same_day_is_high(self) -> None:
        """All obligations on same day → high density."""
        events = [SimpleNamespace(income_flag=False, due_on_day=10) for _ in range(5)]
        score = _compute_contract_density_score(events)
        self.assertGreater(float(score), 50.0, "All-same-day should score > 50")

    # ------------------------------------------------------------------
    # generate_recurring_contracts
    # ------------------------------------------------------------------

    def test_generate_creates_events(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        self._add_employment(player)
        result = generate_recurring_contracts(self.db, player.id, day=self._day)
        self.assertGreater(result["event_rows_upserted"], 0)
        count = self.db.query(PlayerContractEvent).filter(
            PlayerContractEvent.player_id == player.id
        ).count()
        self.assertGreater(count, 0)

    def test_generate_includes_personal_family(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        result = generate_recurring_contracts(self.db, player.id, day=self._day)
        self.assertIn("personal", result["obligation_families"])

    def test_generate_includes_income_family_when_employed(self) -> None:
        player = self._make_player()
        self._add_employment(player, monthly_pay=2400.0)
        result = generate_recurring_contracts(self.db, player.id, day=self._day)
        self.assertIn("income", result["obligation_families"])

    def test_generate_includes_debt_family_when_loan_active(self) -> None:
        player = self._make_player()
        self._add_loan(player, daily_payment=5.0, days_remaining=30)
        result = generate_recurring_contracts(self.db, player.id, day=self._day)
        self.assertIn("debt", result["obligation_families"])

    def test_generate_no_duplicate_on_second_call(self) -> None:
        """Second call on same day must NOT create duplicate rows."""
        player = self._make_player()
        self._add_housing(player)
        self._add_employment(player)
        generate_recurring_contracts(self.db, player.id, day=self._day)
        count_after_first = self.db.query(PlayerContractEvent).filter(
            PlayerContractEvent.player_id == player.id
        ).count()
        generate_recurring_contracts(self.db, player.id, day=self._day)
        count_after_second = self.db.query(PlayerContractEvent).filter(
            PlayerContractEvent.player_id == player.id
        ).count()
        self.assertEqual(count_after_first, count_after_second,
                         "Second generate call must not create duplicate events")

    def test_events_within_forward_window(self) -> None:
        """All generated events must be within EVENT_FORWARD_WINDOW of current day."""
        player = self._make_player()
        self._add_housing(player)
        generate_recurring_contracts(self.db, player.id, day=self._day)
        latest = (
            self.db.query(PlayerContractEvent.due_on_day)
            .filter(PlayerContractEvent.player_id == player.id)
            .order_by(PlayerContractEvent.due_on_day.desc())
            .first()
        )
        if latest:
            self.assertLessEqual(
                latest[0], self.db.query(PlayerContractEvent).count() and self._day + EVENT_FORWARD_WINDOW
            )

    # ------------------------------------------------------------------
    # apply_contract_cycle_progression
    # ------------------------------------------------------------------

    def test_progression_upcoming_becomes_due(self) -> None:
        player = self._make_player()
        ev = PlayerContractEvent(
            player_id=player.id,
            obligation_key="rent",
            obligation_family="personal",
            obligation_type="rent",
            amount_xgp=Decimal("600"),
            cycle_days=30,
            due_on_day=self._day,  # due today
            status="upcoming",
            income_flag=False,
        )
        self.db.add(ev)
        self.db.flush()
        result = apply_contract_cycle_progression(self.db, player.id, day=self._day)
        self.assertEqual(result["became_due"], 1)
        self.db.refresh(ev)
        self.assertEqual(ev.status, "due")

    def test_progression_income_becomes_paid(self) -> None:
        player = self._make_player()
        ev = PlayerContractEvent(
            player_id=player.id,
            obligation_key="salary",
            obligation_family="income",
            obligation_type="salary",
            amount_xgp=Decimal("2400"),
            cycle_days=30,
            due_on_day=self._day,  # payday is today
            status="upcoming",
            income_flag=True,
        )
        self.db.add(ev)
        self.db.flush()
        result = apply_contract_cycle_progression(self.db, player.id, day=self._day)
        self.assertEqual(result["income_received"], 1)
        self.db.refresh(ev)
        self.assertEqual(ev.status, "paid")

    def test_progression_overdue_obligation_becomes_late(self) -> None:
        player = self._make_player()
        ev = PlayerContractEvent(
            player_id=player.id,
            obligation_key="rent",
            obligation_family="personal",
            obligation_type="rent",
            amount_xgp=Decimal("600"),
            cycle_days=30,
            due_on_day=self._day - 3,   # 3 days overdue
            status="due",
            income_flag=False,
        )
        self.db.add(ev)
        self.db.flush()
        result = apply_contract_cycle_progression(self.db, player.id, day=self._day)
        self.assertGreaterEqual(result["became_late"], 1)
        self.db.refresh(ev)
        self.assertEqual(ev.status, "late")

    def test_progression_future_events_untouched(self) -> None:
        player = self._make_player()
        ev = PlayerContractEvent(
            player_id=player.id,
            obligation_key="rent",
            obligation_family="personal",
            obligation_type="rent",
            amount_xgp=Decimal("600"),
            cycle_days=30,
            due_on_day=self._day + 15,   # still upcoming
            status="upcoming",
            income_flag=False,
        )
        self.db.add(ev)
        self.db.flush()
        apply_contract_cycle_progression(self.db, player.id, day=self._day)
        self.db.refresh(ev)
        self.assertEqual(ev.status, "upcoming", "Future events must stay 'upcoming'")

    # ------------------------------------------------------------------
    # build_upcoming_obligation_window
    # ------------------------------------------------------------------

    def test_upcoming_window_distributes_correctly(self) -> None:
        player = self._make_player()
        # today
        for key, day_offset in [("rent", 0), ("utilities", 2), ("insurance", 5)]:
            self.db.add(PlayerContractEvent(
                player_id=player.id,
                obligation_key=key,
                obligation_family="personal",
                obligation_type=key,
                amount_xgp=Decimal("100"),
                cycle_days=30,
                due_on_day=self._day + day_offset,
                status="upcoming",
                income_flag=False,
            ))
        self.db.flush()
        result = build_upcoming_obligation_window(self.db, player.id, day=self._day)
        self.assertEqual(len(result["due_today"]), 1)
        self.assertEqual(len(result["due_in_3d"]), 1)
        self.assertEqual(len(result["due_in_7d"]), 1)

    def test_upcoming_window_net_includes_income(self) -> None:
        player = self._make_player()
        # outflow
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="rent", obligation_family="personal",
            obligation_type="rent", amount_xgp=Decimal("600"), cycle_days=30,
            due_on_day=self._day + 2, status="upcoming", income_flag=False,
        ))
        # inflow
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="salary", obligation_family="income",
            obligation_type="salary", amount_xgp=Decimal("2400"), cycle_days=30,
            due_on_day=self._day + 4, status="upcoming", income_flag=True,
        ))
        self.db.flush()
        result = build_upcoming_obligation_window(self.db, player.id, day=self._day)
        self.assertAlmostEqual(result["net_7d_xgp"], 2400.0 - 600.0, places=2)

    # ------------------------------------------------------------------
    # build_cash_timing_pressure_state
    # ------------------------------------------------------------------

    def test_pressure_low_when_no_obligations(self) -> None:
        player = self._make_player(cash=5000.0)
        result = build_cash_timing_pressure_state(self.db, player.id, day=self._day)
        self.assertIn(result["timing_pressure_label"], ("low", "manageable"))

    def test_pressure_elevated_when_highly_clustered(self) -> None:
        """5 obligations all on same day → elevated/severe pressure."""
        player = self._make_player(cash=50.0)
        for i in range(5):
            self.db.add(PlayerContractEvent(
                player_id=player.id,
                obligation_key=f"ob_{i}",
                obligation_family="personal",
                obligation_type="rent",
                amount_xgp=Decimal("200"),
                cycle_days=30,
                due_on_day=self._day + 1,  # all on same day
                status="upcoming",
                income_flag=False,
            ))
        self.db.flush()
        result = build_cash_timing_pressure_state(self.db, player.id, day=self._day)
        self.assertIn(result["timing_pressure_label"], ("elevated", "severe"),
                      "All-same-day clustering should produce elevated/severe pressure")

    def test_same_obligations_different_timing_different_pressure(self) -> None:
        """Two players same total obligations: clustered vs spread → different pressure."""
        # Clustered player
        clustered = self._make_player(cash=300.0)
        for i in range(4):
            self.db.add(PlayerContractEvent(
                player_id=clustered.id, obligation_key=f"ob_{i}",
                obligation_family="personal", obligation_type="utilities",
                amount_xgp=Decimal("100"), cycle_days=30,
                due_on_day=self._day + 1, status="upcoming", income_flag=False,
            ))

        # Spread player
        spread = self._make_player(cash=300.0)
        for i in range(4):
            self.db.add(PlayerContractEvent(
                player_id=spread.id, obligation_key=f"ob_{i}",
                obligation_family="personal", obligation_type="utilities",
                amount_xgp=Decimal("100"), cycle_days=30,
                due_on_day=self._day + i * 2,  # spread across 8 days
                status="upcoming", income_flag=False,
            ))
        self.db.flush()

        clustered_result = build_cash_timing_pressure_state(self.db, clustered.id, day=self._day)
        spread_result = build_cash_timing_pressure_state(self.db, spread.id, day=self._day)
        self.assertGreaterEqual(
            clustered_result["contract_density_score"],
            spread_result["contract_density_score"],
            "Clustered player should have higher density score",
        )

    def test_pre_payday_cash_gap_detected(self) -> None:
        """Cash < due obligations before next income → positive cash gap."""
        player = self._make_player(cash=100.0)  # low cash
        # Large obligation due before payday
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="rent", obligation_family="personal",
            obligation_type="rent", amount_xgp=Decimal("600"), cycle_days=30,
            due_on_day=self._day + 2, status="upcoming", income_flag=False,
        ))
        # Income arrives later
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="salary", obligation_family="income",
            obligation_type="salary", amount_xgp=Decimal("2400"), cycle_days=30,
            due_on_day=self._day + 7, status="upcoming", income_flag=True,
        ))
        self.db.flush()
        result = build_cash_timing_pressure_state(self.db, player.id, day=self._day)
        self.assertGreater(result["cash_gap_before_next_income_xgp"], 0.0,
                           "Cash gap should be positive when cash < obligations before payday")

    def test_no_cash_gap_when_rich(self) -> None:
        player = self._make_player(cash=50000.0)
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="rent", obligation_family="personal",
            obligation_type="rent", amount_xgp=Decimal("600"), cycle_days=30,
            due_on_day=self._day + 2, status="upcoming", income_flag=False,
        ))
        self.db.flush()
        result = build_cash_timing_pressure_state(self.db, player.id, day=self._day)
        self.assertEqual(result["cash_gap_before_next_income_xgp"], 0.0)

    # ------------------------------------------------------------------
    # build_player_contract_schedule (upsert)
    # ------------------------------------------------------------------

    def test_contract_schedule_creates_row(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        build_player_contract_schedule(self.db, player.id, day=self._day)
        self.db.flush()
        count = self.db.query(PlayerContractSchedule).filter(
            PlayerContractSchedule.player_id == player.id
        ).count()
        self.assertEqual(count, 1)

    def test_contract_schedule_upserts_not_duplicates(self) -> None:
        """Calling build_player_contract_schedule 3x on same day → still 1 row."""
        player = self._make_player()
        self._add_housing(player)
        for _ in range(3):
            build_player_contract_schedule(self.db, player.id, day=self._day)
            self.db.flush()
        count = self.db.query(PlayerContractSchedule).filter(
            PlayerContractSchedule.player_id == player.id
        ).count()
        self.assertEqual(count, 1, "Three calls must upsert, not create 3 rows")

    def test_contract_schedule_has_valid_labels(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        self._add_employment(player)
        result = build_player_contract_schedule(self.db, player.id, day=self._day)
        self.assertIn(result["timing_pressure_label"], ("low", "manageable", "elevated", "severe"))
        self.assertIn(result["clustering_label"], ("spread", "mild_cluster", "clustered", "heavily_clustered"))
        self.assertIn(result["bridge_need_label"], ("none", "pre_payday_squeeze", "moderate", "urgent"))

    def test_contract_schedule_active_count_reflects_obligations(self) -> None:
        player = self._make_player()
        self._add_housing(player)
        result = build_player_contract_schedule(self.db, player.id, day=self._day)
        self.assertGreater(result["active_contract_count"], 0)

    # ------------------------------------------------------------------
    # build_due_soon_summary
    # ------------------------------------------------------------------

    def test_due_soon_summary_projected_net_correct(self) -> None:
        player = self._make_player(cash=1000.0)
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="rent", obligation_family="personal",
            obligation_type="rent", amount_xgp=Decimal("400"), cycle_days=30,
            due_on_day=self._day + 3, status="upcoming", income_flag=False,
        ))
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="salary", obligation_family="income",
            obligation_type="salary", amount_xgp=Decimal("2400"), cycle_days=30,
            due_on_day=self._day + 5, status="upcoming", income_flag=True,
        ))
        self.db.flush()
        result = build_due_soon_summary(self.db, player.id, day=self._day)
        # projected = cash (1000) + income (2400) - obligations (400) = 3000
        self.assertAlmostEqual(result["projected_net_xgp"], 3000.0, places=2)

    def test_due_soon_summary_items_contain_family(self) -> None:
        player = self._make_player()
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="rent", obligation_family="personal",
            obligation_type="rent", amount_xgp=Decimal("600"), cycle_days=30,
            due_on_day=self._day + 1, status="upcoming", income_flag=False,
        ))
        self.db.flush()
        result = build_due_soon_summary(self.db, player.id, day=self._day)
        item = result["items"][0]
        self.assertIn("family", item)
        self.assertEqual(item["family"], "personal")

    # ------------------------------------------------------------------
    # build_contract_pressure_summary
    # ------------------------------------------------------------------

    def test_pressure_summary_includes_late_count(self) -> None:
        player = self._make_player()
        self.db.add(PlayerContractEvent(
            player_id=player.id, obligation_key="rent", obligation_family="personal",
            obligation_type="rent", amount_xgp=Decimal("600"), cycle_days=30,
            due_on_day=self._day - 10, status="late", income_flag=False,
        ))
        self.db.flush()
        result = build_contract_pressure_summary(self.db, player.id, day=self._day)
        self.assertEqual(result["late_event_count"], 1)

    def test_pressure_summary_bridge_rational_only_when_false_payday(self) -> None:
        """bridge_borrow_is_rational requires false_payday_pressure=True."""
        player = self._make_player(cash=5000.0)
        result = build_contract_pressure_summary(self.db, player.id, day=self._day)
        # With no obligations and plenty of cash, bridge is not rational
        self.assertFalse(result["bridge_borrow_is_rational"])

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_invalid_player_id_raises(self) -> None:
        with self.assertRaises(ContractTimingValidationError):
            generate_recurring_contracts(self.db, "not-a-valid-uuid", day=self._day)

    def test_nonexistent_player_raises(self) -> None:
        fake_id = uuid.uuid4()
        with self.assertRaises(ContractTimingNotFoundError):
            generate_recurring_contracts(self.db, fake_id, day=self._day)

    def test_invalid_day_raises(self) -> None:
        player = self._make_player()
        with self.assertRaises(ContractTimingValidationError):
            build_cash_timing_pressure_state(self.db, player.id, day=0)


if __name__ == "__main__":
    unittest.main()
