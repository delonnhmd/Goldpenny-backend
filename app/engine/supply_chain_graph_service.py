"""Step 43 — Supply Chain Graph + Bottleneck Opportunity Engine.

This service adds a *physical-node layer* on top of the Step 13 abstract
supply chain engine.  Step 13 computes macro-sensitivity-driven availability
for eight abstract nodes (fuel, labor, utilities, …); Step 43 maps those to
twelve named physical nodes (OIL_FUEL, TRUCKING_LASTMILE, …), optionally
overlays DB-stored per-day overrides, and exposes richer bottleneck + job
pressure signals to the rest of the system.

Public API
----------
build_node_state_snapshot       — dict of node_id → SupplyChainNodeRecord
compute_node_availability       — float availability for one node + region
detect_supply_chain_bottlenecks — ranked list of BottleneckRecord
build_basket_supply_multipliers — dict of basket_type → BasketMultiplierRecord
build_job_pressure_from_bottlenecks — dict of job_key → JobPressureRecord
build_supply_chain_daily_summary   — SupplyChainSummaryRecord
build_supply_chain_story_summary   — SupplyChainStoryRecord

All functions are compute-only (no DB writes except through the optional
`persist` flag on `build_supply_chain_daily_summary`).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.engine.supply_chain_recipes import (
    GRAPH_BASKET_RECIPES,
    JOB_BOTTLENECK_MAP,
    MVP_NODE_IDS,
    NODE_REGION_MODIFIERS,
    NODE_RELIABILITY_SCALE,
    NODE_TO_ABSTRACT_BRIDGE,
    bottleneck_severity_label,
    cost_pressure_label,
    opportunity_label,
)
from app.engine.supply_chain_service import (
    SupplyChainError,
    compute_supply_chain_daily_snapshot,
)
from app.models.supply_chain_daily_snapshot import SupplyChainDailySnapshot
from app.models.supply_chain_node_state import SupplyChainNodeState

# ── Constants ─────────────────────────────────────────────────────────────────

_AVAILABILITY_MIN = 0.55
_AVAILABILITY_MAX = 1.10
_MULTIPLIER_MIN = 0.85
_MULTIPLIER_MAX = 1.10


# ── Custom error hierarchy ────────────────────────────────────────────────────


class SupplyChainGraphError(Exception):
    """Base exception for Step 43 graph service operations."""


class SupplyChainGraphNotFoundError(SupplyChainGraphError):
    """Raised when requested day/node data is not available."""


class SupplyChainGraphValidationError(SupplyChainGraphError):
    """Raised when input validation fails."""


# ── Internal data records ─────────────────────────────────────────────────────


@dataclass
class SupplyChainNodeRecord:
    node_id: str
    abstract_node: str
    availability: float
    region: str | None
    region_modifier: float
    region_adjusted_availability: float
    reliability_scale: float
    source: str  # "macro" | "db_override"

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "abstract_node": self.abstract_node,
            "availability": round(self.availability, 4),
            "region": self.region,
            "region_modifier": round(self.region_modifier, 4),
            "region_adjusted_availability": round(self.region_adjusted_availability, 4),
            "reliability_scale": round(self.reliability_scale, 4),
            "source": self.source,
        }


@dataclass
class BottleneckRecord:
    node_id: str
    availability: float
    severity_label: str
    affected_baskets: list[str]
    affected_jobs: list[str]
    reason_summary: str
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "availability": round(self.availability, 4),
            "severity_label": self.severity_label,
            "affected_baskets": self.affected_baskets,
            "affected_jobs": self.affected_jobs,
            "reason_summary": self.reason_summary,
            "rank": self.rank,
        }


@dataclass
class BasketMultiplierRecord:
    basket_type: str
    supply_multiplier: float
    cost_pressure_label: str
    primary_bottleneck_node: str | None
    short_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "basket_type": self.basket_type,
            "supply_multiplier": round(self.supply_multiplier, 4),
            "cost_pressure_label": self.cost_pressure_label,
            "primary_bottleneck_node": self.primary_bottleneck_node,
            "short_summary": self.short_summary,
        }


@dataclass
class JobPressureRecord:
    job_key: str
    job_pressure_multiplier: float
    source_bottleneck_nodes: list[str]
    opportunity_label: str
    short_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_key": self.job_key,
            "job_pressure_multiplier": round(self.job_pressure_multiplier, 4),
            "source_bottleneck_nodes": self.source_bottleneck_nodes,
            "opportunity_label": self.opportunity_label,
            "short_summary": self.short_summary,
        }


@dataclass
class SupplyChainSummaryRecord:
    day: int
    top_bottleneck_node: str | None
    top_bottleneck_severity: str
    most_affected_basket: str | None
    most_affected_basket_multiplier: float
    best_job_opportunity: str | None
    best_job_pressure_multiplier: float
    overall_stress_score: float
    short_summary: str
    node_states: list[dict[str, Any]] = field(default_factory=list)
    bottlenecks: list[dict[str, Any]] = field(default_factory=list)
    basket_multipliers: list[dict[str, Any]] = field(default_factory=list)
    job_pressure: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "top_bottleneck_node": self.top_bottleneck_node,
            "top_bottleneck_severity": self.top_bottleneck_severity,
            "most_affected_basket": self.most_affected_basket,
            "most_affected_basket_multiplier": round(self.most_affected_basket_multiplier, 4),
            "best_job_opportunity": self.best_job_opportunity,
            "best_job_pressure_multiplier": round(self.best_job_pressure_multiplier, 4),
            "overall_stress_score": round(self.overall_stress_score, 4),
            "short_summary": self.short_summary,
            "node_states": self.node_states,
            "bottlenecks": self.bottlenecks,
            "basket_multipliers": self.basket_multipliers,
            "job_pressure": self.job_pressure,
        }


@dataclass
class SupplyChainStoryRecord:
    day: int
    shortage_story: str
    bottleneck_highlights: list[str]
    basket_impact_notes: list[str]
    job_opportunity_hints: list[str]
    practical_current_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "shortage_story": self.shortage_story,
            "bottleneck_highlights": self.bottleneck_highlights,
            "basket_impact_notes": self.basket_impact_notes,
            "job_opportunity_hints": self.job_opportunity_hints,
            "practical_current_actions": self.practical_current_actions,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _get_abstract_availability(abstract_snapshots: dict[str, float], abstract_node: str) -> float:
    """Return availability for an abstract node, defaulting to 1.0 if missing."""
    return float(abstract_snapshots.get(abstract_node, 1.0))


def _region_modifier(node_id: str, region: str | None) -> float:
    """Return the region availability modifier for a physical node."""
    if region is None:
        return 1.0
    norm = region.strip().lower()
    modifiers = NODE_REGION_MODIFIERS.get(node_id, {})
    return float(modifiers.get(norm, 1.0))


def _load_abstract_snapshots(db: Session, day: int) -> dict[str, float]:
    """Derive abstract node availability scores for a given day from Step 13."""
    try:
        payload = compute_supply_chain_daily_snapshot(db, macro_day=day)
    except SupplyChainError:
        # Fallback to neutral availability when macro data is absent
        return {}

    node_snapshots: list[dict] = payload.get("node_snapshots", [])
    return {
        snap["node_id"]: float(snap.get("availability", 1.0))
        for snap in node_snapshots
        if "node_id" in snap
    }


def _load_db_overrides(db: Session, day: int) -> dict[str, SupplyChainNodeState]:
    """Return DB-stored node-state overrides for a given day, keyed by node_key."""
    try:
        rows = (
            db.query(SupplyChainNodeState)
            .filter(SupplyChainNodeState.day == day)
            .all()
        )
        return {row.node_key: row for row in rows}
    except Exception:
        return {}


def _compute_physical_availability(
    node_id: str,
    abstract_snapshots: dict[str, float],
    db_override: SupplyChainNodeState | None,
) -> tuple[float, str]:
    """Compute raw availability for one physical node (before region adjustment).

    Returns (availability, source) where source is "macro" or "db_override".
    """
    if db_override is not None:
        cap = float(db_override.capacity or 1.0)
        req = float(db_override.required or 1.0)
        rel = float(db_override.reliability or 1.0)
        raw = min(1.0, cap / max(req, 1e-9)) * rel
        availability = _clamp(raw, _AVAILABILITY_MIN, _AVAILABILITY_MAX)
        return availability, "db_override"

    abstract_node = NODE_TO_ABSTRACT_BRIDGE[node_id]
    abstract_avail = _get_abstract_availability(abstract_snapshots, abstract_node)
    reliability = NODE_RELIABILITY_SCALE.get(node_id, 1.0)
    raw = abstract_avail * reliability
    availability = _clamp(raw, _AVAILABILITY_MIN, _AVAILABILITY_MAX)
    return availability, "macro"


# ── Public function 1: build_node_state_snapshot ─────────────────────────────


def build_node_state_snapshot(
    db: Session,
    day: int,
    region: str | None = None,
) -> dict[str, SupplyChainNodeRecord]:
    """Build a snapshot of all 12 physical node states for a given game day.

    Parameters
    ----------
    db:     SQLAlchemy session.
    day:    Game day integer (1-based).
    region: Optional region key ('suburban', 'downtown', 'rural').

    Returns
    -------
    Dict mapping node_id → SupplyChainNodeRecord.
    """
    abstract_snapshots = _load_abstract_snapshots(db, day)
    db_overrides = _load_db_overrides(db, day)

    result: dict[str, SupplyChainNodeRecord] = {}
    for node_id in MVP_NODE_IDS:
        override = db_overrides.get(node_id)
        availability, source = _compute_physical_availability(node_id, abstract_snapshots, override)
        reg_mod = _region_modifier(node_id, region)
        adj_availability = _clamp(availability * reg_mod, _AVAILABILITY_MIN, _AVAILABILITY_MAX)

        result[node_id] = SupplyChainNodeRecord(
            node_id=node_id,
            abstract_node=NODE_TO_ABSTRACT_BRIDGE[node_id],
            availability=availability,
            region=region,
            region_modifier=reg_mod,
            region_adjusted_availability=adj_availability,
            reliability_scale=NODE_RELIABILITY_SCALE.get(node_id, 1.0),
            source=source,
        )

    return result


# ── Public function 2: compute_node_availability ─────────────────────────────


def compute_node_availability(
    db: Session,
    day: int,
    node_id: str,
    region: str | None = None,
) -> float:
    """Compute region-adjusted availability for a single physical node.

    Parameters
    ----------
    db:      SQLAlchemy session.
    day:     Game day integer.
    node_id: One of the 12 MVP_NODE_IDS.
    region:  Optional region key.

    Returns
    -------
    Float in [_AVAILABILITY_MIN, _AVAILABILITY_MAX].

    Raises
    ------
    SupplyChainGraphValidationError — if node_id is not a known physical node.
    """
    if node_id not in MVP_NODE_IDS:
        raise SupplyChainGraphValidationError(
            f"Unknown physical node: {node_id!r}. Must be one of {MVP_NODE_IDS}."
        )
    snapshot = build_node_state_snapshot(db, day, region=region)
    return snapshot[node_id].region_adjusted_availability


# ── Public function 3: detect_supply_chain_bottlenecks ───────────────────────


def detect_supply_chain_bottlenecks(
    db: Session,
    day: int,
    region: str | None = None,
    threshold: float = 0.95,
) -> list[BottleneckRecord]:
    """Detect and rank supply chain bottlenecks for a given day.

    A node is considered a bottleneck when its region-adjusted availability
    falls below `threshold` (default 0.95).  The returned list is ranked by
    ascending availability (most constrained first).

    Parameters
    ----------
    db:        SQLAlchemy session.
    day:       Game day integer.
    region:    Optional region key.
    threshold: Availability below which a node is considered a bottleneck.

    Returns
    -------
    List of BottleneckRecord, sorted most-constrained first.
    """
    snapshot = build_node_state_snapshot(db, day, region=region)

    bottlenecks: list[BottleneckRecord] = []
    for node_id, record in snapshot.items():
        avail = record.region_adjusted_availability
        if avail < threshold:
            affected_baskets = [
                b for b, weights in GRAPH_BASKET_RECIPES.items() if node_id in weights
            ]
            affected_jobs = list(JOB_BOTTLENECK_MAP.get(node_id, {}).keys())
            pressure_pct = round((1.0 - avail) * 100, 1)
            reason_summary = (
                f"{node_id.replace('_', ' ').title()} running at "
                f"{round(avail * 100, 1)}% capacity "
                f"({pressure_pct}% below normal)."
            )
            bottlenecks.append(
                BottleneckRecord(
                    node_id=node_id,
                    availability=avail,
                    severity_label=bottleneck_severity_label(avail),
                    affected_baskets=affected_baskets,
                    affected_jobs=affected_jobs,
                    reason_summary=reason_summary,
                )
            )

    bottlenecks.sort(key=lambda r: r.availability)
    for i, rec in enumerate(bottlenecks):
        rec.rank = i + 1

    return bottlenecks


# ── Public function 4: build_basket_supply_multipliers ───────────────────────


def build_basket_supply_multipliers(
    db: Session,
    day: int,
    region: str | None = None,
) -> dict[str, BasketMultiplierRecord]:
    """Compute supply chain multipliers for all four MVP baskets.

    For each basket the multiplier is calculated as the weighted geometric
    mean of the contributing physical-node availabilities.  The result is
    inverted relative to a "normal" availability of 1.0, clamped to
    [MULTIPLIER_MIN, MULTIPLIER_MAX], and reflects cost pressure when
    availability < 1.0.

    Formula (per basket):
        avg_avail = Σ weight_i * avail_i
        multiplier = 2 - avg_avail   (so avail=1.0 → multiplier=1.0)
        multiplier = clamp(multiplier, 0.85, 1.10)

    Returns
    -------
    Dict mapping basket_type → BasketMultiplierRecord.
    """
    snapshot = build_node_state_snapshot(db, day, region=region)

    result: dict[str, BasketMultiplierRecord] = {}
    for basket_type, weights in GRAPH_BASKET_RECIPES.items():
        weighted_avail = 0.0
        worst_node: str | None = None
        worst_avail = 1.0

        for node_id, weight in weights.items():
            node_avail = snapshot[node_id].region_adjusted_availability
            weighted_avail += weight * node_avail
            if node_avail < worst_avail:
                worst_avail = node_avail
                worst_node = node_id

        # Invert: lower availability → higher multiplier (cost pressure)
        raw_multiplier = 2.0 - weighted_avail
        multiplier = _clamp(raw_multiplier, _MULTIPLIER_MIN, _MULTIPLIER_MAX)
        pressure_label = cost_pressure_label(multiplier)

        if worst_node and worst_avail < 0.95:
            primary_node_label = worst_node.replace("_", " ").title()
            summary = (
                f"{basket_type.title()} supply at {round(weighted_avail * 100, 1)}% "
                f"— {primary_node_label} is the primary constraint."
            )
        else:
            summary = (
                f"{basket_type.title()} supply well-provisioned at "
                f"{round(weighted_avail * 100, 1)}%."
            )

        result[basket_type] = BasketMultiplierRecord(
            basket_type=basket_type,
            supply_multiplier=multiplier,
            cost_pressure_label=pressure_label,
            primary_bottleneck_node=worst_node if worst_avail < 0.95 else None,
            short_summary=summary,
        )

    return result


# ── Public function 5: build_job_pressure_from_bottlenecks ───────────────────


def build_job_pressure_from_bottlenecks(
    db: Session,
    day: int,
    region: str | None = None,
) -> dict[str, JobPressureRecord]:
    """Compute job opportunity pressure derived from supply-chain bottlenecks.

    For each job key that appears in JOB_BOTTLENECK_MAP, the pressure
    multiplier is accumulated from all constrained nodes weighted by how
    severely constrained each is and by the node's coupling coefficient to
    the job.

        pressure_contribution(node, job) = (1 - availability) * coupling_weight
        total_pressure(job) = Σ pressure_contributions (clamped to [0, 0.50])
        multiplier = 1 + total_pressure

    Returns
    -------
    Dict mapping job_key → JobPressureRecord.  Only jobs with at least one
    active bottleneck contributing to their pressure are included.
    """
    snapshot = build_node_state_snapshot(db, day, region=region)

    # Accumulate pressure per job
    job_pressure_raw: dict[str, float] = {}
    job_source_nodes: dict[str, list[str]] = {}

    for node_id, coupling_map in JOB_BOTTLENECK_MAP.items():
        avail = snapshot[node_id].region_adjusted_availability
        if avail >= 0.95:
            # No meaningful bottleneck pressure from this node
            continue
        constraint = 1.0 - avail  # 0 → 0.45 range

        for job_key, coupling in coupling_map.items():
            contribution = constraint * coupling
            job_pressure_raw[job_key] = job_pressure_raw.get(job_key, 0.0) + contribution
            job_source_nodes.setdefault(job_key, [])
            if node_id not in job_source_nodes[job_key]:
                job_source_nodes[job_key].append(node_id)

    result: dict[str, JobPressureRecord] = {}
    for job_key, raw_pressure in job_pressure_raw.items():
        clamped_pressure = _clamp(raw_pressure, 0.0, 0.50)
        multiplier = round(1.0 + clamped_pressure, 4)
        sources = job_source_nodes.get(job_key, [])
        opp_label = opportunity_label(
            bottleneck_count=len(sources),
            max_pressure=clamped_pressure,
        )

        job_label = job_key.replace("_", " ").title()
        if clamped_pressure >= 0.25:
            summary = (
                f"{job_label} demand is surging — supply chain pressure "
                f"from {len(sources)} node(s) is creating strong openings."
            )
        elif clamped_pressure >= 0.10:
            summary = (
                f"{job_label} is seeing elevated demand driven by "
                f"{', '.join(n.replace('_', ' ').title() for n in sources[:2])} constraints."
            )
        else:
            summary = (
                f"{job_label} has minor upward pressure from "
                f"{', '.join(n.replace('_', ' ').title() for n in sources[:2])}."
            )

        result[job_key] = JobPressureRecord(
            job_key=job_key,
            job_pressure_multiplier=multiplier,
            source_bottleneck_nodes=sources,
            opportunity_label=opp_label,
            short_summary=summary,
        )

    return result


# ── Public function 6: build_supply_chain_daily_summary ──────────────────────


def build_supply_chain_daily_summary(
    db: Session,
    day: int,
    region: str | None = None,
    persist: bool = False,
) -> SupplyChainSummaryRecord:
    """Build the full daily supply chain summary for a given game day.

    Assembles node states, bottlenecks, basket multipliers, and job pressure
    into a single SupplyChainSummaryRecord.  When ``persist=True`` the result
    is upserted into ``supply_chain_daily_snapshots`` (region-agnostic view).

    Parameters
    ----------
    db:      SQLAlchemy session.
    day:     Game day integer.
    region:  Optional region for region-adjusted values.
    persist: If True, upsert result into the DB snapshot table.

    Returns
    -------
    SupplyChainSummaryRecord.
    """
    node_states = build_node_state_snapshot(db, day, region=region)
    bottlenecks = detect_supply_chain_bottlenecks(db, day, region=region)
    basket_multipliers = build_basket_supply_multipliers(db, day, region=region)
    job_pressure = build_job_pressure_from_bottlenecks(db, day, region=region)

    # Top bottleneck
    top_bn: BottleneckRecord | None = bottlenecks[0] if bottlenecks else None

    # Most affected basket (highest cost pressure multiplier)
    most_affected_basket: str | None = None
    highest_multiplier = 0.0
    for bm in basket_multipliers.values():
        if bm.supply_multiplier > highest_multiplier:
            highest_multiplier = bm.supply_multiplier
            most_affected_basket = bm.basket_type

    # Best job opportunity (highest multiplier → most pressure/opportunity)
    best_job: JobPressureRecord | None = None
    if job_pressure:
        best_job = max(job_pressure.values(), key=lambda j: j.job_pressure_multiplier)

    # Overall stress score: mean of (1 - availability) capped at 1.0
    stress_scores = [1.0 - rec.region_adjusted_availability for rec in node_states.values()]
    overall_stress = _clamp(
        sum(stress_scores) / max(len(stress_scores), 1),
        0.0,
        1.0,
    )

    # Short summary text
    if top_bn:
        short_summary = (
            f"Day {day}: {top_bn.node_id.replace('_', ' ').title()} is the top constraint "
            f"({top_bn.severity_label} severity). "
            f"Stress score {round(overall_stress * 100, 1)}%."
        )
    else:
        short_summary = (
            f"Day {day}: Supply chain is operating normally. "
            f"Stress score {round(overall_stress * 100, 1)}%."
        )

    summary = SupplyChainSummaryRecord(
        day=day,
        top_bottleneck_node=top_bn.node_id if top_bn else None,
        top_bottleneck_severity=top_bn.severity_label if top_bn else "none",
        most_affected_basket=most_affected_basket,
        most_affected_basket_multiplier=highest_multiplier,
        best_job_opportunity=best_job.job_key if best_job else None,
        best_job_pressure_multiplier=best_job.job_pressure_multiplier if best_job else 1.0,
        overall_stress_score=round(overall_stress, 4),
        short_summary=short_summary,
        node_states=[rec.to_dict() for rec in node_states.values()],
        bottlenecks=[rec.to_dict() for rec in bottlenecks],
        basket_multipliers=[rec.to_dict() for rec in basket_multipliers.values()],
        job_pressure=[rec.to_dict() for rec in job_pressure.values()],
    )

    if persist:
        _upsert_daily_snapshot(db, summary)

    return summary


def _upsert_daily_snapshot(db: Session, summary: SupplyChainSummaryRecord) -> None:
    """Insert or update the supply_chain_daily_snapshots row for summary.day."""
    existing = (
        db.query(SupplyChainDailySnapshot)
        .filter(SupplyChainDailySnapshot.day == summary.day)
        .first()
    )
    now = datetime.now(timezone.utc)

    if existing is not None:
        existing.top_bottleneck_node = summary.top_bottleneck_node
        existing.most_affected_basket = summary.most_affected_basket
        existing.best_job_opportunity = summary.best_job_opportunity
        existing.overall_stress_score = summary.overall_stress_score
        existing.node_states_json = json.dumps(summary.node_states)
        existing.basket_multipliers_json = json.dumps(summary.basket_multipliers)
        existing.bottlenecks_json = json.dumps(summary.bottlenecks)
        existing.job_pressure_json = json.dumps(summary.job_pressure)
        existing.computed_at = now
    else:
        row = SupplyChainDailySnapshot(
            day=summary.day,
            top_bottleneck_node=summary.top_bottleneck_node,
            most_affected_basket=summary.most_affected_basket,
            best_job_opportunity=summary.best_job_opportunity,
            overall_stress_score=summary.overall_stress_score,
            node_states_json=json.dumps(summary.node_states),
            basket_multipliers_json=json.dumps(summary.basket_multipliers),
            bottlenecks_json=json.dumps(summary.bottlenecks),
            job_pressure_json=json.dumps(summary.job_pressure),
            computed_at=now,
        )
        db.add(row)

    try:
        db.flush()
    except Exception:
        db.rollback()


# ── Public function 7: build_supply_chain_story_summary ──────────────────────


def build_supply_chain_story_summary(
    db: Session,
    day: int,
    region: str | None = None,
) -> SupplyChainStoryRecord:
    """Build a human-readable story/explainer for the current supply chain state.

    Parameters
    ----------
    db:     SQLAlchemy session.
    day:    Game day integer.
    region: Optional region key.

    Returns
    -------
    SupplyChainStoryRecord with narrative and practical action hints.
    """
    summary = build_supply_chain_daily_summary(db, day, region=region)

    bottlenecks = [
        BottleneckRecord(**{k: v for k, v in bn.items() if k != "rank"})
        for bn in summary.bottlenecks
    ]

    # ── Shortage story ────────────────────────────────────────────────────────
    if not bottlenecks:
        shortage_story = (
            "The supply chain is running smoothly today. No major constraints "
            "are impacting basket prices or job availability."
        )
    else:
        top = bottlenecks[0]
        n_bottlenecks = len(bottlenecks)
        severity_desc = {
            "minor": "some minor strain",
            "moderate": "moderate disruption",
            "severe": "severe shortfalls",
            "critical": "critical breakdown",
        }.get(top.severity_label, "disruption")

        shortage_story = (
            f"The supply chain is experiencing {severity_desc}, "
            f"led by {top.node_id.replace('_', ' ').title()}. "
            f"{n_bottlenecks} node(s) are below normal operating capacity, "
            f"which is putting upward pressure on consumer basket prices and "
            f"creating employment opportunities in affected sectors."
        )

    # ── Bottleneck highlights ────────────────────────────────────────────────
    bottleneck_highlights = [rec.reason_summary for rec in bottlenecks[:3]]

    # ── Basket impact notes ───────────────────────────────────────────────────
    basket_impact_notes: list[str] = []
    for bm_dict in summary.basket_multipliers:
        mult = bm_dict["supply_multiplier"]
        label = bm_dict["cost_pressure_label"]
        btype = bm_dict["basket_type"]
        if mult != 1.0:
            pct_change = round((mult - 1.0) * 100, 1)
            direction = "up" if pct_change > 0 else "down"
            basket_impact_notes.append(
                f"{btype.title()} basket cost pressure {label} "
                f"(~{abs(pct_change)}% {direction} from normal)."
            )

    if not basket_impact_notes:
        basket_impact_notes.append("Basket prices are stable — no supply pressure detected.")

    # ── Job opportunity hints ─────────────────────────────────────────────────
    job_opportunity_hints: list[str] = []
    sorted_jobs = sorted(
        summary.job_pressure,
        key=lambda j: j["job_pressure_multiplier"],
        reverse=True,
    )
    for jp in sorted_jobs[:3]:
        job_label = jp["job_key"].replace("_", " ").title()
        opp = jp["opportunity_label"]
        if jp["job_pressure_multiplier"] > 1.05:
            job_opportunity_hints.append(
                f"{job_label}: {opp} opportunity — demand is elevated due to "
                f"supply chain pressure."
            )

    if not job_opportunity_hints:
        job_opportunity_hints.append("No unusual job opportunities from supply chain today.")

    # ── Practical actions ─────────────────────────────────────────────────────
    practical_actions: list[str] = []
    if summary.top_bottleneck_node == "TRUCKING_LASTMILE":
        practical_actions.append("Consider delivery driver side income — transport demand is high.")
    if summary.top_bottleneck_node == "OIL_FUEL":
        practical_actions.append("Fuel costs are elevated; reduce unnecessary commutes today.")
    if summary.most_affected_basket in ("essentials", "protein"):
        practical_actions.append(
            f"Stock up on {summary.most_affected_basket} items before further price rises."
        )
    if summary.best_job_opportunity == "auto_mechanic":
        practical_actions.append("Mechanic work is surging — fuel/transport strain creates demand.")
    if summary.best_job_opportunity == "delivery_driver":
        practical_actions.append("Delivery demand is high — consider extra driving shifts today.")

    if not practical_actions:
        practical_actions.append(
            "No specific supply chain actions required today — maintain normal spending patterns."
        )

    return SupplyChainStoryRecord(
        day=day,
        shortage_story=shortage_story,
        bottleneck_highlights=bottleneck_highlights,
        basket_impact_notes=basket_impact_notes,
        job_opportunity_hints=job_opportunity_hints,
        practical_current_actions=practical_actions,
    )
