"""Step 21 economy telemetry and player viability metrics service."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.balance_config import TELEMETRY_CONFIG, get_balance_profile_metadata
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.financial_distress_log import FinancialDistressLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState

MONEY_Q = Decimal("0.01")
Q4 = Decimal("0.0001")

GAME_EPOCH = date(2026, 1, 1)


class EconomyTelemetryError(Exception):
    """Base exception for balance telemetry operations."""


class EconomyTelemetryNotFoundError(EconomyTelemetryError):
    """Raised when player/resources are missing."""


class EconomyTelemetryValidationError(EconomyTelemetryError):
    """Raised when input payloads are invalid."""


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


def _date_to_day(as_of_date: date) -> int:
    return int((as_of_date - GAME_EPOCH).days) + 1


def _day_to_date(day: int) -> date:
    if int(day) <= 0:
        raise EconomyTelemetryValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _resolve_day(db: Session, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        day = _date_to_day(as_of_date)
        if day <= 0:
            raise EconomyTelemetryValidationError("as_of_date must be on or after game epoch.")
        return int(day), as_of_date

    latest_macro_day = db.query(func.max(MacroDailyState.day)).scalar()
    latest_settlement_day = db.query(func.max(DailySettlementLog.day_number)).scalar()
    day = int(max(int(latest_macro_day or 1), int(latest_settlement_day or 1)))
    return day, _day_to_date(day)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise EconomyTelemetryNotFoundError("Player not found.") from exc
    row = db.query(Player).filter(Player.id == pid).first()
    if row is None:
        raise EconomyTelemetryNotFoundError("Player not found.")
    return row


def _compute_metrics_for_day(db: Session, day: int, resolved_date: date) -> dict:
    window_days = int(TELEMETRY_CONFIG.get("default_window_days", 14))
    window_start = max(1, int(day) - window_days + 1)

    basket_rows = (
        db.query(BasketDailyPrice)
        .filter(BasketDailyPrice.day >= window_start, BasketDailyPrice.day <= int(day))
        .all()
    )
    basket_count = max(1, len(basket_rows))
    avg_abs_daily_change = (
        sum((abs(_d(row.daily_change_pct)) for row in basket_rows), Decimal("0")) / Decimal(str(basket_count))
    )
    avg_price_deviation = (
        sum((abs(_d(row.price_index) - Decimal("10.0")) for row in basket_rows), Decimal("0")) / Decimal(str(basket_count))
    )
    average_basket_inflation_pressure = _clamp(
        (avg_abs_daily_change * Decimal("8.5")) + (avg_price_deviation * Decimal("2.4")),
        Decimal("0"),
        Decimal("100"),
    )
    basket_volatility_index = _clamp(avg_abs_daily_change * Decimal("11.5"), Decimal("0"), Decimal("100"))

    employment_rows = (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.day >= window_start, PlayerEmploymentState.day <= int(day))
        .all()
    )
    spread_by_day: dict[int, list[Decimal]] = {}
    for row in employment_rows:
        spread_by_day.setdefault(int(row.day), []).append(_d(getattr(row, "opportunity_score", 1)))

    spreads: list[Decimal] = []
    for values in spread_by_day.values():
        if not values:
            continue
        spreads.append(max(values) - min(values))

    if spreads:
        avg_spread = sum(spreads, Decimal("0")) / Decimal(str(len(spreads)))
        job_opportunity_spread = _clamp(avg_spread * Decimal("100"), Decimal("0"), Decimal("100"))
    else:
        job_opportunity_spread = Decimal("0")

    business_rows = (
        db.query(BusinessDailyLog)
        .filter(BusinessDailyLog.day >= window_start, BusinessDailyLog.day <= int(day))
        .all()
    )
    pressure_components: list[Decimal] = []
    business_profit_by_type: dict[str, Decimal] = {}
    for row in business_rows:
        revenue = _money(_d(row.gross_revenue_xgp))
        total_cost = _money(
            _d(row.input_cost_xgp)
            + _d(row.overhead_cost_xgp)
            + _d(row.spoilage_cost_xgp)
            + _d(row.fuel_cost_xgp)
            + _d(getattr(row, "maintenance_cost_xgp", 0))
        )
        if revenue > Decimal("0"):
            margin = (revenue - total_cost) / revenue
            pressure = _clamp((Decimal("1.0") - margin) * Decimal("100"), Decimal("0"), Decimal("100"))
        else:
            pressure = Decimal("85") if total_cost > Decimal("0") else Decimal("0")
        pressure_components.append(pressure)
        btype = str(getattr(row, "business_type", "unknown") or "unknown").strip().lower()
        business_profit_by_type[btype] = business_profit_by_type.get(btype, Decimal("0")) + _money(_d(row.net_profit_xgp))

    if pressure_components:
        business_margin_pressure_index = _clamp(
            sum(pressure_components, Decimal("0")) / Decimal(str(len(pressure_components))),
            Decimal("0"),
            Decimal("100"),
        )
    else:
        business_margin_pressure_index = Decimal("0")

    players = db.query(Player).all()
    if players:
        average_stress_burden = _clamp(
            sum((_d(player.stress) for player in players), Decimal("0")) / Decimal(str(len(players))),
            Decimal("0"),
            Decimal("100"),
        )
        average_distress_burden = _clamp(
            sum((_d(getattr(player, "distress_score", 0)) for player in players), Decimal("0")) / Decimal(str(len(players))),
            Decimal("0"),
            Decimal("100"),
        )
    else:
        average_stress_burden = Decimal("0")
        average_distress_burden = Decimal("0")

    distress_rows = (
        db.query(FinancialDistressLog)
        .filter(FinancialDistressLog.day >= window_start, FinancialDistressLog.day <= int(day))
        .all()
    )
    missed_rate = Decimal("0")
    recovery_success_proxy = Decimal("0.50")
    if distress_rows:
        total_rows = Decimal(str(len(distress_rows)))
        missed_rate = _clamp(
            sum((Decimal("1") for row in distress_rows if bool(row.debt_payment_missed)), Decimal("0")) / total_rows,
            Decimal("0"),
            Decimal("1"),
        )
        recovery_days = Decimal("0")
        for row in distress_rows:
            improved = (_d(row.distress_score_after) <= _d(row.distress_score_before))
            stable_pay = (not bool(row.debt_payment_missed)) and int(row.credit_score_delta or 0) >= 0
            if improved or stable_pay:
                recovery_days += Decimal("1")
        recovery_success_proxy = _clamp(recovery_days / total_rows, Decimal("0"), Decimal("1"))

    stress_norm = average_stress_burden / Decimal("100")
    distress_norm = average_distress_burden / Decimal("100")
    margin_norm = business_margin_pressure_index / Decimal("100")

    economy_harshness_score = _clamp(
        Decimal("100")
        * (
            (Decimal("0.30") * stress_norm)
            + (Decimal("0.30") * distress_norm)
            + (Decimal("0.22") * margin_norm)
            + (Decimal("0.18") * missed_rate)
        ),
        Decimal("0"),
        Decimal("100"),
    )
    economy_softness_score = _clamp(
        Decimal("100")
        * (
            (Decimal("0.40") * recovery_success_proxy)
            + (Decimal("0.20") * (Decimal("1") - missed_rate))
            + (Decimal("0.20") * (Decimal("1") - distress_norm))
            + (Decimal("0.20") * (Decimal("1") - stress_norm))
        ),
        Decimal("0"),
        Decimal("100"),
    )

    from app.engine.exploit_detection_service import detect_system_dominance_flags

    system_dominance = detect_system_dominance_flags(db=db, as_of_date=resolved_date, days_window=window_days)
    dominant_flags = list(system_dominance.get("dominant_flags", []))
    if economy_harshness_score >= _d(TELEMETRY_CONFIG.get("harshness_alert", 70)):
        dominant_flags.append("economy_harshness_high")
    if economy_softness_score >= _d(TELEMETRY_CONFIG.get("softness_alert", 70)):
        dominant_flags.append("economy_softness_high")

    dominant_businesses = sorted(
        (
            {"business_type": key, "net_profit_xgp": float(_money(value))}
            for key, value in business_profit_by_type.items()
        ),
        key=lambda item: item["net_profit_xgp"],
        reverse=True,
    )

    profile_meta = get_balance_profile_metadata()
    return {
        "as_of_date": resolved_date.isoformat(),
        **profile_meta,
        "average_basket_inflation_pressure": float(_q4(average_basket_inflation_pressure)),
        "basket_volatility_index": float(_q4(basket_volatility_index)),
        "job_opportunity_spread": float(_q4(job_opportunity_spread)),
        "business_margin_pressure_index": float(_q4(business_margin_pressure_index)),
        "average_stress_burden": float(_q4(average_stress_burden)),
        "average_distress_burden": float(_q4(average_distress_burden)),
        "recovery_success_proxy": float(_q4(recovery_success_proxy)),
        "economy_harshness_score": float(_q4(economy_harshness_score)),
        "economy_softness_score": float(_q4(economy_softness_score)),
        "dominant_flags": sorted(set(dominant_flags)),
        "debug_meta": {
            "window_start_day": int(window_start),
            "window_end_day": int(day),
            "basket_rows": int(len(basket_rows)),
            "employment_rows": int(len(employment_rows)),
            "business_rows": int(len(business_rows)),
            "distress_rows": int(len(distress_rows)),
            "missed_payment_rate": float(_q4(missed_rate)),
            "dominant_businesses": dominant_businesses[:5],
            "system_dominance": system_dominance,
        },
    }


def compute_daily_economy_health_metrics(
    db: Session,
    as_of_date: date | None = None,
) -> dict:
    """Compute one deterministic economy-health telemetry snapshot."""
    day, resolved_date = _resolve_day(db, as_of_date=as_of_date)
    return _compute_metrics_for_day(db=db, day=day, resolved_date=resolved_date)


def compute_player_viability_metrics(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compute player-level viability metrics from recent settlement and life state."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date=as_of_date)

    window_days = int(TELEMETRY_CONFIG.get("viability_window_days", 7))
    start_day = max(1, int(day) - window_days + 1)

    settlements = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number >= start_day,
            DailySettlementLog.day_number <= int(day),
        )
        .order_by(DailySettlementLog.day_number.asc())
        .all()
    )

    if settlements:
        avg_daily_expenses = (
            sum((_d(row.expenses_xgp) for row in settlements), Decimal("0"))
            / Decimal(str(len(settlements)))
        )
        avg_daily_income = (
            sum(
                (
                    _d(row.income_xgp)
                    + _d(getattr(row, "side_income_net_xgp", 0))
                    + _d(getattr(row, "business_net_profit_xgp", 0))
                    for row in settlements
                ),
                Decimal("0"),
            )
            / Decimal(str(len(settlements)))
        )
        net_series = [
            _d(row.income_xgp)
            + _d(getattr(row, "side_income_net_xgp", 0))
            + _d(getattr(row, "business_net_profit_xgp", 0))
            - _d(row.expenses_xgp)
            for row in settlements
        ]
    else:
        avg_daily_expenses = Decimal("20")
        avg_daily_income = Decimal("0")
        net_series = [Decimal("0")]

    cash_now = _money(_d(player.cash_xgp))
    days_cash_cushion = _clamp(
        cash_now / max(Decimal("1.0"), avg_daily_expenses),
        Decimal("0.0"),
        Decimal("180.0"),
    )
    debt_pressure_ratio = _clamp(
        _d(getattr(player, "required_daily_debt_payment_xgp", 0)) / max(Decimal("1.0"), avg_daily_income),
        Decimal("0.0"),
        Decimal("10.0"),
    )

    series_n = Decimal(str(max(1, len(net_series))))
    mean_net = sum(net_series, Decimal("0")) / series_n
    variance = sum(((item - mean_net) ** 2 for item in net_series), Decimal("0")) / series_n
    volatility = variance.sqrt() if variance > Decimal("0") else Decimal("0")
    stability_penalty = _clamp(volatility / max(Decimal("5.0"), abs(mean_net) + Decimal("5.0")), Decimal("0"), Decimal("2.0"))
    net_income_stability_score = _clamp(Decimal("100") - (stability_penalty * Decimal("55")), Decimal("0"), Decimal("100"))

    burnout_danger_score = _clamp(
        (Decimal("0.45") * _d(player.stress))
        + (Decimal("0.30") * (Decimal("100") - _d(player.health)))
        + (Decimal("0.25") * (_d(getattr(player, "burnout_risk", 0)) * Decimal("100"))),
        Decimal("0"),
        Decimal("100"),
    )

    latest_employment = (
        db.query(PlayerEmploymentState)
        .filter(PlayerEmploymentState.player_id == player.id, PlayerEmploymentState.day <= int(day))
        .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
        .first()
    )
    skill_level = int(getattr(latest_employment, "skill_level", 1) or 1)
    promotion_chance = _d(getattr(latest_employment, "promotion_chance_pct", 0))
    upward_mobility_score = _clamp(
        Decimal("50")
        + (Decimal(str(skill_level)) * Decimal("6"))
        + (promotion_chance * Decimal("0.80"))
        - (_d(getattr(player, "distress_score", 0)) * Decimal("0.35"))
        - (_d(getattr(player, "opportunity_access_penalty", 0)) * Decimal("60")),
        Decimal("0"),
        Decimal("100"),
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "days_cash_cushion": float(_q4(days_cash_cushion)),
        "debt_pressure_ratio": float(_q4(debt_pressure_ratio)),
        "net_income_stability_score": float(_q4(net_income_stability_score)),
        "burnout_danger_score": float(_q4(burnout_danger_score)),
        "upward_mobility_score": float(_q4(upward_mobility_score)),
        "debug_meta": {
            "window_start_day": int(start_day),
            "window_end_day": int(day),
            "avg_daily_expenses_xgp": float(_money(avg_daily_expenses)),
            "avg_daily_income_xgp": float(_money(avg_daily_income)),
            "cash_xgp": float(_money(cash_now)),
            "mean_daily_net_xgp": float(_money(mean_net)),
            "net_volatility_xgp": float(_money(volatility)),
            "skill_level": int(skill_level),
            "promotion_chance_pct": float(_q4(promotion_chance)),
        },
    }


def compute_balance_flags(metrics: dict) -> dict:
    """Compute bounded high-level balance flags from one telemetry snapshot."""
    harshness = _clamp(_d(metrics.get("economy_harshness_score", 0)), Decimal("0"), Decimal("100"))
    softness = _clamp(_d(metrics.get("economy_softness_score", 0)), Decimal("0"), Decimal("100"))
    recovery = _clamp(_d(metrics.get("recovery_success_proxy", 0.5)), Decimal("0"), Decimal("1"))
    stress = _clamp(_d(metrics.get("average_stress_burden", 0)), Decimal("0"), Decimal("100"))
    distress = _clamp(_d(metrics.get("average_distress_burden", 0)), Decimal("0"), Decimal("100"))

    harsh_alert = _d(TELEMETRY_CONFIG.get("harshness_alert", 70))
    soft_alert = _d(TELEMETRY_CONFIG.get("softness_alert", 70))

    flags = {
        "economy_too_harsh": bool(harshness >= harsh_alert and recovery < Decimal("0.45")),
        "economy_too_soft": bool(softness >= soft_alert and distress < Decimal("35") and stress < Decimal("40")),
        "recovery_too_hard": bool(recovery < Decimal("0.35") and distress >= Decimal("55")),
        "tension_too_low": bool(stress < Decimal("30") and distress < Decimal("25") and softness >= Decimal("62")),
    }
    active = sorted([name for name, enabled in flags.items() if enabled])
    return {
        "flags": flags,
        "active_flags": active,
        "debug_meta": {
            "harshness": float(_q4(harshness)),
            "softness": float(_q4(softness)),
            "recovery_success_proxy": float(_q4(recovery)),
            "average_stress_burden": float(_q4(stress)),
            "average_distress_burden": float(_q4(distress)),
        },
    }


def get_recent_economy_telemetry(
    db: Session,
    *,
    days: int = 14,
    as_of_date: date | None = None,
) -> dict:
    """Return deterministic trailing telemetry snapshots for balancing dashboards."""
    if int(days) <= 0:
        raise EconomyTelemetryValidationError("days must be greater than 0.")
    end_day, _ = _resolve_day(db, as_of_date=as_of_date)
    start_day = max(1, int(end_day) - int(days) + 1)

    entries = []
    for day in range(start_day, end_day + 1):
        entries.append(_compute_metrics_for_day(db=db, day=day, resolved_date=_day_to_date(day)))

    return {
        "as_of_date": _day_to_date(end_day).isoformat(),
        **get_balance_profile_metadata(),
        "entries": entries,
    }


def get_player_balance_snapshot(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Return player viability metrics plus exploit flags for Step 21 tooling."""
    viability = compute_player_viability_metrics(db=db, player_id=player_id, as_of_date=as_of_date)

    from app.engine.exploit_detection_service import detect_player_exploit_flags

    flags_payload = detect_player_exploit_flags(db=db, player_id=player_id, as_of_date=as_of_date)
    exploit_flags = {
        "rideshare_overfarm_flag": bool(flags_payload.get("rideshare_overfarm_flag", False)),
        "food_truck_margin_abuse_flag": bool(flags_payload.get("food_truck_margin_abuse_flag", False)),
        "fruit_shop_markup_abuse_flag": bool(flags_payload.get("fruit_shop_markup_abuse_flag", False)),
        "zero_rest_grind_flag": bool(flags_payload.get("zero_rest_grind_flag", False)),
        "debt_ignore_abuse_flag": bool(flags_payload.get("debt_ignore_abuse_flag", False)),
        "too_fast_promotion_flag": bool(flags_payload.get("too_fast_promotion_flag", False)),
        "region_switch_abuse_flag": bool(flags_payload.get("region_switch_abuse_flag", False)),
        "event_chain_prediction_advantage_flag": bool(
            flags_payload.get("event_chain_prediction_advantage_flag", False)
        ),
    }

    return {
        "player_id": viability["player_id"],
        "as_of_date": viability["as_of_date"],
        "days_cash_cushion": viability["days_cash_cushion"],
        "debt_pressure_ratio": viability["debt_pressure_ratio"],
        "net_income_stability_score": viability["net_income_stability_score"],
        "burnout_danger_score": viability["burnout_danger_score"],
        "upward_mobility_score": viability["upward_mobility_score"],
        "exploit_flags": exploit_flags,
        "debug_meta": {
            **viability.get("debug_meta", {}),
            "exploit_debug": flags_payload.get("debug_meta", {}),
            **get_balance_profile_metadata(),
        },
    }
