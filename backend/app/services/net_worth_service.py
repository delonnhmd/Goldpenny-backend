"""Daily player net worth snapshot service."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.business_service import get_business_profit_snapshot
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.enums import BasketType
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

BUSINESS_VALUE_MULTIPLIER = Decimal("12.00")
BUSINESS_DAYS_WINDOW = 5
BUSINESS_VALUE_CAP_PER_ACTIVE_BUSINESS = Decimal("12000.00")


class NetWorthError(Exception):
    """Base exception for net-worth service failures."""


class NetWorthNotFoundError(NetWorthError):
    """Raised when a player or snapshot could not be found."""


class NetWorthValidationError(NetWorthError):
    """Raised for invalid net-worth request payloads."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise NetWorthNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise NetWorthNotFoundError("Player not found.")
    return player


def _latest_stock_price_for_ticker(db: Session, ticker: str, day: int) -> Decimal:
    row = (
        db.query(StockDailyPrice)
        .filter(
            StockDailyPrice.ticker == ticker,
            StockDailyPrice.day <= day,
        )
        .order_by(StockDailyPrice.day.desc(), StockDailyPrice.created_at.desc())
        .first()
    )
    if row is None:
        row = (
            db.query(StockDailyPrice)
            .filter(StockDailyPrice.ticker == ticker)
            .order_by(StockDailyPrice.day.desc(), StockDailyPrice.created_at.desc())
            .first()
        )
    if row is None:
        return Decimal("0.00")
    return _money(_d(row.close_price))


def _latest_basket_price(db: Session, basket_type: BasketType, day: int, default_price: Decimal) -> Decimal:
    row = (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day <= day,
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
    return _money(_d(row.price_index)) if row is not None else _money(default_price)


def _compute_stock_market_value(db: Session, player: Player, day: int) -> Decimal:
    holdings = (
        db.query(PlayerStockHolding)
        .filter(
            PlayerStockHolding.player_id == player.id,
            PlayerStockHolding.shares_owned > 0,
        )
        .all()
    )

    total = Decimal("0.00")
    for holding in holdings:
        shares = Decimal(str(int(holding.shares_owned or 0)))
        if shares <= Decimal("0"):
            continue
        close_price = _latest_stock_price_for_ticker(db, holding.stock_id, day)
        total += close_price * shares
    return _money(total)


def _compute_business_value_proxy(db: Session, player: Player, day: int) -> Decimal:
    logs = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day <= day,
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .limit(50)
        .all()
    )
    if not logs:
        return Decimal("0.00")

    net_by_day: dict[int, Decimal] = {}
    for row in logs:
        day_key = int(row.day)
        net_by_day[day_key] = net_by_day.get(day_key, Decimal("0.00")) + _d(row.net_profit_xgp)

    recent_days = sorted(net_by_day.keys(), reverse=True)[:BUSINESS_DAYS_WINDOW]
    if not recent_days:
        return Decimal("0.00")

    avg_recent_profit = sum((net_by_day[d] for d in recent_days), Decimal("0.00")) / Decimal(
        str(len(recent_days))
    )

    raw_value = _money(max(Decimal("0.00"), avg_recent_profit * BUSINESS_VALUE_MULTIPLIER))

    produce_unit_cost = _latest_basket_price(db, BasketType.produce, day, Decimal("9.0")) * Decimal("0.50")
    essentials_unit_cost = _latest_basket_price(db, BasketType.essentials, day, Decimal("10.0")) * Decimal("0.45")
    protein_unit_cost = _latest_basket_price(db, BasketType.protein, day, Decimal("12.0")) * Decimal("0.55")
    inventory_value = Decimal("0.00")
    active_businesses = (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.is_active.is_(True),
        )
        .all()
    )
    for business in active_businesses:
        inventory_value += _d(getattr(business, "inventory_produce_units", 0)) * produce_unit_cost
        inventory_value += _d(getattr(business, "inventory_essentials_units", 0)) * essentials_unit_cost
        inventory_value += _d(getattr(business, "inventory_protein_units", 0)) * protein_unit_cost
    inventory_value = _money(max(Decimal("0.00"), inventory_value))

    active_business_count = (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.is_active.is_(True),
        )
        .count()
    )
    cap = max(Decimal("0.00"), Decimal(str(active_business_count)) * BUSINESS_VALUE_CAP_PER_ACTIVE_BUSINESS)
    if cap <= Decimal("0.00"):
        return Decimal("0.00")
    return _money(min(raw_value + inventory_value, cap))


def _allocation_payload(
    cash_xgp: Decimal,
    savings_xgp: Decimal,
    stock_value_xgp: Decimal,
    business_value_xgp: Decimal,
    inventory_value_xgp: Decimal,
    debt_xgp: Decimal,
    total_assets_xgp: Decimal,
    net_worth_xgp: Decimal,
) -> dict:
    if total_assets_xgp > Decimal("0"):
        cash_pct = float(_q4(cash_xgp / total_assets_xgp))
        savings_pct = float(_q4(savings_xgp / total_assets_xgp))
        stocks_pct = float(_q4(stock_value_xgp / total_assets_xgp))
        business_pct = float(_q4(business_value_xgp / total_assets_xgp))
        inventory_pct = float(_q4(inventory_value_xgp / total_assets_xgp))
    else:
        cash_pct = 0.0
        savings_pct = 0.0
        stocks_pct = 0.0
        business_pct = 0.0
        inventory_pct = 0.0

    return {
        "cash": float(cash_xgp),
        "savings": float(savings_xgp),
        "stocks": float(stock_value_xgp),
        "business": float(business_value_xgp),
        "inventory": float(inventory_value_xgp),
        "debt": float(debt_xgp),
        "total_assets": float(total_assets_xgp),
        "net_worth": float(net_worth_xgp),
        "asset_mix_pct": {
            "cash_pct": cash_pct,
            "savings_pct": savings_pct,
            "stocks_pct": stocks_pct,
            "business_pct": business_pct,
            "inventory_pct": inventory_pct,
        },
    }


def _parse_json(raw: str | None) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _serialize_snapshot(row: PlayerNetWorthSnapshot, *, already_processed: bool | None = None) -> dict:
    payload = {
        "id": str(row.id),
        "player_id": str(row.player_id),
        "day": int(row.day),
        "cash_xgp": float(_money(_d(row.cash_xgp))),
        "bank_savings_xgp": float(_money(_d(row.bank_savings_xgp))),
        "stock_market_value_xgp": float(_money(_d(row.stock_market_value_xgp))),
        "business_value_xgp": float(_money(_d(row.business_value_xgp))),
        "inventory_value_xgp": float(_money(_d(getattr(row, "inventory_value_xgp", 0)))),
        "total_assets_xgp": float(_money(_d(row.total_assets_xgp))),
        "debt_xgp": float(_money(_d(row.debt_xgp))),
        "net_worth_xgp": float(_money(_d(row.net_worth_xgp))),
        "allocation_json": _parse_json(row.allocation_json) or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if already_processed is not None:
        payload["already_processed"] = bool(already_processed)
    return payload


def compute_player_net_worth_snapshot(
    db: Session,
    player_id: str | UUID,
    day: int,
    *,
    commit: bool = True,
) -> dict:
    """Compute and persist one deterministic net-worth snapshot for player/day.

    Behavior is idempotent by upsert: same player/day updates the existing row.
    """
    if day <= 0:
        raise NetWorthValidationError("day must be greater than 0.")

    try:
        player = _resolve_player(db, player_id)

        cash_xgp = _money(_d(player.cash_xgp))
        savings_xgp = _money(_d(player.bank_savings_xgp))
        debt_xgp = _money(_d(player.debt_xgp))
        stock_market_value_xgp = _compute_stock_market_value(db, player, int(day))
        business_snapshot = get_business_profit_snapshot(db=db, player_id=player.id, day_number=int(day))
        business_value_xgp = _money(_d(business_snapshot.get("business_estimated_value_xgp", 0)))
        inventory_value_xgp = _money(_d(business_snapshot.get("inventory_estimated_value_xgp", 0)))
        total_assets_xgp = _money(
            cash_xgp
            + savings_xgp
            + stock_market_value_xgp
            + business_value_xgp
            + inventory_value_xgp
        )
        net_worth_xgp = _money(total_assets_xgp - debt_xgp)

        allocation = _allocation_payload(
            cash_xgp=cash_xgp,
            savings_xgp=savings_xgp,
            stock_value_xgp=stock_market_value_xgp,
            business_value_xgp=business_value_xgp,
            inventory_value_xgp=inventory_value_xgp,
            debt_xgp=debt_xgp,
            total_assets_xgp=total_assets_xgp,
            net_worth_xgp=net_worth_xgp,
        )

        existing = (
            db.query(PlayerNetWorthSnapshot)
            .filter(
                PlayerNetWorthSnapshot.player_id == player.id,
                PlayerNetWorthSnapshot.day == int(day),
            )
            .first()
        )

        already_processed = existing is not None
        row = existing
        if row is None:
            row = PlayerNetWorthSnapshot(
                player_id=player.id,
                day=int(day),
                cash_xgp=cash_xgp,
                bank_savings_xgp=savings_xgp,
                stock_market_value_xgp=stock_market_value_xgp,
                business_value_xgp=business_value_xgp,
                inventory_value_xgp=inventory_value_xgp,
                total_assets_xgp=total_assets_xgp,
                debt_xgp=debt_xgp,
                net_worth_xgp=net_worth_xgp,
                allocation_json=json.dumps(allocation),
            )
            db.add(row)
        else:
            row.cash_xgp = cash_xgp
            row.bank_savings_xgp = savings_xgp
            row.stock_market_value_xgp = stock_market_value_xgp
            row.business_value_xgp = business_value_xgp
            row.inventory_value_xgp = inventory_value_xgp
            row.total_assets_xgp = total_assets_xgp
            row.debt_xgp = debt_xgp
            row.net_worth_xgp = net_worth_xgp
            row.allocation_json = json.dumps(allocation)

        db.flush()
        player.net_worth_xgp = net_worth_xgp

        if commit:
            db.commit()
            db.refresh(row)

        return _serialize_snapshot(row, already_processed=already_processed)
    except NetWorthError:
        if commit:
            db.rollback()
        raise
    except Exception as exc:
        if commit:
            db.rollback()
        raise NetWorthError("Unexpected net-worth snapshot error.") from exc


def get_latest_player_net_worth_snapshot(db: Session, player_id: str | UUID) -> dict:
    """Return latest net-worth snapshot row for player."""
    player = _resolve_player(db, player_id)
    row = (
        db.query(PlayerNetWorthSnapshot)
        .filter(PlayerNetWorthSnapshot.player_id == player.id)
        .order_by(PlayerNetWorthSnapshot.day.desc(), PlayerNetWorthSnapshot.created_at.desc())
        .first()
    )
    if row is None:
        raise NetWorthNotFoundError("No net-worth snapshot found for player.")
    return _serialize_snapshot(row)


def get_player_net_worth_history(db: Session, player_id: str | UUID, limit: int = 30) -> dict:
    """Return ordered net-worth snapshots for one player."""
    if limit <= 0:
        raise NetWorthValidationError("limit must be greater than 0.")

    player = _resolve_player(db, player_id)
    rows = (
        db.query(PlayerNetWorthSnapshot)
        .filter(PlayerNetWorthSnapshot.player_id == player.id)
        .order_by(PlayerNetWorthSnapshot.day.desc(), PlayerNetWorthSnapshot.created_at.desc())
        .limit(int(limit))
        .all()
    )

    return {
        "player_id": str(player.id),
        "count": len(rows),
        "snapshots": [_serialize_snapshot(row) for row in rows],
    }


def get_player_asset_allocation(db: Session, player_id: str | UUID) -> dict:
    """Return latest snapshot allocation for one player."""
    latest = get_latest_player_net_worth_snapshot(db, player_id)
    allocation = latest.get("allocation_json", {}) or {}
    return {
        "player_id": latest["player_id"],
        "day": latest["day"],
        "cash_xgp": latest["cash_xgp"],
        "bank_savings_xgp": latest["bank_savings_xgp"],
        "stock_market_value_xgp": latest["stock_market_value_xgp"],
        "business_value_xgp": latest["business_value_xgp"],
        "inventory_value_xgp": latest["inventory_value_xgp"],
        "debt_xgp": latest["debt_xgp"],
        "total_assets_xgp": latest["total_assets_xgp"],
        "net_worth_xgp": latest["net_worth_xgp"],
        "allocation_json": allocation,
    }
