"""Step 39 integration tests: Wealth Progression end-to-end workflows."""

from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_wealth_progression_integration.db")

from app.db.database import Base
from app.engine.wealth_progression_service import (
    apply_wealth_growth_outcomes,
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


class WealthProgressionIntegrationTests(unittest.TestCase):
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
        cash: float = 2000.0,
        savings: float = 500.0,
        debt_xgp: float = 0.0,
        required_daily_debt: float = 0.0,
        account_created_day: int = 1,
    ) -> Player:
        user = User(email=f"i-{uuid.uuid4()}@x.com", hashed_password="x")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name="Integration Tester",
            cash=Decimal(str(cash)),
            bank_savings_xgp=Decimal(str(savings)),
            debt_xgp=Decimal(str(debt_xgp)),
            required_daily_debt_payment_xgp=Decimal(str(required_daily_debt)),
            credit_score=700,
            account_created_day=account_created_day,
        )
        self.db.add(player)
        self.db.flush()
        return player

    def _seed_state(
        self,
        player: Player,
        *,
        delin_stage: str = "current",
        spiral_label: str = "low",
        shock_risk: float = 20.0,
    ) -> None:
        self.db.add(PlayerDelinquencyState(
            player_id=player.id,
            current_delinquency_stage=delin_stage,
            missed_payment_count_30d=0,
            late_payment_count_30d=0,
            credit_pressure_score=Decimal("0"),
        ))
        self.db.add(PlayerShockState(
            player_id=player.id,
            shock_risk_score=Decimal(str(shock_risk)),
            financial_fragility_score=Decimal("20"),
            recovery_capacity_score=Decimal("60"),
        ))
        self.db.add(PlayerDebtBehaviorState(
            player_id=player.id,
            spiral_risk_label=spiral_label,
            recovery_stage="none",
            debt_dependency_score=Decimal("10"),
            payment_stack_pressure_score=Decimal("10"),
            borrowing_frequency_score=Decimal("10"),
            financial_stability_score=Decimal("80"),
        ))
        self.db.flush()

    def _seed_stock(
        self,
        player: Player,
        *,
        shares: float = 5.0,
        price: float = 100.0,
    ) -> None:
        sid = f"TECH_{uuid.uuid4().hex[:6]}"
        self.db.add(SectorStock(
            stock_id=sid,
            display_name="Test Corp",
            sector_type="tech",
            current_price=Decimal(str(price)),
            is_active=True,
        ))
        self.db.flush()
        self.db.add(PlayerStockHolding(
            player_id=player.id,
            stock_id=sid,
            shares_owned=int(shares),
            average_cost_basis=Decimal(str(price)),
            total_cost_basis=Decimal(str(shares * price)),
        ))
        self.db.flush()

    def _seed_business_with_logs(
        self,
        player: Player,
        *,
        invested: float = 600.0,
        reserve: float = 150.0,
        days: int = 10,
        daily_profit: float = 40.0,
    ) -> PlayerBusiness:
        biz = PlayerBusiness(
            player_id=player.id,
            business_id="food_stall",
            business_name="Integration Stall",
            level_key="starter",
            cash_invested_xgp=Decimal(str(invested)),
            cash_reserve_xgp=Decimal(str(reserve)),
            reputation=65,
        )
        self.db.add(biz)
        self.db.flush()
        for d in range(1, days + 1):
            self.db.add(BusinessDailyLog(
                player_id=player.id,
                business_id=biz.id,
                day=d,
                gross_revenue_xgp=Decimal(str(daily_profit + 10)),
                input_cost_xgp=Decimal("5"),
                overhead_cost_xgp=Decimal("5"),
                net_profit_xgp=Decimal(str(daily_profit)),
                units_sold=8,
                demand_score=Decimal("75"),
                utilization_pct=Decimal("80"),
                inventory_start_units=Decimal("0"),
                inventory_end_units=Decimal("0"),
                demand_signal=Decimal("0"),
            ))
        self.db.flush()
        return biz

    # ------------------------------------------------------------------
    # Integration tests
    # ------------------------------------------------------------------

    def test_full_workflow_profile_to_momentum_summary(self) -> None:
        """Full pipeline: profile → savings capacity → net worth summary → momentum summary."""
        player = self._create_player(cash=3000.0, savings=1000.0)
        self._seed_state(player)

        day = 20
        profile = build_wealth_profile(db=self.db, player_id=str(player.id), day=day)
        savings_cap = build_savings_capacity_state(db=self.db, player_id=str(player.id), day=day)
        nw_summary = build_net_worth_summary(db=self.db, player_id=str(player.id), day=day)
        momentum = build_wealth_momentum_summary(db=self.db, player_id=str(player.id), day=day)

        # All responses should be consistent
        self.assertEqual(profile["net_worth_xgp"], nw_summary["net_worth_xgp"])
        self.assertEqual(profile["safe_to_save_label"], savings_cap["safe_to_save_label"])
        self.assertEqual(profile["wealth_phase_label"], momentum["wealth_phase_label"])

    def test_stock_market_value_reflected_across_pipeline(self) -> None:
        """Stocks should add market value to both profile and asset progression."""
        player = self._create_player(cash=500.0, savings=200.0)
        self._seed_state(player)
        self._seed_stock(player, shares=10.0, price=120.0)  # 1200 XGP in stocks

        profile = build_wealth_profile(db=self.db, player_id=str(player.id), day=15)
        asset_state = build_asset_progression_state(db=self.db, player_id=str(player.id), day=15)

        self.assertAlmostEqual(profile["market_asset_value_xgp"], 1200.0, places=1)
        self.assertAlmostEqual(asset_state["market_asset_value_xgp"], 1200.0, places=1)
        # Total assets includes stocks
        self.assertGreater(profile["total_asset_value_xgp"], 1200.0)

    def test_business_equity_contribution_from_logs(self) -> None:
        """Business equity should be higher when business has profitable logs."""
        player_with_biz = self._create_player(cash=400.0)
        self._seed_state(player_with_biz)
        self._seed_business_with_logs(player_with_biz, invested=500.0, reserve=100.0, days=10, daily_profit=50.0)

        player_without = self._create_player(cash=400.0)
        self._seed_state(player_without)

        r_with = build_wealth_profile(db=self.db, player_id=str(player_with_biz.id), day=15)
        r_without = build_wealth_profile(db=self.db, player_id=str(player_without.id), day=15)

        self.assertGreater(r_with["business_equity_xgp"], r_without["business_equity_xgp"])

    def test_false_growth_integration_with_debt_behavior(self) -> None:
        """False-growth detection should fire when debt behavior + borrowing creates illusion."""
        player = self._create_player(cash=1000.0)
        self._seed_state(player, spiral_label="high")
        # Repeat borrowing state
        self.db.add(PlayerBorrowingState(
            player_id=player.id,
            repeat_borrowing_count_30d=4,
            active_loan_count=2,
            dependence_risk_score=Decimal("60"),
            borrowing_access_score=Decimal("50"),
            credit_access_tier="risky",
        ))
        self.db.flush()

        result = build_net_worth_summary(db=self.db, player_id=str(player.id), day=20)
        self.assertTrue(result["false_growth_detected"])

    def test_apply_wealth_outcomes_does_not_mutate_state(self) -> None:
        """apply_wealth_growth_outcomes must not change any persisted player data."""
        player = self._create_player(cash=2000.0, savings=300.0)
        self._seed_state(player)

        cash_before = player.cash
        savings_before = player.bank_savings_xgp

        apply_wealth_growth_outcomes(
            db=self.db,
            player_id=str(player.id),
            action_key="pay_debt",
            day=15,
            amount_xgp=500.0,
        )

        # Reload from db
        self.db.expire(player)
        self.db.refresh(player)
        self.assertEqual(player.cash, cash_before)
        self.assertEqual(player.bank_savings_xgp, savings_before)

    def test_wealth_phase_stable_player_not_fragile(self) -> None:
        """A healthy player with good buffer should not be in fragile phase."""
        player = self._create_player(cash=5000.0, savings=2000.0)
        self._seed_state(player, delin_stage="current", spiral_label="low", shock_risk=10.0)

        result = build_wealth_profile(db=self.db, player_id=str(player.id), day=20)
        self.assertNotEqual(result["wealth_phase_label"], "fragile")

    def test_wealth_momentum_direction_in_summary(self) -> None:
        """Momentum direction should be one of the expected labels."""
        player = self._create_player(cash=2000.0)
        self._seed_state(player)

        result = build_wealth_momentum_summary(db=self.db, player_id=str(player.id), day=10)
        self.assertIn(result["momentum_direction"], ("accelerating", "steady", "decelerating"))

    def test_diversity_label_with_all_asset_types(self) -> None:
        """Player with cash + stocks + business should have moderate or diversified label."""
        player = self._create_player(cash=500.0, savings=300.0)
        self._seed_state(player)
        self._seed_stock(player, shares=5.0, price=100.0)
        self._seed_business_with_logs(player, invested=300.0, reserve=100.0, days=5)

        result = build_asset_progression_state(db=self.db, player_id=str(player.id), day=10)
        self.assertIn(result["diversification_label"], ("moderate", "diversified"))

    def test_action_evaluation_reasonable_pay_debt_with_loans(self) -> None:
        """Pay-debt action should be reasonable when active loans and spiral risk exist."""
        player = self._create_player(cash=2000.0, required_daily_debt=30.0)
        self._seed_state(player, spiral_label="rising")
        # Add an active loan
        self.db.add(PlayerLoanAccount(
            player_id=player.id,
            offer_key="test_loan",
            offer_family="installment",
            status="active",
            principal_original_xgp=Decimal("1000"),
            principal_outstanding_xgp=Decimal("800"),
            scheduled_daily_payment_xgp=Decimal("30"),
            apr_pct=Decimal("20"),
            term_days=30,
            delinquency_stage="current",
            accepted_on_day=1,
        ))
        self.db.flush()

        result = evaluate_wealth_actions(db=self.db, player_id=str(player.id), day=15)
        pay_debt_eval = next(
            (e for e in result["evaluations"] if e["action_key"] == "pay_debt"), None
        )
        self.assertIsNotNone(pay_debt_eval)
        self.assertIn(pay_debt_eval["evaluation_label"], ("reasonable", "cautious"))

    def test_wealth_state_rolling_upsert(self) -> None:
        """Multiple build_wealth_profile calls on different days should upsert state correctly."""
        player = self._create_player(cash=1800.0)
        self._seed_state(player)

        build_wealth_profile(db=self.db, player_id=str(player.id), day=10)
        build_wealth_profile(db=self.db, player_id=str(player.id), day=11)

        state_count = (
            self.db.query(PlayerWealthState)
            .filter(PlayerWealthState.player_id == player.id)
            .count()
        )
        # Rolling state — only one row per player
        self.assertEqual(state_count, 1)

        state = (
            self.db.query(PlayerWealthState)
            .filter(PlayerWealthState.player_id == player.id)
            .first()
        )
        # Should reflect day 11 (most recent update)
        self.assertEqual(state.last_updated_on, 11)


if __name__ == "__main__":
    unittest.main()
