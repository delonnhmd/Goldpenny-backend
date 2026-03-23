"""Step 22 player strategy classification service."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.career_progress_log import CareerProgressLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_daily_state import PlayerDailyState

Q4 = Decimal("0.0001")
GAME_EPOCH = date(2026, 1, 1)

STRATEGY_CLASSES = {
    "stable_worker",
    "hustler",
    "entrepreneur",
    "overextended",
    "recovery_mode",
    "career_builder",
    "high_risk_operator",
}


class PlayerStrategyError(Exception):
    """Base strategy service exception."""


class PlayerStrategyNotFoundError(PlayerStrategyError):
    """Raised when the target player cannot be found."""


class PlayerStrategyValidationError(PlayerStrategyError):
    """Raised for invalid classification requests."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise PlayerStrategyNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise PlayerStrategyNotFoundError("Player not found.")
    return player


def _resolve_end_day(db: Session, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        day = int((as_of_date - GAME_EPOCH).days) + 1
        if day <= 0:
            raise PlayerStrategyValidationError("as_of_date must be on or after game epoch.")
        return day, as_of_date

    latest_day = db.query(func.max(DailySettlementLog.day_number)).scalar()
    if latest_day is None:
        return 1, GAME_EPOCH
    day_int = int(latest_day)
    return day_int, GAME_EPOCH + timedelta(days=max(0, day_int - 1))


def classify_player_strategy(
    db: Session,
    player_id: str | UUID,
    *,
    as_of_date: date | None = None,
    lookback_days: int = 7,
) -> dict:
    """Classify a player's current strategy path from recent real state."""
    if int(lookback_days) <= 0:
        raise PlayerStrategyValidationError("lookback_days must be greater than 0.")

    player = _resolve_player(db, player_id)
    end_day, resolved_date = _resolve_end_day(db, as_of_date=as_of_date)
    start_day = max(1, end_day - int(lookback_days) + 1)

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
    daily_states = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number >= start_day,
            PlayerDailyState.day_number <= end_day,
        )
        .order_by(PlayerDailyState.day_number.asc(), PlayerDailyState.created_at.asc())
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

    job_income = Decimal("0.00")
    side_income = Decimal("0.00")
    business_income = Decimal("0.00")
    for row in settlements:
        side = _d(getattr(row, "side_income_net_xgp", 0))
        biz = _d(getattr(row, "business_net_profit_xgp", 0))
        gross_income = _d(getattr(row, "income_xgp", 0))
        inferred_job = max(Decimal("0.00"), gross_income - max(Decimal("0.00"), side) - max(Decimal("0.00"), biz))
        job_income += inferred_job
        side_income += side
        business_income += biz

    total_income = job_income + side_income + business_income
    total_income = max(total_income, Decimal("0.01"))
    job_income_share = _q4(job_income / total_income)
    side_income_share = _q4(side_income / total_income)
    business_income_share = _q4(business_income / total_income)

    side_income_hours = sum((_d(getattr(row, "side_income_hours", 0)) for row in daily_states), Decimal("0"))
    business_hours = sum((_d(getattr(row, "business_hours", 0)) for row in daily_states), Decimal("0"))
    job_hours = sum(
        (
            _d(getattr(row, "job_hours", 0))
            if _d(getattr(row, "job_hours", 0)) > Decimal("0")
            else _d(getattr(row, "worked_hours", 0))
            for row in daily_states
        ),
        Decimal("0"),
    )
    overtime_hours = sum((_d(getattr(row, "overtime_hours", 0)) for row in daily_states), Decimal("0"))
    avg_overtime = _q4(overtime_hours / Decimal(str(max(1, len(daily_states)))))

    avg_stress = _q4(
        sum((_d(getattr(row, "stress_after", getattr(row, "stress_before", player.stress))) for row in settlements), Decimal("0"))
        / Decimal(str(max(1, len(settlements))))
    )
    avg_health = _q4(
        sum((_d(getattr(row, "health_after", getattr(row, "health_before", player.health))) for row in settlements), Decimal("0"))
        / Decimal(str(max(1, len(settlements))))
    )
    avg_distress = _q4(
        sum((_d(getattr(row, "distress_score_after", 0)) for row in distress_logs), Decimal("0"))
        / Decimal(str(max(1, len(distress_logs))))
    ) if distress_logs else _q4(_d(getattr(player, "distress_score", 0)))
    missed_payments = sum(1 for row in distress_logs if bool(getattr(row, "debt_payment_missed", False)))
    training_hours = sum((_d(getattr(row, "training_hours", 0)) for row in career_logs), Decimal("0"))

    classification = "stable_worker"
    if avg_distress >= Decimal("75") or missed_payments >= 3:
        classification = "recovery_mode"
    elif avg_stress >= Decimal("78") and avg_overtime >= Decimal("2.5"):
        classification = "overextended"
    elif business_income_share >= Decimal("0.45") and avg_distress >= Decimal("45"):
        classification = "high_risk_operator"
    elif business_income_share >= Decimal("0.45"):
        classification = "entrepreneur"
    elif side_income_hours >= (job_hours * Decimal("0.75")) and side_income_share >= Decimal("0.30"):
        classification = "hustler"
    elif training_hours >= Decimal("3.0") and job_income_share >= Decimal("0.45") and avg_distress < Decimal("55"):
        classification = "career_builder"

    if classification not in STRATEGY_CLASSES:
        classification = "stable_worker"

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "strategy_classification": classification,
        "classification_drivers": {
            "job_income_share": float(job_income_share),
            "side_income_share": float(side_income_share),
            "business_income_share": float(business_income_share),
            "job_hours": float(_q4(job_hours)),
            "side_income_hours": float(_q4(side_income_hours)),
            "business_hours": float(_q4(business_hours)),
            "avg_overtime_hours": float(avg_overtime),
            "avg_stress": float(avg_stress),
            "avg_health": float(avg_health),
            "avg_distress": float(avg_distress),
            "missed_payments": int(missed_payments),
            "training_hours": float(_q4(training_hours)),
        },
        "debug_meta": {
            "window": {"start_day": int(start_day), "end_day": int(end_day)},
            "rows": {
                "settlements": int(len(settlements)),
                "daily_states": int(len(daily_states)),
                "distress_logs": int(len(distress_logs)),
                "career_logs": int(len(career_logs)),
            },
        },
    }
