"""Step 13 supply-chain daily compute engine (compute-only signals)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.basket_recipes import BASKET_RECIPES
from app.engine.supply_chain_nodes import SUPPLY_CHAIN_NODES
from app.models.macro_daily_state import MacroDailyState

Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")

ONE = Decimal("1.00")
ZERO = Decimal("0.00")

BASKET_MIN_MULTIPLIER = Decimal("0.85")
BASKET_MAX_MULTIPLIER = Decimal("1.10")

# Lightweight structural basket adjustments keep perishables slightly more fragile
# than broad staples in stress conditions.
BASKET_STRUCTURAL_ADJUSTMENT: dict[str, Decimal] = {
    "essentials": Decimal("0.00"),
    "protein": Decimal("-0.005"),
    "produce": Decimal("-0.01"),
    "convenience": Decimal("0.00"),
}

BOTTLENECK_THRESHOLD = Decimal("0.95")
BOTTLENECK_MAX_ITEMS = 8

JOB_PRESSURE_MIN = Decimal("-0.30")
JOB_PRESSURE_MAX = Decimal("0.30")
JOB_DIRECTION_THRESHOLD = Decimal("0.03")

NODE_COMPUTE_ORDER = (
    "fuel",
    "labor",
    "utilities",
    "fertilizer",
    "farming",
    "trucking",
    "processing",
    "retail",
)

JOB_KEYS = (
    "auto_mechanic",
    "aircraft_mechanic",
    "banker",
    "chef",
    "retail_worker",
    "delivery_driver",
)

CONSTANTS_VERSION = "supply_chain_v1"


class SupplyChainError(Exception):
    """Base supply-chain compute exception."""


class SupplyChainNotFoundError(SupplyChainError):
    """Raised when required macro inputs are unavailable."""


class SupplyChainValidationError(SupplyChainError):
    """Raised for invalid supply-chain request arguments."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _quantize2(value: Decimal) -> Decimal:
    return value.quantize(Q2, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp_decimal(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


def _get_macro_state_for_date(db: Session, as_of_date: date | None) -> MacroDailyState | None:
    base_query = db.query(MacroDailyState)
    if as_of_date is not None:
        as_of_iso = as_of_date.isoformat()
        row = (
            base_query.filter(func.date(MacroDailyState.created_at) <= as_of_iso)
            .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
            .first()
        )
        if row is not None:
            return row
    return (
        base_query.order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc()).first()
    )


def _get_macro_state_for_day(db: Session, macro_day: int | None) -> MacroDailyState | None:
    if macro_day is None:
        return None
    return (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day == int(macro_day))
        .order_by(MacroDailyState.created_at.desc())
        .first()
    )


def _normalize_macro_inputs(macro_state: MacroDailyState) -> dict[str, Decimal]:
    inflation = _d(macro_state.inflation_rate)
    interest = _d(macro_state.interest_rate)
    unemployment = _d(macro_state.unemployment_rate)
    oil = _d(macro_state.oil_index)
    confidence = _d(macro_state.consumer_confidence)
    supply_stress = _d(macro_state.supply_chain_stress)

    unemployment_gap = abs(unemployment - Decimal("5.0"))

    return {
        "inflation_rate": _q4(inflation),
        "interest_rate": _q4(interest),
        "unemployment_rate": _q4(unemployment),
        "oil_index": _q4(oil),
        "consumer_confidence": _q4(confidence),
        "supply_chain_stress": _q4(supply_stress),
        "inflation_pressure": _q4(_clamp_decimal((inflation - Decimal("2.0")) / Decimal("8.0"), ZERO, ONE)),
        "inflation_relief": _q4(_clamp_decimal((Decimal("2.5") - inflation) / Decimal("2.5"), ZERO, ONE)),
        "interest_pressure": _q4(_clamp_decimal((interest - Decimal("4.0")) / Decimal("6.0"), ZERO, ONE)),
        "oil_pressure": _q4(_clamp_decimal((oil - Decimal("100")) / Decimal("80"), ZERO, ONE)),
        "oil_relief": _q4(_clamp_decimal((Decimal("100") - oil) / Decimal("40"), ZERO, ONE)),
        "confidence_weakness": _q4(
            _clamp_decimal((Decimal("55") - confidence) / Decimal("35"), ZERO, ONE)
        ),
        "confidence_support": _q4(
            _clamp_decimal((confidence - Decimal("52")) / Decimal("28"), ZERO, ONE)
        ),
        "unemployment_pressure": _q4(_clamp_decimal(unemployment_gap / Decimal("6"), ZERO, ONE)),
        "supply_stress_pressure": _q4(_clamp_decimal(supply_stress / Decimal("3.0"), ZERO, ONE)),
        "supply_relief": _q4(_clamp_decimal((Decimal("1.0") - supply_stress) / Decimal("1.0"), ZERO, ONE)),
    }


def _compute_node_availability(
    node_key: str,
    normalized_inputs: dict[str, Decimal],
    memo: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if node_key in memo:
        return memo[node_key]

    if node_key not in SUPPLY_CHAIN_NODES:
        raise SupplyChainValidationError(f"Unknown supply-chain node: {node_key}")

    node_def = SUPPLY_CHAIN_NODES[node_key]
    depends_on = [str(dep) for dep in node_def.get("depends_on", [])]

    upstream_snapshots = [
        _compute_node_availability(dep_key, normalized_inputs, memo) for dep_key in depends_on
    ]

    total_penalty = Decimal("0")
    total_support = Decimal("0")
    drivers: dict[str, Decimal] = {}

    for factor_key, weight in node_def.get("sensitivities", {}).items():
        factor_value = _d(normalized_inputs.get(factor_key, ZERO))
        contribution = _q4(factor_value * _d(weight))
        if contribution > ZERO:
            total_penalty += contribution
            drivers[factor_key] = contribution

    for factor_key, weight in node_def.get("support_sensitivities", {}).items():
        factor_value = _d(normalized_inputs.get(factor_key, ZERO))
        support = _q4(factor_value * _d(weight))
        if support > ZERO:
            total_support += support
            drivers[f"support_{factor_key}"] = support

    dependency_penalty = ZERO
    if upstream_snapshots:
        total_gap = sum(
            (max(ZERO, ONE - _d(snapshot["availability"])) for snapshot in upstream_snapshots),
            ZERO,
        )
        average_gap = total_gap / Decimal(str(len(upstream_snapshots)))
        dependency_penalty = _q4(average_gap * _d(node_def.get("dependency_weight", ZERO)))
        if dependency_penalty > ZERO:
            total_penalty += dependency_penalty
            drivers["dependency_penalty"] = dependency_penalty

    raw_availability = ONE - total_penalty + total_support
    availability = _clamp_decimal(
        _q4(raw_availability),
        _d(node_def.get("min_availability", Decimal("0.70"))),
        _d(node_def.get("max_availability", Decimal("1.10"))),
    )
    severity = _q4(max(ZERO, ONE - availability))

    snapshot = {
        "node_key": node_key,
        "display_name": str(node_def["display_name"]),
        "availability": availability,
        "severity": severity,
        "drivers": {
            key: value for key, value in sorted(drivers.items(), key=lambda item: item[0]) if value > ZERO
        },
        "depends_on": depends_on,
    }
    memo[node_key] = snapshot
    return snapshot


def _compute_all_node_availability(normalized_inputs: dict[str, Decimal]) -> list[dict[str, Any]]:
    memo: dict[str, dict[str, Any]] = {}

    for node_key in NODE_COMPUTE_ORDER:
        _compute_node_availability(node_key, normalized_inputs, memo)
    for node_key in sorted(SUPPLY_CHAIN_NODES.keys()):
        _compute_node_availability(node_key, normalized_inputs, memo)

    ordered_keys = [key for key in NODE_COMPUTE_ORDER if key in memo]
    ordered_keys.extend(
        [key for key in sorted(memo.keys()) if key not in NODE_COMPUTE_ORDER]
    )
    return [memo[key] for key in ordered_keys]


def _compute_basket_supply(node_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_node = {str(s["node_key"]): _d(s["availability"]) for s in node_snapshots}
    rows: list[dict[str, Any]] = []

    for basket_key, recipe in BASKET_RECIPES.items():
        weighted = ZERO
        node_ranking: list[tuple[Decimal, str]] = []
        for node_key, weight in recipe.items():
            availability = _d(by_node.get(node_key, ONE))
            weighted += availability * _d(weight)
            node_ranking.append((availability, str(node_key)))

        weighted += _d(BASKET_STRUCTURAL_ADJUSTMENT.get(str(basket_key), ZERO))
        multiplier = _clamp_decimal(_q4(weighted), BASKET_MIN_MULTIPLIER, BASKET_MAX_MULTIPLIER)
        dominant_nodes = [name for _, name in sorted(node_ranking, key=lambda item: (item[0], item[1]))[:3]]

        rows.append(
            {
                "basket_key": str(basket_key),
                "supply_multiplier": multiplier,
                "dominant_nodes": dominant_nodes,
            }
        )
    return rows


def _compute_bottlenecks(node_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [
        {
            "node_key": str(row["node_key"]),
            "display_name": str(row["display_name"]),
            "availability": _quantize2(_d(row["availability"])),
            "severity": _quantize2(_d(row["severity"])),
        }
        for row in node_snapshots
        if _d(row["availability"]) < BOTTLENECK_THRESHOLD
    ]

    items.sort(key=lambda row: (-row["severity"], row["availability"], row["node_key"]))
    return items[:BOTTLENECK_MAX_ITEMS]


def _compute_job_pressure(
    normalized_inputs: dict[str, Decimal],
    node_snapshots: list[dict[str, Any]],
    basket_supply: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_node = {str(s["node_key"]): _d(s["availability"]) for s in node_snapshots}
    by_basket = {str(b["basket_key"]): _d(b["supply_multiplier"]) for b in basket_supply}

    def weakness(node_key: str) -> Decimal:
        return max(ZERO, ONE - _d(by_node.get(node_key, ONE)))

    def basket_weakness(basket_key: str) -> Decimal:
        return max(ZERO, ONE - _d(by_basket.get(basket_key, ONE)))

    confidence_weakness = _d(normalized_inputs.get("confidence_weakness", ZERO))
    confidence_support = _d(normalized_inputs.get("confidence_support", ZERO))
    inflation_pressure = _d(normalized_inputs.get("inflation_pressure", ZERO))
    interest_pressure = _d(normalized_inputs.get("interest_pressure", ZERO))
    supply_stress_pressure = _d(normalized_inputs.get("supply_stress_pressure", ZERO))
    oil_pressure = _d(normalized_inputs.get("oil_pressure", ZERO))

    logistics_tightness = weakness("trucking") + (weakness("fuel") * Decimal("0.70")) + (
        supply_stress_pressure * Decimal("0.25")
    )
    logistics_collapse_penalty = max(ZERO, weakness("trucking") - Decimal("0.18")) * Decimal("0.90")

    food_cost_stress = (
        basket_weakness("produce") * Decimal("0.45")
        + basket_weakness("protein") * Decimal("0.30")
        + basket_weakness("essentials") * Decimal("0.25")
    )

    raw_pressure = {
        "delivery_driver": (
            (logistics_tightness * Decimal("0.85"))
            - logistics_collapse_penalty
            - (confidence_weakness * Decimal("0.06"))
        ),
        "retail_worker": (
            -(
                (weakness("retail") * Decimal("0.80"))
                + (confidence_weakness * Decimal("0.22"))
                + (inflation_pressure * Decimal("0.12"))
            )
            + (confidence_support * Decimal("0.08"))
        ),
        "chef": (
            -((food_cost_stress * Decimal("0.70")) + (confidence_weakness * Decimal("0.12")))
            + (confidence_support * Decimal("0.06"))
        ),
        "banker": (
            -(confidence_weakness * Decimal("0.12"))
            - (supply_stress_pressure * Decimal("0.04"))
            + (interest_pressure * Decimal("0.08"))
            + (inflation_pressure * Decimal("0.03"))
        ),
        "auto_mechanic": (
            (weakness("trucking") * Decimal("0.35"))
            + (weakness("fuel") * Decimal("0.25"))
            + (supply_stress_pressure * Decimal("0.08"))
            - (confidence_weakness * Decimal("0.05"))
        ),
        "aircraft_mechanic": (
            (weakness("utilities") * Decimal("0.04"))
            + (supply_stress_pressure * Decimal("0.03"))
            + (oil_pressure * Decimal("0.03"))
            - (confidence_weakness * Decimal("0.02"))
        ),
    }

    rows: list[dict[str, Any]] = []
    for job_key in JOB_KEYS:
        pressure = _clamp_decimal(_q4(raw_pressure.get(job_key, ZERO)), JOB_PRESSURE_MIN, JOB_PRESSURE_MAX)
        if pressure >= JOB_DIRECTION_THRESHOLD:
            direction = "up"
        elif pressure <= (JOB_DIRECTION_THRESHOLD * Decimal("-1")):
            direction = "down"
        else:
            direction = "neutral"

        rows.append(
            {
                "job_key": str(job_key),
                "pressure": pressure,
                "direction": direction,
            }
        )
    return rows


def compute_supply_chain_daily_snapshot(
    db: Session,
    as_of_date: date | None = None,
    macro_day: int | None = None,
) -> dict[str, Any]:
    """Compute deterministic supply-chain signals from the latest macro context.

    This function is compute-only for Step 13 and does not mutate player, pricing,
    or wage tables.
    """
    if macro_day is not None and int(macro_day) <= 0:
        raise SupplyChainValidationError("macro_day must be greater than 0.")

    macro_state = _get_macro_state_for_day(db, macro_day=macro_day)
    if macro_state is None:
        macro_state = _get_macro_state_for_date(db, as_of_date=as_of_date)
    if macro_state is None:
        raise SupplyChainNotFoundError("No macro state found for supply-chain compute.")

    normalized_inputs = _normalize_macro_inputs(macro_state)
    node_snapshots = _compute_all_node_availability(normalized_inputs)
    basket_supply = _compute_basket_supply(node_snapshots)
    bottlenecks = _compute_bottlenecks(node_snapshots)
    job_pressure = _compute_job_pressure(normalized_inputs, node_snapshots, basket_supply)

    payload_as_of_date = (
        as_of_date
        if as_of_date is not None
        else (macro_state.created_at.date() if macro_state.created_at else date.today())
    )

    return {
        "as_of_date": payload_as_of_date,
        "macro_state_id": int(macro_state.id),
        "node_snapshots": [
            {
                "node_key": str(row["node_key"]),
                "display_name": str(row["display_name"]),
                "availability": float(_quantize2(_d(row["availability"]))),
                "severity": float(_quantize2(_d(row["severity"]))),
                "drivers": {
                    k: float(_quantize2(_d(v)))
                    for k, v in row["drivers"].items()
                },
                "depends_on": [str(dep) for dep in row["depends_on"]],
            }
            for row in node_snapshots
        ],
        "basket_supply": [
            {
                "basket_key": str(row["basket_key"]),
                "supply_multiplier": float(_quantize2(_d(row["supply_multiplier"]))),
                "dominant_nodes": [str(node) for node in row["dominant_nodes"]],
            }
            for row in basket_supply
        ],
        "bottlenecks": [
            {
                "node_key": str(row["node_key"]),
                "display_name": str(row["display_name"]),
                "availability": float(_quantize2(_d(row["availability"]))),
                "severity": float(_quantize2(_d(row["severity"]))),
            }
            for row in bottlenecks
        ],
        "job_pressure": [
            {
                "job_key": str(row["job_key"]),
                "pressure": float(_quantize2(_d(row["pressure"]))),
                "direction": str(row["direction"]),
            }
            for row in job_pressure
        ],
        "debug_meta": {
            "constants_version": CONSTANTS_VERSION,
            "macro_day": int(macro_state.day),
            "raw_macro_inputs": {
                "inflation_rate": float(_quantize2(_d(macro_state.inflation_rate))),
                "interest_rate": float(_quantize2(_d(macro_state.interest_rate))),
                "unemployment_rate": float(_quantize2(_d(macro_state.unemployment_rate))),
                "oil_index": float(_quantize2(_d(macro_state.oil_index))),
                "consumer_confidence": float(_quantize2(_d(macro_state.consumer_confidence))),
                "supply_chain_stress": float(_quantize2(_d(macro_state.supply_chain_stress))),
            },
            "normalized_macro_inputs": {
                key: float(_quantize2(value))
                for key, value in normalized_inputs.items()
                if key
                not in {
                    "inflation_rate",
                    "interest_rate",
                    "unemployment_rate",
                    "oil_index",
                    "consumer_confidence",
                    "supply_chain_stress",
                }
            },
            "clamp_bounds": {
                "node_availability_min": float(
                    min(_d(node_def["min_availability"]) for node_def in SUPPLY_CHAIN_NODES.values())
                ),
                "node_availability_max": float(
                    max(_d(node_def["max_availability"]) for node_def in SUPPLY_CHAIN_NODES.values())
                ),
                "basket_multiplier_min": float(BASKET_MIN_MULTIPLIER),
                "basket_multiplier_max": float(BASKET_MAX_MULTIPLIER),
                "job_pressure_min": float(JOB_PRESSURE_MIN),
                "job_pressure_max": float(JOB_PRESSURE_MAX),
                "bottleneck_threshold": float(BOTTLENECK_THRESHOLD),
            },
            "basket_structural_adjustment": {
                key: float(value) for key, value in BASKET_STRUCTURAL_ADJUSTMENT.items()
            },
        },
    }
