import os
import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "postgresql://goldpenny:goldpenny@localhost:5432/goldpenny_test"

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_brief_log import DailyBriefLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.gameplay_transaction import GameplayTransaction
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.basket_pricing_service import BasketPricingError
from app.services.daily_settlement_service import settle_player_day
from app.services.day_progression_service import run_player_next_day
from app.services.market_daily_update_service import (
    ensure_stock_market_day,
    generate_next_stock_day,
)


TICKER_SECTOR = {
    "GPEN": "energy",
    "GPTECH": "technology",
    "GPRETAIL": "retail",
    "GPHEALTH": "healthcare",
    "GPBANK": "finance",
    "GPAUTO": "automotive",
    "GPTRANS": "transport",
    "GPREAL": "real_estate",
    "GPDEF": "defense",
    "GPCONS": "consumer",
}


class DayProgressionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            future=True,
        )

        Base.metadata.create_all(bind=self.engine)

        self.db = self.SessionLocal()

        user = User(
            email=f"day-test-{uuid.uuid4()}@example.com",
            hashed_password="hashed-password",
        )
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=user.id,
            display_name="Day Test Player",
            cash=Decimal("1000.00"),
            debt_xgp=Decimal("100.00"),
            stress=20,
            health=95,
            hours_available=16,
            region="suburban",
        )
        self.db.add(player)
        self.db.flush()
        self.player = player

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.2"),
                interest_rate=Decimal("4.1"),
                unemployment_rate=Decimal("5.2"),
                oil_index=Decimal("101.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.5"),
                event_headline="Baseline",
                event_summary="Baseline macro row for tests.",
            )
        )

        for ticker, sector in TICKER_SECTOR.items():
            self.db.add(
                StockDailyPrice(
                    day=1,
                    ticker=ticker,
                    sector=sector,
                    open_price=Decimal("50.0000"),
                    close_price=Decimal("50.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    macro_impact=Decimal("0.0000"),
                    noise_component=Decimal("0.0000"),
                )
            )

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
                    basket_type=BasketType.protein,
                    price_index=Decimal("12.0000"),
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
                    day=1,
                    basket_type=BasketType.convenience,
                    price_index=Decimal("8.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
            ]
        )

        self.db.add(
            JobDefinitionDB(
                job_code="banker",
                title="Banker",
                base_monthly_pay_xgp=Decimal("5100.00"),
                stability_pct=Decimal("0.82"),
                growth_pct=Decimal("0.75"),
                stress_pct=Decimal("0.65"),
                promotion_threshold=100,
            )
        )

        self.db.add(
            PlayerEmploymentState(
                player_id=self.player.id,
                day=1,
                current_job_code="banker",
                skill_level=1,
                monthly_pay_xgp=Decimal("3000.00"),
                employed_flag=True,
                layoff_risk_pct=Decimal("0.00"),
                productivity_modifier=Decimal("1.0000"),
            )
        )

        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _houston_datetime(self, year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
        return pytz.timezone("America/Chicago").localize(datetime(year, month, day, hour, minute))

    def test_stock_next_day_generation_creates_10_rows(self) -> None:
        result = generate_next_stock_day(self.db)
        self.assertEqual(result["previous_market_day"], 1)
        self.assertEqual(result["new_market_day"], 2)
        self.assertEqual(result["number_of_stock_rows_created"], 10)

        day_two_count = (
            self.db.query(StockDailyPrice)
            .filter(StockDailyPrice.day == 2)
            .count()
        )
        self.assertEqual(day_two_count, 10)

    def test_stock_price_daily_move_cap_respected(self) -> None:
        generate_next_stock_day(self.db)
        rows = self.db.query(StockDailyPrice).filter(StockDailyPrice.day == 2).all()
        self.assertEqual(len(rows), 10)
        for row in rows:
            self.assertLessEqual(abs(float(row.daily_change_pct)), 6.0)

    def test_ensure_stock_market_day_is_idempotent_for_same_target_day(self) -> None:
        first = ensure_stock_market_day(self.db, 2, caller="test_same_target_first")
        second = ensure_stock_market_day(self.db, 2, caller="test_same_target_second")

        day_two_rows = (
            self.db.query(StockDailyPrice)
            .filter(StockDailyPrice.day == 2)
            .order_by(StockDailyPrice.ticker.asc())
            .all()
        )

        self.assertEqual(first["latest_market_day"], 2)
        self.assertEqual(first["generated_days"], [2])
        self.assertEqual(second["latest_market_day"], 2)
        self.assertEqual(second["generated_days"], [])
        self.assertEqual(len(day_two_rows), 10)

    def test_settle_player_day_creates_state_and_log(self) -> None:
        result = settle_player_day(self.db, str(self.player.id))
        self.assertEqual(result["settled_day"], 1)
        self.assertIn("housing_cost_xgp", result)
        self.assertIn("housing_stress_delta", result)
        self.assertIn("employment_status", result)
        self.assertIn("employment_event", result)
        self.assertIn("layoff_risk_pct", result)
        self.assertIn("opening_debt_xgp", result)
        self.assertIn("payment_due_xgp", result)
        self.assertIn("payment_made_xgp", result)
        self.assertIn("interest_added_xgp", result)
        self.assertIn("ending_debt_xgp", result)
        self.assertIn("payment_status", result)
        self.assertIn("credit_score_change", result)
        self.assertIn("ending_credit_score", result)
        self.assertIn("delinquency_flag", result)
        summary = result.get("summary_json", {})
        self.assertIn("opening_debt_xgp", summary)
        self.assertIn("payment_due_xgp", summary)
        self.assertIn("payment_made_xgp", summary)
        self.assertIn("interest_added_xgp", summary)
        self.assertIn("ending_debt_xgp", summary)
        self.assertIn("payment_status", summary)
        self.assertIn("credit_score_change", summary)
        self.assertIn("ending_credit_score", summary)
        self.assertIn("delinquency_flag", summary)

        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )
        log = (
            self.db.query(DailySettlementLog)
            .filter(
                DailySettlementLog.player_id == self.player.id,
                DailySettlementLog.day_number == 1,
            )
            .first()
        )
        self.assertIsNotNone(pds)
        self.assertTrue(bool(pds.did_settlement))
        self.assertIsNotNone(log)

    def test_player_cash_changes_after_settlement(self) -> None:
        cash_before = float(self.player.cash_xgp)
        settle_player_day(self.db, str(self.player.id))
        self.db.refresh(self.player)
        cash_after = float(self.player.cash_xgp)
        self.assertNotEqual(cash_before, cash_after)

    def test_day_progression_survives_basket_pricing_failure_with_fallback(self) -> None:
        with patch(
            "app.services.day_progression_service.compute_daily_basket_price_updates",
            side_effect=BasketPricingError("Unexpected basket pricing compute error."),
        ):
            result = run_player_next_day(self.db, str(self.player.id))

        self.assertEqual(result["settled_day"], 1)
        self.assertTrue(bool(result["basket_pricing_summary"]["degraded"]))
        self.assertEqual(result["basket_pricing_summary"]["fallback_mode"], "neutral_placeholder")
        self.assertEqual(
            result["daily_economy_brief"]["headline"],
            "Economy data is temporarily unavailable",
        )
        self.assertIn(
            "Work and core actions are still available.",
            result["daily_economy_brief"]["summary_lines"],
        )

    def test_settlement_records_daily_ledger_and_weekday_missed_shift_effects(self) -> None:
        self.player.main_job = "banker"
        self.db.commit()

        after_shift = self._houston_datetime(2026, 1, 1, 19, 0)
        with patch("app.services.daily_settlement_service.get_houston_now", return_value=after_shift):
            result = settle_player_day(self.db, str(self.player.id))
        rows = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
            )
            .all()
        )
        categories = {str(row.category) for row in rows}
        descriptions = {str(row.description) for row in rows}
        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )

        self.assertEqual(float(result.get("missed_work_penalty_xgp", 0.0)), 0.0)
        self.assertIsNotNone(pds)
        self.assertFalse(bool(pds.did_work))
        self.assertTrue(bool(getattr(pds, "missed_shift", False)))
        self.assertEqual(float(pds.missed_penalty or 0), 0.0)
        self.assertEqual(float(pds.salary_earned or 0), 0.0)
        self.assertTrue({"food", "rent", "missed_work", "health_penalty", "ride_share"}.issubset(categories))
        self.assertIn("Missed shift (Banker 10:00 AM-6:00 PM) - no salary earned", descriptions)
        self.assertIn("Health -5, Stress +6", descriptions)
        if float(result.get("weekly_gas_expense_xgp", 0.0)) > 0.0 or float(result.get("commute_fuel_cost_xgp", 0.0)) > 0.0:
            self.assertIn("gas", categories)

    def test_settlement_uses_actual_meal_spend_instead_of_daily_food_basket_charge(self) -> None:
        result = settle_player_day(self.db, str(self.player.id))
        summary = result.get("summary_json", {})
        expense_breakdown = ((summary.get("settlement_breakdown") or {}).get("expense_breakdown") or {})
        food_rows = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
                GameplayTransaction.category == "food",
            )
            .all()
        )

        self.assertEqual(float(expense_breakdown.get("food_expense", 0.0)), 6.0)
        self.assertEqual(float(summary.get("food_expense_cash_xgp", 0.0)), 6.0)
        self.assertTrue(any("dinner" in str(row.description).lower() for row in food_rows))
        self.assertFalse(any(str(row.description) == "Daily food cost" for row in food_rows))

    def test_settlement_applies_survival_penalty_when_day_has_no_activity(self) -> None:
        employment = self.db.query(PlayerEmploymentState).first()
        if employment is not None:
            employment.employed_flag = False
            employment.current_job_code = None
            employment.monthly_pay_xgp = Decimal("0.00")
        self.player.main_job = None
        self.db.commit()

        with patch(
            "app.services.daily_settlement_service.ensure_day_dinner_resolved",
            return_value=None,
        ), patch(
            "app.services.daily_settlement_service.compute_player_daily_consumption",
            return_value={
                "essentials_spend_xgp": Decimal("0.00"),
                "protein_spend_xgp": Decimal("0.00"),
                "produce_spend_xgp": Decimal("0.00"),
                "convenience_spend_xgp": Decimal("0.00"),
                "total_spend_xgp": Decimal("0.00"),
                "budget_pressure_score": Decimal("0.00"),
                "stress_spend_modifier": Decimal("0.00"),
                "nutrition_pressure_score": Decimal("0.00"),
            },
        ):
            result = settle_player_day(self.db, str(self.player.id))
        pds = (
            self.db.query(PlayerDailyState)
            .filter(
                PlayerDailyState.player_id == self.player.id,
                PlayerDailyState.day_number == 1,
            )
            .first()
        )
        penalty_rows = (
            self.db.query(GameplayTransaction)
            .filter(
                GameplayTransaction.player_id == self.player.id,
                GameplayTransaction.day == 1,
                GameplayTransaction.category == "health_penalty",
            )
            .all()
        )

        self.assertIsNotNone(pds)
        self.assertTrue(bool(getattr(pds, "survival_penalty_applied", False)))
        self.assertLess(int(result.get("health_after", self.player.health)), 95)
        self.assertGreater(int(result.get("stress_after", self.player.stress)), 20)
        self.assertTrue(
            any("No meals or activity - Health -5, Stress +4" == str(row.description) for row in penalty_rows)
        )

    def test_run_player_next_day_returns_coherent_summary(self) -> None:
        first = settle_player_day(self.db, str(self.player.id))
        self.assertEqual(first["settled_day"], 1)

        result = run_player_next_day(self.db, str(self.player.id))
        self.assertEqual(result["settled_day"], 2)
        self.assertGreaterEqual(result["market_day"], 2)
        self.assertIn("Day 2 settled", result["summary_headline"])
        self.assertIn("housing_cost_xgp", result)
        self.assertIn("housing_cost_daily_xgp", result)
        self.assertIn("utilities_cost_daily_xgp", result)
        self.assertIn("commute_hours", result)
        self.assertIn("commute_fuel_cost_xgp", result)
        self.assertIn("region_key", result)
        self.assertIn("region_stress_delta", result)
        self.assertIn("region_business_demand_modifier", result)
        self.assertIn("region_side_income_modifier", result)
        self.assertIn("networking_modifier", result)
        self.assertIn("housing_region_summary", result)
        self.assertIn("housing_region", result)
        self.assertIn("headline", result)
        self.assertIn("summary", result)
        self.assertIn("macro_tags_json", result)
        self.assertIn("player_impact_json", result)
        self.assertIn("action_hints_json", result)
        self.assertIn("economy_headline", result)
        self.assertIn("economy_summary_lines", result)
        self.assertIn("top_bottlenecks", result)
        self.assertIn("top_basket_movers", result)
        self.assertIn("top_job_changes", result)
        self.assertIn("basket_pricing_summary", result)
        self.assertIn("job_market_summary", result)
        self.assertIn("daily_economy_brief", result)
        self.assertIn("net_worth_xgp", result)
        self.assertIn("total_assets_xgp", result)
        self.assertIn("stock_market_value_xgp", result)
        self.assertIn("business_value_xgp", result)
        self.assertIn("debt_xgp", result)
        self.assertIn("allocation_json", result)

        logs = (
            self.db.query(DailySettlementLog)
            .filter(DailySettlementLog.player_id == self.player.id)
            .all()
        )
        self.assertEqual(len(logs), 2)
        snapshot_count = (
            self.db.query(PlayerNetWorthSnapshot)
            .filter(PlayerNetWorthSnapshot.player_id == self.player.id)
            .count()
        )
        self.assertEqual(snapshot_count, 2)


if __name__ == "__main__":
    unittest.main()
