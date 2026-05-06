"""Backend-known portfolio asset summary service."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.business_service import _business_startup_cost
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.enums import BasketType
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.services.stock_trading_service import StockTradingError, StockTradingService

MONEY_Q = Decimal("0.01")
UNIT_Q = Decimal("0.0001")

GENERIC_INVENTORY_BASE_COST_BY_BASKET: dict[BasketType, Decimal] = {
    BasketType.produce: Decimal("1.00"),
    BasketType.essentials: Decimal("0.75"),
    BasketType.protein: Decimal("2.25"),
}

DISTRICT_GROWTH_MODIFIERS: dict[str, Decimal] = {
    "downtown": Decimal("0.12"),
    "suburban": Decimal("0.05"),
    "industrial": Decimal("0.08"),
    "market": Decimal("0.10"),
    "default": Decimal("0.03"),
}

ADDRESS_POOLS: dict[str, tuple[str, ...]] = {
    "downtown": (
        "1203 Market Line Ave",
        "88 Riverfront Plaza",
        "410 Central Trade St",
        "726 Commerce Row",
        "51 Skyline Market Blvd",
    ),
    "suburban": (
        "240 Oak Garden Ln",
        "715 Greenfield Way",
        "332 Maple Creek Dr",
        "909 Willow Bend Rd",
        "128 Pine Orchard St",
    ),
    "industrial": (
        "600 Foundry Loop",
        "144 Warehouse Park Dr",
        "915 Rail Yard Ave",
    ),
    "market": (
        "1203 Market Line Ave",
        "88 Riverfront Plaza",
        "410 Central Trade St",
        "726 Commerce Row",
        "51 Skyline Market Blvd",
    ),
}


class PortfolioAssetServiceError(Exception):
    """Base exception for portfolio asset summary failures."""


class PortfolioAssetNotFoundError(PortfolioAssetServiceError):
    """Raised when a player cannot be resolved."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _unit(value: Decimal) -> Decimal:
    return value.quantize(UNIT_Q, rounding=ROUND_HALF_UP)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise PortfolioAssetNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise PortfolioAssetNotFoundError("Player not found.")
    return player


def _latest_known_day_for_player(db: Session, player: Player) -> int:
    if getattr(player, "last_settled_day", None) is not None and int(player.last_settled_day or 0) > 0:
        return int(player.last_settled_day)

    latest_business_day = (
        db.query(func.max(BusinessDailyLog.day))
        .filter(BusinessDailyLog.player_id == player.id)
        .scalar()
    )
    latest_basket_day = db.query(func.max(BasketDailyPrice.day)).scalar()
    return max(
        int(latest_business_day or 0),
        int(latest_basket_day or 0),
        1,
    )


def _safe_json_dict(raw: object) -> dict[str, dict[str, object]]:
    if raw is None:
        return {}
    loaded: object
    if isinstance(raw, dict):
        loaded = raw
    else:
        try:
            loaded = json.loads(str(raw))
        except Exception:
            return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        str(key).strip().lower(): value
        for key, value in loaded.items()
        if str(key).strip() and isinstance(value, dict)
    }


def _normalize_district_category(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return "default"
    if "downtown" in value or "exchange" in value or "central" in value or "commerce" in value:
        return "downtown"
    if "industrial" in value or "harbor" in value or "warehouse" in value or "rail" in value:
        return "industrial"
    if "market" in value:
        return "market"
    if "suburban" in value or "brookside" in value or "oak" in value or "willow" in value:
        return "suburban"
    return "default"


def _stable_hash(value: str) -> int:
    total = 0
    for char in value:
        total = ((total << 5) - total) + ord(char)
        total &= 0xFFFFFFFF
    return abs(total)


def build_deterministic_slot_address(slot_id: str, district: str | None) -> str:
    category = _normalize_district_category(district)
    pool = ADDRESS_POOLS.get(category) or ADDRESS_POOLS["suburban"]
    seed = _stable_hash(f"{category}:{slot_id or 'slot'}")
    return pool[seed % len(pool)]


def estimate_land_current_value(
    purchase_price: Decimal | float | int,
    demand_score: Decimal | float | int,
    district: str | None,
) -> Decimal:
    price = max(Decimal("0.00"), _money(_d(purchase_price)))
    if price <= Decimal("0.00"):
        return Decimal("0.00")
    demand_modifier = (_d(demand_score) - Decimal("50.00")) / Decimal("200.00")
    district_modifier = DISTRICT_GROWTH_MODIFIERS.get(
        _normalize_district_category(district),
        DISTRICT_GROWTH_MODIFIERS["default"],
    )
    raw_value = price * (Decimal("1.00") + demand_modifier + district_modifier)
    floor_value = price * Decimal("0.75")
    ceiling_value = price * Decimal("1.75")
    return _money(max(floor_value, min(ceiling_value, raw_value)))


def _latest_basket_index(db: Session, basket_type: BasketType, day: int) -> Decimal | None:
    row = (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day <= int(day),
        )
        .order_by(BasketDailyPrice.day.desc(), BasketDailyPrice.created_at.desc())
        .first()
    )
    if row is None:
        row = (
            db.query(BasketDailyPrice)
            .filter(BasketDailyPrice.basket_type == basket_type)
            .order_by(BasketDailyPrice.day.desc(), BasketDailyPrice.created_at.desc())
            .first()
        )
    return _d(row.price_index) if row is not None else None


def _generic_inventory_unit_cost(db: Session, basket_type: BasketType, day: int) -> Decimal:
    base_cost = GENERIC_INVENTORY_BASE_COST_BY_BASKET[basket_type]
    basket_index = _latest_basket_index(db, basket_type, day)
    if basket_index is None:
        return _money(base_cost)
    return _money(base_cost * (basket_index / Decimal("100.00")))


def calculate_inventory_value_for_business(db: Session, business: PlayerBusiness, *, day: int) -> Decimal:
    items = _safe_json_dict(getattr(business, "inventory_items_json", "{}"))
    if items:
        total = Decimal("0.00")
        for payload in items.values():
            quantity = _unit(_d(payload.get("quantity", 0)))
            avg_unit_cost = _d(payload.get("avg_unit_cost", 0))
            total += quantity * avg_unit_cost
        return _money(total)

    produce_units = _unit(_d(getattr(business, "inventory_produce_units", 0)))
    essentials_units = _unit(_d(getattr(business, "inventory_essentials_units", 0)))
    protein_units = _unit(_d(getattr(business, "inventory_protein_units", 0)))
    return _money(
        (produce_units * _generic_inventory_unit_cost(db, BasketType.produce, day))
        + (essentials_units * _generic_inventory_unit_cost(db, BasketType.essentials, day))
        + (protein_units * _generic_inventory_unit_cost(db, BasketType.protein, day))
    )


def _average_recent_profit_xgp(db: Session, business: PlayerBusiness, *, day: int, window_days: int = 7) -> Decimal:
    rows = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.business_id == business.id,
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .limit(int(window_days))
        .all()
    )
    if not rows:
        return Decimal("0.00")
    total = sum((_d(row.net_profit_xgp) for row in rows), Decimal("0.00"))
    return _money(total / Decimal(str(len(rows))))


def _latest_business_log(db: Session, business: PlayerBusiness, *, day: int) -> BusinessDailyLog | None:
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.business_id == business.id,
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .first()
    )


def estimate_business_value(
    db: Session,
    business: PlayerBusiness,
    *,
    day: int,
    inventory_value: Decimal | None = None,
) -> Decimal:
    startup_cost = _money(_business_startup_cost(business.business_type))
    inventory_component = _money(
        calculate_inventory_value_for_business(db, business, day=day)
        if inventory_value is None
        else _d(inventory_value)
    )
    average_profit = _average_recent_profit_xgp(db, business, day=day, window_days=7)
    reputation_bonus = _money(Decimal(int(getattr(business, "reputation", 0) or 0)) * Decimal("5.00"))
    profit_component = _money(max(Decimal("0.00"), average_profit * Decimal("20.00")))
    estimated_value = _money(startup_cost + inventory_component + profit_component + reputation_bonus)
    if average_profit < Decimal("0.00"):
        safe_floor = _money(startup_cost + (inventory_component * Decimal("0.50")))
        estimated_value = _money(max(estimated_value, safe_floor))
    return estimated_value


def _portfolio_profit_totals(db: Session, player: Player, *, day: int) -> tuple[Decimal, Decimal]:
    rows = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .limit(300)
        .all()
    )
    if not rows:
        return Decimal("0.00"), Decimal("0.00")

    latest_day = int(rows[0].day)
    latest_profit = Decimal("0.00")
    trailing_profit = Decimal("0.00")
    for row in rows:
        row_profit = _d(row.net_profit_xgp)
        if int(row.day) == latest_day:
            latest_profit += row_profit
        if int(row.day) >= latest_day - 6:
            trailing_profit += row_profit
    return _money(latest_profit), _money(trailing_profit)


def _safe_stock_holdings_value(db: Session, player: Player) -> Decimal:
    try:
        portfolio = StockTradingService().get_player_portfolio(db, player.id)
    except StockTradingError:
        return Decimal("0.00")
    except Exception:
        return Decimal("0.00")
    return _money(_d(portfolio.get("total_market_value", 0)))


def get_player_portfolio_asset_summary(db: Session, player_id: str | UUID) -> dict:
    player = _resolve_player(db, player_id)
    day = _latest_known_day_for_player(db, player)

    business_rows = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id)
        .order_by(PlayerBusiness.created_at.asc(), PlayerBusiness.id.asc())
        .all()
    )

    business_summaries: list[dict[str, object]] = []
    inventory_value_total = Decimal("0.00")
    business_value_total = Decimal("0.00")
    active_business_count = 0

    for business in business_rows:
        inventory_value = calculate_inventory_value_for_business(db, business, day=day)
        # V1 rule: total_assets = cash + stocks + land + business_value_without_inventory + inventory_value.
        # Pass inventory_value=0 here so business_value excludes inventory; we add it separately below.
        estimated_business_value = estimate_business_value(
            db,
            business,
            day=day,
            inventory_value=Decimal("0.00"),
        )
        average_profit = _average_recent_profit_xgp(db, business, day=day, window_days=7)
        latest_log = _latest_business_log(db, business, day=day)

        inventory_value_total += inventory_value
        business_value_total += estimated_business_value
        if bool(getattr(business, "is_active", False)):
            active_business_count += 1

        business_summaries.append(
            {
                "business_id": str(business.id),
                "business_type": str(business.business_type or ""),
                "region": str(business.region_key or business.region or ""),
                "linked_slot_id": None,
                "address": None,
                "reputation": int(getattr(business, "reputation", 0) or 0),
                "inventory_value": float(_money(inventory_value)),
                "avg_7_day_profit": float(_money(average_profit)),
                "estimated_business_value": float(_money(estimated_business_value)),
                "last_net_profit": float(_money(_d(getattr(latest_log, "net_profit_xgp", 0)))),
                "last_operated_day": (
                    int(getattr(business, "last_operated_day", 0) or 0) or None
                ),
            }
        )

    latest_business_profit, trailing_7d_business_profit = _portfolio_profit_totals(db, player, day=day)

    cash = _money(_d(getattr(player, "cash_xgp", 0)))
    debt = _money(_d(getattr(player, "debt_xgp", 0)))
    stock_holdings_value = _safe_stock_holdings_value(db, player)
    land_value = Decimal("0.00")
    total_assets_without_land = _money(
        cash
        + stock_holdings_value
        + business_value_total
        + inventory_value_total
    )
    net_worth_without_land = _money(total_assets_without_land - debt)

    return {
        "player_id": str(player.id),
        "day": int(day),
        "cash": float(cash),
        "debt": float(debt),
        "stock_holdings_value": float(stock_holdings_value),
        "land_value": float(land_value),
        "business_value": float(_money(business_value_total)),
        "inventory_value": float(_money(inventory_value_total)),
        "total_assets": float(total_assets_without_land),
        "net_worth": float(net_worth_without_land),
        "total_assets_without_sandbox_land": float(total_assets_without_land),
        "net_worth_without_sandbox_land": float(net_worth_without_land),
        "latest_business_profit": float(latest_business_profit),
        "trailing_7d_business_profit": float(trailing_7d_business_profit),
        "active_business_count": int(active_business_count),
        "owned_land": [],
        "businesses": business_summaries,
    }
