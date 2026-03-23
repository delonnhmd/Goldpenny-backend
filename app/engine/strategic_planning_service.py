"""Step 28 strategic choice planning and mid-term decision support service.

This service composes existing simulation state into 3-7 day planning guidance.
It is read-only by design and does not mutate core economy systems.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.economy_presentation_service import (
    build_business_margin_summary,
    build_commute_pressure_summary,
    build_market_overview,
    build_price_trend_summary,
)
from app.engine.population_pressure_service import (
    build_local_competition_state,
    build_region_heat_summary,
)
from app.engine.housing_region_config import REGION_CONFIG
from app.engine.personal_shock_service import (
    build_personal_shock_summary,
    build_player_resilience_summary,
)
from app.engine.consumer_borrowing_service import (
    build_borrowing_pressure_summary,
    build_borrowing_risk_summary,
)
from app.engine.financial_survival_service import build_financial_survival_summary
from app.engine.player_strategy_service import classify_player_strategy
from app.models.business_daily_log import BusinessDailyLog
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.housing_daily_log import HousingDailyLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_housing_state import PlayerHousingState

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
MONEY_Q = Decimal("0.01")


class StrategicPlanningError(Exception):
    """Base exception for strategic planning composition."""


class StrategicPlanningNotFoundError(StrategicPlanningError):
    """Raised when player or required state cannot be found."""


class StrategicPlanningValidationError(StrategicPlanningError):
    """Raised when invalid dates/inputs are supplied."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise StrategicPlanningValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise StrategicPlanningValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise StrategicPlanningNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise StrategicPlanningNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date

    latest_settlement = db.query(func.max(DailySettlementLog.day_number)).scalar()
    latest_daily = db.query(func.max(PlayerDailyState.day_number)).scalar()
    latest_distress = db.query(func.max(FinancialDistressLog.day)).scalar()
    latest_housing = db.query(func.max(HousingDailyLog.day)).scalar()

    day = max(
        int(latest_settlement or 0),
        int(latest_daily or 0),
        int(latest_distress or 0),
        int(latest_housing or 0),
        1,
    )
    return day, _day_to_date(day)


def _latest_settlement(db: Session, player_id: UUID, day: int) -> DailySettlementLog | None:
    return (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player_id,
            DailySettlementLog.day_number <= int(day),
        )
        .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
        .first()
    )


def _latest_daily_state(db: Session, player_id: UUID, day: int) -> PlayerDailyState | None:
    return (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player_id,
            PlayerDailyState.day_number <= int(day),
        )
        .order_by(PlayerDailyState.day_number.desc(), PlayerDailyState.created_at.desc())
        .first()
    )


def _latest_distress_row(db: Session, player_id: UUID, day: int) -> FinancialDistressLog | None:
    return (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player_id,
            FinancialDistressLog.day <= int(day),
        )
        .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
        .first()
    )


def _latest_housing_log(db: Session, player_id: UUID, day: int) -> HousingDailyLog | None:
    return (
        db.query(HousingDailyLog)
        .filter(
            HousingDailyLog.player_id == player_id,
            HousingDailyLog.day <= int(day),
        )
        .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
        .first()
    )


def _active_housing_state(db: Session, player_id: UUID) -> PlayerHousingState | None:
    return (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player_id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc(), PlayerHousingState.created_at.desc())
        .first()
    )


def _latest_business_log(db: Session, player_id: UUID, business_type: str, day: int) -> BusinessDailyLog | None:
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player_id,
            BusinessDailyLog.business_type == business_type,
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .first()
    )


def _active_businesses(db: Session, player_id: UUID) -> list[PlayerBusiness]:
    return (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player_id,
            PlayerBusiness.is_active.is_(True),
        )
        .order_by(PlayerBusiness.business_id.asc(), PlayerBusiness.created_at.asc())
        .all()
    )


def _recent_settlements(db: Session, player_id: UUID, day: int, window: int = 7) -> list[DailySettlementLog]:
    start_day = max(1, int(day) - max(1, int(window)) + 1)
    return (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player_id,
            DailySettlementLog.day_number >= start_day,
            DailySettlementLog.day_number <= int(day),
        )
        .order_by(DailySettlementLog.day_number.asc(), DailySettlementLog.created_at.asc())
        .all()
    )


def _recent_career_logs(db: Session, player_id: UUID, day: int, window: int = 7) -> list[CareerProgressLog]:
    start_day = max(1, int(day) - max(1, int(window)) + 1)
    return (
        db.query(CareerProgressLog)
        .filter(
            CareerProgressLog.player_id == player_id,
            CareerProgressLog.day_number >= start_day,
            CareerProgressLog.day_number <= int(day),
        )
        .order_by(CareerProgressLog.day_number.asc(), CareerProgressLog.created_at.asc())
        .all()
    )


def _parse_effective_commute_hours(commute_payload: dict, fallback_hours: Decimal) -> Decimal:
    debug_meta = commute_payload.get("debug_meta") if isinstance(commute_payload, dict) else None
    if isinstance(debug_meta, dict):
        value = _d(debug_meta.get("effective_commute_hours"))
        if value > Decimal("0"):
            return _q4(value)
    return _q4(_clamp(fallback_hours, Decimal("0.20"), Decimal("4.50")))


def _confidence_from_relevance(score_0_to_1: Decimal) -> str:
    score = _clamp(score_0_to_1, Decimal("0.00"), Decimal("1.00"))
    if score >= Decimal("0.72"):
        return "high"
    if score >= Decimal("0.48"):
        return "moderate"
    return "low"


def _score_to_float(score: Decimal) -> float:
    return float(_q4(score))


def _safe_avg(values: list[Decimal], fallback: Decimal) -> Decimal:
    if not values:
        return fallback
    return _q4(sum(values, Decimal("0")) / Decimal(str(len(values))))


def _build_state_context(db: Session, player: Player, day: int, as_of_date: date) -> dict:
    settlement = _latest_settlement(db, player.id, day)
    daily_state = _latest_daily_state(db, player.id, day)
    distress = _latest_distress_row(db, player.id, day)
    housing_log = _latest_housing_log(db, player.id, day)
    housing_state = _active_housing_state(db, player.id)
    businesses = _active_businesses(db, player.id)
    fruit_log = _latest_business_log(db, player.id, "fruit_shop", day)
    truck_log = _latest_business_log(db, player.id, "food_truck", day)
    settlements = _recent_settlements(db, player.id, day, window=7)
    career_logs = _recent_career_logs(db, player.id, day, window=7)

    commute_payload = build_commute_pressure_summary(db=db, player_id=player.id, as_of_date=as_of_date)
    market_payload = build_market_overview(db=db, player_id=player.id, as_of_date=as_of_date)
    business_margins_payload = build_business_margin_summary(db=db, player_id=player.id, as_of_date=as_of_date)
    price_trends_payload = build_price_trend_summary(db=db, player_id=player.id, as_of_date=as_of_date)
    strategy_payload = classify_player_strategy(db=db, player_id=player.id, as_of_date=as_of_date, lookback_days=7)
    try:
        population_competition_payload = build_local_competition_state(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
        )
    except Exception:
        population_competition_payload = {}
    try:
        population_region_heat_payload = build_region_heat_summary(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
        )
    except Exception:
        population_region_heat_payload = {}
    try:
        personal_shock_summary_payload = build_personal_shock_summary(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
            day_number=day,
        )
    except Exception:
        personal_shock_summary_payload = {}
    try:
        resilience_summary_payload = build_player_resilience_summary(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
            day_number=day,
        )
    except Exception:
        resilience_summary_payload = {}
    try:
        financial_survival_summary_payload = build_financial_survival_summary(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
            day_number=day,
        )
    except Exception:
        financial_survival_summary_payload = {}
    try:
        borrowing_pressure_summary_payload = build_borrowing_pressure_summary(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
            day_number=day,
        )
    except Exception:
        borrowing_pressure_summary_payload = {}
    try:
        borrowing_risk_summary_payload = build_borrowing_risk_summary(
            db=db,
            player_id=player.id,
            as_of_date=as_of_date,
            day_number=day,
        )
    except Exception:
        borrowing_risk_summary_payload = {}

    avg_expenses = _safe_avg(
        [
            _d(getattr(row, "expenses_xgp", 0))
            for row in settlements
            if _d(getattr(row, "expenses_xgp", 0)) > Decimal("0")
        ],
        Decimal("55.0"),
    )
    avg_income = _safe_avg(
        [
            _d(getattr(row, "income_xgp", 0))
            for row in settlements
            if _d(getattr(row, "income_xgp", 0)) > Decimal("0")
        ],
        Decimal("70.0"),
    )

    raw_commute = _d(getattr(housing_log, "commute_hours", 0))
    if raw_commute <= Decimal("0") and daily_state is not None:
        raw_commute = _d(getattr(daily_state, "commute_hours", 0))
    if raw_commute <= Decimal("0"):
        region_guess = (
            str(getattr(housing_log, "region", "") or getattr(housing_state, "region", "") or player.region or "suburban")
            .strip()
            .lower()
        )
        raw_commute = _d(REGION_CONFIG.get(region_guess, REGION_CONFIG["suburban"]).commute_hours_baseline)

    effective_commute_hours = _parse_effective_commute_hours(commute_payload, raw_commute)

    return {
        "player": player,
        "day": int(day),
        "as_of_date": as_of_date,
        "settlement": settlement,
        "daily_state": daily_state,
        "distress": distress,
        "housing_log": housing_log,
        "housing_state": housing_state,
        "businesses": businesses,
        "fruit_log": fruit_log,
        "truck_log": truck_log,
        "settlements": settlements,
        "career_logs": career_logs,
        "commute_payload": commute_payload,
        "market_payload": market_payload,
        "business_margins_payload": business_margins_payload,
        "price_trends_payload": price_trends_payload,
        "strategy_payload": strategy_payload,
        "population_competition_payload": population_competition_payload,
        "population_region_heat_payload": population_region_heat_payload,
        "personal_shock_summary_payload": personal_shock_summary_payload,
        "resilience_summary_payload": resilience_summary_payload,
        "financial_survival_summary_payload": financial_survival_summary_payload,
        "borrowing_pressure_summary_payload": borrowing_pressure_summary_payload,
        "borrowing_risk_summary_payload": borrowing_risk_summary_payload,
        "avg_expenses": avg_expenses,
        "avg_income": avg_income,
        "effective_commute_hours": effective_commute_hours,
    }


def build_short_horizon_plan_options(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build 3-7 day strategic plan options grounded in current player state."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    ctx = _build_state_context(db, player, day, resolved_date)

    distress_value = _d(getattr(ctx["distress"], "distress_score_after", player.distress_score))
    stress_value = _d(player.stress)
    health_value = _d(player.health)
    cash_value = _d(player.cash_xgp)
    debt_value = _d(player.debt_xgp)
    required_payment = _d(getattr(player, "required_daily_debt_payment_xgp", 0))
    productivity = _d(getattr(player, "productivity_modifier", 1.0))
    commute_hours = _d(ctx["effective_commute_hours"])
    shock_summary_payload = ctx.get("personal_shock_summary_payload") or {}
    resilience_summary_payload = ctx.get("resilience_summary_payload") or {}
    shock_profile = (
        (shock_summary_payload.get("debug_meta") or {}).get("profile")
        if isinstance(shock_summary_payload, dict)
        else {}
    ) or {}
    shock_risk_score = _d(shock_profile.get("shock_risk_score", 0))
    recovery_capacity_score = _d(shock_profile.get("recovery_capacity_score", 55))
    resilience_label = str(
        resilience_summary_payload.get("resilience_label", "stable")
    ).lower()

    avg_expenses = _d(ctx["avg_expenses"])
    avg_income = _d(ctx["avg_income"])
    days_cash_cushion = _clamp(cash_value / max(Decimal("1"), avg_expenses), Decimal("0"), Decimal("30"))
    active_business_count = Decimal(str(len(ctx["businesses"])))

    fruit_profit = _d(getattr(ctx["fruit_log"], "net_profit_xgp", 0))
    truck_profit = _d(getattr(ctx["truck_log"], "net_profit_xgp", 0))
    business_recent_net = fruit_profit + truck_profit

    training_hours = sum((_d(getattr(row, "training_hours", 0)) for row in ctx["career_logs"]), Decimal("0"))

    stabilize_score = _clamp(
        (distress_value / Decimal("100")) * Decimal("0.42")
        + _clamp(required_payment / max(Decimal("1"), avg_income), Decimal("0"), Decimal("1")) * Decimal("0.24")
        + _clamp((Decimal("6") - days_cash_cushion) / Decimal("6"), Decimal("0"), Decimal("1")) * Decimal("0.22")
        + _clamp(debt_value / max(Decimal("200"), cash_value + Decimal("200")), Decimal("0"), Decimal("1"))
        * Decimal("0.12"),
        Decimal("0"),
        Decimal("1"),
    )
    stabilize_score = _clamp(
        stabilize_score
        + _clamp(shock_risk_score / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.10")
        + _clamp((Decimal("60") - recovery_capacity_score) / Decimal("60"), Decimal("0"), Decimal("1")) * Decimal("0.06"),
        Decimal("0"),
        Decimal("1"),
    )
    push_income_score = _clamp(
        _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.32")
        + _clamp((Decimal("100") - stress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.24")
        + _clamp(health_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.19")
        + _clamp((Decimal("5") - days_cash_cushion) / Decimal("5"), Decimal("0"), Decimal("1")) * Decimal("0.25"),
        Decimal("0"),
        Decimal("1"),
    )
    push_income_score = _clamp(
        push_income_score
        - _clamp(shock_risk_score / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.14")
        - (Decimal("0.06") if resilience_label == "fragile" else Decimal("0.03") if resilience_label == "stretched" else Decimal("0.00")),
        Decimal("0"),
        Decimal("1"),
    )
    reduce_stress_score = _clamp(
        _clamp(stress_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.45")
        + _clamp((commute_hours - Decimal("0.9")) / Decimal("2.1"), Decimal("0"), Decimal("1")) * Decimal("0.20")
        + _clamp((Decimal("1.00") - productivity) / Decimal("0.30"), Decimal("0"), Decimal("1")) * Decimal("0.20")
        + _clamp((Decimal("75") - health_value) / Decimal("75"), Decimal("0"), Decimal("1")) * Decimal("0.15"),
        Decimal("0"),
        Decimal("1"),
    )
    reduce_stress_score = _clamp(
        reduce_stress_score
        + _clamp(shock_risk_score / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.10"),
        Decimal("0"),
        Decimal("1"),
    )
    career_score = _clamp(
        _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.26")
        + _clamp((Decimal("90") - stress_value) / Decimal("90"), Decimal("0"), Decimal("1")) * Decimal("0.24")
        + _clamp(health_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.18")
        + _clamp((Decimal("8") - training_hours) / Decimal("8"), Decimal("0"), Decimal("1")) * Decimal("0.32"),
        Decimal("0"),
        Decimal("1"),
    )

    margins_by_key = {
        str(item.get("business_key")): item
        for item in ctx["business_margins_payload"].get("items", [])
        if isinstance(item, dict)
    }
    competition_level = str(
        (ctx.get("population_competition_payload") or {}).get("competition_level", "moderate")
    ).lower()
    heat_level = str(
        (ctx.get("population_region_heat_payload") or {}).get("heat_level", "warm")
    ).lower()
    margin_favorable_bonus = Decimal("0")
    for key in ("fruit_shop", "food_truck"):
        item = margins_by_key.get(key) or {}
        if str(item.get("margin_outlook", "")).lower() == "favorable":
            margin_favorable_bonus += Decimal("0.12")
        elif str(item.get("margin_outlook", "")).lower() == "pressured":
            margin_favorable_bonus -= Decimal("0.08")
    if competition_level == "high":
        margin_favorable_bonus -= Decimal("0.05")
    if heat_level == "hot":
        margin_favorable_bonus += Decimal("0.03")

    business_score = _clamp(
        _clamp(active_business_count / Decimal("2"), Decimal("0"), Decimal("1")) * Decimal("0.32")
        + _clamp((business_recent_net + Decimal("40")) / Decimal("120"), Decimal("0"), Decimal("1")) * Decimal("0.33")
        + _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.20")
        + _clamp(margin_favorable_bonus + Decimal("0.15"), Decimal("0"), Decimal("0.30")),
        Decimal("0"),
        Decimal("1"),
    )

    region_key = str(
        getattr(ctx["housing_log"], "region", None)
        or getattr(ctx["housing_state"], "region", None)
        or player.region
        or "suburban"
    ).strip().lower()
    housing_opt_score = _clamp(
        _clamp((commute_hours - Decimal("1.0")) / Decimal("2.0"), Decimal("0"), Decimal("1")) * Decimal("0.52")
        + _clamp(stress_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("0.22")
        + (Decimal("0.20") if region_key == "suburban" else Decimal("0.05"))
        + _clamp((Decimal("12") - days_cash_cushion) / Decimal("12"), Decimal("0"), Decimal("1")) * Decimal("0.06"),
        Decimal("0"),
        Decimal("1"),
    )
    if heat_level == "hot":
        housing_opt_score = _clamp(housing_opt_score + Decimal("0.06"), Decimal("0"), Decimal("1"))

    plan_candidates = [
        {
            "plan_key": "stabilize_finances",
            "title": "Stabilize Finances",
            "short_description": "Lower debt pressure and rebuild a cash cushion over the next few days.",
            "likely_upside": "Distress and payment pressure should ease if obligations are covered consistently.",
            "likely_downside": "Growth pace slows while cash is redirected to defense.",
            "primary_tradeoff": "Short-term expansion speed vs financial stability.",
            "suggested_duration_days": 5,
            "score": stabilize_score,
        },
        {
            "plan_key": "push_income",
            "title": "Push Income",
            "short_description": "Lean into high-yield actions for a short burst to improve liquidity.",
            "likely_upside": "Fast cash improvement if productivity and demand stay supportive.",
            "likely_downside": "Stress and burnout risk can rise if recovery is skipped.",
            "primary_tradeoff": "Immediate cash gain vs higher life-pressure load.",
            "suggested_duration_days": 3,
            "score": push_income_score,
        },
        {
            "plan_key": "reduce_stress",
            "title": "Reduce Stress",
            "short_description": "Prioritize recovery windows to protect health and productivity.",
            "likely_upside": "Better productivity retention and lower burnout risk over the week.",
            "likely_downside": "Lower short-run income while reducing grind intensity.",
            "primary_tradeoff": "Sustainable performance vs short-term earnings.",
            "suggested_duration_days": 3,
            "score": reduce_stress_score,
        },
        {
            "plan_key": "invest_career",
            "title": "Invest in Career",
            "short_description": "Allocate time to training and job progression to improve medium-term earnings.",
            "likely_upside": "Promotion readiness and wage growth potential improve.",
            "likely_downside": "Cash growth is slower in the near term.",
            "primary_tradeoff": "Future compounding income vs current liquidity.",
            "suggested_duration_days": 7,
            "score": career_score,
        },
        {
            "plan_key": "lean_into_business",
            "title": "Lean Into Business",
            "short_description": "Focus on business runs where margin signals are favorable this week.",
            "likely_upside": "Higher upside when demand and cost pressure align.",
            "likely_downside": "Business volatility can amplify losses if conditions turn.",
            "primary_tradeoff": "Higher upside variance vs steadier worker income.",
            "suggested_duration_days": 5,
            "score": business_score,
        },
        {
            "plan_key": "housing_optimization",
            "title": "Housing Optimization",
            "short_description": "Evaluate moving or renting closer to reduce commute burden.",
            "likely_upside": "Lower commute drag can free time and reduce stress load.",
            "likely_downside": "Housing expense rises when living closer to dense opportunities.",
            "primary_tradeoff": "Higher fixed housing cost vs lower daily commute pressure.",
            "suggested_duration_days": 7,
            "score": housing_opt_score,
        },
    ]

    sorted_plans = sorted(plan_candidates, key=lambda item: (-item["score"], item["plan_key"]))
    selected = [item for item in sorted_plans if item["score"] >= Decimal("0.20")][:4]
    if len(selected) < 3:
        selected = sorted_plans[:3]

    items: list[dict] = []
    for item in selected:
        confidence_label = _confidence_from_relevance(item["score"])
        items.append(
            {
                "plan_key": item["plan_key"],
                "title": item["title"],
                "short_description": item["short_description"],
                "likely_upside": item["likely_upside"],
                "likely_downside": item["likely_downside"],
                "primary_tradeoff": item["primary_tradeoff"],
                "suggested_duration_days": int(item["suggested_duration_days"]),
                "confidence_label": confidence_label,
                "debug_meta": {
                    "relevance_score": _score_to_float(item["score"]),
                    "distress_score": _score_to_float(distress_value),
                    "stress": _score_to_float(stress_value),
                    "health": _score_to_float(health_value),
                    "commute_hours": _score_to_float(commute_hours),
                    "days_cash_cushion": _score_to_float(days_cash_cushion),
                    "population_competition_level": competition_level,
                    "population_heat_level": heat_level,
                    "shock_risk_score": _score_to_float(shock_risk_score),
                    "recovery_capacity_score": _score_to_float(recovery_capacity_score),
                    "resilience_label": resilience_label,
                },
            }
        )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "options": items,
        "debug_meta": {
            "day": int(day),
            "strategy_classification": str(ctx["strategy_payload"].get("strategy_classification", "stable_worker")),
            "available_candidates": [item["plan_key"] for item in sorted_plans],
            "population_competition_level": competition_level,
            "population_heat_level": heat_level,
            "shock_risk_score": _score_to_float(shock_risk_score),
            "recovery_capacity_score": _score_to_float(recovery_capacity_score),
            "resilience_label": resilience_label,
        },
    }


def build_housing_tradeoff_analysis(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build a stay-vs-move housing tradeoff analysis for the next 3-7 days."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    ctx = _build_state_context(db, player, day, resolved_date)

    current_region = str(
        getattr(ctx["housing_log"], "region", None)
        or getattr(ctx["housing_state"], "region", None)
        or player.region
        or "suburban"
    ).strip().lower()

    current_cfg = REGION_CONFIG.get(current_region, REGION_CONFIG["suburban"])
    monthly_housing_current = _d(getattr(ctx["housing_state"], "monthly_housing_cost_xgp", current_cfg.monthly_housing_cost_xgp))
    daily_housing_current = _q4(monthly_housing_current / Decimal("30"))

    current_commute_hours = _d(ctx["effective_commute_hours"])

    if current_region == "downtown":
        closer_daily_housing = _q4(daily_housing_current * Decimal("1.12"))
        closer_commute_hours = _clamp(current_commute_hours - Decimal("0.20"), Decimal("0.20"), Decimal("4.50"))
        opportunity_delta = Decimal("0.03")
    else:
        downtown_cfg = REGION_CONFIG["downtown"]
        closer_daily_housing = _q4(_d(downtown_cfg.monthly_housing_cost_xgp) / Decimal("30"))
        closer_commute_hours = _q4(_d(downtown_cfg.commute_hours_baseline) + Decimal("0.18"))
        opportunity_delta = _q4(
            _d(downtown_cfg.job_opportunity_modifier)
            - _d(current_cfg.job_opportunity_modifier)
        )

    housing_delta = _q4(closer_daily_housing - daily_housing_current)
    commute_delta = _q4(closer_commute_hours - current_commute_hours)

    if commute_delta <= Decimal("-0.55"):
        expected_time_delta_label = "Meaningful time gain from shorter commute."
        expected_stress_delta_label = "Likely lower daily stress from reduced travel burden."
    elif commute_delta < Decimal("-0.15"):
        expected_time_delta_label = "Moderate time gain from commuting less."
        expected_stress_delta_label = "Likely mild stress relief from travel reduction."
    else:
        expected_time_delta_label = "Limited time change unless commute congestion worsens."
        expected_stress_delta_label = "Stress impact likely small and mostly workload-driven."

    if opportunity_delta >= Decimal("0.08"):
        opportunity_access_label = "Closer housing should improve access to dense opportunity zones."
    elif opportunity_delta > Decimal("0"):
        opportunity_access_label = "Closer housing should modestly improve opportunity access."
    else:
        opportunity_access_label = "Opportunity access is already near the local ceiling in your current region."

    stress_value = _d(player.stress)
    cash_value = _d(player.cash_xgp)
    if housing_delta > Decimal("0") and stress_value >= Decimal("65") and cash_value >= Decimal("350"):
        recommendation = (
            "Move or rent closer if you can absorb higher housing cost; current stress and commute drag are compounding."
        )
    elif housing_delta > Decimal("0") and cash_value < Decimal("250"):
        recommendation = (
            "Stay for now to protect cash runway, then consider moving closer once buffer improves."
        )
    elif housing_delta <= Decimal("0"):
        recommendation = "Current location is already commute-efficient; focus on cost control and recovery discipline."
    else:
        recommendation = "Hold current region this week and reassess after monitoring commute pressure and cash flow."

    if housing_delta >= Decimal("0"):
        housing_pressure = f"about +{float(_money(housing_delta)):.2f} xgp/day higher housing cost"
    else:
        housing_pressure = f"about {float(_money(housing_delta)):.2f} xgp/day lower housing cost"

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "current_region": current_region,
        "current_commute_burden": f"~{float(_q4(current_commute_hours)):.1f}h/day",
        "closer_housing_cost_pressure": housing_pressure,
        "expected_stress_delta_label": expected_stress_delta_label,
        "expected_time_delta_label": expected_time_delta_label,
        "opportunity_access_label": opportunity_access_label,
        "short_recommendation": recommendation,
        "debug_meta": {
            "day": int(day),
            "current_daily_housing_xgp": float(_money(daily_housing_current)),
            "closer_daily_housing_xgp": float(_money(closer_daily_housing)),
            "housing_delta_xgp": float(_money(housing_delta)),
            "current_commute_hours": float(_q4(current_commute_hours)),
            "closer_commute_hours": float(_q4(closer_commute_hours)),
            "commute_delta_hours": float(_q4(commute_delta)),
            "opportunity_delta": float(_q4(opportunity_delta)),
            "current_actions": ["stay", "move_or_rent_closer"],
        },
    }


def build_debt_vs_growth_analysis(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compare defensive debt moves versus short-horizon growth spending choices."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    ctx = _build_state_context(db, player, day, resolved_date)

    cash_value = _d(player.cash_xgp)
    debt_value = _d(player.debt_xgp)
    distress_value = _d(getattr(ctx["distress"], "distress_score_after", player.distress_score))
    required_payment = _d(getattr(player, "required_daily_debt_payment_xgp", 0))
    avg_expenses = _d(ctx["avg_expenses"])
    avg_income = _d(ctx["avg_income"])
    financial_survival = ctx.get("financial_survival_summary_payload") or {}
    survival_status = str(financial_survival.get("survival_status_label", "current")).strip().lower()
    survival_pressure = str(financial_survival.get("payment_pressure_label", "manageable")).strip().lower()

    days_cash_cushion = _clamp(cash_value / max(Decimal("1"), avg_expenses), Decimal("0"), Decimal("30"))
    debt_pressure = _clamp(required_payment / max(Decimal("1"), avg_income), Decimal("0"), Decimal("2"))

    has_business = len(ctx["businesses"]) > 0
    strategy_class = str(ctx["strategy_payload"].get("strategy_classification", "stable_worker"))

    options: list[dict] = []

    pay_debt_def = _clamp(
        (distress_value / Decimal("100")) * Decimal("56")
        + _clamp(debt_pressure / Decimal("1.2"), Decimal("0"), Decimal("1")) * Decimal("30")
        + _clamp((Decimal("6") - days_cash_cushion) / Decimal("6"), Decimal("0"), Decimal("1")) * Decimal("14"),
        Decimal("0"),
        Decimal("100"),
    )
    if survival_status in {"slipping", "delinquent", "critical"}:
        pay_debt_def = _clamp(pay_debt_def + Decimal("12"), Decimal("0"), Decimal("100"))
    elif survival_pressure in {"high", "critical"}:
        pay_debt_def = _clamp(pay_debt_def + Decimal("7"), Decimal("0"), Decimal("100"))
    pay_debt_growth = _clamp(Decimal("32") - (pay_debt_def / Decimal("5")), Decimal("8"), Decimal("40"))
    options.append(
        {
            "option_key": "pay_down_debt",
            "option_label": "Use extra cash to reduce debt",
            "defensive_score": float(_q4(pay_debt_def)),
            "growth_score": float(_q4(pay_debt_growth)),
            "liquidity_risk": "moderate" if days_cash_cushion < Decimal("4") else "low",
            "distress_impact_label": "Likely lowers distress pressure over the next week.",
            "recommendation_note": "Best when payment pressure is rising or missed-payment risk is visible.",
            "debug_meta": {
                "distress_score": float(_q4(distress_value)),
                "debt_pressure_ratio": float(_q4(debt_pressure)),
                "days_cash_cushion": float(_q4(days_cash_cushion)),
                "survival_status_label": survival_status,
                "payment_pressure_label": survival_pressure,
            },
        }
    )

    training_growth = _clamp(
        Decimal("44")
        + _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("32")
        + (Decimal("8") if strategy_class in {"career_builder", "stable_worker"} else Decimal("0")),
        Decimal("0"),
        Decimal("100"),
    )
    if survival_status in {"delinquent", "critical"}:
        training_growth = _clamp(training_growth - Decimal("12"), Decimal("0"), Decimal("100"))
    training_def = _clamp(
        Decimal("22") + _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("18"),
        Decimal("0"),
        Decimal("100"),
    )
    training_liq = "high" if days_cash_cushion < Decimal("3.0") else "moderate"
    options.append(
        {
            "option_key": "career_training_invest",
            "option_label": "Invest in training and career growth",
            "defensive_score": float(_q4(training_def)),
            "growth_score": float(_q4(training_growth)),
            "liquidity_risk": training_liq,
            "distress_impact_label": "Neutral near-term distress impact; stronger medium-term upside.",
            "recommendation_note": "Stronger when daily finances are stable enough to absorb slower cash gains.",
            "debug_meta": {
                "strategy_classification": strategy_class,
                "days_cash_cushion": float(_q4(days_cash_cushion)),
            },
        }
    )

    cash_buffer_def = _clamp(
        Decimal("30")
        + _clamp((Decimal("5") - days_cash_cushion) / Decimal("5"), Decimal("0"), Decimal("1")) * Decimal("45")
        + _clamp(distress_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("20"),
        Decimal("0"),
        Decimal("100"),
    )
    if survival_pressure in {"high", "critical"}:
        cash_buffer_def = _clamp(cash_buffer_def + Decimal("8"), Decimal("0"), Decimal("100"))
    cash_buffer_growth = _clamp(
        Decimal("20") + _clamp(days_cash_cushion / Decimal("10"), Decimal("0"), Decimal("1")) * Decimal("20"),
        Decimal("0"),
        Decimal("100"),
    )
    options.append(
        {
            "option_key": "hold_cash_buffer",
            "option_label": "Hold cash buffer",
            "defensive_score": float(_q4(cash_buffer_def)),
            "growth_score": float(_q4(cash_buffer_growth)),
            "liquidity_risk": "low",
            "distress_impact_label": "Improves resilience against bad-day chains and bill shocks.",
            "recommendation_note": "Useful when uncertainty is high and your cushion is thin.",
            "debug_meta": {
                "days_cash_cushion": float(_q4(days_cash_cushion)),
                "distress_score": float(_q4(distress_value)),
            },
        }
    )

    if has_business:
        recent_business_net = _d(getattr(ctx["fruit_log"], "net_profit_xgp", 0)) + _d(
            getattr(ctx["truck_log"], "net_profit_xgp", 0)
        )
        business_growth = _clamp(
            Decimal("35")
            + _clamp((recent_business_net + Decimal("45")) / Decimal("110"), Decimal("0"), Decimal("1")) * Decimal("42")
            + _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("13"),
            Decimal("0"),
            Decimal("100"),
        )
        business_def = _clamp(
            Decimal("18")
            + _clamp((Decimal("100") - distress_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("14"),
            Decimal("0"),
            Decimal("100"),
        )
        if survival_status in {"slipping", "delinquent", "critical"}:
            business_def = _clamp(business_def - Decimal("6"), Decimal("0"), Decimal("100"))
            business_growth = _clamp(business_growth - Decimal("10"), Decimal("0"), Decimal("100"))
        liquidity_risk = "high" if days_cash_cushion < Decimal("4.0") or distress_value >= Decimal("60") else "moderate"
        if survival_pressure in {"high", "critical"}:
            liquidity_risk = "high"
        options.append(
            {
                "option_key": "business_upgrade_spend",
                "option_label": "Spend on business upgrades",
                "defensive_score": float(_q4(business_def)),
                "growth_score": float(_q4(business_growth)),
                "liquidity_risk": liquidity_risk,
                "distress_impact_label": (
                    "Can worsen distress if cash is thin; strongest when margin outlook is stable."
                ),
                "recommendation_note": (
                    "Use only if debt pressure is controlled and business margins are not currently pressured."
                ),
                "debug_meta": {
                    "recent_business_net_xgp": float(_money(recent_business_net)),
                    "days_cash_cushion": float(_q4(days_cash_cushion)),
                    "distress_score": float(_q4(distress_value)),
                    "survival_status_label": survival_status,
                },
            }
        )

    options.sort(key=lambda item: (-float(item["defensive_score"] + item["growth_score"] / 2), item["option_key"]))

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": options,
        "debug_meta": {
            "day": int(day),
            "cash_xgp": float(_money(cash_value)),
            "debt_xgp": float(_money(debt_value)),
            "days_cash_cushion": float(_q4(days_cash_cushion)),
            "has_business": has_business,
            "survival_status_label": survival_status,
            "payment_pressure_label": survival_pressure,
        },
    }


def build_business_mode_plan_analysis(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build short-horizon operating guidance for Fruit Shop and Food Truck modes."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    ctx = _build_state_context(db, player, day, resolved_date)

    margins = {
        str(item.get("business_key")): item
        for item in ctx["business_margins_payload"].get("items", [])
        if isinstance(item, dict)
    }
    price_trends = {
        str(item.get("basket_key")): item
        for item in ctx["price_trends_payload"].get("items", [])
        if isinstance(item, dict)
    }
    active_business_by_type = {
        str(row.business_type): row for row in ctx["businesses"]
    }
    competition_payload = ctx.get("population_competition_payload") or {}
    region_heat_payload = ctx.get("population_region_heat_payload") or {}

    def _build_item(business_key: str) -> dict:
        business_row = active_business_by_type.get(business_key)
        margin_row = margins.get(business_key, {})

        if business_key == "fruit_shop":
            input_trend = str(price_trends.get("produce", {}).get("short_term_trend", "stable"))
            input_vol = str(price_trends.get("produce", {}).get("volatility_label", "moderate"))
            watch_item = "Watch produce input pressure and spoilage drift."
        else:
            essentials_trend = str(price_trends.get("essentials", {}).get("short_term_trend", "stable"))
            protein_trend = str(price_trends.get("protein", {}).get("short_term_trend", "stable"))
            input_trend = f"essentials {essentials_trend}, protein {protein_trend}"
            input_vol = str(price_trends.get("protein", {}).get("volatility_label", "moderate"))
            watch_item = "Watch protein + fuel drag against ticket conversion."

        margin_outlook = str(margin_row.get("margin_outlook", "mixed"))
        demand_outlook = str(margin_row.get("demand_outlook", "stable"))
        cost_pressure = str(margin_row.get("cost_pressure", "moderate"))
        competition_level = str(competition_payload.get("competition_level", "moderate")).lower()
        heat_level = str(region_heat_payload.get("heat_level", "warm")).lower()

        if business_row is None:
            recommendation = (
                "No active business here yet. Prioritize cash stability before forcing expansion."
            )
            mode_hint = "not_applicable"
            stability = "n/a"
        elif margin_outlook == "pressured":
            recommendation = (
                "Operate cautiously for 3-5 days: favor conservative mode, tighter inventory, and margin protection."
            )
            mode_hint = "conservative_pricing" if business_key == "fruit_shop" else "budget_menu"
            stability = "fragile"
        elif margin_outlook == "favorable" and demand_outlook in {"supportive", "strong"}:
            recommendation = (
                "Conditions support a controlled push over 5 days; keep risk checks active while scaling output."
            )
            mode_hint = "normal_pricing" if business_key == "fruit_shop" else "standard_menu"
            stability = "stable"
            if competition_level == "high":
                recommendation = (
                    "Demand is favorable but competition is tight; keep a controlled push with strict margin discipline."
                )
        else:
            recommendation = (
                "Stay balanced this week and adjust mode only after daily demand confirms direction."
            )
            mode_hint = "normal_pricing" if business_key == "fruit_shop" else "standard_menu"
            stability = "mixed"

        current_mode = ""
        upgrades: list[str] = []
        if business_row is not None:
            current_mode = str(getattr(business_row, "operating_mode", "") or "")
            upgrades_raw = str(getattr(business_row, "upgrades_json", "[]") or "[]").strip()
            upgrades = [
                value.strip().strip('"')
                for value in upgrades_raw.strip("[]").split(",")
                if value.strip()
            ]

        return {
            "business_key": business_key,
            "business_present": business_row is not None,
            "current_mode": current_mode,
            "demand_outlook": demand_outlook,
            "input_cost_outlook": f"{cost_pressure} ({input_trend})",
            "margin_stability": stability,
            "recommendation_over_horizon": recommendation,
            "key_watch_item": watch_item,
            "debug_meta": {
                "day": int(day),
                "margin_outlook": margin_outlook,
                "cost_pressure": cost_pressure,
                "input_volatility": input_vol,
                "population_competition_level": competition_level,
                "population_heat_level": heat_level,
                "recommended_mode_hint": mode_hint,
                "applied_upgrades": upgrades,
            },
        }

    items = [_build_item("fruit_shop"), _build_item("food_truck")]

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": items,
        "debug_meta": {
            "day": int(day),
            "active_business_count": int(len(ctx["businesses"])),
            "population_competition_level": str(
                (ctx.get("population_competition_payload") or {}).get("competition_level", "moderate")
            ).lower(),
            "population_heat_level": str(
                (ctx.get("population_region_heat_payload") or {}).get("heat_level", "warm")
            ).lower(),
        },
    }


def build_recovery_vs_push_analysis(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compare short-horizon push strategy against recovery strategy."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    ctx = _build_state_context(db, player, day, resolved_date)

    stress_value = _d(player.stress)
    health_value = _d(player.health)
    productivity = _d(getattr(player, "productivity_modifier", 1.0))
    distress_value = _d(getattr(ctx["distress"], "distress_score_after", player.distress_score))
    commute_hours = _d(ctx["effective_commute_hours"])
    overtime = _d(getattr(ctx["daily_state"], "overtime_hours", 0)) if ctx["daily_state"] is not None else Decimal("0")
    shock_summary_payload = ctx.get("personal_shock_summary_payload") or {}
    resilience_summary_payload = ctx.get("resilience_summary_payload") or {}
    shock_profile = (
        (shock_summary_payload.get("debug_meta") or {}).get("profile")
        if isinstance(shock_summary_payload, dict)
        else {}
    ) or {}
    shock_risk_score = _d(shock_profile.get("shock_risk_score", 0))
    recovery_capacity_score = _d(shock_profile.get("recovery_capacity_score", 55))
    resilience_label = str(resilience_summary_payload.get("resilience_label", "stable")).lower()
    practical_actions = list(shock_summary_payload.get("practical_current_actions", []))[:4]

    pressure_score = _clamp(
        _clamp(stress_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("45")
        + _clamp((Decimal("100") - health_value) / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("23")
        + _clamp((Decimal("1") - productivity) / Decimal("0.30"), Decimal("0"), Decimal("1")) * Decimal("14")
        + _clamp((commute_hours - Decimal("0.8")) / Decimal("2.2"), Decimal("0"), Decimal("1")) * Decimal("10")
        + _clamp(distress_value / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("8")
        + _clamp(shock_risk_score / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("10")
        + _clamp((Decimal("60") - recovery_capacity_score) / Decimal("60"), Decimal("0"), Decimal("1")) * Decimal("8"),
        Decimal("0"),
        Decimal("100"),
    )

    if pressure_score >= Decimal("72"):
        pressure_level = "high"
    elif pressure_score >= Decimal("45"):
        pressure_level = "moderate"
    else:
        pressure_level = "low"

    push_case = (
        "Push case: prioritize higher-income actions for 3 days to improve immediate liquidity, "
        "accepting higher stress and recovery drag."
    )
    recovery_case = (
        "Recovery case: reduce grind intensity for 3 days, protect sleep/recovery, and restore productivity efficiency."
    )

    if pressure_level == "high":
        near_term_cost = (
            "Pushing now likely amplifies burnout and personal disruption spillover into income quality."
        )
        near_term_benefit = "Recovery now should stabilize productivity and lower stress spillover into debt/career systems."
        recommendation_summary = (
            "Recovery-first is stronger this week; push only if urgent cash gap cannot be covered otherwise."
        )
    elif pressure_level == "moderate":
        near_term_cost = "Full push can still raise stress faster than income quality if repeated for several days."
        near_term_benefit = "A mixed plan (1 push day, 1 recovery day cadence) can preserve momentum with less burnout risk."
        recommendation_summary = "Use a mixed cadence: selective push with deliberate recovery slots."
    else:
        near_term_cost = "Pure recovery plan may leave growth opportunities underused in the current window."
        near_term_benefit = "Short controlled push can improve cash and progress while pressure remains manageable."
        recommendation_summary = "Controlled push is reasonable now, but maintain recovery floor to avoid pressure creep."

    if resilience_label == "fragile":
        recommendation_summary += " Current resilience is fragile, so avoid multi-day all-in grind streaks."
    elif resilience_label == "stretched":
        recommendation_summary += " Keep at least one low-strain day in each 2-3 day block."

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "current_pressure_level": pressure_level,
        "push_case": push_case,
        "recovery_case": recovery_case,
        "likely_near_term_cost": near_term_cost,
        "likely_near_term_benefit": near_term_benefit,
        "recommendation_summary": recommendation_summary,
        "debug_meta": {
            "day": int(day),
            "pressure_score": float(_q4(pressure_score)),
            "stress": float(_q4(stress_value)),
            "health": float(_q4(health_value)),
            "productivity_modifier": float(_q4(productivity)),
            "commute_hours": float(_q4(commute_hours)),
            "overtime_hours": float(_q4(overtime)),
            "distress_score": float(_q4(distress_value)),
            "shock_risk_score": float(_q4(shock_risk_score)),
            "recovery_capacity_score": float(_q4(recovery_capacity_score)),
            "resilience_label": resilience_label,
            "practical_shock_actions": practical_actions,
        },
    }


def build_player_strategy_recommendation(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build one composed short-horizon recommendation for the player."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    ctx = _build_state_context(db, player, day, resolved_date)

    plans = build_short_horizon_plan_options(db=db, player_id=player.id, as_of_date=resolved_date)
    housing = build_housing_tradeoff_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    debt_vs_growth = build_debt_vs_growth_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    recovery_vs_push = build_recovery_vs_push_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    market = build_market_overview(db=db, player_id=player.id, as_of_date=resolved_date)
    try:
        personal_shock_summary = build_personal_shock_summary(
            db=db,
            player_id=player.id,
            as_of_date=resolved_date,
            day_number=day,
        )
    except Exception:
        personal_shock_summary = {}
    try:
        resilience_summary = build_player_resilience_summary(
            db=db,
            player_id=player.id,
            as_of_date=resolved_date,
            day_number=day,
        )
    except Exception:
        resilience_summary = {}

    options = plans.get("options", [])
    top_option = options[0] if options else {
        "plan_key": "stabilize_finances",
        "title": "Stabilize Finances",
        "confidence_label": "low",
    }

    stress_value = _d(player.stress)
    distress_value = _d(player.distress_score)
    commute_label = str(housing.get("expected_time_delta_label", "")).lower()
    shock_profile = (
        (personal_shock_summary.get("debug_meta") or {}).get("profile")
        if isinstance(personal_shock_summary, dict)
        else {}
    ) or {}
    shock_risk_score = _d(shock_profile.get("shock_risk_score", 0))
    resilience_label = str(resilience_summary.get("resilience_label", "stable")).lower()
    financial_survival_summary = ctx.get("financial_survival_summary_payload") or {}
    survival_status = str(financial_survival_summary.get("survival_status_label", "current")).lower()
    payment_pressure_label = str(financial_survival_summary.get("payment_pressure_label", "manageable")).lower()
    borrowing_pressure_summary = ctx.get("borrowing_pressure_summary_payload") or {}
    borrowing_risk_summary = ctx.get("borrowing_risk_summary_payload") or {}
    borrowing_liquidity_pressure = str(
        borrowing_pressure_summary.get("current_liquidity_pressure_label", "low")
    ).lower()
    borrowing_risk_label = str(borrowing_risk_summary.get("risk_label", "locked")).lower()

    if borrowing_risk_label in {"trap_like", "dangerous"} and borrowing_liquidity_pressure in {"high", "critical"}:
        biggest_risk = "Emergency borrowing pressure is high and available options look trap-like under current burden."
    elif survival_status in {"delinquent", "critical"}:
        biggest_risk = "Obligation survival pressure is now compounding into credit and liquidity damage."
    elif payment_pressure_label in {"high", "critical"}:
        biggest_risk = "Required payment burden is the dominant weekly risk; missed obligations can snowball."
    elif shock_risk_score >= Decimal("70"):
        biggest_risk = "Personal disruption risk is elevated; one bad week can cascade into debt and productivity drag."
    elif distress_value >= Decimal("70"):
        biggest_risk = "Debt and distress pressure can compound quickly if obligations slip this week."
    elif stress_value >= Decimal("70"):
        biggest_risk = "Sustained high stress is threatening productivity and burnout risk."
    elif "time gain" in commute_label:
        biggest_risk = "Commute burden is consuming recovery and limiting high-quality action capacity."
    else:
        biggest_risk = "Cash-flow variance remains the key risk if costs rise faster than income."

    winners = market.get("top_winners", []) if isinstance(market, dict) else []
    if winners:
        biggest_opportunity = f"{winners[0]} currently has favorable momentum in the market setup."
    else:
        biggest_opportunity = "Balanced market conditions support disciplined compounding this week."

    debt_items = debt_vs_growth.get("items", [])
    defensive_pick = max(debt_items, key=lambda item: float(item.get("defensive_score", 0)), default=None)
    growth_pick = max(debt_items, key=lambda item: float(item.get("growth_score", 0)), default=None)

    defensive_move = defensive_pick.get("option_label") if defensive_pick else "Protect cash buffer and avoid optional spend."
    practical_shock_actions = list(personal_shock_summary.get("practical_current_actions", []))
    if practical_shock_actions:
        defensive_move = str(practical_shock_actions[0])
    growth_move = growth_pick.get("option_label") if growth_pick else "Use stable windows for measured career growth."

    pressure_level = str(recovery_vs_push.get("current_pressure_level", "moderate"))
    if borrowing_risk_label in {"trap_like", "dangerous"}:
        avoid_warning = "Avoid stacking another expensive bridge; stabilize obligations first."
    elif pressure_level == "high":
        avoid_warning = "Avoid stacking overtime and business push in the same 2-3 day block."
    elif pressure_level == "moderate":
        avoid_warning = "Avoid all-in grind streaks without recovery days."
    else:
        avoid_warning = "Avoid overconfidence from one good day; keep risk controls active."
    if resilience_label == "fragile":
        avoid_warning = "Avoid all-in growth pushes until resilience improves; instability risk is high."

    reason = (
        f"{top_option.get('title', 'Current plan')} is preferred because your current risk/opportunity profile "
        "shows the best expected 3-7 day tradeoff in this state."
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "recommended_plan_key": str(top_option.get("plan_key", "stabilize_finances")),
        "recommended_plan_title": str(top_option.get("title", "Stabilize Finances")),
        "biggest_risk": biggest_risk,
        "biggest_opportunity": biggest_opportunity,
        "defensive_move": str(defensive_move),
        "growth_move": str(growth_move),
        "avoid_warning": avoid_warning,
        "recommendation_reason": reason,
        "debug_meta": {
            "day": int(day),
            "recommended_confidence": str(top_option.get("confidence_label", "low")),
            "pressure_level": pressure_level,
            "market_mood": str(market.get("current_market_mood", "mixed")),
            "shock_risk_score": float(_q4(shock_risk_score)),
            "resilience_label": resilience_label,
            "practical_shock_actions": practical_shock_actions,
            "survival_status_label": survival_status,
            "payment_pressure_label": payment_pressure_label,
            "borrowing_liquidity_pressure": borrowing_liquidity_pressure,
            "borrowing_risk_label": borrowing_risk_label,
            "borrowing_pressure_summary": borrowing_pressure_summary,
            "borrowing_risk_summary": borrowing_risk_summary,
            "financial_survival_summary": financial_survival_summary,
        },
    }


def build_locked_future_path_preparation(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build subtle future locked path preparation signals (non-actionable)."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)

    commute_payload = build_commute_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    pressure_level = str(commute_payload.get("commute_pressure_level", "moderate")).lower()
    debug_meta = commute_payload.get("debug_meta", {}) if isinstance(commute_payload, dict) else {}

    congestion_hours = _d(debug_meta.get("congestion_hours", 0))
    effective_hours = _d(debug_meta.get("effective_commute_hours", 0))
    if pressure_level == "high" or congestion_hours >= Decimal("0.55"):
        prep_signal = "strong"
    elif pressure_level == "moderate":
        prep_signal = "moderate"
    else:
        prep_signal = "early"

    items = [
        {
            "path_key": "mobility_path",
            "title": "Future Mobility Paths",
            "why_it_matters_now": "Rising commute burden makes long-term mobility options strategically relevant.",
            "current_preparation_signal": f"{prep_signal} signal from current commute pressure and congestion trend.",
            "unlock_status": "locked",
            "category": "mobility",
            "debug_meta": {
                "effective_commute_hours": float(_q4(effective_hours)),
                "congestion_hours": float(_q4(congestion_hours)),
            },
        },
        {
            "path_key": "transport_startup_path",
            "title": "Transportation Startup Track",
            "why_it_matters_now": "Transport friction signals future opportunity for systems that reduce dead travel time.",
            "current_preparation_signal": "Observe commute-heavy weeks and maintain cash discipline for future unlock windows.",
            "unlock_status": "locked",
            "category": "transportation",
            "debug_meta": {
                "pressure_level": pressure_level,
            },
        },
        {
            "path_key": "logistics_venture_path",
            "title": "Logistics Venture Path",
            "why_it_matters_now": "Cost and delivery pressure trends can later support logistics-focused strategic branches.",
            "current_preparation_signal": "Track fuel + commute drag now; practical current solution remains moving/renting closer.",
            "unlock_status": "locked",
            "category": "logistics",
            "debug_meta": {
                "pressure_level": pressure_level,
            },
        },
        {
            "path_key": "housing_services_path",
            "title": "Housing Services Path",
            "why_it_matters_now": "Housing-versus-commute tradeoffs suggest future housing-adjacent optimization opportunities.",
            "current_preparation_signal": "Use current region decisions as preparation; advanced solutions remain locked.",
            "unlock_status": "locked",
            "category": "housing_services",
            "debug_meta": {
                "current_region": str(commute_payload.get("region_key", "suburban")),
            },
        },
    ]

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": items,
        "debug_meta": {
            "day": int(day),
            "commute_pressure_level": pressure_level,
            "current_practical_solutions": ["stay", "move_or_rent_closer"],
        },
    }


def build_strategic_planning_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compose all Step 28 strategic planning payloads for one player."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, as_of_date)

    plans = build_short_horizon_plan_options(db=db, player_id=player.id, as_of_date=resolved_date)
    housing = build_housing_tradeoff_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    debt_growth = build_debt_vs_growth_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    business_plan = build_business_mode_plan_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    recovery_push = build_recovery_vs_push_analysis(db=db, player_id=player.id, as_of_date=resolved_date)
    recommendation = build_player_strategy_recommendation(db=db, player_id=player.id, as_of_date=resolved_date)
    future_paths = build_locked_future_path_preparation(db=db, player_id=player.id, as_of_date=resolved_date)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "plans": plans,
        "housing_tradeoff": housing,
        "debt_vs_growth": debt_growth,
        "business_plan": business_plan,
        "recovery_vs_push": recovery_push,
        "recommendation": recommendation,
        "future_preparation": future_paths,
        "debug_meta": {
            "service": "strategic_planning_service",
            "version": "step28_v1",
        },
    }
