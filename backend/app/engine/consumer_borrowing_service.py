"""Step 37 consumer borrowing + emergency liquidity service.

This service composes with Step 36 survival logic to provide bounded borrowing
options, acceptance decisions, and rolling dependence pressure signals.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.borrowing_offer_catalog import BORROWING_OFFER_CATALOG, BorrowingOfferTemplate
from app.engine.financial_survival_service import build_delinquency_state, build_player_obligation_profile
from app.models.business_daily_log import BusinessDailyLog
from app.models.player import Player
from app.models.player_borrowing_history import PlayerBorrowingHistory
from app.models.player_borrowing_state import PlayerBorrowingState
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_loan_account import PlayerLoanAccount
from app.models.player_payment_history import PlayerPaymentHistory
from app.models.player_shock_state import PlayerShockState

GAME_EPOCH = date(2026, 1, 1)
MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

MAX_ACTIVE_LOANS = 3
MAX_TOTAL_OUTSTANDING_XGP = Decimal("5500.00")
MAX_DAILY_ACCEPTED_OFFERS = 1

PRACTICAL_ACTIONS = [
    "Cut optional spending and protect required payments first.",
    "Take the smallest bridge that closes the immediate gap.",
    "Avoid stacking multiple expensive loans in the same week.",
    "Delay expansion until payment pressure stabilizes.",
    "Reduce fixed burden where possible before adding debt.",
    "Take extra work only if stress and health can support it.",
]

FUTURE_LOCKED_OPTIONS = [
    "Refinance/restructure products (locked)",
    "Secured lending path (locked)",
    "Peer marketplace lending (locked)",
    "Business credit optimization tools (locked)",
]

JOB_STABILITY_WEIGHTS = {
    "aircraft_mechanic": Decimal("0.90"),
    "banker": Decimal("0.84"),
    "auto_mechanic": Decimal("0.74"),
    "chef": Decimal("0.68"),
    "retail_worker": Decimal("0.58"),
    "delivery_driver": Decimal("0.54"),
}

PAYMENT_FACTOR_BY_OUTCOME = {
    "paid_full": Decimal("1.00"),
    "paid_partial": Decimal("0.62"),
    "delayed": Decimal("0.32"),
    "missed": Decimal("0.00"),
}

DELINQUENCY_STAGE_PENALTY = {
    "current": Decimal("0.00"),
    "stretched": Decimal("0.12"),
    "late": Decimal("0.24"),
    "delinquent": Decimal("0.42"),
    "critical": Decimal("0.62"),
}

RISK_SEVERITY_ORDER = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}


class ConsumerBorrowingError(Exception):
    """Base Step 37 consumer borrowing error."""


class ConsumerBorrowingNotFoundError(ConsumerBorrowingError):
    """Raised when player/resources are missing."""


class ConsumerBorrowingValidationError(ConsumerBorrowingError):
    """Raised for invalid payloads or unsupported borrowing actions."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def _safe_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        payload = json.loads(raw)
    except Exception:
        return fallback
    return payload if isinstance(payload, type(fallback)) else fallback


def _dump_json(payload: dict | list) -> str:
    return json.dumps(payload, sort_keys=True)


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise ConsumerBorrowingValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise ConsumerBorrowingValidationError("as_of_date must be on or after game epoch.")
    return day


def _hash_ratio(seed: str) -> Decimal:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    return Decimal(int(digest[:16], 16)) / Decimal((16**16) - 1)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise ConsumerBorrowingNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise ConsumerBorrowingNotFoundError("Player not found.")
    return row


def _resolve_day(db: Session, player: Player, as_of_date: date | None, day_number: int | None) -> tuple[int, date]:
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
        .filter(PlayerEmploymentState.player_id == player_id, PlayerEmploymentState.day <= int(day))
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _latest_shock(db: Session, player_id: UUID) -> PlayerShockState | None:
    return db.query(PlayerShockState).filter(PlayerShockState.player_id == player_id).first()


def _active_loans(db: Session, player_id: UUID) -> list[PlayerLoanAccount]:
    return (
        db.query(PlayerLoanAccount)
        .filter(PlayerLoanAccount.player_id == player_id, PlayerLoanAccount.status.in_(["active", "delinquent"]))
        .order_by(PlayerLoanAccount.accepted_on_day.asc(), PlayerLoanAccount.created_at.asc())
        .all()
    )


def _recent_payments(db: Session, player_id: UUID, day: int, window_days: int = 30) -> list[PlayerPaymentHistory]:
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


def _recent_history(db: Session, player_id: UUID, day: int, window_days: int = 30) -> list[PlayerBorrowingHistory]:
    start_day = max(1, int(day) - max(1, int(window_days)) + 1)
    return (
        db.query(PlayerBorrowingHistory)
        .filter(
            PlayerBorrowingHistory.player_id == player_id,
            PlayerBorrowingHistory.day_number >= start_day,
            PlayerBorrowingHistory.day_number <= int(day),
        )
        .order_by(PlayerBorrowingHistory.day_number.asc(), PlayerBorrowingHistory.created_at.asc())
        .all()
    )


def _get_or_create_borrowing_state(db: Session, player_id: UUID) -> PlayerBorrowingState:
    row = db.query(PlayerBorrowingState).filter(PlayerBorrowingState.player_id == player_id).first()
    if row is not None:
        return row
    row = PlayerBorrowingState(player_id=player_id)
    db.add(row)
    db.flush()
    return row


def _credit_tier(access_score: Decimal) -> str:
    if access_score >= Decimal("78"):
        return "prime"
    if access_score >= Decimal("60"):
        return "standard"
    if access_score >= Decimal("42"):
        return "constrained"
    if access_score >= Decimal("25"):
        return "emergency"
    return "locked"


def _pricing_band(access_score: Decimal, delinquency_stage: str) -> str:
    stage = str(delinquency_stage or "current").lower()
    if stage in {"delinquent", "critical"}:
        return "very_high"
    if access_score >= Decimal("75"):
        return "low"
    if access_score >= Decimal("56"):
        return "moderate"
    if access_score >= Decimal("34"):
        return "high"
    return "very_high"


def _approval_label(score: Decimal) -> str:
    if score >= Decimal("74"):
        return "high"
    if score >= Decimal("54"):
        return "moderate"
    if score >= Decimal("34"):
        return "low"
    return "unlikely"


def _payment_burden_label(daily_payment_xgp: Decimal, required_daily_xgp: Decimal) -> str:
    ratio = _clamp(daily_payment_xgp / max(Decimal("1.00"), required_daily_xgp), Decimal("0"), Decimal("5"))
    if ratio >= Decimal("0.90"):
        return "severe"
    if ratio >= Decimal("0.60"):
        return "high"
    if ratio >= Decimal("0.35"):
        return "moderate"
    return "light"


def _usefulness_label(principal_xgp: Decimal, liquidity_gap_xgp: Decimal) -> str:
    gap = max(Decimal("1.00"), _d(liquidity_gap_xgp))
    coverage = _clamp(principal_xgp / gap, Decimal("0"), Decimal("4"))
    if coverage >= Decimal("1.25"):
        return "strong"
    if coverage >= Decimal("0.80"):
        return "useful"
    if coverage >= Decimal("0.45"):
        return "partial"
    return "weak"


def _history_event_count(rows: list[PlayerBorrowingHistory], event_type: str) -> int:
    target = str(event_type or "").strip().lower()
    return sum(1 for row in rows if str(row.event_type or "").strip().lower() == target)


def _to_float(value: Decimal | int | float) -> float:
    return float(_q4(_d(value)))


def _risk_label_from_offer(template: BorrowingOfferTemplate, pricing_band: str) -> str:
    if pricing_band == "very_high":
        return "very_high"
    if pricing_band == "high" and template.risk_label in {"moderate", "high"}:
        return "high"
    return str(template.risk_label)


def _offer_term_days(template: BorrowingOfferTemplate, seed: str) -> int:
    ratio = _hash_ratio(seed)
    lo, hi = int(template.term_days_range[0]), int(template.term_days_range[1])
    return int(lo + ((hi - lo) * ratio))


def _offer_apr(template: BorrowingOfferTemplate, pricing_band: str, seed: str) -> Decimal:
    lo = _d(template.apr_band[0])
    hi = _d(template.apr_band[1])
    ratio = _hash_ratio(seed)
    if pricing_band == "low":
        scaled = lo + ((hi - lo) * (ratio * Decimal("0.35")))
    elif pricing_band == "moderate":
        scaled = lo + ((hi - lo) * (Decimal("0.35") + ratio * Decimal("0.35")))
    elif pricing_band == "high":
        scaled = lo + ((hi - lo) * (Decimal("0.60") + ratio * Decimal("0.30")))
    else:
        scaled = lo + ((hi - lo) * (Decimal("0.82") + ratio * Decimal("0.18")))
    return _q4(_clamp(scaled, lo, hi))


def _offer_fee_pct(template: BorrowingOfferTemplate, pricing_band: str, seed: str) -> Decimal:
    lo = _d(template.fee_band[0])
    hi = _d(template.fee_band[1])
    ratio = _hash_ratio(seed)
    if pricing_band == "low":
        scaled = lo + ((hi - lo) * (ratio * Decimal("0.45")))
    elif pricing_band == "moderate":
        scaled = lo + ((hi - lo) * (Decimal("0.35") + ratio * Decimal("0.35")))
    elif pricing_band == "high":
        scaled = lo + ((hi - lo) * (Decimal("0.62") + ratio * Decimal("0.30")))
    else:
        scaled = lo + ((hi - lo) * (Decimal("0.86") + ratio * Decimal("0.14")))
    return _q4(_clamp(scaled, lo, hi))


def build_borrowing_eligibility_profile(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build a bounded borrowing-access profile from player finance conditions."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    obligation_profile = build_player_obligation_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    delinquency = build_delinquency_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    employment = _latest_employment(db, player.id, day)
    shock = _latest_shock(db, player.id)
    payments = _recent_payments(db, player.id, day, 30)
    businesses = _recent_business_logs(db, player.id, day, 7)
    history = _recent_history(db, player.id, day, 30)
    loans = _active_loans(db, player.id)

    credit_score = _clamp(_d(getattr(player, "credit_score", 650)), Decimal("300"), Decimal("850"))
    credit_component = _clamp((credit_score - Decimal("300")) / Decimal("550"), Decimal("0"), Decimal("1")) * Decimal("45")
    stage = str(delinquency.get("current_delinquency_stage", "current")).strip().lower()
    stage_penalty = _d(DELINQUENCY_STAGE_PENALTY.get(stage, Decimal("0.18")))

    job_code = str(getattr(employment, "current_job_code", player.main_job or "") or "").strip().lower()
    job_stability = _d(JOB_STABILITY_WEIGHTS.get(job_code, Decimal("0.62")))
    income_stability_component = _clamp(job_stability, Decimal("0.35"), Decimal("0.95")) * Decimal("20")

    payment_rows = max(1, len(payments))
    good_payment_days = sum(
        1
        for row in payments
        if str(getattr(row, "payment_outcome", "paid_full")).strip().lower() == "paid_full"
    )
    payment_discipline_component = _clamp(_d(good_payment_days) / _d(payment_rows), Decimal("0"), Decimal("1")) * Decimal("12")

    missed_30d = int(delinquency.get("missed_payment_count_30d", 0) or 0)
    late_30d = int(delinquency.get("late_payment_count_30d", 0) or 0)
    distress_penalty = _clamp((_d(missed_30d) * Decimal("2.8")) + (_d(late_30d) * Decimal("1.1")), Decimal("0"), Decimal("16"))

    obligation_load = _d(obligation_profile.get("obligation_load_ratio", 0))
    liquidity_days = _d(obligation_profile.get("liquidity_buffer_days", 0))
    obligation_penalty = _clamp(obligation_load - Decimal("0.75"), Decimal("0"), Decimal("3")) * Decimal("8.5")
    liquidity_component = _clamp(liquidity_days / Decimal("8"), Decimal("0"), Decimal("1")) * Decimal("11")

    stress_value = _clamp(_d(getattr(player, "stress", 0)), Decimal("0"), Decimal("100"))
    shock_risk = _clamp(_d(getattr(shock, "shock_risk_score", 0)), Decimal("0"), Decimal("100"))
    fragility_penalty = _clamp((stress_value / Decimal("100")) * Decimal("8") + (shock_risk / Decimal("100")) * Decimal("8"), Decimal("0"), Decimal("16"))

    negative_business_days = sum(1 for row in businesses if _d(getattr(row, "net_profit_xgp", 0)) < Decimal("0"))
    business_volatility_penalty = _clamp(_d(negative_business_days) / Decimal("7"), Decimal("0"), Decimal("1")) * Decimal("7")

    repeat_borrow_count = _history_event_count(history, "offer_accepted")
    dependence_risk_score = _clamp(
        (_d(repeat_borrow_count) * Decimal("13"))
        + (_d(len(loans)) * Decimal("12"))
        + (_d(sum(1 for row in history if str(row.event_type).lower() == "loan_daily_roll" and _d(row.fee_xgp) > Decimal("0"))) * Decimal("4")),
        Decimal("0"),
        Decimal("100"),
    )
    dependence_penalty = _clamp(dependence_risk_score / Decimal("100"), Decimal("0"), Decimal("1")) * Decimal("14")

    access_score = _clamp(
        credit_component
        + income_stability_component
        + payment_discipline_component
        + liquidity_component
        - (stage_penalty * Decimal("42"))
        - distress_penalty
        - obligation_penalty
        - fragility_penalty
        - business_volatility_penalty
        - dependence_penalty,
        Decimal("0"),
        Decimal("100"),
    )

    access_tier = _credit_tier(access_score)
    pricing_band = _pricing_band(access_score, stage)
    outstanding = _money(sum((_d(row.principal_outstanding_xgp) for row in loans), Decimal("0")))
    monthly_income = _money(_d(getattr(employment, "monthly_pay_xgp", 0)))
    daily_income = _money(max(Decimal("1"), monthly_income / Decimal("30")))
    base_safe = _money(
        _clamp(
            _d(obligation_profile.get("required_daily_burden_xgp", 0)) * Decimal("2.4")
            + daily_income * Decimal("1.5")
            + (Decimal("120") if access_tier in {"prime", "standard"} else Decimal("45")),
            Decimal("60"),
            Decimal("2200"),
        )
    )
    safe_from_score = _money(base_safe * _clamp(access_score / Decimal("100"), Decimal("0.25"), Decimal("1.15")))
    max_safe = _money(
        _clamp(
            min(safe_from_score, MAX_TOTAL_OUTSTANDING_XGP - outstanding),
            Decimal("0"),
            Decimal("2500"),
        )
    )

    pressure_label = str(obligation_profile.get("payment_pressure_label", "manageable")).strip().lower()
    if pressure_label in {"high", "critical"} and access_score < Decimal("40"):
        emergency_liquidity_label = "tight"
    elif pressure_label in {"moderate", "high", "critical"}:
        emergency_liquidity_label = "stressed"
    else:
        emergency_liquidity_label = "stable"

    state = _get_or_create_borrowing_state(db, player.id)
    state.borrowing_access_score = _q4(access_score)
    state.credit_access_tier = access_tier
    state.emergency_liquidity_label = emergency_liquidity_label
    state.max_safe_borrow_amount_xgp = _money(max_safe)
    state.estimated_risk_pricing_band = pricing_band
    state.recent_distress_penalty = _q4(stage_penalty + (_d(missed_30d) * Decimal("0.02")))
    state.active_loan_count = int(len(loans))
    state.repeat_borrowing_count_30d = int(repeat_borrow_count)
    state.dependence_risk_score = _q4(dependence_risk_score)
    state.last_updated_on = int(day)
    state.last_updated_date = resolved_date
    state.debug_json = _dump_json(
        {
            "credit_component": float(_q4(credit_component)),
            "income_stability_component": float(_q4(income_stability_component)),
            "payment_discipline_component": float(_q4(payment_discipline_component)),
            "liquidity_component": float(_q4(liquidity_component)),
            "stage_penalty_component": float(_q4(stage_penalty * Decimal("42"))),
            "distress_penalty_component": float(_q4(distress_penalty)),
            "obligation_penalty_component": float(_q4(obligation_penalty)),
            "fragility_penalty_component": float(_q4(fragility_penalty)),
            "business_volatility_penalty_component": float(_q4(business_volatility_penalty)),
            "dependence_penalty_component": float(_q4(dependence_penalty)),
            "loan_outstanding_xgp": float(outstanding),
            "obligation_load_ratio": float(_q4(obligation_load)),
            "liquidity_buffer_days": float(_q4(liquidity_days)),
        }
    )
    db.flush()

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "borrowing_access_score": float(_q4(access_score)),
        "credit_access_tier": access_tier,
        "emergency_liquidity_label": emergency_liquidity_label,
        "max_safe_borrow_amount_xgp": float(_money(max_safe)),
        "estimated_risk_pricing_band": pricing_band,
        "recent_distress_penalty": float(_q4(state.recent_distress_penalty)),
        "dependence_risk_score": float(_q4(dependence_risk_score)),
        "active_loan_count": int(len(loans)),
        "repeat_borrowing_count_30d": int(repeat_borrow_count),
        "last_updated_on": int(day),
        "debug_meta": _safe_json(state.debug_json, {}),
    }


def build_emergency_liquidity_state(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Summarize short-horizon cash-failure pressure and bridge need."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    profile = build_player_obligation_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk_state = build_delinquency_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    required_daily = _money(_d(profile.get("required_daily_burden_xgp", 0)))
    cash = _money(_d(player.cash_xgp))
    liquidity_gap = _money(max(Decimal("0"), required_daily - cash))
    days_to_cash_stress = _q4(_clamp(cash / max(Decimal("1"), required_daily), Decimal("0"), Decimal("120")))

    stage = str(risk_state.get("current_delinquency_stage", "current")).strip().lower()
    if liquidity_gap <= Decimal("0"):
        days_to_payment_failure = Decimal("14")
    elif cash >= _money(required_daily * Decimal("0.7")):
        days_to_payment_failure = Decimal("3")
    elif cash > Decimal("0"):
        days_to_payment_failure = Decimal("2")
    else:
        days_to_payment_failure = Decimal("1")
    if stage in {"delinquent", "critical"}:
        days_to_payment_failure = _clamp(days_to_payment_failure - Decimal("1"), Decimal("1"), Decimal("14"))

    if liquidity_gap <= Decimal("0"):
        bridge_need_label = "none"
        pressure_label = "low"
        preferred_relief_type = "none"
    elif liquidity_gap <= Decimal("120"):
        bridge_need_label = "small_bridge"
        pressure_label = "moderate"
        preferred_relief_type = "small_installment_or_advance"
    elif liquidity_gap <= Decimal("320"):
        bridge_need_label = "bridge_needed"
        pressure_label = "high"
        preferred_relief_type = "structured_short_bridge"
    else:
        bridge_need_label = "urgent_bridge"
        pressure_label = "critical"
        preferred_relief_type = "survival_bridge_only"

    summary = (
        "Current cash can cover required obligations; borrowing is optional and should stay conservative."
        if liquidity_gap <= Decimal("0")
        else "A small bridge may prevent near-term payment failure, but additional debt will raise next-cycle burden."
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "days_to_cash_stress": float(_q4(days_to_cash_stress)),
        "days_to_payment_failure": float(_q4(days_to_payment_failure)),
        "liquidity_gap_xgp": float(_money(liquidity_gap)),
        "bridge_need_label": bridge_need_label,
        "survival_borrowing_pressure_label": pressure_label,
        "preferred_relief_type": preferred_relief_type,
        "short_summary": summary,
        "debug_meta": {
            "required_daily_burden_xgp": float(required_daily),
            "cash_xgp": float(cash),
            "payment_pressure_label": profile.get("payment_pressure_label", "manageable"),
            "delinquency_stage": stage,
        },
    }


def generate_borrowing_options(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    include_locked: bool = False,
) -> dict:
    """Generate bounded, context-sensitive borrowing options for the current day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)

    eligibility = build_borrowing_eligibility_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    liquidity = build_emergency_liquidity_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    profile = build_player_obligation_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    delinquency = build_delinquency_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    loans = _active_loans(db, player.id)
    history_rows = _recent_history(db, player.id, day, 7)

    active_loan_count = int(len(loans))
    outstanding = _money(sum((_d(row.principal_outstanding_xgp) for row in loans), Decimal("0")))
    room_xgp = _money(max(Decimal("0"), MAX_TOTAL_OUTSTANDING_XGP - outstanding))
    if active_loan_count >= MAX_ACTIVE_LOANS:
        room_xgp = Decimal("0.00")

    access_score = _d(eligibility.get("borrowing_access_score", 0))
    pricing_band = str(eligibility.get("estimated_risk_pricing_band", "very_high"))
    credit_score = _clamp(_d(getattr(player, "credit_score", 650)), Decimal("300"), Decimal("850"))
    stage = str(delinquency.get("current_delinquency_stage", "current")).lower()
    max_safe = _money(_d(eligibility.get("max_safe_borrow_amount_xgp", 0)))
    liquidity_gap = _money(_d(liquidity.get("liquidity_gap_xgp", 0)))
    required_daily = _money(_d(profile.get("required_daily_burden_xgp", 0)))
    repeat_recent = _history_event_count(history_rows, "offer_accepted")

    options: list[dict] = []
    for template in BORROWING_OFFER_CATALOG:
        seed = f"{player.id}:{day}:{template.offer_key}"
        stage_penalty = _d(DELINQUENCY_STAGE_PENALTY.get(stage, Decimal("0.18")))
        credit_gap_penalty = _clamp((_d(template.credit_min_hint) - credit_score) / Decimal("22"), Decimal("0"), Decimal("14"))
        difficulty_penalty = _d(template.approval_difficulty) * Decimal("5.4")
        delinquency_penalty = stage_penalty * Decimal(str(32 + (template.delinquency_sensitivity * 20)))
        repeat_penalty = _d(repeat_recent) * Decimal("3.2")
        approval_score = _clamp(
            access_score - difficulty_penalty - credit_gap_penalty - delinquency_penalty - repeat_penalty,
            Decimal("0"),
            Decimal("100"),
        )
        approval_likelihood = _approval_label(approval_score)

        lo_principal = _money(_d(template.principal_range_xgp[0]))
        hi_principal = _money(_d(template.principal_range_xgp[1]))
        ideal_principal = _money(
            _clamp(
                max(liquidity_gap * Decimal("1.08"), lo_principal),
                lo_principal,
                hi_principal,
            )
        )
        principal_cap = _money(min(max_safe, room_xgp, hi_principal))
        principal_offered = _money(min(max(lo_principal, ideal_principal), principal_cap))
        if principal_cap <= Decimal("0"):
            principal_offered = Decimal("0.00")

        term_days = _offer_term_days(template, f"{seed}:term")
        apr = _offer_apr(template, pricing_band, f"{seed}:apr")
        fee_pct = _offer_fee_pct(template, pricing_band, f"{seed}:fee")
        interest_cost = _money(principal_offered * apr * (_d(term_days) / Decimal("365")))
        fee_cost = _money(principal_offered * fee_pct)
        estimated_total_cost = _money(interest_cost + fee_cost)
        total_repay = _money(principal_offered + estimated_total_cost)
        daily_payment = _money(total_repay / max(Decimal("1"), _d(term_days)))

        payment_burden = _payment_burden_label(daily_payment, required_daily)
        usefulness = _usefulness_label(principal_offered, liquidity_gap)
        risk_label = _risk_label_from_offer(template, pricing_band)
        hidden_danger = (
            "Rollover risk can quickly convert short-term relief into compounding debt."
            if template.rollover_allowed and risk_label in {"high", "very_high"}
            else "Even this bridge raises future fixed burden, so only borrow what closes the gap."
        )

        locked_reason = None
        if approval_score < Decimal("24"):
            locked_reason = "Approval odds are too low in current credit/delinquency state."
        elif principal_offered < lo_principal * Decimal("0.60"):
            locked_reason = "Current obligation and outstanding limits cap this offer below viable size."
        elif _history_event_count(history_rows, "offer_accepted") >= MAX_DAILY_ACCEPTED_OFFERS:
            locked_reason = "Daily borrowing limit reached. Reassess tomorrow."
        elif active_loan_count >= MAX_ACTIVE_LOANS:
            locked_reason = "Active borrowing account limit reached."

        row = {
            "offer_key": template.offer_key,
            "offer_family": template.offer_family,
            "headline": template.headline,
            "approval_likelihood_label": approval_likelihood,
            "principal_offered_xgp": float(_money(principal_offered)),
            "estimated_total_cost_xgp": float(_money(estimated_total_cost)),
            "estimated_repay_xgp": float(_money(total_repay)),
            "term_days": int(term_days),
            "term_label": f"{int(term_days)}d term",
            "apr_pct": float(_q4(apr * Decimal("100"))),
            "fee_pct": float(_q4(fee_pct * Decimal("100"))),
            "payment_burden_label": payment_burden,
            "risk_label": risk_label,
            "emergency_usefulness_label": usefulness,
            "hidden_danger_summary": hidden_danger,
            "rollover_allowed": bool(template.rollover_allowed),
            "short_summary": template.short_summary,
            "locked": bool(locked_reason),
            "locked_reason": locked_reason,
            "debug_meta": {
                "approval_score": float(_q4(approval_score)),
                "access_score": float(_q4(access_score)),
                "credit_score": float(_q4(credit_score)),
                "delinquency_stage": stage,
                "pricing_band": pricing_band,
                "required_daily_burden_xgp": float(required_daily),
                "liquidity_gap_xgp": float(liquidity_gap),
                "max_safe_borrow_amount_xgp": float(max_safe),
                "room_remaining_xgp": float(room_xgp),
                "active_loan_count": active_loan_count,
                "stage_penalty_component": float(_q4(delinquency_penalty)),
            },
        }
        if include_locked or not row["locked"]:
            options.append(row)

    options.sort(
        key=lambda item: (
            bool(item.get("locked")),
            RISK_SEVERITY_ORDER.get(str(item.get("risk_label", "very_high")), 9),
            float(item.get("estimated_total_cost_xgp", 0)),
            str(item.get("offer_key", "")),
        )
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "items": options[:6],
        "debug_meta": {
            "active_loan_count": active_loan_count,
            "total_outstanding_xgp": float(outstanding),
            "max_total_outstanding_xgp": float(MAX_TOTAL_OUTSTANDING_XGP),
            "max_active_loans": MAX_ACTIVE_LOANS,
            "pricing_band": pricing_band,
            "future_locked_options": FUTURE_LOCKED_OPTIONS,
        },
    }


def evaluate_borrowing_offer(
    db: Session,
    player_id: str | UUID,
    offer_key: str,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Evaluate one offer in context and surface bounded short vs long tradeoffs."""
    key = str(offer_key or "").strip()
    if not key:
        raise ConsumerBorrowingValidationError("offer_key is required.")

    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    options = generate_borrowing_options(
        db=db,
        player_id=player.id,
        as_of_date=resolved_date,
        day_number=day,
        include_locked=True,
    )
    option = next((item for item in options.get("items", []) if str(item.get("offer_key")) == key), None)
    if option is None:
        raise ConsumerBorrowingValidationError("Borrowing offer is unavailable for this player/day.")

    liquidity = build_emergency_liquidity_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    bridge_need = str(liquidity.get("bridge_need_label", "none"))
    usefulness = str(option.get("emergency_usefulness_label", "weak"))
    risk_label = str(option.get("risk_label", "very_high"))
    burden = str(option.get("payment_burden_label", "severe"))
    can_accept = not bool(option.get("locked", False))

    if usefulness in {"strong", "useful"} and bridge_need in {"bridge_needed", "urgent_bridge"}:
        short_relief = "high"
    elif usefulness in {"partial", "useful"}:
        short_relief = "moderate"
    else:
        short_relief = "low"

    if burden in {"severe", "high"} or risk_label in {"high", "very_high"}:
        future_burden = "high"
    elif burden == "moderate":
        future_burden = "moderate"
    else:
        future_burden = "low"

    if bridge_need in {"bridge_needed", "urgent_bridge"} and short_relief in {"high", "moderate"}:
        credit_protection = "meaningful_if_disciplined"
    elif bridge_need == "none":
        credit_protection = "limited"
    else:
        credit_protection = "situational"

    summary = (
        "This offer can stabilize immediate payment pressure but will add meaningful future burden."
        if future_burden == "high" and short_relief != "low"
        else "This offer is a bounded bridge; keep principal small to avoid dependence."
        if future_burden in {"moderate", "low"} and short_relief != "low"
        else "This offer has weak relief value in your current state and is likely not worth the burden."
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "offer": option,
        "can_accept": can_accept,
        "short_term_relief_label": short_relief,
        "future_burden_label": future_burden,
        "credit_protection_value_label": credit_protection,
        "summary": summary,
        "debug_meta": {
            "bridge_need_label": bridge_need,
            "liquidity_gap_xgp": liquidity.get("liquidity_gap_xgp", 0),
            "locked_reason": option.get("locked_reason"),
        },
    }


def _calculate_offer_terms(option: dict, principal_xgp: Decimal) -> dict:
    apr_pct = _d(option.get("apr_pct", 0))
    fee_pct = _d(option.get("fee_pct", 0))
    term_days = max(7, int(option.get("term_days", 30) or 30))
    apr = _q4(apr_pct / Decimal("100"))
    fee_rate = _q4(fee_pct / Decimal("100"))

    total_fee = _money(principal_xgp * fee_rate)
    interest_cost = _money(principal_xgp * apr * (_d(term_days) / Decimal("365")))
    scheduled_total_repay = _money(principal_xgp + total_fee + interest_cost)
    scheduled_daily = _money(scheduled_total_repay / max(Decimal("1"), _d(term_days)))

    upfront_fee = _money(total_fee * Decimal("0.45"))
    financed_fee = _money(total_fee - upfront_fee)
    cash_delta = _money(max(Decimal("0.00"), principal_xgp - upfront_fee))
    debt_delta = _money(principal_xgp + financed_fee)

    return {
        "apr_rate": apr,
        "fee_rate": fee_rate,
        "term_days": term_days,
        "total_fee_xgp": total_fee,
        "interest_cost_xgp": interest_cost,
        "scheduled_total_repay_xgp": scheduled_total_repay,
        "scheduled_daily_payment_xgp": scheduled_daily,
        "upfront_fee_xgp": upfront_fee,
        "financed_fee_xgp": financed_fee,
        "cash_delta_xgp": cash_delta,
        "debt_delta_xgp": debt_delta,
    }


def apply_borrowing_decision(
    db: Session,
    player_id: str | UUID,
    *,
    offer_key: str,
    principal_requested_xgp: Decimal | float | int | None = None,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Apply one accepted borrowing decision and persist loan + history rows."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    evaluation = evaluate_borrowing_offer(db=db, player_id=player.id, offer_key=offer_key, as_of_date=resolved_date, day_number=day)
    offer = evaluation.get("offer") or {}

    if not evaluation.get("can_accept", False):
        raise ConsumerBorrowingValidationError(
            str(offer.get("locked_reason") or "Offer cannot be accepted in current state.")
        )

    current_loans = _active_loans(db, player.id)
    if len(current_loans) >= MAX_ACTIVE_LOANS:
        raise ConsumerBorrowingValidationError("Maximum active borrowing accounts reached.")
    same_day_accepts = _history_event_count(_recent_history(db, player.id, day, 2), "offer_accepted")
    if same_day_accepts >= MAX_DAILY_ACCEPTED_OFFERS:
        raise ConsumerBorrowingValidationError("Daily borrowing acceptance limit reached.")

    principal_offered = _money(_d(offer.get("principal_offered_xgp", 0)))
    if principal_offered <= Decimal("0"):
        raise ConsumerBorrowingValidationError("Offer has no viable principal in current state.")
    principal = principal_offered
    if principal_requested_xgp is not None:
        requested = _money(_d(principal_requested_xgp))
        if requested <= Decimal("0"):
            raise ConsumerBorrowingValidationError("principal_requested_xgp must be greater than 0.")
        principal = _money(min(principal_offered, requested))
        principal = _money(max(principal, Decimal("25.00")))

    term_info = _calculate_offer_terms(offer, principal)
    outstanding_now = _money(sum((_d(row.principal_outstanding_xgp) for row in current_loans), Decimal("0")))
    projected_outstanding = _money(outstanding_now + term_info["debt_delta_xgp"] + term_info["interest_cost_xgp"])
    if projected_outstanding > MAX_TOTAL_OUTSTANDING_XGP:
        raise ConsumerBorrowingValidationError("Projected outstanding would exceed emergency borrowing cap.")

    cash_before = _money(_d(player.cash_xgp))
    debt_before = _money(_d(player.debt_xgp))
    cash_after = _money(cash_before + term_info["cash_delta_xgp"])
    debt_after = _money(debt_before + term_info["debt_delta_xgp"] + term_info["interest_cost_xgp"])

    loan = PlayerLoanAccount(
        player_id=player.id,
        offer_key=str(offer.get("offer_key", offer_key)),
        offer_family=str(offer.get("offer_family", "unknown")),
        status="active",
        principal_original_xgp=term_info["scheduled_total_repay_xgp"],
        principal_outstanding_xgp=term_info["scheduled_total_repay_xgp"],
        apr_pct=_q4(term_info["apr_rate"] * Decimal("100")),
        fee_amount_xgp=term_info["total_fee_xgp"],
        term_days=int(term_info["term_days"]),
        days_elapsed=0,
        days_remaining=int(term_info["term_days"]),
        scheduled_daily_payment_xgp=term_info["scheduled_daily_payment_xgp"],
        current_due_xgp=term_info["scheduled_daily_payment_xgp"],
        rollover_allowed=bool(offer.get("rollover_allowed", False)),
        accepted_on_day=int(day),
        accepted_on_date=resolved_date,
        account_meta_json=_dump_json(
            {
                "headline": offer.get("headline"),
                "risk_label": offer.get("risk_label"),
                "payment_burden_label": offer.get("payment_burden_label"),
                "short_term_relief_label": evaluation.get("short_term_relief_label"),
                "future_burden_label": evaluation.get("future_burden_label"),
                "principal_requested_xgp": float(_money(_d(principal_requested_xgp))) if principal_requested_xgp is not None else None,
            }
        ),
        debug_json=_dump_json(
            {
                "cash_delta_xgp": float(term_info["cash_delta_xgp"]),
                "debt_delta_xgp": float(term_info["debt_delta_xgp"]),
                "interest_cost_xgp": float(term_info["interest_cost_xgp"]),
                "upfront_fee_xgp": float(term_info["upfront_fee_xgp"]),
                "financed_fee_xgp": float(term_info["financed_fee_xgp"]),
            }
        ),
    )
    db.add(loan)
    db.flush()

    player.cash_xgp = cash_after
    player.debt_xgp = debt_after
    player.net_worth_xgp = _money(_d(player.cash_xgp) + _d(getattr(player, "bank_savings_xgp", 0)) - _d(player.debt_xgp))

    history_row = PlayerBorrowingHistory(
        player_id=player.id,
        day_number=int(day),
        as_of_date=resolved_date,
        event_type="offer_accepted",
        offer_key=str(offer.get("offer_key", offer_key)),
        offer_family=str(offer.get("offer_family", "unknown")),
        loan_account_id=loan.id,
        principal_xgp=principal,
        fee_xgp=term_info["total_fee_xgp"],
        apr_pct=_q4(term_info["apr_rate"] * Decimal("100")),
        term_days=int(term_info["term_days"]),
        estimated_total_cost_xgp=_money(term_info["total_fee_xgp"] + term_info["interest_cost_xgp"]),
        cash_delta_xgp=term_info["cash_delta_xgp"],
        debt_delta_xgp=_money(term_info["debt_delta_xgp"] + term_info["interest_cost_xgp"]),
        obligation_delta_xgp=term_info["scheduled_daily_payment_xgp"],
        status_after="active",
        summary_json=_dump_json(
            {
                "risk_label": offer.get("risk_label"),
                "approval_likelihood_label": offer.get("approval_likelihood_label"),
                "hidden_danger_summary": offer.get("hidden_danger_summary"),
                "short_term_relief_label": evaluation.get("short_term_relief_label"),
                "future_burden_label": evaluation.get("future_burden_label"),
            }
        ),
        debug_json=_dump_json(
            {
                "cash_before_xgp": float(cash_before),
                "cash_after_xgp": float(cash_after),
                "debt_before_xgp": float(debt_before),
                "debt_after_xgp": float(debt_after),
            }
        ),
    )
    db.add(history_row)
    db.flush()

    eligibility_after = build_borrowing_eligibility_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    liquidity_after = build_emergency_liquidity_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk_after = build_borrowing_risk_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "offer_key": str(offer.get("offer_key", offer_key)),
        "offer_family": str(offer.get("offer_family", "unknown")),
        "accepted": True,
        "loan_account_id": str(loan.id),
        "cash_before_xgp": float(cash_before),
        "cash_after_xgp": float(cash_after),
        "debt_before_xgp": float(debt_before),
        "debt_after_xgp": float(debt_after),
        "principal_accepted_xgp": float(principal),
        "estimated_total_cost_xgp": float(_money(term_info["total_fee_xgp"] + term_info["interest_cost_xgp"])),
        "scheduled_daily_payment_xgp": float(term_info["scheduled_daily_payment_xgp"]),
        "risk_label": str(offer.get("risk_label", "moderate")),
        "short_term_relief_label": str(evaluation.get("short_term_relief_label", "moderate")),
        "future_burden_label": str(evaluation.get("future_burden_label", "moderate")),
        "eligibility_profile_after": eligibility_after,
        "liquidity_state_after": liquidity_after,
        "risk_summary_after": risk_after,
        "debug_meta": {
            "term_days": int(term_info["term_days"]),
            "apr_pct": float(_q4(term_info["apr_rate"] * Decimal("100"))),
            "fee_pct": float(_q4(term_info["fee_rate"] * Decimal("100"))),
            "upfront_fee_xgp": float(term_info["upfront_fee_xgp"]),
            "financed_fee_xgp": float(term_info["financed_fee_xgp"]),
        },
    }


def refresh_loan_accounts(
    db: Session,
    player_id: str | UUID,
    *,
    day_number: int | None = None,
    as_of_date: date | None = None,
    payment_outcome: str = "paid_full",
) -> dict:
    """Advance active loan accounts for the day with bounded payment factors."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    rows = _active_loans(db, player.id)
    if not rows:
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "day_number": int(day),
            "processed_accounts": 0,
            "added_interest_xgp": 0.0,
            "paid_toward_loans_xgp": 0.0,
            "late_fee_added_to_loans_xgp": 0.0,
            "debug_meta": {"note": "no_active_loans"},
        }

    factor = PAYMENT_FACTOR_BY_OUTCOME.get(str(payment_outcome or "paid_full").strip().lower(), Decimal("0.0"))
    total_interest = Decimal("0.00")
    total_paid = Decimal("0.00")
    total_penalty = Decimal("0.00")
    processed = 0
    for loan in rows:
        if int(getattr(loan, "last_payment_day", 0) or 0) == int(day):
            continue

        due = _money(max(_d(getattr(loan, "current_due_xgp", 0)), _d(getattr(loan, "scheduled_daily_payment_xgp", 0))))
        outstanding_before = _money(_d(getattr(loan, "principal_outstanding_xgp", 0)))
        apr_rate = _q4(_d(getattr(loan, "apr_pct", 0)) / Decimal("100"))
        interest = _money(outstanding_before * apr_rate / Decimal("365"))
        paid = _money(due * factor)
        penalty = Decimal("0.00")

        if factor < Decimal("0.85"):
            loan.missed_payment_count = int(getattr(loan, "missed_payment_count", 0) or 0) + 1
            penalty = _money(_clamp(due * Decimal("0.07"), Decimal("0"), Decimal("18")))
        else:
            loan.missed_payment_count = max(0, int(getattr(loan, "missed_payment_count", 0) or 0) - 1)

        outstanding_after = _money(max(Decimal("0"), outstanding_before + interest + penalty - paid))
        loan.principal_outstanding_xgp = outstanding_after
        loan.days_elapsed = int(getattr(loan, "days_elapsed", 0) or 0) + 1
        loan.days_remaining = max(0, int(getattr(loan, "term_days", 30) or 30) - int(loan.days_elapsed))
        loan.current_due_xgp = _money(_d(getattr(loan, "scheduled_daily_payment_xgp", due)))
        loan.last_payment_day = int(day)
        loan.last_payment_amount_xgp = paid

        if outstanding_after <= Decimal("0.01"):
            loan.status = "closed"
            loan.current_due_xgp = Decimal("0.00")
            loan.closed_on_day = int(day)
            loan.closed_on_date = resolved_date
            loan.delinquency_stage = "current"
        elif loan.missed_payment_count >= 3 or (loan.days_remaining == 0 and outstanding_after > Decimal("1.00")):
            loan.status = "delinquent"
            loan.delinquency_stage = "delinquent"
        else:
            loan.status = "active"
            loan.delinquency_stage = "current"

        db.add(
            PlayerBorrowingHistory(
                player_id=player.id,
                day_number=int(day),
                as_of_date=resolved_date,
                event_type="loan_daily_roll",
                offer_key=loan.offer_key,
                offer_family=loan.offer_family,
                loan_account_id=loan.id,
                principal_xgp=outstanding_before,
                fee_xgp=penalty,
                apr_pct=_q4(apr_rate * Decimal("100")),
                term_days=int(getattr(loan, "term_days", 30) or 30),
                estimated_total_cost_xgp=_money(interest + penalty),
                cash_delta_xgp=_money(-paid),
                debt_delta_xgp=_money(interest + penalty - paid),
                obligation_delta_xgp=_money(loan.current_due_xgp),
                status_after=str(loan.status),
                summary_json=_dump_json(
                    {
                        "payment_outcome": str(payment_outcome),
                        "payment_factor": float(_q4(factor)),
                        "interest_xgp": float(interest),
                        "penalty_xgp": float(penalty),
                        "paid_xgp": float(paid),
                    }
                ),
                debug_json=_dump_json(
                    {
                        "outstanding_before_xgp": float(outstanding_before),
                        "outstanding_after_xgp": float(outstanding_after),
                        "missed_payment_count": int(loan.missed_payment_count or 0),
                    }
                ),
            )
        )
        total_interest += interest
        total_paid += paid
        total_penalty += penalty
        processed += 1

    player.debt_xgp = _money(max(_d(player.debt_xgp), _money(sum((_d(row.principal_outstanding_xgp) for row in _active_loans(db, player.id)), Decimal("0")))))
    db.flush()
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "processed_accounts": int(processed),
        "added_interest_xgp": float(_money(total_interest)),
        "paid_toward_loans_xgp": float(_money(total_paid)),
        "late_fee_added_to_loans_xgp": float(_money(total_penalty)),
        "debug_meta": {"payment_outcome": str(payment_outcome), "payment_factor": float(_q4(factor))},
    }


def build_borrowing_risk_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Summarize whether borrowing is stabilizing, dangerous, or trap-like."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    liquidity = build_emergency_liquidity_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    options = generate_borrowing_options(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day, include_locked=False)

    if not options.get("items"):
        return {
            "player_id": str(player.id),
            "as_of_date": resolved_date.isoformat(),
            "risk_label": "locked",
            "short_term_relief_label": "low",
            "future_burden_label": "unknown",
            "credit_protection_value_label": "limited",
            "top_risk_driver": "No safe borrowing option is currently available.",
            "top_reason_to_avoid": "Borrowing access is constrained by current delinquency/obligation profile.",
            "top_reason_to_consider": "Focus on non-borrowing stabilization actions first.",
            "short_summary": "Borrowing is currently constrained; prioritize cash discipline and required payments.",
            "debug_meta": {"options_available": 0},
        }

    best = options["items"][0]
    usefulness = str(best.get("emergency_usefulness_label", "weak"))
    burden = str(best.get("payment_burden_label", "high"))
    risk_label = str(best.get("risk_label", "high"))
    bridge_need = str(liquidity.get("bridge_need_label", "none"))

    if risk_label in {"very_high"} or burden in {"severe"}:
        summary_risk = "trap_like"
    elif risk_label == "high" or burden == "high":
        summary_risk = "dangerous"
    elif usefulness in {"strong", "useful"} and bridge_need in {"bridge_needed", "urgent_bridge"}:
        summary_risk = "stabilizing_if_disciplined"
    else:
        summary_risk = "risky_but_manageable"

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "risk_label": summary_risk,
        "short_term_relief_label": usefulness,
        "future_burden_label": burden,
        "credit_protection_value_label": (
            "meaningful" if bridge_need in {"bridge_needed", "urgent_bridge"} and usefulness != "weak" else "limited"
        ),
        "top_risk_driver": str(best.get("hidden_danger_summary", "Future payment burden can compound.")),
        "top_reason_to_avoid": (
            "Future fixed burden is heavy relative to your daily obligation load."
            if burden in {"high", "severe"}
            else "This offer may be unnecessary if you can stabilize without new debt."
        ),
        "top_reason_to_consider": (
            "Can prevent near-term missed obligations and credit damage."
            if usefulness in {"strong", "useful"}
            else "Can partially reduce immediate failure risk."
        ),
        "short_summary": (
            "Borrowing can be a survival bridge right now, but only at controlled size."
            if summary_risk in {"stabilizing_if_disciplined", "risky_but_manageable"}
            else "Current borrowing options carry high trap risk; minimize principal or avoid if possible."
        ),
        "debug_meta": {
            "selected_offer_key": best.get("offer_key"),
            "liquidity_gap_xgp": liquidity.get("liquidity_gap_xgp"),
            "bridge_need_label": bridge_need,
        },
    }


def build_borrowing_pressure_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Build player-facing borrowing pressure summary and practical actions."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    liquidity = build_emergency_liquidity_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk = build_borrowing_risk_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    options = generate_borrowing_options(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day, include_locked=False)

    if not options.get("items"):
        best_option = "none_available"
        trap_warning = "Do not force high-cost debt stacking when no safe option is available."
    else:
        best = options["items"][0]
        best_option = str(best.get("headline") or best.get("offer_key") or "bridge option")
        trap_warning = str(best.get("hidden_danger_summary", "Future burden can compound quickly."))

    pressure_label = str(liquidity.get("survival_borrowing_pressure_label", "low"))
    recommendation = (
        "Use a small bridge only if needed to keep required payments current."
        if pressure_label in {"high", "critical"}
        else "Borrow conservatively and only when the bridge closes a real near-term gap."
        if pressure_label == "moderate"
        else "Keep borrowing optional; strengthen cash buffer first."
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "current_liquidity_pressure_label": pressure_label,
        "best_available_option_label": best_option,
        "worst_trap_warning": trap_warning,
        "practical_current_actions": PRACTICAL_ACTIONS,
        "short_recommendation": recommendation,
        "future_locked_options": FUTURE_LOCKED_OPTIONS,
        "debug_meta": {
            "bridge_need_label": liquidity.get("bridge_need_label"),
            "liquidity_gap_xgp": liquidity.get("liquidity_gap_xgp"),
            "risk_summary": risk,
            "options_available": len(options.get("items", [])),
        },
    }


def get_player_loan_accounts(
    db: Session,
    player_id: str | UUID,
    *,
    include_closed: bool = False,
) -> dict:
    """Return loan account snapshots for UI/debug inspection."""
    player = _resolve_player(db, player_id)
    query = db.query(PlayerLoanAccount).filter(PlayerLoanAccount.player_id == player.id)
    if not include_closed:
        query = query.filter(PlayerLoanAccount.status.in_(["active", "delinquent"]))
    rows = query.order_by(PlayerLoanAccount.accepted_on_day.desc(), PlayerLoanAccount.created_at.desc()).all()
    return {
        "player_id": str(player.id),
        "entries": [
            {
                "loan_account_id": str(row.id),
                "offer_key": str(row.offer_key),
                "offer_family": str(row.offer_family),
                "status": str(row.status),
                "principal_original_xgp": float(_money(_d(row.principal_original_xgp))),
                "principal_outstanding_xgp": float(_money(_d(row.principal_outstanding_xgp))),
                "apr_pct": float(_q4(_d(row.apr_pct))),
                "fee_amount_xgp": float(_money(_d(row.fee_amount_xgp))),
                "term_days": int(row.term_days or 0),
                "days_elapsed": int(row.days_elapsed or 0),
                "days_remaining": int(row.days_remaining or 0),
                "scheduled_daily_payment_xgp": float(_money(_d(row.scheduled_daily_payment_xgp))),
                "current_due_xgp": float(_money(_d(row.current_due_xgp))),
                "missed_payment_count": int(row.missed_payment_count or 0),
                "delinquency_stage": str(row.delinquency_stage or "current"),
                "rollover_allowed": bool(row.rollover_allowed),
                "accepted_on_day": int(row.accepted_on_day or 0),
                "accepted_on_date": row.accepted_on_date.isoformat() if row.accepted_on_date else None,
                "last_payment_day": int(row.last_payment_day) if row.last_payment_day is not None else None,
                "last_payment_amount_xgp": float(_money(_d(row.last_payment_amount_xgp))),
                "closed_on_day": int(row.closed_on_day) if row.closed_on_day is not None else None,
            }
            for row in rows
        ],
        "debug_meta": {"include_closed": bool(include_closed)},
    }


def get_player_borrowing_history(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
    *,
    limit: int = 30,
) -> dict:
    """Return recent borrowing events for audit and world-memory ingestion."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    rows = _recent_history(db, player.id, day, max(1, int(limit)))
    entries = rows[-limit:] if len(rows) > limit else rows
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "entries": [
            {
                "day_number": int(row.day_number),
                "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
                "event_type": str(row.event_type),
                "offer_key": str(row.offer_key or ""),
                "offer_family": str(row.offer_family or ""),
                "loan_account_id": str(row.loan_account_id) if row.loan_account_id else None,
                "principal_xgp": float(_money(_d(row.principal_xgp))),
                "fee_xgp": float(_money(_d(row.fee_xgp))),
                "apr_pct": float(_q4(_d(row.apr_pct))),
                "term_days": int(row.term_days or 0),
                "estimated_total_cost_xgp": float(_money(_d(row.estimated_total_cost_xgp))),
                "cash_delta_xgp": float(_money(_d(row.cash_delta_xgp))),
                "debt_delta_xgp": float(_money(_d(row.debt_delta_xgp))),
                "obligation_delta_xgp": float(_money(_d(row.obligation_delta_xgp))),
                "status_after": str(row.status_after or "active"),
                "summary": _safe_json(row.summary_json, {}),
                "debug_meta": _safe_json(row.debug_json, {}),
            }
            for row in reversed(entries)
        ],
        "debug_meta": {"limit": int(limit), "rows_in_window": len(rows)},
    }


def build_consumer_borrowing_system_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
    day_number: int | None = None,
) -> dict:
    """Compose all Step 37 borrowing payloads for one player/day."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, player, as_of_date, day_number)
    eligibility = build_borrowing_eligibility_profile(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    liquidity = build_emergency_liquidity_state(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    options = generate_borrowing_options(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    risk = build_borrowing_risk_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    pressure = build_borrowing_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day)
    loans = get_player_loan_accounts(db=db, player_id=player.id, include_closed=False)
    history = get_player_borrowing_history(db=db, player_id=player.id, as_of_date=resolved_date, day_number=day, limit=30)
    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "day_number": int(day),
        "eligibility_profile": eligibility,
        "liquidity_state": liquidity,
        "options": options,
        "risk_summary": risk,
        "pressure_summary": pressure,
        "loan_accounts": loans,
        "history": history,
        "debug_meta": {"future_locked_options": FUTURE_LOCKED_OPTIONS},
    }
