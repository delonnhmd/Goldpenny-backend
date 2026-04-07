"""Step 18: Static career progression configuration for all six supported jobs.

Each job has a ``JobCareerConfig`` that controls:
- Skill growth rate per day of work
- Promotion thresholds (per rank transition)
- Rank wage multipliers
- Stress/health sensitivity on skill growth
- Whether entry requires a completed certification
- Certification track key and required in-game days
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services.job_key_service import normalize_main_job_key, supported_main_job_keys_text

# ── Rank constants ─────────────────────────────────────────────────────────────
RANK_ENTRY = "entry"
RANK_INTERMEDIATE = "intermediate"
RANK_ADVANCED = "advanced"
VALID_RANKS = (RANK_ENTRY, RANK_INTERMEDIATE, RANK_ADVANCED)
RANK_ORDER = {RANK_ENTRY: 0, RANK_INTERMEDIATE: 1, RANK_ADVANCED: 2}

# ── Skill scale ────────────────────────────────────────────────────────────────
SKILL_MIN = Decimal("0.0")
SKILL_MAX = Decimal("100.0")

# ── Daily skill delta hard clamp ──────────────────────────────────────────────
SKILL_DELTA_FLOOR = Decimal("0.00")
SKILL_DELTA_CEILING = Decimal("1.20")

# ── Performance score scale ────────────────────────────────────────────────────
PERF_MIN = Decimal("0.0")
PERF_MAX = Decimal("1.0")

# ── Trailing performance window ────────────────────────────────────────────────
TRAILING_PERF_WINDOW_DAYS = 7

# ── Training hours bounds ──────────────────────────────────────────────────────
TRAINING_HOURS_MIN = Decimal("0.0")
TRAINING_HOURS_MAX = Decimal("4.0")   # max training hours allocatable per day

# ── Stress / health thresholds used in skill growth penalties ─────────────────
STRESS_HIGH_THRESHOLD = Decimal("75")
HEALTH_LOW_THRESHOLD = Decimal("50")


@dataclass(frozen=True)
class PromotionThreshold:
    """Minimum requirements to advance from this rank to the next."""

    from_rank: str
    to_rank: str
    min_days_worked: int       # days in current job (resets on job-switch)
    min_skill: Decimal         # current_job_skill must meet this
    min_trailing_performance: Decimal  # trailing_performance_score must meet this


@dataclass(frozen=True)
class JobCareerConfig:
    """Complete career progression definition for a single job."""

    job_key: str
    display_name: str
    base_pay_reference: Decimal           # monthly XGP at entry rank
    max_rank: str = RANK_ADVANCED         # highest achievable rank for MVP

    # Skill growth per day of active work (before modifiers)
    skill_growth_rate: Decimal = Decimal("0.40")

    # Stability weight: how much layoff risk hurts performance score
    stability_weight: Decimal = Decimal("0.10")

    # Stress sensitivity multiplier on skill penalty
    stress_sensitivity: Decimal = Decimal("1.00")

    # Performance weight: how much productivity_modifier drives performance score
    performance_weight: Decimal = Decimal("1.00")

    # Rank → wage multiplier (applied to base_pay_reference)
    rank_wage_multipliers: dict[str, Decimal] = field(default_factory=lambda: {
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.10"),
        RANK_ADVANCED: Decimal("1.22"),
    })

    # Promotion thresholds list (entry→intermediate, intermediate→advanced)
    promotion_thresholds: tuple[PromotionThreshold, ...] = field(default_factory=tuple)

    # Certification gate — True means the player must complete the cert before joining
    certification_required: bool = False
    certification_track_key: str = ""
    certification_days_required: int = 0

    # Extra skill gain per training hour (above and beyond worked_component)
    training_skill_rate: Decimal = Decimal("0.10")


# ── Job Configurations ─────────────────────────────────────────────────────────

AUTO_MECHANIC_CONFIG = JobCareerConfig(
    job_key="auto_mechanic",
    display_name="Auto Mechanic",
    base_pay_reference=Decimal("4000.00"),
    skill_growth_rate=Decimal("0.42"),
    stability_weight=Decimal("0.12"),
    stress_sensitivity=Decimal("0.90"),
    performance_weight=Decimal("1.00"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.12"),
        RANK_ADVANCED: Decimal("1.26"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=20,
            min_skill=Decimal("18.0"),
            min_trailing_performance=Decimal("0.62"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=60,
            min_skill=Decimal("42.0"),
            min_trailing_performance=Decimal("0.70"),
        ),
    ),
    certification_required=True,
    certification_track_key="auto_mechanic_cert",
    certification_days_required=3,
    training_skill_rate=Decimal("0.09"),
)

AIRCRAFT_MECHANIC_CONFIG = JobCareerConfig(
    job_key="aircraft_mechanic",
    display_name="Aircraft Mechanic",
    base_pay_reference=Decimal("6200.00"),
    skill_growth_rate=Decimal("0.38"),
    stability_weight=Decimal("0.08"),
    stress_sensitivity=Decimal("0.80"),
    performance_weight=Decimal("1.10"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.11"),
        RANK_ADVANCED: Decimal("1.24"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=25,
            min_skill=Decimal("22.0"),
            min_trailing_performance=Decimal("0.67"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=70,
            min_skill=Decimal("48.0"),
            min_trailing_performance=Decimal("0.74"),
        ),
    ),
    certification_required=True,
    certification_track_key="aircraft_mechanic_cert",
    certification_days_required=6,
    training_skill_rate=Decimal("0.12"),
)

BANKER_CONFIG = JobCareerConfig(
    job_key="banker",
    display_name="Banker",
    base_pay_reference=Decimal("5100.00"),
    skill_growth_rate=Decimal("0.36"),
    stability_weight=Decimal("0.14"),
    stress_sensitivity=Decimal("1.20"),   # mentally stressful job
    performance_weight=Decimal("1.15"),   # performance-sensitive
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.14"),
        RANK_ADVANCED: Decimal("1.28"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=22,
            min_skill=Decimal("20.0"),
            min_trailing_performance=Decimal("0.65"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=65,
            min_skill=Decimal("46.0"),
            min_trailing_performance=Decimal("0.72"),
        ),
    ),
    certification_required=True,
    certification_track_key="banking_license",
    certification_days_required=5,
    training_skill_rate=Decimal("0.08"),
)

CHEF_CONFIG = JobCareerConfig(
    job_key="chef",
    display_name="Chef",
    base_pay_reference=Decimal("3500.00"),
    skill_growth_rate=Decimal("0.44"),
    stability_weight=Decimal("0.10"),
    stress_sensitivity=Decimal("1.10"),   # physically + mentally intense
    performance_weight=Decimal("1.00"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.10"),
        RANK_ADVANCED: Decimal("1.22"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=20,
            min_skill=Decimal("17.0"),
            min_trailing_performance=Decimal("0.62"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=58,
            min_skill=Decimal("40.0"),
            min_trailing_performance=Decimal("0.69"),
        ),
    ),
    certification_required=True,
    certification_track_key="chef_cert",
    certification_days_required=2,
    training_skill_rate=Decimal("0.10"),
)

CLEANER_CONFIG = JobCareerConfig(
    job_key="cleaner",
    display_name="Cleaner",
    base_pay_reference=Decimal("2400.00"),
    skill_growth_rate=Decimal("0.26"),
    stability_weight=Decimal("0.07"),
    stress_sensitivity=Decimal("0.95"),
    performance_weight=Decimal("0.86"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.07"),
        RANK_ADVANCED: Decimal("1.14"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=14,
            min_skill=Decimal("12.0"),
            min_trailing_performance=Decimal("0.56"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=40,
            min_skill=Decimal("28.0"),
            min_trailing_performance=Decimal("0.60"),
        ),
    ),
    certification_required=False,
    training_skill_rate=Decimal("0.06"),
)

WAREHOUSE_OPERATOR_CONFIG = JobCareerConfig(
    job_key="warehouse_operator",
    display_name="Warehouse Operator",
    base_pay_reference=Decimal("3200.00"),
    skill_growth_rate=Decimal("0.34"),
    stability_weight=Decimal("0.11"),
    stress_sensitivity=Decimal("1.02"),
    performance_weight=Decimal("0.96"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.09"),
        RANK_ADVANCED: Decimal("1.18"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=18,
            min_skill=Decimal("16.0"),
            min_trailing_performance=Decimal("0.60"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=52,
            min_skill=Decimal("36.0"),
            min_trailing_performance=Decimal("0.66"),
        ),
    ),
    certification_required=False,
    training_skill_rate=Decimal("0.08"),
)

RETAIL_CONFIG = JobCareerConfig(
    job_key="retail",
    display_name="Retail",
    base_pay_reference=Decimal("2600.00"),
    skill_growth_rate=Decimal("0.30"),    # low barrier, lower ceiling
    stability_weight=Decimal("0.08"),
    stress_sensitivity=Decimal("0.85"),
    performance_weight=Decimal("0.90"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.08"),
        RANK_ADVANCED: Decimal("1.16"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=15,
            min_skill=Decimal("14.0"),
            min_trailing_performance=Decimal("0.58"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=45,
            min_skill=Decimal("32.0"),
            min_trailing_performance=Decimal("0.64"),
        ),
    ),
    certification_required=False,
    training_skill_rate=Decimal("0.07"),
)

DELIVERY_CONFIG = JobCareerConfig(
    job_key="delivery",
    display_name="Delivery",
    base_pay_reference=Decimal("3000.00"),
    skill_growth_rate=Decimal("0.28"),    # flexible but lower ceiling
    stability_weight=Decimal("0.07"),
    stress_sensitivity=Decimal("0.80"),
    performance_weight=Decimal("0.92"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.07"),
        RANK_ADVANCED: Decimal("1.14"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=14,
            min_skill=Decimal("13.0"),
            min_trailing_performance=Decimal("0.56"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=42,
            min_skill=Decimal("30.0"),
            min_trailing_performance=Decimal("0.62"),
        ),
    ),
    certification_required=False,
    training_skill_rate=Decimal("0.07"),
)

REAL_ESTATE_AGENT_CONFIG = JobCareerConfig(
    job_key="real_estate_agent",
    display_name="Real Estate Agent",
    base_pay_reference=Decimal("4800.00"),
    skill_growth_rate=Decimal("0.33"),
    stability_weight=Decimal("0.09"),
    stress_sensitivity=Decimal("1.08"),
    performance_weight=Decimal("1.12"),
    rank_wage_multipliers={
        RANK_ENTRY: Decimal("1.00"),
        RANK_INTERMEDIATE: Decimal("1.12"),
        RANK_ADVANCED: Decimal("1.25"),
    },
    promotion_thresholds=(
        PromotionThreshold(
            from_rank=RANK_ENTRY,
            to_rank=RANK_INTERMEDIATE,
            min_days_worked=21,
            min_skill=Decimal("19.0"),
            min_trailing_performance=Decimal("0.64"),
        ),
        PromotionThreshold(
            from_rank=RANK_INTERMEDIATE,
            to_rank=RANK_ADVANCED,
            min_days_worked=64,
            min_skill=Decimal("45.0"),
            min_trailing_performance=Decimal("0.72"),
        ),
    ),
    certification_required=True,
    certification_track_key="real_estate_license",
    certification_days_required=4,
    training_skill_rate=Decimal("0.08"),
)

# ── Registry ───────────────────────────────────────────────────────────────────

CAREER_CONFIG: dict[str, JobCareerConfig] = {
    "auto_mechanic": AUTO_MECHANIC_CONFIG,
    "aircraft_mechanic": AIRCRAFT_MECHANIC_CONFIG,
    "banker": BANKER_CONFIG,
    "chef": CHEF_CONFIG,
    "cleaner": CLEANER_CONFIG,
    "warehouse_operator": WAREHOUSE_OPERATOR_CONFIG,
    "real_estate_agent": REAL_ESTATE_AGENT_CONFIG,
    "retail": RETAIL_CONFIG,
    "delivery": DELIVERY_CONFIG,
}

VALID_JOB_KEYS: frozenset[str] = frozenset(CAREER_CONFIG.keys())

# Certification tracks — keyed by certification_track_key
CERTIFICATION_CATALOG: dict[str, dict] = {
    "chef_cert": {
        "display_name": "Chef Certification",
        "required_days": 2,
        "unlocks_job": "chef",
        "cost_xgp": 20,
        "description": (
            "2 in-game days of culinary training. Allocate at least "
            "1 hour/day in training to progress."
        ),
    },
    "auto_mechanic_cert": {
        "display_name": "Auto Mechanic Certification",
        "required_days": 3,
        "unlocks_job": "auto_mechanic",
        "cost_xgp": 40,
        "description": (
            "3 in-game days of workshop training. Allocate at least "
            "1 hour/day in training to progress."
        ),
    },
    "aircraft_mechanic_cert": {
        "display_name": "Aircraft Mechanic Certification",
        "required_days": 6,
        "unlocks_job": "aircraft_mechanic",
        "cost_xgp": 100,
        "description": (
            "6 in-game days of structured training. Must allocate at least "
            "1 hour/day to advance."
        ),
    },
    "banking_license": {
        "display_name": "Banking License",
        "required_days": 5,
        "unlocks_job": "banker",
        "cost_xgp": 80,
        "description": (
            "5 in-game days of finance compliance training. Allocate at least "
            "1 hour/day in training to progress."
        ),
    },
    "real_estate_license": {
        "display_name": "Real Estate License",
        "required_days": 4,
        "unlocks_job": "real_estate_agent",
        "cost_xgp": 60,
        "description": (
            "4 in-game days of property and contract training. Allocate at least "
            "1 hour/day in training to progress."
        ),
    },
}


def get_job_config(job_key: str) -> JobCareerConfig:
    """Return the career config for *job_key*, raising ValueError if unknown."""
    normalized_key = normalize_main_job_key(job_key, allow_aliases=True)
    cfg = CAREER_CONFIG.get(normalized_key or "")
    if cfg is None:
        raise ValueError(
            f"Unknown job key: {job_key!r}. Valid main jobs: {supported_main_job_keys_text()}"
        )
    return cfg


def get_promotion_threshold(job_key: str, from_rank: str) -> PromotionThreshold | None:
    """Return the promotion threshold for the given from_rank, or None if none exists."""
    cfg = get_job_config(job_key)
    for threshold in cfg.promotion_thresholds:
        if threshold.from_rank == from_rank:
            return threshold
    return None


def effective_monthly_pay(job_key: str, rank: str, skill: Decimal) -> Decimal:
    """Return the effective monthly pay for *job_key* at *rank* with *skill*.

    Formula:
        pay = base_pay * rank_multiplier * (1 + skill_bonus)
        skill_bonus = clamp(skill / 200, 0.00, 0.15)  → max +15% at skill 30+

    The total wage uplift from rank entry→advanced is roughly 22–28%, and the
    skill modifier can add up to 15% on top. Combined ceiling is bounded.
    """
    from decimal import ROUND_HALF_UP
    cfg = get_job_config(job_key)
    multiplier = cfg.rank_wage_multipliers.get(rank, Decimal("1.00"))
    skill_bonus = min(skill / Decimal("200"), Decimal("0.15"))
    pay = cfg.base_pay_reference * multiplier * (Decimal("1.00") + skill_bonus)
    return pay.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def next_rank(current_rank: str) -> str | None:
    """Return the rank after *current_rank*, or None if already at advanced."""
    idx = RANK_ORDER.get(current_rank, -1)
    for name, i in RANK_ORDER.items():
        if i == idx + 1:
            return name
    return None
