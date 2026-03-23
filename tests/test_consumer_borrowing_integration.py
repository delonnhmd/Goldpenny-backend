import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_consumer_borrowing_integration.db")

from app.db.database import Base
from app.engine.consumer_borrowing_service import (
    build_borrowing_pressure_summary,
    build_borrowing_risk_summary,
)
from app.engine.strategic_planning_service import build_player_strategy_recommendation
from app.engine.world_memory_service import detect_recurring_patterns
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_shock_state import PlayerShockState
from app.models.region_population_state import RegionPopulationState
from app.models.user import User


class ConsumerBorrowingIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                PlayerEmploymentState.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                DailySettlementLog.__table__,
                PlayerDailyState.__table__,
                CareerProgressLog.__table__,
                FinancialDistressLog.__table__,
                PlayerDelinquencyState.__table__,
                PlayerPaymentHistory.__table__,
                PlayerBorrowingState.__table__,
                PlayerLoanAccount.__table__,
                PlayerBorrowingHistory.__table__,
                PlayerShockState.__table__,
                PlayerRecoveryState.__table__,
                PlayerLifeEventHistory.__table__,
                RegionPopulationState.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step37-integration-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step37 Integration",
            cash=Decimal("62.00"),
            debt_xgp=Decimal("3250.00"),
            credit_score=582,
            stress=82,
            health=64,
            region="downtown",
            main_job="delivery_driver",
            required_daily_debt_payment_xgp=Decimal("36.00"),
            productivity_modifier=Decimal("0.86"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("1180.00"),
                monthly_utilities_cost_xgp=Decimal("168.00"),
                monthly_transport_base_xgp=Decimal("212.00"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="delivery_driver",
                skill_level=1,
                monthly_pay_xgp=Decimal("1760.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("10.5"),
                productivity_modifier=Decimal("0.90"),
            )
        )
        self.db.add(
            PlayerShockState(
                player_id=self.player.id,
                shock_risk_score=Decimal("81.0"),
                financial_fragility_score=Decimal("74.0"),
                health_fragility_score=Decimal("68.0"),
                work_disruption_risk_score=Decimal("61.0"),
                recovery_capacity_score=Decimal("31.0"),
                recent_negative_streak=3,
                recent_recovery_support=0,
                recent_pressure_direction="rising",
                last_updated_on=5,
                last_updated_date=date(2026, 1, 5),
            )
        )
        self.db.add(
            PlayerRecoveryState(
                player_id=self.player.id,
                recovery_days_remaining=2,
                temporary_stress_modifier=Decimal("0.20"),
                temporary_health_modifier=Decimal("-0.08"),
                temporary_income_modifier=Decimal("-0.12"),
                temporary_business_modifier=Decimal("-0.08"),
                temporary_time_modifier=Decimal("0.35"),
                recovery_status_label="active_recovery",
                source_event_key="minor_illness",
                source_event_severity="moderate",
                last_applied_day=5,
                next_expire_day=7,
                last_updated_on=5,
                last_updated_date=date(2026, 1, 5),
            )
        )
        self.db.add(
            PlayerDelinquencyState(
                player_id=self.player.id,
                current_delinquency_stage="late",
                missed_payment_count_30d=4,
                late_payment_count_30d=6,
                days_under_payment_stress=6,
                last_missed_obligation_type="housing",
                credit_pressure_score=Decimal("72.0"),
                financial_distress_score=Decimal("76.0"),
                last_updated_on=5,
                last_updated_date=date(2026, 1, 5),
                stage_debug_json="{}",
            )
        )
        self.db.add(
            RegionPopulationState(
                region_key="downtown",
                memory_window_start_day=1,
                memory_window_end_day=5,
                memory_window_start=date(2026, 1, 1),
                memory_window_end=date(2026, 1, 5),
                active_population_score=Decimal("88.0"),
                opportunity_density_score=Decimal("82.0"),
                congestion_score=Decimal("86.0"),
                housing_pressure_score=Decimal("84.0"),
                business_competition_score=Decimal("79.0"),
                consumer_flow_score=Decimal("83.0"),
                recent_growth_direction="rising",
                state_debug_json="{}",
                last_updated_on=5,
                last_updated_date=date(2026, 1, 5),
            )
        )

        business = PlayerBusiness(
            player_id=self.player.id,
            business_id="food_truck",
            business_type="food_truck",
            region="downtown",
            is_active=True,
            active_flag=True,
            tier=1,
            operating_mode="premium_menu",
        )
        self.db.add(business)
        self.db.flush()

        for day in range(1, 6):
            as_of = date(2026, 1, day)
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.80"),
                    interest_rate=Decimal("4.20"),
                    unemployment_rate=Decimal("5.40"),
                    oil_index=Decimal("116.0") + Decimal(str(day)),
                    consumer_confidence=Decimal("46.0"),
                    supply_chain_stress=Decimal("1.12"),
                    event_headline=f"Step37 pressure {day}",
                    event_summary="Persistent pressure sequence.",
                )
            )
            for basket_type in (
                BasketType.essentials,
                BasketType.protein,
                BasketType.produce,
                BasketType.convenience,
            ):
                self.db.add(
                    BasketDailyPrice(
                        day=day,
                        basket_type=basket_type,
                        price_index=Decimal("10.9") + Decimal(str(day)) * Decimal("0.18"),
                        daily_change_pct=Decimal("0.72"),
                        supply_pressure=Decimal("1.06"),
                        demand_pressure=Decimal("1.02"),
                    )
                )
            self.db.add(
                HousingDailyLog(
                    player_id=self.player.id,
                    day=day,
                    as_of_date=as_of,
                    region="downtown",
                    housing_cost_xgp=Decimal("39.33"),
                    utilities_cost_xgp=Decimal("5.60"),
                    commute_hours=Decimal("1.55") + Decimal(str(day)) * Decimal("0.08"),
                    commute_fuel_cost_xgp=Decimal("5.60"),
                    commute_pressure=Decimal("1.28") + Decimal(str(day)) * Decimal("0.04"),
                    stress_delta=2,
                    opportunity_modifier=Decimal("1.08"),
                    region_stress_delta=Decimal("0.98"),
                    region_opportunity_modifier=Decimal("0.09"),
                    region_business_demand_modifier=Decimal("0.10"),
                    region_side_income_modifier=Decimal("0.08"),
                    networking_modifier=Decimal("0.11"),
                    opportunity_quality_signal=Decimal("1.10"),
                )
            )
            self.db.add(
                BusinessDailyLog(
                    business_id=business.id,
                    player_id=self.player.id,
                    day=day,
                    as_of_date=as_of,
                    business_type="food_truck",
                    region_key="downtown",
                    gross_revenue_xgp=Decimal("80.00"),
                    input_cost_xgp=Decimal("61.00"),
                    fuel_cost_xgp=Decimal("10.20"),
                    overhead_cost_xgp=Decimal("17.00"),
                    net_profit_xgp=Decimal("-8.20"),
                    units_sold=20,
                    inventory_start_units=Decimal("40"),
                    inventory_end_units=Decimal("12"),
                    demand_signal=Decimal("0.80"),
                    demand_score=Decimal("0.80"),
                    utilization_pct=Decimal("0.64"),
                )
            )
            self.db.add(
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=day,
                    hours_before_reset=6,
                    hours_after_reset=24,
                    stress_before=79 + day,
                    stress_after=81 + day,
                    health_before=67 - day,
                    health_after=66 - day,
                    cash_before=Decimal("120.00") - Decimal(str(day)) * Decimal("10.00"),
                    cash_after=Decimal("105.00") - Decimal(str(day)) * Decimal("9.00"),
                    income_xgp=Decimal("158.00"),
                    expenses_xgp=Decimal("214.00"),
                    debt_paid_xgp=Decimal("16.00"),
                    stress_change=2,
                    health_change=-1,
                )
            )
            self.db.add(
                PlayerDailyState(
                    player_id=self.player.id,
                    day_number=day,
                    overtime_hours=Decimal("2.2"),
                    commute_hours=Decimal("1.55") + Decimal(str(day)) * Decimal("0.08"),
                    sleep_hours=Decimal("5.5"),
                    recovery_hours=Decimal("0.8"),
                    productivity_modifier=Decimal("0.86"),
                )
            )
            self.db.add(
                FinancialDistressLog(
                    player_id=self.player.id,
                    day=day,
                    as_of_date=as_of,
                    debt_payment_due_xgp=Decimal("36.00"),
                    debt_payment_paid_xgp=Decimal("20.00"),
                    debt_payment_missed=False,
                    late_fee_xgp=Decimal("1.20"),
                    accrued_interest_xgp=Decimal("2.20"),
                    credit_score_before=590 - day,
                    credit_score_after=588 - day,
                    credit_score_delta=-2,
                    distress_state_before="late",
                    distress_state_after="late",
                    distress_score_before=Decimal("71.0"),
                    distress_score_after=Decimal("73.0"),
                )
            )
            self.db.add(
                PlayerPaymentHistory(
                    player_id=self.player.id,
                    day_number=day,
                    as_of_date=as_of,
                    payment_outcome="missed" if day in {3, 4} else "paid_partial",
                    required_daily_burden_xgp=Decimal("56.00"),
                    obligation_load_ratio=Decimal("1.45"),
                    liquidity_buffer_days=Decimal("1.20"),
                    total_due_xgp=Decimal("56.00"),
                    total_paid_xgp=Decimal("24.00"),
                    unpaid_amount_xgp=Decimal("32.00"),
                    late_fee_xgp=Decimal("4.20"),
                    credit_score_before=590 - day,
                    credit_score_after=588 - day,
                    credit_score_delta=-2,
                    delinquency_stage_before="late",
                    delinquency_stage_after="late",
                    survival_status_label="slipping",
                    payment_pressure_label="high",
                    full_pay_feasible=False,
                    partial_pay_feasible=True,
                    stress_impact_delta=Decimal("0.9"),
                    due_obligations_json="[]",
                    practical_actions_json="[]",
                    summary_json="{}",
                    debug_json="{}",
                )
            )
            if day >= 2:
                self.db.add(
                    PlayerBorrowingHistory(
                        player_id=self.player.id,
                        day_number=day,
                        as_of_date=as_of,
                        event_type="offer_accepted",
                        offer_key=f"high_cost_bridge_{day}",
                        offer_family="riskier_survival",
                        principal_xgp=Decimal("120.00"),
                        fee_xgp=Decimal("18.00"),
                        apr_pct=Decimal("68.0"),
                        term_days=20,
                        estimated_total_cost_xgp=Decimal("42.00"),
                        cash_delta_xgp=Decimal("102.00"),
                        debt_delta_xgp=Decimal("138.00"),
                        obligation_delta_xgp=Decimal("8.10"),
                        status_after="active",
                        summary_json='{"risk_label": "very_high"}',
                        debug_json="{}",
                    )
                )
            self.db.add(
                PlayerLifeEventHistory(
                    player_id=self.player.id,
                    day_number=day,
                    as_of_date=as_of,
                    event_key=f"stress_spike_{day}",
                    event_family="health_stress_shock",
                    headline="Stress spike day",
                    severity_band="moderate",
                    cash_impact_xgp=Decimal("-8.0"),
                    stress_impact_delta=Decimal("2.0"),
                    health_impact_delta=Decimal("-1.0"),
                    time_impact_hours=Decimal("0.5"),
                    work_income_impact=Decimal("-0.03"),
                    business_impact=Decimal("-0.02"),
                    side_income_impact=Decimal("-0.02"),
                    duration_days=2,
                    recovery_hint="Rest and avoid overwork.",
                    trigger_tags_json="[]",
                    impact_json="{}",
                    debug_json="{}",
                )
            )

    def test_world_memory_detects_borrowing_dependence_pattern(self) -> None:
        patterns = detect_recurring_patterns(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
        )
        keys = {str(item["pattern_key"]) for item in patterns["items"]}
        self.assertIn("life_emergency_borrowing_dependence", keys)

    def test_strategic_planning_surfaces_borrowing_trap_warning(self) -> None:
        recommendation = build_player_strategy_recommendation(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
        )
        avoid_warning = str(recommendation.get("avoid_warning", "")).lower()
        debug_meta = recommendation.get("debug_meta", {})
        self.assertIn("borrowing_risk_label", debug_meta)
        self.assertIn("borrowing_liquidity_pressure", debug_meta)
        if str(debug_meta.get("borrowing_risk_label", "")).lower() in {"dangerous", "trap_like"}:
            self.assertIn("borrowing", avoid_warning)
        else:
            self.assertTrue(bool(avoid_warning.strip()))

    def test_pressure_summary_keeps_locked_future_options_non_actionable(self) -> None:
        pressure = build_borrowing_pressure_summary(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
        )
        risk = build_borrowing_risk_summary(
            db=self.db,
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
        )
        self.assertTrue(any("locked" in str(item).lower() for item in pressure["future_locked_options"]))
        self.assertIn(str(risk["risk_label"]), {"locked", "trap_like", "dangerous", "risky_but_manageable", "stabilizing_if_disciplined"})
        self.assertTrue(str(pressure["worst_trap_warning"]).strip())


if __name__ == "__main__":
    unittest.main()
