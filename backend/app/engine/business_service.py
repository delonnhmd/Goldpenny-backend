"""Business system hook-in service (Step 15 MVP).

This module provides deterministic, economy-driven business outcomes for:
  - fruit_shop
  - food_truck

It is intentionally Decimal-first and idempotent per business/day.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.business_ledger_entry import BusinessLedgerEntry
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.engine.balance_config import FRUIT_MARKUP_GUARDRAILS
from app.engine.population_pressure_service import get_population_effect_multipliers
from app.services.housing_region_service import get_business_region_demand_modifier

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
UNIT_Q = Decimal("0.0001")
INT_Q = Decimal("1")

GAME_EPOCH = date(2026, 1, 1)

SUPPORTED_BUSINESS_TYPES = {"fruit_shop", "food_truck"}

MARKUP_MIN = Decimal("0.05")
MARKUP_MAX = Decimal("0.40")
MARKUP_DEFAULT = Decimal("0.20")

FRUIT_REGION_BASE_DEMAND = {
    "downtown": Decimal("34.0"),
    "suburban": Decimal("25.0"),
    "rural": Decimal("18.0"),
}
FRUIT_OVERHEAD_BY_LEVEL = {
    "starter": Decimal("8.00"),
    "cart": Decimal("12.00"),
    "small_shop": Decimal("18.00"),
    "large_store": Decimal("25.00"),
}

TRUCK_REGION_BASE_FOOT = {
    "downtown": Decimal("44.0"),
    "suburban": Decimal("32.0"),
    "rural": Decimal("22.0"),
}
TRUCK_OVERHEAD_BY_LEVEL = {
    "starter": Decimal("14.00"),
    "truck": Decimal("22.00"),
}
TRUCK_FUEL_BASE_BY_LEVEL = {
    "starter": Decimal("5.50"),
    "truck": Decimal("8.75"),
}
FRUIT_OPERATION_HOURS_BY_LEVEL = {
    "starter": Decimal("4.00"),
    "cart": Decimal("5.00"),
    "small_shop": Decimal("5.50"),
    "large_store": Decimal("6.00"),
}
TRUCK_OPERATION_HOURS_BY_LEVEL = {
    "starter": Decimal("5.00"),
    "truck": Decimal("6.50"),
}

FRUIT_OPERATING_MODES: dict[str, dict[str, Decimal]] = {
    "conservative_pricing": {
        "markup_bias": Decimal("-0.05"),
        "demand_multiplier": Decimal("1.14"),
        "elasticity_bonus": Decimal("0.12"),
        "spoilage_multiplier": Decimal("0.95"),
        "reputation_floor": Decimal("0.35"),
    },
    "normal_pricing": {
        "markup_bias": Decimal("0.00"),
        "demand_multiplier": Decimal("1.00"),
        "elasticity_bonus": Decimal("0.00"),
        "spoilage_multiplier": Decimal("1.00"),
        "reputation_floor": Decimal("0.45"),
    },
    "aggressive_markup": {
        "markup_bias": Decimal("0.06"),
        "demand_multiplier": Decimal("0.88"),
        "elasticity_bonus": Decimal("-0.18"),
        "spoilage_multiplier": Decimal("1.07"),
        "reputation_floor": Decimal("0.55"),
    },
}

FOOD_TRUCK_OPERATING_MODES: dict[str, dict[str, Decimal]] = {
    "budget_menu": {
        "ticket_multiplier": Decimal("0.84"),
        "demand_multiplier": Decimal("1.15"),
        "ingredient_usage_multiplier": Decimal("0.94"),
        "confidence_sensitivity": Decimal("0.80"),
        "reputation_sensitivity": Decimal("0.95"),
    },
    "standard_menu": {
        "ticket_multiplier": Decimal("1.00"),
        "demand_multiplier": Decimal("1.00"),
        "ingredient_usage_multiplier": Decimal("1.00"),
        "confidence_sensitivity": Decimal("1.00"),
        "reputation_sensitivity": Decimal("1.00"),
    },
    "premium_menu": {
        "ticket_multiplier": Decimal("1.18"),
        "demand_multiplier": Decimal("0.86"),
        "ingredient_usage_multiplier": Decimal("1.08"),
        "confidence_sensitivity": Decimal("1.18"),
        "reputation_sensitivity": Decimal("1.12"),
    },
}

DEFAULT_MODE_BY_TYPE = {
    "fruit_shop": "normal_pricing",
    "food_truck": "standard_menu",
}

BUSINESS_UPGRADES: dict[str, dict[str, dict[str, Decimal | str]]] = {
    "fruit_shop": {
        "better_storage": {
            "cost_xgp": Decimal("180.00"),
            "spoilage_multiplier": Decimal("0.82"),
            "label": "Better storage",
        },
        "local_supplier_relationship": {
            "cost_xgp": Decimal("220.00"),
            "cost_pressure_multiplier": Decimal("0.93"),
            "label": "Local supplier relationship",
        },
        "signage_boost": {
            "cost_xgp": Decimal("130.00"),
            "demand_multiplier": Decimal("1.09"),
            "label": "Signage boost",
        },
    },
    "food_truck": {
        "fuel_efficiency_upgrade": {
            "cost_xgp": Decimal("210.00"),
            "fuel_multiplier": Decimal("0.88"),
            "label": "Fuel efficiency upgrade",
        },
        "prep_efficiency": {
            "cost_xgp": Decimal("170.00"),
            "ingredient_usage_multiplier": Decimal("0.92"),
            "label": "Prep efficiency",
        },
        "better_location_permit": {
            "cost_xgp": Decimal("260.00"),
            "demand_multiplier": Decimal("1.10"),
            "label": "Better location permit",
        },
    },
}


class BusinessServiceError(Exception):
    """Base error for business service operations."""


class BusinessNotFoundError(BusinessServiceError):
    """Raised when player/business rows cannot be resolved."""


class BusinessValidationError(BusinessServiceError):
    """Raised when payload or operation state is invalid."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _unit(value: Decimal) -> Decimal:
    return value.quantize(UNIT_Q, rounding=ROUND_HALF_UP)


def _to_int(value: Decimal) -> int:
    return int(value.quantize(INT_Q, rounding=ROUND_HALF_UP))


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _normalize_uuid(value: str | UUID, *, label: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError as exc:
        raise BusinessNotFoundError(f"{label} not found.") from exc


def day_to_date(day: int) -> date:
    if day <= 0:
        raise BusinessValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=day - 1)


def date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    pid = _normalize_uuid(player_id, label="Player")
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise BusinessNotFoundError("Player not found.")
    return row


def _resolve_business(
    db: Session,
    player: Player,
    business_id: str | UUID,
    *,
    must_be_active: bool = True,
) -> PlayerBusiness:
    bid = _normalize_uuid(business_id, label="Business")
    row = (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.id == bid,
            PlayerBusiness.player_id == player.id,
        )
        .first()
    )
    if row is None:
        raise BusinessNotFoundError("Business not found.")
    if must_be_active and not bool(row.is_active):
        raise BusinessValidationError("Business is not active.")
    return row


def _resolve_day_and_date(
    as_of_date: date | None = None,
    *,
    day_number: int | None = None,
) -> tuple[int, date]:
    if day_number is not None:
        if int(day_number) <= 0:
            raise BusinessValidationError("day must be greater than 0.")
        day = int(day_number)
        return day, day_to_date(day)
    if as_of_date is None:
        raise BusinessValidationError("as_of_date or day_number is required.")
    day = date_to_day(as_of_date)
    if day <= 0:
        raise BusinessValidationError("as_of_date must be on or after game epoch.")
    return day, as_of_date


def _latest_macro_for_day(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= int(day))
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )
    if row is not None:
        return row
    return db.query(MacroDailyState).order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc()).first()


def _latest_basket_price(db: Session, basket_type: BasketType, day: int, default_price: Decimal) -> Decimal:
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
    return _q4(_d(row.price_index)) if row is not None else _q4(default_price)


def _business_level_key(business: PlayerBusiness) -> str:
    raw = (getattr(business, "level_key", "") or "").strip().lower()
    if raw:
        return raw
    lvl = int(getattr(business, "business_level", 1) or 1)
    if lvl >= 4:
        return "large_store"
    if lvl == 3:
        return "small_shop"
    if lvl == 2:
        return "truck"
    return "starter"


def _decode_upgrade_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(v).strip().lower() for v in raw if str(v).strip()]
    try:
        loaded = json.loads(str(raw))
        if isinstance(loaded, list):
            return [str(v).strip().lower() for v in loaded if str(v).strip()]
    except Exception:
        pass
    return []


def _business_upgrades(business: PlayerBusiness) -> list[str]:
    values = sorted(set(_decode_upgrade_list(getattr(business, "upgrades_json", "[]"))))
    return values


def _set_business_upgrades(business: PlayerBusiness, upgrades: list[str]) -> None:
    normalized = sorted(set(str(v).strip().lower() for v in upgrades if str(v).strip()))
    business.upgrades_json = json.dumps(normalized, sort_keys=True)


def _mode_map_for_type(business_type: str) -> dict[str, dict[str, Decimal]]:
    normalized = (business_type or "").strip().lower()
    if normalized == "fruit_shop":
        return FRUIT_OPERATING_MODES
    if normalized == "food_truck":
        return FOOD_TRUCK_OPERATING_MODES
    return {}


def _resolve_operating_mode(business: PlayerBusiness) -> str:
    btype = (business.business_type or "").strip().lower()
    mode_map = _mode_map_for_type(btype)
    default_mode = DEFAULT_MODE_BY_TYPE.get(btype, "")
    mode = (getattr(business, "operating_mode", "") or "").strip().lower() or default_mode
    if mode not in mode_map:
        mode = default_mode
    return mode


def _productivity_capture_factor(player: Player) -> Decimal:
    productivity_modifier = _clamp(
        _d(getattr(player, "productivity_modifier", 1.0)),
        Decimal("0.70"),
        Decimal("1.05"),
    )
    business_risk_penalty = _clamp(
        _d(getattr(player, "business_risk_penalty", 0.0)),
        Decimal("0.00"),
        Decimal("0.35"),
    )
    financial_access_factor = _clamp(
        Decimal("1.00") - (business_risk_penalty * Decimal("0.40")),
        Decimal("0.86"),
        Decimal("1.00"),
    )
    return _q4(
        _clamp(
            (Decimal("1.00") + ((productivity_modifier - Decimal("1.00")) * Decimal("0.45"))) * financial_access_factor,
            Decimal("0.84"),
            Decimal("1.03"),
        )
    )


def _operation_hours_for_business(business: PlayerBusiness) -> Decimal:
    level = _business_level_key(business)
    btype = (business.business_type or "").strip().lower()
    if btype == "fruit_shop":
        return FRUIT_OPERATION_HOURS_BY_LEVEL.get(level, Decimal("4.00"))
    if btype == "food_truck":
        return TRUCK_OPERATION_HOURS_BY_LEVEL.get(level, Decimal("5.00"))
    return Decimal("0.00")


def _deterministic_ratio(seed: str) -> Decimal:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return Decimal(n) / Decimal((16**16) - 1)


def _serialize_operation_result(log: BusinessDailyLog, *, already_processed: bool = False) -> dict:
    as_of = log.as_of_date.isoformat() if log.as_of_date else None
    try:
        debug_meta = json.loads(log.debug_json or log.notes_json or "{}")
    except Exception:
        debug_meta = {}
    return {
        "business_id": str(log.business_id),
        "business_type": log.business_type,
        "as_of_date": as_of,
        "day": int(log.day),
        "region_key": log.region_key,
        "revenue_xgp": float(_money(_d(log.revenue_xgp))),
        "cogs_xgp": float(_money(_d(log.cogs_xgp))),
        "overhead_xgp": float(_money(_d(log.overhead_xgp))),
        "spoilage_loss_xgp": float(_money(_d(log.spoilage_loss_xgp))),
        "fuel_cost_xgp": float(_money(_d(log.fuel_cost_xgp))),
        "maintenance_cost_xgp": float(_money(_d(log.maintenance_cost_xgp))),
        "net_profit_xgp": float(_money(_d(log.net_profit_xgp))),
        "units_sold": int(log.units_sold or 0),
        "inventory_before": float(_unit(_d(log.inventory_start_units))),
        "inventory_after": float(_unit(_d(log.inventory_end_units))),
        "demand_signal": float(_q4(_d(log.demand_signal))),
        "reputation_before": int(log.reputation_before or 0),
        "reputation_after": int(log.reputation_after or 0),
        "operating_mode": debug_meta.get("operating_mode"),
        "upgrades": debug_meta.get("upgrades", []),
        "debug_meta": debug_meta,
        "already_processed": bool(already_processed),
        "status": "already_processed" if already_processed else "ran",
    }


def _existing_log_for_day(db: Session, business_id: UUID, day: int) -> BusinessDailyLog | None:
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.business_id == business_id,
            BusinessDailyLog.day == int(day),
        )
        .order_by(BusinessDailyLog.created_at.desc())
        .first()
    )


def _upsert_business_daily_log(
    db: Session,
    *,
    business: PlayerBusiness,
    player: Player,
    day: int,
    as_of_date: date,
    business_type: str,
    region_key: str,
    revenue_xgp: Decimal,
    cogs_xgp: Decimal,
    overhead_xgp: Decimal,
    spoilage_loss_xgp: Decimal,
    fuel_cost_xgp: Decimal,
    maintenance_cost_xgp: Decimal,
    net_profit_xgp: Decimal,
    units_sold: int,
    inventory_start_units: Decimal,
    inventory_end_units: Decimal,
    demand_signal: Decimal,
    utilization_pct: Decimal,
    reputation_before: int,
    reputation_after: int,
    debug_meta: dict,
) -> BusinessDailyLog:
    existing = _existing_log_for_day(db, business.id, day)
    if existing is not None:
        return existing

    payload_json = json.dumps(debug_meta, sort_keys=True)
    row = BusinessDailyLog(
        business_id=business.id,
        player_id=player.id,
        day=int(day),
        as_of_date=as_of_date,
        business_type=business_type,
        region_key=region_key,
        gross_revenue_xgp=_money(revenue_xgp),
        input_cost_xgp=_money(cogs_xgp),
        fuel_cost_xgp=_money(fuel_cost_xgp),
        maintenance_cost_xgp=_money(maintenance_cost_xgp),
        spoilage_cost_xgp=_money(spoilage_loss_xgp),
        overhead_cost_xgp=_money(overhead_xgp),
        net_profit_xgp=_money(net_profit_xgp),
        units_sold=int(max(0, units_sold)),
        inventory_start_units=_unit(max(Decimal("0"), inventory_start_units)),
        inventory_end_units=_unit(max(Decimal("0"), inventory_end_units)),
        demand_signal=_q4(max(Decimal("0"), demand_signal)),
        demand_score=_q4(max(Decimal("0"), demand_signal)),
        utilization_pct=_q4(max(Decimal("0"), utilization_pct)),
        reputation_before=int(reputation_before),
        reputation_after=int(reputation_after),
        debug_json=payload_json,
        notes_json=payload_json,
    )
    db.add(row)
    db.flush()

    ledger_rows = [
        BusinessLedgerEntry(
            business_id=business.id,
            day=int(day),
            category="revenue",
            amount_xgp=_money(revenue_xgp),
            direction="inflow",
            memo=f"{business_type} daily revenue",
        ),
        BusinessLedgerEntry(
            business_id=business.id,
            day=int(day),
            category="input_cost",
            amount_xgp=_money(cogs_xgp),
            direction="outflow",
            memo=f"{business_type} daily cogs",
        ),
        BusinessLedgerEntry(
            business_id=business.id,
            day=int(day),
            category="overhead_cost",
            amount_xgp=_money(overhead_xgp),
            direction="outflow",
            memo=f"{business_type} daily overhead",
        ),
    ]
    if _money(fuel_cost_xgp) > Decimal("0.00"):
        ledger_rows.append(
            BusinessLedgerEntry(
                business_id=business.id,
                day=int(day),
                category="fuel_cost",
                amount_xgp=_money(fuel_cost_xgp),
                direction="outflow",
                memo=f"{business_type} daily fuel",
            )
        )
    if _money(spoilage_loss_xgp) > Decimal("0.00"):
        ledger_rows.append(
            BusinessLedgerEntry(
                business_id=business.id,
                day=int(day),
                category="spoilage_cost",
                amount_xgp=_money(spoilage_loss_xgp),
                direction="outflow",
                memo=f"{business_type} spoilage",
            )
        )
    if _money(maintenance_cost_xgp) > Decimal("0.00"):
        ledger_rows.append(
            BusinessLedgerEntry(
                business_id=business.id,
                day=int(day),
                category="maintenance_cost",
                amount_xgp=_money(maintenance_cost_xgp),
                direction="outflow",
                memo=f"{business_type} maintenance",
            )
        )
    for entry in ledger_rows:
        db.add(entry)

    db.flush()
    db.refresh(row)
    return row


def _ensure_supported_business_type(business_type: str) -> str:
    normalized = (business_type or "").strip().lower()
    if normalized not in SUPPORTED_BUSINESS_TYPES:
        raise BusinessValidationError("Unsupported business_type. Use fruit_shop or food_truck.")
    return normalized


def create_or_get_starter_business(
    db: Session,
    player_id: str | UUID,
    business_type: str,
    *,
    region_key: str | None = None,
    business_name: str | None = None,
    level_key: str = "starter",
) -> dict:
    """Create a starter business if missing, otherwise return existing active row."""
    player = _resolve_player(db, player_id)
    normalized_type = _ensure_supported_business_type(business_type)
    region = (region_key or player.region or "suburban").strip().lower()

    existing = (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.business_id == normalized_type,
            PlayerBusiness.is_active.is_(True),
        )
        .order_by(PlayerBusiness.created_at.asc())
        .first()
    )
    if existing is not None:
        mode = _resolve_operating_mode(existing)
        return {
            "created": False,
            "business_id": str(existing.id),
            "player_id": str(existing.player_id),
            "business_type": existing.business_type,
            "business_name": existing.business_name,
            "region_key": existing.region_key,
            "level": existing.level,
            "reputation": int(existing.reputation or 0),
            "inventory_produce_units": float(_unit(_d(existing.inventory_produce_units))),
            "inventory_essentials_units": float(_unit(_d(existing.inventory_essentials_units))),
            "inventory_protein_units": float(_unit(_d(existing.inventory_protein_units))),
            "operating_mode": mode,
            "upgrades": _business_upgrades(existing),
        }

    default_mode = DEFAULT_MODE_BY_TYPE.get(normalized_type)
    row = PlayerBusiness(
        player_id=player.id,
        business_id=normalized_type,
        business_name=(business_name or "").strip() or None,
        region=region,
        level_key=(level_key or "starter").strip().lower(),
        business_level=1,
        reputation=50,
        cash_invested_xgp=_money(Decimal("0")),
        inventory_produce_units=_unit(Decimal("0")),
        inventory_essentials_units=_unit(Decimal("0")),
        inventory_protein_units=_unit(Decimal("0")),
        fruit_markup_pct=_q4(MARKUP_DEFAULT),
        operating_mode=default_mode,
        upgrades_json="[]",
        is_active=True,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return {
        "created": True,
        "business_id": str(row.id),
        "player_id": str(row.player_id),
        "business_type": row.business_type,
        "business_name": row.business_name,
        "region_key": row.region_key,
        "level": row.level,
        "reputation": int(row.reputation or 0),
        "inventory_produce_units": float(_unit(_d(row.inventory_produce_units))),
        "inventory_essentials_units": float(_unit(_d(row.inventory_essentials_units))),
        "inventory_protein_units": float(_unit(_d(row.inventory_protein_units))),
        "operating_mode": _resolve_operating_mode(row),
        "upgrades": _business_upgrades(row),
    }


def purchase_business_inventory(
    db: Session,
    player_id: str | UUID,
    business_id: str | UUID,
    *,
    produce_units: Decimal | int | float = 0,
    essentials_units: Decimal | int | float = 0,
    protein_units: Decimal | int | float = 0,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Purchase inventory for a player-owned business with cash validation."""
    player = _resolve_player(db, player_id)
    business = _resolve_business(db, player, business_id, must_be_active=True)

    day, _ = _resolve_day_and_date(as_of_date, day_number=day_number) if (as_of_date or day_number) else (1, GAME_EPOCH)
    p_units = _unit(max(Decimal("0"), _d(produce_units)))
    e_units = _unit(max(Decimal("0"), _d(essentials_units)))
    pr_units = _unit(max(Decimal("0"), _d(protein_units)))
    if p_units <= 0 and e_units <= 0 and pr_units <= 0:
        raise BusinessValidationError("Purchase quantities must be greater than zero.")

    produce_price = _latest_basket_price(db, BasketType.produce, day, Decimal("9.0"))
    essentials_price = _latest_basket_price(db, BasketType.essentials, day, Decimal("10.0"))
    protein_price = _latest_basket_price(db, BasketType.protein, day, Decimal("12.0"))

    produce_unit_cost = _q4(produce_price * Decimal("0.50"))
    essentials_unit_cost = _q4(essentials_price * Decimal("0.45"))
    protein_unit_cost = _q4(protein_price * Decimal("0.55"))

    total_cost = _money(
        (p_units * produce_unit_cost)
        + (e_units * essentials_unit_cost)
        + (pr_units * protein_unit_cost)
    )
    cash_before = _money(_d(player.cash_xgp))
    if cash_before < total_cost:
        raise BusinessValidationError(
            f"Not enough cash for inventory purchase. Need {total_cost:.2f} XGP, have {cash_before:.2f} XGP."
        )

    business.inventory_produce_units = _unit(_d(business.inventory_produce_units) + p_units)
    business.inventory_essentials_units = _unit(_d(business.inventory_essentials_units) + e_units)
    business.inventory_protein_units = _unit(_d(business.inventory_protein_units) + pr_units)
    business.cash_invested_xgp = _money(_d(business.cash_invested_xgp) + total_cost)

    cash_after = _money(cash_before - total_cost)
    player.cash_xgp = cash_after
    db.flush()

    return {
        "player_id": str(player.id),
        "business_id": str(business.id),
        "business_type": business.business_type,
        "day": int(day),
        "purchase_cost_xgp": float(total_cost),
        "cash_before_xgp": float(cash_before),
        "cash_after_xgp": float(cash_after),
        "inventory_produce_units": float(_unit(_d(business.inventory_produce_units))),
        "inventory_essentials_units": float(_unit(_d(business.inventory_essentials_units))),
        "inventory_protein_units": float(_unit(_d(business.inventory_protein_units))),
    }


def set_business_operating_mode(
    db: Session,
    player_id: str | UUID,
    business_id: str | UUID,
    *,
    mode_key: str,
) -> dict:
    """Set a business operating mode with bounded, type-specific validation."""
    player = _resolve_player(db, player_id)
    business = _resolve_business(db, player, business_id, must_be_active=True)
    business_type = (business.business_type or "").strip().lower()
    mode_map = _mode_map_for_type(business_type)
    normalized_mode = (mode_key or "").strip().lower()
    if normalized_mode not in mode_map:
        raise BusinessValidationError(
            f"Invalid mode for {business_type}. Allowed: {sorted(mode_map.keys())}"
        )

    old_mode = _resolve_operating_mode(business)
    business.operating_mode = normalized_mode
    db.flush()
    return {
        "player_id": str(player.id),
        "business_id": str(business.id),
        "business_type": business_type,
        "old_mode": old_mode,
        "new_mode": normalized_mode,
        "expected_tradeoffs": mode_map[normalized_mode],
        "debug_meta": {
            "allowed_modes": sorted(mode_map.keys()),
            "upgrades": _business_upgrades(business),
        },
    }


def purchase_business_upgrade(
    db: Session,
    player_id: str | UUID,
    business_id: str | UUID,
    *,
    upgrade_key: str,
) -> dict:
    """Purchase and apply a bounded mini-upgrade for fruit shop or food truck."""
    player = _resolve_player(db, player_id)
    business = _resolve_business(db, player, business_id, must_be_active=True)
    business_type = (business.business_type or "").strip().lower()
    upgrade_map = BUSINESS_UPGRADES.get(business_type, {})
    normalized_upgrade = (upgrade_key or "").strip().lower()
    if normalized_upgrade not in upgrade_map:
        raise BusinessValidationError(
            f"Invalid upgrade for {business_type}. Allowed: {sorted(upgrade_map.keys())}"
        )

    current_upgrades = _business_upgrades(business)
    if normalized_upgrade in current_upgrades:
        raise BusinessValidationError("Upgrade already purchased for this business.")

    spec = upgrade_map[normalized_upgrade]
    cost_xgp = _money(_d(spec.get("cost_xgp", 0)))
    cash_before = _money(_d(player.cash_xgp))
    if cash_before < cost_xgp:
        raise BusinessValidationError(
            f"Not enough cash for upgrade. Need {cost_xgp:.2f} XGP, have {cash_before:.2f} XGP."
        )

    player.cash_xgp = _money(cash_before - cost_xgp)
    business.cash_invested_xgp = _money(_d(business.cash_invested_xgp) + cost_xgp)
    current_upgrades.append(normalized_upgrade)
    _set_business_upgrades(business, current_upgrades)
    db.flush()

    expected_effects = {
        k: float(_q4(_d(v))) if isinstance(v, Decimal) else v
        for k, v in spec.items()
        if k not in {"cost_xgp", "label"}
    }
    return {
        "player_id": str(player.id),
        "business_id": str(business.id),
        "upgrade_key": normalized_upgrade,
        "cost_xgp": float(cost_xgp),
        "applied": True,
        "expected_effects": expected_effects,
        "debug_meta": {
            "business_type": business_type,
            "cash_before_xgp": float(cash_before),
            "cash_after_xgp": float(_money(_d(player.cash_xgp))),
            "active_upgrades": _business_upgrades(business),
        },
    }


def operate_fruit_shop(
    db: Session,
    business: PlayerBusiness,
    *,
    as_of_date: date | None = None,
    day_number: int | None = None,
    markup_pct: Decimal | float | int | None = None,
    operating_mode: str | None = None,
) -> dict:
    """Operate one fruit shop day using basket price, confidence, demand and spoilage."""
    if (business.business_type or "").strip().lower() != "fruit_shop":
        raise BusinessValidationError("operate_fruit_shop requires business_type='fruit_shop'.")
    player = _resolve_player(db, business.player_id)
    day, op_date = _resolve_day_and_date(as_of_date, day_number=day_number)

    existing = _existing_log_for_day(db, business.id, day)
    if existing is not None:
        return _serialize_operation_result(existing, already_processed=True)

    markup = _q4(_d(markup_pct) if markup_pct is not None else _d(business.fruit_markup_pct or MARKUP_DEFAULT))
    markup = _clamp(markup, MARKUP_MIN, MARKUP_MAX)
    business.fruit_markup_pct = markup
    if operating_mode is not None:
        requested_mode = (operating_mode or "").strip().lower()
        if requested_mode not in FRUIT_OPERATING_MODES:
            raise BusinessValidationError(
                f"Invalid fruit_shop operating mode. Allowed: {sorted(FRUIT_OPERATING_MODES.keys())}"
            )
        business.operating_mode = requested_mode
    mode_key = _resolve_operating_mode(business)
    mode_cfg = FRUIT_OPERATING_MODES[mode_key]
    upgrades = _business_upgrades(business)
    markup_effective = _clamp(markup + mode_cfg["markup_bias"], MARKUP_MIN, MARKUP_MAX)

    spoilage_upgrade_mult = Decimal("1.00")
    supplier_cost_mult = Decimal("1.00")
    signage_demand_mult = Decimal("1.00")
    if "better_storage" in upgrades:
        spoilage_upgrade_mult = _clamp(
            _d(BUSINESS_UPGRADES["fruit_shop"]["better_storage"].get("spoilage_multiplier", Decimal("1.0"))),
            Decimal("0.70"),
            Decimal("1.00"),
        )
    if "local_supplier_relationship" in upgrades:
        supplier_cost_mult = _clamp(
            _d(BUSINESS_UPGRADES["fruit_shop"]["local_supplier_relationship"].get("cost_pressure_multiplier", Decimal("1.0"))),
            Decimal("0.85"),
            Decimal("1.00"),
        )
    if "signage_boost" in upgrades:
        signage_demand_mult = _clamp(
            _d(BUSINESS_UPGRADES["fruit_shop"]["signage_boost"].get("demand_multiplier", Decimal("1.0"))),
            Decimal("1.00"),
            Decimal("1.15"),
        )

    macro = _latest_macro_for_day(db, day)
    confidence = _d(getattr(macro, "consumer_confidence", 50))
    supply_stress = _d(getattr(macro, "supply_chain_stress", 0))
    supply_stress_norm = _clamp(supply_stress * Decimal("20"), Decimal("0"), Decimal("100"))

    produce_price = _latest_basket_price(db, BasketType.produce, day, Decimal("9.0"))
    wholesale_unit_cost = _q4(produce_price * Decimal("0.50") * supplier_cost_mult)
    market_reference_price = _q4(wholesale_unit_cost * Decimal("1.18"))
    sell_price = _q4(wholesale_unit_cost * (Decimal("1.00") + markup_effective))

    region = (business.region_key or "suburban").strip().lower()
    base_region_demand = FRUIT_REGION_BASE_DEMAND.get(region, Decimal("25.0"))
    weekend_bonus = Decimal("1.20") if op_date.weekday() >= 5 else Decimal("1.00")
    reputation_before = int(_clamp(_d(business.reputation or 50), Decimal("0"), Decimal("100")))
    reputation_bonus = Decimal("1.00") + (Decimal(reputation_before) / Decimal("200"))
    confidence_multiplier = Decimal("1.00") + (Decimal("0.02") * (confidence - Decimal("50")))
    affordability_multiplier = _clamp(
        Decimal("1.20") - (produce_price / Decimal("25.0")),
        Decimal("0.55"),
        Decimal("1.15"),
    )

    try:
        region_demand_modifier = _q4(get_business_region_demand_modifier(db, player.id, "fruit_shop"))
    except Exception:
        region_demand_modifier = Decimal("1.0000")
    population_demand_mult = Decimal("1.0000")
    competition_penalty = Decimal("0.0000")
    try:
        population_effects = get_population_effect_multipliers(
            db=db,
            region_key=region,
            as_of_date=op_date,
            player_id=player.id,
        )
        population_demand_mult = _q4(_d(population_effects.get("business_demand_multiplier", 1)))
        competition_penalty = _q4(_d(population_effects.get("business_competition_penalty", 0)))
    except Exception:
        population_effects = {}
        population_demand_mult = Decimal("1.0000")
        competition_penalty = Decimal("0.0000")
    demand_share_factor = _clamp(Decimal("1.00") - (competition_penalty * Decimal("0.55")), Decimal("0.75"), Decimal("1.00"))

    demand = _q4(
        _clamp(
            base_region_demand
            * _clamp(confidence_multiplier, Decimal("0.30"), Decimal("1.70"))
            * affordability_multiplier
            * weekend_bonus
            * reputation_bonus
            * region_demand_modifier
            * population_demand_mult
            * demand_share_factor,
            Decimal("0"),
            Decimal("120"),
        )
    )
    demand = _q4(
        _clamp(
            demand * mode_cfg["demand_multiplier"] * signage_demand_mult,
            Decimal("0"),
            Decimal("140"),
        )
    )

    elasticity = _q4(
        _clamp(
            Decimal("1.2") - (Decimal("1.5") * ((sell_price / max(market_reference_price, Decimal("0.0001"))) - Decimal("1"))),
            Decimal("0.4"),
            Decimal("1.2"),
        )
    )
    elasticity = _q4(_clamp(elasticity + mode_cfg["elasticity_bonus"], Decimal("0.30"), Decimal("1.25")))
    # Step 21 anti-exploit guardrail: extreme markup gets extra elasticity
    # pressure so high-markup loops cannot dominate indefinitely.
    extreme_threshold = _d(FRUIT_MARKUP_GUARDRAILS["extreme_markup_threshold"])
    extreme_markup_penalty = Decimal("0.0")
    if markup > extreme_threshold:
        threshold_span = max(Decimal("0.01"), MARKUP_MAX - extreme_threshold)
        extreme_markup_penalty = _clamp(
            ((markup - extreme_threshold) / threshold_span)
            * _d(FRUIT_MARKUP_GUARDRAILS["max_extra_elasticity_penalty"]),
            Decimal("0.0"),
            _d(FRUIT_MARKUP_GUARDRAILS["max_extra_elasticity_penalty"]),
        )
    elasticity_guard_factor = _clamp(Decimal("1.0") - extreme_markup_penalty, Decimal("0.55"), Decimal("1.00"))
    elasticity = _q4(_clamp(elasticity * elasticity_guard_factor, Decimal("0.35"), Decimal("1.20")))

    productivity_capture_factor = _productivity_capture_factor(player)
    inventory_start = _unit(_d(business.inventory_produce_units))
    sold_units = min(max(_to_int(demand * elasticity * productivity_capture_factor), 0), _to_int(inventory_start))
    if extreme_markup_penalty > Decimal("0.0"):
        extra_units_penalty = _clamp(
            extreme_markup_penalty,
            Decimal("0.0"),
            _d(FRUIT_MARKUP_GUARDRAILS["max_extra_sold_units_penalty"]),
        )
        sold_units = min(
            sold_units,
            max(0, _to_int(Decimal(str(sold_units)) * (Decimal("1.0") - extra_units_penalty))),
        )
    sold_units_d = Decimal(str(sold_units))

    revenue_xgp = _money(sell_price * sold_units_d)
    cogs_xgp = _money(wholesale_unit_cost * sold_units_d)

    remaining_after_sales = _unit(max(Decimal("0"), inventory_start - sold_units_d))
    spoil_rate = _q4(
        _clamp(
            Decimal("0.05") + (Decimal("0.01") * (supply_stress_norm / Decimal("20"))),
            Decimal("0.01"),
            Decimal("0.15"),
        )
    )
    spoil_rate = _q4(_clamp(spoil_rate * mode_cfg["spoilage_multiplier"] * spoilage_upgrade_mult, Decimal("0.005"), Decimal("0.18")))
    spoil_units = min(_to_int(remaining_after_sales * spoil_rate), _to_int(remaining_after_sales))
    spoil_units_d = Decimal(str(max(0, spoil_units)))
    spoilage_loss_xgp = _money(wholesale_unit_cost * spoil_units_d)

    inventory_end = _unit(max(Decimal("0"), remaining_after_sales - spoil_units_d))
    overhead_xgp = _money(FRUIT_OVERHEAD_BY_LEVEL.get(_business_level_key(business), Decimal("8.00")))

    net_profit_xgp = _money(revenue_xgp - cogs_xgp - overhead_xgp - spoilage_loss_xgp)

    sell_through = _q4(
        (sold_units_d / inventory_start) if inventory_start > 0 else Decimal("0.0")
    )
    rep_delta = 0
    reputation_floor = _clamp(mode_cfg["reputation_floor"], Decimal("0.25"), Decimal("0.70"))
    if net_profit_xgp > 0 and sell_through >= max(Decimal("0.40"), reputation_floor) and markup_effective <= Decimal("0.32"):
        rep_delta = 1
    if (
        sell_through < Decimal("0.35")
        or markup_effective >= Decimal("0.38")
        or net_profit_xgp < (_money(overhead_xgp) * Decimal("-0.5"))
    ):
        rep_delta -= 1
    reputation_after = int(_clamp(Decimal(reputation_before + rep_delta), Decimal("0"), Decimal("100")))

    business.inventory_produce_units = inventory_end
    business.reputation = reputation_after
    business.last_operated_day = day
    business.last_operated_on = op_date

    debug_meta = {
        "wholesale_unit_cost": float(_q4(wholesale_unit_cost)),
        "market_reference_price": float(_q4(market_reference_price)),
        "sell_price": float(_q4(sell_price)),
        "markup_pct": float(_q4(markup)),
        "effective_markup_pct": float(_q4(markup_effective)),
        "operating_mode": mode_key,
        "elasticity": float(_q4(elasticity)),
        "elasticity_guard_factor": float(_q4(elasticity_guard_factor)),
        "extreme_markup_penalty": float(_q4(extreme_markup_penalty)),
        "weekend_bonus": float(_q4(weekend_bonus)),
        "reputation_bonus": float(_q4(reputation_bonus)),
        "confidence_multiplier": float(_q4(_clamp(confidence_multiplier, Decimal("0.30"), Decimal("1.70")))),
        "affordability_multiplier": float(_q4(affordability_multiplier)),
        "region_demand_modifier": float(_q4(region_demand_modifier)),
        "population_demand_multiplier": float(_q4(population_demand_mult)),
        "population_competition_penalty": float(_q4(competition_penalty)),
        "population_demand_share_factor": float(_q4(demand_share_factor)),
        "productivity_modifier": float(_q4(_d(getattr(player, "productivity_modifier", 1.0)))),
        "productivity_capture_factor": float(_q4(productivity_capture_factor)),
        "business_risk_penalty": float(_q4(_d(getattr(player, "business_risk_penalty", 0.0)))),
        "spoil_rate": float(_q4(spoil_rate)),
        "supply_chain_stress": float(_q4(supply_stress)),
        "upgrades": upgrades,
        "mode_demand_multiplier": float(_q4(mode_cfg["demand_multiplier"])),
        "mode_elasticity_bonus": float(_q4(mode_cfg["elasticity_bonus"])),
        "mode_spoilage_multiplier": float(_q4(mode_cfg["spoilage_multiplier"])),
        "upgrade_supplier_cost_multiplier": float(_q4(supplier_cost_mult)),
        "upgrade_signage_demand_multiplier": float(_q4(signage_demand_mult)),
        "upgrade_storage_spoilage_multiplier": float(_q4(spoilage_upgrade_mult)),
        "population_effects": population_effects,
    }

    log = _upsert_business_daily_log(
        db,
        business=business,
        player=player,
        day=day,
        as_of_date=op_date,
        business_type="fruit_shop",
        region_key=region,
        revenue_xgp=revenue_xgp,
        cogs_xgp=cogs_xgp,
        overhead_xgp=overhead_xgp,
        spoilage_loss_xgp=spoilage_loss_xgp,
        fuel_cost_xgp=Decimal("0"),
        maintenance_cost_xgp=Decimal("0"),
        net_profit_xgp=net_profit_xgp,
        units_sold=sold_units,
        inventory_start_units=inventory_start,
        inventory_end_units=inventory_end,
        demand_signal=demand,
        utilization_pct=_q4(sell_through * Decimal("100")),
        reputation_before=reputation_before,
        reputation_after=reputation_after,
        debug_meta=debug_meta,
    )
    return _serialize_operation_result(log, already_processed=False)


def operate_food_truck(
    db: Session,
    business: PlayerBusiness,
    *,
    as_of_date: date | None = None,
    day_number: int | None = None,
    operating_mode: str | None = None,
) -> dict:
    """Operate one food truck day using basket costs, fuel, traffic and maintenance."""
    if (business.business_type or "").strip().lower() != "food_truck":
        raise BusinessValidationError("operate_food_truck requires business_type='food_truck'.")
    player = _resolve_player(db, business.player_id)
    day, op_date = _resolve_day_and_date(as_of_date, day_number=day_number)

    existing = _existing_log_for_day(db, business.id, day)
    if existing is not None:
        return _serialize_operation_result(existing, already_processed=True)

    if operating_mode is not None:
        requested_mode = (operating_mode or "").strip().lower()
        if requested_mode not in FOOD_TRUCK_OPERATING_MODES:
            raise BusinessValidationError(
                f"Invalid food_truck operating mode. Allowed: {sorted(FOOD_TRUCK_OPERATING_MODES.keys())}"
            )
        business.operating_mode = requested_mode
    mode_key = _resolve_operating_mode(business)
    mode_cfg = FOOD_TRUCK_OPERATING_MODES[mode_key]
    upgrades = _business_upgrades(business)

    prep_usage_mult = Decimal("1.00")
    fuel_upgrade_mult = Decimal("1.00")
    location_demand_mult = Decimal("1.00")
    if "prep_efficiency" in upgrades:
        prep_usage_mult = _clamp(
            _d(BUSINESS_UPGRADES["food_truck"]["prep_efficiency"].get("ingredient_usage_multiplier", Decimal("1.0"))),
            Decimal("0.85"),
            Decimal("1.00"),
        )
    if "fuel_efficiency_upgrade" in upgrades:
        fuel_upgrade_mult = _clamp(
            _d(BUSINESS_UPGRADES["food_truck"]["fuel_efficiency_upgrade"].get("fuel_multiplier", Decimal("1.0"))),
            Decimal("0.80"),
            Decimal("1.00"),
        )
    if "better_location_permit" in upgrades:
        location_demand_mult = _clamp(
            _d(BUSINESS_UPGRADES["food_truck"]["better_location_permit"].get("demand_multiplier", Decimal("1.0"))),
            Decimal("1.00"),
            Decimal("1.20"),
        )

    macro = _latest_macro_for_day(db, day)
    confidence = _d(getattr(macro, "consumer_confidence", 50))
    oil_index = _d(getattr(macro, "oil_index", 100))
    supply_stress = _d(getattr(macro, "supply_chain_stress", 0))
    supply_stress_norm = _clamp(supply_stress * Decimal("20"), Decimal("0"), Decimal("100"))

    essentials_price = _latest_basket_price(db, BasketType.essentials, day, Decimal("10.0"))
    protein_price = _latest_basket_price(db, BasketType.protein, day, Decimal("12.0"))

    essentials_unit_cost = _q4(essentials_price * Decimal("0.45"))
    protein_unit_cost = _q4(protein_price * Decimal("0.55"))

    region = (business.region_key or "suburban").strip().lower()
    base_foot = TRUCK_REGION_BASE_FOOT.get(region, Decimal("32.0"))
    weekend_bonus = Decimal("1.18") if op_date.weekday() >= 5 else Decimal("1.00")
    weather_bonus = Decimal("1.00")
    event_bonus = Decimal("0.08") if (getattr(macro, "event_headline", "") or "").strip() else Decimal("0.00")
    confidence_multiplier = _clamp(
        Decimal("1.00") + (Decimal("0.015") * mode_cfg["confidence_sensitivity"] * (confidence - Decimal("50"))),
        Decimal("0.35"),
        Decimal("1.90"),
    )

    try:
        region_demand_modifier = _q4(get_business_region_demand_modifier(db, player.id, "food_truck"))
    except Exception:
        region_demand_modifier = Decimal("1.0000")
    population_demand_mult = Decimal("1.0000")
    competition_penalty = Decimal("0.0000")
    try:
        population_effects = get_population_effect_multipliers(
            db=db,
            region_key=region,
            as_of_date=op_date,
            player_id=player.id,
        )
        population_demand_mult = _q4(_d(population_effects.get("business_demand_multiplier", 1)))
        competition_penalty = _q4(_d(population_effects.get("business_competition_penalty", 0)))
    except Exception:
        population_effects = {}
        population_demand_mult = Decimal("1.0000")
        competition_penalty = Decimal("0.0000")
    demand_share_factor = _clamp(
        Decimal("1.00") - (competition_penalty * Decimal("0.45")),
        Decimal("0.78"),
        Decimal("1.00"),
    )

    raw_foot = base_foot * (Decimal("1.00") + event_bonus) * weekend_bonus * weather_bonus * confidence_multiplier
    bounded_foot = _clamp(
        raw_foot
        * region_demand_modifier
        * population_demand_mult
        * demand_share_factor
        * mode_cfg["demand_multiplier"]
        * location_demand_mult,
        Decimal("8"),
        Decimal("150"),
    )

    reputation_before = int(_clamp(_d(business.reputation or 50), Decimal("0"), Decimal("100")))
    reputation_multiplier = Decimal("1.00") + ((Decimal(reputation_before) / Decimal("250")) * mode_cfg["reputation_sensitivity"])
    productivity_capture_factor = _productivity_capture_factor(player)
    desired_sales = max(0, _to_int(_q4(bounded_foot * reputation_multiplier * productivity_capture_factor)))

    essentials_inventory_start = _unit(_d(business.inventory_essentials_units))
    protein_inventory_start = _unit(_d(business.inventory_protein_units))
    inventory_start_units = _unit(essentials_inventory_start + protein_inventory_start)

    ingredient_mode_mult = _clamp(mode_cfg["ingredient_usage_multiplier"] * prep_usage_mult, Decimal("0.82"), Decimal("1.18"))
    essentials_per_sale = _q4(Decimal("0.60") * ingredient_mode_mult)
    protein_per_sale = _q4(Decimal("0.40") * ingredient_mode_mult)
    max_by_ess = _to_int(essentials_inventory_start / essentials_per_sale) if essentials_per_sale > 0 else 0
    max_by_protein = _to_int(protein_inventory_start / protein_per_sale) if protein_per_sale > 0 else 0
    available_sales = max(0, min(max_by_ess, max_by_protein))
    units_sold = max(0, min(desired_sales, available_sales))
    sold_d = Decimal(str(units_sold))

    avg_ticket = _clamp(
        Decimal("8.50")
        + (Decimal("0.03") * (confidence - Decimal("50")))
        + (Decimal(reputation_before) / Decimal("200")),
        Decimal("6.00"),
        Decimal("14.00"),
    )
    avg_ticket = _clamp(avg_ticket * mode_cfg["ticket_multiplier"], Decimal("5.50"), Decimal("16.00"))
    revenue_xgp = _money(avg_ticket * sold_d)

    essentials_used = _unit(sold_d * essentials_per_sale)
    protein_used = _unit(sold_d * protein_per_sale)
    cogs_xgp = _money((essentials_used * essentials_unit_cost) + (protein_used * protein_unit_cost))

    level_key = _business_level_key(business)
    fuel_base = TRUCK_FUEL_BASE_BY_LEVEL.get(level_key, Decimal("5.50"))
    fuel_cost_xgp = _money(fuel_base * (oil_index / Decimal("100")) * fuel_upgrade_mult)
    overhead_xgp = _money(TRUCK_OVERHEAD_BY_LEVEL.get(level_key, Decimal("14.00")))

    remaining_essentials = _unit(max(Decimal("0"), essentials_inventory_start - essentials_used))
    remaining_protein_before_spoilage = _unit(max(Decimal("0"), protein_inventory_start - protein_used))
    protein_spoil_rate = _q4(
        _clamp(
            Decimal("0.01") + (supply_stress_norm / Decimal("2000")),
            Decimal("0.01"),
            Decimal("0.06"),
        )
    )
    spoiled_protein_units = min(
        _to_int(remaining_protein_before_spoilage * protein_spoil_rate),
        _to_int(remaining_protein_before_spoilage),
    )
    spoiled_protein_d = Decimal(str(max(0, spoiled_protein_units)))
    spoilage_loss_xgp = _money(spoiled_protein_d * protein_unit_cost)
    remaining_protein = _unit(max(Decimal("0"), remaining_protein_before_spoilage - spoiled_protein_d))

    maintenance_prob = _clamp(
        Decimal("0.03")
        + (sold_d / Decimal("220"))
        + ((Decimal("1.00") - (Decimal(reputation_before) / Decimal("100"))) * Decimal("0.03")),
        Decimal("0.00"),
        Decimal("0.30"),
    )
    maint_roll = _deterministic_ratio(
        f"{day}:{region}:{level_key}:{units_sold}:{_q4(oil_index)}:food_truck_maintenance"
    )
    maintenance_triggered = maint_roll < maintenance_prob
    maintenance_cost_xgp = Decimal("0.00")
    if maintenance_triggered:
        maintenance_cost_xgp = _money(
            _clamp(
                (Decimal("4.00") + (sold_d * Decimal("0.05"))) * (oil_index / Decimal("100")),
                Decimal("4.00"),
                Decimal("35.00"),
            )
        )

    net_profit_xgp = _money(
        revenue_xgp
        - cogs_xgp
        - overhead_xgp
        - fuel_cost_xgp
        - spoilage_loss_xgp
        - maintenance_cost_xgp
    )

    shortage_ratio = Decimal("0.0")
    if desired_sales > 0:
        shortage_ratio = _q4(Decimal(str(max(0, desired_sales - units_sold))) / Decimal(str(desired_sales)))

    rep_delta = 0
    if net_profit_xgp > 0 and shortage_ratio <= Decimal("0.35"):
        rep_delta += 1
    if net_profit_xgp < (_money(overhead_xgp) * Decimal("-0.5")) or shortage_ratio >= Decimal("0.55"):
        rep_delta -= 1
    if maintenance_triggered and net_profit_xgp < Decimal("0"):
        rep_delta -= 1
    if mode_key == "premium_menu" and confidence < Decimal("45") and net_profit_xgp < Decimal("0"):
        rep_delta -= 1
    reputation_after = int(_clamp(Decimal(reputation_before + rep_delta), Decimal("0"), Decimal("100")))

    business.inventory_essentials_units = remaining_essentials
    business.inventory_protein_units = remaining_protein
    business.reputation = reputation_after
    business.last_operated_day = day
    business.last_operated_on = op_date

    inventory_end_units = _unit(remaining_essentials + remaining_protein)
    utilization = _q4(
        (Decimal(str(units_sold)) / Decimal(str(max(1, available_sales)))) * Decimal("100")
        if available_sales > 0
        else Decimal("0")
    )
    debug_meta = {
        "foot_traffic": float(_q4(bounded_foot)),
        "base_foot_traffic": float(_q4(base_foot)),
        "event_traffic_bonus": float(_q4(event_bonus)),
        "weekend_bonus": float(_q4(weekend_bonus)),
        "weather_bonus": float(_q4(weather_bonus)),
        "confidence_multiplier": float(_q4(confidence_multiplier)),
        "reputation_multiplier": float(_q4(reputation_multiplier)),
        "operating_mode": mode_key,
        "avg_ticket_xgp": float(_q4(avg_ticket)),
        "available_sales": int(available_sales),
        "desired_sales": int(desired_sales),
        "maintenance_triggered": bool(maintenance_triggered),
        "maintenance_probability": float(_q4(maintenance_prob)),
        "maintenance_roll": float(_q4(maint_roll)),
        "essentials_unit_cost": float(_q4(essentials_unit_cost)),
        "protein_unit_cost": float(_q4(protein_unit_cost)),
        "oil_index": float(_q4(oil_index)),
        "region_demand_modifier": float(_q4(region_demand_modifier)),
        "population_demand_multiplier": float(_q4(population_demand_mult)),
        "population_competition_penalty": float(_q4(competition_penalty)),
        "population_demand_share_factor": float(_q4(demand_share_factor)),
        "productivity_modifier": float(_q4(_d(getattr(player, "productivity_modifier", 1.0)))),
        "productivity_capture_factor": float(_q4(productivity_capture_factor)),
        "business_risk_penalty": float(_q4(_d(getattr(player, "business_risk_penalty", 0.0)))),
        "upgrades": upgrades,
        "mode_ticket_multiplier": float(_q4(mode_cfg["ticket_multiplier"])),
        "mode_demand_multiplier": float(_q4(mode_cfg["demand_multiplier"])),
        "mode_ingredient_usage_multiplier": float(_q4(mode_cfg["ingredient_usage_multiplier"])),
        "mode_confidence_sensitivity": float(_q4(mode_cfg["confidence_sensitivity"])),
        "mode_reputation_sensitivity": float(_q4(mode_cfg["reputation_sensitivity"])),
        "upgrade_prep_usage_multiplier": float(_q4(prep_usage_mult)),
        "upgrade_fuel_multiplier": float(_q4(fuel_upgrade_mult)),
        "upgrade_location_demand_multiplier": float(_q4(location_demand_mult)),
        "population_effects": population_effects,
    }

    log = _upsert_business_daily_log(
        db,
        business=business,
        player=player,
        day=day,
        as_of_date=op_date,
        business_type="food_truck",
        region_key=region,
        revenue_xgp=revenue_xgp,
        cogs_xgp=cogs_xgp,
        overhead_xgp=overhead_xgp,
        spoilage_loss_xgp=spoilage_loss_xgp,
        fuel_cost_xgp=fuel_cost_xgp,
        maintenance_cost_xgp=maintenance_cost_xgp,
        net_profit_xgp=net_profit_xgp,
        units_sold=units_sold,
        inventory_start_units=inventory_start_units,
        inventory_end_units=inventory_end_units,
        demand_signal=_q4(Decimal(str(desired_sales))),
        utilization_pct=utilization,
        reputation_before=reputation_before,
        reputation_after=reputation_after,
        debug_meta=debug_meta,
    )
    return _serialize_operation_result(log, already_processed=False)


def get_player_businesses(db: Session, player_id: str | UUID) -> list[dict]:
    """Return deterministic-ordered business snapshot list for a player."""
    player = _resolve_player(db, player_id)
    rows = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id)
        .order_by(PlayerBusiness.created_at.asc(), PlayerBusiness.id.asc())
        .all()
    )
    return [
        {
            "business_id": str(row.id),
            "player_id": str(row.player_id),
            "business_type": row.business_type,
            "business_name": row.business_name,
            "is_active": bool(row.is_active),
            "region_key": row.region_key,
            "level": row.level,
            "reputation": int(row.reputation or 0),
            "cash_invested_xgp": float(_money(_d(row.cash_invested_xgp))),
            "inventory_produce_units": float(_unit(_d(row.inventory_produce_units))),
            "inventory_essentials_units": float(_unit(_d(row.inventory_essentials_units))),
            "inventory_protein_units": float(_unit(_d(row.inventory_protein_units))),
            "operating_mode": _resolve_operating_mode(row),
            "upgrades": _business_upgrades(row),
            "last_operated_on": row.last_operated_on.isoformat() if row.last_operated_on else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


def get_business_daily_history(
    db: Session,
    player_id: str | UUID,
    *,
    business_id: str | UUID | None = None,
    limit: int = 30,
) -> dict:
    """Return business daily history rows for a player, newest first."""
    player = _resolve_player(db, player_id)
    if limit <= 0:
        raise BusinessValidationError("limit must be greater than 0.")

    q = db.query(BusinessDailyLog).filter(BusinessDailyLog.player_id == player.id)
    if business_id is not None:
        bid = _normalize_uuid(business_id, label="Business")
        q = q.filter(BusinessDailyLog.business_id == bid)
    rows = (
        q.order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc(), BusinessDailyLog.id.desc())
        .limit(int(limit))
        .all()
    )
    return {
        "player_id": str(player.id),
        "count": len(rows),
        "history": [_serialize_operation_result(row, already_processed=False) for row in rows],
    }


def _inventory_value_estimate_for_business(
    *,
    business: PlayerBusiness,
    produce_unit_cost: Decimal,
    essentials_unit_cost: Decimal,
    protein_unit_cost: Decimal,
) -> Decimal:
    return _money(
        (_d(business.inventory_produce_units) * produce_unit_cost)
        + (_d(business.inventory_essentials_units) * essentials_unit_cost)
        + (_d(business.inventory_protein_units) * protein_unit_cost)
    )


def get_business_profit_snapshot(
    db: Session,
    player_id: str | UUID,
    *,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Return aggregated business performance and inventory value snapshot."""
    player = _resolve_player(db, player_id)
    day, _ = _resolve_day_and_date(as_of_date, day_number=day_number) if (as_of_date or day_number) else (1, GAME_EPOCH)

    businesses = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id)
        .order_by(PlayerBusiness.created_at.asc(), PlayerBusiness.id.asc())
        .all()
    )

    logs = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .limit(300)
        .all()
    )

    latest_day = int(logs[0].day) if logs else None
    latest_daily_profit_xgp = Decimal("0.00")
    trailing_7d_profit_xgp = Decimal("0.00")
    if logs:
        for row in logs:
            if latest_day is not None and int(row.day) == latest_day:
                latest_daily_profit_xgp += _d(row.net_profit_xgp)
            if latest_day is not None and int(row.day) >= latest_day - 6:
                trailing_7d_profit_xgp += _d(row.net_profit_xgp)

    produce_price = _latest_basket_price(db, BasketType.produce, day, Decimal("9.0"))
    essentials_price = _latest_basket_price(db, BasketType.essentials, day, Decimal("10.0"))
    protein_price = _latest_basket_price(db, BasketType.protein, day, Decimal("12.0"))
    produce_unit_cost = _q4(produce_price * Decimal("0.50"))
    essentials_unit_cost = _q4(essentials_price * Decimal("0.45"))
    protein_unit_cost = _q4(protein_price * Decimal("0.55"))

    inventory_estimated_value_xgp = Decimal("0.00")
    breakdown: dict[str, dict[str, Decimal | int | bool]] = {}
    for row in businesses:
        inv_value = _inventory_value_estimate_for_business(
            business=row,
            produce_unit_cost=produce_unit_cost,
            essentials_unit_cost=essentials_unit_cost,
            protein_unit_cost=protein_unit_cost,
        )
        inventory_estimated_value_xgp += inv_value
        btype = (row.business_type or "unknown").strip().lower()
        bucket = breakdown.setdefault(
            btype,
            {
                "business_type": btype,
                "count": 0,
                "active_count": 0,
                "inventory_value_xgp": Decimal("0.00"),
                "latest_daily_profit_xgp": Decimal("0.00"),
            },
        )
        bucket["count"] = int(bucket["count"]) + 1
        if bool(row.is_active):
            bucket["active_count"] = int(bucket["active_count"]) + 1
        bucket["inventory_value_xgp"] = _money(_d(bucket["inventory_value_xgp"]) + inv_value)

    if latest_day is not None:
        for row in logs:
            if int(row.day) != latest_day:
                continue
            btype = (row.business_type or "unknown").strip().lower()
            if btype not in breakdown:
                continue
            breakdown[btype]["latest_daily_profit_xgp"] = _money(
                _d(breakdown[btype]["latest_daily_profit_xgp"]) + _d(row.net_profit_xgp)
            )

    business_estimated_value_xgp = _money(
        max(
            Decimal("0.00"),
            (_money(trailing_7d_profit_xgp) * Decimal("8.00")) + _money(inventory_estimated_value_xgp),
        )
    )

    return {
        "player_id": str(player.id),
        "day": int(day),
        "total_businesses": len(businesses),
        "active_businesses": len([row for row in businesses if bool(row.is_active)]),
        "latest_daily_profit_xgp": float(_money(latest_daily_profit_xgp)),
        "trailing_7d_profit_xgp": float(_money(trailing_7d_profit_xgp)),
        "inventory_estimated_value_xgp": float(_money(inventory_estimated_value_xgp)),
        "business_estimated_value_xgp": float(_money(business_estimated_value_xgp)),
        "business_type_breakdown": [
            {
                "business_type": item["business_type"],
                "count": int(item["count"]),
                "active_count": int(item["active_count"]),
                "inventory_value_xgp": float(_money(_d(item["inventory_value_xgp"]))),
                "latest_daily_profit_xgp": float(_money(_d(item["latest_daily_profit_xgp"]))),
            }
            for item in sorted(breakdown.values(), key=lambda v: str(v["business_type"]))
        ],
    }


def run_business_operations_for_player(
    db: Session,
    player_id: int | str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Run all active business operations for one player/day deterministically."""
    player = _resolve_player(db, player_id)

    if as_of_date is None:
        # Resolve next settlement day lazily to avoid circular import at module import time.
        from app.services.daily_settlement_service import get_next_player_day  # local import

        day = int(get_next_player_day(db, player.id))
        as_of_date = day_to_date(day)
    else:
        day = date_to_day(as_of_date)
        if day <= 0:
            raise BusinessValidationError("as_of_date must be on or after game epoch.")

    rows = (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.is_active.is_(True),
        )
        .order_by(PlayerBusiness.created_at.asc(), PlayerBusiness.id.asc())
        .all()
    )

    results: list[dict] = []
    business_hours_total = Decimal("0.00")
    for row in rows:
        btype = (row.business_type or "").strip().lower()
        if btype == "fruit_shop":
            result = operate_fruit_shop(db, row, as_of_date=as_of_date, day_number=day)
        elif btype == "food_truck":
            result = operate_food_truck(db, row, as_of_date=as_of_date, day_number=day)
        else:
            continue
        results.append(result)
        business_hours_total += _operation_hours_for_business(row)

    totals = {
        "business_revenue_xgp": Decimal("0.00"),
        "business_cogs_xgp": Decimal("0.00"),
        "business_overhead_xgp": Decimal("0.00"),
        "business_spoilage_loss_xgp": Decimal("0.00"),
        "business_fuel_cost_xgp": Decimal("0.00"),
        "business_maintenance_cost_xgp": Decimal("0.00"),
        "business_net_profit_xgp": Decimal("0.00"),
    }
    cash_delta_totals = {
        "business_revenue_xgp": Decimal("0.00"),
        "business_cogs_xgp": Decimal("0.00"),
        "business_overhead_xgp": Decimal("0.00"),
        "business_spoilage_loss_xgp": Decimal("0.00"),
        "business_fuel_cost_xgp": Decimal("0.00"),
        "business_maintenance_cost_xgp": Decimal("0.00"),
        "business_net_profit_xgp": Decimal("0.00"),
    }
    for item in results:
        totals["business_revenue_xgp"] += _d(item.get("revenue_xgp", 0))
        totals["business_cogs_xgp"] += _d(item.get("cogs_xgp", 0))
        totals["business_overhead_xgp"] += _d(item.get("overhead_xgp", 0))
        totals["business_spoilage_loss_xgp"] += _d(item.get("spoilage_loss_xgp", 0))
        totals["business_fuel_cost_xgp"] += _d(item.get("fuel_cost_xgp", 0))
        totals["business_maintenance_cost_xgp"] += _d(item.get("maintenance_cost_xgp", 0))
        totals["business_net_profit_xgp"] += _d(item.get("net_profit_xgp", 0))
        if item.get("status") == "ran":
            cash_delta_totals["business_revenue_xgp"] += _d(item.get("revenue_xgp", 0))
            cash_delta_totals["business_cogs_xgp"] += _d(item.get("cogs_xgp", 0))
            cash_delta_totals["business_overhead_xgp"] += _d(item.get("overhead_xgp", 0))
            cash_delta_totals["business_spoilage_loss_xgp"] += _d(item.get("spoilage_loss_xgp", 0))
            cash_delta_totals["business_fuel_cost_xgp"] += _d(item.get("fuel_cost_xgp", 0))
            cash_delta_totals["business_maintenance_cost_xgp"] += _d(item.get("maintenance_cost_xgp", 0))
            cash_delta_totals["business_net_profit_xgp"] += _d(item.get("net_profit_xgp", 0))

    cash_before = _money(_d(player.cash_xgp))
    player.cash_xgp = _money(cash_before + _money(cash_delta_totals["business_net_profit_xgp"]))

    # Side-income snapshot (if any) for the same day, so day/run can return both systems together.
    pds = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == int(day),
        )
        .first()
    )
    side_income_result = {
        "side_income_hours": 0.0,
        "side_income_gross_xgp": 0.0,
        "side_income_fuel_cost_xgp": 0.0,
        "side_income_wear_cost_xgp": 0.0,
        "side_income_maintenance_cost_xgp": 0.0,
        "side_income_net_xgp": 0.0,
    }
    if pds is not None:
        pds.business_hours = _q4(business_hours_total)
        side_income_result = {
            "side_income_hours": float(_q4(_d(getattr(pds, "side_income_hours", 0)))),
            "side_income_gross_xgp": float(_money(_d(getattr(pds, "side_income_gross_xgp", 0)))),
            "side_income_fuel_cost_xgp": float(_money(_d(getattr(pds, "side_income_fuel_cost_xgp", 0)))),
            "side_income_wear_cost_xgp": float(_money(_d(getattr(pds, "side_income_wear_cost_xgp", 0)))),
            "side_income_maintenance_cost_xgp": float(
                _money(_d(getattr(pds, "side_income_maintenance_cost_xgp", 0)))
            ),
            "side_income_net_xgp": float(_money(_d(getattr(pds, "side_income_net_xgp", 0)))),
        }

    fruit_result = next((r for r in results if r.get("business_type") == "fruit_shop"), None)
    truck_result = next((r for r in results if r.get("business_type") == "food_truck"), None)

    summary = {
        "player_id": str(player.id),
        "day": int(day),
        "as_of_date": as_of_date.isoformat(),
        "business_count_run": len(results),
        "per_business_results": results,
        "business_summary": {
            "count": len(results),
            "totals": {k: float(_money(v)) for k, v in totals.items()},
        },
        "fruit_shop_result": fruit_result,
        "food_truck_result": truck_result,
        "side_income_result": side_income_result,
        "business_net_profit_xgp": float(_money(totals["business_net_profit_xgp"])),
        "cash_delta_business_net_xgp": float(_money(cash_delta_totals["business_net_profit_xgp"])),
        "maintenance_cost_xgp": float(_money(totals["business_maintenance_cost_xgp"])),
        "spoilage_loss_xgp": float(_money(totals["business_spoilage_loss_xgp"])),
        "business_hours": float(_q4(business_hours_total)),
        "business_revenue_xgp": float(_money(totals["business_revenue_xgp"])),
        "business_cogs_xgp": float(_money(totals["business_cogs_xgp"])),
        "business_overhead_xgp": float(_money(totals["business_overhead_xgp"])),
        "business_fuel_cost_xgp": float(_money(totals["business_fuel_cost_xgp"])),
        "business_maintenance_cost_xgp": float(_money(totals["business_maintenance_cost_xgp"])),
        "business_spoilage_loss_xgp": float(_money(totals["business_spoilage_loss_xgp"])),
        "total_business_profit_xgp": float(_money(totals["business_net_profit_xgp"])),
        "cash_before_xgp": float(cash_before),
        "cash_after_xgp": float(_money(_d(player.cash_xgp))),
    }
    db.flush()
    return summary
