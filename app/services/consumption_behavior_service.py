"""Consumer Spending Behavior + Basket Consumption Refinement Service.

Replaces the flat _estimate_daily_basket_spend() in the settlement service with
a behaviorally-realistic four-basket consumption model.

Key design principles:
  - Essentials are least elastic — they rarely collapse even under pressure.
  - Protein is moderately elastic — budget-squeezed players cut it first after
    produce.
  - Produce is health-sensitive and budget-sensitive — squeezed under inflation.
  - Convenience is most elastic, stress-driven, and impulsive but bounded.
  - Budget pressure is a composite score from cash/debt/housing ratios.
  - Stress drives convenience UP, poverty drives convenience DOWN.
  - All arithmetic uses Decimal to avoid float drift.

Public API:
  compute_player_daily_consumption(db, player_id, day) -> dict
  get_player_consumption_summary(db, player_id) -> dict
  get_latest_basket_prices_for_day(db, day) -> dict
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.enums import BasketType
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState

# ─── Precision helpers ────────────────────────────────────────────────────────

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")


def _d(v: object) -> Decimal:
    return Decimal(str(v or 0))


def _money(v: Decimal) -> Decimal:
    return v.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(v: Decimal) -> Decimal:
    return v.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, v))


# ─── Custom exceptions ────────────────────────────────────────────────────────


class ConsumptionError(Exception):
    """Base exception for consumption service failures."""


class ConsumptionNotFoundError(ConsumptionError):
    """Raised when a required entity (player, price row) is not found."""


# ─── Default basket prices (fallback when no DB row exists) ──────────────────

# These reflect reasonable in-game daily price indexes  (units × price_index).
_FALLBACK_PRICE_INDEX: dict[BasketType, Decimal] = {
    BasketType.essentials: Decimal("8.50"),
    BasketType.protein: Decimal("7.00"),
    BasketType.produce: Decimal("5.50"),
    BasketType.convenience: Decimal("6.00"),
}

# Base daily unit consumption targets (in basket-units) before pressure.
# These represent a "normal day" for an average player.
_BASE_UNITS: dict[BasketType, Decimal] = {
    BasketType.essentials: Decimal("1.10"),
    BasketType.protein: Decimal("0.80"),
    BasketType.produce: Decimal("0.70"),
    BasketType.convenience: Decimal("0.45"),
}

# Elasticity weights — how much budget pressure reduces each basket.
# 0.0 = perfectly inelastic, 1.0 = fully elastic.
_ELASTICITY: dict[BasketType, Decimal] = {
    BasketType.essentials: Decimal("0.15"),    # near-unavoidable
    BasketType.protein: Decimal("0.55"),       # moderately squeezed
    BasketType.produce: Decimal("0.50"),       # nutrition squeeze
    BasketType.convenience: Decimal("0.85"),   # highly elastic, budget-driven
}

# Region multipliers — downtown living costs more.
_REGION_MULT: dict[str, Decimal] = {
    "downtown": Decimal("1.14"),
    "suburban": Decimal("1.00"),
}

# Minimum daily floor spend per basket (even in severe poverty).
# Ensures survival makes sense even at rock bottom.
_FLOOR_XGP: dict[BasketType, Decimal] = {
    BasketType.essentials: Decimal("3.00"),
    BasketType.protein: Decimal("0.80"),
    BasketType.produce: Decimal("0.50"),
    BasketType.convenience: Decimal("0.00"),
}


# ─── Internal data-fetching helpers ──────────────────────────────────────────


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise ConsumptionNotFoundError(f"Player {player_id} not found.")
    return player


def _latest_price(db: Session, basket_type: BasketType, day: int) -> Decimal:
    """Return the most recent price_index on or before `day`, or fallback."""
    row = (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day <= day,
        )
        .order_by(BasketDailyPrice.day.desc())
        .first()
    )
    if row is None:
        row = (
            db.query(BasketDailyPrice)
            .filter(BasketDailyPrice.basket_type == basket_type)
            .order_by(BasketDailyPrice.day.desc())
            .first()
        )
    if row is not None:
        return _d(row.price_index)
    return _FALLBACK_PRICE_INDEX[basket_type]


def _latest_employment(db: Session, player_id: UUID) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player_id)
        .order_by(PlayerEmploymentState.day.desc())
        .first()
    )


def _latest_housing_state(db: Session, player_id: UUID) -> PlayerHousingState | None:
    return (
        db.query(PlayerHousingState)
        .filter(PlayerHousingState.player_id == player_id)
        .order_by(PlayerHousingState.updated_at.desc())
        .first()
    )


# ─── Pressure computation ─────────────────────────────────────────────────────


def _compute_budget_pressure(
    cash_xgp: Decimal,
    debt_xgp: Decimal,
    housing_cost_daily: Decimal,
    monthly_income: Decimal,
    employed: bool,
) -> Decimal:
    """
    budget_pressure_score ∈ [0.0, 1.0].

    Combines:
      - debt-to-cash ratio  (high debt relative to liquid cash = pressure)
      - housing affordability (housing cost vs income)
      - unemployment shock   (immediate hard pressure)
      - low-cash penalty     (absolute floor check)

    Returns 0.0 for a comfortable player, 1.0 for severely squeezed.
    """
    # Unemployment is a hard multiplier on pressure.
    unemployment_boost = Decimal("0.35") if not employed else Decimal("0.00")

    # Debt-to-cash: ratio of outstanding debt relative to 30 days of income.
    monthly_inc = max(monthly_income, Decimal("1.00"))
    debt_ratio = _clamp(debt_xgp / (monthly_inc * Decimal("6")), Decimal("0"), Decimal("1"))

    # Housing affordability: daily housing vs daily income.
    daily_income = monthly_inc / Decimal("30")
    if daily_income <= Decimal("0.00"):
        housing_pressure = Decimal("0.60")
    else:
        housing_ratio = housing_cost_daily / daily_income
        housing_pressure = _clamp(housing_ratio / Decimal("2"), Decimal("0"), Decimal("0.5"))

    # Low cash absolute penalty: if cash < 30 days of essentials.
    essentials_monthly = _FALLBACK_PRICE_INDEX[BasketType.essentials] * _BASE_UNITS[BasketType.essentials] * Decimal("30")
    cash_pressure = _clamp(
        Decimal("1") - (cash_xgp / essentials_monthly),
        Decimal("0"),
        Decimal("0.5"),
    )

    raw = debt_ratio * Decimal("0.35") + housing_pressure * Decimal("0.30") + cash_pressure * Decimal("0.20") + unemployment_boost
    return _q4(_clamp(raw, Decimal("0"), Decimal("1")))


def _compute_stress_spend_modifier(stress: int) -> Decimal:
    """
    stress_spend_modifier – applied only to convenience basket.

    stress ∈ [0, 100].
    At stress 0  → modifier = 1.00  (normal)
    At stress 50 → modifier ≈ 1.10  (+10% convenience)
    At stress 90 → modifier ≈ 1.22  (+22% convenience, capped)

    Bounded: convenience modifier never exceeds 1.30 and floor is 1.00.
    """
    normalized = Decimal(str(max(0, min(stress, 100)))) / Decimal("100")
    modifier = Decimal("1.00") + (normalized * Decimal("0.30"))
    return _q4(_clamp(modifier, Decimal("1.00"), Decimal("1.30")))


def _compute_nutrition_pressure(
    budget_pressure_score: Decimal,
    protein_price: Decimal,
    produce_price: Decimal,
) -> Decimal:
    """
    nutrition_pressure_score ∈ [0.0, 1.0].

    Reflects how much inflation + budget squeeze is affecting nutritional
    choices.  High when:
      - basket prices for protein/produce are elevated relative to baseline
      - budget pressure is already high

    This is a diagnostic/analytics score, not a spending multiplier.
    """
    protein_baseline = _FALLBACK_PRICE_INDEX[BasketType.protein]
    produce_baseline = _FALLBACK_PRICE_INDEX[BasketType.produce]

    protein_inflation = _clamp(
        (protein_price - protein_baseline) / protein_baseline, Decimal("0"), Decimal("1")
    )
    produce_inflation = _clamp(
        (produce_price - produce_baseline) / produce_baseline, Decimal("0"), Decimal("1")
    )

    price_squeeze = (protein_inflation + produce_inflation) / Decimal("2")
    raw = budget_pressure_score * Decimal("0.65") + price_squeeze * Decimal("0.35")
    return _q4(_clamp(raw, Decimal("0"), Decimal("1")))


# ─── Core basket spend calculation ───────────────────────────────────────────


def _compute_basket_spend(
    prices: dict[BasketType, Decimal],
    region: str,
    budget_pressure: Decimal,
    stress_modifier: Decimal,
    health: int,
) -> dict[BasketType, Decimal]:
    """
    Compute per-basket daily spend in XGP.

    For each basket:
      raw_spend = base_units × price_index × region_mult
      reduction  = raw_spend × elasticity × budget_pressure
      final      = max(floor, raw_spend - reduction)

    Convenience gets an additional stress multiplier applied AFTER
    budget-pressure reduction (stress can override poverty a little, but
    budget floor still applies).
    """
    region_mult = _REGION_MULT.get((region or "suburban").lower(), Decimal("1.00"))
    results: dict[BasketType, Decimal] = {}

    for basket_type in BasketType:
        raw = _BASE_UNITS[basket_type] * prices[basket_type] * region_mult
        reduction = raw * _ELASTICITY[basket_type] * budget_pressure
        adjusted = raw - reduction

        if basket_type == BasketType.convenience:
            # Stress pushes convenience up, but can't undo budget collapse.
            pre_floor = adjusted * stress_modifier
            # Cap stress-driven convenience at 1.5× the raw baseline.
            cap = raw * Decimal("1.50")
            adjusted = _clamp(pre_floor, _FLOOR_XGP[basket_type], cap)
        else:
            # Health-conscious minor boost: if health > 80, slight produce bump.
            if basket_type == BasketType.produce and health >= 80:
                adjusted = adjusted * Decimal("1.05")
            adjusted = max(_FLOOR_XGP[basket_type], adjusted)

        results[basket_type] = _money(adjusted)

    return results


# ─── Public service functions ─────────────────────────────────────────────────


def get_latest_basket_prices_for_day(db: Session, day: int) -> dict:
    """
    Return the latest available price_index for each basket type on or
    before `day`.  Falls back to hard-coded defaults if no DB rows exist.
    """
    prices = {}
    for basket_type in BasketType:
        row = (
            db.query(BasketDailyPrice)
            .filter(
                BasketDailyPrice.basket_type == basket_type,
                BasketDailyPrice.day <= day,
            )
            .order_by(BasketDailyPrice.day.desc())
            .first()
        )
        if row is None:
            row = (
                db.query(BasketDailyPrice)
                .filter(BasketDailyPrice.basket_type == basket_type)
                .order_by(BasketDailyPrice.day.desc())
                .first()
            )
        prices[basket_type.value] = {
            "day": int(row.day) if row else day,
            "price_index": float(_d(row.price_index) if row else _FALLBACK_PRICE_INDEX[basket_type]),
            "daily_change_pct": float(_d(row.daily_change_pct) if row else 0),
            "supply_pressure": float(_d(row.supply_pressure) if row else Decimal("1.0")),
            "demand_pressure": float(_d(row.demand_pressure) if row else Decimal("1.0")),
        }
    return prices


def compute_player_daily_consumption(
    db: Session,
    player_id: str | UUID,
    day: int,
    *,
    commit: bool = True,
) -> dict:
    """
    Compute a player's daily basket consumption and persist a BasketConsumptionLog.

    Idempotent: if a log already exists for (player_id, day), returns the
    existing record without creating a duplicate or recharging the player.

    Returns a dict with all four basket spend values plus pressure scores.
    """
    try:
        player = _resolve_player(db, player_id)

        # ── Idempotency check ─────────────────────────────────────────────────
        existing = (
            db.query(BasketConsumptionLog)
            .filter(
                BasketConsumptionLog.player_id == player.id,
                BasketConsumptionLog.day == day,
            )
            .first()
        )
        if existing is not None:
            return _serialize_log(existing)

        # ── Gather player state ───────────────────────────────────────────────
        cash_xgp = _d(getattr(player, "cash_xgp", None) or getattr(player, "cash", 0))
        debt_xgp = _d(player.debt_xgp)
        stress = int(player.stress or 0)
        health = int(player.health or 100)
        region = str(player.region or "suburban")

        # ── Employment state ──────────────────────────────────────────────────
        employment = _latest_employment(db, player.id)
        employed = bool(getattr(employment, "employed_flag", False))
        monthly_pay = _d(getattr(employment, "monthly_pay_xgp", 0))

        # ── Housing daily cost estimate ───────────────────────────────────────
        housing_state = _latest_housing_state(db, player.id)
        if housing_state is not None and getattr(housing_state, "active_flag", False):
            housing_cost_daily = _money(_d(getattr(housing_state, "daily_housing_cost_xgp", 0)))
        elif player.has_active_housing and player.housing_region_id:
            # Fallback: approximate from region.
            housing_cost_daily = Decimal("12.00") if player.housing_region_id == "downtown" else Decimal("7.00")
        else:
            housing_cost_daily = Decimal("0.00")

        # ── Basket prices ─────────────────────────────────────────────────────
        prices: dict[BasketType, Decimal] = {
            bt: _latest_price(db, bt, day) for bt in BasketType
        }

        # ── Pressure scores ───────────────────────────────────────────────────
        budget_pressure = _compute_budget_pressure(
            cash_xgp=cash_xgp,
            debt_xgp=debt_xgp,
            housing_cost_daily=housing_cost_daily,
            monthly_income=monthly_pay,
            employed=employed,
        )
        stress_modifier = _compute_stress_spend_modifier(stress)
        nutrition_pressure = _compute_nutrition_pressure(
            budget_pressure_score=budget_pressure,
            protein_price=prices[BasketType.protein],
            produce_price=prices[BasketType.produce],
        )

        # ── Per-basket spend ──────────────────────────────────────────────────
        spend = _compute_basket_spend(
            prices=prices,
            region=region,
            budget_pressure=budget_pressure,
            stress_modifier=stress_modifier,
            health=health,
        )

        essentials_spend = spend[BasketType.essentials]
        protein_spend = spend[BasketType.protein]
        produce_spend = spend[BasketType.produce]
        convenience_spend = spend[BasketType.convenience]
        total_spend = _money(essentials_spend + protein_spend + produce_spend + convenience_spend)

        # ── Notes payload for explainability ─────────────────────────────────
        notes = {
            "cash_xgp": float(cash_xgp),
            "debt_xgp": float(debt_xgp),
            "employed": employed,
            "monthly_pay_xgp": float(monthly_pay),
            "housing_cost_daily_xgp": float(housing_cost_daily),
            "region": region,
            "stress": stress,
            "health": health,
            "prices": {bt.value: float(p) for bt, p in prices.items()},
        }

        # ── Persist log ───────────────────────────────────────────────────────
        log = BasketConsumptionLog(
            player_id=player.id,
            day=day,
            essentials_spend_xgp=essentials_spend,
            protein_spend_xgp=protein_spend,
            produce_spend_xgp=produce_spend,
            convenience_spend_xgp=convenience_spend,
            total_spend_xgp=total_spend,
            budget_pressure_score=budget_pressure,
            stress_spend_modifier=stress_modifier,
            nutrition_pressure_score=nutrition_pressure,
            notes_json=json.dumps(notes),
        )
        db.add(log)

        if commit:
            db.commit()
            db.refresh(log)

        return _serialize_log(log)

    except ConsumptionError:
        if commit:
            db.rollback()
        raise
    except Exception as exc:
        if commit:
            db.rollback()
        raise ConsumptionError("Unexpected error in consumption service.") from exc


def get_player_consumption_summary(db: Session, player_id: str | UUID) -> dict:
    """
    Return the most recently logged basket consumption for a player.
    Raises ConsumptionNotFoundError if no log exists yet.
    """
    player = _resolve_player(db, player_id)
    log = (
        db.query(BasketConsumptionLog)
        .filter(BasketConsumptionLog.player_id == player.id)
        .order_by(BasketConsumptionLog.day.desc())
        .first()
    )
    if log is None:
        raise ConsumptionNotFoundError(
            f"No consumption log found for player {player_id}."
        )
    return _serialize_log(log)


# ─── Serialiser ───────────────────────────────────────────────────────────────


def _serialize_log(log: BasketConsumptionLog) -> dict:
    return {
        "player_id": str(log.player_id),
        "day": int(log.day),
        "essentials_spend_xgp": float(log.essentials_spend_xgp),
        "protein_spend_xgp": float(log.protein_spend_xgp),
        "produce_spend_xgp": float(log.produce_spend_xgp),
        "convenience_spend_xgp": float(log.convenience_spend_xgp),
        "total_spend_xgp": float(log.total_spend_xgp),
        "budget_pressure_score": float(log.budget_pressure_score),
        "stress_spend_modifier": float(log.stress_spend_modifier),
        "nutrition_pressure_score": float(log.nutrition_pressure_score),
    }
