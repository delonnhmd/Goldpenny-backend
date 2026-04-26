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
    get_supplier_market_items,
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
                consumer_confidence=Decimal("54.0"),
                supply_chain_stress=Decimal("0.6"),
                event_headline=f"Stable day {day}",
                event_summary="Stable simulator macro row.",
            )
        )
        db.add_all(
            [
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.produce,
                    price_index=Decimal("100.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.essentials,
                    price_index=Decimal("100.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.protein,
                    price_index=Decimal("100.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
                BasketDailyPrice(
                    day=day,
                    basket_type=BasketType.convenience,
                    price_index=Decimal("100.0000"),
                    daily_change_pct=Decimal("0.0000"),
                    supply_pressure=Decimal("1.0000"),
                    demand_pressure=Decimal("1.0000"),
                ),
            ]
        )
    db.commit()


def create_player(db) -> Player:
    user = User(
        email=f"supplier-sim-{uuid.uuid4()}@example.com",
        hashed_password="sim-password",
    )
    db.add(user)
    db.flush()

    player = Player(
        user_id=str(user.id),
        display_name="Supplier Simulator",
        cash=Decimal("1200.00"),
        stress=18,
        health=92,
        hours_available=16,
        region="suburban",
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def print_purchase(label: str, payload: dict) -> None:
    purchased = ", ".join(
        f"{item['item_id']} x{int(item['quantity'])} @ {money(item['unit_cost_xgp'])}"
        for item in payload["purchased_items"]
    )
    print(
        f"{label}: cost {money(payload['total_purchase_cost_xgp'])}, "
        f"cash left {money(payload['cash_after_xgp'])}, "
        f"inventory {payload['inventory_total_units']:.1f}u -> {purchased}"
    )


def print_day_result(day: int, payload: dict) -> None:
    print(
        f"day {day}: revenue {money(payload['gross_revenue_xgp'])}, "
        f"COGS {money(payload['cost_of_goods_sold_xgp'])}, "
        f"labor {money(payload['labor_cost_xgp'])}, "
        f"overhead {money(payload['overhead_xgp'])}, "
        f"fuel {money(payload['fuel_cost_xgp'])}, "
        f"spoilage {payload['spoilage_units']:.2f}u/{money(payload['spoilage_loss_xgp'])}, "
        f"net {money(payload['net_profit_xgp'])}, "
        f"inventory left {payload['inventory_after']:.2f}u, "
        f"days left {payload['days_of_stock_left'] if payload['days_of_stock_left'] is not None else 'n/a'}, "
        f"warning {payload['restock_warning'] or '-'}"
    )


def simulate_fruit_shop_supplier_loop() -> None:
    engine, db = build_session()
    try:
        seed_market_rows(db)
        player = create_player(db)

        supplier_catalog = get_supplier_market_items(db, "fruit_shop", as_of_date=as_of(1))
        print("supplier quotes day 1:")
        for item in supplier_catalog["items"][:2]:
            print(
                f"  {item['item_id']}: wholesale {money(item['current_wholesale_cost'])}, "
                f"retail {money(item['suggested_retail_price'])}, "
                f"basket {item['basket_link']}"
            )

        business = create_player_business(db, str(player.id), "fruit_shop", "suburban", 1)
        db.commit()

        purchase = purchase_business_inventory_items(
            db,
            str(player.id),
            business["business_id"],
            items=[
                {"item_id": "mango", "quantity": 25},
                {"item_id": "orange", "quantity": 25},
            ],
            as_of_date=as_of(1),
        )
        db.commit()
        print_purchase("initial buy", purchase)

        for day in range(1, 6):
            result = run_business_day(db, business["business_id"], day)
            db.commit()
            print_day_result(day, result)

            if day == 2:
                restock = purchase_business_inventory_items(
                    db,
                    str(player.id),
                    business["business_id"],
                    items=[
                        {"item_id": "mango", "quantity": 30},
                        {"item_id": "orange", "quantity": 30},
                    ],
                    as_of_date=as_of(3),
                )
                db.commit()
                print_purchase("restock before day 3", restock)
    finally:
        db.close()
        engine.dispose()


def main() -> None:
    simulate_fruit_shop_supplier_loop()


if __name__ == "__main__":
    main()
