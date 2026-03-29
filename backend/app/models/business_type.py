"""app/models/business_type.py — Step 10: DB-backed business type catalog.

Each BusinessType row defines what a small business costs to operate
each day: which basket inputs it consumes, how much base revenue it
generates, how many player hours it uses, and how it affects stress.

Economic context:
  Businesses convert daily labor + basket inputs into profit.
  The base_revenue is then adjusted by macro conditions (confidence /
  unemployment) in the business engine, making profitability dynamic.
  Input costs come from the live basket price system, so oil and inflation
  affect running costs just like they affect living costs.

Two businesses ship in MVP:
  - fruit_shop  — produce-heavy, low inputs, moderate revenue
  - food_truck  — multi-input, higher revenue, more risk via oil prices

Seeding is idempotent (get_or_seed_business_types in business_engine.py).
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class BusinessType(Base):
    """Catalog entry for one kind of player-owned business."""

    __tablename__ = "business_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Stable short identifier used throughout the codebase.
    # e.g. "fruit_shop", "food_truck"
    business_id = Column(String(40), unique=True, nullable=False, index=True)

    # Frontend-facing name shown in UI.
    display_name = Column(String(80), nullable=False)

    # ── Basket inputs consumed per operation ──────────────────────────────────
    # The engine multiplies these by the live basket unit price to compute
    # total input_cost_xgp each time the player operates the business.
    # Zero means that basket is not required.
    input_produce_units    = Column(Integer, nullable=False, default=0)
    input_essentials_units = Column(Integer, nullable=False, default=0)
    input_protein_units    = Column(Integer, nullable=False, default=0)

    # ── Revenue and cost parameters ───────────────────────────────────────────
    # base_revenue: XGP revenue before macro adjustment.
    # Actual revenue = base_revenue * confidence_factor * unemployment_factor.
    base_revenue = Column(Numeric(10, 2), nullable=False, default=0.0)

    # Player time consumed per operation (hours subtracted from hours_available).
    hours_required = Column(Integer, nullable=False, default=4)

    # Stress added to the player on each operation.
    # Business = opportunity/risk, not a stress-free activity.
    stress_change = Column(Integer, nullable=False, default=2)

    # XGP cost to start this business (deducted once at launch).
    startup_cost = Column(Numeric(10, 2), nullable=False, default=0.0)

    # Inactive types cannot be started by players.
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Step 11 balancing metadata ────────────────────────────────────────────
    # fixed_overhead_xgp: mandatory operating cost per run (XGP), always deducted.
    #   Makes businesses fragile — thin margins disappear fast.
    fixed_overhead_xgp = Column(Numeric(10, 2), nullable=False, default=0.0)

    # base_demand_factor: starting point for demand multiplier (normally 1.0).
    base_demand_factor = Column(Numeric(8, 4), nullable=False, default=1.0)

    # saturation_penalty_rate: fractional revenue reduction per repeated same-day run.
    #   0.18 → second run loses 18% efficiency, third loses 36%, etc.
    saturation_penalty_rate = Column(Numeric(8, 4), nullable=False, default=0.0)

    # confidence_sensitivity: how strongly consumer confidence shifts demand.
    confidence_sensitivity = Column(Numeric(8, 4), nullable=False, default=0.0)

    # unemployment_sensitivity: how strongly unemployment suppresses demand.
    unemployment_sensitivity = Column(Numeric(8, 4), nullable=False, default=0.0)

    # oil_margin_sensitivity: how much oil price spikes compress profit margins.
    #   food_truck is fuel-intensive so gets a higher value.
    oil_margin_sensitivity = Column(Numeric(8, 4), nullable=False, default=0.0)

    # input_cost_pressure_weight: how much expensive inputs (relative to revenue)
    #   compress margins.  Higher = more exposed to supply-chain volatility.
    input_cost_pressure_weight = Column(Numeric(8, 4), nullable=False, default=0.0)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ── Canonical seed data ───────────────────────────────────────────────────────
# Used by get_or_seed_business_types() in business_engine.py.
DEFAULT_BUSINESS_TYPES: list[dict] = [
    {
        "business_id": "fruit_shop",
        "display_name": "Fruit Shop",
        # Fruit shop only needs produce — simple input chain.
        # Produce prices react strongly to oil and supply chains,
        # so operating costs fluctuate with the macro environment.
        "input_produce_units":    2,
        "input_essentials_units": 0,
        "input_protein_units":    0,
        "base_revenue":           55.0,
        "hours_required":           6,
        "stress_change":            2,
        "startup_cost":             300.0,
        # Step 11 balancing
        "fixed_overhead_xgp":       8.0,
        "base_demand_factor":       1.0,
        "saturation_penalty_rate":  0.18,
        "confidence_sensitivity":   0.20,
        "unemployment_sensitivity": 0.25,
        "oil_margin_sensitivity":   0.05,
        "input_cost_pressure_weight": 0.55,
    },
    {
        "business_id": "food_truck",
        "display_name": "Food Truck",
        # Food truck uses three basket types: essentials + protein + produce(1).
        # Higher input diversity means more exposure to supply-chain volatility.
        # Fuel sensitivity is implicit — produce and essentials both carry
        # oil_sensitivity, so oil spikes hurt the truck more than the shop.
        "input_produce_units":    1,
        "input_essentials_units": 1,
        "input_protein_units":    2,
        "base_revenue":           85.0,
        "hours_required":         8,
        "stress_change":          4,
        "startup_cost":           600.0,
        # Step 11 balancing
        "fixed_overhead_xgp":       15.0,
        "base_demand_factor":       1.0,
        "saturation_penalty_rate":  0.22,
        "confidence_sensitivity":   0.30,
        "unemployment_sensitivity": 0.30,
        "oil_margin_sensitivity":   0.25,
        "input_cost_pressure_weight": 0.70,
    },
]
