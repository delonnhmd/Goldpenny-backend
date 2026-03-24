"""Save/load onboarding service for creating playable starter players."""

from __future__ import annotations

import json
import logging
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.job_definition import JOB_CATALOG
from app.models.job_definition_db import JobDefinition as JobDefinitionDB
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.user import User
from app.services.housing_region_service import assign_player_housing
from app.services.stock_trading_service import StockTradingError, StockTradingService

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

SUPPORTED_GENDERS = {"male", "female"}
SUPPORTED_REGIONS = {"suburban", "downtown"}
SUPPORTED_STARTER_JOBS = {
    "auto_mechanic",
    "aircraft_mechanic",
    "banker",
    "chef",
    "retail_worker",
    "delivery_driver",
}

STARTER_BASELINES: dict[str, dict[str, Decimal | int]] = {
    "suburban": {
        "cash_xgp": Decimal("850.00"),
        "bank_savings_xgp": Decimal("125.00"),
        "debt_xgp": Decimal("250.00"),
        "credit_score": 640,
        "health": 88,
        "stress": 24,
        "available_hours": 16,
        "skill_level": 1,
        "reputation": 0,
    },
    "downtown": {
        "cash_xgp": Decimal("780.00"),
        "bank_savings_xgp": Decimal("110.00"),
        "debt_xgp": Decimal("360.00"),
        "credit_score": 635,
        "health": 86,
        "stress": 28,
        "available_hours": 16,
        "skill_level": 1,
        "reputation": 0,
    },
}

_stock_service = StockTradingService()
logger = logging.getLogger(__name__)


class OnboardingError(Exception):
    """Base exception for onboarding and save/load flow."""


class OnboardingNotFoundError(OnboardingError):
    """Raised when the target player/user does not exist."""


class OnboardingValidationError(OnboardingError):
    """Raised for invalid onboarding input."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _normalize_display_name(display_name: str) -> str:
    cleaned = (display_name or "").strip()
    if not cleaned:
        raise OnboardingValidationError("display_name is required.")
    if len(cleaned) > 80:
        raise OnboardingValidationError("display_name must be 80 characters or fewer.")
    return cleaned


def _normalize_gender(gender: str) -> str:
    normalized = (gender or "").strip().lower()
    if normalized not in SUPPORTED_GENDERS:
        raise OnboardingValidationError("Unsupported gender. Use male or female.")
    return normalized


def _normalize_region(region: str) -> str:
    normalized = (region or "").strip().lower()
    if normalized not in SUPPORTED_REGIONS:
        raise OnboardingValidationError("Unsupported region. Use suburban or downtown.")
    return normalized


def _normalize_starter_job(starter_job_code: str) -> str:
    normalized = (starter_job_code or "").strip().lower()
    if normalized not in SUPPORTED_STARTER_JOBS:
        raise OnboardingValidationError(
            f"Unsupported starter_job_code. Use one of: {sorted(SUPPORTED_STARTER_JOBS)}"
        )
    return normalized


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise OnboardingNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise OnboardingNotFoundError("Player not found.")
    return player


def _resolve_user(db: Session, user_id: str | UUID) -> User:
    try:
        uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    except ValueError as exc:
        raise OnboardingNotFoundError("User not found.") from exc

    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise OnboardingNotFoundError("User not found.")
    return user


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    return normalized


def _build_generated_email(db: Session, display_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", display_name.lower())[:24] or "player"
    for _ in range(12):
        candidate = f"onboard+{slug}-{uuid.uuid4().hex[:10]}@goldpenny.local"
        exists = db.query(User).filter(User.email == candidate).first()
        if exists is None:
            return candidate
    raise OnboardingError("Could not generate a unique onboarding email.")


def _generate_placeholder_hash() -> str:
    # Onboarding flow creates game-ready profiles without interactive auth setup.
    # The auth system can later rotate this to a real credential hash.
    return f"onboarding-placeholder::{uuid.uuid4().hex}"


def _starter_monthly_pay_xgp(db: Session, starter_job_code: str) -> Decimal:
    normalized = _normalize_starter_job(starter_job_code)

    db_row = (
        db.query(JobDefinitionDB)
        .filter(JobDefinitionDB.job_code == normalized)
        .first()
    )
    if db_row is not None:
        return _money(_d(db_row.base_monthly_pay_xgp))

    static = JOB_CATALOG.get(normalized)
    if static is not None:
        return _money(_d(static.monthly_salary))

    # Fallback should practically never happen after validation, but remains
    # to keep startup behavior deterministic if catalogs change.
    return Decimal("2600.00")


def _serialize_housing_state(state: PlayerHousingState | None) -> dict | None:
    if state is None:
        return None
    return {
        "id": str(state.id),
        "region": str(state.region),
        "housing_type": str(state.housing_type),
        "daily_housing_cost_xgp": float(_money(_d(state.daily_housing_cost_xgp))),
        "commute_modifier": float(_q4(_d(state.commute_modifier))),
        "stress_modifier": int(state.stress_modifier or 0),
        "opportunity_modifier": float(_q4(_d(state.opportunity_modifier))),
        "active_flag": bool(state.active_flag),
        "created_at": state.created_at.isoformat() if state.created_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_employment_state(state: PlayerEmploymentState | None) -> dict | None:
    if state is None:
        return None
    return {
        "id": str(state.id),
        "day": int(state.day),
        "current_job_code": state.current_job_code,
        "monthly_pay_xgp": float(_money(_d(state.monthly_pay_xgp))),
        "employed_flag": bool(state.employed_flag),
        "job_status": str(state.job_status or "seeking"),
        "skill_level": int(state.skill_level or 1),
        "layoff_risk_pct": float(_q4(_d(state.layoff_risk_pct))),
        "productivity_modifier": float(_q4(_d(state.productivity_modifier))),
        "opportunity_score": float(_q4(_d(state.opportunity_score))),
        "promotion_count": int(state.promotion_count or 0),
        "last_employment_event": state.last_employment_event,
        "created_at": state.created_at.isoformat() if state.created_at else None,
    }


def _parse_json(text_value: str | None) -> dict | list | None:
    if not text_value:
        return None
    try:
        return json.loads(text_value)
    except Exception:
        return None


def _serialize_settlement(settlement: DailySettlementLog | None) -> dict | None:
    if settlement is None:
        return None
    return {
        "day_number": int(settlement.day_number),
        "income_xgp": float(_money(_d(settlement.income_xgp))),
        "expenses_xgp": float(_money(_d(settlement.expenses_xgp))),
        "debt_paid_xgp": float(_money(_d(settlement.debt_paid_xgp))),
        "ending_cash_xgp": float(_money(_d(settlement.ending_cash_xgp))),
        "health_change": int(settlement.health_change or 0),
        "stress_change": int(settlement.stress_change or 0),
        "summary_json": _parse_json(settlement.summary_json) or {},
        "created_at": settlement.created_at.isoformat() if settlement.created_at else None,
    }


def _serialize_brief(brief: DailyBriefLog | None) -> dict | None:
    if brief is None:
        return None
    return {
        "id": str(brief.id),
        "day": int(brief.day),
        "headline": str(brief.headline),
        "summary": str(brief.summary),
        "macro_tags_json": _parse_json(brief.macro_tags_json) or [],
        "player_impact_json": _parse_json(brief.player_impact_json) or {},
        "action_hints_json": _parse_json(brief.action_hints_json) or [],
        "created_at": brief.created_at.isoformat() if brief.created_at else None,
    }


def _placeholder_portfolio_summary(player: Player) -> dict:
    return {
        "player_id": str(player.id),
        "cash_xgp": float(_money(_d(player.cash_xgp))),
        "total_market_value": 0.0,
        "total_cost_basis": 0.0,
        "total_unrealized_pnl": 0.0,
        "holdings": [],
    }


def build_minimal_playable_player_summary(player: Player, *, load_ready: bool = False) -> dict[str, Any]:
    """Build a minimal load payload when optional onboarding state fetch fails.

    This avoids hard failures in environments where optional onboarding tables
    or seed data are missing, while still returning a valid player id and
    baseline gameplay fields.
    """
    return {
        "player_id": str(player.id),
        "display_name": player.display_name,
        "gender": player.gender,
        "region": str(player.region or "suburban"),
        "cash_xgp": float(_money(_d(player.cash_xgp))),
        "bank_savings_xgp": float(_money(_d(player.bank_savings_xgp))),
        "debt_xgp": float(_money(_d(player.debt_xgp))),
        "credit_score": int(player.credit_score or 650),
        "net_worth_xgp": float(_money(_d(player.net_worth_xgp))),
        "health": int(player.health or 100),
        "stress": int(player.stress or 0),
        "available_hours": int(player.available_hours or 0),
        "active_housing_summary": None,
        "active_employment_summary": None,
        "latest_settlement_summary": None,
        "latest_daily_brief": None,
        "latest_portfolio_summary": _placeholder_portfolio_summary(player),
        "load_ready": bool(load_ready),
    }


def create_new_player_profile(
    db: Session,
    *,
    display_name: str,
    gender: str,
    region: str,
    starter_job_code: str,
    user_id: str | UUID | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Create a user+player profile row pair with starter financial baselines.

    This function does not commit. Caller owns transaction boundaries.
    """
    logger.info(
        "player_onboarding.create_new_player_profile validating payload.",
        extra={
            "display_name": display_name,
            "gender": gender,
            "region": region,
            "starter_job_code": starter_job_code,
            "has_user_id": user_id is not None,
            "has_email": bool(email),
        },
    )
    clean_name = _normalize_display_name(display_name)
    clean_gender = _normalize_gender(gender)
    clean_region = _normalize_region(region)
    clean_job = _normalize_starter_job(starter_job_code)
    logger.info(
        "player_onboarding.create_new_player_profile payload validation succeeded.",
        extra={
            "display_name": clean_name,
            "gender": clean_gender,
            "region": clean_region,
            "starter_job_code": clean_job,
        },
    )

    if user_id is not None:
        user = _resolve_user(db, user_id)
        if user.player is not None:
            raise OnboardingValidationError("Selected user already has a player profile.")
    else:
        normalized_email = _normalize_email(email)
        if normalized_email is None:
            normalized_email = _build_generated_email(db, clean_name)
        else:
            existing = db.query(User).filter(User.email == normalized_email).first()
            if existing is not None:
                raise OnboardingValidationError("Email already exists.")

        user = User(
            email=normalized_email,
            hashed_password=_generate_placeholder_hash(),
        )
        db.add(user)
        logger.info(
            "player_onboarding.create_new_player_profile inserting user row.",
            extra={
                "email": normalized_email,
            },
        )
        db.flush()
        logger.info(
            "player_onboarding.create_new_player_profile user insert succeeded.",
            extra={
                "user_id": str(user.id),
            },
        )

    starter = STARTER_BASELINES[clean_region]
    cash_xgp = _money(_d(starter["cash_xgp"]))
    bank_savings_xgp = _money(_d(starter["bank_savings_xgp"]))
    debt_xgp = _money(_d(starter["debt_xgp"]))
    net_worth_xgp = _money(cash_xgp + bank_savings_xgp - debt_xgp)

    player = Player(
        user_id=user.id,
        display_name=clean_name,
        gender=clean_gender,
        region=clean_region,
        cash_xgp=cash_xgp,
        bank_savings_xgp=bank_savings_xgp,
        debt_xgp=debt_xgp,
        credit_score=int(starter["credit_score"]),
        net_worth_xgp=net_worth_xgp,
        health=int(starter["health"]),
        stress=int(starter["stress"]),
        available_hours=int(starter["available_hours"]),
        skill_level=int(starter["skill_level"]),
        reputation=int(starter["reputation"]),
        main_job=clean_job,
        has_active_housing=False,
        housing_region_id=None,
    )
    db.add(player)
    logger.info(
        "player_onboarding.create_new_player_profile inserting player row.",
        extra={
            "user_id": str(user.id),
            "display_name": clean_name,
            "region": clean_region,
            "starter_job_code": clean_job,
        },
    )
    db.flush()
    logger.info(
        "player_onboarding.create_new_player_profile player insert succeeded.",
        extra={
            "player_id": str(player.id),
        },
    )

    return {
        "user": user,
        "player": player,
    }


def initialize_starter_player_state(
    db: Session,
    *,
    player_id: str | UUID,
    region: str,
    starter_job_code: str,
) -> dict[str, Any]:
    """Initialize housing/employment/day-1 context for immediate gameplay.

    This function does not commit. Caller owns transaction boundaries.
    """
    player = _resolve_player(db, player_id)
    clean_region = _normalize_region(region)
    clean_job = _normalize_starter_job(starter_job_code)
    logger.info(
        "player_onboarding.initialize_starter_player_state start.",
        extra={
            "player_id": str(player.id),
            "region": clean_region,
            "starter_job_code": clean_job,
        },
    )

    housing_payload = assign_player_housing(
        db=db,
        player_id=player.id,
        region=clean_region,
        housing_type="starter_rent",
        commit=False,
    )
    logger.info(
        "player_onboarding.initialize_starter_player_state housing assignment succeeded.",
        extra={
            "player_id": str(player.id),
            "region": clean_region,
        },
    )

    existing_employment_count = (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player.id)
        .count()
    )
    if existing_employment_count > 0:
        raise OnboardingValidationError("Player already has employment history; starter init requires a fresh player.")

    starter_monthly_pay_xgp = _starter_monthly_pay_xgp(db, clean_job)

    employment_state = PlayerEmploymentState(
        player_id=player.id,
        day=1,
        current_job_code=clean_job,
        skill_level=max(int(player.skill_level or 1), 1),
        monthly_pay_xgp=starter_monthly_pay_xgp,
        employed_flag=True,
        layoff_risk_pct=Decimal("0.00"),
        productivity_modifier=Decimal("1.0000"),
        job_status="employed",
        promotion_eligible_flag=False,
        promotion_count=0,
        last_raise_pct=Decimal("0.00"),
        last_employment_event="onboarding_start",
        opportunity_score=Decimal("1.0000"),
        layoff_event_flag=False,
        promotion_chance_pct=Decimal("0.00"),
        wage_adjustment_pct=Decimal("0.00"),
        employment_evaluated_flag=False,
    )
    db.add(employment_state)

    day_one_state = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number == 1,
        )
        .first()
    )

    if day_one_state is None:
        cash_now = _money(_d(player.cash_xgp))
        starter_hours = int(player.available_hours or 16)
        day_one_state = PlayerDailyState(
            player_id=player.id,
            day_number=1,
            hours_available_start=starter_hours,
            hours_available_end=starter_hours,
            worked_main_job=False,
            worked_hours=0,
            gross_income_xgp=Decimal("0.00"),
            did_settlement=False,
            stress_start=int(player.stress or 0),
            stress_end=int(player.stress or 0),
            health_start=int(player.health or 100),
            health_end=int(player.health or 100),
            cash_start=cash_now,
            cash_end=cash_now,
            housing_region_id=clean_region,
            notes="starter_context_initialized",
        )
        db.add(day_one_state)

    player.main_job = clean_job
    player.skill_level = max(int(player.skill_level or 1), 1)
    player.region = clean_region
    player.housing_region_id = clean_region
    player.has_active_housing = True

    db.flush()
    db.refresh(employment_state)
    logger.info(
        "player_onboarding.initialize_starter_player_state completed.",
        extra={
            "player_id": str(player.id),
        },
    )

    return {
        "player_id": str(player.id),
        "housing_state": housing_payload,
        "employment_state": _serialize_employment_state(employment_state),
        "starter_day_initialized": True,
    }


def get_playable_player_summary(db: Session, player_id: str | UUID) -> dict[str, Any]:
    """Return a load-ready summary for UI/app startup and resume flow."""
    player = _resolve_player(db, player_id)

    active_housing = (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player.id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc())
        .first()
    )
    latest_employment = (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player.id)
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )
    latest_settlement = (
        db.query(DailySettlementLog)
        .filter(DailySettlementLog.player_id == player.id)
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )
    latest_brief = (
        db.query(DailyBriefLog)
        .filter(DailyBriefLog.player_id == player.id)
        .order_by(DailyBriefLog.day.desc(), DailyBriefLog.created_at.desc())
        .first()
    )

    try:
        portfolio = _stock_service.get_player_portfolio(db, player.id)
    except StockTradingError:
        portfolio = _placeholder_portfolio_summary(player)
    except Exception:
        portfolio = _placeholder_portfolio_summary(player)

    return {
        "player_id": str(player.id),
        "display_name": player.display_name,
        "gender": player.gender,
        "region": player.region,
        "cash_xgp": float(_money(_d(player.cash_xgp))),
        "bank_savings_xgp": float(_money(_d(player.bank_savings_xgp))),
        "debt_xgp": float(_money(_d(player.debt_xgp))),
        "credit_score": int(player.credit_score or 650),
        "net_worth_xgp": float(_money(_d(player.net_worth_xgp))),
        "health": int(player.health or 100),
        "stress": int(player.stress or 0),
        "available_hours": int(player.available_hours or 0),
        "active_housing_summary": _serialize_housing_state(active_housing),
        "active_employment_summary": _serialize_employment_state(latest_employment),
        "latest_settlement_summary": _serialize_settlement(latest_settlement),
        "latest_daily_brief": _serialize_brief(latest_brief),
        "latest_portfolio_summary": portfolio,
    }


def load_existing_player_state(db: Session, player_id: str | UUID) -> dict[str, Any]:
    """Return current saved state for app resume flow."""
    payload = get_playable_player_summary(db, player_id)
    payload["load_ready"] = True
    return payload
