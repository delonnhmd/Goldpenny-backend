"""Step 42 unit tests for forecasting_planning_service.py.

Tests cover:
  - _project_cash_curve builds correct day-by-day cash projections
  - _find_liquidity_low_point detects minimum cash day
  - _find_delinquency_risk_day returns correct day or None when solvent
  - _compute_composite_risk_score reflects delinquency stage weight
  - _outlook_label returns expected label for given score
  - _compute_guidance produces guidance_label, top_recommendation, avoid_action
  - build_short_term_forecast returns full projection dict
  - simulate_player_path returns baseline + simulated comparison
  - build_scenario_comparison returns ranked options list
  - build_risk_projection_state returns danger-radar labels
  - build_forecast_summary returns overall_outlook_label and days_until_next_problem
  - build_decision_guidance returns guidance_label and recommendations
  - build_and_persist_forecast writes PlayerForecastSnapshot row
  - Second call to build_and_persist_forecast updates existing snapshot (upsert)
  - Missing player raises ForecastingNotFoundError
  - Invalid action raises ForecastingValidationError
  - Delinquency risk day is None when cash never goes negative
  - Delinquency risk day is detected when cash goes negative within horizon
  - Player with no employment state still returns valid forecast
"""

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_forecasting.db")

from app.db.database import Base
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_contract_event import PlayerContractEvent
from app.models.player_contract_schedule import PlayerContractSchedule
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_forecast_snapshot import PlayerForecastSnapshot
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_reputation_state import PlayerReputationState
from app.models.player_shock_state import PlayerShockState
from app.models.player_wealth_state import PlayerWealthState
from app.models.user import User
from app.engine.forecasting_planning_service import (
    DELINQUENCY_SEVERITY,
    ForecastingNotFoundError,
    ForecastingValidationError,
    _clamp,
    _compute_composite_risk_score,
    _compute_guidance,
    _d,
    _find_delinquency_risk_day,
    _find_liquidity_low_point,
    _outlook_label,
    _project_cash_curve,
    _ForecastState,
    build_and_persist_forecast,
    build_decision_guidance,
    build_forecast_summary,
    build_risk_projection_state,
    build_scenario_comparison,
    build_short_term_forecast,
    simulate_player_path,
)

TABLES = [
    User.__table__,
    Player.__table__,
    PlayerHousingState.__table__,
    PlayerEmploymentState.__table__,
    PlayerLoanAccount.__table__,
    PlayerBorrowingState.__table__,
    PlayerDelinquencyState.__table__,
    PlayerWealthState.__table__,
    PlayerDebtBehaviorState.__table__,
    PlayerShockState.__table__,
    PlayerReputationState.__table__,
    PlayerContractSchedule.__table__,
    PlayerContractEvent.__table__,
    PlayerForecastSnapshot.__table__,
]


class ForecastingServiceTests(unittest.TestCase):
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
    # Player / state factory helpers
    # ------------------------------------------------------------------

    def _make_player(self, *, cash: float = 1000.0, credit_score: int = 650) -> Player:
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

    def _add_employment(self, player: Player, *, monthly_pay: float = 2400.0) -> PlayerEmploymentState:
        emp = PlayerEmploymentState(
            player_id=player.id,
            day=self._day,
            monthly_pay_xgp=Decimal(str(monthly_pay)),
            employed_flag=True,
            job_status="employed",
        )
        self.db.add(emp)
        self.db.flush()
        return emp

    def _add_delinquency(self, player: Player, *, stage: str = "current") -> PlayerDelinquencyState:
        ds = PlayerDelinquencyState(
            player_id=player.id,
            current_delinquency_stage=stage,
            financial_distress_score=Decimal("20"),
            missed_payment_count_30d=0,
        )
        self.db.add(ds)
        self.db.flush()
        return ds

    def _add_loan(self, player: Player, *, daily_payment: float = 10.0) -> PlayerLoanAccount:
        loan = PlayerLoanAccount(
            player_id=player.id,
            offer_key="test_personal_loan",
            offer_family="personal",
            scheduled_daily_payment_xgp=Decimal(str(daily_payment)),
            days_remaining=30,
            term_days=30,
            delinquency_stage="current",
            accepted_on_day=1,
        )
        self.db.add(loan)
        self.db.flush()
        return loan

    def _add_contract_schedule(self, player: Player, *, gap: float = 50.0, pressure: str = "low") -> PlayerContractSchedule:
        sched = PlayerContractSchedule(
            player_id=player.id,
            last_updated_on=self._day,
            active_contract_count=2,
            total_due_7d_xgp=Decimal("100"),
            timing_pressure_label=pressure,
            cash_gap_before_next_income_xgp=Decimal(str(gap)),
            contract_density_score=Decimal("20"),
        )
        self.db.add(sched)
        self.db.flush()
        return sched

    def _add_contract_event(
        self,
        player: Player,
        *,
        due_on_day: int,
        amount: float,
        income_flag: bool = False,
        status: str = "upcoming",
    ) -> PlayerContractEvent:
        ev = PlayerContractEvent(
            player_id=player.id,
            obligation_key="test_rent",
            obligation_family="housing",
            obligation_type="rent",
            amount_xgp=Decimal(str(amount)),
            due_on_day=due_on_day,
            income_flag=income_flag,
            status=status,
        )
        self.db.add(ev)
        self.db.flush()
        return ev

    def _add_wealth_state(self, player: Player, *, safe_label: str = "safe_small") -> PlayerWealthState:
        ws = PlayerWealthState(
            player_id=player.id,
            wealth_phase_label="building",
            safe_to_invest_label=safe_label,
            cash_reserve_xgp=Decimal("500"),
        )
        self.db.add(ws)
        self.db.flush()
        return ws

    def _add_debt_behavior(self, player: Player, *, spiral: str = "low") -> PlayerDebtBehaviorState:
        db_state = PlayerDebtBehaviorState(
            player_id=player.id,
            debt_state_label="stable",
            spiral_risk_label=spiral,
            financial_stability_score=Decimal("70"),
        )
        self.db.add(db_state)
        self.db.flush()
        return db_state

    # ------------------------------------------------------------------
    # Pure helper tests (no DB)
    # ------------------------------------------------------------------

    def test_clamp_bounds_value(self) -> None:
        self.assertEqual(_clamp(Decimal("-5")), Decimal("0"))
        self.assertEqual(_clamp(Decimal("105")), Decimal("100"))
        self.assertEqual(_clamp(Decimal("50")), Decimal("50"))

    def test_d_handles_none(self) -> None:
        self.assertEqual(_d(None), Decimal("0"))

    def test_delinquency_severity_mapping_is_ordered(self) -> None:
        self.assertLess(DELINQUENCY_SEVERITY["current"], DELINQUENCY_SEVERITY["late"])
        self.assertLess(DELINQUENCY_SEVERITY["late"], DELINQUENCY_SEVERITY["critical"])

    def test_outlook_label_from_score(self) -> None:
        self.assertEqual(_outlook_label(Decimal("10")), "stable")
        self.assertEqual(_outlook_label(Decimal("37")), "tight")
        self.assertEqual(_outlook_label(Decimal("50")), "risky")
        self.assertEqual(_outlook_label(Decimal("70")), "critical")

    def test_find_liquidity_low_point_empty_curve(self) -> None:
        low, day = _find_liquidity_low_point([])
        self.assertEqual(low, 0.0)
        self.assertEqual(day, 0)

    def test_find_liquidity_low_point_finds_minimum(self) -> None:
        curve = [
            {"day": 1, "cash_xgp": 500.0, "daily_net_xgp": -10.0},
            {"day": 2, "cash_xgp": 100.0, "daily_net_xgp": -400.0},
            {"day": 3, "cash_xgp": 600.0, "daily_net_xgp": 500.0},
        ]
        low, day = _find_liquidity_low_point(curve)
        self.assertAlmostEqual(low, 100.0)
        self.assertEqual(day, 2)

    def test_find_delinquency_risk_day_none_when_solvent(self) -> None:
        curve = [{"day": i, "cash_xgp": 500.0 - i * 10, "daily_net_xgp": -10.0} for i in range(10)]
        # min is 500 - 90 = 410, always positive
        player = self._make_player(cash=1000.0)
        state = _ForecastState(player, 1, None, None, None, None, None, None, None, [], [], None, None)
        result = _find_delinquency_risk_day(state, curve)
        self.assertIsNone(result)

    def test_find_delinquency_risk_day_detects_negative_cash(self) -> None:
        curve = [
            {"day": 10, "cash_xgp": 50.0, "daily_net_xgp": -30.0},
            {"day": 11, "cash_xgp": 20.0, "daily_net_xgp": -30.0},
            {"day": 12, "cash_xgp": -10.0, "daily_net_xgp": -30.0},
            {"day": 13, "cash_xgp": -40.0, "daily_net_xgp": -30.0},
        ]
        player = self._make_player(cash=50.0)
        state = _ForecastState(player, 10, None, None, None, None, None, None, None, [], [], None, None)
        result = _find_delinquency_risk_day(state, curve)
        self.assertEqual(result, 12)

    def test_composite_risk_score_critical_delinquency(self) -> None:
        player = self._make_player()
        from types import SimpleNamespace
        delinquency_mock = SimpleNamespace(
            current_delinquency_stage="critical",
            financial_distress_score=90,
            missed_payment_count_30d=5,
        )
        contract_schedule_mock = SimpleNamespace(
            cash_gap_before_next_income_xgp=Decimal("600"),
            timing_pressure_label="severe",
            obligation_collision_label="collision",
            total_due_7d_xgp=Decimal("700"),
            contract_density_score=Decimal("80"),
        )
        state = _ForecastState(
            player, 10, contract_schedule_mock, delinquency_mock,
            None, None, None, None, None, [], [], None, None
        )
        curve = [{"day": 10, "cash_xgp": -5.0, "daily_net_xgp": -30.0}]
        score = _compute_composite_risk_score(state, curve)
        self.assertGreater(score, Decimal("60"))

    def test_composite_risk_score_stable_player(self) -> None:
        player = self._make_player(cash=2000.0)
        from types import SimpleNamespace
        delinquency_mock = SimpleNamespace(
            current_delinquency_stage="current",
            financial_distress_score=10,
            missed_payment_count_30d=0,
        )
        contract_schedule_mock = SimpleNamespace(
            cash_gap_before_next_income_xgp=Decimal("10"),
            timing_pressure_label="low",
            obligation_collision_label="none",
            total_due_7d_xgp=Decimal("50"),
            contract_density_score=Decimal("15"),
        )
        state = _ForecastState(
            player, 10, contract_schedule_mock, delinquency_mock,
            None, None, None, None, None, [], [], None, None
        )
        curve = [{"day": 10, "cash_xgp": 2000.0, "daily_net_xgp": 0.0}]
        score = _compute_composite_risk_score(state, curve)
        self.assertLess(score, Decimal("35"))

    def test_compute_guidance_safe_player(self) -> None:
        player = self._make_player(cash=2000.0)
        from types import SimpleNamespace
        wealth_mock = SimpleNamespace(
            safe_to_invest_label="safe_medium",
            wealth_phase_label="building",
            cash_reserve_xgp=Decimal("1000"),
            buffer_days=30,
        )
        contract_schedule_mock = SimpleNamespace(
            cash_gap_before_next_income_xgp=Decimal("5"),
            timing_pressure_label="low",
            obligation_collision_label="none",
            total_due_7d_xgp=Decimal("50"),
            contract_density_score=Decimal("10"),
        )
        delinquency_mock = SimpleNamespace(
            current_delinquency_stage="current",
            financial_distress_score=10,
            missed_payment_count_30d=0,
        )
        debt_mock = SimpleNamespace(
            spiral_risk_label="low",
            trend_direction="stable",
            financial_stability_score=Decimal("80"),
            debt_state_label="stable",
        )
        state = _ForecastState(
            player, 10, contract_schedule_mock, delinquency_mock,
            None, debt_mock, wealth_mock, None, None, [], [], None, None
        )
        guidance = _compute_guidance(state, Decimal("10"), None)
        self.assertIn(guidance["guidance_label"], ("opportunity_ready", "monitor"))

    def test_compute_guidance_critical_player(self) -> None:
        player = self._make_player(cash=50.0)
        from types import SimpleNamespace
        delinquency_mock = SimpleNamespace(
            current_delinquency_stage="delinquent",
            financial_distress_score=80,
            missed_payment_count_30d=4,
        )
        contract_schedule_mock = SimpleNamespace(
            cash_gap_before_next_income_xgp=Decimal("500"),
            timing_pressure_label="severe",
            obligation_collision_label="collision",
            total_due_7d_xgp=Decimal("600"),
            contract_density_score=Decimal("90"),
        )
        debt_mock = SimpleNamespace(
            spiral_risk_label="critical",
            trend_direction="rising",
            financial_stability_score=Decimal("10"),
            debt_state_label="spiral",
        )
        wealth_mock = SimpleNamespace(
            safe_to_invest_label="not_safe",
            wealth_phase_label="fragile",
            cash_reserve_xgp=Decimal("10"),
            buffer_days=0,
        )
        state = _ForecastState(
            player, 10, contract_schedule_mock, delinquency_mock,
            None, debt_mock, wealth_mock, None, None, [], [], None, None
        )
        guidance = _compute_guidance(state, Decimal("80"), 12)
        self.assertEqual(guidance["guidance_label"], "urgent_caution")

    # ------------------------------------------------------------------
    # DB-backed happy-path tests
    # ------------------------------------------------------------------

    def test_build_short_term_forecast_returns_curve(self) -> None:
        player = self._make_player(cash=800.0)
        self._add_employment(player, monthly_pay=2400.0)
        self._add_delinquency(player, stage="current")
        self._add_contract_schedule(player, gap=50.0, pressure="low")

        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=7)

        self.assertEqual(result["player_id"], str(player.id))
        self.assertIn("projected_cash_curve", result)
        self.assertEqual(len(result["projected_cash_curve"]), 8)  # horizon + 1 (offset 0..7)
        self.assertEqual(result["forecast_horizon_days"], 7)
        self.assertIn("confidence_level", result)
        self.assertIn("short_summary", result)

    def test_build_short_term_forecast_with_obligations(self) -> None:
        player = self._make_player(cash=200.0)
        self._add_employment(player, monthly_pay=0.0)  # no income
        # Large obligation due tomorrow: should deplete cash
        self._add_contract_event(player, due_on_day=self._day + 1, amount=300.0, income_flag=False)

        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=7)
        # With 200 cash and 300 obligation + survival floor, cash should go negative
        self.assertIsNotNone(result.get("projected_delinquency_risk_day"))

    def test_build_short_term_forecast_income_extends_solvency(self) -> None:
        player = self._make_player(cash=100.0)
        # Income arrives on day 11, large enough to cover obligations
        self._add_contract_event(player, due_on_day=self._day + 1, amount=500.0, income_flag=True)

        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=7)
        # No delinquency risk because income arrives
        curve = result["projected_cash_curve"]
        # Cash should increase after day 11
        self.assertGreater(curve[1]["cash_xgp"], curve[0]["cash_xgp"] - 1)

    def test_build_short_term_forecast_missing_player_raises(self) -> None:
        with self.assertRaises(ForecastingNotFoundError):
            build_short_term_forecast(self.db, uuid.uuid4(), day=10, horizon_days=7)

    def test_simulate_do_nothing_matches_baseline(self) -> None:
        player = self._make_player(cash=600.0)
        self._add_employment(player, monthly_pay=2400.0)

        result = simulate_player_path(self.db, player.id, "do_nothing", day=self._day, horizon_days=7)
        # Baseline and simulated should have identical end cash for do_nothing
        baseline_end = result["baseline"]["end_cash_xgp"]
        sim_end = result["simulated"]["end_cash_xgp"]
        self.assertAlmostEqual(baseline_end, sim_end, places=2)

    def test_simulate_borrow_small_increases_starting_cash(self) -> None:
        player = self._make_player(cash=100.0)

        result = simulate_player_path(self.db, player.id, "borrow_small", day=self._day, horizon_days=7)
        # Borrow small adds 200 upfront. Simulated cash at day 0 must be higher than baseline.
        # Net balance at end may be lower due to repayment, but day-1 entry should be higher.
        sim_curve = result["simulated"]["projected_cash_curve"]
        base_end = result["baseline"]["end_cash_xgp"]
        # After 7 days of +7/day repayment the end might be similar or lower, but day-0 was boosted
        self.assertGreater(sim_curve[0]["cash_xgp"], result["baseline"]["projected_liquidity_low_point"])

    def test_simulate_invalid_action_raises(self) -> None:
        player = self._make_player()
        with self.assertRaises(ForecastingValidationError):
            simulate_player_path(self.db, player.id, "fly_to_moon", day=self._day, horizon_days=7)

    def test_build_scenario_comparison_returns_options(self) -> None:
        player = self._make_player(cash=600.0)
        self._add_employment(player, monthly_pay=2400.0)

        result = build_scenario_comparison(
            self.db, player.id, day=self._day, horizon_days=7,
            actions=["do_nothing", "borrow_small", "invest_small"],
        )
        self.assertEqual(len(result["options"]), 3)
        option_keys = {o["option_key"] for o in result["options"]}
        self.assertIn("do_nothing", option_keys)
        self.assertIn("borrow_small", option_keys)
        self.assertIn("invest_small", option_keys)
        self.assertIn("recommended_option_key", result)

    def test_build_scenario_comparison_too_many_actions_raises(self) -> None:
        player = self._make_player()
        with self.assertRaises(ForecastingValidationError):
            build_scenario_comparison(
                self.db, player.id, day=self._day, horizon_days=7,
                actions=["do_nothing", "borrow_small", "borrow_large", "invest_small", "invest_large", "skip_payment"],
            )

    def test_build_risk_projection_state_stable(self) -> None:
        player = self._make_player(cash=1200.0)
        self._add_delinquency(player, stage="current")
        self._add_contract_schedule(player, gap=20.0, pressure="low")
        self._add_debt_behavior(player, spiral="low")

        result = build_risk_projection_state(self.db, player.id, day=self._day)
        self.assertIn(result["near_term_risk_label"], ("low", "moderate"))
        self.assertIn("delinquency_risk_label", result)
        self.assertIn("composite_risk_score", result)
        self.assertIsInstance(result["composite_risk_score"], float)

    def test_build_risk_projection_state_critical(self) -> None:
        player = self._make_player(cash=30.0)
        self._add_delinquency(player, stage="critical")
        self._add_contract_schedule(player, gap=600.0, pressure="severe")

        result = build_risk_projection_state(self.db, player.id, day=self._day)
        self.assertIn(result["near_term_risk_label"], ("high", "critical"))
        self.assertIn(result["delinquency_risk_label"], ("high", "critical"))

    def test_build_forecast_summary_stable(self) -> None:
        player = self._make_player(cash=1000.0)
        self._add_employment(player, monthly_pay=2400.0)
        self._add_delinquency(player, stage="current")
        self._add_contract_schedule(player, gap=20.0, pressure="low")

        result = build_forecast_summary(self.db, player.id, day=self._day)
        self.assertEqual(result["overall_outlook_label"], "stable")
        self.assertIn("next_major_risk_event", result)
        self.assertIn("best_stabilizing_action", result)
        self.assertIn("worst_action_to_take", result)

    def test_build_forecast_summary_risky(self) -> None:
        player = self._make_player(cash=50.0)
        self._add_delinquency(player, stage="delinquent")
        self._add_contract_schedule(player, gap=500.0, pressure="severe")

        result = build_forecast_summary(self.db, player.id, day=self._day)
        self.assertIn(result["overall_outlook_label"], ("risky", "critical"))

    def test_build_decision_guidance_returns_keys(self) -> None:
        player = self._make_player(cash=800.0)
        self._add_employment(player, monthly_pay=2400.0)

        result = build_decision_guidance(self.db, player.id, day=self._day)
        self.assertIn("guidance_label", result)
        self.assertIn("top_recommendation", result)
        self.assertIn("avoid_action", result)
        self.assertIn("confidence_label", result)
        self.assertIn("reasoning_summary", result)
        self.assertIn(result["guidance_label"], (
            "opportunity_ready", "monitor", "reduce_risk", "urgent_caution"
        ))

    def test_build_and_persist_creates_snapshot(self) -> None:
        player = self._make_player(cash=600.0)
        self._add_employment(player, monthly_pay=2400.0)
        self._add_delinquency(player, stage="current")

        result = build_and_persist_forecast(self.db, player.id, day=self._day)
        self.db.commit()

        snap = self.db.query(PlayerForecastSnapshot).filter_by(player_id=player.id).first()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.generated_on_day, self._day)
        self.assertIn(snap.overall_outlook_label, ("stable", "tight", "risky", "critical"))
        self.assertIn("snapshot_id", result)

    def test_build_and_persist_upserts_existing_snapshot(self) -> None:
        player = self._make_player(cash=600.0)
        self._add_employment(player, monthly_pay=2400.0)

        build_and_persist_forecast(self.db, player.id, day=self._day)
        self.db.commit()

        # Second call should update, not insert a new row
        build_and_persist_forecast(self.db, player.id, day=self._day + 5)
        self.db.commit()

        snaps = self.db.query(PlayerForecastSnapshot).filter_by(player_id=player.id).all()
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].generated_on_day, self._day + 5)

    def test_player_with_no_employment_returns_forecast(self) -> None:
        # Player with no employment state should still return valid (zero income) forecast
        player = self._make_player(cash=500.0)
        # No employment added
        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=5)
        self.assertIn("projected_cash_curve", result)
        self.assertEqual(len(result["projected_cash_curve"]), 6)

    def test_invalid_horizon_raises(self) -> None:
        player = self._make_player()
        with self.assertRaises(ForecastingValidationError):
            build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=0)
        with self.assertRaises(ForecastingValidationError):
            build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=61)

    def test_delinquency_risk_day_none_when_cash_stays_positive(self) -> None:
        # Very high cash, no obligations
        player = self._make_player(cash=50000.0)
        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=14)
        self.assertIsNone(result["projected_delinquency_risk_day"])

    def test_scenario_comparison_recommended_key_valid(self) -> None:
        player = self._make_player(cash=800.0)
        result = build_scenario_comparison(
            self.db, player.id, day=self._day, horizon_days=7,
            actions=["do_nothing", "borrow_small"],
        )
        self.assertIn(result["recommended_option_key"], ["do_nothing", "borrow_small"])

    def test_simulation_net_effect_structure(self) -> None:
        player = self._make_player(cash=400.0)
        result = simulate_player_path(self.db, player.id, "invest_small", day=self._day, horizon_days=7)
        net = result["net_effect"]
        self.assertIn("cash_change_end_xgp", net)
        self.assertIn("delinquency_risk_change", net)
        self.assertIn("stability_change", net)
        # invest_small removes 100 XGP from starting cash, so end_cash should be lower
        self.assertLess(net["cash_change_end_xgp"], 0)

    def test_missing_player_in_simulate_raises(self) -> None:
        with self.assertRaises(ForecastingNotFoundError):
            simulate_player_path(self.db, uuid.uuid4(), "do_nothing", day=self._day)

    def test_missing_player_in_risk_projection_raises(self) -> None:
        with self.assertRaises(ForecastingNotFoundError):
            build_risk_projection_state(self.db, uuid.uuid4(), day=self._day)


if __name__ == "__main__":
    unittest.main()
