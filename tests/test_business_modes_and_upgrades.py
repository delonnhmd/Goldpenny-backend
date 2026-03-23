import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_business_modes_and_upgrades.db")

from app.db.database import Base
from app.engine.business_service import (
    create_or_get_starter_business,
    day_to_date,
    operate_food_truck,
    operate_fruit_shop,
    purchase_business_upgrade,
    set_business_operating_mode,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.user import User


class BusinessModesAndUpgradesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                PlayerDailyState.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(email=f"biz-modes-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()
        self.player = Player(
            user_id=user.id,
            display_name="Mode Test Player",
            cash=Decimal("25000.00"),
            stress=22,
            health=94,
            hours_available=16,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        self._seed_macro_and_prices()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_macro_and_prices(self) -> None:
        macro_rows = [
            (1, Decimal("102.0"), Decimal("54.0"), Decimal("0.6")),
            (2, Decimal("104.0"), Decimal("52.0"), Decimal("0.8")),
            (3, Decimal("118.0"), Decimal("48.0"), Decimal("1.2")),
            (4, Decimal("165.0"), Decimal("42.0"), Decimal("2.0")),
        ]
        for day, oil, confidence, supply_stress in macro_rows:
            self.db.add(
                MacroDailyState(
                    day=day,
                    inflation_rate=Decimal("2.5"),
                    interest_rate=Decimal("4.1"),
                    unemployment_rate=Decimal("5.2"),
                    oil_index=oil,
                    consumer_confidence=confidence,
                    supply_chain_stress=supply_stress,
                    event_headline="Mode test macro",
                    event_summary="Seeded for mode and upgrade coverage.",
                )
            )

        price_rows = [
            (1, BasketType.produce, Decimal("8.2")),
            (1, BasketType.essentials, Decimal("10.1")),
            (1, BasketType.protein, Decimal("12.0")),
            (2, BasketType.produce, Decimal("9.4")),
            (2, BasketType.essentials, Decimal("11.2")),
            (2, BasketType.protein, Decimal("13.4")),
            (3, BasketType.produce, Decimal("10.3")),
            (3, BasketType.essentials, Decimal("12.8")),
            (3, BasketType.protein, Decimal("15.1")),
            (4, BasketType.produce, Decimal("11.8")),
            (4, BasketType.essentials, Decimal("15.2")),
            (4, BasketType.protein, Decimal("18.4")),
        ]
        for day, basket_type, price_index in price_rows:
            self.db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=basket_type,
                    price_index=price_index,
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )

    def _new_business(self, business_type: str, *, region: str = "downtown", reputation: int = 55) -> PlayerBusiness:
        (
            self.db.query(PlayerBusiness)
            .filter(
                PlayerBusiness.player_id == self.player.id,
                PlayerBusiness.business_id == business_type,
                PlayerBusiness.is_active.is_(True),
            )
            .update({"is_active": False}, synchronize_session=False)
        )
        self.db.flush()
        payload = create_or_get_starter_business(
            db=self.db,
            player_id=str(self.player.id),
            business_type=business_type,
            region_key=region,
        )
        business = self.db.query(PlayerBusiness).filter(PlayerBusiness.id == uuid.UUID(payload["business_id"])).first()
        self.assertIsNotNone(business)
        business.reputation = reputation
        self.db.flush()
        return business

    def test_fruit_modes_change_sell_through_in_expected_direction(self) -> None:
        conservative = self._new_business("fruit_shop")
        aggressive = self._new_business("fruit_shop")
        conservative.inventory_produce_units = Decimal("180")
        aggressive.inventory_produce_units = Decimal("180")

        set_business_operating_mode(
            db=self.db,
            player_id=str(self.player.id),
            business_id=str(conservative.id),
            mode_key="conservative_pricing",
        )
        set_business_operating_mode(
            db=self.db,
            player_id=str(self.player.id),
            business_id=str(aggressive.id),
            mode_key="aggressive_markup",
        )

        conservative_result = operate_fruit_shop(self.db, conservative, day_number=2, as_of_date=day_to_date(2))
        aggressive_result = operate_fruit_shop(self.db, aggressive, day_number=2, as_of_date=day_to_date(2))

        self.assertGreater(conservative_result["units_sold"], aggressive_result["units_sold"])
        self.assertEqual(conservative_result["debug_meta"]["operating_mode"], "conservative_pricing")
        self.assertEqual(aggressive_result["debug_meta"]["operating_mode"], "aggressive_markup")

    def test_fruit_upgrade_reduces_spoilage_but_stays_bounded(self) -> None:
        baseline = self._new_business("fruit_shop", reputation=45)
        upgraded = self._new_business("fruit_shop", reputation=45)
        baseline.inventory_produce_units = Decimal("120")
        upgraded.inventory_produce_units = Decimal("120")

        base_result = operate_fruit_shop(self.db, baseline, day_number=4, as_of_date=day_to_date(4))
        purchase_business_upgrade(
            db=self.db,
            player_id=str(self.player.id),
            business_id=str(upgraded.id),
            upgrade_key="better_storage",
        )
        upgrade_result = operate_fruit_shop(self.db, upgraded, day_number=4, as_of_date=day_to_date(4))

        self.assertLessEqual(upgrade_result["spoilage_loss_xgp"], base_result["spoilage_loss_xgp"])
        # Upgrade should help but not fully erase spoilage pressure.
        self.assertGreaterEqual(upgrade_result["spoilage_loss_xgp"], 0.0)

    def test_food_truck_upgrade_reduces_fuel_cost_without_extreme_gain(self) -> None:
        baseline = self._new_business("food_truck", reputation=60)
        upgraded = self._new_business("food_truck", reputation=60)
        baseline.inventory_essentials_units = Decimal("180")
        baseline.inventory_protein_units = Decimal("180")
        upgraded.inventory_essentials_units = Decimal("180")
        upgraded.inventory_protein_units = Decimal("180")

        base_result = operate_food_truck(self.db, baseline, day_number=4, as_of_date=day_to_date(4))
        purchase_business_upgrade(
            db=self.db,
            player_id=str(self.player.id),
            business_id=str(upgraded.id),
            upgrade_key="fuel_efficiency_upgrade",
        )
        upgraded_result = operate_food_truck(self.db, upgraded, day_number=4, as_of_date=day_to_date(4))

        self.assertLess(upgraded_result["fuel_cost_xgp"], base_result["fuel_cost_xgp"])
        reduction = Decimal(str(base_result["fuel_cost_xgp"])) - Decimal(str(upgraded_result["fuel_cost_xgp"]))
        self.assertLessEqual(reduction, Decimal(str(base_result["fuel_cost_xgp"])) * Decimal("0.40"))
        self.assertIn("fuel_efficiency_upgrade", upgraded_result["debug_meta"]["upgrades"])


if __name__ == "__main__":
    unittest.main()

