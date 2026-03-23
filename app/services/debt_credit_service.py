"""Debt pressure and credit score dynamics service."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

CREDIT_MIN = 300
CREDIT_MAX = 850


class DebtCreditError(Exception):
    """Base exception for debt and credit service failures."""


class DebtCreditNotFoundError(DebtCreditError):
    """Raised when player or debt/credit history is missing."""


class DebtCreditValidationError(DebtCreditError):
    """Raised for invalid input payloads."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DebtCreditNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise DebtCreditNotFoundError("Player not found.")
    return player


def _latest_employment_state(db: Session, player_id: UUID, day: int) -> PlayerEmploymentState | None:
    return (
        db.query(PlayerEmploymentState)
        .filter(
            PlayerEmploymentState.player_id == player_id,
            PlayerEmploymentState.day <= day,
        )
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )


def _latest_budget_pressure_score(db: Session, player_id: UUID, day: int) -> Decimal | None:
    row = (
        db.query(BasketConsumptionLog)
        .filter(
            BasketConsumptionLog.player_id == player_id,
            BasketConsumptionLog.day <= day,
        )
        .order_by(BasketConsumptionLog.day.desc(), BasketConsumptionLog.created_at.desc())
        .first()
    )
    if row is None:
        return None
    return _q4(_d(row.budget_pressure_score))


def _prior_delinquency_streak(db: Session, player_id: UUID, day: int) -> int:
    rows = (
        db.query(DebtCreditLog)
        .filter(
            DebtCreditLog.player_id == player_id,
            DebtCreditLog.day < day,
        )
        .order_by(DebtCreditLog.day.desc(), DebtCreditLog.created_at.desc())
        .limit(90)
        .all()
    )

    streak = 0
    for row in rows:
        if bool(row.delinquency_flag):
            streak += 1
        else:
            break
    return streak


def _fallback_pressure(opening_debt: Decimal, cash_xgp: Decimal, employed: bool) -> Decimal:
    cash_anchor = max(cash_xgp, Decimal("1.00"))
    debt_cash_ratio = _q4(_money(opening_debt) / (cash_anchor * Decimal("4.00")))
    base = min(Decimal("0.65"), debt_cash_ratio)
    if cash_xgp < Decimal("25.00"):
        base += Decimal("0.20")
    if not employed:
        base += Decimal("0.20")
    return _q4(min(Decimal("1.00"), max(Decimal("0.00"), base)))


def _compute_daily_interest_rate(
    opening_credit_score: int,
    pressure_score: Decimal,
    prior_delinquency_streak: int,
    employed_flag: bool,
) -> Decimal:
    rate = Decimal("0.0004")

    if opening_credit_score < 650:
        rate += Decimal(str(650 - opening_credit_score)) / Decimal("200000")
    elif opening_credit_score >= 740:
        rate -= Decimal("0.00005")

    rate += min(Decimal(str(prior_delinquency_streak)) * Decimal("0.00008"), Decimal("0.00032"))
    rate += _q4(pressure_score) * Decimal("0.00020")

    if not employed_flag:
        rate += Decimal("0.00008")

    rate = min(Decimal("0.0014"), max(Decimal("0.0002"), rate))
    return _q4(rate)


def _build_obligation_state(db: Session, player: Player, day: int) -> dict:
    opening_debt = _money(_d(player.debt_xgp))
    opening_credit = _clamp_int(int(player.credit_score or 650), CREDIT_MIN, CREDIT_MAX)
    cash_now = _money(_d(player.cash_xgp))

    employment = _latest_employment_state(db, player.id, day)
    employed = bool(getattr(employment, "employed_flag", False))
    monthly_pay = _money(_d(getattr(employment, "monthly_pay_xgp", 0))) if employment is not None else Decimal("0.00")

    budget_pressure = _latest_budget_pressure_score(db, player.id, day)
    if budget_pressure is None:
        budget_pressure = _fallback_pressure(opening_debt, cash_now, employed)

    prior_streak = _prior_delinquency_streak(db, player.id, day)

    if opening_debt <= Decimal("0.00"):
        payment_due = Decimal("0.00")
        daily_interest_rate = Decimal("0.0000")
    else:
        # MVP debt burden: 1.25% daily minimum, with low/high guardrails.
        # This keeps pressure meaningful without allowing explosive swings.
        payment_due = _money(
            min(
                opening_debt,
                max(Decimal("6.00"), min(Decimal("120.00"), opening_debt * Decimal("0.0125"))),
            )
        )
        daily_interest_rate = _compute_daily_interest_rate(
            opening_credit_score=opening_credit,
            pressure_score=budget_pressure,
            prior_delinquency_streak=prior_streak,
            employed_flag=employed,
        )

    return {
        "player_id": str(player.id),
        "day": int(day),
        "opening_debt_xgp": opening_debt,
        "opening_credit_score": opening_credit,
        "cash_available_xgp": cash_now,
        "payment_due_xgp": payment_due,
        "daily_interest_rate": daily_interest_rate,
        "budget_pressure_score": _q4(budget_pressure),
        "employed_flag": bool(employed),
        "monthly_pay_xgp": monthly_pay,
        "prior_delinquency_streak": int(prior_streak),
    }


def _determine_payment(
    payment_due_xgp: Decimal,
    available_cash_xgp: Decimal,
    budget_pressure_score: Decimal,
    employed_flag: bool,
) -> tuple[Decimal, str]:
    if payment_due_xgp <= Decimal("0.00"):
        return Decimal("0.00"), "no_debt"

    available_cash_xgp = _money(max(Decimal("0.00"), available_cash_xgp))
    if available_cash_xgp <= Decimal("0.00"):
        return Decimal("0.00"), "missed"

    if available_cash_xgp >= payment_due_xgp:
        if (not employed_flag) and budget_pressure_score >= Decimal("0.93") and available_cash_xgp < (payment_due_xgp * Decimal("1.20")):
            buffered = _money(available_cash_xgp * Decimal("0.70"))
            if buffered >= payment_due_xgp:
                return payment_due_xgp, "paid_full"
            if buffered >= Decimal("1.00"):
                return buffered, "paid_partial"
            return Decimal("0.00"), "missed"
        return payment_due_xgp, "paid_full"

    reserve_ratio = Decimal("0.12") + (_q4(budget_pressure_score) * Decimal("0.40"))
    if not employed_flag:
        reserve_ratio += Decimal("0.18")
    reserve_ratio = min(Decimal("0.78"), max(Decimal("0.12"), reserve_ratio))

    payable = _money(max(Decimal("0.00"), available_cash_xgp * (Decimal("1.00") - reserve_ratio)))

    if payable >= (payment_due_xgp * Decimal("0.98")):
        return payment_due_xgp, "paid_full"
    if payable >= max(Decimal("1.00"), payment_due_xgp * Decimal("0.20")):
        return min(payment_due_xgp, payable), "paid_partial"
    return Decimal("0.00"), "missed"


def _compute_credit_change(
    payment_status: str,
    opening_credit_score: int,
    opening_debt_xgp: Decimal,
    budget_pressure_score: Decimal,
    prior_delinquency_streak: int,
    monthly_pay_xgp: Decimal,
) -> int:
    if opening_debt_xgp <= Decimal("0.00"):
        return 0

    base_by_status = {
        "paid_full": 1,
        "paid_partial": -2,
        "missed": -6,
    }
    change = base_by_status.get(payment_status, 0)

    income_anchor = max(monthly_pay_xgp, Decimal("1200.00"))
    burden_ratio = opening_debt_xgp / income_anchor
    if burden_ratio >= Decimal("4.00"):
        change -= 2
    elif burden_ratio >= Decimal("2.00"):
        change -= 1

    if payment_status == "missed":
        change -= min(4, prior_delinquency_streak + 1)
    elif payment_status == "paid_partial" and prior_delinquency_streak >= 2:
        change -= 1

    if payment_status == "paid_full" and prior_delinquency_streak >= 1:
        change -= 1

    if budget_pressure_score >= Decimal("0.85") and payment_status in {"paid_partial", "missed"}:
        change -= 1

    change = _clamp_int(change, -12, 2)

    if opening_credit_score <= CREDIT_MIN and change < 0:
        return 0
    if opening_credit_score >= CREDIT_MAX and change > 0:
        return 0
    return int(change)


def compute_daily_debt_obligation(db: Session, player_id: str | UUID, day: int) -> dict:
    """Compute deterministic debt due + context factors for one player/day."""
    if day <= 0:
        raise DebtCreditValidationError("day must be greater than 0.")

    player = _resolve_player(db, player_id)
    state = _build_obligation_state(db, player, day)
    return {
        "player_id": state["player_id"],
        "day": state["day"],
        "opening_debt_xgp": float(state["opening_debt_xgp"]),
        "opening_credit_score": int(state["opening_credit_score"]),
        "cash_available_xgp": float(state["cash_available_xgp"]),
        "payment_due_xgp": float(state["payment_due_xgp"]),
        "daily_interest_rate": float(state["daily_interest_rate"]),
        "budget_pressure_score": float(state["budget_pressure_score"]),
        "employed_flag": bool(state["employed_flag"]),
        "monthly_pay_xgp": float(state["monthly_pay_xgp"]),
        "prior_delinquency_streak": int(state["prior_delinquency_streak"]),
    }


def apply_daily_debt_and_credit(
    db: Session,
    player_id: str | UUID,
    day: int,
    *,
    commit: bool = True,
    mutate_player: bool = True,
    available_cash_xgp: Decimal | float | int | None = None,
    budget_pressure_override: Decimal | float | None = None,
    employed_override: bool | None = None,
    monthly_pay_override: Decimal | float | None = None,
) -> dict:
    """Apply one day of debt pressure + credit movement with idempotent logging."""
    if day <= 0:
        raise DebtCreditValidationError("day must be greater than 0.")

    try:
        player = _resolve_player(db, player_id)

        existing = (
            db.query(DebtCreditLog)
            .filter(
                DebtCreditLog.player_id == player.id,
                DebtCreditLog.day == day,
            )
            .first()
        )
        if existing is not None:
            payload = _serialize_log(existing)
            payload["already_processed"] = True
            payload["player_mutation_applied"] = bool(_parse_notes(existing.notes_json).get("player_mutation_applied", True))
            return payload

        state = _build_obligation_state(db, player, day)

        opening_debt = state["opening_debt_xgp"]
        opening_credit = int(state["opening_credit_score"])
        payment_due = state["payment_due_xgp"]
        prior_streak = int(state["prior_delinquency_streak"])

        pressure_score = (
            _q4(_d(budget_pressure_override))
            if budget_pressure_override is not None
            else _q4(_d(state["budget_pressure_score"]))
        )
        employed_flag = bool(state["employed_flag"]) if employed_override is None else bool(employed_override)
        monthly_pay = _money(_d(monthly_pay_override)) if monthly_pay_override is not None else _money(_d(state["monthly_pay_xgp"]))

        available_cash = _money(_d(available_cash_xgp)) if available_cash_xgp is not None else _money(_d(player.cash_xgp))
        if available_cash < Decimal("0.00"):
            available_cash = Decimal("0.00")

        if opening_debt <= Decimal("0.00"):
            payment_made = Decimal("0.00")
            payment_status = "no_debt"
            interest_added = Decimal("0.00")
            ending_debt = Decimal("0.00")
            credit_change = 0
            ending_credit = opening_credit
            delinquency_flag = False
            daily_interest_rate = Decimal("0.0000")
        else:
            payment_made, payment_status = _determine_payment(
                payment_due_xgp=payment_due,
                available_cash_xgp=available_cash,
                budget_pressure_score=pressure_score,
                employed_flag=employed_flag,
            )
            payment_made = _money(min(payment_due, max(Decimal("0.00"), payment_made)))

            daily_interest_rate = _compute_daily_interest_rate(
                opening_credit_score=opening_credit,
                pressure_score=pressure_score,
                prior_delinquency_streak=prior_streak,
                employed_flag=employed_flag,
            )

            principal_after_payment = _money(max(Decimal("0.00"), opening_debt - payment_made))
            interest_added = _money(principal_after_payment * daily_interest_rate)
            ending_debt = _money(principal_after_payment + interest_added)

            delinquency_flag = payment_status in {"paid_partial", "missed"}
            credit_change = _compute_credit_change(
                payment_status=payment_status,
                opening_credit_score=opening_credit,
                opening_debt_xgp=opening_debt,
                budget_pressure_score=pressure_score,
                prior_delinquency_streak=prior_streak,
                monthly_pay_xgp=monthly_pay,
            )
            ending_credit = _clamp_int(opening_credit + credit_change, CREDIT_MIN, CREDIT_MAX)

        delinquency_streak_after = (prior_streak + 1) if delinquency_flag else 0

        notes = {
            "daily_interest_rate": float(daily_interest_rate),
            "budget_pressure_score": float(pressure_score),
            "available_cash_considered_xgp": float(available_cash),
            "employed_flag": bool(employed_flag),
            "monthly_pay_xgp": float(monthly_pay),
            "prior_delinquency_streak": int(prior_streak),
            "delinquency_streak_after": int(delinquency_streak_after),
            "player_mutation_applied": bool(mutate_player),
            "used_budget_override": budget_pressure_override is not None,
            "used_employment_override": employed_override is not None,
            "used_monthly_pay_override": monthly_pay_override is not None,
        }

        row = DebtCreditLog(
            player_id=player.id,
            day=int(day),
            opening_debt_xgp=opening_debt,
            payment_due_xgp=payment_due,
            payment_made_xgp=payment_made,
            interest_added_xgp=interest_added,
            ending_debt_xgp=ending_debt,
            payment_status=payment_status,
            opening_credit_score=opening_credit,
            credit_score_change=credit_change,
            ending_credit_score=ending_credit,
            delinquency_flag=bool(delinquency_flag),
            notes_json=json.dumps(notes),
        )
        db.add(row)

        if mutate_player:
            cash_before = _money(_d(player.cash_xgp))
            player.cash_xgp = _money(max(Decimal("0.00"), cash_before - payment_made))
            player.debt_xgp = ending_debt
            player.credit_score = ending_credit
            player.net_worth_xgp = _money(
                _d(player.cash_xgp) + _d(player.bank_savings_xgp) - _d(player.debt_xgp)
            )

        db.flush()

        if commit:
            db.commit()
            db.refresh(row)

        payload = _serialize_log(row)
        payload["already_processed"] = False
        payload["player_mutation_applied"] = bool(mutate_player)
        return payload

    except DebtCreditError:
        if commit:
            db.rollback()
        raise
    except Exception as exc:
        if commit:
            db.rollback()
        raise DebtCreditError("Unexpected debt/credit processing error.") from exc


def get_player_debt_credit_summary(db: Session, player_id: str | UUID) -> dict:
    """Return current debt/credit state with latest debt-credit processing snapshot."""
    player = _resolve_player(db, player_id)

    latest = (
        db.query(DebtCreditLog)
        .filter(DebtCreditLog.player_id == player.id)
        .order_by(DebtCreditLog.day.desc(), DebtCreditLog.created_at.desc())
        .first()
    )

    payload = {
        "player_id": str(player.id),
        "current_debt_xgp": float(_money(_d(player.debt_xgp))),
        "current_credit_score": int(_clamp_int(int(player.credit_score or 650), CREDIT_MIN, CREDIT_MAX)),
        "latest_day": None,
        "opening_debt_xgp": None,
        "payment_due_xgp": None,
        "payment_made_xgp": None,
        "interest_added_xgp": None,
        "ending_debt_xgp": None,
        "payment_status": None,
        "opening_credit_score": None,
        "credit_score_change": None,
        "ending_credit_score": None,
        "delinquency_flag": None,
    }

    if latest is None:
        return payload

    latest_payload = _serialize_log(latest)
    payload.update(
        {
            "latest_day": latest_payload["day"],
            "opening_debt_xgp": latest_payload["opening_debt_xgp"],
            "payment_due_xgp": latest_payload["payment_due_xgp"],
            "payment_made_xgp": latest_payload["payment_made_xgp"],
            "interest_added_xgp": latest_payload["interest_added_xgp"],
            "ending_debt_xgp": latest_payload["ending_debt_xgp"],
            "payment_status": latest_payload["payment_status"],
            "opening_credit_score": latest_payload["opening_credit_score"],
            "credit_score_change": latest_payload["credit_score_change"],
            "ending_credit_score": latest_payload["ending_credit_score"],
            "delinquency_flag": latest_payload["delinquency_flag"],
        }
    )
    return payload


def get_player_debt_credit_logs(db: Session, player_id: str | UUID, limit: int = 20) -> dict:
    """Return the latest debt-credit logs for a player."""
    player = _resolve_player(db, player_id)

    rows = (
        db.query(DebtCreditLog)
        .filter(DebtCreditLog.player_id == player.id)
        .order_by(DebtCreditLog.day.desc(), DebtCreditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "player_id": str(player.id),
        "count": len(rows),
        "logs": [_serialize_log(row) for row in rows],
    }


def _parse_notes(notes_json: str | None) -> dict:
    if not notes_json:
        return {}
    try:
        payload = json.loads(notes_json)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _serialize_log(row: DebtCreditLog) -> dict:
    return {
        "id": str(row.id),
        "player_id": str(row.player_id),
        "day": int(row.day),
        "opening_debt_xgp": float(_money(_d(row.opening_debt_xgp))),
        "payment_due_xgp": float(_money(_d(row.payment_due_xgp))),
        "payment_made_xgp": float(_money(_d(row.payment_made_xgp))),
        "interest_added_xgp": float(_money(_d(row.interest_added_xgp))),
        "ending_debt_xgp": float(_money(_d(row.ending_debt_xgp))),
        "payment_status": str(row.payment_status),
        "opening_credit_score": int(row.opening_credit_score),
        "credit_score_change": int(row.credit_score_change),
        "ending_credit_score": int(row.ending_credit_score),
        "delinquency_flag": bool(row.delinquency_flag),
        "notes_json": row.notes_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
