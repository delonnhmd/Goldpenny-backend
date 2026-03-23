import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_consumer_borrowing_service.db")

from app.db.database import Base
from app.engine.consumer_borrowing_service import (
    ConsumerBorrowingValidationError,
    apply_borrowing_decision,
    build_borrowing_eligibility_profile,
    build_borrowing_pressure_summary,
    build_borrowing_risk_summary,
    build_emergency_liquidity_state,
    generate_borrowing_options,
)
from app.engine.financial_survival_service import (
    apply_daily_financial_survival,
    build_player_obligation_profile,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState
from app.models.user import User


PRICING_ORDER = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}
PAYMENT_OUTCOME_ORDER = {"missed": 0, "delayed": 1, "paid_partial": 2, "paid_full": 3}


class ConsumerBorrowingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                FinancialDistressLog.__table__,
                PlayerShockState.__table__,
                PlayerDelinquencyState.__table__,
                PlayerPaymentHistory.__table__,
                PlayerBorrowingState.__table__,
                PlayerLoanAccount.__table__,
                PlayerBorrowingHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self.strong_player = self._seed_player(
            name="Strong",
            region="suburban",
            cash=Decimal("2900.00"),
            debt=Decimal("260.00"),
            credit_score=742,
            stress=24,
            health=93,
            monthly_pay=Decimal("4700.00"),
            housing_monthly=Decimal("620.00"),
            utilities_monthly=Decimal("90.00"),
            transport_monthly=Decimal("120.00"),
            shock_risk=Decimal("20.0"),
            with_business=False,
            business_overhead=Decimal("0.00"),
        )
        self.distressed_player = self._seed_player(
            name="Distressed",
            region="downtown",
            cash=Decimal("75.00"),
            debt=Decimal("3850.00"),
            credit_score=565,
            stress=84,
            health=62,
            monthly_pay=Decimal("1650.00"),
            housing_monthly=Decimal("1180.00"),
            utilities_monthly=Decimal("170.00"),
            transport_monthly=Decimal("210.00"),
            shock_risk=Decimal("86.0"),
            with_business=True,
            business_overhead=Decimal("34.00"),
        )
        self.bridge_player = self._seed_player(
            name="Bridge",
            region="downtown",
            cash=Decimal("95.00"),
            debt=Decimal("1240.00"),
            credit_score=702,
            stress=48,
            health=82,
            monthly_pay=Decimal("3200.00"),
            housing_monthly=Decimal("920.00"),
            utilities_monthly=Decimal("132.00"),
            transport_monthly=Decimal("162.00"),
            shock_risk=Decimal("38.0"),
            with_business=True,
            business_overhead=Decimal("16.00"),
        )
        self.no_bridge_player = self._seed_player(
            name="NoBridge",
            region="downtown",
            cash=Decimal("65.00"),
            debt=Decimal("1320.00"),
            credit_score=698,
            stress=50,
            health=80,
            monthly_pay=Decimal("3050.00"),
            housing_monthly=Decimal("940.00"),
            utilities_monthly=Decimal("136.00"),
            transport_monthly=Decimal("168.00"),
            shock_risk=Decimal("42.0"),
            with_business=False,
            business_overhead=Decimal("0.00"),
        )
        self.with_bridge_player = self._seed_player(
            name="WithBridge",
            region="downtown",
            cash=Decimal("65.00"),
            debt=Decimal("1320.00"),
            credit_score=698,
            stress=50,
            health=80,
            monthly_pay=Decimal("3050.00"),
            housing_monthly=Decimal("940.00"),
            utilities_monthly=Decimal("136.00"),
            transport_monthly=Decimal("168.00"),
            shock_risk=Decimal("42.0"),
            with_business=False,
            business_overhead=Decimal("0.00"),
        )
        self.business_heavy_player = self._seed_player(
            name="BizHeavy",
            region="downtown",
            cash=Decimal("120.00"),
            debt=Decimal("1950.00"),
            credit_score=635,
            stress=72,
            health=70,
            monthly_pay=Decimal("2100.00"),
            housing_monthly=Decimal("1020.00"),
            utilities_monthly=Decimal("150.00"),
            transport_monthly=Decimal("190.00"),
            shock_risk=Decimal("61.0"),
            with_business=True,
            business_overhead=Decimal("30.00"),
        )
        self.business_light_player = self._seed_player(
            name="BizLight",
            region="downtown",
            cash=Decimal("120.00"),
            debt=Decimal("1950.00"),
            credit_score=635,
            stress=72,
            health=70,
            monthly_pay=Decimal("2100.00"),
            housing_monthly=Decimal("1020.00"),
            utilities_monthly=Decimal("150.00"),
            transport_monthly=Decimal("190.00"),
            shock_risk=Decimal("61.0"),
            with_business=False,
            business_overhead=Decimal("0.00"),
        )
        self.stack_limit_player = self._seed_player(
            name="Stacked",
            region="downtown",
            cash=Decimal("150.00"),
            debt=Decimal("2200.00"),
            credit_score=620,
            stress=74,
            health=69,
            monthly_pay=Decimal("2050.00"),
            housing_monthly=Decimal("1010.00"),
            utilities_monthly=Decimal("148.00"),
            transport_monthly=Decimal("188.00"),
            shock_risk=Decimal("63.0"),
            with_business=False,
            business_overhead=Decimal("0.00"),
        )

        self._seed_payment_history(self.strong_player.id, outcomes=["paid_full", "paid_full", "paid_full"])
        self._seed_payment_history(self.distressed_player.id, outcomes=["missed", "paid_partial", "delayed"])
        self._seed_delinquency(self.distressed_player.id, stage="late", missed=3, late=4)
        self._seed_delinquency(self.bridge_player.id, stage="stretched", missed=1, late=1)
        self._seed_three_active_loans(self.stack_limit_player.id)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_player(
        self,
        *,
        name: str,
        region: str,
        cash: Decimal,
        debt: Decimal,
        credit_score: int,
        stress: int,
        health: int,
        monthly_pay: Decimal,
        housing_monthly: Decimal,
        utilities_monthly: Decimal,
        transport_monthly: Decimal,
        shock_risk: Decimal,
        with_business: bool,
        business_overhead: Decimal,
    ) -> Player:
        user = User(email=f"step37-{name.lower()}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=f"Step37 {name}",
            cash=cash,
            debt_xgp=debt,
            credit_score=credit_score,
            stress=stress,
            health=health,
            region=region,
            main_job="delivery_driver" if region == "downtown" else "banker",
            required_daily_debt_payment_xgp=Decimal("24.00"),
        )
        self.db.add(player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=player.id,
                region=region,
                housing_type="rent",
                monthly_housing_cost_xgp=housing_monthly,
                monthly_utilities_cost_xgp=utilities_monthly,
                monthly_transport_base_xgp=transport_monthly,
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=player.id,
                day=1,
                current_job_code="delivery_driver" if region == "downtown" else "banker",
                skill_level=1,
                monthly_pay_xgp=monthly_pay,
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("8.0"),
                productivity_modifier=Decimal("1.0000"),
            )
        )
        self.db.add(
            PlayerShockState(
                player_id=player.id,
                shock_risk_score=shock_risk,
                financial_fragility_score=Decimal("72.0") if shock_risk >= 60 else Decimal("28.0"),
                health_fragility_score=Decimal("68.0") if shock_risk >= 60 else Decimal("26.0"),
                work_disruption_risk_score=Decimal("57.0") if shock_risk >= 60 else Decimal("24.0"),
                recovery_capacity_score=Decimal("36.0") if shock_risk >= 60 else Decimal("78.0"),
                recent_negative_streak=2 if shock_risk >= 60 else 0,
                recent_recovery_support=0 if shock_risk >= 60 else 2,
                recent_pressure_direction="rising" if shock_risk >= 60 else "stable",
                last_updated_on=1,
                last_updated_date=date(2026, 1, 1),
            )
        )
        self.db.add(
            FinancialDistressLog(
                player_id=player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                debt_payment_due_xgp=Decimal("24.00"),
                debt_payment_paid_xgp=Decimal("24.00"),
                debt_payment_missed=False,
                late_fee_xgp=Decimal("0.00"),
                accrued_interest_xgp=Decimal("1.20"),
                credit_score_before=credit_score,
                credit_score_after=credit_score,
                credit_score_delta=0,
                distress_state_before="stretched" if stress >= 65 else "stable",
                distress_state_after="stretched" if stress >= 65 else "stable",
                distress_score_before=Decimal("58.0") if stress >= 65 else Decimal("18.0"),
                distress_score_after=Decimal("58.0") if stress >= 65 else Decimal("18.0"),
            )
        )

        if with_business:
            business = PlayerBusiness(
                player_id=player.id,
                business_id="food_truck",
                business_type="food_truck",
                region=region,
                is_active=True,
                active_flag=True,
                tier=1,
                operating_mode="standard_menu",
            )
            self.db.add(business)
            self.db.flush()
            self.db.add(
                BusinessDailyLog(
                    business_id=business.id,
                    player_id=player.id,
                    day=1,
                    as_of_date=date(2026, 1, 1),
                    business_type="food_truck",
                    region_key=region,
                    gross_revenue_xgp=Decimal("76.00"),
                    input_cost_xgp=Decimal("54.00"),
                    fuel_cost_xgp=Decimal("8.00"),
                    overhead_cost_xgp=business_overhead,
                    net_profit_xgp=Decimal("-5.00"),
                    units_sold=18,
                    inventory_start_units=Decimal("40"),
                    inventory_end_units=Decimal("18"),
                    demand_signal=Decimal("0.74"),
                    demand_score=Decimal("0.74"),
                    utilization_pct=Decimal("0.56"),
                )
            )
        return player

    def _seed_payment_history(self, player_id: uuid.UUID, outcomes: list[str]) -> None:
        for idx, outcome in enumerate(outcomes, start=1):
            self.db.add(
                PlayerPaymentHistory(
                    player_id=player_id,
                    day_number=idx,
                    as_of_date=date(2026, 1, idx),
                    payment_outcome=outcome,
                    required_daily_burden_xgp=Decimal("40.00"),
                    obligation_load_ratio=Decimal("1.10") if outcome != "paid_full" else Decimal("0.75"),
                    liquidity_buffer_days=Decimal("1.80") if outcome != "paid_full" else Decimal("6.00"),
                    total_due_xgp=Decimal("40.00"),
                    total_paid_xgp=Decimal("40.00") if outcome == "paid_full" else Decimal("18.00"),
                    unpaid_amount_xgp=Decimal("0.00") if outcome == "paid_full" else Decimal("22.00"),
                    late_fee_xgp=Decimal("0.00") if outcome == "paid_full" else Decimal("3.00"),
                    credit_score_before=650,
                    credit_score_after=649 if outcome != "paid_full" else 650,
                    credit_score_delta=-1 if outcome != "paid_full" else 0,
                    delinquency_stage_before="stretched",
                    delinquency_stage_after="late" if outcome == "missed" else "stretched",
                    survival_status_label="stretched",
                    payment_pressure_label="high" if outcome != "paid_full" else "manageable",
                    full_pay_feasible=outcome == "paid_full",
                    partial_pay_feasible=True,
                    stress_impact_delta=Decimal("0.6") if outcome != "paid_full" else Decimal("0.0"),
                    due_obligations_json="[]",
                    practical_actions_json="[]",
                    summary_json="{}",
                    debug_json="{}",
                )
            )

    def _seed_delinquency(self, player_id: uuid.UUID, *, stage: str, missed: int, late: int) -> None:
        self.db.add(
            PlayerDelinquencyState(
                player_id=player_id,
                current_delinquency_stage=stage,
                missed_payment_count_30d=missed,
                late_payment_count_30d=late,
                days_under_payment_stress=max(missed, late),
                last_missed_obligation_type="housing" if missed > 0 else None,
                credit_pressure_score=Decimal("66.0") if stage in {"late", "delinquent", "critical"} else Decimal("28.0"),
                financial_distress_score=Decimal("68.0") if stage in {"late", "delinquent", "critical"} else Decimal("32.0"),
                last_updated_on=1,
                last_updated_date=date(2026, 1, 1),
                stage_debug_json="{}",
            )
        )

    def _seed_three_active_loans(self, player_id: uuid.UUID) -> None:
        for idx in range(1, 4):
            self.db.add(
                PlayerLoanAccount(
                    player_id=player_id,
                    offer_key=f"seed_offer_{idx}",
                    offer_family="riskier_survival",
                    status="active",
                    principal_original_xgp=Decimal("300.00"),
                    principal_outstanding_xgp=Decimal("240.00"),
                    apr_pct=Decimal("48.0"),
                    fee_amount_xgp=Decimal("24.00"),
                    term_days=30,
                    days_elapsed=idx,
                    days_remaining=max(0, 30 - idx),
                    scheduled_daily_payment_xgp=Decimal("11.50"),
                    current_due_xgp=Decimal("11.50"),
                    missed_payment_count=0,
                    delinquency_stage="current",
                    rollover_allowed=True,
                    accepted_on_day=idx,
                    accepted_on_date=date(2026, 1, idx),
                )
            )

    def test_strong_profile_gets_better_access_than_distressed_profile(self) -> None:
        strong_profile = build_borrowing_eligibility_profile(
            self.db, str(self.strong_player.id), day_number=4
        )
        distressed_profile = build_borrowing_eligibility_profile(
            self.db, str(self.distressed_player.id), day_number=4
        )

        self.assertGreater(
            Decimal(str(strong_profile["borrowing_access_score"])),
            Decimal(str(distressed_profile["borrowing_access_score"])),
        )
        self.assertLessEqual(
            PRICING_ORDER.get(str(strong_profile["estimated_risk_pricing_band"]), 9),
            PRICING_ORDER.get(str(distressed_profile["estimated_risk_pricing_band"]), 9),
        )

        strong_options = generate_borrowing_options(
            self.db, str(self.strong_player.id), day_number=4, include_locked=False
        )
        distressed_options = generate_borrowing_options(
            self.db, str(self.distressed_player.id), day_number=4, include_locked=True
        )
        self.assertGreater(len(strong_options["items"]), 0)
        self.assertGreater(len(distressed_options["items"]), 0)

    def test_delinquency_stage_worsens_access_and_pricing(self) -> None:
        baseline = build_borrowing_eligibility_profile(self.db, str(self.bridge_player.id), day_number=2)
        for day in range(2, 7):
            self.db.add(
                PlayerPaymentHistory(
                    player_id=self.bridge_player.id,
                    day_number=day,
                    as_of_date=date(2026, 1, day),
                    payment_outcome="missed",
                    required_daily_burden_xgp=Decimal("52.00"),
                    obligation_load_ratio=Decimal("1.45"),
                    liquidity_buffer_days=Decimal("1.20"),
                    total_due_xgp=Decimal("52.00"),
                    total_paid_xgp=Decimal("0.00"),
                    unpaid_amount_xgp=Decimal("52.00"),
                    late_fee_xgp=Decimal("5.00"),
                    credit_score_before=700 - day,
                    credit_score_after=697 - day,
                    credit_score_delta=-3,
                    delinquency_stage_before="stretched",
                    delinquency_stage_after="late",
                    survival_status_label="slipping",
                    payment_pressure_label="high",
                    full_pay_feasible=False,
                    partial_pay_feasible=False,
                    stress_impact_delta=Decimal("1.20"),
                    due_obligations_json="[]",
                    practical_actions_json="[]",
                    summary_json="{}",
                    debug_json="{}",
                )
            )
        self.db.flush()

        worsened = build_borrowing_eligibility_profile(self.db, str(self.bridge_player.id), day_number=6)
        self.assertGreater(
            Decimal(str(baseline["borrowing_access_score"])),
            Decimal(str(worsened["borrowing_access_score"])),
        )
        self.assertLessEqual(
            PRICING_ORDER.get(str(baseline["estimated_risk_pricing_band"]), 9),
            PRICING_ORDER.get(str(worsened["estimated_risk_pricing_band"]), 9),
        )

    def test_accepting_offer_increases_cash_now_and_obligation_burden_later(self) -> None:
        obligation_before = build_player_obligation_profile(self.db, str(self.bridge_player.id), day_number=2)
        cash_before = Decimal(str(self.bridge_player.cash_xgp))
        debt_before = Decimal(str(self.bridge_player.debt_xgp))

        options = generate_borrowing_options(
            self.db, str(self.bridge_player.id), day_number=2, include_locked=False
        )
        self.assertGreater(len(options["items"]), 0)
        selected = options["items"][0]
        decision = apply_borrowing_decision(
            db=self.db,
            player_id=str(self.bridge_player.id),
            offer_key=str(selected["offer_key"]),
            principal_requested_xgp=Decimal("140.00"),
            day_number=2,
        )
        self.db.flush()
        self.db.refresh(self.bridge_player)

        obligation_after = build_player_obligation_profile(self.db, str(self.bridge_player.id), day_number=2)
        self.assertTrue(decision["accepted"])
        self.assertGreater(Decimal(str(self.bridge_player.cash_xgp)), cash_before)
        self.assertGreater(Decimal(str(self.bridge_player.debt_xgp)), debt_before)
        self.assertGreater(
            Decimal(str(obligation_after["loan_obligation_xgp"])),
            Decimal(str(obligation_before["loan_obligation_xgp"])),
        )

    def test_small_bridge_can_reduce_immediate_payment_failure_risk(self) -> None:
        no_bridge_result = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.no_bridge_player.id),
            day_number=2,
            available_cash_xgp=Decimal("0.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )

        options = generate_borrowing_options(
            self.db, str(self.with_bridge_player.id), day_number=2, include_locked=False
        )
        self.assertGreater(len(options["items"]), 0)
        apply_borrowing_decision(
            db=self.db,
            player_id=str(self.with_bridge_player.id),
            offer_key=str(options["items"][0]["offer_key"]),
            principal_requested_xgp=Decimal("85.00"),
            day_number=2,
        )
        with_bridge_result = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.with_bridge_player.id),
            day_number=2,
        )

        self.assertGreaterEqual(
            PAYMENT_OUTCOME_ORDER.get(str(with_bridge_result["payment_outcome"]), 0),
            PAYMENT_OUTCOME_ORDER.get(str(no_bridge_result["payment_outcome"]), 0),
        )
        self.assertGreaterEqual(
            Decimal(str(with_bridge_result["total_paid_xgp"])),
            Decimal(str(no_bridge_result["total_paid_xgp"])),
        )

    def test_repeated_borrowing_dependence_reduces_future_access(self) -> None:
        baseline = build_borrowing_eligibility_profile(self.db, str(self.bridge_player.id), day_number=2)

        for day in range(2, 5):
            options = generate_borrowing_options(
                self.db, str(self.bridge_player.id), day_number=day, include_locked=False
            )
            if not options["items"]:
                break
            apply_borrowing_decision(
                db=self.db,
                player_id=str(self.bridge_player.id),
                offer_key=str(options["items"][0]["offer_key"]),
                principal_requested_xgp=Decimal("90.00"),
                day_number=day,
            )
            self.db.flush()

        later = build_borrowing_eligibility_profile(self.db, str(self.bridge_player.id), day_number=5)
        self.assertGreaterEqual(int(later["repeat_borrowing_count_30d"]), 1)
        self.assertGreater(
            Decimal(str(later["dependence_risk_score"])),
            Decimal(str(baseline["dependence_risk_score"])),
        )
        self.assertLessEqual(
            Decimal(str(later["borrowing_access_score"])),
            Decimal(str(baseline["borrowing_access_score"])),
        )

    def test_infinite_loan_stacking_is_blocked(self) -> None:
        options = generate_borrowing_options(
            self.db, str(self.stack_limit_player.id), day_number=4, include_locked=True
        )
        self.assertGreater(len(options["items"]), 0)
        with self.assertRaises(ConsumerBorrowingValidationError):
            apply_borrowing_decision(
                db=self.db,
                player_id=str(self.stack_limit_player.id),
                offer_key=str(options["items"][0]["offer_key"]),
                day_number=4,
            )

    def test_business_overhead_can_create_real_bridge_need(self) -> None:
        heavy_liquidity = build_emergency_liquidity_state(
            self.db, str(self.business_heavy_player.id), day_number=2
        )
        light_liquidity = build_emergency_liquidity_state(
            self.db, str(self.business_light_player.id), day_number=2
        )
        heavy_profile = build_player_obligation_profile(
            self.db, str(self.business_heavy_player.id), day_number=2
        )
        light_profile = build_player_obligation_profile(
            self.db, str(self.business_light_player.id), day_number=2
        )
        self.assertGreater(
            Decimal(str(heavy_profile["business_overhead_obligation_xgp"])),
            Decimal(str(light_profile["business_overhead_obligation_xgp"])),
        )
        self.assertGreaterEqual(
            Decimal(str(heavy_liquidity["liquidity_gap_xgp"])),
            Decimal(str(light_liquidity["liquidity_gap_xgp"])),
        )

    def test_trap_warning_and_future_locked_guidance_are_visible(self) -> None:
        risk = build_borrowing_risk_summary(
            self.db, str(self.distressed_player.id), day_number=4
        )
        pressure = build_borrowing_pressure_summary(
            self.db, str(self.distressed_player.id), day_number=4
        )
        self.assertIn(
            str(risk["risk_label"]),
            {"locked", "trap_like", "dangerous", "risky_but_manageable", "stabilizing_if_disciplined"},
        )
        self.assertTrue(str(pressure["worst_trap_warning"]).strip())
        self.assertTrue(pressure["practical_current_actions"])
        self.assertTrue(
            any("locked" in str(item).lower() for item in pressure["future_locked_options"])
        )


if __name__ == "__main__":
    unittest.main()
