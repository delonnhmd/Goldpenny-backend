import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_side_income_transmission.db")

from app.engine.rideshare_engine import process_rideshare_action
from app.engine.side_income_service import compute_rideshare_shift
from app.db.database import Base
from app.models.contribution_event import ContributionEvent
from app.models.game_state import GameState
from app.models.macro_state import MacroState
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.side_income_action import SideIncomeAction
from app.models.user import User
from app.models.xgp_transaction import XGPTransaction


class SideIncomeTransmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                SideIncomeAction.__table__,
                XGPTransaction.__table__,
                ContributionEvent.__table__,
                GameState.__table__,
                MacroState.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"side-income-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Side Income Player",
            cash=Decimal("1200.00"),
            stress=18,
            health=95,
            hours_available=16,
            region="suburban",
            rideshare_reliability=Decimal("0.95"),
        )
        self.db.add(self.player)
        self.db.add(
            GameState(
                current_day=1,
                day_status="open",
            )
        )
        self.db.add(
            MacroState(
                day_number=1,
                inflation=Decimal("2.0"),
                interest_rate=Decimal("4.0"),
                unemployment=Decimal("6.0"),
                oil_index=Decimal("110.0"),
                consumer_confidence=Decimal("48.0"),
                supply_chain_stress=Decimal("0.0"),
                is_active=True,
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_higher_oil_increases_gas_cost(self) -> None:
        low_oil = compute_rideshare_shift(
            player_seed="p1",
            day_number=1,
            region_key="suburban",
            hours_worked=3,
            oil_index=Decimal("90"),
            consumer_confidence=Decimal("50"),
            unemployment_rate=Decimal("5"),
            reliability=Decimal("0.95"),
        )
        high_oil = compute_rideshare_shift(
            player_seed="p1",
            day_number=1,
            region_key="suburban",
            hours_worked=3,
            oil_index=Decimal("160"),
            consumer_confidence=Decimal("50"),
            unemployment_rate=Decimal("5"),
            reliability=Decimal("0.95"),
        )
        self.assertGreater(high_oil["gas_cost_xgp"], low_oil["gas_cost_xgp"])

    def test_stronger_demand_multiplier_raises_gross_income(self) -> None:
        weak = compute_rideshare_shift(
            player_seed="p2",
            day_number=1,
            region_key="suburban",
            hours_worked=4,
            oil_index=Decimal("100"),
            consumer_confidence=Decimal("75"),
            unemployment_rate=Decimal("3"),
            reliability=Decimal("0.95"),
        )
        strong = compute_rideshare_shift(
            player_seed="p2",
            day_number=1,
            region_key="suburban",
            hours_worked=4,
            oil_index=Decimal("100"),
            consumer_confidence=Decimal("40"),
            unemployment_rate=Decimal("9"),
            reliability=Decimal("0.95"),
        )
        self.assertGreater(strong["demand_multiplier"], weak["demand_multiplier"])
        self.assertGreater(strong["gross_income_xgp"], weak["gross_income_xgp"])

    def test_maintenance_trigger_probability_is_bounded_and_cost_is_consistent(self) -> None:
        shift = compute_rideshare_shift(
            player_seed="maintenance-seed",
            day_number=1,
            region_key="suburban",
            hours_worked=6,
            oil_index=Decimal("150"),
            consumer_confidence=Decimal("45"),
            unemployment_rate=Decimal("8"),
            reliability=Decimal("0.70"),
        )
        self.assertGreaterEqual(shift["maintenance_probability"], Decimal("0.01"))
        self.assertLessEqual(shift["maintenance_probability"], Decimal("0.35"))
        if shift["maintenance_triggered"]:
            self.assertGreater(shift["maintenance_cost_xgp"], Decimal("0.00"))
        else:
            self.assertEqual(shift["maintenance_cost_xgp"], Decimal("0.00"))

    def test_process_rideshare_action_enforces_daily_anti_grind_cap(self) -> None:
        with self.assertRaises(ValueError):
            process_rideshare_action(self.db, self.player, 7)

        first = process_rideshare_action(self.db, self.player, 4)
        self.assertEqual(first["hours_worked"], 4)

        # Only 2 hours should remain under the 6h side-income cap.
        with self.assertRaises(ValueError):
            process_rideshare_action(self.db, self.player, 3)


if __name__ == "__main__":
    unittest.main()

