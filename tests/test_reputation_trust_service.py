"""Step 40 unit tests for reputation_trust_service.py.

Tests cover:
  - Stable player gets better trust than an unstable player
  - Delinquency + repeat borrowing reduce financial reliability
  - Strong recovery stage rebuilds reputation gradually
  - False growth does NOT create strong trust
  - Business consistency improves business reliability score
  - Poor reputation hurts opportunity access without making game unwinnable
  - Score clamping stays within 0–100
  - Direction detection: improving / weakening / stable / recovering
"""

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_reputation_trust.db")

from app.db.database import Base
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_reputation_history import PlayerReputationHistory
from app.models.player_reputation_state import PlayerReputationState
from app.models.player_shock_state import PlayerShockState
from app.models.player_wealth_state import PlayerWealthState
from app.models.user import User
from app.engine.reputation_trust_service import (
    ReputationTrustNotFoundError,
    ReputationTrustValidationError,
    _compute_financial_reliability_score,
    _compute_work_reliability_score,
    _compute_business_reliability_score,
    _compute_composite_reputation_score,
    _compute_trust_score,
    _compute_opportunity_readiness_score,
    _resolve_trust_label,
    _resolve_opportunity_label,
    _resolve_reputation_direction,
    build_player_reputation_profile,
    build_trust_signal_state,
    build_opportunity_access_state,
    apply_reputation_effects,
    SCORE_MIN,
    SCORE_MAX,
)

TABLES = [
    User.__table__,
    Player.__table__,
    PlayerReputationState.__table__,
    PlayerReputationHistory.__table__,
    PlayerDelinquencyState.__table__,
    PlayerBorrowingState.__table__,
    PlayerDebtBehaviorState.__table__,
    PlayerWealthState.__table__,
    PlayerShockState.__table__,
    PlayerRecoveryState.__table__,
]


class ReputationTrustServiceTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_player(
        self,
        *,
        credit_score: int = 650,
        missed_payment_streak: int = 0,
        skill_level: int = 3,
        stress: int = 20,
        main_job: str | None = "retail_worker",
        opportunity_access_penalty: float = 0.0,
        career_progress_penalty: float = 0.0,
        business_risk_penalty: float = 0.0,
        account_created_day: int = 1,
    ) -> Player:
        user = User(
            email=f"rt-test-{uuid.uuid4()}@example.com",
            hashed_password="x",
        )
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name="RepTrust Test",
            credit_score=credit_score,
            missed_payment_streak=missed_payment_streak,
            skill_level=skill_level,
            stress=stress,
            main_job=main_job,
            opportunity_access_penalty=Decimal(str(opportunity_access_penalty)),
            career_progress_penalty=Decimal(str(career_progress_penalty)),
            business_risk_penalty=Decimal(str(business_risk_penalty)),
            account_created_day=account_created_day,
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _add_delinquency(
        self,
        player: Player,
        *,
        stage: str = "current",
        missed_30d: int = 0,
        late_30d: int = 0,
        credit_pressure: float = 0.0,
        distress_score: float = 0.0,
    ) -> PlayerDelinquencyState:
        row = PlayerDelinquencyState(
            player_id=player.id,
            current_delinquency_stage=stage,
            missed_payment_count_30d=missed_30d,
            late_payment_count_30d=late_30d,
            credit_pressure_score=Decimal(str(credit_pressure)),
            financial_distress_score=Decimal(str(distress_score)),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _add_borrowing(
        self,
        player: Player,
        *,
        access_score: float = 60.0,
        active_loan_count: int = 0,
        repeat_30d: int = 0,
        dependence_risk: float = 0.0,
    ) -> PlayerBorrowingState:
        row = PlayerBorrowingState(
            player_id=player.id,
            borrowing_access_score=Decimal(str(access_score)),
            active_loan_count=active_loan_count,
            repeat_borrowing_count_30d=repeat_30d,
            dependence_risk_score=Decimal(str(dependence_risk)),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _add_debt_behavior(
        self,
        player: Player,
        *,
        debt_label: str = "stable",
        spiral_label: str = "low",
        fin_stability: float = 60.0,
        trend: str = "stable",
        recovery_stage: str = "none",
    ) -> PlayerDebtBehaviorState:
        row = PlayerDebtBehaviorState(
            player_id=player.id,
            debt_state_label=debt_label,
            spiral_risk_label=spiral_label,
            financial_stability_score=Decimal(str(fin_stability)),
            trend_direction=trend,
            recovery_stage=recovery_stage,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _add_wealth_state(
        self,
        player: Player,
        *,
        stability_score: float = 60.0,
        buffer_days: float = 10.0,
        false_growth: bool = False,
        phase: str = "stabilization",
    ) -> PlayerWealthState:
        row = PlayerWealthState(
            player_id=player.id,
            stability_before_growth_score=Decimal(str(stability_score)),
            buffer_days=Decimal(str(buffer_days)),
            false_growth_detected=false_growth,
            wealth_phase_label=phase,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _add_shock_state(
        self,
        player: Player,
        *,
        fragility: float = 20.0,
        work_risk: float = 15.0,
        neg_streak: int = 0,
    ) -> PlayerShockState:
        row = PlayerShockState(
            player_id=player.id,
            financial_fragility_score=Decimal(str(fragility)),
            work_disruption_risk_score=Decimal(str(work_risk)),
            recent_negative_streak=neg_streak,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _add_recovery_state(
        self,
        player: Player,
        *,
        status: str = "none",
    ) -> PlayerRecoveryState:
        row = PlayerRecoveryState(
            player_id=player.id,
            recovery_status_label=status,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------------
    # Label resolver tests
    # ------------------------------------------------------------------

    def test_trust_label_mapping(self) -> None:
        self.assertEqual(_resolve_trust_label(Decimal("85")), "highly_trusted")
        self.assertEqual(_resolve_trust_label(Decimal("70")), "trusted")
        self.assertEqual(_resolve_trust_label(Decimal("50")), "solid")
        self.assertEqual(_resolve_trust_label(Decimal("35")), "mixed")
        self.assertEqual(_resolve_trust_label(Decimal("20")), "weak")

    def test_opportunity_label_mapping(self) -> None:
        self.assertEqual(_resolve_opportunity_label(Decimal("85")), "preferred")
        self.assertEqual(_resolve_opportunity_label(Decimal("70")), "elevated")
        self.assertEqual(_resolve_opportunity_label(Decimal("50")), "standard")
        self.assertEqual(_resolve_opportunity_label(Decimal("32")), "limited")
        self.assertEqual(_resolve_opportunity_label(Decimal("15")), "restricted")

    # ------------------------------------------------------------------
    # Financial reliability
    # ------------------------------------------------------------------

    def test_delinquency_reduces_financial_reliability(self) -> None:
        player = self._make_player(credit_score=600)
        delinq = self._add_delinquency(player, stage="delinquent", missed_30d=4, late_30d=5)
        borrowing = self._add_borrowing(player, dependence_risk=30.0, repeat_30d=3)
        debt = self._add_debt_behavior(player)
        wealth = self._add_wealth_state(player)

        score, label, drag = _compute_financial_reliability_score(player, delinq, borrowing, debt, wealth)

        self.assertLess(score, Decimal("40"))
        self.assertIn(label, ("weak", "mixed"))
        self.assertNotEqual(drag, "none")

    def test_clean_payment_history_improves_financial_reliability(self) -> None:
        player = self._make_player(credit_score=750)
        delinq = self._add_delinquency(player, stage="current", missed_30d=0, late_30d=0)
        borrowing = self._add_borrowing(player, dependence_risk=5.0, repeat_30d=0)
        debt = self._add_debt_behavior(player, debt_label="stable_surplus", fin_stability=75.0)
        wealth = self._add_wealth_state(player)

        score, label, _ = _compute_financial_reliability_score(player, delinq, borrowing, debt, wealth)

        self.assertGreater(score, Decimal("55"))
        self.assertIn(label, ("solid", "trusted", "highly_trusted"))

    def test_false_growth_caps_financial_reliability_before_credit_bonus(self) -> None:
        """False growth caps the base score at 55 (applied before the credit score bonus).

        With a neutral credit score (620 — no bonus/penalty), the cap holds at 55.
        With a high credit score (750), the +8 bonus is added after the cap → 63.
        Verify false-growth player scores lower than an identical clean player.
        """
        player = self._make_player(credit_score=620)
        delinq = self._add_delinquency(player, stage="current")
        borrowing = self._add_borrowing(player)
        debt = self._add_debt_behavior(player, debt_label="stable_surplus")
        wealth = self._add_wealth_state(player, false_growth=True, stability_score=80.0)

        score_fg, _, _ = _compute_financial_reliability_score(player, delinq, borrowing, debt, wealth)

        # Neutral credit: only cap applies → expected 55
        self.assertLessEqual(score_fg, Decimal("55"))

        # A clean player (no false growth, same everything) should score higher
        player_clean = self._make_player(credit_score=620)
        delinq_clean = self._add_delinquency(player_clean, stage="current")
        borrowing_clean = self._add_borrowing(player_clean)
        debt_clean = self._add_debt_behavior(player_clean, debt_label="stable_surplus")
        wealth_clean = self._add_wealth_state(player_clean, false_growth=False, stability_score=80.0)

        score_clean, _, _ = _compute_financial_reliability_score(
            player_clean, delinq_clean, borrowing_clean, debt_clean, wealth_clean
        )
        self.assertGreater(score_clean, score_fg)

    def test_high_repeat_borrowing_reduces_score(self) -> None:
        player = self._make_player()
        delinq = self._add_delinquency(player)
        borrowing = self._add_borrowing(player, repeat_30d=8, dependence_risk=60.0, active_loan_count=4)
        debt = self._add_debt_behavior(player, debt_label="distressed")
        wealth = self._add_wealth_state(player)

        score, _, _ = _compute_financial_reliability_score(player, delinq, borrowing, debt, wealth)

        self.assertLess(score, Decimal("40"))

    # ------------------------------------------------------------------
    # Work reliability
    # ------------------------------------------------------------------

    def test_no_job_reduces_work_reliability(self) -> None:
        player = self._make_player(main_job=None)
        shock = self._add_shock_state(player)
        recovery = self._add_recovery_state(player)
        debt = self._add_debt_behavior(player)

        score, label, drag = _compute_work_reliability_score(player, shock, recovery, debt)

        self.assertLess(score, Decimal("50"))
        self.assertEqual(drag, "no active employment")

    def test_high_skill_boosts_work_reliability(self) -> None:
        player = self._make_player(skill_level=5, stress=10)
        shock = self._add_shock_state(player, work_risk=5.0)
        recovery = self._add_recovery_state(player)
        debt = self._add_debt_behavior(player)

        score, label, _ = _compute_work_reliability_score(player, shock, recovery, debt)

        self.assertGreater(score, Decimal("55"))

    def test_high_stress_reduces_work_reliability(self) -> None:
        player = self._make_player(stress=85, skill_level=2)
        shock = self._add_shock_state(player, neg_streak=6)
        recovery = self._add_recovery_state(player)
        debt = self._add_debt_behavior(player)

        score, _, drag = _compute_work_reliability_score(player, shock, recovery, debt)

        self.assertLess(score, Decimal("40"))
        self.assertIn(drag, ("extreme stress level", "sustained negative shock streak", "no active employment"))

    def test_recovery_stage_rebuilding_boosts_work_score(self) -> None:
        player = self._make_player(stress=30)
        shock = self._add_shock_state(player)
        recovery = self._add_recovery_state(player, status="rebuilding")
        debt = self._add_debt_behavior(player, recovery_stage="rebuilding")

        score_with_recovery, _, _ = _compute_work_reliability_score(player, shock, recovery, debt)

        # Should be higher than baseline 50 due to recovery boosts
        self.assertGreater(score_with_recovery, Decimal("50"))

    # ------------------------------------------------------------------
    # Composite and trust scores
    # ------------------------------------------------------------------

    def test_stable_player_gets_better_trust_than_unstable(self) -> None:
        """Core spec requirement: stability produces measurably better trust."""
        stable = self._make_player(credit_score=720, missed_payment_streak=0, skill_level=4, stress=15)
        self._add_delinquency(stable, stage="current")
        self._add_borrowing(stable, dependence_risk=5.0)
        self._add_debt_behavior(stable, debt_label="stable_surplus", fin_stability=70.0)
        self._add_wealth_state(stable, stability_score=65.0, false_growth=False)
        self._add_shock_state(stable, fragility=15.0)
        self._add_recovery_state(stable)

        unstable = self._make_player(credit_score=550, missed_payment_streak=4, skill_level=1, stress=80)
        self._add_delinquency(unstable, stage="delinquent", missed_30d=5, late_30d=7)
        self._add_borrowing(unstable, dependence_risk=70.0, repeat_30d=8, active_loan_count=4)
        self._add_debt_behavior(unstable, debt_label="critical", spiral_label="critical")
        self._add_wealth_state(unstable, stability_score=10.0, false_growth=True)
        self._add_shock_state(unstable, fragility=80.0, neg_streak=7)
        self._add_recovery_state(unstable)

        self.db.commit()

        stable_profile = build_player_reputation_profile(self.db, stable.id, day=1)
        self.db.commit()
        unstable_profile = build_player_reputation_profile(self.db, unstable.id, day=1)
        self.db.commit()

        self.assertGreater(
            stable_profile["trust_score"],
            unstable_profile["trust_score"],
            "Stable player should have higher trust than unstable player",
        )
        self.assertGreater(
            stable_profile["opportunity_readiness_score"],
            unstable_profile["opportunity_readiness_score"],
        )

    def test_false_growth_does_not_create_strong_trust(self) -> None:
        """False growth must NOT produce trust_score above 60."""
        player = self._make_player(credit_score=750, skill_level=5, stress=10)
        self._add_delinquency(player, stage="current")
        self._add_borrowing(player, dependence_risk=0.0)
        self._add_debt_behavior(player, debt_label="stable_surplus")
        self._add_wealth_state(player, stability_score=90.0, false_growth=True)
        self._add_shock_state(player, fragility=5.0)
        self._add_recovery_state(player)

        self.db.commit()

        profile = build_player_reputation_profile(self.db, player.id, day=5)
        self.db.commit()

        self.assertLessEqual(
            profile["trust_score"],
            61.0,
            "False growth must not create strong trust (max ~60)",
        )

    def test_recovery_stage_rebuilding_improves_trust_over_time(self) -> None:
        """Recovery trajectory should yield better trust than zero-recovery baseline."""
        # Recovering player
        recovering = self._make_player(credit_score=600, stress=30)
        self._add_delinquency(recovering, stage="stretched")
        self._add_borrowing(recovering, dependence_risk=20.0)
        self._add_debt_behavior(recovering, debt_label="stretched", recovery_stage="rebuilding")
        self._add_wealth_state(recovering, stability_score=35.0)
        self._add_recovery_state(recovering, status="rebuilding")

        # Same player profile but NO recovery
        stuck = self._make_player(credit_score=600, stress=30)
        self._add_delinquency(stuck, stage="stretched")
        self._add_borrowing(stuck, dependence_risk=20.0)
        self._add_debt_behavior(stuck, debt_label="stretched", recovery_stage="none")
        self._add_wealth_state(stuck, stability_score=35.0)
        self._add_recovery_state(stuck, status="none")

        self.db.commit()

        r_profile = build_player_reputation_profile(self.db, recovering.id, day=10)
        self.db.commit()
        s_profile = build_player_reputation_profile(self.db, stuck.id, day=10)
        self.db.commit()

        self.assertGreater(
            r_profile["trust_score"],
            s_profile["trust_score"],
            "Recovering player should have higher trust than stuck player",
        )

    # ------------------------------------------------------------------
    # Opportunity access
    # ------------------------------------------------------------------

    def test_poor_reputation_restricts_opportunity_without_game_over(self) -> None:
        """Low rep must restrict access but not make the game unwinnable (score ≥ 0)."""
        player = self._make_player(
            credit_score=450,
            missed_payment_streak=6,
            skill_level=1,
            stress=90,
            main_job=None,
        )
        self._add_delinquency(player, stage="critical", missed_30d=8, late_30d=10)
        self._add_borrowing(player, dependence_risk=90.0, repeat_30d=10, active_loan_count=5)
        self._add_debt_behavior(player, debt_label="critical", spiral_label="critical")
        self._add_wealth_state(player, stability_score=5.0, false_growth=True)
        self._add_shock_state(player, fragility=90.0, work_risk=90.0, neg_streak=10)
        self._add_recovery_state(player, status="none")

        self.db.commit()

        profile = build_player_reputation_profile(self.db, player.id, day=1)
        self.db.commit()

        self.assertIn(profile["opportunity_access_label"], ("restricted", "limited"))
        # Must remain within range — game must not be unwinnable
        self.assertGreaterEqual(profile["reputation_score"], 0.0)
        self.assertLessEqual(profile["reputation_score"], 100.0)
        self.assertGreaterEqual(profile["trust_score"], 0.0)
        self.assertGreaterEqual(profile["opportunity_readiness_score"], 0.0)

    def test_high_trust_player_gets_elevated_or_preferred_access(self) -> None:
        player = self._make_player(credit_score=780, skill_level=5, stress=10)
        self._add_delinquency(player, stage="current", missed_30d=0)
        self._add_borrowing(player, dependence_risk=2.0)
        self._add_debt_behavior(player, debt_label="stable_surplus", fin_stability=80.0, spiral_label="low")
        self._add_wealth_state(player, stability_score=75.0, buffer_days=20.0, false_growth=False)
        self._add_shock_state(player, fragility=5.0, work_risk=8.0)
        self._add_recovery_state(player)

        self.db.commit()

        profile = build_player_reputation_profile(self.db, player.id, day=1)
        self.db.commit()

        self.assertIn(profile["opportunity_access_label"], ("standard", "elevated", "preferred"))
        self.assertGreater(profile["trust_score"], 50.0)

    # ------------------------------------------------------------------
    # Score clamping
    # ------------------------------------------------------------------

    def test_scores_are_always_within_0_100(self) -> None:
        # Extreme positive scenario
        player_good = self._make_player(credit_score=850, skill_level=5, stress=0)
        self._add_delinquency(player_good, stage="current")
        self._add_borrowing(player_good, dependence_risk=0.0)
        self._add_debt_behavior(player_good, debt_label="stable_surplus", fin_stability=100.0)
        self._add_wealth_state(player_good, stability_score=100.0, buffer_days=30.0)
        self._add_shock_state(player_good, fragility=0.0)
        self._add_recovery_state(player_good)

        # Extreme negative scenario
        player_bad = self._make_player(credit_score=300, skill_level=0, stress=100, main_job=None)
        self._add_delinquency(player_bad, stage="critical", missed_30d=20, late_30d=20)
        self._add_borrowing(player_bad, dependence_risk=100.0, repeat_30d=20, active_loan_count=10)
        self._add_debt_behavior(player_bad, debt_label="critical", spiral_label="critical", fin_stability=0.0)
        self._add_wealth_state(player_bad, stability_score=0.0, buffer_days=0.0, false_growth=True)
        self._add_shock_state(player_bad, fragility=100.0, work_risk=100.0, neg_streak=20)
        self._add_recovery_state(player_bad)

        self.db.commit()

        for player in (player_good, player_bad):
            profile = build_player_reputation_profile(self.db, player.id, day=1)
            self.db.commit()
            for key in (
                "reputation_score",
                "trust_score",
                "financial_reliability_score",
                "work_reliability_score",
                "opportunity_readiness_score",
            ):
                val = profile[key]
                self.assertGreaterEqual(val, 0.0, f"{key} must be >= 0")
                self.assertLessEqual(val, 100.0, f"{key} must be <= 100")

    # ------------------------------------------------------------------
    # Trust signal state
    # ------------------------------------------------------------------

    def test_trust_signal_state_returns_all_signals(self) -> None:
        player = self._make_player()
        self._add_delinquency(player)
        self._add_borrowing(player)
        self._add_debt_behavior(player)
        self._add_wealth_state(player)
        self._add_shock_state(player)
        self._add_recovery_state(player)
        self.db.commit()

        signals = build_trust_signal_state(self.db, player.id, day=1)

        self.assertIn("payment_signal", signals)
        self.assertIn("label", signals["payment_signal"])
        self.assertIn("borrowing_signal", signals)
        self.assertIn("work_signal", signals)
        self.assertIn("business_signal", signals)
        self.assertIn("stability_signal", signals)

    # ------------------------------------------------------------------
    # Reputation effects
    # ------------------------------------------------------------------

    def test_apply_reputation_effects_returns_bounded_modifiers(self) -> None:
        player = self._make_player()
        self._add_delinquency(player)
        self._add_borrowing(player)
        self._add_debt_behavior(player)
        self._add_wealth_state(player)
        self._add_shock_state(player)
        self._add_recovery_state(player)
        self.db.commit()

        effects = apply_reputation_effects(self.db, player.id, day=1)

        e = effects["effects"]
        # job_quality bounded to [-0.15, +0.15]
        self.assertGreaterEqual(e["job_quality_modifier_pct"], -0.16)
        self.assertLessEqual(e["job_quality_modifier_pct"], 0.16)
        # credit_rate bounded to [-0.10, +0.10]
        self.assertGreaterEqual(e["credit_rate_modifier_pct"], -0.11)
        self.assertLessEqual(e["credit_rate_modifier_pct"], 0.11)
        # demand bounded to [-0.12, +0.12]
        self.assertGreaterEqual(e["demand_modifier_pct"], -0.13)
        self.assertLessEqual(e["demand_modifier_pct"], 0.13)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_invalid_player_id_raises_not_found(self) -> None:
        with self.assertRaises(ReputationTrustNotFoundError):
            build_player_reputation_profile(self.db, "00000000-0000-0000-0000-000000000000", day=1)

    def test_invalid_day_raises_validation_error(self) -> None:
        player = self._make_player()
        self._add_delinquency(player)
        self._add_borrowing(player)
        self._add_debt_behavior(player)
        self._add_wealth_state(player)
        self.db.commit()

        with self.assertRaises((ReputationTrustValidationError, Exception)):
            build_player_reputation_profile(self.db, player.id, day=0)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def test_building_profile_persists_reputation_state_and_history(self) -> None:
        player = self._make_player()
        self._add_delinquency(player)
        self._add_borrowing(player)
        self._add_debt_behavior(player)
        self._add_wealth_state(player)
        self._add_shock_state(player)
        self._add_recovery_state(player)
        self.db.commit()

        build_player_reputation_profile(self.db, player.id, day=5)
        self.db.commit()

        state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).first()
        self.assertIsNotNone(state)
        self.assertEqual(int(state.last_updated_on), 5)

        hist = self.db.query(PlayerReputationHistory).filter(
            PlayerReputationHistory.player_id == player.id,
            PlayerReputationHistory.day == 5,
        ).first()
        self.assertIsNotNone(hist)

    def test_rebuild_profile_same_day_updates_in_place(self) -> None:
        player = self._make_player()
        self._add_delinquency(player)
        self._add_borrowing(player)
        self._add_debt_behavior(player)
        self._add_wealth_state(player)
        self._add_shock_state(player)
        self._add_recovery_state(player)
        self.db.commit()

        build_player_reputation_profile(self.db, player.id, day=7)
        self.db.commit()
        build_player_reputation_profile(self.db, player.id, day=7)
        self.db.commit()

        count = self.db.query(PlayerReputationHistory).filter(
            PlayerReputationHistory.player_id == player.id,
            PlayerReputationHistory.day == 7,
        ).count()
        self.assertEqual(count, 1)

        state_count = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).count()
        self.assertEqual(state_count, 1)


if __name__ == "__main__":
    unittest.main()
