"""Step 27 economy presentation + market feel composition service.

This service is intentionally read-only. It translates existing simulation
state into player-facing explainability payloads without mutating core game
systems.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.housing_region_config import REGION_CONFIG
from app.engine.supply_chain_graph_service import (
    build_supply_chain_daily_summary,
    build_supply_chain_story_summary,
)
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_housing_state import PlayerHousingState
from app.services.daily_brief_service import build_daily_economy_brief

GAME_EPOCH = date(2026, 1, 1)
Q4 = Decimal("0.0001")
MONEY_Q = Decimal("0.01")
logger = logging.getLogger(__name__)

BASKET_ORDER: tuple[BasketType, ...] = (
    BasketType.essentials,
    BasketType.protein,
    BasketType.produce,
    BasketType.convenience,
)


class EconomyPresentationError(Exception):
    """Base exception for Step 27 presentation composition."""


class EconomyPresentationNotFoundError(EconomyPresentationError):
    """Raised when player or required state cannot be found."""


class EconomyPresentationValidationError(EconomyPresentationError):
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
        raise EconomyPresentationValidationError("day must be greater than 0.")
    return GAME_EPOCH + timedelta(days=int(day) - 1)


def _date_to_day(as_of_date: date) -> int:
    day = int((as_of_date - GAME_EPOCH).days) + 1
    if day <= 0:
        raise EconomyPresentationValidationError("as_of_date must be on or after game epoch.")
    return day


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise EconomyPresentationNotFoundError("Player not found.") from exc
    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise EconomyPresentationNotFoundError("Player not found.")
    return player


def _resolve_day(db: Session, as_of_date: date | None = None) -> tuple[int, date]:
    if as_of_date is not None:
        return _date_to_day(as_of_date), as_of_date

    latest_macro = db.query(func.max(MacroDailyState.day)).scalar()
    latest_baskets = db.query(func.max(BasketDailyPrice.day)).scalar()
    latest_housing = db.query(func.max(HousingDailyLog.day)).scalar()
    latest_business = db.query(func.max(BusinessDailyLog.day)).scalar()
    latest_settlement = db.query(func.max(DailySettlementLog.day_number)).scalar()
    latest = max(
        int(latest_macro or 0),
        int(latest_baskets or 0),
        int(latest_housing or 0),
        int(latest_business or 0),
        int(latest_settlement or 0),
        1,
    )
    return latest, _day_to_date(latest)


def _latest_macro_row(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= int(day))
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )
    if row is not None:
        return row
    return db.query(MacroDailyState).order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc()).first()


def _previous_macro_row(db: Session, day: int) -> MacroDailyState | None:
    return (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day < int(day))
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )


def _latest_basket_row(db: Session, basket_type: BasketType, day: int) -> BasketDailyPrice | None:
    return (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day <= int(day),
        )
        .order_by(BasketDailyPrice.day.desc(), BasketDailyPrice.created_at.desc())
        .first()
    )


def _previous_basket_row(db: Session, basket_type: BasketType, day: int) -> BasketDailyPrice | None:
    return (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day < int(day),
        )
        .order_by(BasketDailyPrice.day.desc(), BasketDailyPrice.created_at.desc())
        .first()
    )


def _latest_housing_row(db: Session, player_id: UUID, day: int) -> HousingDailyLog | None:
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


def _resolve_region_key(player: Player, housing_state: PlayerHousingState | None) -> str:
    region = getattr(housing_state, "region", None) or getattr(player, "region", None) or "suburban"
    return str(region).strip().lower() or "suburban"


def _settlement_digest(settlement: DailySettlementLog | None) -> dict | None:
    if settlement is None:
        return None

    income = _money(_d(getattr(settlement, "income_xgp", 0)))
    expenses = _money(_d(getattr(settlement, "expenses_xgp", 0)))
    net_change = _money(income - expenses)

    return {
        "day_number": int(getattr(settlement, "day_number", 0) or 0),
        "income_xgp": float(income),
        "expenses_xgp": float(expenses),
        "net_change_xgp": float(net_change),
        "cash_after_xgp": float(_money(_d(getattr(settlement, "cash_after", 0)))),
        "stress_change": int(getattr(settlement, "stress_change", 0) or 0),
        "health_change": int(getattr(settlement, "health_change", 0) or 0),
        "debug_meta": {
            "source": "daily_settlement_logs",
        },
    }


def _dedupe_nonempty(items: list[str], limit: int = 6) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in items:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
        if len(ordered) >= limit:
            break
    return ordered


def _build_mobile_signal_lists(
    market: dict,
    supply_chain_summary: dict,
    supply_chain_story: dict,
    daily_brief: dict,
) -> tuple[list[str], list[str]]:
    warnings = _dedupe_nonempty([
        *(f"Pressure: {item}." for item in market.get("top_losers", [])[:2]),
        *(str(item) for item in supply_chain_story.get("bottleneck_highlights", [])[:2]),
        *(str(item) for item in supply_chain_story.get("basket_impact_notes", [])[:2]),
        (
            f"Top bottleneck: {str(supply_chain_summary.get('top_bottleneck_node') or '').replace('_', ' ').title()}."
            if supply_chain_summary.get("top_bottleneck_node")
            else ""
        ),
    ])

    opportunities = _dedupe_nonempty([
        *(f"Demand tailwind: {item}." for item in market.get("top_winners", [])[:2]),
        *(str(item) for item in supply_chain_story.get("job_opportunity_hints", [])[:2]),
        *(str(item) for item in supply_chain_story.get("practical_current_actions", [])[:2]),
        (
            f"Best job opportunity today: {str(supply_chain_summary.get('best_job_opportunity') or '').replace('_', ' ').title()}."
            if supply_chain_summary.get("best_job_opportunity")
            else ""
        ),
        *(
            f"Watch {str(item).replace('_', ' ')} for changing conditions."
            for item in daily_brief.get("top_job_changes", [])[:1]
        ),
    ])

    return warnings, opportunities


def _trend_label(delta: Decimal, *, tolerance: Decimal) -> str:
    if delta > tolerance:
        return "rising"
    if delta < -tolerance:
        return "falling"
    return "stable"


def _pressure_label(score: Decimal) -> str:
    value = _clamp(score, Decimal("0"), Decimal("100"))
    if value >= Decimal("75"):
        return "high"
    if value >= Decimal("45"):
        return "moderate"
    return "low"


def _volatility_label(abs_daily_change_pct: Decimal) -> str:
    change = abs(abs_daily_change_pct)
    if change >= Decimal("2.8"):
        return "high"
    if change >= Decimal("1.2"):
        return "moderate"
    return "calm"


def _basket_pressure_label(row: BasketDailyPrice | None) -> str:
    if row is None:
        return "stable"
    drift = abs(_d(row.price_index) - Decimal("10.00")) * Decimal("3.0")
    change = abs(_d(row.daily_change_pct)) * Decimal("12.0")
    supply = abs(_d(row.supply_pressure) - Decimal("1.00")) * Decimal("30.0")
    demand = abs(_d(row.demand_pressure) - Decimal("1.00")) * Decimal("22.0")
    score = _clamp(drift + change + supply + demand, Decimal("0"), Decimal("100"))
    return _pressure_label(score)


def _driver_from_row(
    basket_key: str,
    row: BasketDailyPrice | None,
    macro: MacroDailyState | None,
) -> str:
    supply_gap = abs(_d(getattr(row, "supply_pressure", 1)) - Decimal("1.0"))
    demand_gap = abs(_d(getattr(row, "demand_pressure", 1)) - Decimal("1.0"))
    oil_gap = abs((_d(getattr(macro, "oil_index", 100)) / Decimal("100")) - Decimal("1.0"))
    supply_stress = _d(getattr(macro, "supply_chain_stress", 0))
    confidence = _d(getattr(macro, "consumer_confidence", 50))

    if basket_key == "produce" and (supply_stress >= Decimal("1.00") or supply_gap >= demand_gap):
        return "transport and supply bottlenecks"
    if basket_key == "protein" and (oil_gap >= Decimal("0.08") or supply_gap >= Decimal("0.05")):
        return "fuel and logistics drag"
    if basket_key == "convenience" and abs(confidence - Decimal("50")) >= Decimal("6.00"):
        return "consumer sentiment swings"
    if demand_gap > supply_gap:
        return "demand pressure in household spending"
    if supply_gap > Decimal("0.03"):
        return "supplier pressure and inventory flow"
    return "broad inflation and normal seasonality"


def _price_impact_text(
    basket_key: str,
    trend_label: str,
    volatility_label: str,
) -> str:
    if basket_key == "produce":
        if trend_label == "rising":
            return "Produce costs are rising; Fruit Shop margins face tighter pressure."
        if trend_label == "falling":
            return "Produce costs are easing; Fruit Shop margins get breathing room."
        return f"Produce is {volatility_label}; watch spoilage and purchase timing."
    if basket_key == "essentials":
        if trend_label == "rising":
            return "Essentials are getting pricier; daily cash-flow flexibility narrows."
        if trend_label == "falling":
            return "Essentials are easing; household cost pressure softens."
        return "Essentials are stable; budget discipline still matters."
    if basket_key == "protein":
        if trend_label == "rising":
            return "Protein inflation increases Food Truck ingredient drag."
        if trend_label == "falling":
            return "Protein relief supports Food Truck unit economics."
        return f"Protein prices are {volatility_label}; menu strategy matters."
    if trend_label == "rising":
        return "Convenience costs are climbing and can quietly erode debt-control progress."
    if trend_label == "falling":
        return "Convenience pricing is cooling, reducing impulse-spend pressure."
    return "Convenience is stable; keep spending intentional."


def _margin_outlook_label(net_score: Decimal) -> str:
    if net_score >= Decimal("0.25"):
        return "favorable"
    if net_score <= Decimal("-0.25"):
        return "pressured"
    return "mixed"


def _demand_outlook_label(score: Decimal) -> str:
    if score >= Decimal("0.20"):
        return "supportive"
    if score <= Decimal("-0.20"):
        return "soft"
    return "stable"


def _cost_outlook_label(score: Decimal) -> str:
    if score >= Decimal("0.75"):
        return "high"
    if score >= Decimal("0.35"):
        return "moderate"
    return "low"


def _future_locked_solution_titles() -> list[str]:
    return [
        "Personal vehicle brand path (locked)",
        "Transportation startup path (locked)",
        "Logistics and mobility venture path (locked)",
        "Player-created commute optimization business (locked)",
    ]


def build_market_overview(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build compact market mood + macro driver summary in player language."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    macro = _latest_macro_row(db, day)
    if macro is None:
        raise EconomyPresentationNotFoundError("No macro state available yet.")
    prev = _previous_macro_row(db, int(macro.day))

    inflation = _d(macro.inflation_rate)
    oil = _d(macro.oil_index)
    unemployment = _d(macro.unemployment_rate)
    confidence = _d(macro.consumer_confidence)
    supply_stress = _d(macro.supply_chain_stress)

    inflation_delta = inflation - _d(getattr(prev, "inflation_rate", inflation))
    oil_delta = oil - _d(getattr(prev, "oil_index", oil))
    unemployment_delta = unemployment - _d(getattr(prev, "unemployment_rate", unemployment))
    confidence_delta = confidence - _d(getattr(prev, "consumer_confidence", confidence))
    supply_delta = supply_stress - _d(getattr(prev, "supply_chain_stress", supply_stress))

    macro_trends = {
        "inflation_direction": _trend_label(inflation_delta, tolerance=Decimal("0.10")),
        "oil_direction": _trend_label(oil_delta, tolerance=Decimal("0.90")),
        "unemployment_direction": _trend_label(unemployment_delta, tolerance=Decimal("0.06")),
        "confidence_direction": _trend_label(confidence_delta, tolerance=Decimal("0.40")),
        "supply_chain_pressure": _trend_label(supply_delta, tolerance=Decimal("0.03")),
    }

    basket_rows: dict[str, BasketDailyPrice | None] = {
        basket.value: _latest_basket_row(db, basket, day) for basket in BASKET_ORDER
    }
    basket_pressure_labels = {
        key: _basket_pressure_label(row) for key, row in basket_rows.items()
    }

    negative_score = Decimal("0")
    positive_score = Decimal("0")
    if inflation > Decimal("3.30") or macro_trends["inflation_direction"] == "rising":
        negative_score += Decimal("1")
    if oil > Decimal("120") or macro_trends["oil_direction"] == "rising":
        negative_score += Decimal("1")
    if confidence < Decimal("46") or macro_trends["confidence_direction"] == "falling":
        negative_score += Decimal("1")
    if unemployment > Decimal("6.2") or macro_trends["unemployment_direction"] == "rising":
        negative_score += Decimal("1")
    if supply_stress > Decimal("1.00") or macro_trends["supply_chain_pressure"] == "rising":
        negative_score += Decimal("1")

    if macro_trends["confidence_direction"] == "rising" and confidence >= Decimal("52"):
        positive_score += Decimal("1")
    if macro_trends["unemployment_direction"] == "falling":
        positive_score += Decimal("1")
    if macro_trends["oil_direction"] == "falling":
        positive_score += Decimal("1")
    if supply_stress <= Decimal("0.80"):
        positive_score += Decimal("1")

    if negative_score - positive_score >= Decimal("2"):
        market_mood = "pressured"
    elif positive_score - negative_score >= Decimal("2"):
        market_mood = "supportive"
    else:
        market_mood = "mixed"

    headline_drivers: list[str] = []
    if macro_trends["oil_direction"] == "rising":
        headline_drivers.append("Oil is rising, lifting transport and fuel drag.")
    if macro_trends["supply_chain_pressure"] == "rising":
        headline_drivers.append("Supply chain pressure is tightening inventory flow.")
    if macro_trends["confidence_direction"] == "falling":
        headline_drivers.append("Consumer confidence softened, reducing discretionary demand.")
    if macro_trends["unemployment_direction"] == "falling":
        headline_drivers.append("Unemployment eased, improving job access momentum.")
    if not headline_drivers:
        headline_drivers.append("Macro signals are broadly stable today.")

    top_winners: list[str] = []
    top_losers: list[str] = []
    if macro_trends["unemployment_direction"] == "falling":
        top_winners.append("Job seekers in dense markets")
    if macro_trends["confidence_direction"] == "rising":
        top_winners.append("Demand-sensitive retail and service work")
    if macro_trends["oil_direction"] == "falling":
        top_winners.append("Fuel-intensive side-income and delivery shifts")
    if basket_pressure_labels.get("produce") == "high":
        top_losers.append("Fruit Shop margin stability")
    if basket_pressure_labels.get("protein") in {"moderate", "high"}:
        top_losers.append("Food Truck ingredient margin")
    if macro_trends["oil_direction"] == "rising":
        top_losers.append("Commute-heavy schedules")
    if not top_winners:
        top_winners.append("Disciplined cash-buffer strategies")
    if not top_losers:
        top_losers.append("High-leverage growth plans")

    short_explainer = (
        f"Market mood is {market_mood}: oil {macro_trends['oil_direction']}, confidence "
        f"{macro_trends['confidence_direction']}, and supply pressure "
        f"{macro_trends['supply_chain_pressure']}."
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "current_market_mood": market_mood,
        "headline_drivers": headline_drivers[:4],
        "top_winners": top_winners[:3],
        "top_losers": top_losers[:3],
        "macro_trend_labels": macro_trends,
        "basket_pressure_labels": basket_pressure_labels,
        "short_explainer": short_explainer,
        "debug_meta": {
            "day": int(day),
            "macro_values": {
                "inflation_rate": float(_q4(inflation)),
                "oil_index": float(_q4(oil)),
                "unemployment_rate": float(_q4(unemployment)),
                "consumer_confidence": float(_q4(confidence)),
                "supply_chain_stress": float(_q4(supply_stress)),
            },
            "macro_deltas": {
                "inflation_delta": float(_q4(inflation_delta)),
                "oil_delta": float(_q4(oil_delta)),
                "unemployment_delta": float(_q4(unemployment_delta)),
                "confidence_delta": float(_q4(confidence_delta)),
                "supply_chain_delta": float(_q4(supply_delta)),
            },
            "scores": {
                "negative_score": float(_q4(negative_score)),
                "positive_score": float(_q4(positive_score)),
            },
        },
    }


def build_price_trend_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build player-readable basket trend summaries and impact framing."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    macro = _latest_macro_row(db, day)

    items: list[dict] = []
    for basket_type in BASKET_ORDER:
        row = _latest_basket_row(db, basket_type, day)
        prev = _previous_basket_row(db, basket_type, int(getattr(row, "day", day)))
        current_level = _d(getattr(row, "price_index", 10))
        current_day = int(getattr(row, "day", day))
        prev_level = _d(getattr(prev, "price_index", current_level))
        daily_change = _d(getattr(row, "daily_change_pct", current_level - prev_level))
        trend = _trend_label(daily_change, tolerance=Decimal("0.12"))
        volatility = _volatility_label(daily_change)
        basket_key = basket_type.value
        primary_driver = _driver_from_row(basket_key, row, macro)
        impact = _price_impact_text(basket_key, trend, volatility)

        items.append(
            {
                "basket_key": basket_key,
                "current_level": float(_q4(current_level)),
                "short_term_trend": trend,
                "volatility_label": volatility,
                "primary_driver": primary_driver,
                "player_impact_summary": impact,
                "debug_meta": {
                    "row_day": int(current_day),
                    "daily_change_pct": float(_q4(daily_change)),
                    "supply_pressure": float(_q4(_d(getattr(row, "supply_pressure", 1)))),
                    "demand_pressure": float(_q4(_d(getattr(row, "demand_pressure", 1)))),
                    "prev_level": float(_q4(prev_level)),
                },
            }
        )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": items,
        "debug_meta": {
            "day": int(day),
            "macro_context": {
                "oil_index": float(_q4(_d(getattr(macro, "oil_index", 100)))) if macro is not None else 100.0,
                "confidence": float(_q4(_d(getattr(macro, "consumer_confidence", 50)))) if macro is not None else 50.0,
                "supply_chain_stress": float(_q4(_d(getattr(macro, "supply_chain_stress", 0)))) if macro is not None else 0.0,
            },
        },
    }


def build_business_margin_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build business environment visibility for fruit shop and food truck."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    macro = _latest_macro_row(db, day)
    housing_state = _active_housing_state(db, player.id)
    region_key = (getattr(housing_state, "region", None) or player.region or "suburban").strip().lower()

    produce_row = _latest_basket_row(db, BasketType.produce, day)
    essentials_row = _latest_basket_row(db, BasketType.essentials, day)
    protein_row = _latest_basket_row(db, BasketType.protein, day)

    produce_price = _d(getattr(produce_row, "price_index", 10))
    essentials_price = _d(getattr(essentials_row, "price_index", 10))
    protein_price = _d(getattr(protein_row, "price_index", 10))
    oil = _d(getattr(macro, "oil_index", 100))
    confidence = _d(getattr(macro, "consumer_confidence", 50))
    supply_stress = _d(getattr(macro, "supply_chain_stress", 0))

    region_business_mod = _d(getattr(housing_state, "business_demand_modifier", 1))
    networking_mod = _d(getattr(housing_state, "networking_modifier", 0))
    region_demand_support = (region_business_mod - Decimal("1.0")) + (networking_mod * Decimal("0.25"))
    confidence_support = (confidence - Decimal("50")) / Decimal("60")

    fruit_cost_score = _clamp(
        (max(Decimal("0"), produce_price - Decimal("10")) / Decimal("4.5"))
        + (max(Decimal("0"), supply_stress - Decimal("0.8")) * Decimal("0.7"))
        + (max(Decimal("0"), oil - Decimal("105")) / Decimal("120")),
        Decimal("0"),
        Decimal("1.5"),
    )
    fruit_demand_score = _clamp(
        confidence_support + region_demand_support + (Decimal("0.05") if region_key == "downtown" else Decimal("-0.02")),
        Decimal("-0.8"),
        Decimal("0.8"),
    )
    fruit_margin_net = _q4(fruit_demand_score - fruit_cost_score)

    truck_cost_score = _clamp(
        (max(Decimal("0"), essentials_price - Decimal("10")) / Decimal("6.0"))
        + (max(Decimal("0"), protein_price - Decimal("10")) / Decimal("6.0"))
        + (max(Decimal("0"), oil - Decimal("100")) / Decimal("80")),
        Decimal("0"),
        Decimal("1.7"),
    )
    truck_demand_score = _clamp(
        (confidence_support * Decimal("0.75"))
        + region_demand_support
        + (Decimal("0.09") if region_key == "downtown" else Decimal("-0.03")),
        Decimal("-0.8"),
        Decimal("0.8"),
    )
    truck_margin_net = _q4(truck_demand_score - truck_cost_score)

    fruit_latest = _latest_business_log(db, player.id, "fruit_shop", day)
    truck_latest = _latest_business_log(db, player.id, "food_truck", day)

    fruit_risks: list[str] = []
    fruit_opps: list[str] = []
    if produce_price >= Decimal("10.8"):
        fruit_risks.append("Produce input costs are elevated.")
    if supply_stress >= Decimal("1.1"):
        fruit_risks.append("Supply bottlenecks can worsen spoilage and restock timing.")
    if fruit_latest is not None and _d(fruit_latest.net_profit_xgp) < Decimal("0"):
        fruit_risks.append("Recent Fruit Shop run closed negative.")
    if confidence >= Decimal("52"):
        fruit_opps.append("Confidence support can lift basket demand.")
    if region_key == "downtown":
        fruit_opps.append("Downtown traffic can improve sell-through.")
    if fruit_latest is not None and _d(fruit_latest.net_profit_xgp) > Decimal("0"):
        fruit_opps.append("Recent Fruit Shop run was profitable.")

    truck_risks: list[str] = []
    truck_opps: list[str] = []
    if oil >= Decimal("112"):
        truck_risks.append("Oil pressure is lifting daily fuel drag.")
    if protein_price >= Decimal("11.8"):
        truck_risks.append("Protein costs are constraining menu margin.")
    if truck_latest is not None and _d(truck_latest.net_profit_xgp) < Decimal("0"):
        truck_risks.append("Recent Food Truck run closed negative.")
    if region_key == "downtown":
        truck_opps.append("Downtown foot traffic supports order volume.")
    if confidence >= Decimal("50"):
        truck_opps.append("Confidence is supportive for ticket conversion.")
    if truck_latest is not None and _d(truck_latest.net_profit_xgp) > Decimal("0"):
        truck_opps.append("Recent Food Truck run was profitable.")

    fruit_item = {
        "business_key": "fruit_shop",
        "margin_outlook": _margin_outlook_label(fruit_margin_net),
        "demand_outlook": _demand_outlook_label(fruit_demand_score),
        "cost_pressure": _cost_outlook_label(fruit_cost_score),
        "risk_factors": fruit_risks[:4],
        "opportunity_factors": fruit_opps[:4],
        "short_explainer": (
            "Fruit Shop margins follow produce input pressure, confidence demand, and neighborhood traffic."
        ),
        "debug_meta": {
            "cost_score": float(_q4(fruit_cost_score)),
            "demand_score": float(_q4(fruit_demand_score)),
            "margin_net_score": float(_q4(fruit_margin_net)),
            "latest_net_profit_xgp": float(_money(_d(getattr(fruit_latest, "net_profit_xgp", 0)))),
        },
    }
    truck_item = {
        "business_key": "food_truck",
        "margin_outlook": _margin_outlook_label(truck_margin_net),
        "demand_outlook": _demand_outlook_label(truck_demand_score),
        "cost_pressure": _cost_outlook_label(truck_cost_score),
        "risk_factors": truck_risks[:4],
        "opportunity_factors": truck_opps[:4],
        "short_explainer": (
            "Food Truck margin depends on essentials/protein inputs, oil-driven fuel drag, and local foot traffic."
        ),
        "debug_meta": {
            "cost_score": float(_q4(truck_cost_score)),
            "demand_score": float(_q4(truck_demand_score)),
            "margin_net_score": float(_q4(truck_margin_net)),
            "latest_net_profit_xgp": float(_money(_d(getattr(truck_latest, "net_profit_xgp", 0)))),
        },
    }

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "items": [fruit_item, truck_item],
        "debug_meta": {
            "day": int(day),
            "region_key": region_key,
            "region_business_modifier": float(_q4(region_business_mod)),
            "networking_modifier": float(_q4(networking_mod)),
        },
    }


def build_commute_pressure_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build commute pressure explainability with congestion and housing tradeoff framing."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    housing_log = _latest_housing_row(db, player.id, day)
    housing_state = _active_housing_state(db, player.id)
    region_key = (
        (getattr(housing_log, "region", None) or getattr(housing_state, "region", None) or player.region or "suburban")
        .strip()
        .lower()
    )

    baseline_hours = _d(getattr(housing_log, "commute_hours", 0))
    if baseline_hours <= Decimal("0"):
        region_cfg = REGION_CONFIG.get(region_key, REGION_CONFIG["suburban"])
        baseline_hours = _q4(_d(region_cfg.commute_hours_baseline))

    total_players = int(db.query(func.count(Player.id)).scalar() or 0)
    active_density = Decimal(str(max(0, total_players - 5))) / Decimal("95")
    congestion_base = _clamp(active_density, Decimal("0.00"), Decimal("0.40"))
    region_density = Decimal("1.15") if region_key == "downtown" else Decimal("0.85")
    congestion_hours = _q4(_clamp(baseline_hours * congestion_base * region_density, Decimal("0.00"), Decimal("1.20")))
    effective_hours = _q4(_clamp(baseline_hours + congestion_hours, Decimal("0.20"), Decimal("4.50")))

    if effective_hours >= Decimal("2.40"):
        pressure_level = "high"
    elif effective_hours >= Decimal("1.40"):
        pressure_level = "moderate"
    else:
        pressure_level = "low"

    stress_signal = _d(getattr(housing_log, "region_stress_delta", getattr(housing_log, "stress_delta", 0)))
    if stress_signal >= Decimal("1.6") or pressure_level == "high":
        stress_impact = "Commute load is materially increasing daily stress pressure."
    elif stress_signal <= Decimal("-0.2"):
        stress_impact = "Current region setup gives slight stress relief from travel load."
    else:
        stress_impact = "Commute impact on stress is noticeable but manageable."

    if effective_hours >= Decimal("2.00"):
        time_impact = "High commute time is consuming action budget and recovery capacity."
    elif effective_hours >= Decimal("1.00"):
        time_impact = "Commute time is a moderate drag on your daily time budget."
    else:
        time_impact = "Commute burden is relatively light right now."

    if region_key == "suburban":
        housing_tradeoff_summary = (
            "Suburban housing is cheaper, but commute drag is higher. Moving or renting closer can save time "
            "at the cost of higher monthly housing expense."
        )
    else:
        housing_tradeoff_summary = (
            "Downtown access keeps commute shorter, but housing cost pressure is higher. Moving outward can cut "
            "rent burden, but adds commute time and stress load."
        )

    suggested_current_responses = [
        "Stay in current region and absorb commute pressure while protecting sleep/recovery.",
        "Move or rent closer to core work zones to cut commute, accepting higher housing cost.",
    ]

    estimated_burden = (
        f"~{float(_q4(effective_hours)):.1f}h/day (includes ~{float(_q4(congestion_hours)):.1f}h "
        "population congestion load)"
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "region_key": region_key,
        "commute_pressure_level": pressure_level,
        "estimated_commute_burden": estimated_burden,
        "stress_impact_label": stress_impact,
        "time_impact_label": time_impact,
        "housing_tradeoff_summary": housing_tradeoff_summary,
        "suggested_current_responses": suggested_current_responses,
        "debug_meta": {
            "day": int(day),
            "baseline_commute_hours": float(_q4(baseline_hours)),
            "effective_commute_hours": float(_q4(effective_hours)),
            "congestion_hours": float(_q4(congestion_hours)),
            "population_count": int(total_players),
            "congestion_base": float(_q4(congestion_base)),
            "region_density_factor": float(_q4(region_density)),
            "region_stress_delta": float(_q4(stress_signal)),
            "source_housing_day": int(getattr(housing_log, "day", 0) or 0),
        },
    }


def build_player_economy_explainer(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build plain-language explanation chain for player-facing economy readability."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)

    market = build_market_overview(db=db, player_id=player.id, as_of_date=resolved_date)
    prices = build_price_trend_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    margins = build_business_margin_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    commute = build_commute_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    settlement = _latest_settlement(db, player.id, day)

    price_items = {item["basket_key"]: item for item in prices["items"]}
    produce_trend = str(price_items.get("produce", {}).get("short_term_trend", "stable"))
    essentials_trend = str(price_items.get("essentials", {}).get("short_term_trend", "stable"))
    protein_trend = str(price_items.get("protein", {}).get("short_term_trend", "stable"))

    why_costs_changed = (
        f"Costs shifted because essentials are {essentials_trend}, protein is {protein_trend}, "
        f"and market mood is {market['current_market_mood']}."
    )

    margin_items = {item["business_key"]: item for item in margins["items"]}
    fruit_outlook = str(margin_items.get("fruit_shop", {}).get("margin_outlook", "mixed"))
    truck_outlook = str(margin_items.get("food_truck", {}).get("margin_outlook", "mixed"))
    more_pressured = "Fruit Shop" if fruit_outlook == "pressured" and truck_outlook != "pressured" else (
        "Food Truck" if truck_outlook == "pressured" and fruit_outlook != "pressured" else "both businesses"
    )
    why_business_changed = (
        f"{more_pressured} face margin changes from input costs, demand shifts, and region traffic modifiers."
    )

    why_commute_changed = (
        f"Commute pressure is {commute['commute_pressure_level']} with {commute['estimated_commute_burden']}; "
        "higher player density increases travel drag."
    )

    stress_change = int(getattr(settlement, "stress_change", 0) or 0)
    if stress_change > 0:
        stress_direction = "increased"
    elif stress_change < 0:
        stress_direction = "eased"
    else:
        stress_direction = "held steady"

    why_stress_changed = (
        f"Stress {stress_direction} due to workload, commute burden, and financial pressure interacting on the same day."
    )

    if market["current_market_mood"] == "pressured":
        this_week_focus = "Protect cash runway and avoid overcommitting inventory or overtime."
        defensive_move = "Keep inventory lean, reduce optional spend, and prioritize recovery windows."
    else:
        this_week_focus = "Use stable conditions to compound skill and selective business momentum."
        defensive_move = "Keep a cash buffer while avoiding high-variance expansion bets."

    if produce_trend == "falling" and fruit_outlook != "pressured":
        growth_move = "Lean into Fruit Shop sell-through while produce costs are easing."
    elif truck_outlook == "favorable":
        growth_move = "Push Food Truck in high-foot-traffic windows and protect fuel efficiency."
    else:
        growth_move = "Prioritize career/training momentum while waiting for cleaner margin signals."

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "why_costs_changed": why_costs_changed,
        "why_business_changed": why_business_changed,
        "why_commute_changed": why_commute_changed,
        "why_stress_changed": why_stress_changed,
        "this_week_focus": this_week_focus,
        "suggested_defensive_move": defensive_move,
        "suggested_growth_move": growth_move,
        "debug_meta": {
            "day": int(day),
            "market_mood": market["current_market_mood"],
            "fruit_margin_outlook": fruit_outlook,
            "food_truck_margin_outlook": truck_outlook,
            "produce_trend": produce_trend,
            "stress_change": int(stress_change),
        },
    }


def build_future_opportunity_teasers(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Build subtle future-content teasers while keeping systems locked."""
    player = _resolve_player(db, player_id)
    _, resolved_date = _resolve_day(db, as_of_date)
    commute = build_commute_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date)

    congestion_label = str(commute["commute_pressure_level"])
    teaser_body_suffix = (
        "as congestion trends climb."
        if congestion_label in {"moderate", "high"}
        else "as your city activity density grows over time."
    )
    teasers = [
        {
            "teaser_key": "future_vehicle_brands",
            "title": "Personal Vehicle Tracks (Future)",
            "body": "Vehicle ownership and brand paths may unlock future commute control options.",
            "unlock_status": "locked",
            "category": "mobility",
            "debug_meta": {"source": "step27_teaser"},
        },
        {
            "teaser_key": "future_transport_startups",
            "title": "Transportation Startups (Future)",
            "body": f"Mobility ventures may open ways to monetize and offset commute pressure {teaser_body_suffix}",
            "unlock_status": "locked",
            "category": "startup",
            "debug_meta": {"source": "step27_teaser"},
        },
        {
            "teaser_key": "future_logistics_business",
            "title": "Logistics Ventures (Future)",
            "body": "Advanced logistics businesses are planned but not available in the current progression tier.",
            "unlock_status": "locked",
            "category": "business",
            "debug_meta": {"source": "step27_teaser"},
        },
    ]

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "teasers": teasers,
        "debug_meta": {
            "commute_pressure_level": congestion_label,
            "teaser_count": len(teasers),
        },
    }


def build_economy_presentation_summary(
    db: Session,
    player_id: str | UUID,
    as_of_date: date | None = None,
) -> dict:
    """Compose all Step 27 economy presentation payloads for one player."""
    player = _resolve_player(db, player_id)
    day, resolved_date = _resolve_day(db, as_of_date)
    housing_state = _active_housing_state(db, player.id)
    region_key = _resolve_region_key(player, housing_state)

    market = build_market_overview(db=db, player_id=player.id, as_of_date=resolved_date)
    prices = build_price_trend_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    margins = build_business_margin_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    commute = build_commute_pressure_summary(db=db, player_id=player.id, as_of_date=resolved_date)
    explainer = build_player_economy_explainer(db=db, player_id=player.id, as_of_date=resolved_date)
    degraded_sections: list[str] = []
    try:
        daily_brief = build_daily_economy_brief(db=db, as_of_date=resolved_date, day=day)
    except Exception as exc:
        logger.exception(
            "economy_presentation.daily_brief_degraded",
            extra={
                "player_id": str(player.id),
                "day_number": int(day),
                "fallback_applied": True,
            },
        )
        degraded_sections.append("daily_brief")
        daily_brief = {
            "day": int(day),
            "headline": "Economy data is temporarily unavailable",
            "summary_lines": [
                "Work and core actions are still available.",
                "Basket pricing is using safe fallback values right now.",
            ],
            "top_bottlenecks": [],
            "top_basket_movers": [],
            "top_job_changes": [],
            "debug_meta": {
                "fallback_reason": str(exc),
                "fallback_applied": True,
                "degraded_sections": ["basket_pricing"],
            },
        }
    supply_chain_summary = build_supply_chain_daily_summary(db=db, day=day, region=region_key).to_dict()
    supply_chain_story = build_supply_chain_story_summary(db=db, day=day, region=region_key).to_dict()
    settlement_summary = _settlement_digest(_latest_settlement(db, player.id, day))
    player_warnings, player_opportunities = _build_mobile_signal_lists(
        market=market,
        supply_chain_summary=supply_chain_summary,
        supply_chain_story=supply_chain_story,
        daily_brief=daily_brief,
    )

    return {
        "player_id": str(player.id),
        "as_of_date": resolved_date.isoformat(),
        "current_day": int(day),
        "market_overview": market,
        "price_trends": prices,
        "business_margins": margins,
        "commute_pressure": commute,
        "explainer": explainer,
        "daily_brief": {
            **daily_brief,
            "as_of_date": resolved_date.isoformat(),
        },
        "supply_chain_summary": supply_chain_summary,
        "supply_chain_story": supply_chain_story,
        "settlement_summary": settlement_summary,
        "player_warnings": player_warnings,
        "player_opportunities": player_opportunities,
        "debug_meta": {
            "service": "economy_presentation_service",
            "version": "step27_v1",
            "region_key": region_key,
            "summary_source": "canonical_backend_economy",
            "degraded_sections": degraded_sections,
        },
    }
