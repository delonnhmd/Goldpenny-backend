"""Economy-coupled side-income formulas (Step 15 MVP)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256

from app.engine.balance_config import RIDESHARE_GUARDRAILS

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

REGION_BASE_RATE_XGP = {
    "downtown": Decimal("22.00"),
    "suburban": Decimal("18.00"),
    "rural": Decimal("16.50"),
}

GAS_BASE_PRICE_XGP = Decimal("3.20")
MILES_PER_HOUR = Decimal("20.0")
BASE_MPG = Decimal("28.0")
WEAR_BASE_PER_HOUR = Decimal("1.10")
WEAR_MILEAGE_FACTOR = Decimal("0.025")


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _deterministic_ratio(seed: str) -> Decimal:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return Decimal(n) / Decimal((16**16) - 1)


def compute_rideshare_shift(
    *,
    player_seed: str,
    day_number: int,
    region_key: str,
    hours_worked: int,
    oil_index: Decimal,
    consumer_confidence: Decimal,
    unemployment_rate: Decimal,
    reliability: Decimal,
    productivity_modifier: Decimal = Decimal("1.00"),
    region_side_income_modifier: Decimal = Decimal("1.00"),
    opportunity_access_penalty: Decimal = Decimal("0.00"),
) -> dict[str, Decimal | bool]:
    """Compute deterministic rideshare economics for a single shift."""
    hours_decimal = _clamp(_d(hours_worked), Decimal("0.0"), _d(RIDESHARE_GUARDRAILS["hard_hour_cap"]))
    region = (region_key or "suburban").strip().lower()
    base_rate = REGION_BASE_RATE_XGP.get(region, REGION_BASE_RATE_XGP["suburban"])

    pressure_from_jobs = _clamp((unemployment_rate - Decimal("5.0")) / Decimal("10.0"), Decimal("-0.20"), Decimal("0.50"))
    pressure_from_confidence = _clamp((Decimal("60.0") - consumer_confidence) / Decimal("100.0"), Decimal("-0.10"), Decimal("0.30"))
    demand_spike = _q4(
        (_deterministic_ratio(f"{player_seed}:{day_number}:rideshare_spike") * Decimal("0.08")) - Decimal("0.01")
    )
    demand_multiplier = _clamp(
        Decimal("1.00") + pressure_from_jobs + pressure_from_confidence + demand_spike,
        Decimal("0.70"),
        Decimal("1.80"),
    )
    region_density_modifier = _clamp(_d(region_side_income_modifier), Decimal("0.90"), Decimal("1.15"))
    opportunity_penalty = _clamp(_d(opportunity_access_penalty), Decimal("0.00"), Decimal("0.30"))
    financial_access_factor = _clamp(Decimal("1.00") - (opportunity_penalty * Decimal("0.55")), Decimal("0.80"), Decimal("1.00"))
    demand_multiplier = _clamp(demand_multiplier * region_density_modifier * financial_access_factor, Decimal("0.70"), Decimal("1.85"))

    # Step 21 anti-exploit guardrail: sustained same-day rideshare hours have
    # diminishing returns instead of linear scaling forever.
    soft_cap = _d(RIDESHARE_GUARDRAILS["soft_hour_cap"])
    extra_hours = max(Decimal("0.0"), hours_decimal - soft_cap)
    grind_fatigue_factor = _clamp(
        Decimal("1.00") - (extra_hours * _d(RIDESHARE_GUARDRAILS["diminish_per_extra_hour"])),
        _d(RIDESHARE_GUARDRAILS["min_output_factor"]),
        Decimal("1.00"),
    )

    labor_efficiency_modifier = _clamp(
        Decimal("1.00") + ((_d(productivity_modifier) - Decimal("1.00")) * Decimal("0.60")),
        Decimal("0.82"),
        Decimal("1.03"),
    )
    gross_per_hour = _q4(base_rate * demand_multiplier * labor_efficiency_modifier * grind_fatigue_factor)
    gas_price = _q4(GAS_BASE_PRICE_XGP * (oil_index / Decimal("100.0")))
    gas_cost_per_hour = _q4((MILES_PER_HOUR / BASE_MPG) * gas_price)
    wear_cost_per_hour = _q4(WEAR_BASE_PER_HOUR + (WEAR_MILEAGE_FACTOR * MILES_PER_HOUR))

    gross_income = _money(gross_per_hour * hours_decimal)
    gas_cost = _money(gas_cost_per_hour * hours_decimal)
    wear_cost = _money(wear_cost_per_hour * hours_decimal)

    mileage_today = MILES_PER_HOUR * hours_decimal
    maintenance_prob = _clamp(
        Decimal("0.02")
        + (mileage_today / Decimal("200"))
        + ((Decimal("1.0") - reliability) * Decimal("0.02"))
        + (extra_hours * _d(RIDESHARE_GUARDRAILS["maintenance_risk_per_extra_hour"])),
        Decimal("0.01"),
        Decimal("0.35"),
    )
    maintenance_roll = _deterministic_ratio(f"{player_seed}:{day_number}:rideshare_maintenance")
    maintenance_triggered = maintenance_roll < maintenance_prob
    maintenance_cost = Decimal("0.00")
    if maintenance_triggered:
        maintenance_cost = _money(
            _clamp(
                Decimal("8.00") + (mileage_today * Decimal("0.08")),
                Decimal("8.00"),
                Decimal("45.00"),
            )
        )

    net_income = _money(gross_income - gas_cost - wear_cost - maintenance_cost)
    net_per_hour = _q4(net_income / max(Decimal("1.0"), hours_decimal))

    reliability_after = reliability
    if maintenance_triggered:
        reliability_after = _clamp(reliability - Decimal("0.015"), Decimal("0.70"), Decimal("1.00"))
    else:
        reliability_after = _clamp(reliability - (Decimal("0.0020") * hours_decimal), Decimal("0.70"), Decimal("1.00"))

    return {
        "demand_multiplier": _q4(demand_multiplier),
        "region_side_income_modifier": _q4(region_density_modifier),
        "opportunity_access_penalty": _q4(opportunity_penalty),
        "financial_access_factor": _q4(financial_access_factor),
        "labor_efficiency_modifier": _q4(labor_efficiency_modifier),
        "grind_fatigue_factor": _q4(grind_fatigue_factor),
        "hours_soft_cap": _q4(soft_cap),
        "hours_after_soft_cap": _q4(extra_hours),
        "productivity_modifier": _q4(_d(productivity_modifier)),
        "gross_per_hour_xgp": _q4(gross_per_hour),
        "gross_income_xgp": _money(gross_income),
        "gas_price_xgp": _q4(gas_price),
        "gas_cost_per_hour_xgp": _q4(gas_cost_per_hour),
        "gas_cost_xgp": _money(gas_cost),
        "wear_cost_per_hour_xgp": _q4(wear_cost_per_hour),
        "wear_cost_xgp": _money(wear_cost),
        "maintenance_probability": _q4(maintenance_prob),
        "maintenance_roll": _q4(maintenance_roll),
        "maintenance_triggered": bool(maintenance_triggered),
        "maintenance_cost_xgp": _money(maintenance_cost),
        "net_income_xgp": _money(net_income),
        "net_per_hour_xgp": _q4(net_per_hour),
        "reliability_before": _q4(reliability),
        "reliability_after": _q4(reliability_after),
    }
