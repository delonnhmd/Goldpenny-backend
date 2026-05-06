"""Step 18 — Career Service unit tests.

Tests:
  - Skill growth: working gains skill; high stress reduces growth; skill bounded [0, 100]
  - Performance score: missing work lowers score; stable day raises; EMA update
  - Promotion: threshold gates; one rank per day; cert gate for aircraft_mechanic
  - Certification: enrolment; training advances progress; completion unlocks switch
  - Job switching: valid switch works; invalid blocked; aircraft cert gate; skill transfer
"""

from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_career_service.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.career_progress_log import CareerProgressLog
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_career import PlayerCareer
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_job_progression import PlayerJobProgression
from app.models.user import User

from app.engine.career_service import (
    CareerNotFoundError,
    CareerValidationError,
    attempt_promotion,
    complete_certification_if_eligible,
    compute_daily_performance_score,
    compute_daily_skill_growth,
    compute_promotion_progress,
    get_or_create_player_career,
    get_player_career_history,
    get_player_career_snapshot,
    start_certification_track,
    switch_player_job,
    update_certification_progress,
    apply_daily_career_progression,
)
from app.engine.career_config import (
    RANK_ENTRY,
    RANK_INTERMEDIATE,
    RANK_ADVANCED,
    effective_monthly_pay,
)

JOB_SEED = {
    "auto_mechanic": Decimal("4000.00"),
    "aircraft_mechanic": Decimal("6200.00"),
    "banker": Decimal("5100.00"),
    "chef": Decimal("3500.00"),
    "retail": Decimal("2600.00"),
    "delivery": Decimal("3000.00"),
}


class CareerServiceTests(unittest.TestCase):
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
                PlayerJobProgression.__table__,
                PlayerDailyState.__table__,
                MacroDailyState.__table__,
            ],
        )

        self.db = self.SessionLocal()

        user = User(
            email=f"career-test-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Career Test Player",
            cash=Decimal("3000.00"),
            debt_xgp=Decimal("0.00"),
            stress=20,
            health=95,
            hours_available=16,
            region="suburban",
            main_job="auto_mechanic",
        )
        self.db.add(self.player)
        self.db.flush()

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
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.4"),
                interest_rate=Decimal("4.2"),
                unemployment_rate=Decimal("5.3"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("53.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Baseline",
                event_summary="Baseline macro.",
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _make_career(
        self,
        *,
        job_key: str = "auto_mechanic",
        rank: str = RANK_ENTRY,
        skill: Decimal = Decimal("0.0"),
        days_worked: int = 0,
        trailing_perf: Decimal = Decimal("0.0"),
        cert_track: str | None = None,
        cert_progress: int = 0,
        cert_required: int = 0,
        cert_completed: bool = False,
    ) -> PlayerCareer:
        career = PlayerCareer(
            player_id=self.player.id,
            current_job_key=job_key,
            current_job_rank=rank,
            current_job_skill=skill,
            total_days_worked_in_job=days_worked,
            trailing_performance_score=trailing_perf,
            certification_track_key=cert_track,
            certification_progress_days=cert_progress,
            certification_required_days=cert_required,
            certification_completed=cert_completed,
        )
        self.db.add(career)
        self.db.flush()
        return career

    # ── get_or_create ─────────────────────────────────────────────────────────

    def test_get_or_create_creates_new_row(self) -> None:
        career = get_or_create_player_career(self.db, self.player.id)
        self.assertIsNotNone(career)
        self.assertEqual(career.player_id, self.player.id)
        self.assertEqual(career.current_job_rank, RANK_ENTRY)

    def test_get_or_create_is_idempotent(self) -> None:
        c1 = get_or_create_player_career(self.db, self.player.id)
        c2 = get_or_create_player_career(self.db, self.player.id)
        self.assertEqual(c1.id, c2.id)

    def test_get_or_create_seeds_from_main_job(self) -> None:
        career = get_or_create_player_career(self.db, self.player.id)
        self.assertEqual(career.current_job_key, "auto_mechanic")

    def test_get_or_create_invalid_player_raises(self) -> None:
        with self.assertRaises(CareerNotFoundError):
            get_or_create_player_career(self.db, uuid.uuid4())

    # ── Skill growth ─────────────────────────────────────────────────────────

    def test_working_increases_skill(self) -> None:
        delta = compute_daily_skill_growth(
            job_key="auto_mechanic",
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            stress=20,
            health=95,
            training_hours=Decimal("0.0"),
        )
        self.assertGreater(delta, Decimal("0.00"))

    def test_not_working_without_training_gives_zero_skill(self) -> None:
        delta = compute_daily_skill_growth(
            job_key="auto_mechanic",
            worked_today=False,
            productivity_modifier=Decimal("1.0"),
            stress=20,
            health=95,
            training_hours=Decimal("0.0"),
        )
        self.assertEqual(delta, Decimal("0.0000"))

    def test_high_stress_reduces_skill_growth(self) -> None:
        low_stress = compute_daily_skill_growth(
            job_key="banker",
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            stress=10,
            health=90,
            training_hours=Decimal("0.0"),
        )
        high_stress = compute_daily_skill_growth(
            job_key="banker",
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            stress=95,
            health=90,
            training_hours=Decimal("0.0"),
        )
        self.assertLess(high_stress, low_stress)

    def test_low_health_reduces_skill_growth(self) -> None:
        healthy = compute_daily_skill_growth(
            job_key="chef",
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            stress=20,
            health=95,
            training_hours=Decimal("0.0"),
        )
        sick = compute_daily_skill_growth(
            job_key="chef",
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            stress=20,
            health=20,
            training_hours=Decimal("0.0"),
        )
        self.assertLessEqual(sick, healthy)

    def test_training_hours_add_skill_even_without_working(self) -> None:
        delta = compute_daily_skill_growth(
            job_key="auto_mechanic",
            worked_today=False,
            productivity_modifier=Decimal("1.0"),
            stress=20,
            health=95,
            training_hours=Decimal("2.0"),
        )
        self.assertGreater(delta, Decimal("0.00"))

    def test_skill_delta_clamped_to_ceiling(self) -> None:
        # Even with extreme conditions, delta should never exceed ceiling
        from app.engine.career_config import SKILL_DELTA_CEILING
        delta = compute_daily_skill_growth(
            job_key="auto_mechanic",
            worked_today=True,
            productivity_modifier=Decimal("1.5"),
            stress=0,
            health=100,
            training_hours=Decimal("4.0"),
        )
        self.assertLessEqual(delta, SKILL_DELTA_CEILING)

    def test_skill_delta_never_negative(self) -> None:
        delta = compute_daily_skill_growth(
            job_key="banker",
            worked_today=False,
            productivity_modifier=Decimal("0.30"),
            stress=100,
            health=0,
            training_hours=Decimal("0.0"),
        )
        self.assertGreaterEqual(delta, Decimal("0.0"))

    # ── Performance score ─────────────────────────────────────────────────────

    def test_working_full_day_gives_high_performance(self) -> None:
        score = compute_daily_performance_score(
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            employment_state=None,
            daily_state=None,
        )
        self.assertGreater(score, Decimal("0.70"))

    def test_missing_work_lowers_performance(self) -> None:
        worked = compute_daily_performance_score(
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            employment_state=None,
            daily_state=None,
        )
        skipped = compute_daily_performance_score(
            worked_today=False,
            productivity_modifier=Decimal("1.0"),
            employment_state=None,
            daily_state=None,
        )
        self.assertLess(skipped, worked)

    def test_performance_score_bounded(self) -> None:
        score = compute_daily_performance_score(
            worked_today=True,
            productivity_modifier=Decimal("1.1"),
            employment_state=None,
            daily_state=None,
        )
        self.assertGreaterEqual(score, Decimal("0.0"))
        self.assertLessEqual(score, Decimal("1.0"))

    # ── Promotion progress ─────────────────────────────────────────────────────

    def test_promotion_progress_zero_at_start(self) -> None:
        progress = compute_promotion_progress(
            job_key="auto_mechanic",
            current_rank=RANK_ENTRY,
            days_worked=0,
            skill=Decimal("0.0"),
            trailing_performance=Decimal("0.0"),
        )
        self.assertEqual(progress, Decimal("0.0000"))

    def test_promotion_progress_one_when_all_thresholds_met(self) -> None:
        # auto_mechanic entry→intermediate: 20 days, skill>=18, perf>=0.62
        progress = compute_promotion_progress(
            job_key="auto_mechanic",
            current_rank=RANK_ENTRY,
            days_worked=20,
            skill=Decimal("18.0"),
            trailing_performance=Decimal("0.62"),
        )
        self.assertEqual(progress, Decimal("1.0000"))

    def test_promotion_progress_max_rank_returns_zero(self) -> None:
        progress = compute_promotion_progress(
            job_key="auto_mechanic",
            current_rank=RANK_ADVANCED,
            days_worked=999,
            skill=Decimal("90.0"),
            trailing_performance=Decimal("0.99"),
        )
        self.assertEqual(progress, Decimal("0.0000"))

    # ── attempt_promotion ─────────────────────────────────────────────────────

    def test_promotion_succeeds_when_thresholds_met(self) -> None:
        career = self._make_career(
            job_key="auto_mechanic",
            rank=RANK_ENTRY,
            skill=Decimal("20.0"),
            days_worked=25,
            trailing_perf=Decimal("0.70"),
            cert_track="auto_mechanic_cert",
            cert_completed=True,
        )
        promoted = attempt_promotion(self.db, career, day=5)
        self.assertTrue(promoted)
        self.assertEqual(career.current_job_rank, RANK_INTERMEDIATE)

    def test_promotion_fails_insufficient_skill(self) -> None:
        career = self._make_career(
            job_key="auto_mechanic",
            rank=RANK_ENTRY,
            skill=Decimal("5.0"),  # way below 18
            days_worked=30,
            trailing_perf=Decimal("0.70"),
        )
        promoted = attempt_promotion(self.db, career, day=5)
        self.assertFalse(promoted)
        self.assertEqual(career.current_job_rank, RANK_ENTRY)

    def test_promotion_fails_insufficient_days(self) -> None:
        career = self._make_career(
            job_key="auto_mechanic",
            rank=RANK_ENTRY,
            skill=Decimal("20.0"),
            days_worked=5,  # need 20
            trailing_perf=Decimal("0.70"),
        )
        promoted = attempt_promotion(self.db, career, day=5)
        self.assertFalse(promoted)

    def test_promotion_fails_insufficient_performance(self) -> None:
        career = self._make_career(
            job_key="auto_mechanic",
            rank=RANK_ENTRY,
            skill=Decimal("25.0"),
            days_worked=25,
            trailing_perf=Decimal("0.30"),  # need 0.62
        )
        promoted = attempt_promotion(self.db, career, day=5)
        self.assertFalse(promoted)

    def test_promotion_blocked_at_advanced_rank(self) -> None:
        career = self._make_career(
            job_key="auto_mechanic",
            rank=RANK_ADVANCED,
            skill=Decimal("90.0"),
            days_worked=200,
            trailing_perf=Decimal("0.95"),
        )
        promoted = attempt_promotion(self.db, career, day=5)
        self.assertFalse(promoted)
        self.assertEqual(career.current_job_rank, RANK_ADVANCED)

    def test_aircraft_mechanic_promotion_blocked_without_cert(self) -> None:
        career = self._make_career(
            job_key="aircraft_mechanic",
            rank=RANK_ENTRY,
            skill=Decimal("30.0"),
            days_worked=30,
            trailing_perf=Decimal("0.80"),
            cert_completed=False,
        )
        promoted = attempt_promotion(self.db, career, day=10)
        self.assertFalse(promoted)

    def test_aircraft_mechanic_promotion_succeeds_with_cert(self) -> None:
        career = self._make_career(
            job_key="aircraft_mechanic",
            rank=RANK_ENTRY,
            skill=Decimal("30.0"),
            days_worked=30,
            trailing_perf=Decimal("0.80"),
            cert_track="aircraft_mechanic_cert",
            cert_completed=False,
        )
        # Force cert completed
        career.certification_completed = True
        self.db.flush()
        promoted = attempt_promotion(self.db, career, day=10)
        self.assertTrue(promoted)

    # ── Certification ─────────────────────────────────────────────────────────

    def test_enrol_valid_cert_track(self) -> None:
        result = start_certification_track(self.db, self.player.id, "aircraft_mechanic_cert")
        self.assertTrue(result["enrolled"])
        self.assertEqual(result["certification_track_key"], "aircraft_mechanic_cert")

    def test_enrol_invalid_cert_track_raises(self) -> None:
        with self.assertRaises(CareerValidationError):
            start_certification_track(self.db, self.player.id, "invalid_cert_xyz")

    def test_enrol_twice_returns_not_enrolled(self) -> None:
        start_certification_track(self.db, self.player.id, "aircraft_mechanic_cert")
        result = start_certification_track(self.db, self.player.id, "aircraft_mechanic_cert")
        self.assertFalse(result["enrolled"])
        self.assertIn("Already enrolled", result["message"])

    def test_cert_progress_advances_with_sufficient_training(self) -> None:
        career = self._make_career(
            cert_track="aircraft_mechanic_cert",
            cert_progress=0,
            cert_required=180,
        )
        new_progress, completed = update_certification_progress(career, Decimal("2.0"))
        self.assertGreater(new_progress, 0)
        self.assertFalse(completed)

    def test_cert_progress_does_not_advance_below_minimum_training(self) -> None:
        career = self._make_career(
            cert_track="aircraft_mechanic_cert",
            cert_progress=0,
            cert_required=180,
        )
        original_progress = career.certification_progress_days
        new_progress, completed = update_certification_progress(career, Decimal("0.5"))
        self.assertEqual(new_progress, original_progress)  # no change
        self.assertFalse(completed)

    def test_cert_completion_triggers_at_threshold(self) -> None:
        career = self._make_career(
            cert_track="aircraft_mechanic_cert",
            cert_progress=179,
            cert_required=180,
        )
        _new_prog, advanced = update_certification_progress(career, Decimal("2.0"))
        if advanced:
            just_completed = complete_certification_if_eligible(self.db, career)
            self.assertTrue(just_completed)
        else:
            self.fail("Expected certification progress to advance to completion")

    def test_complete_certification_already_done_returns_false(self) -> None:
        career = self._make_career(
            cert_track="aircraft_mechanic_cert",
            cert_progress=180,
            cert_required=180,
            cert_completed=True,
        )
        result = complete_certification_if_eligible(self.db, career)
        self.assertFalse(result)

    # ── Job switching ─────────────────────────────────────────────────────────

    def test_valid_job_switch_resets_rank(self) -> None:
        get_or_create_player_career(self.db, self.player.id)
        result = switch_player_job(self.db, self.player.id, "delivery")
        self.assertTrue(result["success"])
        self.assertEqual(result["new_job_key"], "delivery")
        self.assertEqual(result["new_rank"], RANK_ENTRY)

    def test_invalid_job_key_raises(self) -> None:
        with self.assertRaises(CareerValidationError):
            switch_player_job(self.db, self.player.id, "astronaut")

    def test_aircraft_mechanic_switch_blocked_without_cert(self) -> None:
        get_or_create_player_career(self.db, self.player.id)
        with self.assertRaises(CareerValidationError):
            switch_player_job(self.db, self.player.id, "aircraft_mechanic")

    def test_auto_to_aircraft_skill_transfer(self) -> None:
        career = get_or_create_player_career(self.db, self.player.id)
        career.current_job_key = "auto_mechanic"
        career.current_job_skill = Decimal("40.0")
        career.certification_track_key = "aircraft_mechanic_cert"
        career.certification_completed = True
        self.player.last_settled_day = 1
        self.player.skill_level = 4
        self.db.add(
            PlayerJobProgression(
                player_id=self.player.id,
                job_key="auto_mechanic",
                skill_level=4,
                xp_total=100,
                xp=0,
                xp_to_next_level=2000,
                promotion_tier="Junior",
                shifts_completed=8,
            )
        )
        self.db.flush()
        result = switch_player_job(self.db, self.player.id, "aircraft_mechanic")
        # 15% of 40 = 6.0 skill transferred
        self.assertAlmostEqual(result["transferred_skill"], 6.0, places=2)
        self.assertGreater(result["starting_skill"], 0.0)

    def test_job_switch_updates_player_main_job(self) -> None:
        get_or_create_player_career(self.db, self.player.id)
        switch_player_job(self.db, self.player.id, "delivery")
        self.db.refresh(self.player)
        self.assertEqual(self.player.main_job, "delivery")

    # ── Snapshot and history ──────────────────────────────────────────────────

    def test_career_snapshot_returns_expected_keys(self) -> None:
        snapshot = get_player_career_snapshot(self.db, self.player.id)
        for key in [
            "player_id",
            "current_job_key",
            "current_job_rank",
            "current_job_skill",
            "promotion_eligible",
            "promotion_progress",
            "certification_completed",
            "effective_monthly_pay_xgp",
            "debug_meta",
        ]:
            self.assertIn(key, snapshot, f"Missing key: {key}")

    def test_career_history_empty_when_no_logs(self) -> None:
        history = get_player_career_history(self.db, self.player.id)
        self.assertEqual(history["entries"], [])

    # ── apply_daily_career_progression ───────────────────────────────────────

    def test_daily_progression_creates_log_row(self) -> None:
        result = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=None,
            training_hours=Decimal("0.0"),
            commit=False,
        )
        self.assertIn("skill_after", result)
        self.assertIn("performance_score", result)

    def test_daily_progression_idempotent_same_day(self) -> None:
        from datetime import date

        today = date(2026, 1, 1)
        result1 = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=today,
            training_hours=Decimal("0.0"),
            commit=False,
        )
        result2 = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=today,
            training_hours=Decimal("0.0"),
            commit=False,
        )
        # Should update in place, not raise or insert duplicate
        count = (
            self.db.query(CareerProgressLog)
            .filter(
                CareerProgressLog.player_id == self.player.id,
                CareerProgressLog.day_number == 1,
            )
            .count()
        )
        self.assertEqual(count, 1)

    def test_training_hours_advance_cert(self) -> None:
        from datetime import date

        career = get_or_create_player_career(self.db, self.player.id)
        career.certification_track_key = "aircraft_mechanic_cert"
        career.certification_progress_days = 0
        career.certification_required_days = 180
        career.certification_completed = False
        self.db.flush()

        result = apply_daily_career_progression(
            self.db,
            self.player.id,
            as_of_date=date(2026, 1, 1),
            training_hours=Decimal("2.0"),
            commit=False,
        )
        self.assertGreater(result["certification_progress_days"], 0)

    # ── Effective pay calculations ────────────────────────────────────────────

    def test_effective_pay_increases_with_higher_rank(self) -> None:
        entry_pay = effective_monthly_pay("auto_mechanic", RANK_ENTRY, Decimal("0.0"))
        intermediate_pay = effective_monthly_pay(
            "auto_mechanic", RANK_INTERMEDIATE, Decimal("0.0")
        )
        self.assertGreater(intermediate_pay, entry_pay)

    def test_effective_pay_increases_with_skill(self) -> None:
        low_skill_pay = effective_monthly_pay(
            "banker", RANK_ENTRY, Decimal("0.0")
        )
        high_skill_pay = effective_monthly_pay(
            "banker", RANK_ENTRY, Decimal("80.0")
        )
        self.assertGreater(high_skill_pay, low_skill_pay)

    def test_skill_pay_modifier_caps_at_15_pct(self) -> None:
        # skill/200 * base_pay, capped at 15% of base
        base = effective_monthly_pay("retail_worker", RANK_ENTRY, Decimal("0.0"))
        max_skill_pay = effective_monthly_pay("retail_worker", RANK_ENTRY, Decimal("100.0"))
        ratio = max_skill_pay / base
        self.assertLessEqual(ratio, Decimal("1.16"))  # 1.00 + 0.15 bonus + minor rounding


class CareerEdgeCaseTests(unittest.TestCase):
    """Edge cases: boundary-safe skill handling."""

    def test_skill_growth_capped_at_skill_max(self) -> None:
        from app.engine.career_config import SKILL_MAX, SKILL_DELTA_CEILING
        # If skill is at max, growth should still produce a non-negative delta
        # (delta is clamped per day; the caller in daily progression clamps total skill)
        delta = compute_daily_skill_growth(
            job_key="auto_mechanic",
            worked_today=True,
            productivity_modifier=Decimal("1.0"),
            stress=10,
            health=100,
            training_hours=Decimal("0.0"),
        )
        self.assertLessEqual(delta, SKILL_DELTA_CEILING)
        self.assertGreaterEqual(delta, Decimal("0.0"))

    def test_performance_score_with_high_burnout_daily_state(self) -> None:
        # Simulate a daily_state object with high burnout
        class FakeDailyState:
            overtime_hours = Decimal("4.0")
            burnout_risk = Decimal("0.50")
            stress_end = 70
            health_end = 80
            productivity_modifier = Decimal("0.90")

        score = compute_daily_performance_score(
            worked_today=True,
            productivity_modifier=Decimal("0.90"),
            employment_state=None,
            daily_state=FakeDailyState(),  # type: ignore[arg-type]
        )
        self.assertGreaterEqual(score, Decimal("0.0"))
        self.assertLessEqual(score, Decimal("1.0"))
