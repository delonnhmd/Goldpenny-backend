import os
import unittest
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_life_integration_productivity.db")

from app.db.database import Base
from app.engine.business_service import operate_fruit_shop
from app.engine.side_income_service import compute_rideshare_shift
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.gameplay_transaction import GameplayTransaction
from app.models.game_state import GameState
from app.models.housing_daily_log import HousingDailyLog
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_progression_state import PlayerProgressionState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.player_transaction_log import PlayerTransactionLog
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.daily_settlement_service import settle_player_day


class LifeIntegrationProductivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine, future=True)
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                User.__table__,
                Player.__table__,
                PlayerDailyState.__table__,
                PlayerBusiness.__table__,
                BusinessDailyLog.__table__,
                BusinessLedgerEntry.__table__,
                BasketDailyPrice.__table__,
                MacroDailyState.__table__,
                DailySettlementLog.__table__,
                PlayerEmploymentState.__table__,
                JobDefinitionDB.__table__,
                PlayerHousingState.__table__,
                HousingDailyLog.__table__,
                StockDailyPrice.__table__,
                PlayerNetWorthSnapshot.__table__,
                PlayerStockHolding.__table__,
                GameplayTransaction.__table__,
                GameState.__table__,
                PlayerTransactionLog.__table__,
                PlayerProgressionState.__table__,
            ],
        )
        self.db = self.SessionLocal()

        self.db.add(
            MacroDailyState(
                day=1,
                inflation_rate=Decimal("2.0"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.0"),
                oil_index=Decimal("105.0"),
                consumer_confidence=Decimal("52.0"),
                supply_chain_stress=Decimal("0.5"),
            )
        )
        self.db.add(
            BasketDailyPrice(
                day=1,
                basket_type=BasketType.produce,
                price_index=Decimal("9.0000"),
                daily_change_pct=Decimal("0.0000"),
                supply_pressure=Decimal("1.0000"),
                demand_pressure=Decimal("1.0000"),
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_player_with_fruit_shop(self, productivity: Decimal) -> tuple[Player, PlayerBusiness]:
        user = User(email=f"prod-{uuid.uuid4()}@example.com", hashed_password="hashed")
        self.db.add(user)
        self.db.flush()

        player = Player(
            user_id=str(user.id),
            cash=Decimal("2000.00"),
            stress=30,
            health=92,
            hours_available=16,
            region="suburban",
            productivity_modifier=productivity,
            base_productivity_modifier=productivity,
        )
        self.db.add(player)
        self.db.flush()

        business = PlayerBusiness(
            player_id=player.id,
            business_id="fruit_shop",
            region="suburban",
            level_key="starter",
            business_level=1,
            reputation=65,
            inventory_produce_units=Decimal("180.0000"),
            is_active=True,
        )
        self.db.add(business)
        self.db.flush()
        return player, business

    def test_rideshare_gross_income_respects_productivity_modifier(self) -> None:
        low = compute_rideshare_shift(
            player_seed="prod-side",
            day_number=1,
            region_key="suburban",
            hours_worked=4,
            oil_index=Decimal("100"),
            consumer_confidence=Decimal("50"),
            unemployment_rate=Decimal("5"),
            reliability=Decimal("0.95"),
            productivity_modifier=Decimal("0.70"),
        )
        high = compute_rideshare_shift(
            player_seed="prod-side",
            day_number=1,
            region_key="suburban",
            hours_worked=4,
            oil_index=Decimal("100"),
            consumer_confidence=Decimal("50"),
            unemployment_rate=Decimal("5"),
            reliability=Decimal("0.95"),
            productivity_modifier=Decimal("1.05"),
        )
        self.assertGreater(high["gross_income_xgp"], low["gross_income_xgp"])

    def test_business_units_sold_respects_productivity_capture(self) -> None:
        _, low_business = self._create_player_with_fruit_shop(Decimal("0.70"))
        _, high_business = self._create_player_with_fruit_shop(Decimal("1.05"))
        self.db.commit()

        low_result = operate_fruit_shop(
            db=self.db,
            business=low_business,
            as_of_date=date(2026, 1, 1),
            day_number=1,
        )
        high_result = operate_fruit_shop(
            db=self.db,
            business=high_business,
            as_of_date=date(2026, 1, 1),
            day_number=1,
        )
        self.assertGreaterEqual(high_result["units_sold"], low_result["units_sold"])
        self.assertGreaterEqual(high_result["revenue_xgp"], low_result["revenue_xgp"])

    def test_settlement_job_income_scales_with_productivity_modifier(self) -> None:
        # Seed two players with identical employment; only productivity differs.
        users = []
        players = []
        for prod in (Decimal("0.70"), Decimal("1.05")):
            user = User(email=f"settle-prod-{uuid.uuid4()}@example.com", hashed_password="hashed")
            self.db.add(user)
            self.db.flush()
            player = Player(
                user_id=str(user.id),
                cash=Decimal("1000.00"),
                debt_xgp=Decimal("0.00"),
                stress=20,
                health=95,
                hours_available=16,
                region="suburban",
                productivity_modifier=prod,
                base_productivity_modifier=prod,
            )
            self.db.add(player)
            self.db.flush()
            self.db.add(
                PlayerEmploymentState(
                    player_id=player.id,
                    day=1,
                    current_job_code="banker",
                    skill_level=1,
                    monthly_pay_xgp=Decimal("3000.00"),
                    employed_flag=True,
                    layoff_risk_pct=Decimal("0.00"),
                    productivity_modifier=Decimal("1.0000"),
                )
            )
            self.db.add(
                PlayerDailyState(
                    player_id=player.id,
                    day_number=1,
                    hours_available_start=16,
                    hours_available_end=16,
                    worked_main_job=True,
                    worked_hours=8,
                    did_settlement=False,
                    stress_start=20,
                    stress_end=20,
                    health_start=95,
                    health_end=95,
                    cash_start=Decimal("1000.0000"),
                    cash_end=Decimal("1000.0000"),
                )
            )
            users.append(user)
            players.append(player)

        self.db.commit()

        def _fake_business(*args, **kwargs):
            return {
                "business_revenue_xgp": 0.0,
                "business_cogs_xgp": 0.0,
                "business_overhead_xgp": 0.0,
                "business_spoilage_loss_xgp": 0.0,
                "business_fuel_cost_xgp": 0.0,
                "business_maintenance_cost_xgp": 0.0,
                "business_net_profit_xgp": 0.0,
                "total_business_profit_xgp": 0.0,
                "business_count_run": 0,
                "per_business_results": [],
            }

        def _fake_housing(*args, **kwargs):
            return {
                "housing_cost_xgp": 0.0,
                "region": "suburban",
                "commute_pressure": 1.0,
                "stress_delta": 0,
                "opportunity_modifier": 1.0,
                "already_processed": True,
            }

        def _fake_employment(*args, **kwargs):
            return {
                "monthly_pay_xgp_after_event": 3000.0,
                "productivity_modifier": 1.0,
                "employment_status": "employed",
                "employment_event": "none",
                "layoff_risk_pct": 0.0,
                "promotion_chance_pct": 0.0,
                "wage_adjustment_pct": 0.0,
            }

        def _fake_consumption(*args, **kwargs):
            return {
                "essentials_spend_xgp": 0.0,
                "protein_spend_xgp": 0.0,
                "produce_spend_xgp": 0.0,
                "convenience_spend_xgp": 0.0,
                "total_spend_xgp": 0.0,
                "budget_pressure_score": 0.0,
                "stress_spend_modifier": 1.0,
                "nutrition_pressure_score": 0.0,
            }

        def _fake_debt(*args, **kwargs):
            return {
                "opening_debt_xgp": 0.0,
                "payment_due_xgp": 0.0,
                "payment_made_xgp": 0.0,
                "interest_added_xgp": 0.0,
                "ending_debt_xgp": 0.0,
                "payment_status": "paid_full",
                "opening_credit_score": 650,
                "credit_score_change": 0,
                "ending_credit_score": 650,
                "delinquency_flag": False,
                "already_processed": False,
                "player_mutation_applied": False,
            }

        def _fake_networth(db, player_id, day, commit=False):
            player = db.query(Player).filter(Player.id == player_id).first()
            return {
                "net_worth_xgp": float(player.cash_xgp),
                "total_assets_xgp": float(player.cash_xgp),
                "stock_market_value_xgp": 0.0,
                "business_value_xgp": 0.0,
                "debt_xgp": float(player.debt_xgp),
                "allocation_json": {"cash_pct": 1.0},
            }

        def _fake_life(db, player_id, as_of_date=None):
            pds = (
                db.query(PlayerDailyState)
                .filter(PlayerDailyState.player_id == player_id, PlayerDailyState.day_number == 1)
                .first()
            )
            if pds is not None:
                pds.stress_start = 20
                pds.stress_end = 20
                pds.health_start = 95
                pds.health_end = 95
                pds.stress_delta = 0
                pds.health_delta = 0
                pds.total_hours_used = Decimal("15.0000")
                pds.overtime_hours = Decimal("0.0000")
                pds.sleep_hours = Decimal("8.0000")
                pds.recovery_hours = Decimal("1.0000")
                pds.productivity_modifier = Decimal("1.0000")
                pds.burnout_risk = Decimal("0.0000")
                pds.medical_event_risk = Decimal("0.0000")
                pds.medical_cost_xgp = Decimal("0.0000")
                pds.missed_work_penalty_xgp = Decimal("0.0000")
            return {
                "medical_cost_xgp": 0.0,
                "missed_work_penalty_xgp": 0.0,
                "life_summary": "ok",
                "time_budget_summary": "ok",
                "debug_meta": {},
            }

        with (
            patch("app.services.daily_settlement_service.run_player_businesses_for_day", side_effect=_fake_business),
            patch("app.services.daily_settlement_service.compute_housing_effects_for_day", side_effect=_fake_housing),
            patch("app.services.daily_settlement_service.apply_employment_progression", side_effect=_fake_employment),
            patch("app.services.daily_settlement_service.compute_player_daily_consumption", side_effect=_fake_consumption),
            patch("app.services.daily_settlement_service.apply_daily_debt_and_credit", side_effect=_fake_debt),
            patch("app.services.daily_settlement_service.compute_player_net_worth_snapshot", side_effect=_fake_networth),
            patch("app.services.daily_settlement_service.apply_life_consequences_for_player", side_effect=_fake_life),
        ):
            low = settle_player_day(self.db, str(players[0].id))
            high = settle_player_day(self.db, str(players[1].id))

        self.assertAlmostEqual(low["income_xgp"], 70.0, places=2)
        self.assertAlmostEqual(high["income_xgp"], 105.0, places=2)
        self.assertGreater(high["income_xgp"], low["income_xgp"])


if __name__ == "__main__":
    unittest.main()
