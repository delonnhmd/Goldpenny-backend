import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_personal_shock_api.db")

from app.api.personal_shocks import (
    get_recent_event_route,
    get_recovery_state_route,
    get_resilience_summary_route,
    get_risk_state_route,
    get_shock_profile_route,
    get_shock_summary_route,
    get_shock_system_summary_route,
)
from app.db.database import Base
from app.models.daily_settlement_log import DailySettlementLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_life_event_history import PlayerLifeEventHistory
from app.models.player_recovery_state import PlayerRecoveryState
from app.models.player_shock_state import PlayerShockState
from app.models.region_population_state import RegionPopulationState
from app.models.user import User


class PersonalShockApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                DailySettlementLog.__table__,
                PlayerHousingState.__table__,
                PlayerEmploymentState.__table__,
                PlayerBusiness.__table__,
                RegionPopulationState.__table__,
                PlayerShockState.__table__,
                PlayerRecoveryState.__table__,
                PlayerLifeEventHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step35-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step35 API Tester",
            cash=Decimal("840.00"),
            debt_xgp=Decimal("960.00"),
            stress=68,
            health=72,
            region="downtown",
            main_job="delivery_driver",
            burnout_risk=Decimal("0.24"),
            productivity_modifier=Decimal("0.92"),
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            RegionPopulationState(
                region_key="downtown",
                active_population_score=Decimal("74.0"),
                opportunity_density_score=Decimal("78.0"),
                congestion_score=Decimal("72.0"),
                housing_pressure_score=Decimal("76.0"),
                business_competition_score=Decimal("70.0"),
                consumer_flow_score=Decimal("79.0"),
                recent_growth_direction="rising",
                last_updated_on=5,
                last_updated_date=date(2026, 1, 5),
            )
        )
        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("980.00"),
                monthly_utilities_cost_xgp=Decimal("150.00"),
                monthly_transport_base_xgp=Decimal("195.00"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=5,
                current_job_code="delivery_driver",
                skill_level=1,
                monthly_pay_xgp=Decimal("2900.00"),
                employed_flag=True,
                job_status="employed",
                layoff_risk_pct=Decimal("9.00"),
                productivity_modifier=Decimal("0.92"),
            )
        )
        for day in range(1, 6):
            self.db.add(
                DailySettlementLog(
                    player_id=self.player.id,
                    day_number=day,
                    hours_before_reset=8,
                    hours_after_reset=24,
                    stress_before=66 + day - 1,
                    stress_after=68 + day - 1,
                    health_before=74 - day + 1,
                    health_after=73 - day + 1,
                    cash_before=Decimal("900.00"),
                    cash_after=Decimal("860.00"),
                    income_xgp=Decimal("145.00"),
                    expenses_xgp=Decimal("198.00"),
                    stock_pnl_xgp=Decimal("0.0"),
                    debt_paid_xgp=Decimal("12.00"),
                    health_change=-1,
                    stress_change=2,
                )
            )
            self.db.add(
                PlayerDailyState(
                    player_id=self.player.id,
                    day_number=day,
                    sleep_hours=Decimal("5.8"),
                    overtime_hours=Decimal("1.8"),
                    recovery_hours=Decimal("0.8"),
                    commute_hours=Decimal("1.35"),
                    productivity_modifier=Decimal("0.91"),
                )
            )

    def test_personal_shock_routes_return_frontend_ready_shapes(self) -> None:
        profile = get_shock_profile_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
            db=self.db,
        )
        risk = get_risk_state_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
            db=self.db,
        )
        recent_event = get_recent_event_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
            db=self.db,
        )
        recovery = get_recovery_state_route(
            player_id=str(self.player.id),
            db=self.db,
        )
        resilience = get_resilience_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
            db=self.db,
        )
        summary = get_shock_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
            db=self.db,
        )
        system = get_shock_system_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 5),
            day_number=5,
            db=self.db,
        )

        self.assertEqual(profile.player_id, str(self.player.id))
        self.assertEqual(risk.player_id, str(self.player.id))
        self.assertIsNotNone(recent_event.headline)
        self.assertIn(summary.current_shock_risk_label, {"low", "moderate", "high"})
        self.assertEqual(system.player_id, str(self.player.id))
        self.assertEqual(system.shock_profile.player_id, str(self.player.id))
        self.assertEqual(system.risk_state.player_id, str(self.player.id))
        self.assertEqual(system.resilience_summary.player_id, str(self.player.id))
        self.assertIn(recovery.recovery_status_label, {"stable", "brief_recovery", "active_recovery", "extended_recovery"})


if __name__ == "__main__":
    unittest.main()
