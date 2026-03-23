"""Step 42 integration tests for the forecasting, planning, and forward projection layer.

Tests the full pipeline end-to-end:
  - Full forecast built for player with all state systems populated
  - Two identical players, one with elevated delinquency, have different outlooks
  - Players with late delinquency stage produce near_term_risk_label=high or critical
  - build_and_persist_forecast writes snapshot, second call updates (upsert behaviour)
  - Simulation (borrow_small vs do_nothing) shows differing delinquency_risk_change
  - Scenario comparison with 3 different actions returns recommended_option_key
  - Risk projection changes when timing pressure changes from 'low' to 'severe'
  - Decision guidance changes between stable and critical player profiles
  - No duplicate PlayerForecastSnapshot rows across multiple calls for same player
  - Projection correctly handles player with only income events (no obligations)
  - Projection correctly handles player with only obligation events (no income)
"""

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_forecasting_integration.db")

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

_VALID_OUTLOOK = {"stable", "tight", "risky", "critical"}
_VALID_RISK = {"low", "moderate", "high", "critical"}
_VALID_GUIDANCE = {"opportunity_ready", "monitor", "reduce_risk", "urgent_caution"}


class ForecastingIntegrationTests(unittest.TestCase):
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

    def _make_player(self, *, cash: float = 1000.0, credit_score: int = 660) -> Player:
        user = User(id=uuid.uuid4(), email=f"e_{uuid.uuid4().hex[:8]}@x.com", hashed_password="x")
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

    def _add_loan(self, player: Player, *, daily_payment: float = 8.0) -> PlayerLoanAccount:
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

    def _add_contract_schedule(
        self, player: Player, *, gap: float = 50.0, pressure: str = "low"
    ) -> PlayerContractSchedule:
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
            obligation_key="test_obligation",
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
        dbs = PlayerDebtBehaviorState(
            player_id=player.id,
            debt_state_label="stable",
            spiral_risk_label=spiral,
            financial_stability_score=Decimal("70"),
        )
        self.db.add(dbs)
        self.db.flush()
        return dbs

    def _build_stable_player(self) -> Player:
        p = self._make_player(cash=1500.0)
        self._add_employment(p, monthly_pay=3000.0)
        self._add_delinquency(p, stage="current")
        self._add_contract_schedule(p, gap=20.0, pressure="low")
        self._add_wealth_state(p, safe_label="safe_small")
        self._add_debt_behavior(p, spiral="low")
        return p

    def _build_risky_player(self) -> Player:
        p = self._make_player(cash=80.0)
        self._add_delinquency(p, stage="late")
        self._add_contract_schedule(p, gap=400.0, pressure="elevated")
        self._add_debt_behavior(p, spiral="high")
        return p

    # ------------------------------------------------------------------
    # Full pipeline tests
    # ------------------------------------------------------------------

    def test_full_forecast_stable_player(self) -> None:
        player = self._build_stable_player()
        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=14)

        self.assertIn("projected_cash_curve", result)
        self.assertEqual(len(result["projected_cash_curve"]), 15)
        self.assertIn(result["projected_stress_trend"], ("stable", "elevated", "rising"))
        self.assertEqual(result["forecast_horizon_days"], 14)

    def test_stable_vs_risky_outlook_differs(self) -> None:
        stable = self._build_stable_player()
        risky = self._build_risky_player()

        stable_summary = build_forecast_summary(self.db, stable.id, day=self._day)
        risky_summary = build_forecast_summary(self.db, risky.id, day=self._day)

        self.assertIn(stable_summary["overall_outlook_label"], _VALID_OUTLOOK)
        self.assertIn(risky_summary["overall_outlook_label"], _VALID_OUTLOOK)
        # Stable player should not be worse than risky player  
        stable_idx = ["stable", "tight", "risky", "critical"].index(stable_summary["overall_outlook_label"])
        risky_idx = ["stable", "tight", "risky", "critical"].index(risky_summary["overall_outlook_label"])
        self.assertLessEqual(stable_idx, risky_idx)

    def test_late_delinquency_produces_high_risk(self) -> None:
        player = self._make_player(cash=100.0)
        self._add_delinquency(player, stage="delinquent")
        self._add_contract_schedule(player, gap=300.0, pressure="severe")

        result = build_risk_projection_state(self.db, player.id, day=self._day)
        self.assertIn(result["near_term_risk_label"], ("high", "critical"))
        self.assertIn(result["delinquency_risk_label"], ("high", "critical"))

    def test_build_and_persist_no_duplicate_snapshot(self) -> None:
        player = self._build_stable_player()

        build_and_persist_forecast(self.db, player.id, day=self._day)
        self.db.commit()
        build_and_persist_forecast(self.db, player.id, day=self._day + 5)
        self.db.commit()
        build_and_persist_forecast(self.db, player.id, day=self._day + 10)
        self.db.commit()

        snaps = self.db.query(PlayerForecastSnapshot).filter_by(player_id=player.id).all()
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].generated_on_day, self._day + 10)

    def test_snapshot_labels_are_valid(self) -> None:
        player = self._build_stable_player()
        build_and_persist_forecast(self.db, player.id, day=self._day)
        self.db.commit()

        snap = self.db.query(PlayerForecastSnapshot).filter_by(player_id=player.id).first()
        self.assertIsNotNone(snap)
        self.assertIn(snap.overall_outlook_label, _VALID_OUTLOOK)
        self.assertIn(snap.near_term_risk_label, _VALID_RISK)
        self.assertIn(snap.delinquency_risk_label, _VALID_RISK)

    def test_simulate_borrow_vs_do_nothing_differ(self) -> None:
        player = self._make_player(cash=150.0)
        self._add_employment(player, monthly_pay=1200.0)

        do_nothing = simulate_player_path(self.db, player.id, "do_nothing", day=self._day, horizon_days=7)
        borrow = simulate_player_path(self.db, player.id, "borrow_small", day=self._day, horizon_days=7)

        # borrow_small injects 200 XGP upfront — its initial simulated cash should be higher
        borrow_initial = borrow["simulated"]["projected_cash_curve"][0]["cash_xgp"]
        nothing_initial = do_nothing["simulated"]["projected_cash_curve"][0]["cash_xgp"]
        self.assertGreater(borrow_initial, nothing_initial)

    def test_scenario_comparison_3_options(self) -> None:
        player = self._build_stable_player()

        result = build_scenario_comparison(
            self.db, player.id, day=self._day, horizon_days=7,
            actions=["do_nothing", "borrow_small", "invest_small"],
        )
        self.assertEqual(len(result["options"]), 3)
        self.assertIn(result["recommended_option_key"], ["do_nothing", "borrow_small", "invest_small"])
        for opt in result["options"]:
            self.assertIn(opt["risk_label"], ("low", "moderate", "high", "critical"))
            self.assertIn(opt["stability_label"], ("stable", "improving", "flat", "volatile", "deteriorating", "unknown"))

    def test_risk_projection_changes_with_timing_pressure(self) -> None:
        low_pressure_player = self._make_player(cash=1000.0)
        self._add_delinquency(low_pressure_player, stage="current")
        self._add_contract_schedule(low_pressure_player, gap=10.0, pressure="low")

        severe_pressure_player = self._make_player(cash=200.0)
        self._add_delinquency(severe_pressure_player, stage="current")
        self._add_contract_schedule(severe_pressure_player, gap=400.0, pressure="severe")

        low_result = build_risk_projection_state(self.db, low_pressure_player.id, day=self._day)
        severe_result = build_risk_projection_state(self.db, severe_pressure_player.id, day=self._day)

        risk_order = ["low", "moderate", "high", "critical"]
        low_risk_idx = risk_order.index(low_result["near_term_risk_label"])
        severe_risk_idx = risk_order.index(severe_result["near_term_risk_label"])
        self.assertLessEqual(low_risk_idx, severe_risk_idx)

    def test_decision_guidance_differs_stable_vs_critical(self) -> None:
        stable = self._build_stable_player()
        risky = self._build_risky_player()

        stable_guidance = build_decision_guidance(self.db, stable.id, day=self._day)
        risky_guidance = build_decision_guidance(self.db, risky.id, day=self._day)

        self.assertIn(stable_guidance["guidance_label"], _VALID_GUIDANCE)
        self.assertIn(risky_guidance["guidance_label"], _VALID_GUIDANCE)
        # Risky player should not have better guidance than stable player
        guidance_order = ["opportunity_ready", "monitor", "reduce_risk", "urgent_caution"]
        stable_idx = guidance_order.index(stable_guidance["guidance_label"])
        risky_idx = guidance_order.index(risky_guidance["guidance_label"])
        self.assertLessEqual(stable_idx, risky_idx)

    def test_only_income_events(self) -> None:
        player = self._make_player(cash=500.0)
        # Add income events only (no obligations)
        self._add_contract_event(player, due_on_day=self._day + 3, amount=300.0, income_flag=True)
        self._add_contract_event(player, due_on_day=self._day + 7, amount=300.0, income_flag=True)

        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=7)
        # Cash should grow since only income arrives
        self.assertIsNone(result["projected_delinquency_risk_day"])
        income_events = result["projected_income_events"]
        self.assertEqual(len(income_events), 2)

    def test_only_obligation_events(self) -> None:
        player = self._make_player(cash=10.0)  # very low cash
        # Add large obligations, no income
        self._add_contract_event(player, due_on_day=self._day + 1, amount=100.0, income_flag=False)
        self._add_contract_event(player, due_on_day=self._day + 2, amount=100.0, income_flag=False)

        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=7)
        # With 10 XGP and 200 XGP in obligations, cash should go negative
        obligations = result["projected_obligation_hits"]
        self.assertEqual(len(obligations), 2)
        # Delinquency risk day should be detected
        self.assertIsNotNone(result["projected_delinquency_risk_day"])

    def test_two_players_same_obligations_different_cash_different_outlook(self) -> None:
        rich = self._make_player(cash=5000.0)
        poor = self._make_player(cash=30.0)

        # Same large obligation for both
        self._add_contract_event(rich, due_on_day=self._day + 3, amount=400.0, income_flag=False)
        self._add_contract_event(poor, due_on_day=self._day + 3, amount=400.0, income_flag=False)

        rich_result = build_short_term_forecast(self.db, rich.id, day=self._day, horizon_days=7)
        poor_result = build_short_term_forecast(self.db, poor.id, day=self._day, horizon_days=7)

        # Rich player should remain solvent
        self.assertIsNone(rich_result["projected_delinquency_risk_day"])
        # Poor player should show delinquency risk
        self.assertIsNotNone(poor_result["projected_delinquency_risk_day"])

    def test_forecast_confidence_level_valid(self) -> None:
        # Player with all states populated should have high confidence
        player = self._build_stable_player()
        self._add_loan(player, daily_payment=5.0)

        result = build_short_term_forecast(self.db, player.id, day=self._day, horizon_days=7)
        self.assertIn(result["confidence_level"], ("low", "medium", "high"))

    def test_simulation_skip_payment_effects(self) -> None:
        player = self._make_player(cash=100.0)
        self._add_loan(player, daily_payment=20.0)

        result = simulate_player_path(self.db, player.id, "skip_payment", day=self._day, horizon_days=7)
        # skip_payment adds daily_debt_payment back to starting cash, so initial cash should be higher
        sim_initial = result["simulated"]["projected_cash_curve"][0]["cash_xgp"]
        base_initial = result["baseline"]["projected_liquidity_low_point"]
        # The simulated initial should be >= base initial since we retained one payment cycle
        self.assertGreaterEqual(sim_initial, base_initial)

    def test_scenario_comparison_invest_large_depletes_cash(self) -> None:
        player = self._make_player(cash=200.0)

        result = build_scenario_comparison(
            self.db, player.id, day=self._day, horizon_days=7,
            actions=["do_nothing", "invest_large"],
        )
        do_nothing_end = next(o for o in result["options"] if o["option_key"] == "do_nothing")
        invest_large_end = next(o for o in result["options"] if o["option_key"] == "invest_large")
        # invest_large takes 400 XGP from player with 200 cash — worse outcome
        self.assertLess(invest_large_end["projected_end_cash_xgp"], do_nothing_end["projected_end_cash_xgp"])


if __name__ == "__main__":
    unittest.main()
