"""Step 36 credit, delinquency, and financial survival service."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.business_daily_log import BusinessDailyLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_delinquency_state import PlayerDelinquencyState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_housing_state import PlayerHousingState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState

GAME_EPOCH = date(2026, 1, 1)
MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

CREDIT_MIN = 300
CREDIT_MAX = 850

DELINQUENCY_STAGES: tuple[str, ...] = ("current", "stretched", "late", "delinquent", "critical")
STAGE_INDEX = {stage: idx for idx, stage in enumerate(DELINQUENCY_STAGES)}

SURVIVAL_LABEL_BY_STAGE = {
    "current": "current",
    "stretched": "stretched",
    "late": "slipping",
    "delinquent": "delinquent",
    "critical": "critical",
}

PRACTICAL_ACTIONS = [
    "Cut optional spending until obligations stabilize.",
    "Hold more cash buffer before non-essential upgrades.",
    "Pay required obligations first and delay risky expansion.",
    "Avoid risky inventory increases while payment pressure is elevated.",
    "Take extra work only if health and stress can support it.",
    "Reduce commute/housing burden if travel stress keeps compounding.",
]


class FinancialSurvivalError(Exception):
    """Base exception for Step 36 survival logic."""


class FinancialSurvivalNotFoundError(FinancialSurvivalError):
    """Raised when player/resources are missing."""


class FinancialSurvivalValidationError(FinancialSurvivalError):
    """Raised for invalid day/date arguments."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _safe_json(raw: str | None, default):
    if not raw:
        return default
    try:
        payload = json.loads(raw)
    except Exception:
        return default
    return payload if isinstance(payload, type(default)) else default


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise FinancialSurvivalNotFoundError("Player not found.") from exc

    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise FinancialSurvivalNotFoundError("Player not found.")
    return row


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise FinancialSurvivalValidationError("as_of_date must be on or after game epoch.")
    return day


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise FinancialSurvivalValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _resolve_day(
    db: Session,
    player: Player,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> tuple[int, date]:
    if day_number is not None:
        return int(day_number), _day_to_date(int(day_number))
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date

    from app.services.daily_settlement_service import get_next_player_day

    day = int(get_next_player_day(db, player.id))
    return day, _day_to_date(day)


def _latest_employment(db: Session, player_id: UUID, day: int) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player_id,
            PlayerEmploymentState.day <= int(day),
        )
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _latest_housing_state(db: Session, player_id: UUID) -> PlayerHousingState | None:
    return (
        db.query(PlayerHousingState)
        .filter(
            PlayerHousingState.player_id == player_id,
            PlayerHousingState.active_flag.is_(True),
        )
        .order_by(PlayerHousingState.updated_at.desc(), PlayerHousingState.created_at.desc())
        .first()
    )


def _active_businesses(db: Session, player_id: UUID) -> list[PlayerBusiness]:
    return (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player_id,
            PlayerBusiness.is_active.is_(True),
        )
        .order_by(PlayerBusiness.created_at.asc())
        .all()
    )


def _active_loans(db: Session, player_id: UUID) -> list[PlayerLoanAccount]:
    try:
        return (
            db.query(PlayerLoanAccount)
            .filter(
                PlayerLoanAccount.player_id == player_id,
                PlayerLoanAccount.status.in_(["active", "delinquent"]),
            )
            .order_by(PlayerLoanAccount.accepted_on_day.asc(), PlayerLoanAccount.created_at.asc())
            .all()
        )
    except Exception:
        # Loan table may be absent in isolated legacy test schemas.
        return []


def _recent_business_logs(db: Session, player_id: UUID, day: int, window_days: int = 7) -> list[BusinessDailyLog]:
    start_day = max(1, int(day) - max(1, int(window_days)) + 1)
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player_id,
            BusinessDailyLog.day >= start_day,
            BusinessDailyLog.day <= int(day),
        )
        .order_by(BusinessDailyLog.day.asc(), BusinessDailyLog.created_at.asc())
        .all()
    )


def _recent_payment_rows(db: Session, player_id: UUID, day: int, window_days: int = 30) -> list[PlayerPaymentHistory]:
    start_day = max(1, int(day) - max(1, int(window_days)) + 1)
    return (
        db.query(PlayerPaymentHistory)
        .filter(
            PlayerPaymentHistory.player_id == player_id,
            PlayerPaymentHistory.day_number >= start_day,
            PlayerPaymentHistory.day_number <= int(day),
        )
        .order_by(PlayerPaymentHistory.day_number.asc(), PlayerPaymentHistory.created_at.asc())
        .all()
    )


def _latest_payment_row(db: Session, player_id: UUID, day: int | None = None) -> PlayerPaymentHistory | None:
    q = db.query(PlayerPaymentHistory).filter(PlayerPaymentHistory.player_id == player_id)
    if day is not None:
        q = q.filter(PlayerPaymentHistory.day_number <= int(day))
    return q.order_by(PlayerPaymentHistory.day_number.desc(), PlayerPaymentHistory.created_at.desc()).first()


def _existing_payment_row_for_day(db: Session, player_id: UUID, day: int) -> PlayerPaymentHistory | None:
    return (
        db.query(PlayerPaymentHistory)
        .filter(
            PlayerPaymentHistory.player_id == player_id,
            PlayerPaymentHistory.day_number == int(day),
        )
        .first()
    )


def _get_or_create_delinquency_state(db: Session, player_id: UUID) -> PlayerDelinquencyState:
    row = db.query(PlayerDelinquencyState).filter(PlayerDelinquencyState.player_id == player_id).first()
    if row is not None:
        return row
    row = PlayerDelinquencyState(player_id=player_id)
    db.add(row)
    db.flush()
    return row


def _stage_from_score(score: Decimal) -> str:
    value = _clamp(score, Decimal("0"), Decimal("100"))
    if value >= Decimal("82"):
        return "critical"
    if value >= Decimal("63"):
        return "delinquent"
    if value >= Decimal("43"):
        return "late"
    if value >= Decimal("23"):
        return "stretched"
    return "current"


def _payment_pressure_label(load_ratio: Decimal, liquidity_buffer_days: Decimal) -> str:
    load = _clamp(load_ratio, Decimal("0"), Decimal("6"))
    buffer_days = _clamp(liquidity_buffer_days, Decimal("0"), Decimal("60"))
    if load >= Decimal("1.80") or buffer_days <= Decimal("1.5"):
        return "critical"
    if load >= Decimal("1.25") or buffer_days <= Decimal("3.5"):
        return "high"
    if load >= Decimal("0.85") or buffer_days <= Decimal("7.0"):
        return "moderate"
    return "manageable"


def _liquidity_label(buffer_days: Decimal) -> str:
    value = _clamp(buffer_days, Decimal("0"), Decimal("365"))
    if value <= Decimal("1.5"):
        return "critical"
    if value <= Decimal("4.0"):
        return "thin"
    if value <= Decimal("10.0"):
        return "adequate"
    return "strong"


def _credit_pressure_label(credit_pressure_score: Decimal) -> str:
    value = _clamp(credit_pressure_score, Decimal("0"), Decimal("100"))
    if value >= Decimal("72"):
        return "high"
    if value >= Decimal("45"):
        return "moderate"
    return "low"


def _serialize_delinquency_state_row(row: PlayerDelinquencyState | None) -> dict:
    if row is None:
        return {
            "player_id": None,
            "current_delinquency_stage": "current",
            "missed_payment_count_30d": 0,
            "late_payment_count_30d": 0,
            "days_under_payment_stress": 0,
            "last_missed_obligation_type": None,
            "credit_pressure_score": 0.0,
            "financial_distress_score": 0.0,
            "last_updated_on": None,
            "last_updated_date": None,
            "debug_meta": {},
        }
    return {
        "player_id": str(row.player_id),
        "current_delinquency_stage": str(row.current_delinquency_stage or "current"),
        "missed_payment_count_30d": int(row.missed_payment_count_30d or 0),
        "late_payment_count_30d": int(row.late_payment_count_30d or 0),
        "days_under_payment_stress": int(row.days_under_payment_stress or 0),
        "last_missed_obligation_type": row.last_missed_obligation_type,
        "credit_pressure_score": float(_q4(_d(row.credit_pressure_score))),
        "financial_distress_score": float(_q4(_d(row.financial_distress_score))),
        "last_updated_on": int(row.last_updated_on) if row.last_updated_on is not None else None,
        "last_updated_date": row.last_updated_date.isoformat() if row.last_updated_date else None,
        "debug_meta": _safe_json(row.stage_debug_json, {}),
    }


def _serialize_payment_row(row: PlayerPaymentHistory | None) -> dict:
    if row is None:
        return {
            "player_id": None,
            "day_number": None,
            "as_of_date": None,
            "payment_outcome": "none",
            "total_due_xgp": 0.0,
            "total_paid_xgp": 0.0,
            "unpaid_amount_xgp": 0.0,
            "late_fee_xgp": 0.0,
            "credit_score_before": 650,
            "credit_score_after": 650,
            "credit_score_delta": 0,
            "delinquency_stage_before": "current",
            "delinquency_stage_after": "current",
            "survival_status_label": "current",
            "payment_pressure_label": "manageable",
            "full_pay_feasible": True,
            "partial_pay_feasible": True,
            "stress_impact_delta": 0.0,
            "required_daily_burden_xgp": 0.0,
            "obligation_load_ratio": 0.0,
            "liquidity_buffer_days": 0.0,
            "due_obligations": [],
            "practical_current_actions": [],
            "summary": {},
            "debug_meta": {},
        }
    return {
        "player_id": str(row.player_id),
        "day_number": int(row.day_number),
        "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
        "payment_outcome": str(row.payment_outcome or "paid_full"),
        "total_due_xgp": float(_money(_d(row.total_due_xgp))),
        "total_paid_xgp": float(_money(_d(row.total_paid_xgp))),
        "unpaid_amount_xgp": float(_money(_d(row.unpaid_amount_xgp))),
        "late_fee_xgp": float(_money(_d(row.late_fee_xgp))),
        "credit_score_before": int(row.credit_score_before or 650),
        "credit_score_after": int(row.credit_score_after or 650),
        "credit_score_delta": int(row.credit_score_delta or 0),
        "delinquency_stage_before": str(row.delinquency_stage_before or "current"),
        "delinquency_stage_after": str(row.delinquency_stage_after or "current"),
        "survival_status_label": str(row.survival_status_label or "current"),
        "payment_pressure_label": str(row.payment_pressure_label or "manageable"),
        "full_pay_feasible": bool(row.full_pay_feasible),
        "partial_pay_feasible": bool(row.partial_pay_feasible),
        "stress_impact_delta": float(_q4(_d(row.stress_impact_delta))),
        "required_daily_burden_xgp": float(_money(_d(row.required_daily_burden_xgp))),
        "obligation_load_ratio": float(_q4(_d(row.obligation_load_ratio))),
        "liquidity_buffer_days": float(_q4(_d(row.liquidity_buffer_days))),
        "due_obligations": _safe_json(row.due_obligations_json, []),
        "practical_current_actions": _safe_json(row.practical_actions_json, []),
        "summary": _safe_json(row.summary_json, {}),
        "debug_meta": _safe_json(row.debug_json, {}),
    }


def build_player_obligation_profile(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build required-obligation profile and payment pressure labels."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    housing = _latest_housing_state(db, player.id)
    employment = _latest_employment(db, player.id, day)
    business_logs = _recent_business_logs(db, player.id, day, 7)
    businesses = _active_businesses(db, player.id)
    loans = _active_loans(db, player.id)
    latest_distress = (
        db.query(FinancialDistressLog)
        .filter(
            FinancialDistressLog.player_id == player.id,
            FinancialDistressLog.day <= int(day),
        )
        .order_by(FinancialDistressLog.day.desc(), FinancialDistressLog.created_at.desc())
        .first()
    )

    region_key = str(getattr(housing, "region", None) or player.region or "suburban").strip().lower() or "suburban"
    housing_daily = _money(_d(getattr(housing, "monthly_housing_cost_xgp", 0)) / Decimal("30"))
    utilities_daily = _money(_d(getattr(housing, "monthly_utilities_cost_xgp", 0)) / Decimal("30"))

    debt_min = _money(_d(getattr(player, "required_daily_debt_payment_xgp", 0)))
    if debt_min <= Decimal("0") and _d(player.debt_xgp) > Decimal("0"):
        debt_min = _money(
            _clamp(
                _d(player.debt_xgp) * Decimal("0.0125"),
                Decimal("6.00"),
                Decimal("120.00"),
            )
        )

    if business_logs:
        business_overhead = _money(
            sum((_d(getattr(row, "overhead_cost_xgp", 0)) for row in business_logs), Decimal("0"))
            / Decimal(str(len(business_logs)))
        )
    elif businesses:
        business_overhead = _money(Decimal(str(len(businesses))) * Decimal("7.50"))
    else:
        business_overhead = Decimal("0.00")

    insurance_basic = _money(Decimal("7.00") if region_key == "downtown" else Decimal("5.00"))
    if _d(getattr(player, "distress_score", 0)) >= Decimal("70"):
        insurance_basic = _money(insurance_basic + Decimal("1.25"))

    loan_daily_obligation = _money(
        sum(
            (
                max(
                    _d(getattr(loan, "current_due_xgp", 0)),
                    _d(getattr(loan, "scheduled_daily_payment_xgp", 0)),
                )
                for loan in loans
            ),
            Decimal("0"),
        )
    )

    required_daily = _money(
        housing_daily + utilities_daily + debt_min + business_overhead + insurance_basic + loan_daily_obligation
    )
    required_monthly = _money(required_daily * Decimal("30"))

    monthly_income = _money(_d(getattr(employment, "monthly_pay_xgp", 0)))
    daily_income_proxy = _money(max(Decimal("1.00"), monthly_income / Decimal("30")))
    obligation_load_ratio = _q4(_clamp(required_daily / daily_income_proxy, Decimal("0.00"), Decimal("8.00")))

    liquidity_buffer_days = _q4(
        _clamp(
            _d(player.cash_xgp) / max(Decimal("1.00"), required_daily),
            Decimal("0.00"),
            Decimal("365.00"),
        )
    )
    payment_pressure_label = _payment_pressure_label(obligation_load_ratio, liquidity_buffer_days)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "required_monthly_obligation_xgp": float(required_monthly),
        "required_daily_burden_xgp": float(required_daily),
        "debt_minimum_obligation_xgp": float(debt_min),
        "housing_obligation_xgp": float(housing_daily + utilities_daily),
        "business_overhead_obligation_xgp": float(business_overhead),
        "loan_obligation_xgp": float(loan_daily_obligation),
        "insurance_basic_obligation_xgp": float(insurance_basic),
        "obligation_load_ratio": float(obligation_load_ratio),
        "liquidity_buffer_days": float(liquidity_buffer_days),
        "payment_pressure_label": payment_pressure_label,
        "last_updated_on": int(day),
        "debug_meta": {
            "region_key": region_key,
            "monthly_income_xgp": float(monthly_income),
            "daily_income_proxy_xgp": float(daily_income_proxy),
            "components": {
                "housing_daily_xgp": float(housing_daily),
                "utilities_daily_xgp": float(utilities_daily),
                "debt_minimum_xgp": float(debt_min),
                "business_overhead_xgp": float(business_overhead),
                "loan_obligation_xgp": float(loan_daily_obligation),
                "insurance_basic_xgp": float(insurance_basic),
            },
            "active_business_count": int(len(businesses)),
            "active_loan_count": int(len(loans)),
            "recent_business_logs_considered": int(len(business_logs)),
            "latest_distress_day": int(getattr(latest_distress, "day", 0) or 0),
        },
    }


def build_payment_risk_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build player-facing payment-risk and recommendation state."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    profile = build_player_obligation_profile(db, player.id, resolved_date, day)
    delinquency = build_delinquency_state(db, player.id, resolved_date, day)

    available_cash = _money(_d(player.cash_xgp))
    required_daily = _money(_d(profile["required_daily_burden_xgp"]))
    full_feasible = available_cash >= required_daily
    partial_feasible = available_cash >= _money(required_daily * Decimal("0.55"))

    stage = str(delinquency.get("current_delinquency_stage", "current"))
    stage_idx = int(STAGE_INDEX.get(stage, 0))

    if full_feasible:
        likely_stress = "manageable"
        recommendation = "Keep obligations current and rebuild buffer before taking new risk."
    elif partial_feasible:
        likely_stress = "elevated"
        recommendation = "Cover as much required burden as possible and cut optional spending."
    else:
        likely_stress = "high"
        recommendation = "Prioritize survival cash actions immediately to avoid delinquency escalation."

    late_fee_exposure = _money(
        _clamp(
            (required_daily * (Decimal("0.035") + (Decimal(str(stage_idx)) * Decimal("0.012")))),
            Decimal("0.50"),
            Decimal("35.00"),
        )
    )
    delinquency_exposure = (
        "critical"
        if stage in {"delinquent", "critical"}
        else "elevated"
        if stage in {"late", "stretched"}
        else "contained"
    )

    components = (profile.get("debug_meta") or {}).get("components") or {}
    due_obligations = [
        {"obligation_type": "housing", "amount_xgp": float(_money(_d(components.get("housing_daily_xgp", 0))))},
        {"obligation_type": "utilities", "amount_xgp": float(_money(_d(components.get("utilities_daily_xgp", 0))))},
        {"obligation_type": "debt_minimum", "amount_xgp": float(_money(_d(components.get("debt_minimum_xgp", 0))))},
        {"obligation_type": "business_overhead", "amount_xgp": float(_money(_d(components.get("business_overhead_xgp", 0))))},
        {"obligation_type": "loan_obligation", "amount_xgp": float(_money(_d(components.get("loan_obligation_xgp", 0))))},
        {"obligation_type": "insurance_basic", "amount_xgp": float(_money(_d(components.get("insurance_basic_xgp", 0))))},
    ]

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "due_obligations": due_obligations,
        "full_pay_feasible": bool(full_feasible),
        "partial_pay_feasible": bool(partial_feasible),
        "likely_stress_impact": likely_stress,
        "late_fee_exposure_xgp": float(late_fee_exposure),
        "delinquency_exposure": delinquency_exposure,
        "short_recommendation": recommendation,
        "debug_meta": {
            "available_cash_xgp": float(available_cash),
            "required_daily_burden_xgp": float(required_daily),
            "obligation_load_ratio": float(profile.get("obligation_load_ratio", 0.0)),
            "liquidity_buffer_days": float(profile.get("liquidity_buffer_days", 0.0)),
            "payment_pressure_label": profile.get("payment_pressure_label", "manageable"),
            "current_delinquency_stage": stage,
        },
    }


def evaluate_due_obligations(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    available_cash_xgp: Decimal | float | int | None = None,
    debt_payment_due_xgp: Decimal | float | int | None = None,
    debt_payment_paid_xgp: Decimal | float | int | None = None,
    housing_paid_xgp: Decimal | float | int | None = None,
    utilities_paid_xgp: Decimal | float | int | None = None,
    business_overhead_paid_xgp: Decimal | float | int | None = None,
) -> dict:
    """Evaluate due obligations and deterministic payment feasibility for the day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    profile = build_player_obligation_profile(db, player.id, resolved_date, day)

    components = (profile.get("debug_meta") or {}).get("components") or {}
    housing_due = _money(_d(components.get("housing_daily_xgp", 0)))
    utilities_due = _money(_d(components.get("utilities_daily_xgp", 0)))
    debt_due = _money(_d(debt_payment_due_xgp if debt_payment_due_xgp is not None else components.get("debt_minimum_xgp", 0)))
    business_due = _money(_d(components.get("business_overhead_xgp", 0)))
    loan_due = _money(_d(components.get("loan_obligation_xgp", 0)))
    insurance_due = _money(_d(components.get("insurance_basic_xgp", 0)))

    total_due = _money(housing_due + utilities_due + debt_due + business_due + loan_due + insurance_due)
    available_cash = _money(_d(available_cash_xgp if available_cash_xgp is not None else player.cash_xgp))

    housing_paid = _money(_d(housing_paid_xgp if housing_paid_xgp is not None else housing_due))
    utilities_paid = _money(_d(utilities_paid_xgp if utilities_paid_xgp is not None else utilities_due))
    debt_paid = _money(_d(debt_payment_paid_xgp if debt_payment_paid_xgp is not None else debt_due))
    business_paid = _money(_d(business_overhead_paid_xgp if business_overhead_paid_xgp is not None else business_due))
    loan_paid = _money(min(loan_due, max(Decimal("0.00"), available_cash - (housing_paid + utilities_paid + debt_paid + business_paid))))

    covered_known = _money(
        min(housing_due, housing_paid)
        + min(utilities_due, utilities_paid)
        + min(debt_due, debt_paid)
        + min(business_due, business_paid)
        + min(loan_due, loan_paid)
    )

    remaining_cash_after_known = _money(max(Decimal("0.00"), available_cash - covered_known))
    insurance_paid = _money(min(insurance_due, remaining_cash_after_known))
    total_paid = _money(min(total_due, covered_known + insurance_paid))
    unpaid_amount = _money(max(Decimal("0.00"), total_due - total_paid))

    full_feasible = bool(available_cash >= total_due)
    partial_feasible = bool(available_cash >= _money(total_due * Decimal("0.55")))
    coverage_ratio = _q4(_clamp(total_paid / max(Decimal("1.00"), total_due), Decimal("0.00"), Decimal("1.10")))

    if coverage_ratio >= Decimal("0.98"):
        payment_outcome = "paid_full"
    elif coverage_ratio >= Decimal("0.70"):
        payment_outcome = "paid_partial"
    elif coverage_ratio >= Decimal("0.45"):
        payment_outcome = "delayed"
    else:
        payment_outcome = "missed"

    stage = str(build_delinquency_state(db, player.id, resolved_date, day).get("current_delinquency_stage", "current"))
    stage_idx = int(STAGE_INDEX.get(stage, 0))
    late_fee_exposure = _money(
        _clamp(
            total_due * (Decimal("0.018") + (Decimal(str(stage_idx)) * Decimal("0.011"))),
            Decimal("0.00"),
            Decimal("35.00"),
        )
    )

    likely_stress_impact = (
        "manageable"
        if payment_outcome == "paid_full"
        else "elevated"
        if payment_outcome == "paid_partial"
        else "high"
        if payment_outcome == "delayed"
        else "severe"
    )
    delinquency_exposure = (
        "contained"
        if stage == "current"
        else "elevated"
        if stage in {"stretched", "late"}
        else "high"
    )
    recommendation = (
        "Stay current and rebuild buffer."
        if payment_outcome == "paid_full"
        else "Cover required obligations first and defer optional spend."
        if payment_outcome == "paid_partial"
        else "Stabilize cash immediately to prevent credit damage."
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "due_obligations": [
            {"obligation_type": "housing", "amount_xgp": float(housing_due), "paid_xgp": float(min(housing_due, housing_paid))},
            {"obligation_type": "utilities", "amount_xgp": float(utilities_due), "paid_xgp": float(min(utilities_due, utilities_paid))},
            {"obligation_type": "debt_minimum", "amount_xgp": float(debt_due), "paid_xgp": float(min(debt_due, debt_paid))},
            {"obligation_type": "business_overhead", "amount_xgp": float(business_due), "paid_xgp": float(min(business_due, business_paid))},
            {"obligation_type": "loan_obligation", "amount_xgp": float(loan_due), "paid_xgp": float(min(loan_due, loan_paid))},
            {"obligation_type": "insurance_basic", "amount_xgp": float(insurance_due), "paid_xgp": float(insurance_paid)},
        ],
        "full_pay_feasible": bool(full_feasible),
        "partial_pay_feasible": bool(partial_feasible),
        "likely_stress_impact": likely_stress_impact,
        "late_fee_exposure_xgp": float(late_fee_exposure),
        "delinquency_exposure": delinquency_exposure,
        "short_recommendation": recommendation,
        "total_due_xgp": float(total_due),
        "total_paid_xgp": float(total_paid),
        "unpaid_amount_xgp": float(unpaid_amount),
        "coverage_ratio": float(coverage_ratio),
        "payment_outcome": payment_outcome,
        "insurance_basic_paid_xgp": float(insurance_paid),
        "debug_meta": {
            "available_cash_xgp": float(available_cash),
            "covered_known_xgp": float(covered_known),
            "remaining_cash_after_known_xgp": float(remaining_cash_after_known),
            "obligation_profile": profile,
        },
    }


def build_credit_impact_summary(
    *,
    credit_score_before: int,
    credit_score_after: int,
    credit_delta: int,
    payment_outcome: str,
    delinquency_stage_after: str,
) -> dict:
    """Build bounded player-facing credit impact summary."""
    before = _clamp_int(int(credit_score_before or 650), CREDIT_MIN, CREDIT_MAX)
    after = _clamp_int(int(credit_score_after or before), CREDIT_MIN, CREDIT_MAX)
    delta = int(credit_delta or 0)
    outcome = str(payment_outcome or "paid_full")
    stage = str(delinquency_stage_after or "current")

    if outcome == "paid_full" and delta > 0:
        impact_label = "improving"
        primary_driver = "On-time obligation coverage"
    elif outcome == "missed":
        impact_label = "negative"
        primary_driver = "Missed required obligations"
    elif outcome in {"delayed", "paid_partial"}:
        impact_label = "pressured"
        primary_driver = "Late/partial required obligation coverage"
    else:
        impact_label = "flat"
        primary_driver = "Mixed payment signals"

    future_pressure = (
        "high"
        if after < 560 or stage in {"delinquent", "critical"}
        else "moderate"
        if after < 650 or stage in {"late", "stretched"}
        else "low"
    )
    summary = (
        "Credit pressure is rising; prioritize current obligations."
        if delta < 0
        else "Credit is stabilizing, but recovery remains gradual."
        if delta > 0
        else "Credit held roughly flat today."
    )
    return {
        "credit_score_before": int(before),
        "credit_score_after": int(after),
        "credit_delta": int(delta),
        "impact_label": impact_label,
        "primary_driver": primary_driver,
        "future_borrowing_pressure_label": future_pressure,
        "short_summary": summary,
        "debug_meta": {
            "payment_outcome": outcome,
            "delinquency_stage_after": stage,
        },
    }


def _compute_credit_delta(
    *,
    payment_outcome: str,
    missed_payment_count_30d: int,
    late_payment_count_30d: int,
    obligation_load_ratio: Decimal,
    liquidity_buffer_days: Decimal,
    stage_before: str,
) -> int:
    outcome = str(payment_outcome or "paid_full")
    missed_30d = int(max(0, missed_payment_count_30d))
    late_30d = int(max(0, late_payment_count_30d))
    load_ratio = _clamp(_d(obligation_load_ratio), Decimal("0.00"), Decimal("8.00"))
    buffer_days = _clamp(_d(liquidity_buffer_days), Decimal("0.00"), Decimal("365.00"))
    stage_idx = int(STAGE_INDEX.get(str(stage_before or "current"), 0))

    if outcome == "paid_full":
        delta = 1 if missed_30d == 0 and late_30d <= 1 else 0
    elif outcome == "paid_partial":
        delta = -2
    elif outcome == "delayed":
        delta = -3
    else:
        delta = -6

    if outcome != "paid_full":
        if missed_30d >= 3:
            delta -= 2
        elif missed_30d >= 1:
            delta -= 1
        if late_30d >= 5:
            delta -= 1
        if load_ratio >= Decimal("1.35"):
            delta -= 1
        if buffer_days <= Decimal("2.0"):
            delta -= 1
    else:
        if stage_idx >= 2:
            delta = min(delta, 0)

    return _clamp_int(int(delta), -10, 2)


def _compute_distress_score(
    *,
    missed_payment_count_30d: int,
    late_payment_count_30d: int,
    days_under_payment_stress: int,
    obligation_load_ratio: Decimal,
    liquidity_buffer_days: Decimal,
    credit_score_after: int,
    shock_risk_score: Decimal,
) -> tuple[Decimal, Decimal]:
    missed_30d = int(max(0, missed_payment_count_30d))
    late_30d = int(max(0, late_payment_count_30d))
    days_stress = int(max(0, days_under_payment_stress))
    load_ratio = _clamp(_d(obligation_load_ratio), Decimal("0.00"), Decimal("8.00"))
    buffer_days = _clamp(_d(liquidity_buffer_days), Decimal("0.00"), Decimal("365.00"))
    credit_after = _clamp_int(int(credit_score_after or 650), CREDIT_MIN, CREDIT_MAX)
    shock_score = _clamp(_d(shock_risk_score), Decimal("0.00"), Decimal("100.00"))

    load_component = _clamp((load_ratio - Decimal("0.80")) / Decimal("1.20"), Decimal("0.00"), Decimal("1.00"))
    liquidity_component = _clamp((Decimal("4.00") - buffer_days) / Decimal("4.00"), Decimal("0.00"), Decimal("1.00"))
    credit_component = _clamp((Decimal("640.00") - Decimal(str(credit_after))) / Decimal("340.00"), Decimal("0.00"), Decimal("1.00"))

    distress_score = _clamp(
        Decimal(str(missed_30d)) * Decimal("18.0")
        + Decimal(str(late_30d)) * Decimal("9.0")
        + Decimal(str(days_stress)) * Decimal("1.8")
        + load_component * Decimal("22.0")
        + liquidity_component * Decimal("20.0")
        + credit_component * Decimal("16.0")
        + _clamp(shock_score / Decimal("100.0"), Decimal("0"), Decimal("1")) * Decimal("8.0"),
        Decimal("0.00"),
        Decimal("100.00"),
    )
    credit_pressure_score = _clamp(
        (credit_component * Decimal("100.0")) + (Decimal(str(missed_30d)) * Decimal("2.5")),
        Decimal("0.00"),
        Decimal("100.00"),
    )
    return _q4(distress_score), _q4(credit_pressure_score)


def _choose_stage_after(
    *,
    stage_before: str,
    target_stage: str,
    payment_outcome: str,
    missed_payment_count_30d: int,
    late_payment_count_30d: int,
) -> str:
    before = str(stage_before or "current")
    target = str(target_stage or "current")
    before_idx = int(STAGE_INDEX.get(before, 0))
    target_idx = int(STAGE_INDEX.get(target, 0))
    outcome = str(payment_outcome or "paid_full")

    if target_idx > before_idx:
        return DELINQUENCY_STAGES[min(before_idx + 1, target_idx)]
    if target_idx < before_idx:
        if outcome == "paid_full" and int(missed_payment_count_30d) == 0 and int(late_payment_count_30d) <= max(1, before_idx - 1):
            return DELINQUENCY_STAGES[max(before_idx - 1, target_idx)]
        return DELINQUENCY_STAGES[before_idx]
    return DELINQUENCY_STAGES[before_idx]


def _practical_actions(
    *,
    stage: str,
    payment_outcome: str,
    pressure_label: str,
    liquidity_buffer_days: Decimal,
) -> list[str]:
    actions = list(PRACTICAL_ACTIONS)
    if str(stage) in {"delinquent", "critical"}:
        actions.insert(0, "Pause non-essential growth until payment performance stabilizes.")
    if str(payment_outcome) in {"missed", "delayed"}:
        actions.insert(0, "Repair payment consistency first to stop credit deterioration.")
    if str(pressure_label) in {"high", "critical"} or _d(liquidity_buffer_days) <= Decimal("2.0"):
        actions.insert(0, "Prioritize required obligations before optional spending this week.")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in actions:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:6]


def apply_payment_outcomes(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    available_cash_xgp: Decimal | float | int | None = None,
    debt_payment_due_xgp: Decimal | float | int | None = None,
    debt_payment_paid_xgp: Decimal | float | int | None = None,
    housing_paid_xgp: Decimal | float | int | None = None,
    utilities_paid_xgp: Decimal | float | int | None = None,
    business_overhead_paid_xgp: Decimal | float | int | None = None,
    apply_stress_to_player: bool = True,
) -> dict:
    """Apply deterministic daily payment outcomes and persist Step 36 state."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    existing = _existing_payment_row_for_day(db, player.id, day)
    if existing is not None:
        payload = _serialize_payment_row(existing)
        payload["already_processed"] = True
        return payload

    profile = build_player_obligation_profile(db, player.id, resolved_date, day)
    evaluation = evaluate_due_obligations(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        available_cash_xgp=available_cash_xgp,
        debt_payment_due_xgp=debt_payment_due_xgp,
        debt_payment_paid_xgp=debt_payment_paid_xgp,
        housing_paid_xgp=housing_paid_xgp,
        utilities_paid_xgp=utilities_paid_xgp,
        business_overhead_paid_xgp=business_overhead_paid_xgp,
    )
    delinquency_state = _get_or_create_delinquency_state(db, player.id)
    stage_before = str(delinquency_state.current_delinquency_stage or "current")

    recent_rows = _recent_payment_rows(db, player.id, day - 1, 29)
    historical_missed = sum(1 for row in recent_rows if str(row.payment_outcome) == "missed")
    historical_late = sum(1 for row in recent_rows if str(row.payment_outcome) in {"paid_partial", "delayed"})
    outcome = str(evaluation["payment_outcome"])
    missed_30d = historical_missed + (1 if outcome == "missed" else 0)
    late_30d = historical_late + (1 if outcome in {"paid_partial", "delayed"} else 0)

    load_ratio = _d(profile["obligation_load_ratio"])
    liquidity_buffer_days = _d(profile["liquidity_buffer_days"])
    stress_days_before = int(delinquency_state.days_under_payment_stress or 0)
    under_stress_today = bool(load_ratio >= Decimal("1.00") or outcome != "paid_full")
    days_under_stress = (stress_days_before + 1) if under_stress_today else max(0, stress_days_before - 1)

    stage_idx = int(STAGE_INDEX.get(stage_before, 0))
    due_total = _money(_d(evaluation["total_due_xgp"]))
    debt_due_for_split = _money(
        _d(
            next(
                (
                    item.get("amount_xgp", 0.0)
                    for item in evaluation.get("due_obligations", [])
                    if str(item.get("obligation_type")) == "debt_minimum"
                ),
                0.0,
            )
        )
    )
    non_debt_due_for_split = _money(max(Decimal("0.00"), due_total - debt_due_for_split))
    if outcome == "paid_full":
        late_fee = Decimal("0.00")
        stress_delta = Decimal("0.20") if profile["payment_pressure_label"] in {"high", "critical"} else Decimal("0.00")
        missed_type = None
    elif outcome == "paid_partial":
        late_fee = _money(_clamp((due_total * Decimal("0.025")) + (Decimal(str(stage_idx)) * Decimal("1.10")), Decimal("1.00"), Decimal("18.00")))
        stress_delta = Decimal("1.40") + (Decimal(str(stage_idx)) * Decimal("0.30"))
        missed_type = "partial_required"
    elif outcome == "delayed":
        late_fee = _money(_clamp((due_total * Decimal("0.045")) + (Decimal(str(stage_idx)) * Decimal("1.75")), Decimal("2.00"), Decimal("25.00")))
        stress_delta = Decimal("2.60") + (Decimal(str(stage_idx)) * Decimal("0.40"))
        missed_type = "delayed_required"
    else:
        late_fee = _money(_clamp((due_total * Decimal("0.070")) + (Decimal(str(stage_idx)) * Decimal("2.50")), Decimal("3.50"), Decimal("35.00")))
        stress_delta = Decimal("4.20") + (Decimal(str(stage_idx)) * Decimal("0.55"))
        missed_type = "missed_required"
    if outcome in {"delayed", "missed"}:
        late_fee = _money(
            _clamp(
                late_fee + (Decimal(str(missed_30d)) * Decimal("0.55")),
                Decimal("0.00"),
                Decimal("35.00"),
            )
        )
    stress_delta = _q4(_clamp(stress_delta, Decimal("0.00"), Decimal("8.00")))

    late_fee_non_debt = _money(
        _clamp(
            late_fee * (non_debt_due_for_split / max(Decimal("1.00"), due_total)),
            Decimal("0.00"),
            late_fee,
        )
    )
    late_fee_debt_component = _money(max(Decimal("0.00"), late_fee - late_fee_non_debt))

    credit_before = _clamp_int(int(player.credit_score or 650), CREDIT_MIN, CREDIT_MAX)
    credit_delta = _compute_credit_delta(
        payment_outcome=outcome,
        missed_payment_count_30d=missed_30d,
        late_payment_count_30d=late_30d,
        obligation_load_ratio=load_ratio,
        liquidity_buffer_days=liquidity_buffer_days,
        stage_before=stage_before,
    )
    credit_after = _clamp_int(credit_before + int(credit_delta), CREDIT_MIN, CREDIT_MAX)

    shock_state = db.query(PlayerShockState).filter(PlayerShockState.player_id == player.id).first()
    shock_risk_score = _d(getattr(shock_state, "shock_risk_score", 0))
    distress_score, credit_pressure_score = _compute_distress_score(
        missed_payment_count_30d=missed_30d,
        late_payment_count_30d=late_30d,
        days_under_payment_stress=days_under_stress,
        obligation_load_ratio=load_ratio,
        liquidity_buffer_days=liquidity_buffer_days,
        credit_score_after=credit_after,
        shock_risk_score=shock_risk_score,
    )

    target_stage = _stage_from_score(distress_score)
    stage_after = _choose_stage_after(
        stage_before=stage_before,
        target_stage=target_stage,
        payment_outcome=outcome,
        missed_payment_count_30d=missed_30d,
        late_payment_count_30d=late_30d,
    )

    survival_status_label = SURVIVAL_LABEL_BY_STAGE.get(stage_after, "current")
    practical_actions = _practical_actions(
        stage=stage_after,
        payment_outcome=outcome,
        pressure_label=str(profile["payment_pressure_label"]),
        liquidity_buffer_days=liquidity_buffer_days,
    )

    credit_impact = build_credit_impact_summary(
        credit_score_before=credit_before,
        credit_score_after=credit_after,
        credit_delta=credit_delta,
        payment_outcome=outcome,
        delinquency_stage_after=stage_after,
    )

    delinquency_state.current_delinquency_stage = stage_after
    delinquency_state.missed_payment_count_30d = int(missed_30d)
    delinquency_state.late_payment_count_30d = int(late_30d)
    delinquency_state.days_under_payment_stress = int(days_under_stress)
    delinquency_state.last_missed_obligation_type = missed_type
    delinquency_state.credit_pressure_score = _q4(credit_pressure_score)
    delinquency_state.financial_distress_score = _q4(distress_score)
    delinquency_state.last_updated_on = int(day)
    delinquency_state.last_updated_date = resolved_date
    delinquency_state.stage_debug_json = _dump_json(
        {
            "stage_before": stage_before,
            "target_stage": target_stage,
            "stage_after": stage_after,
            "score_inputs": {
                "missed_payment_count_30d": int(missed_30d),
                "late_payment_count_30d": int(late_30d),
                "days_under_payment_stress": int(days_under_stress),
                "obligation_load_ratio": float(_q4(load_ratio)),
                "liquidity_buffer_days": float(_q4(liquidity_buffer_days)),
                "shock_risk_score": float(_q4(shock_risk_score)),
            },
            "distress_score": float(_q4(distress_score)),
            "credit_pressure_score": float(_q4(credit_pressure_score)),
        }
    )

    additional_required_paid = _money(_d(evaluation.get("insurance_basic_paid_xgp", 0)))
    payment_row = PlayerPaymentHistory(
        player_id=player.id,
        day_number=int(day),
        as_of_date=resolved_date,
        required_monthly_obligation_xgp=_money(_d(profile["required_monthly_obligation_xgp"])),
        required_daily_burden_xgp=_money(_d(profile["required_daily_burden_xgp"])),
        debt_minimum_obligation_xgp=_money(_d(profile["debt_minimum_obligation_xgp"])),
        housing_obligation_xgp=_money(_d(profile["housing_obligation_xgp"])),
        business_overhead_obligation_xgp=_money(_d(profile["business_overhead_obligation_xgp"])),
        insurance_basic_obligation_xgp=_money(_d(profile["insurance_basic_obligation_xgp"])),
        obligation_load_ratio=_q4(_d(profile["obligation_load_ratio"])),
        liquidity_buffer_days=_q4(_d(profile["liquidity_buffer_days"])),
        payment_pressure_label=str(profile["payment_pressure_label"]),
        full_pay_feasible=bool(evaluation["full_pay_feasible"]),
        partial_pay_feasible=bool(evaluation["partial_pay_feasible"]),
        payment_outcome=outcome,
        total_due_xgp=_money(_d(evaluation["total_due_xgp"])),
        total_paid_xgp=_money(_d(evaluation["total_paid_xgp"])),
        unpaid_amount_xgp=_money(_d(evaluation["unpaid_amount_xgp"])),
        late_fee_xgp=late_fee,
        stress_impact_delta=stress_delta,
        delinquency_stage_before=stage_before,
        delinquency_stage_after=stage_after,
        credit_score_before=int(credit_before),
        credit_score_after=int(credit_after),
        credit_score_delta=int(credit_delta),
        survival_status_label=survival_status_label,
        due_obligations_json=_dump_json(evaluation.get("due_obligations", [])),
        practical_actions_json=_dump_json(practical_actions),
        summary_json=_dump_json(
            {
                "payment_pressure_label": profile["payment_pressure_label"],
                "liquidity_buffer_label": _liquidity_label(liquidity_buffer_days),
                "credit_pressure_label": _credit_pressure_label(credit_pressure_score),
                "credit_impact": credit_impact,
                "additional_required_paid_xgp": float(additional_required_paid),
            }
        ),
        debug_json=_dump_json(
            {
                "profile": profile,
                "evaluation": evaluation,
                "stress_days_before": int(stress_days_before),
                "stress_days_after": int(days_under_stress),
                "shock_risk_score": float(_q4(shock_risk_score)),
                "credit_impact": credit_impact,
            }
        ),
    )
    db.add(payment_row)
    db.flush()

    player.credit_score = int(credit_after)
    if apply_stress_to_player:
        player.stress = _clamp_int(
            int(round(float(_d(player.stress) + stress_delta))),
            0,
            100,
        )
    player.credit_debug_json = _dump_json(
        {
            "step36_day": int(day),
            "payment_outcome": outcome,
            "delinquency_stage_after": stage_after,
            "credit_impact": credit_impact,
            "late_fee_xgp": float(late_fee),
            "additional_required_paid_xgp": float(additional_required_paid),
        }
    )
    db.flush()

    payload = _serialize_payment_row(payment_row)
    payload.update(
        {
            "already_processed": False,
            "credit_impact_summary": credit_impact,
            "delinquency_state": _serialize_delinquency_state_row(delinquency_state),
            "obligation_profile": profile,
            "payment_risk_state": {
                "player_id": str(player.id),
                "as_of_date": resolved_date.isoformat(),
                "day_number": int(day),
                "due_obligations": evaluation.get("due_obligations", []),
                "full_pay_feasible": bool(evaluation["full_pay_feasible"]),
                "partial_pay_feasible": bool(evaluation["partial_pay_feasible"]),
                "likely_stress_impact": evaluation.get("likely_stress_impact", "manageable"),
                "late_fee_exposure_xgp": float(evaluation.get("late_fee_exposure_xgp", 0.0)),
                "delinquency_exposure": evaluation.get("delinquency_exposure", "contained"),
                "short_recommendation": evaluation.get("short_recommendation", ""),
                "debug_meta": evaluation.get("debug_meta", {}),
            },
            "late_fee_xgp": float(late_fee),
            "late_fee_non_debt_xgp": float(late_fee_non_debt),
            "late_fee_debt_component_xgp": float(late_fee_debt_component),
            "stress_impact_delta": float(stress_delta),
            "additional_required_paid_xgp": float(additional_required_paid),
            "credit_score_before": int(credit_before),
            "credit_score_after": int(credit_after),
            "credit_score_delta": int(credit_delta),
            "current_delinquency_stage": stage_after,
            "survival_status_label": survival_status_label,
            "liquidity_buffer_label": _liquidity_label(liquidity_buffer_days),
            "credit_pressure_label": _credit_pressure_label(credit_pressure_score),
            "payment_pressure_label": str(profile.get("payment_pressure_label", "manageable")),
            "practical_current_actions": practical_actions,
            "short_summary": (
                "Payment pressure is controlled today."
                if outcome == "paid_full"
                else "Payment pressure slipped today; stabilize obligations to prevent compounding damage."
            ),
            "debug_meta": {
                "profile": profile,
                "evaluation": evaluation,
                "credit_impact": credit_impact,
                "stage_before": stage_before,
                "stage_after": stage_after,
                "distress_score": float(distress_score),
                "credit_pressure_score": float(credit_pressure_score),
                "late_fee_non_debt_xgp": float(late_fee_non_debt),
                "late_fee_debt_component_xgp": float(late_fee_debt_component),
            },
        }
    )
    return payload


def apply_daily_financial_survival(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    available_cash_xgp: Decimal | float | int | None = None,
    debt_payment_due_xgp: Decimal | float | int | None = None,
    debt_payment_paid_xgp: Decimal | float | int | None = None,
    housing_paid_xgp: Decimal | float | int | None = None,
    utilities_paid_xgp: Decimal | float | int | None = None,
    business_overhead_paid_xgp: Decimal | float | int | None = None,
    apply_stress_to_player: bool = True,
) -> dict:
    """Main Step 36 orchestrator used by settlement/day lifecycle."""
    return apply_payment_outcomes(
        db=db,
        player_id=player_id,
        as_of_date=as_of_date,
        day_number=day_number,
        available_cash_xgp=available_cash_xgp,
        debt_payment_due_xgp=debt_payment_due_xgp,
        debt_payment_paid_xgp=debt_payment_paid_xgp,
        housing_paid_xgp=housing_paid_xgp,
        utilities_paid_xgp=utilities_paid_xgp,
        business_overhead_paid_xgp=business_overhead_paid_xgp,
        apply_stress_to_player=apply_stress_to_player,
    )


def build_delinquency_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Return deterministic delinquency stage + rolling counters for one player/day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    state = _get_or_create_delinquency_state(db, player.id)

    rows = _recent_payment_rows(db, player.id, day, 30)
    missed_30d = int(sum(1 for row in rows if str(getattr(row, "payment_outcome", "")) == "missed"))
    late_30d = int(
        sum(1 for row in rows if str(getattr(row, "payment_outcome", "")) in {"paid_partial", "delayed"})
    )
    stress_days = int(
        sum(
            1
            for row in rows
            if str(getattr(row, "payment_pressure_label", "")) in {"high", "critical"}
            or str(getattr(row, "payment_outcome", "")) != "paid_full"
        )
    )

    latest_row = _latest_payment_row(db, player.id, day)
    stage_from_rows = str(getattr(latest_row, "delinquency_stage_after", "") or "")
    if stage_from_rows in STAGE_INDEX:
        stage = stage_from_rows
    else:
        inferred_score = _clamp(
            Decimal(str(missed_30d)) * Decimal("18")
            + Decimal(str(late_30d)) * Decimal("8")
            + Decimal(str(stress_days)) * Decimal("1.4"),
            Decimal("0"),
            Decimal("100"),
        )
        stage = _stage_from_score(inferred_score)

    state.current_delinquency_stage = stage
    state.missed_payment_count_30d = int(max(0, missed_30d))
    state.late_payment_count_30d = int(max(0, late_30d))
    state.days_under_payment_stress = int(max(0, stress_days))
    if latest_row is not None and str(getattr(latest_row, "payment_outcome", "")) == "missed":
        state.last_missed_obligation_type = "required_obligation"
    state.last_updated_on = int(day)
    state.last_updated_date = resolved_date
    if not state.stage_debug_json:
        state.stage_debug_json = _dump_json({"source": "step36_init"})
    db.flush()

    payload = _serialize_delinquency_state_row(state)
    payload.update(
        {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "day_number": int(day),
            "survival_status_label": SURVIVAL_LABEL_BY_STAGE.get(stage, "current"),
            "credit_pressure_label": _credit_pressure_label(_d(state.credit_pressure_score)),
            "debug_meta": {
                **(payload.get("debug_meta") or {}),
                "window_days": 30,
                "rows_considered": len(rows),
                "stage_source": "payment_history" if stage_from_rows in STAGE_INDEX else "counter_inference",
            },
        }
    )
    return payload


def get_player_payment_history(
    db: Session,
    player_id: str | UUID,
    *,
    as_of_date: date | None = None,
    day_number: int | None = None,
    limit: int = 30,
) -> dict:
    """Return recent payment outcomes with trailing Step 36 diagnostics."""
    if int(limit) <= 0:
        raise FinancialSurvivalValidationError("limit must be greater than 0.")
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    rows = (
        db.query(PlayerPaymentHistory)
        .filter(
            PlayerPaymentHistory.player_id == player.id,
            PlayerPaymentHistory.day_number <= int(day),
        )
        .order_by(PlayerPaymentHistory.day_number.desc(), PlayerPaymentHistory.created_at.desc())
        .limit(int(limit))
        .all()
    )
    entries = [_serialize_payment_row(row) for row in rows]

    trailing = entries[:7]
    n = Decimal(str(max(1, len(trailing))))
    missed_7d = int(sum(1 for item in trailing if str(item.get("payment_outcome")) == "missed"))
    late_7d = int(
        sum(1 for item in trailing if str(item.get("payment_outcome")) in {"paid_partial", "delayed"})
    )
    avg_load = _q4(
        sum((Decimal(str(item.get("obligation_load_ratio", 0.0))) for item in trailing), Decimal("0")) / n
    )
    avg_liquidity = _q4(
        sum((Decimal(str(item.get("liquidity_buffer_days", 0.0))) for item in trailing), Decimal("0")) / n
    )
    credit_change = int(sum(int(item.get("credit_score_delta", 0)) for item in trailing))

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "entries": entries,
        "trailing_7d_missed_payments": int(missed_7d),
        "trailing_7d_late_payments": int(late_7d),
        "trailing_7d_avg_obligation_load_ratio": float(avg_load),
        "trailing_7d_avg_liquidity_buffer_days": float(avg_liquidity),
        "trailing_7d_credit_change": int(credit_change),
        "debug_meta": {
            "limit": int(limit),
            "rows_returned": len(entries),
            "latest_day_number": int(entries[0]["day_number"]) if entries else None,
        },
    }


def build_financial_survival_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Compose bounded player-facing financial survival status and practical actions."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    profile = build_player_obligation_profile(db, player.id, resolved_date, day)
    risk_state = build_payment_risk_state(db, player.id, resolved_date, day)
    delinquency = build_delinquency_state(db, player.id, resolved_date, day)
    latest = _latest_payment_row(db, player.id, day)
    latest_payload = _serialize_payment_row(latest)

    stage = str(delinquency.get("current_delinquency_stage", "current"))
    survival_status = SURVIVAL_LABEL_BY_STAGE.get(stage, "current")

    payment_pressure_label = str(profile.get("payment_pressure_label", "manageable"))
    liquidity_buffer_days = _d(profile.get("liquidity_buffer_days", 0))
    liquidity_buffer_label = _liquidity_label(liquidity_buffer_days)
    credit_pressure_label = _credit_pressure_label(_d(delinquency.get("credit_pressure_score", 0)))

    obligation_load = _d(profile.get("obligation_load_ratio", 0))
    missed_30d = int(delinquency.get("missed_payment_count_30d", 0) or 0)
    late_30d = int(delinquency.get("late_payment_count_30d", 0) or 0)

    if missed_30d >= 3:
        top_distress_driver = "Repeated missed required payments"
    elif payment_pressure_label in {"high", "critical"}:
        top_distress_driver = "Required obligation load is too high for current cash flow"
    elif liquidity_buffer_days <= Decimal("2.0"):
        top_distress_driver = "Liquidity buffer is too thin for routine obligations"
    elif late_30d >= 3:
        top_distress_driver = "Repeated late/partial payments are compounding pressure"
    else:
        top_distress_driver = "Variable weekly cash flow is creating obligation stress"

    outcome = str(latest_payload.get("payment_outcome", "paid_full"))
    if outcome == "paid_full" and liquidity_buffer_days >= Decimal("6"):
        top_stabilizer = "On-time payments with improving cash cushion"
    elif outcome == "paid_full":
        top_stabilizer = "Payment performance is currently on track"
    elif liquidity_buffer_days >= Decimal("4"):
        top_stabilizer = "Cash buffer still offers limited stabilization room"
    else:
        top_stabilizer = "Short-term income actions can still prevent escalation"

    practical_actions = _practical_actions(
        stage=stage,
        payment_outcome=outcome,
        pressure_label=payment_pressure_label,
        liquidity_buffer_days=liquidity_buffer_days,
    )

    if survival_status in {"delinquent", "critical"}:
        short_summary = "Financial survival is fragile; missed obligations are creating compounding pressure."
    elif survival_status in {"slipping", "stretched"}:
        short_summary = "Payment pressure is rising; disciplined obligation coverage is now the priority."
    else:
        short_summary = "Financial survival is stable if payment consistency and buffer discipline continue."

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "survival_status_label": survival_status,
        "payment_pressure_label": payment_pressure_label,
        "credit_pressure_label": credit_pressure_label,
        "liquidity_buffer_label": liquidity_buffer_label,
        "top_distress_driver": top_distress_driver,
        "top_stabilizer": top_stabilizer,
        "practical_current_actions": practical_actions,
        "short_summary": short_summary,
        "debug_meta": {
            "day_number": int(day),
            "obligation_load_ratio": float(_q4(obligation_load)),
            "liquidity_buffer_days": float(_q4(liquidity_buffer_days)),
            "missed_payment_count_30d": int(missed_30d),
            "late_payment_count_30d": int(late_30d),
            "latest_payment_outcome": outcome,
            "latest_payment_row": latest_payload,
            "profile": profile,
            "payment_risk_state": risk_state,
            "delinquency_state": delinquency,
        },
    }


def build_financial_survival_system_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Return composed Step 36 financial survival payload for UI/debug hydration."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    obligation_profile = build_player_obligation_profile(db, player.id, resolved_date, day)
    payment_risk = build_payment_risk_state(db, player.id, resolved_date, day)
    delinquency = build_delinquency_state(db, player.id, resolved_date, day)
    latest = _latest_payment_row(db, player.id, day)
    latest_payload = _serialize_payment_row(latest)
    credit_impact = build_credit_impact_summary(
        credit_score_before=int(latest_payload.get("credit_score_before", player.credit_score or 650)),
        credit_score_after=int(latest_payload.get("credit_score_after", player.credit_score or 650)),
        credit_delta=int(latest_payload.get("credit_score_delta", 0)),
        payment_outcome=str(latest_payload.get("payment_outcome", "paid_full")),
        delinquency_stage_after=str(
            latest_payload.get("delinquency_stage_after")
            or delinquency.get("current_delinquency_stage", "current")
        ),
    )
    survival_summary = build_financial_survival_summary(db, player.id, resolved_date, day)
    history = get_player_payment_history(db, player.id, as_of_date=resolved_date, day_number=day, limit=30)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "obligation_profile": obligation_profile,
        "payment_risk_state": payment_risk,
        "delinquency_state": delinquency,
        "credit_impact": credit_impact,
        "survival_summary": survival_summary,
        "payment_history": history,
        "recent_payment": latest_payload,
        "debug_meta": {
            "service": "financial_survival_service",
            "version": "step36_v1",
        },
    }
