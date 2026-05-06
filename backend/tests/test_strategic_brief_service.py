"""Tests for Phase 4 Step 4 — Strategic Daily Brief service."""

from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_strategic_brief_service.db")

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.user import User
from app.services.strategic_brief_service import (
    MAX_BUSINESS_ALERTS,
    MAX_PORTFOLIO_ALERTS,
    MAX_RECOMMENDED_ACTIONS,
    MAX_RISK_WARNINGS,
    VALID_TARGET_SCREENS,
    build_strategic_brief,
)


class StrategicBriefServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, future=True
        )
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
            ],
        )
        self.db = self.SessionLocal()

        user = User(
            email=f"strat-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=str(user.id),
            display_name="Strat Test",
            cash=Decimal("1000.00"),
            debt_xgp=Decimal("0.00"),
            credit_score=650,
            stress=20,
            health=90,
            region="suburban",
            net_worth=Decimal("1000.00"),
        )
        self.db.add(self.player)
        self.db.flush()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _add_business(
        self,
        *,
        business_id: str = "fruit_shop",
        produce: Decimal = Decimal("0"),
        essentials: Decimal = Decimal("0"),
        protein: Decimal = Decimal("0"),
        is_active: bool = True,
        region: str | None = None,
        last_operated_day: int | None = 1,
    ) -> PlayerBusiness:
        biz = PlayerBusiness(
            id=uuid.uuid4(),
            player_id=self.player.id,
            business_id=business_id,
            business_name=business_id,
            region=region or self.player.region,
            business_level=1,
            reputation=50,
            inventory_produce_units=produce,
            inventory_essentials_units=essentials,
            inventory_protein_units=protein,
            created_day=1,
            last_operated_day=last_operated_day,
            is_active=is_active,
        )
        self.db.add(biz)
        self.db.flush()
        return biz

    def _add_log(
        self,
        biz: PlayerBusiness,
        *,
        day: int = 1,
        units_sold: int = 10,
        net_profit: Decimal = Decimal("5"),
        spoilage: Decimal = Decimal("0"),
        revenue: Decimal = Decimal("50"),
    ) -> BusinessDailyLog:
        log = BusinessDailyLog(
            business_id=biz.id,
            player_id=self.player.id,
            day=day,
            business_type=biz.business_id,
            region_key=biz.region,
            gross_revenue_xgp=revenue,
            input_cost_xgp=Decimal("20"),
            labor_cost_xgp=Decimal("0"),
            maintenance_cost_xgp=Decimal("0"),
            spoilage_cost_xgp=spoilage,
            overhead_cost_xgp=Decimal("5"),
            net_profit_xgp=net_profit,
            units_sold=units_sold,
            inventory_start_units=Decimal("100"),
            inventory_end_units=Decimal("90"),
            demand_signal=Decimal("1.0"),
            demand_score=Decimal("1.0"),
            utilization_pct=Decimal("0.5"),
        )
        self.db.add(log)
        self.db.flush()
        return log

    def _add_macro(
        self,
        *,
        day: int = 1,
        oil: Decimal = Decimal("90"),
        supply_stress: Decimal = Decimal("0.5"),
        confidence: Decimal = Decimal("55"),
        inflation: Decimal = Decimal("2.5"),
        unemployment: Decimal = Decimal("5.0"),
    ) -> None:
        self.db.add(
            MacroDailyState(
                day=day,
                inflation_rate=inflation,
                interest_rate=Decimal("4.0"),
                unemployment_rate=unemployment,
                oil_index=oil,
                consumer_confidence=confidence,
                supply_chain_stress=supply_stress,
                event_headline="x",
                event_summary="x",
            )
        )

    def _add_produce_prices(self, today: Decimal, prev: Decimal) -> None:
        self.db.add_all(
            [
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.produce,
                    price_index=prev,
                    daily_change_pct=Decimal("0"),
                    supply_pressure=Decimal("1"),
                    demand_pressure=Decimal("1"),
                ),
                BasketDailyPrice(
                    day=2,
                    basket_type=BasketType.produce,
                    price_index=today,
                    daily_change_pct=Decimal("0"),
                    supply_pressure=Decimal("1"),
                    demand_pressure=Decimal("1"),
                ),
            ]
        )

    # ── tests ────────────────────────────────────────────────────────────────

    def test_no_inventory_creates_high_severity_alert(self):
        biz = self._add_business(business_id="fruit_shop", produce=Decimal("0"))
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        alerts = brief["business_alerts"]
        self.assertTrue(any(a["severity"] == "high" and "no inventory" in a["cause"].lower() for a in alerts))
        # Recommended action references restocking.
        actions = brief["recommended_actions"]
        self.assertTrue(any("restock" in a["action"].lower() for a in actions))

    def test_low_stock_creates_restock_action(self):
        biz = self._add_business(business_id="fruit_shop", produce=Decimal("5"))
        self._add_log(biz, day=1, units_sold=10, net_profit=Decimal("5"))
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        # 5 / 10 = 0.5 days_left → high severity, restock today.
        actions = brief["recommended_actions"]
        self.assertTrue(any("restock" in a["action"].lower() for a in actions))

    def test_negative_profit_creates_business_warning(self):
        biz = self._add_business(business_id="generic", produce=Decimal("100"))
        self._add_log(biz, day=1, units_sold=10, net_profit=Decimal("-12.50"))
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        self.assertTrue(any("lost" in a["cause"].lower() for a in brief["business_alerts"]))

    def test_high_oil_creates_food_truck_warning(self):
        biz = self._add_business(business_id="food_truck", produce=Decimal("50"))
        self._add_log(biz, day=1, units_sold=10)
        self._add_macro(day=1, oil=Decimal("160"), supply_stress=Decimal("2.0"))
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        self.assertTrue(
            any(
                "fuel" in a["effect"].lower() or "oil" in a["cause"].lower()
                for a in brief["business_alerts"]
            )
        )

    def test_produce_price_pressure_creates_fruit_shop_warning(self):
        biz = self._add_business(business_id="fruit_shop", produce=Decimal("50"))
        self._add_log(biz, day=2, units_sold=10)
        self._add_produce_prices(today=Decimal("11.0"), prev=Decimal("10.0"))
        self._add_macro(day=2)
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 2)
        self.assertTrue(
            any("produce prices" in a["cause"].lower() for a in brief["business_alerts"])
        )

    def test_low_cash_creates_risk_warning(self):
        self.player.cash = Decimal("5.00")
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        self.assertTrue(
            any("cash" in a["cause"].lower() for a in brief["risk_warnings"])
        )

    def test_high_debt_creates_portfolio_alert(self):
        self.player.cash = Decimal("100.00")
        self.player.debt_xgp = Decimal("5000.00")
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        self.assertTrue(
            any(a["severity"] == "high" for a in brief["portfolio_alerts"])
        )

    def test_owned_unused_slot_creates_map_opportunity(self):
        self._add_business(
            business_id="fruit_shop",
            produce=Decimal("10"),
            last_operated_day=None,
        )
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        self.assertTrue(
            any(
                a["type"] == "map_opportunity"
                for a in brief["map_opportunities"]
            )
        )

    def test_recommendations_capped_at_3(self):
        # Stack many issues.
        self.player.cash = Decimal("5.00")
        self.player.stress = 95
        self.player.health = 25
        self.player.debt_xgp = Decimal("5000.00")
        self.player.missed_payment_streak = 3
        self.player.distress_score = Decimal("0.95")
        for biz_id in ("fruit_shop", "food_truck", "produce_stand"):
            self._add_business(business_id=biz_id, produce=Decimal("0"))
        self._add_macro(day=1, oil=Decimal("160"), supply_stress=Decimal("2.0"))
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        self.assertLessEqual(len(brief["recommended_actions"]), MAX_RECOMMENDED_ACTIONS)
        self.assertLessEqual(len(brief["risk_warnings"]), MAX_RISK_WARNINGS)
        self.assertLessEqual(len(brief["business_alerts"]), MAX_BUSINESS_ALERTS)
        self.assertLessEqual(len(brief["portfolio_alerts"]), MAX_PORTFOLIO_ALERTS)

    def test_missing_business_portfolio_slot_data_does_not_crash(self):
        # No businesses, no macro, no baskets. Should still return a valid shape.
        brief = build_strategic_brief(self.db, self.player.id, 1)
        for key in (
            "headline",
            "today_pressure",
            "macro_summary",
            "player_condition",
            "business_alerts",
            "portfolio_alerts",
            "map_opportunities",
            "risk_warnings",
            "recommended_actions",
        ):
            self.assertIn(key, brief)
        self.assertIsInstance(brief["recommended_actions"], list)

    def test_target_screen_values_are_valid(self):
        self.player.cash = Decimal("5.00")
        self.player.stress = 95
        self.player.debt_xgp = Decimal("3000.00")
        self._add_business(business_id="fruit_shop", produce=Decimal("0"))
        self._add_macro(day=1, oil=Decimal("160"), supply_stress=Decimal("2.0"))
        self.db.commit()
        brief = build_strategic_brief(self.db, self.player.id, 1)
        for section in ("business_alerts", "portfolio_alerts", "map_opportunities", "risk_warnings"):
            for alert in brief[section]:
                self.assertIn(alert["target_screen"], VALID_TARGET_SCREENS)
        for action in brief["recommended_actions"]:
            self.assertIn(action["target_screen"], VALID_TARGET_SCREENS)

    def test_no_economy_or_business_formulas_changed(self):
        """Strategic brief must read existing model fields only — no new formula state.

        We assert this structurally: the service module does NOT mutate any
        rows (no commit/flush) and does NOT import any engine module. This
        guards against accidental coupling that would change formulas.
        """
        import inspect

        from app.services import strategic_brief_service as svc

        source = inspect.getsource(svc)
        # No engine writes / formula files.
        self.assertNotIn("from app.engine.macro_engine", source)
        self.assertNotIn("from app.engine.economy_engine", source)
        self.assertNotIn("from app.engine.business_balance_engine", source)
        self.assertNotIn("from app.engine.business_engine", source)
        # No state mutation.
        self.assertNotIn("db.commit", source)
        self.assertNotIn("db.add(", source)
        self.assertNotIn("db.flush", source)


if __name__ == "__main__":
    unittest.main()
