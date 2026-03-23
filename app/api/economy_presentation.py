"""Step 27 economy presentation endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.economy_presentation_service import (
    EconomyPresentationError,
    EconomyPresentationNotFoundError,
    EconomyPresentationValidationError,
    build_business_margin_summary,
    build_commute_pressure_summary,
    build_economy_presentation_summary,
    build_future_opportunity_teasers,
    build_market_overview,
    build_player_economy_explainer,
    build_price_trend_summary,
)
from app.schemas.economy_presentation import (
    BusinessMarginsResponse,
    CommutePressureResponse,
    EconomyPresentationSummaryResponse,
    FutureOpportunityTeasersResponse,
    MarketOverviewResponse,
    PlayerEconomyExplainerResponse,
    PriceTrendsResponse,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, EconomyPresentationNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, EconomyPresentationValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, EconomyPresentationError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected economy presentation error.")


@router.get("/player/{player_id}/market-overview", response_model=MarketOverviewResponse)
def get_market_overview(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> MarketOverviewResponse:
    """Return a compact market mood/driver summary in player language."""
    try:
        payload = build_market_overview(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return MarketOverviewResponse(**payload)


@router.get("/player/{player_id}/price-trends", response_model=PriceTrendsResponse)
def get_price_trends(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PriceTrendsResponse:
    """Return readable basket trend items with drivers and impact notes."""
    try:
        payload = build_price_trend_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return PriceTrendsResponse(**payload)


@router.get("/player/{player_id}/business-margins", response_model=BusinessMarginsResponse)
def get_business_margins(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BusinessMarginsResponse:
    """Return Fruit Shop + Food Truck margin environment explanation."""
    try:
        payload = build_business_margin_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return BusinessMarginsResponse(**payload)


@router.get("/player/{player_id}/commute-pressure", response_model=CommutePressureResponse)
def get_commute_pressure(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CommutePressureResponse:
    """Return commute pressure + housing tradeoff context."""
    try:
        payload = build_commute_pressure_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return CommutePressureResponse(**payload)


@router.get("/player/{player_id}/explainer", response_model=PlayerEconomyExplainerResponse)
def get_player_explainer(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PlayerEconomyExplainerResponse:
    """Return plain-language why/impact/next-move explainer."""
    try:
        payload = build_player_economy_explainer(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return PlayerEconomyExplainerResponse(**payload)


@router.get("/player/{player_id}/future-teasers", response_model=FutureOpportunityTeasersResponse)
def get_future_teasers(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> FutureOpportunityTeasersResponse:
    """Return subtle locked future opportunity teasers (non-actionable)."""
    try:
        payload = build_future_opportunity_teasers(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return FutureOpportunityTeasersResponse(**payload)


@router.get("/player/{player_id}/summary", response_model=EconomyPresentationSummaryResponse)
def get_economy_presentation_summary(
    player_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EconomyPresentationSummaryResponse:
    """Return composed Step 27 summary payload for frontend hydration."""
    try:
        payload = build_economy_presentation_summary(db=db, player_id=player_id, as_of_date=as_of_date)
    except Exception as exc:
        _raise_http_error(exc)
    return EconomyPresentationSummaryResponse(**payload)
