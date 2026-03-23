"""Step 22 weekly strategy summary service."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.event_catalog import EVENT_CATALOG_BY_KEY
from app.engine.player_strategy_service import classify_player_strategy
from app.models.basket_daily_price import BasketDailyPrice
from app.models.career_progress_log import CareerProgressLog
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.financial_distress_log import FinancialDistressLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState

Q4 = Decimal("0.0001")
GAME_EPOCH = date(2026, 1, 1)


class WeeklyStrategyError(Exception):
    """Base weekly summary exception."""


class WeeklyStrategyNotFoundError(WeeklyStrategyError):
    """Raised when required state cannot be found."""


class WeeklyStrategyValidationError(WeeklyStrategyError):
    """Raised when input values are invalid."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise WeeklyStrategyNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise WeeklyStrategyNotFoundError("Player not found.")
    return row


def _resolve_end_day(db: Session, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        day = int((as_of_date - GAME_EPOCH).days) + 1
        if day <= 0:
            raise WeeklyStrategyValidationError("as_of_date must be on or after game epoch.")
        return day, as_of_date
    latest = db.query(func.max(DailySettlementLog.day_number)).scalar()
    if latest is None:
        latest = db.query(func.max(MacroDailyState.day)).scalar()
    if latest is None:
        return 1, GAME_EPOCH
    day_int = int(latest)
    return day_int, GAME_EPOCH + timedelta(days=max(0, day_int - 1))


def _day_to_date(day: int) -> date:
    return GAME_EPOCH + timedelta(days=max(0, int(day) - 1))


def _trend_label(start_value: Decimal, end_value: Decimal, *, tolerance: Decimal = Decimal("0.25")) -> str:
    delta = end_value - start_value
    if delta > tolerance:
        return "rising"
    if delta < -tolerance:
        return "falling"
    return "stable"


def build_player_weekly_strategy_summary(
    db: Session,
    player_id: str | UUID,
    *,
    as_of_date: date | None = None,
) -> dict:
    """Build deterministic player weekly strategic summary from actual logs."""
    player = _resolve_player(db, player_id)
    end_day, _ = _resolve_end_day(db, as_of_date=as_of_date)
    start_day = max(1, end_day - 6)

    settlements = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number >= start_day,
            DailySettlementLog.day_number <= end_day,
        )
        .order_by(DailySettlementLog.day_number.asc(), DailySettlementLog.created_at.asc())
        .all()
    )
    distress_logs = (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player.id,
            FinancialDistressLog.day >= start_day,
            FinancialDistressLog.day <= end_day,
        )
        .order_by(FinancialDistressLog.day.asc(), FinancialDistressLog.created_at.asc())
        .all()
    )
    career_logs = (
        db.query(CareerProgressLog)
        .filter(
            CareerProgressLog.player_id == player.id,
            CareerProgressLog.day_number >= start_day,
            CareerProgressLog.day_number <= end_day,
        )
        .order_by(CareerProgressLog.day_number.asc(), CareerProgressLog.created_at.asc())
        .all()
    )

    income_totals = {
        "job_income": Decimal("0.00"),
        "side_income": Decimal("0.00"),
        "business_income": Decimal("0.00"),
    }
    cost_totals = {
        "living_cost_pressure": Decimal("0.00"),
        "debt_pressure": Decimal("0.00"),
        "business_cost_pressure": Decimal("0.00"),
    }
    for row in settlements:
        side_income = _d(getattr(row, "side_income_net_xgp", 0))
        business_income = _d(getattr(row, "business_net_profit_xgp", 0))
        gross_income = _d(getattr(row, "income_xgp", 0))
        inferred_job_income = max(Decimal("0.00"), gross_income - max(Decimal("0.00"), side_income) - max(Decimal("0.00"), business_income))
        income_totals["job_income"] += inferred_job_income
        income_totals["side_income"] += side_income
        income_totals["business_income"] += business_income

        cost_totals["living_cost_pressure"] += (
            _d(getattr(row, "housing_cost_daily_xgp", 0))
            + _d(getattr(row, "utilities_cost_daily_xgp", 0))
            + _d(getattr(row, "commute_fuel_cost_xgp", 0))
        )
        cost_totals["debt_pressure"] += (
            _d(getattr(row, "debt_payment_due_xgp", 0))
            + _d(getattr(row, "late_fee_xgp", 0))
            + _d(getattr(row, "accrued_interest_xgp", 0))
        )
        cost_totals["business_cost_pressure"] += (
            _d(getattr(row, "business_cogs_xgp", 0))
            + _d(getattr(row, "business_overhead_xgp", 0))
            + _d(getattr(row, "business_fuel_cost_xgp", 0))
        )

    dominant_income_source = max(income_totals.items(), key=lambda item: item[1])[0]
    largest_cost_pressure = max(cost_totals.items(), key=lambda item: item[1])[0]

    if settlements:
        stress_trend = _trend_label(_d(settlements[0].stress_after), _d(settlements[-1].stress_after))
        health_trend = _trend_label(_d(settlements[0].health_after), _d(settlements[-1].health_after))
    else:
        stress_trend = "stable"
        health_trend = "stable"

    if distress_logs:
        distress_trend = _trend_label(
            _d(distress_logs[0].distress_score_after),
            _d(distress_logs[-1].distress_score_after),
            tolerance=Decimal("0.75"),
        )
    else:
        distress_trend = "stable"

    if career_logs:
        career_trend = _trend_label(
            _d(career_logs[0].skill_after),
            _d(career_logs[-1].skill_after),
            tolerance=Decimal("0.05"),
        )
    else:
        career_trend = "stable"

    classification = classify_player_strategy(
        db=db,
        player_id=player.id,
        as_of_date=_day_to_date(end_day),
        lookback_days=7,
    )
    strategy_classification = str(classification["strategy_classification"])

    suggested_next_moves: list[str] = []
    if distress_trend == "rising" or strategy_classification == "recovery_mode":
        suggested_next_moves.append("Prioritize debt stability and reduce fixed outflows this week.")
    if stress_trend == "rising":
        suggested_next_moves.append("Reduce overtime blocks and protect sleep/recovery windows.")
    if dominant_income_source == "job_income" and career_trend != "rising":
        suggested_next_moves.append("Shift 2-4 hours toward training to improve promotion pace.")
    if dominant_income_source == "business_income" and largest_cost_pressure == "business_cost_pressure":
        suggested_next_moves.append("Switch to lower-risk business mode and pause risky inventory scaling.")
    if dominant_income_source == "side_income" and strategy_classification in {"hustler", "overextended"}:
        suggested_next_moves.append("Trim grind hours slightly to avoid productivity drag.")
    if not suggested_next_moves:
        suggested_next_moves.append("Maintain current plan and keep a small cash buffer for volatility.")

    return {
        "player_id": str(player.id),
        "week_start": _day_to_date(start_day).isoformat(),
        "week_end": _day_to_date(end_day).isoformat(),
        "dominant_income_source": dominant_income_source,
        "largest_cost_pressure": largest_cost_pressure,
        "distress_trend": distress_trend,
        "stress_trend": stress_trend,
        "health_trend": health_trend,
        "career_trend": career_trend,
        "strategy_classification": strategy_classification,
        "suggested_next_moves": suggested_next_moves[:4],
        "debug_meta": {
            "income_totals": {k: float(_q4(v)) for k, v in income_totals.items()},
            "cost_totals": {k: float(_q4(v)) for k, v in cost_totals.items()},
            "classification_drivers": classification["classification_drivers"],
            "rows": {
                "settlements": len(settlements),
                "distress_logs": len(distress_logs),
                "career_logs": len(career_logs),
            },
        },
    }


def build_economy_weekly_summary(
    db: Session,
    *,
    as_of_date: date | None = None,
) -> dict:
    """Build deterministic weekly macro/economy summary from existing logs."""
    end_day, _ = _resolve_end_day(db, as_of_date=as_of_date)
    start_day = max(1, end_day - 6)

    events = (
        db.query(DailyEconomyEvent)
        .filter(DailyEconomyEvent.day >= start_day, DailyEconomyEvent.day <= end_day)
        .order_by(DailyEconomyEvent.day.asc(), DailyEconomyEvent.created_at.asc())
        .all()
    )
    event_counts: dict[str, int] = {}
    chain_counts: dict[str, int] = {}
    pressured_sectors: dict[str, int] = {}
    total_event_severity = Decimal("0.00")
    for row in events:
        event_counts[row.event_key] = event_counts.get(row.event_key, 0) + 1
        template = EVENT_CATALOG_BY_KEY.get(row.event_key)
        chain_key = template.chain_group_key if template is not None and template.chain_group_key else row.event_category
        chain_counts[chain_key] = chain_counts.get(chain_key, 0) + 1
        if str(row.sentiment).lower() == "negative":
            pressured_sectors[row.event_category] = pressured_sectors.get(row.event_category, 0) + 1
        total_event_severity += _d(getattr(row, "severity", 0))

    baskets = (
        db.query(BasketDailyPrice)
        .filter(BasketDailyPrice.day >= start_day, BasketDailyPrice.day <= end_day)
        .order_by(BasketDailyPrice.day.asc(), BasketDailyPrice.basket_type.asc())
        .all()
    )
    basket_series: dict[str, list[Decimal]] = {}
    for row in baskets:
        key = str(row.basket_type.value if isinstance(row.basket_type, BasketType) else row.basket_type)
        basket_series.setdefault(key, []).append(_d(row.price_index))
    basket_movers: list[tuple[str, Decimal]] = []
    for key, values in basket_series.items():
        if len(values) < 2:
            continue
        start_price = values[0]
        end_price = values[-1]
        if start_price <= Decimal("0"):
            continue
        change_pct = _q4((end_price - start_price) / start_price)
        basket_movers.append((key, change_pct))
    basket_movers.sort(key=lambda item: abs(item[1]), reverse=True)

    employment_rows = (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.day >= start_day,
            PlayerEmploymentState.day <= end_day,
            PlayerEmploymentState.current_job_code.isnot(None),
        )
        .all()
    )
    job_scores: dict[str, list[Decimal]] = {}
    for row in employment_rows:
        job_key = str(row.current_job_code or "").strip().lower()
        if not job_key:
            continue
        job_scores.setdefault(job_key, []).append(_d(getattr(row, "opportunity_score", 1)))
    strongest_jobs: list[tuple[str, Decimal]] = []
    for job_key, scores in job_scores.items():
        strongest_jobs.append((job_key, _q4(sum(scores, Decimal("0")) / Decimal(str(max(1, len(scores)))))))
    strongest_jobs.sort(key=lambda item: item[1], reverse=True)

    macro_rows = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day >= start_day, MacroDailyState.day <= end_day)
        .order_by(MacroDailyState.day.asc())
        .all()
    )
    volatility_signal = Decimal("0.00")
    if len(macro_rows) >= 2:
        for idx in range(1, len(macro_rows)):
            prev = macro_rows[idx - 1]
            cur = macro_rows[idx]
            volatility_signal += abs(_d(cur.consumer_confidence) - _d(prev.consumer_confidence)) / Decimal("6")
            volatility_signal += abs(_d(cur.oil_index) - _d(prev.oil_index)) / Decimal("25")
            volatility_signal += abs(_d(cur.supply_chain_stress) - _d(prev.supply_chain_stress)) / Decimal("0.25")
    volatility_signal += total_event_severity / Decimal("20")

    if volatility_signal >= Decimal("7.5"):
        volatility_tone = "high_volatility"
    elif volatility_signal >= Decimal("4.0"):
        volatility_tone = "mixed_volatility"
    else:
        volatility_tone = "stable_to_recovery"

    return {
        "week_start": _day_to_date(start_day).isoformat(),
        "week_end": _day_to_date(end_day).isoformat(),
        "dominant_event_chains": [name for name, _count in sorted(chain_counts.items(), key=lambda item: item[1], reverse=True)[:4]],
        "top_basket_movers": [
            {"basket_type": name, "weekly_change_pct": float(change)}
            for name, change in basket_movers[:4]
        ],
        "strongest_jobs": [
            {"job_key": name, "avg_opportunity_score": float(score)}
            for name, score in strongest_jobs[:4]
        ],
        "pressured_sectors": [name for name, _count in sorted(pressured_sectors.items(), key=lambda item: item[1], reverse=True)[:4]],
        "volatility_tone": volatility_tone,
        "debug_meta": {
            "event_count": len(events),
            "volatility_signal": float(_q4(volatility_signal)),
            "top_events": [name for name, _count in sorted(event_counts.items(), key=lambda item: item[1], reverse=True)[:5]],
            "window": {"start_day": start_day, "end_day": end_day},
        },
    }
