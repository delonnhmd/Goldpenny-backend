"""app/api/internal.py — Step 14: Internal admin API for the Firm Layer.

These routes are NOT player-facing.  They exist for:
  - Admin dashboards and monitoring
  - Automated backend health checks
  - Simulation debugging

Security: every request must supply the X-Internal-Key header matching the
INTERNAL_API_KEY environment variable.  If INTERNAL_API_KEY is not set, ALL
requests are rejected with 503.  This prevents accidental exposure.

Route overview
--------------
GET /internal/firms                         — List firms (with optional filters)
GET /internal/firms/{firm_id}               — Firm detail with capacity and policy
GET /internal/job-openings                  — Browse job openings
GET /internal/firms/{firm_id}/ledger        — Firm ledger entries (filterable)
GET /internal/firms/{firm_id}/balance-history — Daily balance snapshots
"""

from __future__ import annotations

from datetime import date, timedelta
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.balance_report_service import build_balance_report
from app.engine.economy_telemetry_service import (
    EconomyTelemetryError,
    EconomyTelemetryNotFoundError,
    EconomyTelemetryValidationError,
    compute_daily_economy_health_metrics,
    get_player_balance_snapshot,
)
from app.engine.exploit_detection_service import (
    ExploitDetectionError,
    ExploitDetectionNotFoundError,
    ExploitDetectionValidationError,
    get_exploit_report,
)
from app.engine.simulation_service import (
    SimulationNotFoundError,
    SimulationServiceError,
    SimulationValidationError,
    run_player_scenario_simulation,
)
from app.models.firm import Firm
from app.models.firm_balance_snapshot import FirmBalanceSnapshot
from app.models.firm_capacity import FirmCapacity
from app.models.firm_ledger_entry import FirmLedgerEntry
from app.models.firm_policy import FirmPolicy
from app.models.goods_basket import GoodsBasket
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.job_opening import JobOpening
from app.models.macro_daily_state import MacroDailyState
from app.models.macro_state import MacroState
from app.models.basket_price_history import BasketPriceHistory
from app.models.basket_daily_price import BasketDailyPrice
from app.models.player import Player
from app.models.sector_stock import SectorStock
from app.models.stock_price_history import StockPriceHistory
from app.models.stock_daily_price import StockDailyPrice
from app.models.user import User
from app.services.admin_debug_service import (
    AdminDebugError,
    AdminDebugNotFoundError,
    AdminDebugValidationError,
    force_macro_scenario,
    force_player_debug_state,
    get_economy_debug_snapshot,
    get_full_player_debug_snapshot,
    reset_player_to_starter_state,
)

router = APIRouter()

CORE_SECURITY_TABLES: tuple[str, ...] = (
    "alembic_version",
    "users",
    "players",
    "player_daily_states",
    "player_stock_holdings",
    "daily_settlement_logs",
    "macro_daily_states",
    "basket_daily_prices",
    "stock_daily_prices",
    "player_employment_states",
    "job_definitions",
    "stock_trade_logs",
)


# ── Security ───────────────────────────────────────────────────────────────────


def _require_internal_key(x_internal_key: str = Header(default="")) -> None:
    """Validate X-Internal-Key header against INTERNAL_API_KEY env var.

    Returns 503 if INTERNAL_API_KEY is not configured (fail-closed).
    Returns 403 if the key does not match.
    """
    expected = os.getenv("INTERNAL_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API is disabled (INTERNAL_API_KEY not configured).",
        )
    if x_internal_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key.",
        )


# ── Response schemas ───────────────────────────────────────────────────────────


class FirmSummary(BaseModel):
    id: int
    name: str
    owner_type: str
    firm_type: str
    region: str
    tier: int
    status: str
    reputation: float
    cash_xgp: float
    retained_earnings_xgp: float
    distress_level: int
    created_day: int


class FirmDetail(FirmSummary):
    capacities: list[dict]
    policy: Optional[dict]


class JobOpeningSummary(BaseModel):
    id: int
    firm_id: Optional[int]
    region: str
    job_type: str
    slots_total: int
    slots_filled: int
    wage_offer_xgp: float
    demand_multiplier: float
    source_type: str
    status: str
    created_day: int
    expires_day: Optional[int]


class LedgerEntryOut(BaseModel):
    day: int
    category: str
    direction: str
    amount_xgp: float
    memo: Optional[str]


class BalanceSnapshotOut(BaseModel):
    day: int
    cash_xgp: float
    inventory_value_xgp: float
    equity_estimate_xgp: float
    runway_days: Optional[int]


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get(
    "/firms",
    response_model=list[FirmSummary],
    summary="List all firms",
    dependencies=[Depends(_require_internal_key)],
)
def list_firms(
    region: Optional[str] = Query(None, description="Filter by region"),
    firm_type: Optional[str] = Query(None, description="Filter by firm_type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
) -> list[FirmSummary]:
    q = db.query(Firm)
    if region:
        q = q.filter(Firm.region == region)
    if firm_type:
        q = q.filter(Firm.firm_type == firm_type)
    if status_filter:
        q = q.filter(Firm.status == status_filter)
    firms = q.order_by(Firm.id.asc()).all()
    return [
        FirmSummary(
            id=f.id,
            name=f.name,
            owner_type=f.owner_type,
            firm_type=f.firm_type,
            region=f.region,
            tier=f.tier,
            status=f.status,
            reputation=float(f.reputation),
            cash_xgp=float(f.cash_xgp),
            retained_earnings_xgp=float(f.retained_earnings_xgp),
            distress_level=f.distress_level,
            created_day=f.created_day,
        )
        for f in firms
    ]


@router.get(
    "/firms/{firm_id}",
    response_model=FirmDetail,
    summary="Firm detail with capacity and policy",
    dependencies=[Depends(_require_internal_key)],
)
def get_firm(
    firm_id: int,
    db: Session = Depends(get_db),
) -> FirmDetail:
    firm = db.query(Firm).filter(Firm.id == firm_id).first()
    if firm is None:
        raise HTTPException(status_code=404, detail="Firm not found.")

    caps = db.query(FirmCapacity).filter(FirmCapacity.firm_id == firm_id).all()
    policy = db.query(FirmPolicy).filter(FirmPolicy.firm_id == firm_id).first()

    caps_out = [
        {
            "capacity_type":   c.capacity_type,
            "base_capacity":   float(c.base_capacity),
            "current_capacity": float(c.current_capacity),
            "utilization":     float(c.utilization),
            "maintenance_state": c.maintenance_state,
            "reliability":     float(c.reliability),
        }
        for c in caps
    ]
    policy_out = None
    if policy:
        policy_out = {
            "hiring_aggressiveness":   float(policy.hiring_aggressiveness),
            "wage_strategy":           policy.wage_strategy,
            "inventory_buffer_target": float(policy.inventory_buffer_target),
            "debt_tolerance":          float(policy.debt_tolerance),
            "expansion_threshold":     float(policy.expansion_threshold),
            "is_active":               policy.is_active,
        }

    return FirmDetail(
        id=firm.id,
        name=firm.name,
        owner_type=firm.owner_type,
        firm_type=firm.firm_type,
        region=firm.region,
        tier=firm.tier,
        status=firm.status,
        reputation=float(firm.reputation),
        cash_xgp=float(firm.cash_xgp),
        retained_earnings_xgp=float(firm.retained_earnings_xgp),
        distress_level=firm.distress_level,
        created_day=firm.created_day,
        capacities=caps_out,
        policy=policy_out,
    )


@router.get(
    "/job-openings",
    response_model=list[JobOpeningSummary],
    summary="Browse job openings",
    dependencies=[Depends(_require_internal_key)],
)
def list_job_openings(
    region: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    open_only: bool = Query(True, description="Only return status='open' openings"),
    db: Session = Depends(get_db),
) -> list[JobOpeningSummary]:
    q = db.query(JobOpening)
    if region:
        q = q.filter(JobOpening.region == region)
    if job_type:
        q = q.filter(JobOpening.job_type == job_type)
    if open_only:
        q = q.filter(JobOpening.status == "open")
    openings = q.order_by(JobOpening.id.asc()).all()
    return [
        JobOpeningSummary(
            id=o.id,
            firm_id=o.firm_id,
            region=o.region,
            job_type=o.job_type,
            slots_total=o.slots_total,
            slots_filled=o.slots_filled,
            wage_offer_xgp=float(o.wage_offer_xgp),
            demand_multiplier=float(o.demand_multiplier),
            source_type=o.source_type,
            status=o.status,
            created_day=o.created_day,
            expires_day=o.expires_day,
        )
        for o in openings
    ]


@router.get(
    "/firms/{firm_id}/ledger",
    response_model=list[LedgerEntryOut],
    summary="Get a firm's accounting ledger entries",
    dependencies=[Depends(_require_internal_key)],
)
def get_firm_ledger(
    firm_id: int,
    day_from: Optional[int] = Query(None, description="Filter from this in-game day (inclusive)"),
    day_to: Optional[int] = Query(None, description="Filter up to this in-game day (inclusive)"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. 'payroll')"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[LedgerEntryOut]:
    firm = db.query(Firm).filter(Firm.id == firm_id).first()
    if firm is None:
        raise HTTPException(status_code=404, detail="Firm not found.")

    q = db.query(FirmLedgerEntry).filter(FirmLedgerEntry.firm_id == firm_id)
    if day_from is not None:
        q = q.filter(FirmLedgerEntry.day >= day_from)
    if day_to is not None:
        q = q.filter(FirmLedgerEntry.day <= day_to)
    if category:
        q = q.filter(FirmLedgerEntry.category == category)

    entries = (
        q.order_by(FirmLedgerEntry.day.desc(), FirmLedgerEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        LedgerEntryOut(
            day=e.day,
            category=e.category,
            direction=e.direction,
            amount_xgp=float(e.amount_xgp),
            memo=e.memo,
        )
        for e in entries
    ]


@router.get(
    "/firms/{firm_id}/balance-history",
    response_model=list[BalanceSnapshotOut],
    summary="Get a firm's daily balance sheet history",
    dependencies=[Depends(_require_internal_key)],
)
def get_firm_balance_history(
    firm_id: int,
    last_n_days: int = Query(30, ge=1, le=365, description="Number of most recent days to return"),
    db: Session = Depends(get_db),
) -> list[BalanceSnapshotOut]:
    firm = db.query(Firm).filter(Firm.id == firm_id).first()
    if firm is None:
        raise HTTPException(status_code=404, detail="Firm not found.")

    snapshots = (
        db.query(FirmBalanceSnapshot)
        .filter(FirmBalanceSnapshot.firm_id == firm_id)
        .order_by(FirmBalanceSnapshot.day.desc())
        .limit(last_n_days)
        .all()
    )
    return [
        BalanceSnapshotOut(
            day=s.day,
            cash_xgp=float(s.cash_xgp),
            inventory_value_xgp=float(s.inventory_value_xgp),
            equity_estimate_xgp=float(s.equity_estimate_xgp),
            runway_days=s.runway_days,
        )
        for s in snapshots
    ]


# ── Bootstrap summary ──────────────────────────────────────────────────────────


class BootstrapSummary(BaseModel):
    total_users: int
    total_players: int
    total_jobs: int
    total_macro_rows: int
    total_basket_rows: int
    total_stock_price_rows: int
    latest_macro_day: Optional[int]


class SecurityTableSummary(BaseModel):
    table_name: str
    rls_expected_enabled: bool
    rls_currently_enabled: Optional[bool]


class SecuritySummaryResponse(BaseModel):
    core_tables: list[SecurityTableSummary]
    policies_open_to_anon_users: bool
    note: str


class InternalPlayerSnapshotResponse(BaseModel):
    player_profile: dict
    active_housing_summary: Optional[dict] = None
    latest_housing_log: Optional[dict] = None
    active_employment_summary: Optional[dict] = None
    latest_job_summary: dict
    latest_consumption_summary: Optional[dict] = None
    latest_debt_credit_summary: Optional[dict] = None
    latest_financial_distress_summary: Optional[dict] = None
    businesses: list[dict]
    latest_business_summary: dict
    latest_side_income_summary: Optional[dict] = None
    latest_life_summary: Optional[dict] = None
    latest_settlement_summary: Optional[dict] = None
    location_chain: dict = Field(default_factory=dict)
    latest_daily_brief: Optional[dict] = None
    latest_portfolio_summary: dict
    balance_profile: dict = Field(default_factory=dict)
    player_balance_snapshot: dict = Field(default_factory=dict)
    exploit_flags: dict = Field(default_factory=dict)
    strategy_classification: dict = Field(default_factory=dict)
    weekly_strategy_summary: dict = Field(default_factory=dict)
    onboarding_state: Optional[dict] = None
    onboarding_state_snapshot: dict = Field(default_factory=dict)
    onboarding_guidance: dict = Field(default_factory=dict)
    onboarding_dashboard_config: dict = Field(default_factory=dict)
    onboarding_unlock_schedule: dict = Field(default_factory=dict)
    onboarding_completion_debug: dict = Field(default_factory=dict)
    progression_state: Optional[dict] = None
    progression_goal_history: list[dict] = Field(default_factory=list)
    progression_summary: dict = Field(default_factory=dict)
    economy_presentation_summary: dict = Field(default_factory=dict)
    strategic_planning_summary: dict = Field(default_factory=dict)
    commitment_state: Optional[dict] = None
    commitment_history: list[dict] = Field(default_factory=list)
    commitment_available: dict = Field(default_factory=dict)
    commitment_summary: dict = Field(default_factory=dict)
    commitment_feedback: dict = Field(default_factory=dict)
    commitment_drift_debug: dict = Field(default_factory=dict)
    commitment_adherence_debug: dict = Field(default_factory=dict)
    commitment_history_snapshot: dict = Field(default_factory=dict)
    world_memory_state: Optional[dict] = None
    world_pattern_history: list[dict] = Field(default_factory=list)
    world_memory_snapshot: dict = Field(default_factory=dict)
    world_pattern_detection: dict = Field(default_factory=dict)
    world_narrative: dict = Field(default_factory=dict)
    world_local_pressure_summary: dict = Field(default_factory=dict)
    world_player_pattern_summary: dict = Field(default_factory=dict)
    world_region_memory_summary: dict = Field(default_factory=dict)
    world_memory_history_snapshot: dict = Field(default_factory=dict)
    world_memory_summary: dict = Field(default_factory=dict)
    financial_delinquency_state_raw: Optional[dict] = None
    financial_latest_payment_history_raw: Optional[dict] = None
    financial_payment_history_raw: list[dict] = Field(default_factory=list)
    financial_obligation_profile: dict = Field(default_factory=dict)
    financial_payment_risk_state: dict = Field(default_factory=dict)
    financial_delinquency_state: dict = Field(default_factory=dict)
    financial_credit_impact: dict = Field(default_factory=dict)
    financial_survival_summary: dict = Field(default_factory=dict)
    financial_payment_history: dict = Field(default_factory=dict)
    financial_survival_system_summary: dict = Field(default_factory=dict)


class InternalEconomySnapshotResponse(BaseModel):
    latest_macro_state: Optional[dict] = None
    latest_basket_day: Optional[int] = None
    latest_basket_daily_prices: list[dict]
    latest_stock_day: Optional[int] = None
    latest_stock_daily_prices_summary: dict
    latest_supply_chain_daily: Optional[dict] = None
    latest_basket_pricing_daily: Optional[dict] = None
    latest_job_market_daily: Optional[dict] = None
    latest_daily_economy_brief: Optional[dict] = None
    top_bottlenecks: list[str] = Field(default_factory=list)
    top_basket_movers: list[str] = Field(default_factory=list)
    top_job_pressure_movers: list[str] = Field(default_factory=list)
    economy_telemetry_snapshot: dict = Field(default_factory=dict)
    system_dominance_flags: dict = Field(default_factory=dict)
    economy_weekly_summary: dict = Field(default_factory=dict)
    economy_presentation_sample_player_id: str | None = None
    economy_presentation_market_overview: dict = Field(default_factory=dict)
    economy_presentation_price_trends: dict = Field(default_factory=dict)
    economy_presentation_business_margins: dict = Field(default_factory=dict)
    economy_presentation_commute_pressure: dict = Field(default_factory=dict)
    economy_presentation_explainer: dict = Field(default_factory=dict)
    economy_presentation_future_teasers: dict = Field(default_factory=dict)
    strategic_planning_sample_player_id: str | None = None
    strategic_planning_summary: dict = Field(default_factory=dict)
    strategic_planning_plans: dict = Field(default_factory=dict)
    strategic_planning_housing_tradeoff: dict = Field(default_factory=dict)
    strategic_planning_debt_vs_growth: dict = Field(default_factory=dict)
    strategic_planning_business_plan: dict = Field(default_factory=dict)
    strategic_planning_recovery_vs_push: dict = Field(default_factory=dict)
    strategic_planning_recommendation: dict = Field(default_factory=dict)
    strategic_planning_future_preparation: dict = Field(default_factory=dict)
    commitment_sample_player_id: str | None = None
    commitment_available: dict = Field(default_factory=dict)
    commitment_summary: dict = Field(default_factory=dict)
    commitment_feedback: dict = Field(default_factory=dict)
    commitment_drift_debug: dict = Field(default_factory=dict)
    commitment_adherence_debug: dict = Field(default_factory=dict)
    world_memory_sample_player_id: str | None = None
    world_memory_snapshot: dict = Field(default_factory=dict)
    world_pattern_detection: dict = Field(default_factory=dict)
    world_narrative: dict = Field(default_factory=dict)
    world_local_pressure_summary: dict = Field(default_factory=dict)
    world_player_pattern_summary: dict = Field(default_factory=dict)
    world_region_memory_summary: dict = Field(default_factory=dict)
    world_memory_history_snapshot: dict = Field(default_factory=dict)
    world_memory_summary: dict = Field(default_factory=dict)
    financial_survival_sample_player_id: str | None = None
    financial_obligation_profile: dict = Field(default_factory=dict)
    financial_payment_risk_state: dict = Field(default_factory=dict)
    financial_delinquency_state: dict = Field(default_factory=dict)
    financial_credit_impact: dict = Field(default_factory=dict)
    financial_survival_summary: dict = Field(default_factory=dict)
    financial_payment_history: dict = Field(default_factory=dict)
    financial_survival_system_summary: dict = Field(default_factory=dict)
    onboarding_sample_player_id: str | None = None
    onboarding_state: dict = Field(default_factory=dict)
    onboarding_guidance: dict = Field(default_factory=dict)
    onboarding_dashboard_config: dict = Field(default_factory=dict)
    onboarding_unlock_schedule: dict = Field(default_factory=dict)
    onboarding_completion_debug: dict = Field(default_factory=dict)
    event_catalog_metadata: dict = Field(default_factory=dict)
    balance_profile: dict = Field(default_factory=dict)
    aggregate_counts: dict


class EconomyTelemetryResponse(BaseModel):
    as_of_date: str
    balance_profile: str
    balance_profile_version: str
    average_basket_inflation_pressure: float
    basket_volatility_index: float
    economy_harshness_score: float
    economy_softness_score: float
    average_distress_burden: float
    average_stress_burden: float
    business_margin_pressure_index: float
    job_opportunity_spread: float
    recovery_success_proxy: float
    dominant_flags: list[str] = Field(default_factory=list)
    debug_meta: dict = Field(default_factory=dict)


class PlayerBalanceSnapshotResponse(BaseModel):
    player_id: str
    as_of_date: str
    days_cash_cushion: float
    debt_pressure_ratio: float
    net_income_stability_score: float
    burnout_danger_score: float
    upward_mobility_score: float
    exploit_flags: dict = Field(default_factory=dict)
    debug_meta: dict = Field(default_factory=dict)


class ExploitFlagsResponse(BaseModel):
    player_id: str
    as_of_date: str
    rideshare_overfarm_flag: bool = False
    food_truck_margin_abuse_flag: bool = False
    fruit_shop_markup_abuse_flag: bool = False
    zero_rest_grind_flag: bool = False
    debt_ignore_abuse_flag: bool = False
    too_fast_promotion_flag: bool = False
    region_switch_abuse_flag: bool = False
    event_chain_prediction_advantage_flag: bool = False
    debug_meta: dict = Field(default_factory=dict)


class SimulationRunRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=90)
    scenario_key: Optional[str] = Field(default=None)


class SimulationRunResponse(BaseModel):
    scenario_key: str
    days: int
    final_cash_xgp: float
    final_net_worth_xgp: float
    avg_stress: float
    avg_health: float
    final_distress_state: str
    promotions_earned: int
    missed_payments: int
    total_business_profit_xgp: float
    strategy_classification: str = "stable_worker"
    strategy_classification_drivers: dict = Field(default_factory=dict)
    business_mode_outcomes: list[dict] = Field(default_factory=list)
    upgrade_roi_signals: dict = Field(default_factory=dict)
    weekly_summary_snapshots: list[dict] = Field(default_factory=list)
    exploit_flags: dict = Field(default_factory=dict)
    telemetry_summary: dict = Field(default_factory=dict)
    debug_meta: dict = Field(default_factory=dict)


class BalanceReportResponse(BaseModel):
    as_of_date: str
    balance_profile: str
    balance_profile_version: str
    top_system_risks: list[str] = Field(default_factory=list)
    dominant_jobs: list = Field(default_factory=list)
    dominant_businesses: list = Field(default_factory=list)
    weak_recovery_areas: list[str] = Field(default_factory=list)
    high_volatility_areas: list[str] = Field(default_factory=list)
    suggested_tuning_targets: list[str] = Field(default_factory=list)
    debug_meta: dict = Field(default_factory=dict)


class MacroScenarioRequest(BaseModel):
    scenario_name: str
    day: Optional[int] = None


class MacroScenarioResponse(BaseModel):
    scenario_name: str
    day: int
    created_new_macro_day: bool = False
    before_macro: Optional[dict] = None
    after_macro: Optional[dict] = None


class PlayerScenarioRequest(BaseModel):
    scenario_name: str


class PlayerScenarioResponse(BaseModel):
    player_id: str
    scenario_name: str
    notes: list[str] = Field(default_factory=list)
    before_player_summary: dict
    after_player_summary: dict


class PlayerResetRequest(BaseModel):
    preserve_profile: bool = True


class PlayerResetResponse(BaseModel):
    player_id: str
    reset_complete: bool
    playable_summary: dict


def _raise_admin_debug_http_error(exc: Exception) -> None:
    if isinstance(exc, AdminDebugNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AdminDebugValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, AdminDebugError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected admin debug service error.")


def _raise_balance_http_error(exc: Exception) -> None:
    if isinstance(exc, (EconomyTelemetryNotFoundError, ExploitDetectionNotFoundError, SimulationNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (EconomyTelemetryValidationError, ExploitDetectionValidationError, SimulationValidationError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, (EconomyTelemetryError, ExploitDetectionError, SimulationServiceError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected balance tooling error.")


@router.get(
    "/bootstrap-summary",
    response_model=BootstrapSummary,
    summary="High-level count of seeded reference data",
)
def bootstrap_summary(db: Session = Depends(get_db)) -> BootstrapSummary:
    """Return row counts for all seeded reference tables.

    Useful for verifying that `python seed.py` completed successfully and
    that the database is in the expected initial state.
    """
    latest_macro = db.query(MacroDailyState.day).order_by(MacroDailyState.day.desc()).scalar()
    return BootstrapSummary(
        total_users=db.query(User).count(),
        total_players=db.query(Player).count(),
        total_jobs=db.query(JobDefinitionDB).count(),
        total_macro_rows=db.query(MacroDailyState).count(),
        total_basket_rows=db.query(BasketDailyPrice).count(),
        total_stock_price_rows=db.query(StockDailyPrice).count(),
        latest_macro_day=latest_macro,
    )


@router.get(
    "/security-summary",
    response_model=SecuritySummaryResponse,
    summary="RLS hardening summary for core public tables",
    dependencies=[Depends(_require_internal_key)],
)
def security_summary(db: Session = Depends(get_db)) -> SecuritySummaryResponse:
    """Return expected RLS posture for core public tables.

    This endpoint documents the deny-by-default setup and helps verify
    migration state in Supabase without opening anon policies yet.
    """
    observed_rls: dict[str, bool] = {}
    note_suffix = ""
    try:
        stmt = sa.text(
            """
            SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND c.relname IN :table_names
            """
        ).bindparams(sa.bindparam("table_names", expanding=True))
        rows = db.execute(stmt, {"table_names": list(CORE_SECURITY_TABLES)}).mappings().all()
        observed_rls = {str(r["table_name"]): bool(r["rls_enabled"]) for r in rows}
    except Exception:
        # Non-Postgres local dev environments may not expose pg_catalog tables.
        note_suffix = " Runtime RLS check is unavailable on the current database dialect."

    return SecuritySummaryResponse(
        core_tables=[
            SecurityTableSummary(
                table_name=table_name,
                rls_expected_enabled=True,
                rls_currently_enabled=observed_rls.get(table_name),
            )
            for table_name in CORE_SECURITY_TABLES
        ],
        policies_open_to_anon_users=False,
        note=(
            "RLS is expected enabled for these core tables (deny-by-default). "
            "Policies are intentionally not opened to anon users yet, and FastAPI remains the primary backend path."
            f"{note_suffix}"
        ),
    )


@router.get(
    "/player/{player_id}/snapshot",
    response_model=InternalPlayerSnapshotResponse,
    summary="Internal debug snapshot for one player",
    dependencies=[Depends(_require_internal_key)],
)
def get_internal_player_snapshot(player_id: str, db: Session = Depends(get_db)) -> InternalPlayerSnapshotResponse:
    try:
        payload = get_full_player_debug_snapshot(db, player_id)
        return InternalPlayerSnapshotResponse(**payload)
    except Exception as exc:
        _raise_admin_debug_http_error(exc)


@router.get(
    "/economy/snapshot",
    response_model=InternalEconomySnapshotResponse,
    summary="Internal debug economy snapshot",
    dependencies=[Depends(_require_internal_key)],
)
def get_internal_economy_snapshot(db: Session = Depends(get_db)) -> InternalEconomySnapshotResponse:
    try:
        payload = get_economy_debug_snapshot(db)
        return InternalEconomySnapshotResponse(**payload)
    except Exception as exc:
        _raise_admin_debug_http_error(exc)


@router.post(
    "/scenario/macro",
    response_model=MacroScenarioResponse,
    summary="Force internal macro scenario for balancing",
    dependencies=[Depends(_require_internal_key)],
)
def force_internal_macro_scenario(
    body: MacroScenarioRequest,
    db: Session = Depends(get_db),
) -> MacroScenarioResponse:
    try:
        payload = force_macro_scenario(db, body.scenario_name, body.day)
        return MacroScenarioResponse(**payload)
    except Exception as exc:
        _raise_admin_debug_http_error(exc)


@router.post(
    "/scenario/player/{player_id}",
    response_model=PlayerScenarioResponse,
    summary="Force internal player debug scenario",
    dependencies=[Depends(_require_internal_key)],
)
def force_internal_player_scenario(
    player_id: str,
    body: PlayerScenarioRequest,
    db: Session = Depends(get_db),
) -> PlayerScenarioResponse:
    try:
        payload = force_player_debug_state(db, player_id, body.scenario_name)
        return PlayerScenarioResponse(**payload)
    except Exception as exc:
        _raise_admin_debug_http_error(exc)


@router.post(
    "/player/{player_id}/reset",
    response_model=PlayerResetResponse,
    summary="Reset player to starter-like debug state",
    dependencies=[Depends(_require_internal_key)],
)
def reset_internal_player_state(
    player_id: str,
    body: Optional[PlayerResetRequest] = None,
    db: Session = Depends(get_db),
) -> PlayerResetResponse:
    try:
        payload = reset_player_to_starter_state(
            db,
            player_id,
            preserve_profile=bool(body.preserve_profile) if body is not None else True,
        )
        return PlayerResetResponse(**payload)
    except Exception as exc:
        _raise_admin_debug_http_error(exc)


@router.get(
    "/balance/telemetry",
    response_model=EconomyTelemetryResponse,
    summary="Internal Step 21 economy telemetry snapshot",
    dependencies=[Depends(_require_internal_key)],
)
def get_internal_balance_telemetry(
    day: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> EconomyTelemetryResponse:
    try:
        as_of_date = None
        if day is not None:
            as_of_date = date(2026, 1, 1) + timedelta(days=int(day) - 1)
        payload = compute_daily_economy_health_metrics(db=db, as_of_date=as_of_date)
        return EconomyTelemetryResponse(**payload)
    except Exception as exc:
        _raise_balance_http_error(exc)


@router.get(
    "/player/{player_id}/balance-snapshot",
    response_model=PlayerBalanceSnapshotResponse,
    summary="Internal Step 21 player viability + exploit snapshot",
    dependencies=[Depends(_require_internal_key)],
)
def get_internal_player_balance_snapshot(
    player_id: str,
    db: Session = Depends(get_db),
) -> PlayerBalanceSnapshotResponse:
    try:
        payload = get_player_balance_snapshot(db=db, player_id=player_id)
        return PlayerBalanceSnapshotResponse(**payload)
    except Exception as exc:
        _raise_balance_http_error(exc)


@router.get(
    "/player/{player_id}/exploit-flags",
    response_model=ExploitFlagsResponse,
    summary="Internal Step 21 exploit flags for one player",
    dependencies=[Depends(_require_internal_key)],
)
def get_internal_player_exploit_flags(
    player_id: str,
    db: Session = Depends(get_db),
) -> ExploitFlagsResponse:
    try:
        payload = get_exploit_report(db=db, player_id=player_id)
        return ExploitFlagsResponse(**payload)
    except Exception as exc:
        _raise_balance_http_error(exc)


@router.post(
    "/simulate/player/{player_id}",
    response_model=SimulationRunResponse,
    summary="Internal Step 21 deterministic player simulation run",
    dependencies=[Depends(_require_internal_key)],
)
def run_internal_player_simulation(
    player_id: str,
    body: SimulationRunRequest,
    db: Session = Depends(get_db),
) -> SimulationRunResponse:
    try:
        payload = run_player_scenario_simulation(
            db=db,
            player_id=player_id,
            days=int(body.days),
            scenario_key=body.scenario_key,
        )
        return SimulationRunResponse(**payload)
    except Exception as exc:
        _raise_balance_http_error(exc)


@router.get(
    "/balance/report",
    response_model=BalanceReportResponse,
    summary="Internal Step 21 balance report",
    dependencies=[Depends(_require_internal_key)],
)
def get_internal_balance_report(
    day: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> BalanceReportResponse:
    try:
        as_of_date = None
        if day is not None:
            as_of_date = date(2026, 1, 1) + timedelta(days=int(day) - 1)
        payload = build_balance_report(db=db, as_of_date=as_of_date)
        return BalanceReportResponse(**payload)
    except Exception as exc:
        _raise_balance_http_error(exc)


# ── Step 68: Day 1 Calibration Layer endpoints ─────────────────────────────────


class Day1BalanceConfigResponse(BaseModel):
    active_preset: str
    active_config: dict
    all_presets: dict


class Day1PresetSetRequest(BaseModel):
    preset: str = Field(
        description="One of: easy, normal, hard, stress_test",
        examples=["normal"],
    )


class Day1PresetSetResponse(BaseModel):
    previous_preset: str
    active_preset: str
    active_config: dict


class Day1SimulationRequest(BaseModel):
    preset: Optional[str] = Field(
        default=None,
        description="Run simulation against a specific preset. Defaults to the active preset.",
    )
    n_sessions: int = Field(default=60, ge=4, le=200)
    seed: int = Field(default=42)


class Day1SessionResult(BaseModel):
    preset_name: str
    job: str
    starting_cash: float
    ending_cash: float
    cash_delta: float
    starting_stress: int
    ending_stress: int
    stress_delta: int
    starting_health: int
    ending_health: int
    health_delta: int
    income_earned: float
    expenses_paid: float
    completed: bool
    had_opportunity: bool


class Day1BatchSimulationResponse(BaseModel):
    preset_name: str
    n_sessions: int
    completion_rate: float
    avg_cash_delta: float
    avg_stress_delta: float
    avg_health_delta: float
    avg_income_earned: float
    avg_expenses_paid: float
    opportunity_rate: float
    min_cash_delta: float
    max_cash_delta: float


# ── Step 70: Soft Launch admin endpoints ──────────────────────────────────────


class SoftLaunchMemberRow(BaseModel):
    user_id: str
    email: str
    cohort_tag: str
    invite_code_used: Optional[str]
    is_approved: bool
    joined_at: Optional[str]


class SoftLaunchCohortResponse(BaseModel):
    total_members: int
    members: list[SoftLaunchMemberRow]


class SoftLaunchMetricsResponse(BaseModel):
    total_soft_launch_members: int
    day1_completion_count: int
    day1_completion_rate: float
    day2_return_count: int
    day2_return_rate: float
    avg_rating: Optional[float]
    total_feedback_submissions: int
    total_issue_reports: int
    high_severity_issues: int


class FeedbackRow(BaseModel):
    feedback_id: str
    player_id: str
    game_day: int
    rating: int
    response_confusing: Optional[str]
    response_hard: Optional[str]
    response_interesting: Optional[str]
    cohort_tag: Optional[str]
    submitted_at: Optional[str]


class FeedbackListResponse(BaseModel):
    total: int
    items: list[FeedbackRow]


class IssueRow(BaseModel):
    issue_id: str
    player_id: str
    game_day: Optional[int]
    description: str
    category: Optional[str]
    severity: Optional[str]
    submitted_at: Optional[str]


class IssueListResponse(BaseModel):
    total: int
    items: list[IssueRow]


@router.get(
    "/soft-launch/cohort",
    response_model=SoftLaunchCohortResponse,
    summary="List all soft launch cohort members",
    dependencies=[Depends(_require_internal_key)],
)
def list_soft_launch_cohort(db: Session = Depends(get_db)) -> SoftLaunchCohortResponse:
    from app.models.soft_launch_member import SoftLaunchMember

    rows = db.query(SoftLaunchMember, User).join(User, SoftLaunchMember.user_id == User.id).all()
    members = [
        SoftLaunchMemberRow(
            user_id=str(m.user_id),
            email=u.email,
            cohort_tag=m.cohort_tag,
            invite_code_used=m.invite_code_used,
            is_approved=m.is_approved,
            joined_at=m.joined_at.isoformat() if m.joined_at else None,
        )
        for m, u in rows
    ]
    return SoftLaunchCohortResponse(total_members=len(members), members=members)


@router.get(
    "/soft-launch/metrics",
    response_model=SoftLaunchMetricsResponse,
    summary="Day 1 completion rate, Day 2 return rate, avg rating, issue counts",
    dependencies=[Depends(_require_internal_key)],
)
def get_soft_launch_metrics(db: Session = Depends(get_db)) -> SoftLaunchMetricsResponse:
    from app.models.daily_settlement_log import DailySettlementLog
    from app.models.player_feedback import PlayerFeedback
    from app.models.issue_report import IssueReport
    from app.models.soft_launch_member import SoftLaunchMember

    total_members = db.query(SoftLaunchMember).count()

    # Soft launch member user_ids → player_ids
    member_user_ids = [
        row.user_id for row in db.query(SoftLaunchMember.user_id).all()
    ]
    if member_user_ids:
        member_player_ids = [
            row.id
            for row in db.query(Player.id).filter(Player.user_id.in_(member_user_ids)).all()
        ]
    else:
        member_player_ids = []

    # Day 1 completion: settled at least day 1
    if member_player_ids:
        day1_completions = (
            db.query(DailySettlementLog.player_id)
            .filter(
                DailySettlementLog.player_id.in_(member_player_ids),
                DailySettlementLog.game_day == 1,
            )
            .distinct()
            .count()
        )
        # Day 2 return: settled day 2 (implies returned after day 1)
        day2_returns = (
            db.query(DailySettlementLog.player_id)
            .filter(
                DailySettlementLog.player_id.in_(member_player_ids),
                DailySettlementLog.game_day == 2,
            )
            .distinct()
            .count()
        )
    else:
        day1_completions = 0
        day2_returns = 0

    day1_rate = round(day1_completions / total_members, 4) if total_members else 0.0
    day2_rate = round(day2_returns / total_members, 4) if total_members else 0.0

    # Feedback stats
    feedback_rows = db.query(PlayerFeedback).all()
    total_feedback = len(feedback_rows)
    avg_rating: Optional[float] = None
    if feedback_rows:
        avg_rating = round(sum(f.rating for f in feedback_rows) / total_feedback, 2)

    total_issues = db.query(IssueReport).count()
    high_severity = (
        db.query(IssueReport)
        .filter(IssueReport.severity.in_(["high", "blocker"]))
        .count()
    )

    return SoftLaunchMetricsResponse(
        total_soft_launch_members=total_members,
        day1_completion_count=day1_completions,
        day1_completion_rate=day1_rate,
        day2_return_count=day2_returns,
        day2_return_rate=day2_rate,
        avg_rating=avg_rating,
        total_feedback_submissions=total_feedback,
        total_issue_reports=total_issues,
        high_severity_issues=high_severity,
    )


@router.get(
    "/soft-launch/feedback",
    response_model=FeedbackListResponse,
    summary="Paginated list of soft launch feedback submissions",
    dependencies=[Depends(_require_internal_key)],
)
def list_soft_launch_feedback(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> FeedbackListResponse:
    from app.models.player_feedback import PlayerFeedback

    total = db.query(PlayerFeedback).count()
    rows = (
        db.query(PlayerFeedback)
        .order_by(PlayerFeedback.submitted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    items = [
        FeedbackRow(
            feedback_id=str(r.id),
            player_id=str(r.player_id),
            game_day=r.game_day,
            rating=r.rating,
            response_confusing=r.response_confusing,
            response_hard=r.response_hard,
            response_interesting=r.response_interesting,
            cohort_tag=r.cohort_tag,
            submitted_at=r.submitted_at.isoformat() if r.submitted_at else None,
        )
        for r in rows
    ]
    return FeedbackListResponse(total=total, items=items)


@router.get(
    "/soft-launch/issues",
    response_model=IssueListResponse,
    summary="Paginated list of soft launch issue reports",
    dependencies=[Depends(_require_internal_key)],
)
def list_soft_launch_issues(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
) -> IssueListResponse:
    from app.models.issue_report import IssueReport

    q = db.query(IssueReport)
    if severity:
        q = q.filter(IssueReport.severity == severity)
    if category:
        q = q.filter(IssueReport.category == category)
    total = q.count()
    rows = q.order_by(IssueReport.submitted_at.desc()).offset(skip).limit(limit).all()
    items = [
        IssueRow(
            issue_id=str(r.id),
            player_id=str(r.player_id),
            game_day=r.game_day,
            description=r.description,
            category=r.category,
            severity=r.severity,
            submitted_at=r.submitted_at.isoformat() if r.submitted_at else None,
        )
        for r in rows
    ]
    return IssueListResponse(total=total, items=items)
    p25_cash_delta: float
    p75_cash_delta: float
    meets_completion_target: bool
    meets_stress_target: bool
    meets_cash_target: bool
    meets_opportunity_target: bool
    calibration_pass: bool
    sessions: list[Day1SessionResult] = Field(default_factory=list)


@router.get(
    "/balance/day1-config",
    response_model=Day1BalanceConfigResponse,
    summary="Step 68: active Day 1 balance preset and all preset values",
    dependencies=[Depends(_require_internal_key)],
)
def get_day1_balance_config() -> Day1BalanceConfigResponse:
    """Return the currently active Day 1 balance preset and full config for all presets."""
    from app.engine.balance_config import (
        get_active_day1_config,
        get_active_day1_preset_name,
        get_all_day1_presets,
    )
    return Day1BalanceConfigResponse(
        active_preset=get_active_day1_preset_name(),
        active_config=get_active_day1_config(),
        all_presets=get_all_day1_presets(),
    )


@router.post(
    "/balance/day1-preset",
    response_model=Day1PresetSetResponse,
    summary="Step 68: switch the active Day 1 balance preset",
    dependencies=[Depends(_require_internal_key)],
)
def set_day1_balance_preset(body: Day1PresetSetRequest) -> Day1PresetSetResponse:
    """Switch the active Day 1 balance preset for the running process.

    Effect is immediate and in-process only — restarting the server reverts to
    'normal'.  For persistent overrides set the BALANCE_DAY1_PRESET environment
    variable before starting the server.
    """
    from app.engine.balance_config import (
        get_active_day1_config,
        get_active_day1_preset_name,
        set_active_day1_preset,
    )
    try:
        previous = get_active_day1_preset_name()
        set_active_day1_preset(body.preset)
        return Day1PresetSetResponse(
            previous_preset=previous,
            active_preset=body.preset,
            active_config=get_active_day1_config(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/balance/day1-simulation",
    response_model=Day1BatchSimulationResponse,
    summary="Step 68: run batch Day 1 simulation for a given preset",
    dependencies=[Depends(_require_internal_key)],
)
def run_day1_batch_simulation_endpoint(body: Day1SimulationRequest) -> Day1BatchSimulationResponse:
    """Run a pure in-memory batch Day 1 simulation.

    No DB access.  Mirrors work_engine and daily_engine formulas exactly.
    If *preset* is omitted the currently active preset is used.
    """
    from app.engine.balance_config import (
        DAY1_BALANCE_PRESETS,
        get_active_day1_config,
        get_active_day1_preset_name,
    )
    from app.engine.day1_simulation import run_day1_batch_simulation

    preset_name = body.preset or get_active_day1_preset_name()
    config = DAY1_BALANCE_PRESETS.get(preset_name) or get_active_day1_config()

    try:
        result = run_day1_batch_simulation(
            config,
            preset_name=preset_name,
            n_sessions=body.n_sessions,
            seed=body.seed,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulation error: {exc}",
        )

    sessions_out = [
        Day1SessionResult(
            preset_name=s.preset_name,
            job=s.job,
            starting_cash=s.starting_cash,
            ending_cash=s.ending_cash,
            cash_delta=s.cash_delta,
            starting_stress=s.starting_stress,
            ending_stress=s.ending_stress,
            stress_delta=s.stress_delta,
            starting_health=s.starting_health,
            ending_health=s.ending_health,
            health_delta=s.health_delta,
            income_earned=s.income_earned,
            expenses_paid=s.expenses_paid,
            completed=s.completed,
            had_opportunity=s.had_opportunity,
        )
        for s in result.sessions
    ]

    return Day1BatchSimulationResponse(
        preset_name=result.preset_name,
        n_sessions=result.n_sessions,
        completion_rate=result.completion_rate,
        avg_cash_delta=result.avg_cash_delta,
        avg_stress_delta=result.avg_stress_delta,
        avg_health_delta=result.avg_health_delta,
        avg_income_earned=result.avg_income_earned,
        avg_expenses_paid=result.avg_expenses_paid,
        opportunity_rate=result.opportunity_rate,
        min_cash_delta=result.min_cash_delta,
        max_cash_delta=result.max_cash_delta,
        p25_cash_delta=result.p25_cash_delta,
        p75_cash_delta=result.p75_cash_delta,
        meets_completion_target=result.meets_completion_target,
        meets_stress_target=result.meets_stress_target,
        meets_cash_target=result.meets_cash_target,
        meets_opportunity_target=result.meets_opportunity_target,
        calibration_pass=result.calibration_pass,
        sessions=sessions_out,
    )
