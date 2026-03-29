import json
import os
import unittest
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_daily_brief_service.db")

from app.db.database import Base
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.daily_brief_service import (
    generate_global_daily_event,
    generate_player_daily_brief,
    get_player_daily_brief_history,
    get_player_latest_daily_brief,
)


class DailyBriefServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )

        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                MacroDailyState.__table__,
                BasketDailyPrice.__table__,
                StockDailyPrice.__table__,
                PlayerStockHolding.__table__,
                PlayerEmploymentState.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                HousingDailyLog.__table__,
                BasketConsumptionLog.__table__,
                DebtCreditLog.__table__,
                DailySettlementLog.__table__,
                DailyBriefLog.__table__,
            ],
        )

        self.db = self.SessionLocal()

        user = User(
            email=f"brief-test-{uuid.uuid4()}@example.com",
            hashed_password="hashed",
        )
        self.db.add(user)
        self.db.flush()

        self.player = Player(
            user_id=user.id,
            display_name="Brief Test Player",
            cash=Decimal("1200.00"),
            debt_xgp=Decimal("850.00"),
            credit_score=640,
            stress=35,
            health=88,
            region="downtown",
        )
        self.db.add(self.player)
        self.db.flush()

        self._seed_macro()
        self._seed_baskets()
        self._seed_stocks()
        self._seed_player_signals()

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _seed_macro(self) -> None:
        self.db.add_all(
            [
                MacroDailyState(
                    day=1,
                    inflation_rate=Decimal("2.1"),
                    interest_rate=Decimal("4.0"),
                    unemployment_rate=Decimal("5.0"),
                    oil_index=Decimal("99.0"),
                    consumer_confidence=Decimal("58.0"),
                    supply_chain_stress=Decimal("0.5"),
                    event_headline="Calm day",
                    event_summary="Baseline conditions.",
                ),
                MacroDailyState(
                    day=2,
                    inflation_rate=Decimal("4.8"),
                    interest_rate=Decimal("5.8"),
                    unemployment_rate=Decimal("8.4"),
                    oil_index=Decimal("152.0"),
                    consumer_confidence=Decimal("33.0"),
                    supply_chain_stress=Decimal("2.2"),
                    event_headline="Stress day",
                    event_summary="High macro pressure.",
                ),
            ]
        )

    def _seed_baskets(self) -> None:
        self.db.add_all(
            [
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("10.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=1,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=2,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("11.0000"),
                    daily_change_pct=Decimal("10.0000"),
                    supply_pressure=Decimal("1.2500"),
                    demand_pressure=Decimal("1.1000"),
                ),
                BasketDailyPrice(
                    day=2,
                    basket_type=BasketType.produce,
                    price_index=Decimal("9.9000"),
                    daily_change_pct=Decimal("10.0000"),
                    supply_pressure=Decimal("1.3000"),
                    demand_pressure=Decimal("1.0500"),
                ),
            ]
        )

    def _seed_stocks(self) -> None:
        self.db.add(
            StockDailyPrice(
                day=2,
                ticker="GPTECH",
                sector="technology",
                open_price=Decimal("50.0000"),
                close_price=Decimal("48.5000"),
                daily_change_pct=Decimal("-3.0000"),
                macro_impact=Decimal("-1.2000"),
                noise_component=Decimal("0.0000"),
            )
        )
        self.db.add(
            PlayerStockHolding(
                player_id=self.player.id,
                stock_id="GPTECH",
                shares_owned=20,
                average_cost_basis=Decimal("50.0000"),
                total_cost_basis=Decimal("1000.0000"),
            )
        )

    def _seed_player_signals(self) -> None:
        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=2,
                current_job_code="retail_worker",
                skill_level=2,
                monthly_pay_xgp=Decimal("2600.00"),
                employed_flag=False,
                job_status="seeking",
                layoff_risk_pct=Decimal("18.00"),
                productivity_modifier=Decimal("0.9000"),
                last_employment_event="layoff",
            )
        )

        business_id = uuid.uuid4()
        self.db.add(
            PlayerBusiness(
                id=business_id,
                player_id=self.player.id,
                business_id="food_truck",
                region="downtown",
                business_level=1,
                reputation=50,
                created_day=1,
                is_active=True,
            )
        )
        self.db.add(
            BusinessDailyLog(
                business_id=business_id,
                player_id=self.player.id,
                day=2,
                gross_revenue_xgp=Decimal("42.0000"),
                input_cost_xgp=Decimal("35.0000"),
                fuel_cost_xgp=Decimal("8.0000"),
                spoilage_cost_xgp=Decimal("0.0000"),
                overhead_cost_xgp=Decimal("12.0000"),
                net_profit_xgp=Decimal("-13.0000"),
                demand_score=Decimal("0.8900"),
                utilization_pct=Decimal("0.5200"),
                notes_json=json.dumps({"note": "cost squeeze"}),
            )
        )

        self.db.add(
            HousingDailyLog(
                player_id=self.player.id,
                day=2,
                region="downtown",
                housing_cost_xgp=Decimal("35.00"),
                commute_pressure=Decimal("0.9000"),
                stress_delta=3,
                opportunity_modifier=Decimal("1.0900"),
                notes_json=json.dumps({"source": "seed"}),
            )
        )

        self.db.add(
            BasketConsumptionLog(
                player_id=self.player.id,
                day=2,
                essentials_spend_xgp=Decimal("8.20"),
                protein_spend_xgp=Decimal("3.20"),
                produce_spend_xgp=Decimal("2.90"),
                convenience_spend_xgp=Decimal("4.80"),
                total_spend_xgp=Decimal("19.10"),
                budget_pressure_score=Decimal("0.9200"),
                stress_spend_modifier=Decimal("1.2400"),
                nutrition_pressure_score=Decimal("0.7200"),
                notes_json=json.dumps({"seed": True}),
            )
        )

        self.db.add(
            DebtCreditLog(
                player_id=self.player.id,
                day=2,
                opening_debt_xgp=Decimal("850.00"),
                payment_due_xgp=Decimal("10.63"),
                payment_made_xgp=Decimal("0.00"),
                interest_added_xgp=Decimal("0.54"),
                ending_debt_xgp=Decimal("850.54"),
                payment_status="missed",
                opening_credit_score=640,
                credit_score_change=-8,
                ending_credit_score=632,
                delinquency_flag=True,
                notes_json=json.dumps({"seed": True}),
            )
        )

        self.db.add(
            DailySettlementLog(
                player_id=self.player.id,
                day_number=2,
                hours_before_reset=8,
                hours_after_reset=24,
                stress_before=35,
                stress_after=42,
                health_before=88,
                health_after=86,
                cash_before=Decimal("1200.0000"),
                cash_after=Decimal("1084.0000"),
                income_xgp=Decimal("0.0000"),
                expenses_xgp=Decimal("116.0000"),
                stock_pnl_xgp=Decimal("0.0000"),
                debt_paid_xgp=Decimal("0.0000"),
                health_change=-2,
                stress_change=7,
                summary_json=json.dumps(
                    {
                        "employment_status": "seeking",
                        "employment_event": "layoff",
                        "layoff_risk_pct": 18.0,
                        "total_business_profit_xgp": -13.0,
                        "housing_region": "downtown",
                        "housing_cost_xgp": 35.0,
                    }
                ),
            )
        )

    def test_global_event_generation_produces_headline_and_tags(self) -> None:
        event = generate_global_daily_event(self.db, day=2)
        self.assertTrue(event["headline"])
        self.assertTrue(event["summary"])
        self.assertIsInstance(event["macro_tags_json"], list)
        self.assertGreater(len(event["macro_tags_json"]), 0)

    def test_player_daily_brief_is_created_once_per_player_day(self) -> None:
        first = generate_player_daily_brief(self.db, str(self.player.id), day=2)
        second = generate_player_daily_brief(self.db, str(self.player.id), day=2)

        count = (
            self.db.query(DailyBriefLog)
            .filter(DailyBriefLog.player_id == self.player.id, DailyBriefLog.day == 2)
            .count()
        )

        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])
        self.assertEqual(count, 1)

    def test_macro_condition_changes_shift_headline_category(self) -> None:
        day1_event = generate_global_daily_event(self.db, day=1)
        day2_event = generate_global_daily_event(self.db, day=2)

        self.assertNotEqual(day1_event["category"], day2_event["category"])
        self.assertIn("oil_up", day2_event["macro_tags_json"])

    def test_player_impact_surfaces_debt_business_employment_housing_signals(self) -> None:
        brief = generate_player_daily_brief(self.db, str(self.player.id), day=2)

        combined_text = " ".join(
            [
                brief["summary"].lower(),
                json.dumps(brief["player_impact_json"]).lower(),
                json.dumps(brief["action_hints_json"]).lower(),
            ]
        )

        self.assertIn("debt", combined_text)
        self.assertIn("business", combined_text)
        self.assertIn("employment", combined_text)
        self.assertIn("housing", combined_text)

    def test_latest_and_history_endpoints_return_recent_briefs(self) -> None:
        generate_player_daily_brief(self.db, str(self.player.id), day=1)
        generate_player_daily_brief(self.db, str(self.player.id), day=2)

        latest = get_player_latest_daily_brief(self.db, str(self.player.id))
        history = get_player_daily_brief_history(self.db, str(self.player.id), limit=10)

        self.assertEqual(latest["day"], 2)
        self.assertGreaterEqual(history["count"], 2)
        self.assertEqual(history["briefs"][0]["day"], 2)


if __name__ == "__main__":
    unittest.main()
