"""Compatibility wrappers for business daily operations.

Step 15 canonical logic now lives in ``app.engine.business_service``.
This module keeps existing imports stable for routes/tests that still use the
older service entrypoints.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.business_service import (
    BusinessNotFoundError,
    BusinessServiceError as BusinessOperationsError,
    BusinessValidationError,
    create_or_get_starter_business,
    day_to_date,
    get_business_daily_history,
    get_business_profit_snapshot,
    get_player_businesses,
    get_supplier_market_items,
    operate_food_truck,
    operate_fruit_shop,
    purchase_business_upgrade,
    purchase_business_inventory,
    purchase_business_inventory_items,
    run_business_operations_for_player,
    set_business_operating_mode,
)
from app.models.business_daily_log import BusinessDailyLog
from app.models.player_business import PlayerBusiness


def create_player_business(
    db: Session,
    player_id: str | UUID,
    business_type: str,
    region: str,
    tier: int = 1,
) -> dict:
    """Backward-compatible create call used by existing tests/routes."""
    level_key = "starter"
    if (business_type or "").strip().lower() == "food_truck" and int(tier) >= 2:
        level_key = "truck"
    if (business_type or "").strip().lower() == "fruit_shop":
        if int(tier) >= 4:
            level_key = "large_store"
        elif int(tier) == 3:
            level_key = "small_shop"
        elif int(tier) == 2:
            level_key = "cart"

    payload = create_or_get_starter_business(
        db=db,
        player_id=player_id,
        business_type=business_type,
        region_key=region,
        level_key=level_key,
    )
    business = db.query(PlayerBusiness).filter(PlayerBusiness.id == UUID(payload["business_id"])).first()
    if business is not None:
        business.business_level = max(1, int(tier))
        db.flush()

    return {
        "business_id": payload["business_id"],
        "player_id": payload["player_id"],
        "business_type": payload["business_type"],
        "region": payload["region_key"],
        "tier": int(tier),
        "active_flag": True,
    }


def run_business_day(db: Session, business_id: str | UUID, day: int) -> dict:
    """Backward-compatible single-business day run."""
    if int(day) <= 0:
        raise BusinessValidationError("day must be greater than 0.")

    business = db.query(PlayerBusiness).filter(PlayerBusiness.id == UUID(str(business_id))).first()
    if business is None:
        raise BusinessNotFoundError("Business not found.")

    if (business.business_type or "").strip().lower() == "fruit_shop":
        return operate_fruit_shop(db, business, day_number=int(day), as_of_date=day_to_date(int(day)))
    if (business.business_type or "").strip().lower() == "food_truck":
        return operate_food_truck(db, business, day_number=int(day), as_of_date=day_to_date(int(day)))
    raise BusinessValidationError("Unsupported business type for daily operations.")


def run_player_businesses_for_day(
    db: Session,
    player_id: str | UUID,
    day: int,
    commit: bool = True,
) -> dict:
    """Backward-compatible per-player day run."""
    if int(day) <= 0:
        raise BusinessValidationError("day must be greater than 0.")
    try:
        payload = run_business_operations_for_player(db=db, player_id=player_id, as_of_date=day_to_date(int(day)))
        if commit:
            db.commit()
        else:
            db.flush()
        return payload
    except BusinessOperationsError:
        if commit:
            db.rollback()
        raise
    except Exception as exc:
        if commit:
            db.rollback()
        raise BusinessOperationsError("Unexpected business daily operations error.") from exc


def get_player_business_summary(db: Session, player_id: str | UUID) -> dict:
    """Backward-compatible summary shape."""
    businesses = get_player_businesses(db, player_id)
    items: list[dict] = []
    for row in businesses:
        latest_log = (
            db.query(BusinessDailyLog)
            .filter(BusinessDailyLog.business_id == UUID(row["business_id"]))
            .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
            .first()
        )
        model = db.query(PlayerBusiness).filter(PlayerBusiness.id == UUID(row["business_id"])).first()
        items.append(
            {
                "business_id": row["business_id"],
                "player_id": row["player_id"],
                "business_type": row["business_type"],
                "region": row["region_key"],
                "tier": int(getattr(model, "business_level", 1) or 1),
                "active_flag": bool(row["is_active"]),
                "reputation": int(row["reputation"]),
                "cash_reserve_xgp": float(getattr(model, "cash_reserve_xgp", 0) or 0),
                "created_day": int(getattr(model, "created_day", 0) or 0),
                "last_operated_day": int(getattr(model, "last_operated_day", 0) or 0) if getattr(model, "last_operated_day", None) is not None else None,
                "latest_day": int(latest_log.day) if latest_log is not None else None,
                "latest_net_profit_xgp": float(latest_log.net_profit_xgp) if latest_log is not None else None,
            }
        )

    return {
        "player_id": str(player_id),
        "businesses": items,
    }


def get_player_business_logs(db: Session, player_id: str | UUID, limit: int = 50) -> dict:
    """Backward-compatible logs wrapper."""
    payload = get_business_daily_history(db=db, player_id=player_id, limit=limit)
    return {
        "player_id": payload["player_id"],
        "count": payload["count"],
        "logs": payload["history"],
    }


__all__ = [
    "BusinessOperationsError",
    "BusinessNotFoundError",
    "BusinessValidationError",
    "create_or_get_starter_business",
    "purchase_business_inventory",
    "set_business_operating_mode",
    "purchase_business_upgrade",
    "operate_fruit_shop",
    "operate_food_truck",
    "get_player_businesses",
    "get_business_daily_history",
    "get_business_profit_snapshot",
    "get_supplier_market_items",
    "run_business_operations_for_player",
    "purchase_business_inventory_items",
    # Backward-compatible exports
    "create_player_business",
    "run_business_day",
    "run_player_businesses_for_day",
    "get_player_business_summary",
    "get_player_business_logs",
]
