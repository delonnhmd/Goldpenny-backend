"""Supply Chain Graph API — Step 43.

Dedicated router for the physical supply chain graph endpoints.  The Step 13
daily economy endpoint remains at GET /economy/supply-chain/daily.

Route overview
--------------
GET  /supply-chain/day/{day}/nodes             — All 12 physical node states
GET  /supply-chain/day/{day}/bottlenecks       — Ranked bottleneck list
GET  /supply-chain/day/{day}/basket-multipliers — Basket supply multipliers
GET  /supply-chain/day/{day}/job-pressure      — Job opportunity pressure
GET  /supply-chain/day/{day}/summary           — Full daily summary
GET  /supply-chain/day/{day}/story             — Human-readable story explainer
POST /supply-chain/day/{day}/compute           — Compute + persist snapshot
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.supply_chain_graph_service import (
    SupplyChainGraphError,
    SupplyChainGraphNotFoundError,
    SupplyChainGraphValidationError,
    build_basket_supply_multipliers,
    build_job_pressure_from_bottlenecks,
    build_node_state_snapshot,
    build_supply_chain_daily_summary,
    build_supply_chain_story_summary,
    detect_supply_chain_bottlenecks,
)
from app.schemas.supply_chain import (
    BasketSupplyMultiplierResponse,
    JobPressureResponse,
    SupplyChainBottleneckResponse,
    SupplyChainNodeStateResponse,
    SupplyChainStoryResponse,
    SupplyChainSummaryResponse,
)

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, SupplyChainGraphNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, SupplyChainGraphValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ── GET /supply-chain/day/{day}/nodes ─────────────────────────────────────────


@router.get("/day/{day}/nodes", response_model=list[SupplyChainNodeStateResponse])
def get_node_states(
    day: int,
    region: str | None = Query(None, description="Region key: suburban, downtown, rural"),
    db: Session = Depends(get_db),
) -> list[SupplyChainNodeStateResponse]:
    """Return availability state for all 12 physical supply chain nodes."""
    try:
        snapshot = build_node_state_snapshot(db, day, region=region)
        return [SupplyChainNodeStateResponse(**rec.to_dict()) for rec in snapshot.values()]
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)


# ── GET /supply-chain/day/{day}/bottlenecks ───────────────────────────────────


@router.get("/day/{day}/bottlenecks", response_model=list[SupplyChainBottleneckResponse])
def get_bottlenecks(
    day: int,
    region: str | None = Query(None),
    threshold: float = Query(0.95, ge=0.5, le=1.0),
    db: Session = Depends(get_db),
) -> list[SupplyChainBottleneckResponse]:
    """Return ranked supply chain bottlenecks (most constrained first)."""
    try:
        bottlenecks = detect_supply_chain_bottlenecks(db, day, region=region, threshold=threshold)
        return [SupplyChainBottleneckResponse(**rec.to_dict()) for rec in bottlenecks]
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)


# ── GET /supply-chain/day/{day}/basket-multipliers ───────────────────────────


@router.get("/day/{day}/basket-multipliers", response_model=list[BasketSupplyMultiplierResponse])
def get_basket_multipliers(
    day: int,
    region: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[BasketSupplyMultiplierResponse]:
    """Return supply chain cost-pressure multipliers for all four baskets."""
    try:
        multipliers = build_basket_supply_multipliers(db, day, region=region)
        return [BasketSupplyMultiplierResponse(**rec.to_dict()) for rec in multipliers.values()]
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)


# ── GET /supply-chain/day/{day}/job-pressure ─────────────────────────────────


@router.get("/day/{day}/job-pressure", response_model=list[JobPressureResponse])
def get_job_pressure(
    day: int,
    region: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[JobPressureResponse]:
    """Return job opportunity pressure signals from supply chain bottlenecks."""
    try:
        pressure = build_job_pressure_from_bottlenecks(db, day, region=region)
        return [JobPressureResponse(**rec.to_dict()) for rec in pressure.values()]
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)


# ── GET /supply-chain/day/{day}/summary ──────────────────────────────────────


@router.get("/day/{day}/summary", response_model=SupplyChainSummaryResponse)
def get_daily_summary(
    day: int,
    region: str | None = Query(None),
    db: Session = Depends(get_db),
) -> SupplyChainSummaryResponse:
    """Return the full daily supply chain summary for a game day."""
    try:
        summary = build_supply_chain_daily_summary(db, day, region=region)
        raw = summary.to_dict()
        raw["node_states"] = [SupplyChainNodeStateResponse(**n) for n in raw["node_states"]]
        raw["bottlenecks"] = [SupplyChainBottleneckResponse(**b) for b in raw["bottlenecks"]]
        raw["basket_multipliers"] = [
            BasketSupplyMultiplierResponse(**m) for m in raw["basket_multipliers"]
        ]
        raw["job_pressure"] = [JobPressureResponse(**j) for j in raw["job_pressure"]]
        return SupplyChainSummaryResponse(**raw)
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)


# ── GET /supply-chain/day/{day}/story ────────────────────────────────────────


@router.get("/day/{day}/story", response_model=SupplyChainStoryResponse)
def get_daily_story(
    day: int,
    region: str | None = Query(None),
    db: Session = Depends(get_db),
) -> SupplyChainStoryResponse:
    """Return a human-readable supply chain story/explainer for a game day."""
    try:
        story = build_supply_chain_story_summary(db, day, region=region)
        return SupplyChainStoryResponse(**story.to_dict())
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)


# ── POST /supply-chain/day/{day}/compute ─────────────────────────────────────


@router.post("/day/{day}/compute", response_model=SupplyChainSummaryResponse)
def compute_and_persist(
    day: int,
    region: str | None = Query(None),
    db: Session = Depends(get_db),
) -> SupplyChainSummaryResponse:
    """Compute and persist the supply chain daily snapshot for a game day.

    Upserts the result into supply_chain_daily_snapshots.  Idempotent —
    calling a second time for the same day overwrites the cached snapshot.
    """
    try:
        summary = build_supply_chain_daily_summary(db, day, region=region, persist=True)
        db.commit()
        raw = summary.to_dict()
        raw["node_states"] = [SupplyChainNodeStateResponse(**n) for n in raw["node_states"]]
        raw["bottlenecks"] = [SupplyChainBottleneckResponse(**b) for b in raw["bottlenecks"]]
        raw["basket_multipliers"] = [
            BasketSupplyMultiplierResponse(**m) for m in raw["basket_multipliers"]
        ]
        raw["job_pressure"] = [JobPressureResponse(**j) for j in raw["job_pressure"]]
        return SupplyChainSummaryResponse(**raw)
    except SupplyChainGraphError as exc:
        _raise_http(exc)
    except Exception as exc:
        _raise_http(exc)
