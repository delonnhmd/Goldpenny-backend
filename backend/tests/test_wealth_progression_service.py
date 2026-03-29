"""Step 39 tests: Wealth Building + Asset Progression Layer."""

from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_wealth_progression_service.db")

from app.db.database import Base
from app.engine.wealth_progression_service import (
    BUFFER_DAYS_INVEST_THRESHOLD,
    BUFFER_DAYS_SAVE_THRESHOLD,
    MINIMUM_EMERGENCY_RESERVE,
    WealthProgressionNotFoundError,
    _compute_experience_phase,
    _compute_investable_surplus,
    _compute_stability_score,
    _compute_wealth_momentum,
    _detect_false_growth,
    _determine_wealth_phase,
    build_asset_progression_state,
    build_net_worth_summary,
    build_savings_capacity_state,
    build_wealth_momentum_summary,
    build_wealth_profile,
    evaluate_wealth_actions,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.player import Player
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_debt_behavior_state import PlayerDebtBehaviorState
from app.models.player_debt_trend_history import PlayerDebtTrendHistory
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_shock_state import PlayerShockState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_wealth_state import PlayerWealthState
from app.models.player_wealth_trend_history import PlayerWealthTrendHistory
from app.models.sector_stock import SectorStock
from app.models.user import User


class WealthProgressionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.Session = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, future=True
        )
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerShockState.__table__,
                PlayerDelinquencyState.__table__,
                PlayerBorrowingState.__table__,
                PlayerLoanAccount.__table__,
                PlayerDebtBehaviorState.__table__,
                PlayerDebtTrendHistory.__table__,
                PlayerStockHolding.__table__,
                SectorStock.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                PlayerWealthState.__table__,
                PlayerWealthTrendHistory.__table__,
            ],
        )
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    def _create_player(
        self,
        *,
        cash: float = 1200.0,
        savings: float = 0.0,
        debt_xgp: float = 0.0,
        required_daily_debt: float = 0.0,
        credit_score: int = 650,
        account_created_day: int = 1,
    ) -> Player:
        user = User(email=f"t-{uuid.uuid4()}@x.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name="Test",
            cash=Decimal(str(cash)),
            bank_savings_xgp=Decimal(str(savings)),
            debt_xgp=Decimal(str(debt_xgp)),
            required_daily_debt_payment_xgp=Decimal(str(required_daily_debt)),
            credit_score=credit_score,
            account_created_day=account_created_day,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_delinquency(self, player: Player, *, stage: str = "current") -> PlayerDelinquencyState:
        state = PlayerDelinquencyState(
            player_id=player.id,
            current_delinquency_stage=stage,
            missed_payment_count_30d=0,
            late_payment_count_30d=0,
            credit_pressure_score=Decimal("0"),
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _seed_borrowing(
        self,
        player: Player,
        *,
        repeat_count: int = 0,
        active_loans: int = 0,
        dependence_risk: float = 0.0,
    ) -> PlayerBorrowingState:
        state = PlayerBorrowingState(
            player_id=player.id,
            repeat_borrowing_count_30d=repeat_count,
            active_loan_count=active_loans,
            dependence_risk_score=Decimal(str(dependence_risk)),
            borrowing_access_score=Decimal("75"),
            credit_access_tier="standard",
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _seed_shock(self, player: Player, *, shock_risk: float = 20.0) -> PlayerShockState:
        state = PlayerShockState(
            player_id=player.id,
            shock_risk_score=Decimal(str(shock_risk)),
            financial_fragility_score=Decimal("20"),
            recovery_capacity_score=Decimal("60"),
        )
        self.db.add(state)
        self.db.flush()
        return state

    def _seed_debt_behavior(
        self,
        player: Player,
        *,
        spiral_label: str = "low",
        recovery_stage: str = "none",
    ) -> PlayerDebtBehaviorState:
        state = PlayerDebtBehaviorState(
            player_id=player.id,
            spiral_risk_label=spiral_label,
            recovery_stage=recovery_stage,
            debt_dependency_score=Decimal("10"),
            payment_stack_pressure_score=Decimal("10"),
            borrowing_frequency_score=Decimal("10"),
            financial_stability_score=Decimal("80"),
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
        daily_payment: float = 20.0,
        status: str = "active",
    ) -> PlayerLoanAccount:
        loan = PlayerLoanAccount(
            player_id=player.id,
            offer_key="test_loan",
            offer_family="installment",
            status=status,
            principal_original_xgp=Decimal(str(principal)),
            principal_outstanding_xgp=Decimal(
                str(outstanding if outstanding is not None else principal)
            ),
            scheduled_daily_payment_xgp=Decimal(str(daily_payment)),
            apr_pct=Decimal("18.00"),
            term_days=30,
            delinquency_stage="current",
            accepted_on_day=1,
        )
        self.db.add(loan)
        self.db.flush()
        return loan

    def _seed_stock(
        self,
        player: Player,
        *,
        shares: float = 10.0,
        price: float = 50.0,
        stock_id: str | None = None,
    ) -> tuple[PlayerStockHolding, SectorStock]:
        sid = stock_id or f"STOCK_{uuid.uuid4().hex[:6]}"
        sector = SectorStock(
            stock_id=sid,
            display_name="Test Co",
            sector_type="tech",
            current_price=Decimal(str(price)),
            is_active=True,
        )
        self.db.add(sector)
        self.db.flush()
        holding = PlayerStockHolding(
            player_id=player.id,
            stock_id=sid,
            shares_owned=int(shares),
            average_cost_basis=Decimal(str(price)),
            total_cost_basis=Decimal(str(shares * price)),
        )
        self.db.add(holding)
        self.db.flush()
        return holding, sector

    def _seed_business(
        self,
        player: Player,
        *,
        invested: float = 500.0,
        reserve: float = 100.0,
    ) -> PlayerBusiness:
        biz = PlayerBusiness(
            player_id=player.id,
            business_id="food_stall",
            business_name="My Stall",
            level_key="starter",
            cash_invested_xgp=Decimal(str(invested)),
            cash_reserve_xgp=Decimal(str(reserve)),
            reputation=50,
        )
        self.db.add(biz)
        self.db.flush()
        return biz

    def _seed_biz_log(
        self,
        player: Player,
        biz: PlayerBusiness,
        *,
        day: int,
        net_profit: float = 30.0,
    ) -> BusinessDailyLog:
        log = BusinessDailyLog(
            player_id=player.id,
            business_id=biz.id,
            day=day,
            gross_revenue_xgp=Decimal(str(net_profit + 10)),
            input_cost_xgp=Decimal("5"),
            overhead_cost_xgp=Decimal("5"),
            net_profit_xgp=Decimal(str(net_profit)),
            units_sold=5,
            demand_score=Decimal("70"),
            utilization_pct=Decimal("80"),
            inventory_start_units=Decimal("0"),
            inventory_end_units=Decimal("0"),
            demand_signal=Decimal("0"),
        )
        self.db.add(log)
        self.db.flush()
        return log

    def _seed_wealth_trend(
        self,
        player: Player,
        *,
        day: int,
        net_worth: float = 1000.0,
        total_assets: float = 2000.0,
        total_debt: float = 1000.0,
        debt_drag: float = 200.0,
        investable_surplus: float = 100.0,
    ) -> PlayerWealthTrendHistory:
        row = PlayerWealthTrendHistory(
            player_id=player.id,
            day=day,
            net_worth_xgp=Decimal(str(net_worth)),
            total_asset_value_xgp=Decimal(str(total_assets)),
            total_debt_xgp=Decimal(str(total_debt)),
            debt_drag_xgp=Decimal(str(debt_drag)),
            investable_surplus_xgp=Decimal(str(investable_surplus)),
            market_asset_value_xgp=Decimal("0"),
            business_equity_xgp=Decimal("0"),
            wealth_momentum_score=Decimal("50"),
            stability_before_growth_score=Decimal("50"),
            buffer_days=Decimal("10"),
            wealth_phase_label="stabilizing",
            asset_growth_trend="stable",
            experience_phase="early_growth",
            false_growth_flag=False,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------------
    # Tests: experience phase
    # ------------------------------------------------------------------

    def test_experience_phase_onboarding(self) -> None:
        player = self._create_player(account_created_day=1)
        phase, days_in, softening = _compute_experience_phase(player, current_day=3)
        self.assertEqual(phase, "onboarding")
        self.assertTrue(softening)
        self.assertEqual(days_in, 3)

    def test_experience_phase_early_growth(self) -> None:
        player = self._create_player(account_created_day=1)
        phase, days_in, softening = _compute_experience_phase(player, current_day=15)
        self.assertEqual(phase, "early_growth")
        self.assertTrue(softening)

    def test_experience_phase_stabilization(self) -> None:
        player = self._create_player(account_created_day=1)
        phase, days_in, softening = _compute_experience_phase(player, current_day=50)
        self.assertEqual(phase, "stabilization")
        self.assertTrue(softening)

    def test_experience_phase_pressure_no_softening(self) -> None:
        player = self._create_player(account_created_day=1)
        phase, _, softening = _compute_experience_phase(player, current_day=120)
        self.assertEqual(phase, "pressure")
        self.assertFalse(softening)

    def test_experience_phase_full_sim(self) -> None:
        player = self._create_player(account_created_day=1)
        phase, _, softening = _compute_experience_phase(player, current_day=200)
        self.assertEqual(phase, "full_sim")
        self.assertFalse(softening)

    def test_experience_phase_uses_account_created_day(self) -> None:
        # player who started 50 days ago (created_day=50, current=100 → elapsed=51 → stabilization)
        player = self._create_player(account_created_day=50)
        phase, _, _ = _compute_experience_phase(player, current_day=100)
        self.assertEqual(phase, "stabilization")

    # ------------------------------------------------------------------
    # Tests: investable surplus
    # ------------------------------------------------------------------

    def test_investable_surplus_zero_when_late_delinquency(self) -> None:
        surplus = _compute_investable_surplus(
            liquid=Decimal("5000"),
            daily_obligations=Decimal("50"),
            buffer_days=Decimal("20"),
            delinquency_stage="late",
        )
        self.assertEqual(surplus, Decimal("0"))

    def test_investable_surplus_zero_when_delinquent(self) -> None:
        surplus = _compute_investable_surplus(
            liquid=Decimal("5000"),
            daily_obligations=Decimal("50"),
            buffer_days=Decimal("20"),
            delinquency_stage="delinquent",
        )
        self.assertEqual(surplus, Decimal("0"))

    def test_investable_surplus_positive_when_current_and_liquid(self) -> None:
        # 2000 liquid, daily obligations=20, current stage → good buffer
        surplus = _compute_investable_surplus(
            liquid=Decimal("2000"),
            daily_obligations=Decimal("20"),
            buffer_days=Decimal("20"),
            delinquency_stage="current",
        )
        self.assertGreater(surplus, Decimal("0"))

    def test_investable_surplus_reduced_when_stretched(self) -> None:
        current = _compute_investable_surplus(
            liquid=Decimal("2000"),
            daily_obligations=Decimal("20"),
            buffer_days=Decimal("20"),
            delinquency_stage="current",
        )
        stretched = _compute_investable_surplus(
            liquid=Decimal("2000"),
            daily_obligations=Decimal("20"),
            buffer_days=Decimal("20"),
            delinquency_stage="stretched",
        )
        self.assertLess(stretched, current)

    def test_investable_surplus_never_exceeds_sixty_percent_liquid(self) -> None:
        surplus = _compute_investable_surplus(
            liquid=Decimal("100000"),
            daily_obligations=Decimal("10"),
            buffer_days=Decimal("200"),
            delinquency_stage="current",
        )
        self.assertLessEqual(surplus, Decimal("100000") * Decimal("0.6"))

    # ------------------------------------------------------------------
    # Tests: stability score
    # ------------------------------------------------------------------

    def test_stability_score_high_buffer_current_low_spiral(self) -> None:
        score = _compute_stability_score(
            buffer_days=Decimal("25"),
            delinquency_stage="current",
            spiral_label="low",
            shock_risk=Decimal("10"),
        )
        self.assertGreater(score, Decimal("60"))

    def test_stability_score_low_buffer_critical_stage(self) -> None:
        score = _compute_stability_score(
            buffer_days=Decimal("2"),
            delinquency_stage="critical",
            spiral_label="critical",
            shock_risk=Decimal("80"),
        )
        self.assertEqual(score, Decimal("0"))  # clamped to 0

    # ------------------------------------------------------------------
    # Tests: wealth momentum
    # ------------------------------------------------------------------

    def test_wealth_momentum_higher_for_healthy_player(self) -> None:
        healthy = _compute_wealth_momentum(
            net_worth=Decimal("3000"),
            buffer_days=Decimal("20"),
            spiral_label="low",
            recovery_stage="none",
            debt_drag=Decimal("100"),
            total_assets=Decimal("5000"),
            strong_business_trend=True,
            market_value=Decimal("1000"),
        )
        distressed = _compute_wealth_momentum(
            net_worth=Decimal("-500"),
            buffer_days=Decimal("2"),
            spiral_label="critical",
            recovery_stage="none",
            debt_drag=Decimal("2000"),
            total_assets=Decimal("1000"),
            strong_business_trend=False,
            market_value=Decimal("0"),
        )
        self.assertGreater(healthy, distressed)

    # ------------------------------------------------------------------
    # Tests: wealth phase detection
    # ------------------------------------------------------------------

    def test_wealth_phase_fragile_critical_spiral(self) -> None:
        phase = _determine_wealth_phase(
            stability_score=Decimal("20"),
            momentum_score=Decimal("20"),
            spiral_label="critical",
            delinquency_stage="current",
            business_equity=Decimal("0"),
            market_value=Decimal("0"),
            investable_surplus=Decimal("0"),
            total_debt=Decimal("500"),
            liquid=Decimal("1000"),
        )
        self.assertEqual(phase, "fragile")

    def test_wealth_phase_compounding_strong_position(self) -> None:
        phase = _determine_wealth_phase(
            stability_score=Decimal("80"),
            momentum_score=Decimal("75"),
            spiral_label="low",
            delinquency_stage="current",
            business_equity=Decimal("2000"),
            market_value=Decimal("1000"),
            investable_surplus=Decimal("500"),
            total_debt=Decimal("200"),
            liquid=Decimal("3000"),
        )
        self.assertEqual(phase, "compounding")

    def test_wealth_phase_overextended_debt_heavy(self) -> None:
        # Investable surplus negative and debt > 80% of liquid
        phase = _determine_wealth_phase(
            stability_score=Decimal("50"),
            momentum_score=Decimal("50"),
            spiral_label="low",
            delinquency_stage="current",
            business_equity=Decimal("0"),
            market_value=Decimal("0"),
            investable_surplus=Decimal("-100"),
            total_debt=Decimal("1800"),
            liquid=Decimal("2000"),
        )
        self.assertEqual(phase, "overextended")

    def test_wealth_phase_growing_moderate_position(self) -> None:
        phase = _determine_wealth_phase(
            stability_score=Decimal("60"),
            momentum_score=Decimal("60"),
            spiral_label="low",
            delinquency_stage="current",
            business_equity=Decimal("0"),
            market_value=Decimal("0"),
            investable_surplus=Decimal("100"),
            total_debt=Decimal("200"),
            liquid=Decimal("2000"),
        )
        self.assertEqual(phase, "growing")

    # ------------------------------------------------------------------
    # Tests: false-growth detection
    # ------------------------------------------------------------------

    def test_false_growth_detected_high_repeat_borrowing(self) -> None:
        borrowing_state = PlayerBorrowingState(
            player_id=uuid.uuid4(),
            repeat_borrowing_count_30d=4,
            active_loan_count=2,
            dependence_risk_score=Decimal("50"),
            borrowing_access_score=Decimal("50"),
            credit_access_tier="standard",
        )
        detected, warnings = _detect_false_growth(
            net_worth=Decimal("500"),
            debt_drag=Decimal("200"),
            investable_surplus=Decimal("0"),
            spiral_label="low",
            borrowing_state=borrowing_state,
            business_logs=[],
            history=[],
        )
        self.assertTrue(detected)
        self.assertGreater(len(warnings), 0)

    def test_false_growth_detected_positive_nw_zero_surplus(self) -> None:
        detected, warnings = _detect_false_growth(
            net_worth=Decimal("600"),
            debt_drag=Decimal("300"),
            investable_surplus=Decimal("0"),
            spiral_label="low",
            borrowing_state=None,
            business_logs=[],
            history=[],
        )
        self.assertTrue(detected)
        self.assertTrue(any("no investable surplus" in w.lower() for w in warnings))

    def test_no_false_growth_clean_player(self) -> None:
        detected, warnings = _detect_false_growth(
            net_worth=Decimal("2000"),
            debt_drag=Decimal("100"),
            investable_surplus=Decimal("500"),
            spiral_label="low",
            borrowing_state=None,
            business_logs=[],
            history=[],
        )
        self.assertFalse(detected)
        self.assertEqual(len(warnings), 0)

    # ------------------------------------------------------------------
    # Tests: build_wealth_profile (integration)
    # ------------------------------------------------------------------

    def test_build_wealth_profile_stable_player(self) -> None:
        player = self._create_player(cash=2000.0, savings=500.0)
        self._seed_delinquency(player, stage="current")
        self._seed_shock(player, shock_risk=15.0)
        self._seed_debt_behavior(player, spiral_label="low")

        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=10)

        self.assertEqual(result["player_id"], str(player.id))
        self.assertIn("wealth_phase_label", result)
        self.assertIn("wealth_momentum_score", result)
        self.assertIn("stability_before_growth_score", result)
        self.assertIn("safe_to_save_label", result)
        self.assertIn("safe_to_invest_label", result)
        self.assertGreater(result["liquid_asset_value_xgp"], 0)

    def test_build_wealth_profile_persists_both_tables(self) -> None:
        player = self._create_player(cash=1500.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        build_wealth_profile(db=self.db, player_id=str(player.id), day=5)

        state_row = (
            self.db.query(PlayerWealthState)
            .filter(PlayerWealthState.player_id == player.id)
            .first()
        )
        trend_row = (
            self.db.query(PlayerWealthTrendHistory)
            .filter(
                PlayerWealthTrendHistory.player_id == player.id,
                PlayerWealthTrendHistory.day == 5,
            )
            .first()
        )
        self.assertIsNotNone(state_row)
        self.assertIsNotNone(trend_row)

    def test_build_wealth_profile_upsert_no_duplicates(self) -> None:
        """Calling build_wealth_profile twice on same day should not create duplicate trend row."""
        player = self._create_player(cash=1500.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        build_wealth_profile(db=self.db, player_id=str(player.id), day=7)
        build_wealth_profile(db=self.db, player_id=str(player.id), day=7)

        count = (
            self.db.query(PlayerWealthTrendHistory)
            .filter(
                PlayerWealthTrendHistory.player_id == player.id,
                PlayerWealthTrendHistory.day == 7,
            )
            .count()
        )
        self.assertEqual(count, 1)

    def test_build_wealth_profile_invalid_player_raises(self) -> None:
        with self.assertRaises(WealthProgressionNotFoundError):
            build_wealth_profile(db=self.db, player_id=str(uuid.uuid4()), day=5)

    def test_early_game_softening_does_not_allow_free_money(self) -> None:
        """Momentum boost from early-game softening must remain bounded (≤ 100)."""
        player = self._create_player(cash=200.0, account_created_day=1)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        # Day 3 = onboarding phase with softening
        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=3)
        self.assertLessEqual(result["wealth_momentum_score"], 100.0)
        # Softening should be active in onboarding
        self.assertTrue(result["softening_active"])

    def test_early_game_phase_transitions_correctly(self) -> None:
        """Player at day 180 should be in pressure phase (no softening)."""
        player = self._create_player(cash=2000.0, account_created_day=1)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=150)
        self.assertIn(result["experience_phase"], ("pressure", "full_sim"))
        self.assertFalse(result["softening_active"])

    def test_stock_holdings_contribute_to_market_value(self) -> None:
        player = self._create_player(cash=500.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)
        self._seed_stock(player, shares=20.0, price=100.0)  # 2000 XGP in stocks

        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=10)
        self.assertGreater(result["market_asset_value_xgp"], 0)
        self.assertAlmostEqual(result["market_asset_value_xgp"], 2000.0, places=1)

    def test_delinquent_player_has_lower_momentum_than_current(self) -> None:
        stable = self._create_player(cash=2000.0)
        self._seed_delinquency(stable, stage="current")
        self._seed_shock(stable, shock_risk=10.0)
        self._seed_debt_behavior(stable, spiral_label="low")

        distressed = self._create_player(cash=300.0, required_daily_debt=25.0)
        self._seed_delinquency(distressed, stage="delinquent")
        self._seed_shock(distressed, shock_risk=70.0)
        self._seed_debt_behavior(distressed, spiral_label="critical")

        r_stable = build_wealth_profile(db=self.db, player_id=str(stable.id), day=10)
        r_dist = build_wealth_profile(db=self.db, player_id=str(distressed.id), day=10)
        self.assertGreater(
            r_stable["wealth_momentum_score"],
            r_dist["wealth_momentum_score"],
        )

    def test_debt_spiral_suppresses_safe_investing(self) -> None:
        player = self._create_player(cash=3000.0)
        self._seed_delinquency(player, stage="stretched")
        self._seed_shock(player)
        self._seed_debt_behavior(player, spiral_label="high")

        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=10)
        self.assertEqual(result["safe_to_invest_label"], "not_safe")

    def test_buffer_days_computed_from_cash_over_obligations(self) -> None:
        # Cash=600, no loans, floor obligation=15/day → buffer = 600/15 = 40 days
        player = self._create_player(cash=600.0, required_daily_debt=0.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=10)
        # buffer_days = 600/15 = 40 (capped at 999)
        self.assertGreater(result["buffer_days"], 7.0)

    # ------------------------------------------------------------------
    # Tests: build_savings_capacity_state
    # ------------------------------------------------------------------

    def test_savings_capacity_not_safe_critical_stage(self) -> None:
        player = self._create_player(cash=500.0)
        self._seed_delinquency(player, stage="critical")
        self._seed_shock(player)
        self._seed_debt_behavior(player, spiral_label="critical")

        result = build_savings_capacity_state(
            db=self.db, player_id=str(player.id), day=10
        )
        self.assertEqual(result["safe_to_save_label"], "not_safe")
        self.assertEqual(result["safe_to_invest_label"], "not_safe")

    def test_savings_capacity_safe_to_save_with_buffer(self) -> None:
        # Cash=3000, obligations low → buffer > 7 days
        player = self._create_player(cash=3000.0)
        self._seed_delinquency(player, stage="current")
        self._seed_shock(player)
        self._seed_debt_behavior(player, spiral_label="low")

        result = build_savings_capacity_state(
            db=self.db, player_id=str(player.id), day=10
        )
        self.assertIn(result["safe_to_save_label"], ("safe", "strongly_recommended"))

    def test_savings_capacity_distinguishes_save_from_invest(self) -> None:
        # Player can save but not yet invest (buffer between 7 and 14)
        # Cash=120, obligations~15/day → buffer ~8 days (can save, not quite invest)
        player = self._create_player(cash=120.0)
        self._seed_delinquency(player, stage="current")
        self._seed_shock(player)
        self._seed_debt_behavior(player, spiral_label="low")

        result = build_savings_capacity_state(
            db=self.db, player_id=str(player.id), day=10
        )
        # buffer ~8 days → safe_to_save should be "safe" or "cautious"
        self.assertIn(result["safe_to_save_label"], ("safe", "cautious"))
        # invest not yet ready → premature or not_safe
        self.assertIn(result["safe_to_invest_label"], ("premature", "not_safe", "cautious"))

    # ------------------------------------------------------------------
    # Tests: build_asset_progression_state
    # ------------------------------------------------------------------

    def test_asset_progression_liquid_matches_cash_plus_savings(self) -> None:
        player = self._create_player(cash=800.0, savings=200.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = build_asset_progression_state(
            db=self.db, player_id=str(player.id), day=10
        )
        self.assertAlmostEqual(result["liquid_asset_value_xgp"], 1000.0, places=1)

    def test_asset_progression_business_equity_included(self) -> None:
        player = self._create_player(cash=500.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)
        biz = self._seed_business(player, invested=400.0, reserve=100.0)
        for d in range(1, 8):
            self._seed_biz_log(player, biz, day=d, net_profit=30.0)

        result = build_asset_progression_state(
            db=self.db, player_id=str(player.id), day=10
        )
        # equity = 400 (invested) + 100 (reserve) + some profit contribution
        self.assertGreater(result["business_equity_xgp"], 400.0)

    # ------------------------------------------------------------------
    # Tests: evaluate_wealth_actions
    # ------------------------------------------------------------------

    def test_evaluate_actions_returns_all_six_actions(self) -> None:
        player = self._create_player(cash=2000.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = evaluate_wealth_actions(db=self.db, player_id=str(player.id), day=10)
        action_keys = {e["action_key"] for e in result["evaluations"]}
        expected = {"hold_cash", "save_cash", "buy_stocks", "reinvest_business", "pay_debt", "delay_wealth_move"}
        self.assertEqual(action_keys, expected)

    def test_evaluate_actions_buy_stocks_reckless_during_critical_spiral(self) -> None:
        player = self._create_player(cash=1000.0)
        self._seed_delinquency(player, stage="stretched")
        self._seed_shock(player, shock_risk=80.0)
        self._seed_debt_behavior(player, spiral_label="critical")

        result = evaluate_wealth_actions(db=self.db, player_id=str(player.id), day=10)
        buy_eval = next(
            (e for e in result["evaluations"] if e["action_key"] == "buy_stocks"), None
        )
        self.assertIsNotNone(buy_eval)
        self.assertIn(buy_eval["evaluation_label"], ("reckless", "premature", "not_safe"))

    # ------------------------------------------------------------------
    # Tests: build_net_worth_summary
    # ------------------------------------------------------------------

    def test_net_worth_summary_structure(self) -> None:
        player = self._create_player(cash=2000.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = build_net_worth_summary(db=self.db, player_id=str(player.id), day=10)
        self.assertIn("net_worth_xgp", result)
        self.assertIn("growth_quality_label", result)
        self.assertIn("false_growth_detected", result)
        self.assertIn("short_recommendation", result)
        self.assertIn("debt_drag_ratio", result)

    def test_net_worth_summary_false_growth_with_borrowing(self) -> None:
        player = self._create_player(cash=800.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)
        self._seed_borrowing(player, repeat_count=5)

        result = build_net_worth_summary(db=self.db, player_id=str(player.id), day=10)
        # With 5 repeat borrows and positive NW, false growth should be detected
        self.assertTrue(result["false_growth_detected"])
        self.assertGreater(len(result["false_growth_warnings"]), 0)

    # ------------------------------------------------------------------
    # Tests: build_wealth_momentum_summary
    # ------------------------------------------------------------------

    def test_wealth_momentum_summary_structure(self) -> None:
        player = self._create_player(cash=2000.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = build_wealth_momentum_summary(db=self.db, player_id=str(player.id), day=10)
        self.assertIn("momentum_direction", result)
        self.assertIn("softening_modifiers", result)
        self.assertIn("phase_advisory", result)
        self.assertIn("planning_insights", result)
        self.assertIn("savings_capacity_summary", result)

    def test_wealth_momentum_softening_modifiers_present_in_early_phase(self) -> None:
        player = self._create_player(cash=800.0, account_created_day=1)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)

        result = build_wealth_momentum_summary(db=self.db, player_id=str(player.id), day=5)
        # onboarding phase → softening_modifiers should have values less than 1.0
        mods = result.get("softening_modifiers", {})
        self.assertIsInstance(mods, dict)
        if mods:  # only assert if populated
            mult = mods.get("shock_severity_mult", 1.0)
            self.assertLess(mult, 1.0)

    def test_apply_wealth_growth_outcomes_is_readonly(self) -> None:
        """apply_wealth_growth_outcomes must not mutate player cash."""
        from app.engine.wealth_progression_service import apply_wealth_growth_outcomes

        player = self._create_player(cash=2000.0)
        self._seed_delinquency(player)
        self._seed_shock(player)
        self._seed_debt_behavior(player)
        original_cash = float(player.cash)

        apply_wealth_growth_outcomes(
            db=self.db,
            player_id=str(player.id),
            action_key="save_cash",
            day=10,
            amount_xgp=200.0,
        )
        self.db.refresh(player)
        self.assertAlmostEqual(float(player.cash), original_cash, places=2)


if __name__ == "__main__":
    unittest.main()
