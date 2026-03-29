"""Economy API — Step 5.

Provides debug and game-display endpoints for the macro-economy simulation.

Route overview
--------------
GET  /economy/current             — Latest macro state + derived pressures
GET  /economy/history             — Last 30 daily history snapshots
GET  /economy/events/current      — Events active on the latest economy day
POST /economy/process-next-day    — Advance economy to the next in-game day
GET  /economy/sectors/current     — Latest sector index values
GET  /economy/sectors/history     — Sector performance history grouped by name
GET  /economy/price-factors       — Multipliers for the shop / basket engine
GET  /economy/daily-brief         — Backward-compatible alias of /current
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.economy_engine import EconomyEngine
from app.engine.stock_engine import StockEngine
from app.engine.supply_chain_service import (
    SupplyChainError,
    SupplyChainNotFoundError,
    compute_supply_chain_daily_snapshot,
)
from app.models.economy import EconomyState
from app.models.economy_event import EconomyEvent
from app.models.economy_history import EconomyHistory
from app.models.sector_index import SectorIndex
from app.schemas.economy_transmission import (
    BasketPricingDailyResponse,
    DailyEconomyBriefResponse,
    JobMarketDailyResponse,
)
from app.schemas.supply_chain import SupplyChainDailyResponse
from app.services.basket_pricing_service import (
    BasketPricingError,
    BasketPricingNotFoundError,
    compute_daily_basket_price_updates,
)
from app.services.daily_brief_service import DailyBriefError, build_daily_economy_brief
from app.services.job_market_service import (
    JobMarketError,
    JobMarketNotFoundError,
    compute_daily_job_market_updates,
)
from app.engine.weekly_strategy_service import build_economy_weekly_summary

router = APIRouter()
_engine = EconomyEngine()
_stock_engine = StockEngine()


class EconomyWeeklySummary(BaseModel):
    week_start: str
    week_end: str
    dominant_event_chains: list[str] = Field(default_factory=list)
    top_basket_movers: list[dict] = Field(default_factory=list)
    strongest_jobs: list[dict] = Field(default_factory=list)
    pressured_sectors: list[str] = Field(default_factory=list)
    volatility_tone: str
    debug_meta: dict = Field(default_factory=dict)


# ── GET /economy/current ──────────────────────────────────────────────────────

@router.get("/current")
def get_economy_current(db: Session = Depends(get_db)) -> dict:
    """Return the latest macro-economy state with derived pressure metrics."""
    summary = _engine.get_current_state(db)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No economy state found. Call POST /economy/process-next-day first.",
        )
    return summary


# ── GET /economy/history ──────────────────────────────────────────────────────

@router.get("/history")
def get_economy_history(db: Session = Depends(get_db)) -> list[dict]:
    """Return the last 30 daily economy history snapshots, newest first."""
    rows = (
        db.query(EconomyHistory)
        .order_by(EconomyHistory.day.desc())
        .limit(30)
        .all()
    )
    return [
        {
            "day": r.day,
            "inflation_rate": r.inflation_rate,
            "interest_rate": r.interest_rate,
            "unemployment_rate": r.unemployment_rate,
            "oil_index": r.oil_index,
            "consumer_confidence": r.consumer_confidence,
            "supply_chain_index": r.supply_chain_index,
            "seasonal_index": r.seasonal_index,
            "basket_price_pressure": r.basket_price_pressure,
            "layoff_pressure": r.layoff_pressure,
            "wage_pressure": r.wage_pressure,
            "sector_pressure_summary": r.sector_pressure_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── GET /economy/events/current ───────────────────────────────────────────────

@router.get("/events/current")
def get_current_events(db: Session = Depends(get_db)) -> list[dict]:
    """Return all economy events for the latest processed economy day."""
    latest = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
    if latest is None:
        return []
    events = (
        db.query(EconomyEvent)
        .filter(EconomyEvent.day == latest.day)
        .all()
    )
    return [
        {
            "id": e.id,
            "day": e.day,
            "title": e.title,
            "description": e.description,
            "event_type": e.event_type,
            "severity": e.severity,
            "is_system_generated": e.is_system_generated,
            "inflation_impact": e.inflation_impact,
            "interest_rate_impact": e.interest_rate_impact,
            "unemployment_impact": e.unemployment_impact,
            "oil_impact": e.oil_impact,
            "confidence_impact": e.confidence_impact,
            "supply_chain_impact": e.supply_chain_impact,
            "seasonal_impact": e.seasonal_impact,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


# ── POST /economy/process-next-day ────────────────────────────────────────────

@router.post("/process-next-day")
def process_next_day(db: Session = Depends(get_db)) -> dict:
    """Advance the economy engine to the next in-game day.

    Determines the next unprocessed day from the latest EconomyState row.
    Idempotent — calling a second time for the same day returns the cached
    result without re-processing.
    """
    latest = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
    next_day = (latest.day + 1) if latest is not None else 1

    # Idempotency guard at the API layer for clear feedback.
    already_done = db.query(EconomyState).filter(EconomyState.day == next_day).first()
    if already_done is not None:
        summary = _engine.get_current_state(db)
        return {"message": "Economy already processed for this day", **(summary or {})}

    summary = _engine.process_next_day_economy(next_day, db)

    # Update stock prices based on the freshly-computed sector indexes.
    _stock_engine.update_daily_stock_prices(next_day, db)

    # Re-query event count for an accurate response value.
    event_count = (
        db.query(EconomyEvent).filter(EconomyEvent.day == next_day).count()
    )
    return {"message": "Economy processed", "event_count": event_count, **summary}


# ── GET /economy/sectors/current ─────────────────────────────────────────────

@router.get("/sectors/current")
def get_sectors_current(db: Session = Depends(get_db)) -> list[dict]:
    """Return sector index rows for the latest economy day."""
    latest = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
    if latest is None:
        return []
    rows = (
        db.query(SectorIndex)
        .filter(SectorIndex.day == latest.day)
        .order_by(SectorIndex.sector_name)
        .all()
    )
    return [
        {
            "day": r.day,
            "sector_name": r.sector_name,
            "sector_index_value": r.sector_index_value,
            "daily_change_percent": r.daily_change_percent,
            "macro_driver": r.macro_driver,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── GET /economy/sectors/history ─────────────────────────────────────────────

@router.get("/sectors/history")
def get_sectors_history(db: Session = Depends(get_db)) -> dict[str, list[dict]]:
    """Return sector performance history for the last 30 days, grouped by sector."""
    rows = (
        db.query(SectorIndex)
        .order_by(SectorIndex.day.desc())
        .limit(300)  # 10 sectors × 30 days
        .all()
    )
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        if r.sector_name not in grouped:
            grouped[r.sector_name] = []
        grouped[r.sector_name].append(
            {
                "day": r.day,
                "sector_index_value": r.sector_index_value,
                "daily_change_percent": r.daily_change_percent,
                "macro_driver": r.macro_driver,
            }
        )
    return grouped


# ── GET /economy/price-factors ────────────────────────────────────────────────

@router.get("/price-factors")
def get_price_factors(db: Session = Depends(get_db)) -> dict:
    """Return economy-derived multipliers for the shop / basket pricing engine."""
    return _engine.get_price_factors(db)

@router.get(
    "/supply-chain/daily",
    response_model=SupplyChainDailyResponse,
    summary="Compute daily supply-chain signal snapshot",
)
def get_supply_chain_daily_route(
    as_of_date: date | None = None,
    db: Session = Depends(get_db),
) -> SupplyChainDailyResponse:
    """Compute one daily supply-chain signal snapshot from macro conditions."""
    try:
        payload = compute_supply_chain_daily_snapshot(db, as_of_date=as_of_date)
        return SupplyChainDailyResponse(**payload)
    except SupplyChainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SupplyChainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /economy/daily-brief ──────────────────────────────────────────────────

@router.get(
    "/baskets/pricing-daily",
    response_model=BasketPricingDailyResponse,
    summary="Compute or inspect daily basket pricing transmission",
)
def get_basket_pricing_daily_route(
    as_of_date: date | None = None,
    day: int | None = None,
    db: Session = Depends(get_db),
) -> BasketPricingDailyResponse:
    try:
        payload = compute_daily_basket_price_updates(
            db,
            as_of_date=as_of_date,
            day=day,
            persist=False,
            commit=False,
        )
        return BasketPricingDailyResponse(**payload)
    except BasketPricingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BasketPricingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/jobs/market-daily",
    response_model=JobMarketDailyResponse,
    summary="Compute or inspect daily job market modifiers",
)
def get_job_market_daily_route(
    as_of_date: date | None = None,
    day: int | None = None,
    db: Session = Depends(get_db),
) -> JobMarketDailyResponse:
    try:
        payload = compute_daily_job_market_updates(
            db,
            as_of_date=as_of_date,
            day=day,
        )
        return JobMarketDailyResponse(**payload)
    except JobMarketNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobMarketError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/brief/economy-daily",
    response_model=DailyEconomyBriefResponse,
    summary="Build deterministic daily economy explainability brief",
)
def get_daily_economy_brief_route(
    as_of_date: date | None = None,
    day: int | None = None,
    db: Session = Depends(get_db),
) -> DailyEconomyBriefResponse:
    try:
        payload = build_daily_economy_brief(
            db,
            as_of_date=as_of_date,
            day=day,
        )
        return DailyEconomyBriefResponse(**payload)
    except DailyBriefError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/daily-brief")
def get_daily_brief(db: Session = Depends(get_db)) -> dict:
    """Backward-compatible alias of GET /economy/current."""
    summary = _engine.get_current_state(db)
    if summary is None:
        return {"message": "No economy state yet. Call POST /economy/process-next-day first."}
    return summary


@router.get("/weekly-summary", response_model=EconomyWeeklySummary)
def get_economy_weekly_summary_route(
    as_of_date: date | None = None,
    db: Session = Depends(get_db),
) -> EconomyWeeklySummary:
    """Return deterministic weekly economy summary from real event and market state."""
    try:
        return build_economy_weekly_summary(db=db, as_of_date=as_of_date)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


