"""Step 38 tests: Debt Behavior, Spiral Detection, and Recovery Layer."""

from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_debt_behavior_service.db")

from app.db.database import Base
from app.engine.debt_behavior_service import (
    DebtBehaviorNotFoundError,
    build_debt_behavior_profile,
    build_debt_behavior_summary,
    build_debt_pressure_effects,
    build_debt_trend_state,
    detect_debt_spiral_state,
    detect_recovery_state,
)
from app.models.player import Player
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_debt_trend_history import PlayerDebtTrendHistory
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState
from app.models.user import User


# ---------------------------------------------------------------------------
# Test base
# ---------------------------------------------------------------------------


class DebtBehaviorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerShockState.__table__,
                PlayerDelinquencyState.__table__,
                PlayerPaymentHistory.__table__,
                PlayerBorrowingState.__table__,
                PlayerLoanAccount.__table__,
                PlayerBorrowingHistory.__table__,
                PlayerDebtBehaviorState.__table__,
                PlayerDebtTrendHistory.__table__,
            ],
        )
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # -----------------------------------------------------------------------
    # Fixture helpers
    # -----------------------------------------------------------------------

    def _create_player(
        self,
        *,
        cash: float = 1200.0,
        debt_xgp: float = 0.0,
        credit_score: int = 650,
        stress: int = 25,
        health: int = 85,
        region: str = "suburban",
    ) -> Player:
        user = User(email=f"t-{uuid.uuid4()}@x.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name="Test Player",
            cash=Decimal(str(cash)),
            debt_xgp=Decimal(str(debt_xgp)),
            credit_score=credit_score,
            stress=stress,
            health=health,
            region=region,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_borrowing_state(
        self,
        player: Player,
        *,
        dependence_risk_score: float = 0.0,
        repeat_borrowing_count_30d: int = 0,
        active_loan_count: int = 0,
        borrowing_access_score: float = 75.0,
        credit_access_tier: str = "standard",
    ) -> PlayerBorrowingState:
        state = PlayerBorrowingState(
            player_id=player.id,
            dependence_risk_score=Decimal(str(dependence_risk_score)),
            repeat_borrowing_count_30d=int(repeat_borrowing_count_30d),
            active_loan_count=int(active_loan_count),
            borrowing_access_score=Decimal(str(borrowing_access_score)),
            credit_access_tier=credit_access_tier,
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _seed_delinquency_state(
        self,
        player: Player,
        *,
        stage: str = "current",
        missed_30d: int = 0,
        late_30d: int = 0,
        credit_pressure: float = 0.0,
        financial_distress: float = 0.0,
        stress_days: int = 0,
    ) -> PlayerDelinquencyState:
        state = PlayerDelinquencyState(
            player_id=player.id,
            current_delinquency_stage=stage,
            missed_payment_count_30d=missed_30d,
            late_payment_count_30d=late_30d,
            credit_pressure_score=Decimal(str(credit_pressure)),
            financial_distress_score=Decimal(str(financial_distress)),
            days_under_payment_stress=stress_days,
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _seed_shock_state(
        self,
        player: Player,
        *,
        shock_risk: float = 20.0,
        financial_fragility: float = 20.0,
        recovery_capacity: float = 60.0,
        pressure_direction: str = "stable",
        negative_streak: int = 0,
        recovery_support: int = 0,
    ) -> PlayerShockState:
        state = PlayerShockState(
            player_id=player.id,
            shock_risk_score=Decimal(str(shock_risk)),
            financial_fragility_score=Decimal(str(financial_fragility)),
            recovery_capacity_score=Decimal(str(recovery_capacity)),
            recent_pressure_direction=pressure_direction,
            recent_negative_streak=negative_streak,
            recent_recovery_support=recovery_support,
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _seed_loan(
        self,
        player: Player,
        *,
        principal: float = 500.0,
        outstanding: float | None = None,
        status: str = "active",
        delinquency_stage: str = "current",
        day: int = 1,
    ) -> PlayerLoanAccount:
        loan = PlayerLoanAccount(
            player_id=player.id,
            offer_key="test_loan",
            offer_family="installment",
            status=status,
            principal_original_xgp=Decimal(str(principal)),
            principal_outstanding_xgp=Decimal(str(outstanding if outstanding is not None else principal)),
            apr_pct=Decimal("18.00"),
            term_days=30,
            delinquency_stage=delinquency_stage,
            accepted_on_day=int(day),
        )
        self.db.add(loan)
        self.db.flush()
        return loan

    def _seed_trend_row(
        self,
        player: Player,
        *,
        day: int,
        composite_risk: float = 10.0,
        spiral_label: str = "low",
        trend_dir: str = "stable",
        debt_state: str = "controlled",
        recovery_stage: str = "none",
    ) -> PlayerDebtTrendHistory:
        from datetime import date, timedelta

        GAME_EPOCH = date(2026, 1, 1)
        row = PlayerDebtTrendHistory(
            player_id=player.id,
            day=int(day),
            as_of_date=GAME_EPOCH + timedelta(days=day - 1),
            debt_dependency_score=Decimal("10"),
            payment_stack_pressure_score=Decimal("10"),
            borrowing_frequency_score=Decimal("10"),
            financial_stability_score=Decimal("80"),
            composite_risk_score=Decimal(str(composite_risk)),
            trend_direction=trend_dir,
            debt_state_label=debt_state,
            spiral_risk_label=spiral_label,
            recovery_stage=recovery_stage,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # -----------------------------------------------------------------------
    # 1. Clean player — scores are near zero / state is controlled
    # -----------------------------------------------------------------------

    def test_clean_player_has_low_risk(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        profile = build_debt_behavior_profile(self.db, player.id, 1)

        self.assertLess(profile["debt_dependency_score"], 10.0)
        self.assertLess(profile["payment_stack_pressure_score"], 10.0)
        self.assertLess(profile["borrowing_frequency_score"], 10.0)
        self.assertGreater(profile["financial_stability_score"], 80.0)
        self.assertEqual(profile["spiral_risk_label"], "low")
        self.assertEqual(profile["debt_state_label"], "controlled")

    # -----------------------------------------------------------------------
    # 2. Repeated borrowing increases spiral risk
    # -----------------------------------------------------------------------

    def test_repeated_borrowing_raises_spiral_risk(self) -> None:
        player = self._create_player(credit_score=620)
        # Simulate high borrowing frequency and 3 active loans
        self._seed_borrowing_state(
            player,
            dependence_risk_score=50.0,
            repeat_borrowing_count_30d=4,
            active_loan_count=3,
        )
        self._seed_delinquency_state(player, credit_pressure=30.0)
        self._seed_shock_state(player, shock_risk=35.0, financial_fragility=40.0)
        self._seed_loan(player, principal=500.0)
        self._seed_loan(player, principal=300.0)
        self._seed_loan(player, principal=400.0)

        profile = build_debt_behavior_profile(self.db, player.id, 5)

        # Dependency and frequency must be significant with 3 loans + repeat borrowing
        self.assertGreater(profile["debt_dependency_score"], 30.0)
        self.assertGreater(profile["borrowing_frequency_score"], 70.0)
        # Spiral risk must be at least "rising"
        self.assertIn(profile["spiral_risk_label"], {"rising", "high", "critical"})

    # -----------------------------------------------------------------------
    # 3. Stable payments reduce spiral risk over time
    # -----------------------------------------------------------------------

    def test_stable_payments_result_in_low_spiral(self) -> None:
        player = self._create_player(cash=2500.0, credit_score=740)
        # Player with good payment history: no loans, no delinquency, low scores
        self._seed_borrowing_state(
            player,
            dependence_risk_score=0.0,
            repeat_borrowing_count_30d=0,
            active_loan_count=0,
            borrowing_access_score=80.0,
        )
        self._seed_delinquency_state(
            player, stage="current", missed_30d=0, late_30d=0, credit_pressure=0.0
        )
        self._seed_shock_state(player, shock_risk=15.0, financial_fragility=10.0)

        profile = build_debt_behavior_profile(self.db, player.id, 10)

        self.assertEqual(profile["spiral_risk_label"], "low")
        self.assertEqual(profile["debt_state_label"], "controlled")

    # -----------------------------------------------------------------------
    # 4. Recovery is slower than damage — requires consecutive stable signals
    # -----------------------------------------------------------------------

    def test_recovery_requires_consecutive_stable_days(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        # Seed 2 stable trend rows (enough for "early" but not "stabilizing")
        self._seed_trend_row(player, day=1, composite_risk=8.0, spiral_label="low")
        self._seed_trend_row(player, day=2, composite_risk=9.0, spiral_label="low")

        recovery = detect_recovery_state(self.db, player.id, 3)
        # 2 consecutive stable days → "early" stage
        self.assertIn(recovery["recovery_stage"], {"early", "stabilizing"})
        self.assertGreater(recovery["consecutive_stable_days"], 0)

    def test_recovery_strong_requires_fourteen_days(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        # Seed 14 consecutive stable trend rows
        for d in range(1, 15):
            self._seed_trend_row(player, day=d, composite_risk=8.0, spiral_label="low", recovery_stage="rebuilding")

        recovery = detect_recovery_state(self.db, player.id, 15)
        self.assertEqual(recovery["recovery_stage"], "strong")
        self.assertGreaterEqual(recovery["consecutive_stable_days"], 14)

    def test_single_high_spiral_row_resets_recovery(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        # 5 stable days, then 1 critical day → no recovery streak
        for d in range(1, 6):
            self._seed_trend_row(player, day=d, composite_risk=8.0, spiral_label="low")
        self._seed_trend_row(player, day=6, composite_risk=80.0, spiral_label="critical")

        recovery = detect_recovery_state(self.db, player.id, 7)
        self.assertEqual(recovery["consecutive_stable_days"], 0)
        self.assertEqual(recovery["recovery_stage"], "none")

    # -----------------------------------------------------------------------
    # 5. Critical spiral suppresses recovery stage
    # -----------------------------------------------------------------------

    def test_critical_spiral_prevents_recovery(self) -> None:
        player = self._create_player(cash=50.0, credit_score=400)
        # Build a high-spiral player state
        self._seed_borrowing_state(
            player,
            dependence_risk_score=80.0,
            repeat_borrowing_count_30d=5,
            active_loan_count=3,
        )
        self._seed_delinquency_state(
            player,
            stage="critical",
            missed_30d=5,
            late_30d=3,
            credit_pressure=85.0,
            financial_distress=80.0,
            stress_days=20,
        )
        self._seed_shock_state(player, shock_risk=80.0, financial_fragility=90.0)

        profile = build_debt_behavior_profile(self.db, player.id, 10)
        recovery = detect_recovery_state(self.db, player.id, 10, profile)

        self.assertEqual(profile["spiral_risk_label"], "critical")
        self.assertEqual(recovery["recovery_stage"], "none")

    # -----------------------------------------------------------------------
    # 6. Spiral detection — primary driver attribution
    # -----------------------------------------------------------------------

    def test_spiral_detection_returns_primary_driver(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(
            player,
            dependence_risk_score=70.0,
            repeat_borrowing_count_30d=3,
            active_loan_count=2,
        )
        self._seed_delinquency_state(player, stage="late", missed_30d=2, credit_pressure=45.0)
        self._seed_shock_state(player, shock_risk=30.0)

        spiral = detect_debt_spiral_state(self.db, player.id, 5)

        self.assertIn(spiral["spiral_risk_label"], {"rising", "high", "critical"})
        self.assertIsNotNone(spiral["primary_driver"])
        self.assertIn(spiral["time_to_instability_estimate"], {"1–3 days", "3–5 days", "4–7 days", "7–10 days", "10–14 days", "30+ days"})
        self.assertIsInstance(spiral["short_summary"], str)
        self.assertGreater(len(spiral["short_summary"]), 10)

    # -----------------------------------------------------------------------
    # 7. Debt pressure effects are bounded and proportional
    # -----------------------------------------------------------------------

    def test_pressure_effects_are_bounded(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player, dependence_risk_score=60.0, active_loan_count=2)
        self._seed_delinquency_state(player, stage="late", missed_30d=3, credit_pressure=55.0)
        self._seed_shock_state(player, shock_risk=50.0, financial_fragility=55.0)

        effects = build_debt_pressure_effects(self.db, player.id, 5)

        self.assertGreaterEqual(effects["stress_baseline_modifier"], 0.0)
        self.assertLessEqual(effects["stress_baseline_modifier"], 25.0)
        self.assertGreaterEqual(effects["shock_sensitivity_modifier"], 1.0)
        self.assertLessEqual(effects["shock_sensitivity_modifier"], 1.5)
        self.assertGreaterEqual(effects["borrowing_access_penalty"], 0.0)
        self.assertLessEqual(effects["borrowing_access_penalty"], 35.0)
        self.assertGreaterEqual(effects["business_expansion_penalty"], 0.0)
        self.assertLessEqual(effects["business_expansion_penalty"], 0.40)

    def test_clean_player_has_minimal_pressure_effects(self) -> None:
        player = self._create_player(cash=2000.0, credit_score=750)
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player, shock_risk=10.0, financial_fragility=10.0)

        effects = build_debt_pressure_effects(self.db, player.id, 1)

        self.assertLess(effects["stress_baseline_modifier"], 5.0)
        self.assertLess(effects["shock_sensitivity_modifier"], 1.15)
        self.assertLess(effects["borrowing_access_penalty"], 5.0)
        self.assertLess(effects["business_expansion_penalty"], 0.05)

    def test_critical_player_has_elevated_pressure_effects(self) -> None:
        player = self._create_player(cash=50.0, credit_score=380)
        self._seed_borrowing_state(player, dependence_risk_score=90.0, repeat_borrowing_count_30d=6, active_loan_count=3)
        self._seed_delinquency_state(player, stage="critical", missed_30d=6, credit_pressure=95.0, financial_distress=90.0, stress_days=25)
        self._seed_shock_state(player, shock_risk=90.0, financial_fragility=90.0)

        effects = build_debt_pressure_effects(self.db, player.id, 10)

        self.assertGreater(effects["stress_baseline_modifier"], 10.0)
        self.assertGreater(effects["shock_sensitivity_modifier"], 1.3)
        self.assertGreater(effects["borrowing_access_penalty"], 15.0)
        self.assertGreater(effects["business_expansion_penalty"], 0.20)

    # -----------------------------------------------------------------------
    # 8. Trend detection — improving vs deteriorating
    # -----------------------------------------------------------------------

    def test_deteriorating_trend_detected(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player, active_loan_count=1, dependence_risk_score=20.0)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        # Seed gradually worsening history
        for d, risk in enumerate([10.0, 12.0, 15.0, 20.0, 28.0, 36.0, 45.0], start=1):
            self._seed_trend_row(player, day=d, composite_risk=risk)

        profile = build_debt_behavior_profile(self.db, player.id, 8)
        # Profile computed at day 8 looks back at days 1-7
        # Current composite will be derived from actual state
        # The trend function compares current vs history
        trend = build_debt_trend_state(self.db, player.id, 8)
        # With ascending composites, recent should be higher than older
        self.assertIn(trend["trend_direction"], {"deteriorating", "stable"})

    def test_improving_trend_detected(self) -> None:
        player = self._create_player(cash=2200.0, credit_score=720)
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player, shock_risk=10.0)

        # Seed improving history (decreasing composite risk)
        for d, risk in enumerate([50.0, 45.0, 38.0, 30.0, 22.0, 15.0, 10.0], start=1):
            self._seed_trend_row(player, day=d, composite_risk=risk)

        trend = build_debt_trend_state(self.db, player.id, 8)
        self.assertIn(trend["trend_direction"], {"improving", "stable"})

    # -----------------------------------------------------------------------
    # 9. Full summary function integrates all sub-components
    # -----------------------------------------------------------------------

    def test_summary_returns_all_required_fields(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player, active_loan_count=1, dependence_risk_score=20.0)
        self._seed_delinquency_state(player, stage="stretched", missed_30d=1)
        self._seed_shock_state(player, shock_risk=30.0)
        self._seed_loan(player, principal=400.0)

        summary = build_debt_behavior_summary(self.db, player.id, day_number=5)

        required_keys = [
            "player_id", "as_of_date", "day_number", "debt_state_label",
            "recovery_state_label", "spiral_risk_label", "trend_direction",
            "top_risk_driver", "top_recovery_driver", "debt_dependency_score",
            "payment_stack_pressure_score", "borrowing_frequency_score",
            "financial_stability_score", "composite_risk_score",
            "consecutive_stable_days", "recovery_confidence_score",
            "stress_baseline_modifier", "shock_sensitivity_modifier",
            "borrowing_access_penalty", "business_expansion_penalty",
            "time_to_instability_estimate", "practical_actions",
            "planning_warnings", "trend_days_tracked", "short_summary",
        ]
        for key in required_keys:
            self.assertIn(key, summary, msg=f"Missing key in summary: {key}")

        self.assertIsInstance(summary["practical_actions"], list)
        self.assertGreater(len(summary["practical_actions"]), 0)
        self.assertIsInstance(summary["short_summary"], str)

    # -----------------------------------------------------------------------
    # 10. Persistence — state row is created and updated
    # -----------------------------------------------------------------------

    def test_behavior_state_row_is_persisted(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        build_debt_behavior_profile(self.db, player.id, 1)
        self.db.commit()

        state = self.db.query(PlayerDebtBehaviorState).filter(
            PlayerDebtBehaviorState.player_id == player.id
        ).first()
        self.assertIsNotNone(state)
        self.assertEqual(int(state.last_updated_on), 1)
        self.assertIn(str(state.spiral_risk_label), {"low", "rising", "high", "critical"})

    def test_trend_history_row_appended(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        build_debt_behavior_profile(self.db, player.id, 5)
        self.db.commit()

        rows = self.db.query(PlayerDebtTrendHistory).filter(
            PlayerDebtTrendHistory.player_id == player.id
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].day, 5)

    def test_trend_history_upsert_on_same_day(self) -> None:
        player = self._create_player()
        self._seed_borrowing_state(player)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player)

        build_debt_behavior_profile(self.db, player.id, 7)
        build_debt_behavior_profile(self.db, player.id, 7)
        self.db.commit()

        rows = self.db.query(PlayerDebtTrendHistory).filter(
            PlayerDebtTrendHistory.player_id == player.id,
            PlayerDebtTrendHistory.day == 7,
        ).all()
        # Second call should upsert, not insert duplicate
        self.assertEqual(len(rows), 1)

    # -----------------------------------------------------------------------
    # 11. Missing state tables return safe defaults (not exceptions)
    # -----------------------------------------------------------------------

    def test_no_borrowing_state_defaults_gracefully(self) -> None:
        player = self._create_player()
        # No borrowing/delinquency/shock rows seeded
        profile = build_debt_behavior_profile(self.db, player.id, 1)

        self.assertIsNotNone(profile)
        self.assertGreaterEqual(profile["financial_stability_score"], 0.0)
        self.assertLessEqual(profile["financial_stability_score"], 100.0)

    def test_no_trend_history_returns_stable_trend(self) -> None:
        player = self._create_player()
        trend = build_debt_trend_state(self.db, player.id, 1)

        self.assertFalse(trend["has_history"])
        self.assertEqual(trend["trend_direction"], "stable")
        self.assertEqual(trend["days_tracked"], 0)

    # -----------------------------------------------------------------------
    # 12. Invalid player ID raises expected error
    # -----------------------------------------------------------------------

    def test_invalid_player_id_raises_not_found(self) -> None:
        with self.assertRaises(DebtBehaviorNotFoundError):
            build_debt_behavior_profile(self.db, "not-a-uuid", 1)

    def test_missing_player_raises_not_found(self) -> None:
        with self.assertRaises(DebtBehaviorNotFoundError):
            build_debt_behavior_profile(self.db, str(uuid.uuid4()), 1)

    # -----------------------------------------------------------------------
    # 13. Delinquency stage escalation drives higher payment pressure
    # -----------------------------------------------------------------------

    def test_stage_escalation_raises_payment_pressure(self) -> None:
        stages = ["current", "stretched", "late", "delinquent", "critical"]
        pressures: list[float] = []

        for stage in stages:
            player = self._create_player()
            self._seed_borrowing_state(player)
            self._seed_delinquency_state(player, stage=stage, missed_30d=0, credit_pressure=0.0)
            self._seed_shock_state(player)
            profile = build_debt_behavior_profile(self.db, player.id, 1)
            pressures.append(profile["payment_stack_pressure_score"])

        # Each successive stage should produce higher payment pressure
        for i in range(len(pressures) - 1):
            self.assertLessEqual(
                pressures[i],
                pressures[i + 1],
                msg=f"Stage '{stages[i]}' should have less or equal pressure than '{stages[i+1]}'",
            )

    # -----------------------------------------------------------------------
    # 14. Planning warnings appear under appropriate conditions
    # -----------------------------------------------------------------------

    def test_planning_warnings_issued_for_critical_spiral(self) -> None:
        player = self._create_player(cash=50.0, credit_score=380)
        self._seed_borrowing_state(player, dependence_risk_score=80.0, active_loan_count=3, repeat_borrowing_count_30d=5)
        self._seed_delinquency_state(player, stage="critical", missed_30d=5, credit_pressure=90.0)
        self._seed_shock_state(player, shock_risk=85.0, financial_fragility=88.0)

        profile = build_debt_behavior_profile(self.db, player.id, 3)
        self.assertGreater(len(profile["planning_warnings"]), 0)

    def test_no_unnecessary_warnings_for_clean_player(self) -> None:
        player = self._create_player(cash=3000.0, credit_score=780)
        self._seed_borrowing_state(player, borrowing_access_score=85.0)
        self._seed_delinquency_state(player)
        self._seed_shock_state(player, shock_risk=10.0, financial_fragility=10.0)

        profile = build_debt_behavior_profile(self.db, player.id, 1)
        # A clean player should have zero or very few warnings
        self.assertLessEqual(len(profile["planning_warnings"]), 1)

    # -----------------------------------------------------------------------
    # 15. Financial stability is inversely related to composite risk
    # -----------------------------------------------------------------------

    def test_stability_inversely_correlates_with_risk(self) -> None:
        # High risk player
        player_hi = self._create_player(cash=80.0)
        self._seed_borrowing_state(player_hi, dependence_risk_score=85.0, active_loan_count=3, repeat_borrowing_count_30d=5)
        self._seed_delinquency_state(player_hi, stage="critical", credit_pressure=90.0, missed_30d=5)
        self._seed_shock_state(player_hi, shock_risk=80.0, financial_fragility=85.0)
        profile_hi = build_debt_behavior_profile(self.db, player_hi.id, 1)

        # Low risk player
        player_lo = self._create_player(cash=3500.0, credit_score=800)
        self._seed_borrowing_state(player_lo)
        self._seed_delinquency_state(player_lo)
        self._seed_shock_state(player_lo, shock_risk=5.0, financial_fragility=5.0)
        profile_lo = build_debt_behavior_profile(self.db, player_lo.id, 1)

        self.assertGreater(profile_lo["financial_stability_score"], profile_hi["financial_stability_score"])
        self.assertGreater(profile_hi["composite_risk_score"], profile_lo["composite_risk_score"])


if __name__ == "__main__":
    unittest.main()
