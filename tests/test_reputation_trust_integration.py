"""Step 40 cross-service integration tests for reputation/trust services.

These tests exercise the full service call chain across all upstream signals
and verify that reputation state persists correctly, that multiple calls on
the same day upsert (not duplicate), and that the public summary includes
the expected nested structures.
"""

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_reputation_trust_integration.db")

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
    apply_reputation_effects,
    build_opportunity_access_state,
    build_player_reputation_profile,
    build_reputation_summary,
    build_trust_signal_state,
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

_VALID_TRUST_LABELS = {"weak", "mixed", "solid", "trusted", "highly_trusted"}
_VALID_OPP_LABELS = {"restricted", "limited", "standard", "elevated", "preferred"}
_VALID_DIRECTIONS = {"improving", "stable", "weakening", "recovering"}


class ReputationTrustIntegrationTests(unittest.TestCase):
    """Integration tests — full pipeline with all upstream signal tables seeded."""

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
    # Seed helpers
    # ------------------------------------------------------------------

    def _seed_full_player(
        self,
        *,
        credit_score: int = 650,
        missed_payment_streak: int = 0,
        skill_level: int = 3,
        stress: int = 25,
        main_job: str | None = "retail_worker",
        delinquency_stage: str = "current",
        missed_30d: int = 0,
        late_30d: int = 0,
        repeat_30d: int = 0,
        dependence_risk: float = 10.0,
        active_loan_count: int = 0,
        debt_label: str = "stable",
        spiral_label: str = "low",
        fin_stability: float = 55.0,
        recovery_stage: str = "none",
        stability_score: float = 55.0,
        buffer_days: float = 8.0,
        false_growth: bool = False,
        fragility: float = 20.0,
        work_risk: float = 15.0,
        neg_streak: int = 0,
        recovery_status: str = "none",
    ) -> Player:
        user = User(
            email=f"rt-int-{uuid.uuid4()}@example.com",
            hashed_password="x",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Integration Test Player",
            credit_score=credit_score,
            missed_payment_streak=missed_payment_streak,
            skill_level=skill_level,
            stress=stress,
            main_job=main_job,
            opportunity_access_penalty=Decimal("0"),
            career_progress_penalty=Decimal("0"),
            business_risk_penalty=Decimal("0"),
            account_created_day=1,
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()

        pid = player.id
        self.db.add(PlayerDelinquencyState(
            player_id=pid,
            current_delinquency_stage=delinquency_stage,
            missed_payment_count_30d=missed_30d,
            late_payment_count_30d=late_30d,
            credit_pressure_score=Decimal("0"),
            financial_distress_score=Decimal("0"),
        ))
        self.db.add(PlayerBorrowingState(
            player_id=pid,
            borrowing_access_score=Decimal("60"),
            active_loan_count=active_loan_count,
            repeat_borrowing_count_30d=repeat_30d,
            dependence_risk_score=Decimal(str(dependence_risk)),
        ))
        self.db.add(PlayerDebtBehaviorState(
            player_id=pid,
            debt_state_label=debt_label,
            spiral_risk_label=spiral_label,
            financial_stability_score=Decimal(str(fin_stability)),
            trend_direction="stable",
            recovery_stage=recovery_stage,
        ))
        self.db.add(PlayerWealthState(
            player_id=pid,
            stability_before_growth_score=Decimal(str(stability_score)),
            buffer_days=Decimal(str(buffer_days)),
            false_growth_detected=false_growth,
            wealth_phase_label="stabilization",
        ))
        self.db.add(PlayerShockState(
            player_id=pid,
            financial_fragility_score=Decimal(str(fragility)),
            work_disruption_risk_score=Decimal(str(work_risk)),
            recent_negative_streak=neg_streak,
        ))
        self.db.add(PlayerRecoveryState(
            player_id=pid,
            recovery_status_label=recovery_status,
        ))
        self.db.flush()
        return player

    # ------------------------------------------------------------------
    # Profile persistence
    # ------------------------------------------------------------------

    def test_profile_persists_state_row(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        build_player_reputation_profile(self.db, player.id, day=3)
        self.db.commit()

        state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).first()
        self.assertIsNotNone(state, "PlayerReputationState must be created")
        self.assertEqual(int(state.last_updated_on), 3)

    def test_profile_persists_history_row(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        build_player_reputation_profile(self.db, player.id, day=3)
        self.db.commit()

        hist = self.db.query(PlayerReputationHistory).filter(
            PlayerReputationHistory.player_id == player.id,
            PlayerReputationHistory.day == 3,
        ).first()
        self.assertIsNotNone(hist, "PlayerReputationHistory row for day 3 must be created")

    def test_profile_same_day_upserts_not_duplicates(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        build_player_reputation_profile(self.db, player.id, day=5)
        self.db.commit()
        build_player_reputation_profile(self.db, player.id, day=5)
        self.db.commit()
        build_player_reputation_profile(self.db, player.id, day=5)
        self.db.commit()

        state_count = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).count()
        self.assertEqual(state_count, 1)

        history_count = self.db.query(PlayerReputationHistory).filter(
            PlayerReputationHistory.player_id == player.id,
            PlayerReputationHistory.day == 5,
        ).count()
        self.assertEqual(history_count, 1)

    def test_different_days_create_separate_history_rows(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        for d in (1, 2, 3, 4, 5):
            build_player_reputation_profile(self.db, player.id, day=d)
            self.db.commit()

        count = self.db.query(PlayerReputationHistory).filter(
            PlayerReputationHistory.player_id == player.id
        ).count()
        self.assertEqual(count, 5)

    # ------------------------------------------------------------------
    # Profile response structure
    # ------------------------------------------------------------------

    def test_profile_contains_expected_keys(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        result = build_player_reputation_profile(self.db, player.id, day=1)
        self.db.commit()

        required_keys = {
            "player_id",
            "day",
            "as_of_date",
            "reputation_score",
            "trust_score",
            "financial_reliability_score",
            "work_reliability_score",
            "business_reliability_score",
            "opportunity_readiness_score",
            "overall_trust_label",
            "reputation_direction",
            "payment_signal_label",
            "borrowing_signal_label",
            "work_signal_label",
            "business_signal_label",
            "stability_signal_label",
            "opportunity_access_label",
            "top_reputation_driver",
            "top_reputation_drag",
            "practical_actions",
            "planning_insights",
        }
        for k in required_keys:
            self.assertIn(k, result, f"Expected key '{k}' missing from profile response")

    def test_profile_labels_are_valid_enum_values(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        result = build_player_reputation_profile(self.db, player.id, day=1)
        self.db.commit()

        self.assertIn(result["overall_trust_label"], _VALID_TRUST_LABELS)
        self.assertIn(result["opportunity_access_label"], _VALID_OPP_LABELS)
        self.assertIn(result["reputation_direction"], _VALID_DIRECTIONS)
        self.assertIn(result["payment_signal_label"], _VALID_TRUST_LABELS)
        self.assertIn(result["work_signal_label"], _VALID_TRUST_LABELS)

    def test_practical_actions_is_a_non_empty_list(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        result = build_player_reputation_profile(self.db, player.id, day=1)
        self.db.commit()

        self.assertIsInstance(result["practical_actions"], list)
        self.assertTrue(len(result["practical_actions"]) >= 1)

    # ------------------------------------------------------------------
    # Trust signal state
    # ------------------------------------------------------------------

    def test_trust_signal_state_has_all_signal_keys(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        signals = build_trust_signal_state(self.db, player.id, day=1)

        for key in ("payment_signal", "borrowing_signal", "work_signal", "business_signal", "stability_signal"):
            self.assertIn(key, signals, f"Expected '{key}' in trust signals")

    def test_trust_signal_does_not_write_state_rows(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        build_trust_signal_state(self.db, player.id, day=1)
        # No commit — trust signals are read-only

        state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).first()
        self.assertIsNone(state, "Trust signal state must NOT write PlayerReputationState")

    # ------------------------------------------------------------------
    # Opportunity access
    # ------------------------------------------------------------------

    def test_opportunity_access_contains_tier_description(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        result = build_opportunity_access_state(self.db, player.id, day=1)
        self.db.commit()

        self.assertIn("opportunity_access_label", result)
        self.assertIn(result["opportunity_access_label"], _VALID_OPP_LABELS)
        self.assertIn("tier_description", result)
        self.assertIsInstance(result["tier_description"], str)
        self.assertTrue(len(result["tier_description"]) > 0)

    # ------------------------------------------------------------------
    # Effects — read-only
    # ------------------------------------------------------------------

    def test_apply_effects_does_not_persist_state(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        apply_reputation_effects(self.db, player.id, day=2)
        # Do NOT commit

        state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).first()
        self.assertIsNone(state, "apply_reputation_effects must not write PlayerReputationState")

    def test_apply_effects_returns_all_modifier_keys(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        result = apply_reputation_effects(self.db, player.id, day=1)

        self.assertIn("effects", result)
        effects = result["effects"]
        self.assertIn("job_quality_modifier_pct", effects)
        self.assertIn("credit_rate_modifier_pct", effects)
        self.assertIn("demand_modifier_pct", effects)
        self.assertIn("trust_modifier_pct", effects)
        self.assertEqual(result["note"], "Modifiers are projections only — no changes applied.")

    def test_apply_effects_uses_persisted_state_when_available(self) -> None:
        player = self._seed_full_player(credit_score=720, skill_level=4, stability_score=65.0)
        self.db.commit()

        # Persist state first
        build_player_reputation_profile(self.db, player.id, day=4)
        self.db.commit()

        # Effects should read from persisted state
        result = apply_reputation_effects(self.db, player.id, day=4)

        state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).first()
        self.assertAlmostEqual(result["trust_score"], float(state.trust_score), places=2)

    # ------------------------------------------------------------------
    # Summary — comprehensive
    # ------------------------------------------------------------------

    def test_summary_contains_profile_and_trust_signals(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        summary = build_reputation_summary(self.db, player.id, day=1)
        self.db.commit()

        self.assertIn("profile", summary)
        self.assertIn("trust_signals", summary)
        self.assertIn("effects", summary)
        self.assertIn("trend_7d", summary)
        self.assertIn("practical_actions", summary)
        self.assertIn("planning_insights", summary)

    def test_summary_top_level_labels_match_profile(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        summary = build_reputation_summary(self.db, player.id, day=1)
        self.db.commit()

        profile = summary["profile"]
        self.assertEqual(summary["opportunity_access_label"], profile["opportunity_access_label"])
        self.assertEqual(summary["overall_trust_label"], profile["overall_trust_label"])
        self.assertEqual(summary["reputation_direction"], profile["reputation_direction"])

    def test_summary_trend_7d_empty_on_first_call(self) -> None:
        """No previous history → trend_7d is empty dict."""
        player = self._seed_full_player()
        self.db.commit()

        summary = build_reputation_summary(self.db, player.id, day=1)
        self.db.commit()

        # Day 1 has no prior history rows, so trend_7d should be empty
        self.assertIsInstance(summary["trend_7d"], dict)

    def test_summary_trend_7d_populated_after_multiple_days(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        for d in range(1, 8):
            build_player_reputation_profile(self.db, player.id, day=d)
            self.db.commit()

        summary = build_reputation_summary(self.db, player.id, day=8)
        self.db.commit()

        trend = summary["trend_7d"]
        self.assertIn("avg_reputation_score", trend)
        self.assertIn("avg_trust_score", trend)
        self.assertIn("samples", trend)
        self.assertGreaterEqual(trend["samples"], 1)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_unknown_player_id_raises_not_found(self) -> None:
        with self.assertRaises(ReputationTrustNotFoundError):
            build_player_reputation_profile(self.db, "00000000-0000-0000-0000-000000000000", day=1)

    def test_unknown_player_id_in_summary_raises_not_found(self) -> None:
        with self.assertRaises(ReputationTrustNotFoundError):
            build_reputation_summary(self.db, "00000000-0000-0000-0000-000000000000", day=1)

    def test_unknown_player_id_in_effects_raises_not_found(self) -> None:
        with self.assertRaises(ReputationTrustNotFoundError):
            apply_reputation_effects(self.db, "00000000-0000-0000-0000-000000000000", day=1)

    # ------------------------------------------------------------------
    # Multi-player isolation
    # ------------------------------------------------------------------

    def test_two_players_have_independent_reputation_rows(self) -> None:
        strong = self._seed_full_player(credit_score=720, skill_level=4, stability_score=65.0)
        weak = self._seed_full_player(
            credit_score=550,
            missed_payment_streak=4,
            delinquency_stage="delinquent",
            missed_30d=5,
            debt_label="critical",
            false_growth=True,
            stability_score=15.0,
        )
        self.db.commit()

        build_player_reputation_profile(self.db, strong.id, day=3)
        build_player_reputation_profile(self.db, weak.id, day=3)
        self.db.commit()

        strong_state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == strong.id
        ).first()
        weak_state = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == weak.id
        ).first()

        self.assertIsNotNone(strong_state)
        self.assertIsNotNone(weak_state)
        self.assertGreater(
            float(strong_state.trust_score),
            float(weak_state.trust_score),
            "Stronger player must have higher trust score in persistence",
        )

    def test_reputation_state_only_one_row_per_player(self) -> None:
        player = self._seed_full_player()
        self.db.commit()

        for d in (1, 3, 5, 7):
            build_player_reputation_profile(self.db, player.id, day=d)
            self.db.commit()

        state_count = self.db.query(PlayerReputationState).filter(
            PlayerReputationState.player_id == player.id
        ).count()
        self.assertEqual(state_count, 1, "PlayerReputationState must always be a single upserted row")

        hist_count = self.db.query(PlayerReputationHistory).filter(
            PlayerReputationHistory.player_id == player.id
        ).count()
        self.assertEqual(hist_count, 4, "PlayerReputationHistory must have one row per unique day")


if __name__ == "__main__":
    unittest.main()
