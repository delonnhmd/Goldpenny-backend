import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_financial_survival_service.db")

from app.db.database import Base
from app.engine.financial_survival_service import (
    apply_daily_financial_survival,
    build_financial_survival_summary,
    build_player_obligation_profile,
    build_delinquency_state,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState
from app.models.user import User


PAYMENT_PRESSURE_ORDER = {
    "manageable": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
}


class FinancialSurvivalServiceTests(unittest.TestCase):
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
            ],
        )
        self.db = self.SessionLocal()
        self.fragile = self._seed_player(
            name="Fragile",
            region="downtown",
            cash=Decimal("140.00"),
            debt=Decimal("3200.00"),
            credit_score=630,
            stress=79,
            health=66,
            monthly_pay=Decimal("1700.00"),
            housing_monthly=Decimal("1180.00"),
            utilities_monthly=Decimal("170.00"),
            transport_monthly=Decimal("220.00"),
            with_business=True,
            business_overhead=Decimal("32.00"),
            shock_risk=Decimal("84.00"),
        )
        self.stable = self._seed_player(
            name="Stable",
            region="suburban",
            cash=Decimal("2800.00"),
            debt=Decimal("280.00"),
            credit_score=690,
            stress=30,
            health=92,
            monthly_pay=Decimal("4300.00"),
            housing_monthly=Decimal("590.00"),
            utilities_monthly=Decimal("95.00"),
            transport_monthly=Decimal("130.00"),
            with_business=False,
            business_overhead=Decimal("0.00"),
            shock_risk=Decimal("22.00"),
        )
        self.low_shock = self._seed_player(
            name="LowShock",
            region="downtown",
            cash=Decimal("120.00"),
            debt=Decimal("3100.00"),
            credit_score=635,
            stress=74,
            health=71,
            monthly_pay=Decimal("1700.00"),
            housing_monthly=Decimal("1120.00"),
            utilities_monthly=Decimal("165.00"),
            transport_monthly=Decimal("210.00"),
            with_business=False,
            business_overhead=Decimal("0.00"),
            shock_risk=Decimal("12.00"),
        )
        self.high_shock = self._seed_player(
            name="HighShock",
            region="downtown",
            cash=Decimal("120.00"),
            debt=Decimal("3100.00"),
            credit_score=635,
            stress=74,
            health=71,
            monthly_pay=Decimal("1700.00"),
            housing_monthly=Decimal("1120.00"),
            utilities_monthly=Decimal("165.00"),
            transport_monthly=Decimal("210.00"),
            with_business=False,
            business_overhead=Decimal("0.00"),
            shock_risk=Decimal("92.00"),
        )
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
        with_business: bool,
        business_overhead: Decimal,
        shock_risk: Decimal,
    ) -> Player:
        user = User(email=f"step36-{name.lower()}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name=f"Step36 {name}",
            cash=cash,
            debt_xgp=debt,
            credit_score=credit_score,
            stress=stress,
            health=health,
            region=region,
            main_job="retail_worker",
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
                current_job_code="retail_worker",
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
                financial_fragility_score=Decimal("72.0") if shock_risk > 50 else Decimal("28.0"),
                health_fragility_score=Decimal("66.0") if shock_risk > 50 else Decimal("24.0"),
                work_disruption_risk_score=Decimal("58.0") if shock_risk > 50 else Decimal("22.0"),
                recovery_capacity_score=Decimal("34.0") if shock_risk > 50 else Decimal("76.0"),
                recent_negative_streak=2 if shock_risk > 50 else 0,
                recent_recovery_support=0 if shock_risk > 50 else 2,
                recent_pressure_direction="rising" if shock_risk > 50 else "falling",
                last_updated_on=1,
                last_updated_date=date(2026, 1, 1),
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
                    gross_revenue_xgp=Decimal("75.00"),
                    input_cost_xgp=Decimal("53.00"),
                    fuel_cost_xgp=Decimal("8.00"),
                    overhead_cost_xgp=business_overhead,
                    net_profit_xgp=Decimal("-6.00"),
                    units_sold=18,
                    inventory_start_units=Decimal("40"),
                    inventory_end_units=Decimal("18"),
                    demand_signal=Decimal("0.72"),
                    demand_score=Decimal("0.72"),
                    utilization_pct=Decimal("0.58"),
                )
            )

        return player

    def test_low_liquidity_raises_payment_stress(self) -> None:
        fragile_profile = build_player_obligation_profile(self.db, str(self.fragile.id), day_number=1)
        stable_profile = build_player_obligation_profile(self.db, str(self.stable.id), day_number=1)

        self.assertGreater(
            Decimal(str(fragile_profile["obligation_load_ratio"])),
            Decimal(str(stable_profile["obligation_load_ratio"])),
        )
        self.assertLess(
            Decimal(str(fragile_profile["liquidity_buffer_days"])),
            Decimal(str(stable_profile["liquidity_buffer_days"])),
        )
        self.assertGreaterEqual(
            PAYMENT_PRESSURE_ORDER.get(str(fragile_profile["payment_pressure_label"]), 0),
            PAYMENT_PRESSURE_ORDER.get(str(stable_profile["payment_pressure_label"]), 0),
        )

    def test_business_overhead_worsens_survival_pressure(self) -> None:
        fragile_profile = build_player_obligation_profile(self.db, str(self.fragile.id), day_number=1)
        low_shock_profile = build_player_obligation_profile(self.db, str(self.low_shock.id), day_number=1)

        self.assertGreater(
            Decimal(str(fragile_profile["business_overhead_obligation_xgp"])),
            Decimal(str(low_shock_profile["business_overhead_obligation_xgp"])),
        )
        self.assertGreater(
            Decimal(str(fragile_profile["required_daily_burden_xgp"])),
            Decimal(str(low_shock_profile["required_daily_burden_xgp"])),
        )

    def test_one_late_payment_hurts_but_is_survivable(self) -> None:
        result = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.fragile.id),
            day_number=1,
            available_cash_xgp=Decimal("42.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )

        self.assertIn(result["payment_outcome"], {"paid_partial", "delayed", "missed"})
        self.assertLess(int(result["credit_score_after"]), int(result["credit_score_before"]))
        self.assertIn(result["survival_status_label"], {"current", "stretched", "slipping", "delinquent", "critical"})
        self.assertNotEqual(result["survival_status_label"], "critical")
        self.assertGreaterEqual(float(result["late_fee_xgp"]), 0.0)
        self.assertLessEqual(int(result["credit_score_after"]), 850)
        self.assertGreaterEqual(int(result["credit_score_after"]), 300)

    def test_repeated_missed_payments_escalate_delinquency(self) -> None:
        for day in range(1, 7):
            apply_daily_financial_survival(
                db=self.db,
                player_id=str(self.fragile.id),
                day_number=day,
                available_cash_xgp=Decimal("0.00"),
                debt_payment_paid_xgp=Decimal("0.00"),
                housing_paid_xgp=Decimal("0.00"),
                utilities_paid_xgp=Decimal("0.00"),
                business_overhead_paid_xgp=Decimal("0.00"),
            )
        self.db.flush()

        delinquency = build_delinquency_state(self.db, str(self.fragile.id), day_number=6)
        self.assertGreaterEqual(int(delinquency["missed_payment_count_30d"]), 4)
        self.assertIn(
            str(delinquency["current_delinquency_stage"]),
            {"late", "delinquent", "critical"},
        )

    def test_credit_damage_is_bounded_and_recovery_is_gradual(self) -> None:
        initial_credit = int(self.low_shock.credit_score or 650)

        for day in range(1, 4):
            apply_daily_financial_survival(
                db=self.db,
                player_id=str(self.low_shock.id),
                day_number=day,
                available_cash_xgp=Decimal("0.00"),
                debt_payment_paid_xgp=Decimal("0.00"),
                housing_paid_xgp=Decimal("0.00"),
                utilities_paid_xgp=Decimal("0.00"),
                business_overhead_paid_xgp=Decimal("0.00"),
            )
        miss_day = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.low_shock.id),
            day_number=4,
            available_cash_xgp=Decimal("0.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )
        credit_after_misses = int(miss_day["credit_score_after"])

        for day in range(5, 10):
            apply_daily_financial_survival(
                db=self.db,
                player_id=str(self.low_shock.id),
                day_number=day,
                available_cash_xgp=Decimal("900.00"),
            )

        recovery_state = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.low_shock.id),
            day_number=10,
            available_cash_xgp=Decimal("900.00"),
        )
        credit_after_recovery = int(recovery_state["credit_score_after"])

        self.assertLess(credit_after_misses, initial_credit)
        self.assertGreaterEqual(credit_after_recovery, credit_after_misses)
        self.assertLess(credit_after_recovery, initial_credit + 1)
        self.assertGreaterEqual(credit_after_recovery, 300)
        self.assertLessEqual(credit_after_recovery, 850)

    def test_personal_shock_risk_can_amplify_payment_distress(self) -> None:
        low = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.low_shock.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )
        high = apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.high_shock.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )

        low_distress = Decimal(str((low.get("debug_meta") or {}).get("distress_score", 0)))
        high_distress = Decimal(str((high.get("debug_meta") or {}).get("distress_score", 0)))

        self.assertGreater(high_distress, low_distress)

    def test_practical_actions_are_current_scope_and_non_bloated(self) -> None:
        apply_daily_financial_survival(
            db=self.db,
            player_id=str(self.fragile.id),
            day_number=1,
            available_cash_xgp=Decimal("0.00"),
            debt_payment_paid_xgp=Decimal("0.00"),
            housing_paid_xgp=Decimal("0.00"),
            utilities_paid_xgp=Decimal("0.00"),
            business_overhead_paid_xgp=Decimal("0.00"),
        )
        summary = build_financial_survival_summary(self.db, str(self.fragile.id), day_number=1)
        actions = [str(item).lower() for item in summary["practical_current_actions"]]

        self.assertLessEqual(len(actions), 6)
        self.assertTrue(any("required obligations" in item or "cash buffer" in item for item in actions))
        self.assertFalse(any("token" in item or "crypto" in item for item in actions))


if __name__ == "__main__":
    unittest.main()
