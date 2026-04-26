from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql://tester:tester@localhost:5432/goldpenny_test")

from app.db.database import Base
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.enums import BasketType
from app.models.game_state import GameState
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.user import User
from app.services.business_daily_operations_service import (
    create_player_business,
    purchase_business_inventory_items,
    run_business_day,
)


def as_of(day: int) -> date:
    return date(2026, 1, 1) + timedelta(days=day - 1)


def money(value: float) -> str:
    return f"${value:,.2f}"


def build_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        future=True,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Player.__table__,
            GameState.__table__,
            PlayerBusiness.__table__,
            BusinessDailyLog.__table__,
            BusinessLedgerEntry.__table__,
            MacroDailyState.__table__,
            BasketDailyPrice.__table__,
        ],
    )
    return engine, session_local()


def seed_market_rows(db) -> None:
    db.add(GameState(current_day=1, day_status="open"))
    for day in range(1, 7):
        db.add(
            MacroDailyState(
                day=day,
                inflation_rate=Decimal("2.0"),
                interest_rate=Decimal("4.0"),
                unemployment_rate=Decimal("5.0"),
                oil_index=Decimal("100.0"),
                consumer_confidence=Decimal("55.0"),
                supply_chain_stress=Decimal("0.4"),
                event_headline=f"Stable day {day}",
                event_summary="Stable simulator macro row.",
            )
        )
        for basket_type in (
            BasketType.produce,
            BasketType.essentials,
            BasketType.protein,
            BasketType.convenience,
        ):
            db.add(
                BasketDailyPrice(
                    day=day,
                    basket_type=basket_type,
                    price_index=Decimal("100.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                )
            )
    db.commit()


def create_player(db, *, cash: Decimal) -> Player:
    user = User(
        email=f"itemized-sim-{uuid.uuid4()}@example.com",
        hashed_password="sim-password",
    )
    db.add(user)
    db.flush()

    player = Player(
        user_id=str(user.id),
        display_name="Itemized Simulator",
        cash=cash,
        stress=18,
        health=92,
        hours_available=16,
        region="suburban",
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def format_map(values: dict[str, float] | None) -> str:
    return ", ".join(
        f"{key}={value:.2f}" if abs(value - round(value)) > 1e-9 else f"{key}={value:.0f}"
        for key, value in (values or {}).items()
        if value > 0
    ) or "-"


def simulate_fruit_shop() -> None:
    engine, db = build_session()
    try:
        seed_market_rows(db)
        player = create_player(db, cash=Decimal("2500.00"))
        business = create_player_business(db, str(player.id), "fruit_shop", "suburban", 1)
        db.commit()

        purchase_business_inventory_items(
            db,
            str(player.id),
            business["business_id"],
            items=[
                {"item_id": "mango", "quantity": 30},
                {"item_id": "orange", "quantity": 30},
                {"item_id": "grape", "quantity": 20},
                {"item_id": "strawberry", "quantity": 20},
            ],
            as_of_date=as_of(1),
        )
        db.commit()

        print("Fruit shop, 5 days")
        for day in range(1, 6):
            result = run_business_day(db, business["business_id"], day)
            db.commit()
            print(
                f"day {day}: sold [{format_map(result.get('units_sold_by_item'))}] | "
                f"spoilage [{format_map(result.get('spoilage_by_item'))}] | "
                f"revenue {money(result['gross_revenue_xgp'])} | "
                f"COGS {money(result['cost_of_goods_sold_xgp'])} | "
                f"labor {money(result['labor_cost_xgp'])} | "
                f"overhead {money(result['overhead_xgp'])} | "
                f"net {money(result['net_profit_xgp'])} | "
                f"inventory left [{format_map(result.get('remaining_inventory_by_item'))}] | "
                f"warning {result.get('restock_warning') or '-'}"
            )
    finally:
        db.close()
        engine.dispose()


def simulate_food_truck() -> None:
    engine, db = build_session()
    try:
        seed_market_rows(db)
        player = create_player(db, cash=Decimal("3500.00"))
        business = create_player_business(db, str(player.id), "food_truck", "downtown", 1)
        db.commit()

        purchase_business_inventory_items(
            db,
            str(player.id),
            business["business_id"],
            items=[
                {"item_id": "bread", "quantity": 40},
                {"item_id": "rice", "quantity": 40},
                {"item_id": "chicken", "quantity": 30},
                {"item_id": "beef", "quantity": 20},
                {"item_id": "egg", "quantity": 60},
                {"item_id": "cooking_oil", "quantity": 10},
            ],
            as_of_date=as_of(1),
        )
        db.commit()

        print("\nFood truck, 5 days")
        for day in range(1, 6):
            result = run_business_day(db, business["business_id"], day)
            db.commit()
            print(
                f"day {day}: meals [{format_map(result.get('meals_sold_by_type'))}] | "
                f"ingredients [{format_map(result.get('ingredients_used_by_item'))}] | "
                f"spoilage [{format_map(result.get('spoilage_by_item'))}] | "
                f"revenue {money(result['gross_revenue_xgp'])} | "
                f"COGS {money(result['cost_of_goods_sold_xgp'])} | "
                f"labor {money(result['labor_cost_xgp'])} | "
                f"fuel {money(result['fuel_cost_xgp'])} | "
                f"net {money(result['net_profit_xgp'])} | "
                f"possible meals remaining {result.get('possible_meals_remaining', 0) or 0:.0f} | "
                f"warning {result.get('restock_warning') or '-'}"
            )
    finally:
        db.close()
        engine.dispose()


def main() -> None:
    simulate_fruit_shop()
    simulate_food_truck()


if __name__ == "__main__":
    main()
