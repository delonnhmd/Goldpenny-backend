"""
Static job catalog for Gold Penny.

Jobs are not stored in the database — they are plain Python data used by
the work engine and surfaced through the /jobs/list endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.job_key_service import normalize_job_key

JobCategory = Literal["main", "side"]


@dataclass(frozen=True)
class JobDefinition:
    name: str
    category: JobCategory
    monthly_salary: float   # in game-dollars
    base_stress: int        # flat stress added per shift
    stability: float        # 0-1: how stable the income is
    growth: float           # 0-1: long-term career growth potential
    layoff_risk: float      # 0-1: chance of losing the job
    physical_load: float    # 0-1: physical toll per shift
    mental_load: float      # 0-1: cognitive/emotional toll per shift


# ── Main jobs ────────────────────────────────────────────────────────────────
# hourly = monthly_salary / 30 / 8

JOB_CATALOG: dict[str, JobDefinition] = {
    "auto_mechanic": JobDefinition(
        name="auto_mechanic",
        category="main",
        monthly_salary=20_000.0,
        base_stress=4,
        stability=0.80,
        growth=0.55,
        layoff_risk=0.08,
        physical_load=0.75,
        mental_load=0.30,
    ),
    "aircraft_mechanic": JobDefinition(
        name="aircraft_mechanic",
        category="main",
        monthly_salary=31_000.0,
        base_stress=6,
        stability=0.88,
        growth=0.70,
        layoff_risk=0.05,
        physical_load=0.70,
        mental_load=0.65,
    ),
    "banker": JobDefinition(
        name="banker",
        category="main",
        monthly_salary=25_500.0,
        base_stress=7,
        stability=0.82,
        growth=0.75,
        layoff_risk=0.10,
        physical_load=0.15,
        mental_load=0.80,
    ),
    "chef": JobDefinition(
        name="chef",
        category="main",
        monthly_salary=17_500.0,
        base_stress=8,
        stability=0.72,
        growth=0.60,
        layoff_risk=0.12,
        physical_load=0.65,
        mental_load=0.55,
    ),
    "cleaner": JobDefinition(
        name="cleaner",
        category="main",
        monthly_salary=12_000.0,
        base_stress=4,
        stability=0.62,
        growth=0.28,
        layoff_risk=0.20,
        physical_load=0.72,
        mental_load=0.20,
    ),
    "warehouse_operator": JobDefinition(
        name="warehouse_operator",
        category="main",
        monthly_salary=16_000.0,
        base_stress=6,
        stability=0.70,
        growth=0.45,
        layoff_risk=0.14,
        physical_load=0.80,
        mental_load=0.35,
    ),
    "real_estate_agent": JobDefinition(
        name="real_estate_agent",
        category="main",
        monthly_salary=24_000.0,
        base_stress=7,
        stability=0.68,
        growth=0.72,
        layoff_risk=0.10,
        physical_load=0.20,
        mental_load=0.75,
    ),
    "retail": JobDefinition(
        name="retail",
        category="main",
        monthly_salary=13_000.0,
        base_stress=5,
        stability=0.65,
        growth=0.35,
        layoff_risk=0.18,
        physical_load=0.50,
        mental_load=0.35,
    ),
    # ── Side jobs ─────────────────────────────────────────────────────────────
    "delivery": JobDefinition(
        name="delivery",
        category="main",
        monthly_salary=15_000.0,
        base_stress=3,
        stability=0.60,
        growth=0.20,
        layoff_risk=0.15,
        physical_load=0.55,
        mental_load=0.25,
    ),
    "rideshare": JobDefinition(
        name="rideshare",
        category="side",
        monthly_salary=2_400.0,
        base_stress=2,
        stability=0.50,
        growth=0.10,
        layoff_risk=0.05,
        physical_load=0.25,
        mental_load=0.35,
    ),
}

MAIN_JOBS: set[str] = {name for name, j in JOB_CATALOG.items() if j.category == "main"}
SIDE_JOBS: set[str] = {name for name, j in JOB_CATALOG.items() if j.category == "side"}


def resolve_job_definition(job_key: str | None) -> JobDefinition | None:
    normalized = normalize_job_key(job_key, allow_aliases=True)
    if normalized is None:
        return None
    return JOB_CATALOG.get(normalized)
