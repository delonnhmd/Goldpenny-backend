"""Job market pressure + layoff/promotion progression service.

This layer keeps employment behavior explainable and bounded:
- Jobs react to macro pressure and region opportunity.
- Layoff risk exists but remains controlled for stable roles.
- Wages are sticky (small daily adjustments).
- Promotion events are possible under skill/productivity/growth conditions.
"""

from __future__ import annotations

from datetime import date
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.supply_chain_service import compute_supply_chain_daily_snapshot
from app.models.job_definition import JOB_CATALOG
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.services.housing_region_service import get_active_housing_state
from app.services.job_key_service import job_key_lookup_variants, normalize_main_job_key

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")
PCT_Q = Decimal("0.01")

DEFAULT_REGION_OPPORTUNITY = {
    "suburban": Decimal("0.9500"),
    "downtown": Decimal("1.0900"),
}

# Per-job behavior knobs. All values are intentionally small/bounded.
JOB_BEHAVIOR: dict[str, dict[str, Decimal | int]] = {
    "auto_mechanic": {
        "unemployment_w": Decimal("0.45"),
        "confidence_w": Decimal("0.08"),
        "inflation_w": Decimal("0.07"),
        "oil_w": Decimal("-0.02"),  # mild tailwind from transport wear
        "rate_w": Decimal("0.03"),
        "opportunity_bias": Decimal("1.00"),
        "oil_wage_drag": Decimal("-0.01"),
        "promotion_gate": 1,
        "layoff_floor": Decimal("1.10"),
    },
    "aircraft_mechanic": {
        "unemployment_w": Decimal("0.24"),
        "confidence_w": Decimal("0.06"),
        "inflation_w": Decimal("0.05"),
        "oil_w": Decimal("0.04"),
        "rate_w": Decimal("0.04"),
        "opportunity_bias": Decimal("0.98"),
        "oil_wage_drag": Decimal("0.01"),
        "promotion_gate": 4,
        "layoff_floor": Decimal("0.60"),
    },
    "banker": {
        "unemployment_w": Decimal("0.52"),
        "confidence_w": Decimal("0.14"),
        "inflation_w": Decimal("0.05"),
        "oil_w": Decimal("0.01"),
        "rate_w": Decimal("0.10"),
        "opportunity_bias": Decimal("1.05"),
        "oil_wage_drag": Decimal("0.01"),
        "promotion_gate": 2,
        "layoff_floor": Decimal("1.40"),
    },
    "chef": {
        "unemployment_w": Decimal("0.62"),
        "confidence_w": Decimal("0.16"),
        "inflation_w": Decimal("0.10"),
        "oil_w": Decimal("0.03"),
        "rate_w": Decimal("0.04"),
        "opportunity_bias": Decimal("1.01"),
        "oil_wage_drag": Decimal("0.02"),
        "promotion_gate": 1,
        "layoff_floor": Decimal("1.80"),
    },
    "retail": {
        "unemployment_w": Decimal("0.90"),
        "confidence_w": Decimal("0.24"),
        "inflation_w": Decimal("0.12"),
        "oil_w": Decimal("0.04"),
        "rate_w": Decimal("0.08"),
        "opportunity_bias": Decimal("0.96"),
        "oil_wage_drag": Decimal("0.03"),
        "promotion_gate": 1,
        "layoff_floor": Decimal("2.60"),
    },
    "delivery": {
        "unemployment_w": Decimal("0.58"),
        "confidence_w": Decimal("0.09"),
        "inflation_w": Decimal("0.08"),
        "oil_w": Decimal("0.24"),  # fuel pressure hits this role
        "rate_w": Decimal("0.04"),
        "opportunity_bias": Decimal("1.02"),
        "oil_wage_drag": Decimal("0.07"),
        "promotion_gate": 1,
        "layoff_floor": Decimal("2.00"),
    },
}

DEFAULT_BEHAVIOR: dict[str, Decimal | int] = {
    "unemployment_w": Decimal("0.55"),
    "confidence_w": Decimal("0.10"),
    "inflation_w": Decimal("0.08"),
    "oil_w": Decimal("0.04"),
    "rate_w": Decimal("0.05"),
    "opportunity_bias": Decimal("1.00"),
    "oil_wage_drag": Decimal("0.02"),
    "promotion_gate": 1,
    "layoff_floor": Decimal("1.50"),
}

JOB_MARKET_OPPORTUNITY_MULTIPLIER = Decimal("1.25")
JOB_MARKET_WAGE_DRIFT_MULTIPLIER = Decimal("0.015")
JOB_MARKET_LAYOFF_MULTIPLIER = Decimal("0.50")

JOB_MARKET_OPPORTUNITY_MIN = Decimal("-0.40")
JOB_MARKET_OPPORTUNITY_MAX = Decimal("0.40")
JOB_MARKET_WAGE_DRIFT_MIN = Decimal("-0.01")
JOB_MARKET_WAGE_DRIFT_MAX = Decimal("0.01")
JOB_MARKET_LAYOFF_MIN = Decimal("-0.05")
JOB_MARKET_LAYOFF_MAX = Decimal("0.08")

SUPPORTED_JOB_KEYS = (
    "auto_mechanic",
    "aircraft_mechanic",
    "banker",
    "chef",
    "cleaner",
    "warehouse_operator",
    "real_estate_agent",
    "retail",
    "delivery",
)


class JobMarketError(Exception):
    """Base exception for job market progression."""


class JobMarketNotFoundError(JobMarketError):
    """Raised when required player/employment resources are missing."""


class JobMarketValidationError(JobMarketError):
    """Raised for invalid requests (for example, invalid day)."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _pct(value: Decimal) -> Decimal:
    return value.quantize(PCT_Q, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(maximum, value))


def _ratio(value: object, default: Decimal) -> Decimal:
    raw = _d(value) if value is not None else default
    if raw > Decimal("1.50"):
        raw = raw / Decimal("100")
    return _clamp(raw, Decimal("0.00"), Decimal("1.50"))


def _deterministic_roll(key: str, day: int, salt: str) -> Decimal:
    digest = hashlib.sha256(f"{key}:{day}:{salt}".encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return Decimal(n) / Decimal(16**16 - 1)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise JobMarketNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise JobMarketNotFoundError("Player not found.")
    return player


def _latest_macro_for_day(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= day)
        .order_by(MacroDailyState.day.desc())
        .first()
    )
    if row is not None:
        return row
    return db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()


def _macro_for_market_request(
    db: Session,
    *,
    as_of_date: date | None = None,
    day: int | None = None,
) -> MacroDailyState | None:
    if day is not None:
        return (
            db.query(MacroDailyState)
            .filter(MacroDailyState.day <= int(day))
            .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
            .first()
        )
    if as_of_date is not None:
        row = (
            db.query(MacroDailyState)
            .filter(func.date(MacroDailyState.created_at) <= as_of_date.isoformat())
            .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
            .first()
        )
        if row is not None:
            return row
    return (
        db.query(MacroDailyState)
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )


def compute_daily_job_market_updates(
    db: Session,
    as_of_date: date | None = None,
    *,
    day: int | None = None,
) -> dict[str, Any]:
    """Compute deterministic economy-level job modifiers from supply-chain pressure."""
    if day is not None and int(day) <= 0:
        raise JobMarketValidationError("day must be greater than 0.")

    macro = _macro_for_market_request(db, as_of_date=as_of_date, day=day)
    if macro is None:
        raise JobMarketNotFoundError("Macro state not found for job market compute.")

    target_day = int(day) if day is not None else int(macro.day)

    supply_snapshot = compute_supply_chain_daily_snapshot(
        db=db,
        as_of_date=as_of_date if day is None else None,
        macro_day=int(macro.day),
    )
    pressure_by_job = {
        str(row["job_key"]): row for row in supply_snapshot.get("job_pressure", [])
    }

    updates: list[dict[str, Any]] = []
    for job_key in SUPPORTED_JOB_KEYS:
        row = pressure_by_job.get(job_key, {})
        pressure = _q4(_d(row.get("pressure", 0)))
        direction = str(row.get("direction", "neutral"))

        opportunity_modifier = _clamp(
            _q4(pressure * JOB_MARKET_OPPORTUNITY_MULTIPLIER),
            JOB_MARKET_OPPORTUNITY_MIN,
            JOB_MARKET_OPPORTUNITY_MAX,
        )
        wage_drift_modifier = _clamp(
            _q4(pressure * JOB_MARKET_WAGE_DRIFT_MULTIPLIER),
            JOB_MARKET_WAGE_DRIFT_MIN,
            JOB_MARKET_WAGE_DRIFT_MAX,
        )
        layoff_risk_modifier = _clamp(
            _q4((-pressure) * JOB_MARKET_LAYOFF_MULTIPLIER),
            JOB_MARKET_LAYOFF_MIN,
            JOB_MARKET_LAYOFF_MAX,
        )

        updates.append(
            {
                "job_key": job_key,
                "pressure": float(pressure),
                "direction": direction,
                "opportunity_modifier": float(opportunity_modifier),
                "wage_drift_modifier": float(wage_drift_modifier),
                "layoff_risk_modifier": float(layoff_risk_modifier),
            }
        )

    updates.sort(key=lambda row: row["job_key"])

    return {
        "as_of_date": (
            as_of_date
            if as_of_date is not None
            else (macro.created_at.date() if macro.created_at else date.today())
        ),
        "macro_state_id": int(macro.id),
        "day": int(target_day),
        "job_updates": updates,
        "debug_meta": {
            "constants_version": "job_market_v1",
            "macro_day_used": int(macro.day),
            "modifier_clamps": {
                "opportunity": [float(JOB_MARKET_OPPORTUNITY_MIN), float(JOB_MARKET_OPPORTUNITY_MAX)],
                "wage_drift": [float(JOB_MARKET_WAGE_DRIFT_MIN), float(JOB_MARKET_WAGE_DRIFT_MAX)],
                "layoff_risk": [float(JOB_MARKET_LAYOFF_MIN), float(JOB_MARKET_LAYOFF_MAX)],
            },
            "multipliers": {
                "opportunity": float(JOB_MARKET_OPPORTUNITY_MULTIPLIER),
                "wage_drift": float(JOB_MARKET_WAGE_DRIFT_MULTIPLIER),
                "layoff_risk": float(JOB_MARKET_LAYOFF_MULTIPLIER),
            },
        },
    }


def _latest_employment_state(
    db: Session,
    player_id: UUID,
    day: int | None = None,
) -> PlayerEmploymentState | None:
    q = db.query(PlayerEmploymentState).filter(PlayerEmploymentState.player_id == player_id)
    if day is not None:
        q = q.filter(PlayerEmploymentState.day <= int(day))
    return q.order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc()).first()


def _employment_state_for_exact_day(
    db: Session,
    player_id: UUID,
    day: int,
) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player_id,
            PlayerEmploymentState.day == int(day),
        )
        .order_by(PlayerEmploymentState.created_at.desc())
        .first()
    )


def _job_meta(db: Session, job_code: str | None) -> dict[str, Any]:
    if not job_code:
        return {
            "job_code": None,
            "title": None,
            "base_monthly_pay_xgp": Decimal("0.00"),
            "stability_ratio": Decimal("0.65"),
            "growth_ratio": Decimal("0.40"),
            "promotion_threshold": 100,
            "base_layoff_ratio": Decimal("0.15"),
        }

    normalized = normalize_main_job_key(job_code, allow_aliases=True) or job_code.strip().lower()
    lookup_variants = job_key_lookup_variants(normalized, allow_side_jobs=False)
    db_row = (
        db.query(JobDefinitionDB)
        .filter(JobDefinitionDB.job_code.in_(lookup_variants or (normalized,)))
        .first()
    )
    static_row = JOB_CATALOG.get(normalized)

    if db_row is not None:
        base_pay = _money(_d(db_row.base_monthly_pay_xgp))
        stability = _ratio(db_row.stability_pct, Decimal("0.65"))
        growth = _ratio(db_row.growth_pct, Decimal("0.40"))
        threshold = int(getattr(db_row, "promotion_threshold", 100) or 100)
        base_layoff_ratio = _clamp((Decimal("1.0") - stability) * Decimal("0.18"), Decimal("0.01"), Decimal("0.25"))
        return {
            "job_code": normalized,
            "title": getattr(db_row, "title", normalized.replace("_", " ").title()),
            "base_monthly_pay_xgp": base_pay,
            "stability_ratio": stability,
            "growth_ratio": growth,
            "promotion_threshold": threshold,
            "base_layoff_ratio": base_layoff_ratio,
        }

    if static_row is not None:
        return {
            "job_code": normalized,
            "title": static_row.name.replace("_", " ").title(),
            "base_monthly_pay_xgp": _money(_d(static_row.monthly_salary)),
            "stability_ratio": _ratio(static_row.stability, Decimal("0.65")),
            "growth_ratio": _ratio(static_row.growth, Decimal("0.40")),
            "promotion_threshold": 100,
            "base_layoff_ratio": _ratio(static_row.layoff_risk, Decimal("0.12")),
        }

    return {
        "job_code": normalized,
        "title": normalized.replace("_", " ").title(),
        "base_monthly_pay_xgp": Decimal("0.00"),
        "stability_ratio": Decimal("0.65"),
        "growth_ratio": Decimal("0.40"),
        "promotion_threshold": 100,
        "base_layoff_ratio": Decimal("0.15"),
    }


def _job_behavior(job_code: str | None) -> dict[str, Decimal | int]:
    if not job_code:
        return DEFAULT_BEHAVIOR
    normalized = normalize_main_job_key(job_code, allow_aliases=True) or job_code.strip().lower()
    return JOB_BEHAVIOR.get(normalized, DEFAULT_BEHAVIOR)


def _normalize_status(state: PlayerEmploymentState | None, has_job_code: bool) -> str:
    if state is None:
        return "employed" if has_job_code else "seeking"
    raw = (getattr(state, "job_status", "") or "").strip().lower()
    if raw in {"employed", "laid_off", "seeking"}:
        return raw
    if bool(getattr(state, "employed_flag", False)):
        return "employed"
    return "seeking"


def _resolve_region_inputs(
    player: Player,
    housing_state: object | None,
) -> tuple[str, Decimal, Decimal, int]:
    region = (
        (getattr(housing_state, "region", None) or player.housing_region_id or player.region or "suburban")
        .strip()
        .lower()
    )
    fallback_opportunity = DEFAULT_REGION_OPPORTUNITY.get(region, Decimal("1.0000"))
    opportunity_modifier = _q4(
        _d(getattr(housing_state, "opportunity_modifier", fallback_opportunity))
    )
    commute_modifier = _q4(_d(getattr(housing_state, "commute_modifier", Decimal("1.0000"))))
    stress_modifier = int(getattr(housing_state, "stress_modifier", 0) or 0)
    return region, opportunity_modifier, commute_modifier, stress_modifier


def _bootstrap_or_clone_state_for_day(
    db: Session,
    player: Player,
    day: int,
) -> tuple[PlayerEmploymentState, bool]:
    existing = _employment_state_for_exact_day(db, player.id, day)
    if existing is not None:
        return existing, False

    latest = _latest_employment_state(db, player.id, day=None)
    if latest is not None:
        state = PlayerEmploymentState(
            player_id=player.id,
            day=day,
            current_job_code=latest.current_job_code,
            skill_level=int(latest.skill_level or player.skill_level or 1),
            monthly_pay_xgp=_money(_d(latest.monthly_pay_xgp)),
            employed_flag=bool(latest.employed_flag),
            layoff_risk_pct=_pct(_d(latest.layoff_risk_pct)),
            productivity_modifier=_q4(_d(latest.productivity_modifier)),
            job_status=_normalize_status(latest, bool(latest.current_job_code)),
            promotion_eligible_flag=False,
            promotion_count=int(getattr(latest, "promotion_count", 0) or 0),
            last_raise_pct=Decimal("0.00"),
            last_employment_event=None,
            opportunity_score=_q4(_d(getattr(latest, "opportunity_score", 1.0))),
            layoff_event_flag=False,
            promotion_chance_pct=Decimal("0.00"),
            wage_adjustment_pct=Decimal("0.00"),
            employment_evaluated_flag=False,
        )
        db.add(state)
        db.flush()
        return state, True

    seed_job = normalize_main_job_key(player.main_job, allow_aliases=True) or None
    seed_meta = _job_meta(db, seed_job)
    employed = bool(seed_job)
    state = PlayerEmploymentState(
        player_id=player.id,
        day=day,
        current_job_code=seed_job,
        skill_level=max(int(player.skill_level or 1), 1),
        monthly_pay_xgp=_money(_d(seed_meta["base_monthly_pay_xgp"])) if employed else Decimal("0.00"),
        employed_flag=employed,
        layoff_risk_pct=Decimal("0.00"),
        productivity_modifier=Decimal("1.0000"),
        job_status="employed" if employed else "seeking",
        promotion_eligible_flag=False,
        promotion_count=0,
        last_raise_pct=Decimal("0.00"),
        last_employment_event=None,
        opportunity_score=Decimal("1.0000"),
        layoff_event_flag=False,
        promotion_chance_pct=Decimal("0.00"),
        wage_adjustment_pct=Decimal("0.00"),
        employment_evaluated_flag=False,
    )
    db.add(state)
    db.flush()
    return state, True


def _serialize_event_result(
    player: Player,
    day: int,
    state: PlayerEmploymentState,
    *,
    employment_event: str,
    monthly_pay_before: Decimal,
    monthly_pay_after: Decimal,
    already_processed: bool,
) -> dict[str, Any]:
    return {
        "player_id": str(player.id),
        "day": int(day),
        "current_job_code": state.current_job_code,
        "employment_status": _normalize_status(state, bool(state.current_job_code)),
        "employment_event": employment_event,
        "layoff_event_flag": bool(getattr(state, "layoff_event_flag", False)),
        "layoff_risk_pct": float(_pct(_d(getattr(state, "layoff_risk_pct", 0)))),
        "promotion_chance_pct": float(_pct(_d(getattr(state, "promotion_chance_pct", 0)))),
        "wage_adjustment_pct": float(_pct(_d(getattr(state, "wage_adjustment_pct", 0)))),
        "monthly_pay_before": float(_money(_d(monthly_pay_before))),
        "monthly_pay_after": float(_money(_d(monthly_pay_after))),
        "monthly_pay_xgp_after_event": float(_money(_d(monthly_pay_after))),
        "skill_level": int(state.skill_level or 1),
        "opportunity_score": float(_q4(_d(getattr(state, "opportunity_score", 1.0)))),
        "productivity_modifier": float(_q4(_d(getattr(state, "productivity_modifier", 1.0)))),
        "promotion_count": int(getattr(state, "promotion_count", 0) or 0),
        "last_raise_pct": float(_pct(_d(getattr(state, "last_raise_pct", 0)))),
        "already_processed": already_processed,
    }


def compute_job_market_pressure(db: Session, player_id: str | UUID, day: int) -> dict[str, Any]:
    """Compute bounded market pressure metrics without mutating DB state."""
    if day <= 0:
        raise JobMarketValidationError("day must be greater than 0.")

    player = _resolve_player(db, player_id)
    employment = _latest_employment_state(db, player.id, day)
    job_code = normalize_main_job_key(
        (employment.current_job_code if employment else None) or player.main_job or "",
        allow_aliases=True,
    ) or None
    status = _normalize_status(employment, bool(job_code))

    macro = _latest_macro_for_day(db, day)
    inflation = _d(getattr(macro, "inflation_rate", 2.0))
    interest = _d(getattr(macro, "interest_rate", 4.0))
    unemployment = _d(getattr(macro, "unemployment_rate", 5.0))
    oil = _d(getattr(macro, "oil_index", 100.0))
    confidence = _d(getattr(macro, "consumer_confidence", 50.0))

    housing_state = get_active_housing_state(db, player.id)
    region, region_opportunity, commute_modifier, housing_stress_modifier = _resolve_region_inputs(player, housing_state)

    job_meta = _job_meta(db, job_code)
    behavior = _job_behavior(job_code)
    try:
        daily_job_market = compute_daily_job_market_updates(db, day=int(day))
    except JobMarketError:
        daily_job_market = {
            "day": int(day),
            "job_updates": [],
        }
    job_update_lookup = {
        str(row["job_key"]): row for row in daily_job_market.get("job_updates", [])
    }
    active_job_update = job_update_lookup.get(
        (job_code or "").strip().lower(),
        {
            "pressure": 0.0,
            "direction": "neutral",
            "opportunity_modifier": 0.0,
            "wage_drift_modifier": 0.0,
            "layoff_risk_modifier": 0.0,
        },
    )
    active_job_pressure = _q4(_d(active_job_update.get("pressure", 0)))
    active_job_direction = str(active_job_update.get("direction", "neutral"))
    active_job_opportunity_modifier = _q4(_d(active_job_update.get("opportunity_modifier", 0)))
    active_job_wage_drift_modifier = _q4(_d(active_job_update.get("wage_drift_modifier", 0)))
    active_job_layoff_risk_modifier = _q4(_d(active_job_update.get("layoff_risk_modifier", 0)))

    base_productivity = _q4(_d(getattr(employment, "productivity_modifier", 1.0)))
    stress_drag = Decimal(max(int(player.stress or 0) - 55, 0)) / Decimal("220")
    health_boost = Decimal(max(int(player.health or 100) - 65, 0)) / Decimal("260")
    commute_drag = max(Decimal("0.0"), commute_modifier - Decimal("1.0")) * Decimal("0.35")
    housing_stress_drag = Decimal(max(housing_stress_modifier, 0)) / Decimal("120")

    macro_opportunity = (
        Decimal("1.00")
        + ((confidence - Decimal("50")) / Decimal("180"))
        - (max(unemployment - Decimal("5"), Decimal("0")) / Decimal("55"))
        - (max(inflation - Decimal("3"), Decimal("0")) / Decimal("120"))
        - (max(interest - Decimal("4"), Decimal("0")) / Decimal("160"))
    )
    opportunity_score = _clamp(
        macro_opportunity * region_opportunity * _d(behavior["opportunity_bias"]),
        Decimal("0.70"),
        Decimal("1.45"),
    )
    opportunity_score = _clamp(
        opportunity_score * (Decimal("1.00") + (active_job_opportunity_modifier * Decimal("0.35"))),
        Decimal("0.70"),
        Decimal("1.45"),
    )

    opportunity_boost = max(Decimal("0.0"), opportunity_score - Decimal("1.0")) * Decimal("0.20")
    productivity_modifier = _clamp(
        base_productivity - stress_drag - commute_drag - housing_stress_drag + health_boost + opportunity_boost,
        Decimal("0.70"),
        Decimal("1.25"),
    )

    employed_now = status == "employed" and bool(job_code) and bool(getattr(employment, "employed_flag", True))
    if not employed_now:
        return {
            "player_id": str(player.id),
            "day": int(day),
            "current_job_code": job_code,
            "employment_status": status,
            "opportunity_score": float(_q4(opportunity_score)),
            "layoff_risk_pct": 0.0,
            "promotion_chance_pct": 0.0,
            "wage_adjustment_pct": 0.0,
            "productivity_modifier": float(_q4(productivity_modifier)),
            "region": region,
            "region_opportunity_modifier": float(_q4(region_opportunity)),
            "commute_modifier": float(_q4(commute_modifier)),
            "macro_day_used": int(getattr(macro, "day", day) or day),
            "job_market_day_used": int(daily_job_market.get("day", day)),
            "active_job_pressure": float(active_job_pressure),
            "active_job_direction": active_job_direction,
            "active_job_opportunity_modifier": float(active_job_opportunity_modifier),
            "active_job_wage_drift_modifier": float(active_job_wage_drift_modifier),
            "active_job_layoff_risk_modifier": float(active_job_layoff_risk_modifier),
        }

    base_layoff_pct = _d(job_meta["base_layoff_ratio"]) * Decimal("100")
    unemployment_term = max(unemployment - Decimal("5"), Decimal("0")) * _d(behavior["unemployment_w"])
    confidence_term = max(Decimal("50") - confidence, Decimal("0")) * _d(behavior["confidence_w"])
    inflation_term = max(inflation - Decimal("3"), Decimal("0")) * _d(behavior["inflation_w"])
    oil_term = (max(oil - Decimal("100"), Decimal("0")) / Decimal("20")) * _d(behavior["oil_w"])
    rate_term = max(interest - Decimal("4"), Decimal("0")) * _d(behavior["rate_w"])
    stress_term = Decimal(max(int(player.stress or 0) - 65, 0)) * Decimal("0.08")
    region_term = Decimal("-0.80") if region == "downtown" else Decimal("0.40")
    productivity_buffer = (
        max(productivity_modifier - Decimal("1.0"), Decimal("0")) * Decimal("7.0")
        + max(opportunity_score - Decimal("1.0"), Decimal("0")) * Decimal("4.0")
    )
    layoff_risk_pct = _clamp(
        base_layoff_pct
        + unemployment_term
        + confidence_term
        + inflation_term
        + oil_term
        + rate_term
        + stress_term
        + region_term
        - productivity_buffer,
        _d(behavior["layoff_floor"]),
        Decimal("35.00"),
    )
    layoff_risk_pct = _clamp(
        layoff_risk_pct + (active_job_layoff_risk_modifier * Decimal("100")),
        _d(behavior["layoff_floor"]),
        Decimal("35.00"),
    )

    skill_level = int(getattr(employment, "skill_level", player.skill_level) or 1)
    promotion_threshold = max(int(job_meta["promotion_threshold"] or 100), 1)
    skill_progress = _clamp(
        Decimal(skill_level * 10) / Decimal(promotion_threshold),
        Decimal("0.00"),
        Decimal("1.40"),
    )
    growth_ratio = _d(job_meta["growth_ratio"])
    promotion_gate = int(behavior["promotion_gate"])
    if skill_level < promotion_gate:
        promotion_chance_pct = Decimal("0.00")
    else:
        promotion_chance_pct = _clamp(
            (skill_progress * growth_ratio * Decimal("8.0"))
            + (max(opportunity_score - Decimal("1.0"), Decimal("0")) * Decimal("12.0"))
            + (max(productivity_modifier - Decimal("1.0"), Decimal("0")) * Decimal("14.0"))
            + (max(confidence - Decimal("50"), Decimal("0")) * Decimal("0.03"))
            - (max(unemployment - Decimal("5"), Decimal("0")) * Decimal("0.35")),
            Decimal("0.00"),
            Decimal("20.00"),
        )

    wage_adjustment_pct = _clamp(
        ((growth_ratio - Decimal("0.50")) * Decimal("0.90"))
        + ((opportunity_score - Decimal("1.00")) * Decimal("0.80"))
        + ((productivity_modifier - Decimal("1.00")) * Decimal("0.65"))
        + ((confidence - Decimal("50")) * Decimal("0.012"))
        - (max(unemployment - Decimal("5"), Decimal("0")) * Decimal("0.06"))
        - (max(inflation - Decimal("3"), Decimal("0")) * Decimal("0.04"))
        - (max(interest - Decimal("4"), Decimal("0")) * Decimal("0.025"))
        - ((max(oil - Decimal("100"), Decimal("0")) / Decimal("25")) * _d(behavior["oil_wage_drag"])),
        Decimal("-0.40"),
        Decimal("0.50"),
    )
    wage_adjustment_pct = _clamp(
        wage_adjustment_pct
        + (active_job_wage_drift_modifier * Decimal("100") * Decimal("0.35")),
        Decimal("-0.40"),
        Decimal("0.50"),
    )

    return {
        "player_id": str(player.id),
        "day": int(day),
        "current_job_code": job_code,
        "employment_status": status,
        "opportunity_score": float(_q4(opportunity_score)),
        "layoff_risk_pct": float(_pct(layoff_risk_pct)),
        "promotion_chance_pct": float(_pct(promotion_chance_pct)),
        "wage_adjustment_pct": float(_pct(wage_adjustment_pct)),
        "productivity_modifier": float(_q4(productivity_modifier)),
        "region": region,
        "region_opportunity_modifier": float(_q4(region_opportunity)),
        "commute_modifier": float(_q4(commute_modifier)),
        "macro_day_used": int(getattr(macro, "day", day) or day),
        "job_market_day_used": int(daily_job_market.get("day", day)),
        "active_job_pressure": float(active_job_pressure),
        "active_job_direction": active_job_direction,
        "active_job_opportunity_modifier": float(active_job_opportunity_modifier),
        "active_job_wage_drift_modifier": float(active_job_wage_drift_modifier),
        "active_job_layoff_risk_modifier": float(active_job_layoff_risk_modifier),
    }


def evaluate_daily_employment_event(db: Session, player_id: str | UUID, day: int) -> dict[str, Any]:
    """Evaluate layoff/promotion/wage event for a player/day (idempotent)."""
    if day <= 0:
        raise JobMarketValidationError("day must be greater than 0.")

    player = _resolve_player(db, player_id)
    state, _ = _bootstrap_or_clone_state_for_day(db, player, day)

    if bool(getattr(state, "employment_evaluated_flag", False)):
        event = getattr(state, "last_employment_event", None) or "none"
        metrics = compute_job_market_pressure(db, player.id, day)
        payload = _serialize_event_result(
            player,
            day,
            state,
            employment_event=event,
            monthly_pay_before=_money(_d(state.monthly_pay_xgp)),
            monthly_pay_after=_money(_d(state.monthly_pay_xgp)),
            already_processed=True,
        )
        payload.update(
            {
                "active_job_pressure": float(_q4(_d(metrics.get("active_job_pressure", 0)))),
                "active_job_direction": str(metrics.get("active_job_direction", "neutral")),
                "active_job_opportunity_modifier": float(
                    _q4(_d(metrics.get("active_job_opportunity_modifier", 0)))
                ),
                "active_job_wage_drift_modifier": float(
                    _q4(_d(metrics.get("active_job_wage_drift_modifier", 0)))
                ),
                "active_job_layoff_risk_modifier": float(
                    _q4(_d(metrics.get("active_job_layoff_risk_modifier", 0)))
                ),
            }
        )
        return payload

    metrics = compute_job_market_pressure(db, player.id, day)
    layoff_risk_pct = _d(metrics["layoff_risk_pct"])
    promotion_chance_pct = _d(metrics["promotion_chance_pct"])
    wage_adjustment_pct = _d(metrics["wage_adjustment_pct"])
    productivity_modifier = _d(metrics["productivity_modifier"])
    opportunity_score = _d(metrics["opportunity_score"])

    monthly_pay_before = _money(_d(state.monthly_pay_xgp))
    monthly_pay_after = monthly_pay_before
    employment_event = "none"
    layoff_happened = False

    job_code = normalize_main_job_key(state.current_job_code or "", allow_aliases=True) or None
    status = _normalize_status(state, bool(job_code))
    job_meta = _job_meta(db, job_code)
    behavior = _job_behavior(job_code)

    if status == "employed" and job_code and bool(state.employed_flag):
        layoff_roll = _deterministic_roll(str(player.id), day, f"layoff:{job_code}")
        if layoff_roll * Decimal("100") < layoff_risk_pct:
            layoff_happened = True
            employment_event = "layoff"
            status = "laid_off"
            state.employed_flag = False
            monthly_pay_after = Decimal("0.00")
            player.main_job = None
        else:
            skill_level = int(state.skill_level or player.skill_level or 1)
            promotion_threshold = max(int(job_meta["promotion_threshold"] or 100), 1)
            promotion_gate = int(behavior["promotion_gate"])
            promotion_eligible = (
                skill_level >= promotion_gate
                and Decimal(skill_level * 10) >= (Decimal(promotion_threshold) * Decimal("0.80"))
                and productivity_modifier >= Decimal("0.95")
            )
            state.promotion_eligible_flag = bool(promotion_eligible)

            if promotion_eligible:
                promotion_roll = _deterministic_roll(str(player.id), day, f"promotion:{job_code}")
                if promotion_roll * Decimal("100") < promotion_chance_pct:
                    employment_event = "promotion"
                    growth_ratio = _d(job_meta["growth_ratio"])
                    promotion_raise_pct = _clamp(
                        Decimal("1.00")
                        + (growth_ratio * Decimal("0.80"))
                        + (max(opportunity_score - Decimal("1.0"), Decimal("0")) * Decimal("2.00"))
                        + (max(productivity_modifier - Decimal("1.0"), Decimal("0")) * Decimal("3.00")),
                        Decimal("0.80"),
                        Decimal("2.80"),
                    )
                    monthly_pay_after = _money(monthly_pay_after * (Decimal("1.0") + (promotion_raise_pct / Decimal("100"))))
                    state.promotion_count = int(getattr(state, "promotion_count", 0) or 0) + 1
                    state.last_raise_pct = _pct(promotion_raise_pct)

            # Wage stickiness: small bounded drift, never wild swings.
            monthly_pay_after = _money(
                monthly_pay_after * (Decimal("1.0") + (_pct(wage_adjustment_pct) / Decimal("100")))
            )
            floor = _money(_d(job_meta["base_monthly_pay_xgp"]) * Decimal("0.65"))
            if floor > Decimal("0.00"):
                monthly_pay_after = max(monthly_pay_after, floor)
            state.employed_flag = True
            player.main_job = job_code
    else:
        status = "seeking" if status != "laid_off" else status
        monthly_pay_after = Decimal("0.00")
        state.employed_flag = False
        state.promotion_eligible_flag = False

    if layoff_happened:
        state.promotion_eligible_flag = False
        state.last_raise_pct = Decimal("0.00")
        state.wage_adjustment_pct = Decimal("0.00")
    else:
        state.wage_adjustment_pct = _pct(wage_adjustment_pct if state.employed_flag else Decimal("0.00"))
        if employment_event != "promotion":
            state.last_raise_pct = _pct(state.wage_adjustment_pct if state.employed_flag else Decimal("0.00"))

    state.job_status = status
    state.layoff_event_flag = layoff_happened
    state.last_employment_event = employment_event
    state.monthly_pay_xgp = _money(monthly_pay_after)
    state.layoff_risk_pct = _pct(layoff_risk_pct if state.employed_flag else Decimal("0.00"))
    state.productivity_modifier = _q4(productivity_modifier)
    state.opportunity_score = _q4(opportunity_score)
    state.promotion_chance_pct = _pct(promotion_chance_pct if state.employed_flag else Decimal("0.00"))
    state.employment_evaluated_flag = True
    state.skill_level = max(int(state.skill_level or player.skill_level or 1), 1)

    payload = _serialize_event_result(
        player,
        day,
        state,
        employment_event=employment_event,
        monthly_pay_before=monthly_pay_before,
        monthly_pay_after=state.monthly_pay_xgp,
        already_processed=False,
    )
    payload.update(
        {
            "active_job_pressure": float(_q4(_d(metrics.get("active_job_pressure", 0)))),
            "active_job_direction": str(metrics.get("active_job_direction", "neutral")),
            "active_job_opportunity_modifier": float(
                _q4(_d(metrics.get("active_job_opportunity_modifier", 0)))
            ),
            "active_job_wage_drift_modifier": float(
                _q4(_d(metrics.get("active_job_wage_drift_modifier", 0)))
            ),
            "active_job_layoff_risk_modifier": float(
                _q4(_d(metrics.get("active_job_layoff_risk_modifier", 0)))
            ),
        }
    )
    return payload


def apply_employment_progression(
    db: Session,
    player_id: str | UUID,
    day: int,
    *,
    commit: bool = False,
) -> dict[str, Any]:
    """Run daily employment event + bounded skill progression."""
    player = _resolve_player(db, player_id)
    result = evaluate_daily_employment_event(db, player.id, day)

    state = _employment_state_for_exact_day(db, player.id, day)
    if state is None:
        raise JobMarketNotFoundError("Employment state for day could not be resolved.")

    if bool(state.employed_flag) and not bool(getattr(state, "layoff_event_flag", False)):
        job_code = normalize_main_job_key(state.current_job_code or "", allow_aliases=True) or None
        job_meta = _job_meta(db, job_code)
        growth_ratio = _d(job_meta["growth_ratio"])
        skill_roll = _deterministic_roll(str(player.id), day, f"skill:{job_code or 'none'}")
        learning_chance = _clamp(
            Decimal("0.05")
            + (max(_d(state.productivity_modifier) - Decimal("1.0"), Decimal("0")) * Decimal("0.35"))
            + (max(_d(state.opportunity_score) - Decimal("1.0"), Decimal("0")) * Decimal("0.25"))
            + (growth_ratio * Decimal("0.10")),
            Decimal("0.05"),
            Decimal("0.30"),
        )
        if skill_roll < learning_chance:
            state.skill_level = int(state.skill_level or 1) + 1
            player.skill_level = max(int(player.skill_level or 1), int(state.skill_level))
            if result.get("employment_event") == "none":
                state.last_employment_event = "skill_up"
                result["employment_event"] = "skill_up"

    # Sync top-level player skill and flush the per-day row updates.
    player.skill_level = max(int(player.skill_level or 1), int(state.skill_level or 1))
    db.flush()
    if commit:
        db.commit()

    result["skill_level"] = int(state.skill_level or 1)
    result["employment_status"] = _normalize_status(state, bool(state.current_job_code))
    result["monthly_pay_after"] = float(_money(_d(state.monthly_pay_xgp)))
    result["monthly_pay_xgp_after_event"] = float(_money(_d(state.monthly_pay_xgp)))
    result["layoff_risk_pct"] = float(_pct(_d(state.layoff_risk_pct)))
    result["promotion_chance_pct"] = float(_pct(_d(state.promotion_chance_pct)))
    result["wage_adjustment_pct"] = float(_pct(_d(state.wage_adjustment_pct)))
    result["opportunity_score"] = float(_q4(_d(state.opportunity_score)))
    result["productivity_modifier"] = float(_q4(_d(state.productivity_modifier)))
    result["promotion_count"] = int(getattr(state, "promotion_count", 0) or 0)
    result["last_raise_pct"] = float(_pct(_d(getattr(state, "last_raise_pct", 0))))
    return result


def get_player_job_summary(db: Session, player_id: str | UUID) -> dict[str, Any]:
    """Return latest employment snapshot and a concise job summary."""
    player = _resolve_player(db, player_id)
    latest = _latest_employment_state(db, player.id)
    if latest is None:
        return {
            "player_id": str(player.id),
            "current_job_summary": None,
            "current_status": "seeking",
            "current_monthly_pay_xgp": 0.0,
            "skill_level": int(player.skill_level or 1),
            "promotion_count": 0,
            "last_employment_event": None,
            "current_job_code": normalize_main_job_key(player.main_job, allow_aliases=True),
        }

    current_job_code = (
        normalize_main_job_key(latest.current_job_code, allow_aliases=True)
        or normalize_main_job_key(player.main_job, allow_aliases=True)
    )
    status = _normalize_status(latest, bool(current_job_code))
    meta = _job_meta(db, current_job_code)
    return {
        "player_id": str(player.id),
        "current_job_code": current_job_code,
        "current_job_summary": {
            "job_code": current_job_code,
            "title": meta["title"],
            "status": status,
            "monthly_pay_xgp": float(_money(_d(latest.monthly_pay_xgp))),
            "skill_level": int(latest.skill_level or 1),
            "layoff_risk_pct": float(_pct(_d(latest.layoff_risk_pct))),
            "promotion_chance_pct": float(_pct(_d(getattr(latest, "promotion_chance_pct", 0)))),
            "wage_adjustment_pct": float(_pct(_d(getattr(latest, "wage_adjustment_pct", 0)))),
            "opportunity_score": float(_q4(_d(getattr(latest, "opportunity_score", 1.0)))),
            "productivity_modifier": float(_q4(_d(getattr(latest, "productivity_modifier", 1.0)))),
        },
        "current_status": status,
        "current_monthly_pay_xgp": float(_money(_d(latest.monthly_pay_xgp))),
        "skill_level": int(latest.skill_level or 1),
        "promotion_count": int(getattr(latest, "promotion_count", 0) or 0),
        "last_employment_event": getattr(latest, "last_employment_event", None),
    }
