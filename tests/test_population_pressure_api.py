import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_population_pressure_api.db")

from app.api.population_pressure import (
    get_competition_state_route,
    get_opportunity_pressure_route,
    get_population_summary_route,
    get_region_heat_route,
    get_region_state_route,
    get_response_summary_route,
    refresh_population_route,
)
from app.db.database import Base
from app.models.business_daily_log import BusinessDailyLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_housing_state import PlayerHousingState
from app.models.region_population_history import RegionPopulationHistory
from app.models.region_population_state import RegionPopulationState
from app.models.user import User


class PopulationPressureApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerHousingState.__table__,
                MacroDailyState.__table__,
                HousingDailyLog.__table__,
                BusinessDailyLog.__table__,
                RegionPopulationState.__table__,
                RegionPopulationHistory.__table__,
            ],
        )
        self.db = self.SessionLocal()
        self._seed()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed(self) -> None:
        user = User(email=f"step34-api-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Step34 API Tester",
            cash=Decimal("1500.00"),
            stress=35,
            health=86,
            hours_available=16,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        self.db.add(
            PlayerHousingState(
                player_id=self.player.id,
                region="downtown",
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("980.0"),
                monthly_utilities_cost_xgp=Decimal("150.0"),
                monthly_transport_base_xgp=Decimal("180.0"),
                commute_mode="car",
                active_flag=True,
            )
        )
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.70"),
                interest_rate=Decimal("4.20"),
                unemployment_rate=Decimal("5.10"),
                oil_index=Decimal("110.0"),
                consumer_confidence=Decimal("50.0"),
                supply_chain_stress=Decimal("0.95"),
                event_headline="Step34 API macro",
                event_summary="Seeded API macro row.",
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                region="downtown",
                housing_cost_xgp=Decimal("31.33"),
                utilities_cost_xgp=Decimal("4.70"),
                commute_hours=Decimal("0.82"),
                commute_fuel_cost_xgp=Decimal("3.50"),
                commute_pressure=Decimal("0.66"),
                stress_delta=2,
                opportunity_modifier=Decimal("1.08"),
                region_stress_delta=Decimal("0.90"),
                region_opportunity_modifier=Decimal("0.09"),
                region_business_demand_modifier=Decimal("0.11"),
                region_side_income_modifier=Decimal("0.10"),
                networking_modifier=Decimal("0.10"),
                opportunity_quality_signal=Decimal("1.07"),
            )
        )
        self.db.add(
            BusinessDailyLog(
                business_id=uuid.uuid4(),
                player_id=self.player.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                business_type="food_truck",
                region_key="downtown",
                gross_revenue_xgp=Decimal("84.00"),
                input_cost_xgp=Decimal("62.00"),
                fuel_cost_xgp=Decimal("9.50"),
                overhead_cost_xgp=Decimal("14.00"),
                net_profit_xgp=Decimal("-1.00"),
                units_sold=27,
                inventory_start_units=Decimal("40"),
                inventory_end_units=Decimal("11"),
                demand_signal=Decimal("0.84"),
                demand_score=Decimal("0.84"),
                utilization_pct=Decimal("0.68"),
            )
        )

    def test_population_routes_return_frontend_ready_shapes(self) -> None:
        region_state = get_region_state_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        opportunity = get_opportunity_pressure_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        competition = get_competition_state_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        heat = get_region_heat_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        response = get_response_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        summary = get_population_summary_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )

        self.assertEqual(region_state.player_id, str(self.player.id))
        self.assertEqual(opportunity.player_id, str(self.player.id))
        self.assertEqual(competition.player_id, str(self.player.id))
        self.assertEqual(heat.player_id, str(self.player.id))
        self.assertEqual(response.player_id, str(self.player.id))
        self.assertEqual(summary.player_id, str(self.player.id))
        self.assertTrue(summary.response_summary.future_locked_response_options)
        self.assertIn("locked", " ".join(summary.response_summary.future_locked_response_options).lower())

    def test_refresh_route_updates_and_returns_region_state(self) -> None:
        refreshed = refresh_population_route(
            player_id=str(self.player.id),
            as_of_date=date(2026, 1, 1),
            db=self.db,
        )
        self.assertEqual(refreshed.player_id, str(self.player.id))
        self.assertIn(refreshed.heat_level, {"cool", "warm", "hot"})


if __name__ == "__main__":
    unittest.main()
