"""app/schemas/__init__.py — Step 15: Pydantic schemas for the Gold Penny API.

All schemas follow the convention:
  - <Model>Base  — shared read/write fields (used as base for Create and Read)
  - <Model>Create — fields required when creating a new resource
  - <Model>      — full read schema including server-set fields (id, timestamps)

UUID fields are serialized as strings for JSON compatibility.
Monetary fields use float in schemas (precision held at the DB layer).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ── Shared config ──────────────────────────────────────────────────────────────

class _OrmBase(BaseModel):
    """All schemas that map to ORM rows inherit this to enable from_attributes."""
    model_config = ConfigDict(from_attributes=True)


# ── Player ─────────────────────────────────────────────────────────────────────

class PlayerBase(_OrmBase):
    display_name: Optional[str] = None
    region: str = "suburban"
    cash: float = 1000.0
    credit_score: int = 650
    reputation: int = 0
    health: int = 100
    stress: int = 0
    hours_available: int = 24
    main_job: Optional[str] = None
    side_job: Optional[str] = None
    net_worth: float = 1000.0
    has_active_housing: bool = False


class PlayerCreate(PlayerBase):
    user_id: UUID


class Player(PlayerBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    successful_coop_deals_count: int = 0
    failed_coop_deals_count: int = 0


# ── MacroDailyState ────────────────────────────────────────────────────────────

class MacroDailyStateBase(_OrmBase):
    day_number: int
    inflation: float
    interest_rate: float
    unemployment: float
    oil_index: float
    consumer_confidence: float
    supply_chain_stress: float


class MacroDailyState(MacroDailyStateBase):
    id: int
    is_active: bool
    created_at: datetime


# ── BasketDailyPrice ───────────────────────────────────────────────────────────

class BasketDailyPriceBase(_OrmBase):
    basket_id: str
    day_number: int
    old_price_index: float
    new_price_index: float
    change_percent: float
    inflation_used: float
    oil_index_used: float
    consumer_confidence_used: float
    supply_chain_stress_used: float


class BasketDailyPrice(BasketDailyPriceBase):
    id: UUID
    created_at: datetime


# ── StockDailyPrice ────────────────────────────────────────────────────────────

class StockDailyPriceBase(_OrmBase):
    stock_id: str
    day_number: int
    open_price: float
    close_price: float
    daily_change_pct: float


class StockDailyPrice(StockDailyPriceBase):
    id: UUID
    macro_sensitivity_used: Optional[float] = None
    noise_component: Optional[float] = None
    created_at: datetime


# ── PlayerStockHolding ─────────────────────────────────────────────────────────

class PlayerStockHoldingBase(_OrmBase):
    player_id: UUID
    stock_id: str
    shares_owned: int = 0
    average_cost_basis: float = 0.0
    total_cost_basis: float = 0.0


class PlayerStockHolding(PlayerStockHoldingBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


# ── StockTradeLog ──────────────────────────────────────────────────────────────

class StockTradeLogBase(_OrmBase):
    player_id: UUID
    stock_id: str
    day_number: int
    trade_type: str        # "buy" | "sell"
    shares: int
    price_per_share: float
    gross_amount: float
    transaction_fee: float
    net_amount: float
    balance_before: float
    balance_after: float


class StockTradeLog(StockTradeLogBase):
    id: UUID
    created_at: datetime


# ── DailySettlementLog ─────────────────────────────────────────────────────────

class DailySettlementLogBase(_OrmBase):
    player_id: UUID
    day_number: int
    hours_before_reset: int
    hours_after_reset: int
    stress_before: int
    stress_after: int
    health_before: int
    health_after: int
    cash_before: float
    cash_after: float
    recovery_applied: bool = True


class DailySettlementLog(DailySettlementLogBase):
    id: UUID
    needs_score: float = 0.0
    needs_tier: Optional[str] = None
    food_quality_modifier: int = 0
    stress_penalty_from_needs: int = 0
    created_at: datetime


# ── Job (read-only, derived from Python catalog) ───────────────────────────────

class JobSummary(_OrmBase):
    name: str
    category: str
    monthly_salary: float
    base_stress: int
    stability: float
    growth: float
    layoff_risk: float
    physical_load: float
    mental_load: float
