import os
import unittest
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_population_pressure_service.db")

from app.db.database import Base
from app.engine.population_pressure_service import (
    build_local_competition_state,
    build_population_response_summary,
    build_region_heat_summary,
    build_region_population_state,
    update_population_pressure,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_housing_state import PlayerHousingState
from app.models.region_population_history import RegionPopulationHistory
from app.models.region_population_state import RegionPopulationState
from app.models.user import User


class PopulationPressureServiceTests(unittest.TestCase):
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
        self._seed_day_one()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_player(self, *, region: str, cash: Decimal = Decimal("1200.00")) -> Player:
        user = User(email=f"step34-{region}-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        player = Player(
            user_id=user.id,
            display_name=f"Step34 {region}",
            cash=cash,
            stress=32,
            health=88,
            hours_available=16,
            region=region,
        )
        self.db.add(player)
        self.db.flush()
        self.db.add(
            PlayerHousingState(
                player_id=player.id,
                region=region,
                housing_type="rent",
                monthly_housing_cost_xgp=Decimal("980.0") if region == "downtown" else Decimal("560.0"),
                monthly_utilities_cost_xgp=Decimal("150.0") if region == "downtown" else Decimal("95.0"),
                monthly_transport_base_xgp=Decimal("180.0") if region == "downtown" else Decimal("130.0"),
                commute_mode="car",
                active_flag=True,
            )
        )
        return player

    def _seed_day_one(self) -> None:
        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.60"),
                interest_rate=Decimal("4.10"),
                unemployment_rate=Decimal("5.20"),
                oil_index=Decimal("108.0"),
                consumer_confidence=Decimal("51.0"),
                supply_chain_stress=Decimal("0.90"),
                event_headline="Step34 baseline",
                event_summary="Baseline macro for population pressure tests.",
            )
        )
        self.player_suburban = self._create_player(region="suburban")
        self.player_downtown = self._create_player(region="downtown")

        self.db.add(
            HousingDailyLog(
                player_id=self.player_suburban.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                region="suburban",
                housing_cost_xgp=Decimal("18.67"),
                utilities_cost_xgp=Decimal("3.17"),
                commute_hours=Decimal("1.45"),
                commute_fuel_cost_xgp=Decimal("4.80"),
                commute_pressure=Decimal("1.12"),
                stress_delta=1,
                opportunity_modifier=Decimal("0.95"),
                region_stress_delta=Decimal("0.55"),
                region_opportunity_modifier=Decimal("-0.04"),
                region_business_demand_modifier=Decimal("-0.05"),
                region_side_income_modifier=Decimal("-0.04"),
                networking_modifier=Decimal("-0.05"),
                opportunity_quality_signal=Decimal("0.95"),
            )
        )
        self.db.add(
            HousingDailyLog(
                player_id=self.player_downtown.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                region="downtown",
                housing_cost_xgp=Decimal("31.33"),
                utilities_cost_xgp=Decimal("4.70"),
                commute_hours=Decimal("0.78"),
                commute_fuel_cost_xgp=Decimal("3.40"),
                commute_pressure=Decimal("0.64"),
                stress_delta=2,
                opportunity_modifier=Decimal("1.09"),
                region_stress_delta=Decimal("0.90"),
                region_opportunity_modifier=Decimal("0.09"),
                region_business_demand_modifier=Decimal("0.12"),
                region_side_income_modifier=Decimal("0.10"),
                networking_modifier=Decimal("0.11"),
                opportunity_quality_signal=Decimal("1.08"),
            )
        )
        self.db.add(
            BusinessDailyLog(
                business_id=uuid.uuid4(),
                player_id=self.player_suburban.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                business_type="fruit_shop",
                region_key="suburban",
                gross_revenue_xgp=Decimal("62.00"),
                input_cost_xgp=Decimal("40.00"),
                spoilage_cost_xgp=Decimal("4.00"),
                overhead_cost_xgp=Decimal("10.00"),
                net_profit_xgp=Decimal("8.00"),
                units_sold=22,
                inventory_start_units=Decimal("52"),
                inventory_end_units=Decimal("24"),
                demand_signal=Decimal("0.72"),
                demand_score=Decimal("0.72"),
                utilization_pct=Decimal("0.58"),
            )
        )
        self.db.add(
            BusinessDailyLog(
                business_id=uuid.uuid4(),
                player_id=self.player_downtown.id,
                day=1,
                as_of_date=date(2026, 1, 1),
                business_type="food_truck",
                region_key="downtown",
                gross_revenue_xgp=Decimal("84.00"),
                input_cost_xgp=Decimal("62.00"),
                fuel_cost_xgp=Decimal("9.20"),
                overhead_cost_xgp=Decimal("14.00"),
                net_profit_xgp=Decimal("-1.20"),
                units_sold=27,
                inventory_start_units=Decimal("40"),
                inventory_end_units=Decimal("11"),
                demand_signal=Decimal("0.84"),
                demand_score=Decimal("0.84"),
                utilization_pct=Decimal("0.68"),
            )
        )

    def test_activity_density_raises_congestion_in_bounded_way(self) -> None:
        baseline = update_population_pressure(
            self.db,
            str(self.player_downtown.id),
            as_of_date=date(2026, 1, 1),
        )
        baseline_congestion = Decimal(str(baseline["region_state"]["congestion_score"]))

        # Add more players concentrated downtown to intensify activity density.
        for _ in range(10):
            self._create_player(region="downtown", cash=Decimal("900.00"))
        self.db.commit()

        updated = update_population_pressure(
            self.db,
            str(self.player_downtown.id),
            as_of_date=date(2026, 1, 1),
        )
        updated_congestion = Decimal(str(updated["region_state"]["congestion_score"]))

        self.assertGreater(updated_congestion, baseline_congestion)
        self.assertGreaterEqual(updated_congestion, Decimal("0"))
        self.assertLessEqual(updated_congestion, Decimal("100"))

    def test_hot_regions_show_upside_and_friction_together(self) -> None:
        update_population_pressure(self.db, str(self.player_downtown.id), as_of_date=date(2026, 1, 1))
        heat = build_region_heat_summary(
            self.db,
            str(self.player_downtown.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertTrue(heat["dominant_upside"])
        self.assertTrue(heat["dominant_friction"])
        self.assertIn(heat["heat_level"], {"cool", "warm", "hot"})

    def test_suburban_and_downtown_diverge_meaningfully(self) -> None:
        update_population_pressure(self.db, str(self.player_suburban.id), as_of_date=date(2026, 1, 1))
        sub_state = build_region_population_state(
            self.db,
            str(self.player_suburban.id),
            as_of_date=date(2026, 1, 1),
        )
        down_state = build_region_population_state(
            self.db,
            str(self.player_downtown.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertNotEqual(sub_state["region_key"], down_state["region_key"])
        self.assertNotEqual(
            Decimal(str(sub_state["opportunity_density_score"])),
            Decimal(str(down_state["opportunity_density_score"])),
        )
        self.assertNotEqual(
            Decimal(str(sub_state["housing_pressure_score"])),
            Decimal(str(down_state["housing_pressure_score"])),
        )

    def test_business_competition_changes_with_region_heat(self) -> None:
        update_population_pressure(self.db, str(self.player_suburban.id), as_of_date=date(2026, 1, 1))
        sub_comp = build_local_competition_state(
            self.db,
            str(self.player_suburban.id),
            as_of_date=date(2026, 1, 1),
        )
        down_comp = build_local_competition_state(
            self.db,
            str(self.player_downtown.id),
            as_of_date=date(2026, 1, 1),
        )
        self.assertNotEqual(sub_comp["competition_level"], down_comp["competition_level"])
        for payload in (sub_comp, down_comp):
            pressure = Decimal(str(payload["demand_share_pressure"]))
            self.assertGreaterEqual(pressure, Decimal("0.05"))
            self.assertLessEqual(pressure, Decimal("0.72"))

    def test_response_summary_keeps_practical_tradeoff_and_locked_future(self) -> None:
        update_population_pressure(self.db, str(self.player_downtown.id), as_of_date=date(2026, 1, 1))
        response = build_population_response_summary(
            self.db,
            str(self.player_downtown.id),
            as_of_date=date(2026, 1, 1),
        )
        practical = " ".join(response["practical_current_responses"]).lower()
        locked = " ".join(response["future_locked_response_options"]).lower()
        self.assertIn("move", practical)
        self.assertIn("rent closer", practical)
        self.assertIn("locked", locked)


if __name__ == "__main__":
    unittest.main()
