"""Phase 4 Step 4 — Strategic Daily Brief.

Aggregates existing player, business, portfolio, map, and risk signals into a
compact strategic_brief payload with cause/effect/action alerts and a capped
list of recommended actions.

This service:
  * adds NO new economy/business/map formulas
  * reads only existing models
  * never raises on missing data — degrades to empty sections
  * never invokes AI
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.enums import BasketType
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_business import PlayerBusiness


VALID_TARGET_SCREENS = {"Life", "Map", "Work", "Business", "Portfolio", "Summary"}

MAX_RECOMMENDED_ACTIONS = 3
MAX_RISK_WARNINGS = 3
MAX_BUSINESS_ALERTS = 3
MAX_PORTFOLIO_ALERTS = 2
MAX_MAP_OPPORTUNITIES = 2

# Severity rank for sorting (higher = more urgent)
_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}

# Action priority groups (lower = more urgent slot in recommended_actions)
_PRIORITY_SURVIVAL = 0
_PRIORITY_BUSINESS_BLOCKER = 1
_PRIORITY_PORTFOLIO_RISK = 2
_PRIORITY_OPPORTUNITY = 3


def _d(value: object) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def _resolve_player(db: Session, player_id: str | UUID) -> Player | None:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except (ValueError, TypeError):
        return None
    return db.query(Player).filter(Player.id == pid).first()


def _alert(
    *,
    type_: str,
    severity: str,
    cause: str,
    effect: str,
    action: str,
    target_screen: str,
) -> dict[str, Any]:
    if severity not in _SEVERITY_RANK:
        severity = "low"
    if target_screen not in VALID_TARGET_SCREENS:
        target_screen = "Life"
    return {
        "type": type_,
        "severity": severity,
        "cause": cause,
        "effect": effect,
        "action": action,
        "target_screen": target_screen,
    }


def _days_of_stock_left(business: PlayerBusiness, latest_log: BusinessDailyLog | None) -> Decimal | None:
    """Estimate days_of_stock_left from total inventory units / yesterday's units_sold.

    No new formula — this is just a ratio of two existing recorded values.
    Returns None when units_sold is unknown or zero (cannot project).
    """
    total_units = (
        _d(business.inventory_produce_units)
        + _d(business.inventory_essentials_units)
        + _d(business.inventory_protein_units)
    )
    if latest_log is None:
        return None
    units_sold = _d(latest_log.units_sold)
    if units_sold <= Decimal("0"):
        return None
    return total_units / units_sold


def _latest_business_log(db: Session, business_id: UUID, day: int) -> BusinessDailyLog | None:
    return (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.business_id == business_id,
            BusinessDailyLog.day <= day,
        )
        .order_by(BusinessDailyLog.day.desc(), BusinessDailyLog.created_at.desc())
        .first()
    )


def _latest_macro(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= day)
        .order_by(MacroDailyState.day.desc())
        .first()
    )
    if row is None:
        row = db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()
    return row


def _basket_price_index(db: Session, basket_type: BasketType, day: int) -> Decimal:
    row = (
        db.query(BasketDailyPrice)
        .filter(
            BasketDailyPrice.basket_type == basket_type,
            BasketDailyPrice.day <= day,
        )
        .order_by(BasketDailyPrice.day.desc())
        .first()
    )
    if row is None:
        return Decimal("0")
    return _d(row.price_index)


def _build_business_alerts(
    db: Session,
    businesses: list[PlayerBusiness],
    macro: MacroDailyState | None,
    produce_index_today: Decimal,
    produce_index_prev: Decimal,
    day: int,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    oil_index = _d(macro.oil_index) if macro is not None else Decimal("0")
    supply_stress = _d(macro.supply_chain_stress) if macro is not None else Decimal("0")
    produce_jump_pct = Decimal("0")
    if produce_index_prev > Decimal("0"):
        produce_jump_pct = (
            (produce_index_today - produce_index_prev) / produce_index_prev
        ) * Decimal("100")

    for biz in businesses:
        try:
            biz_label = str(biz.business_name or biz.business_id or "your business")
            biz_type = str(biz.business_id or "")
            total_units = (
                _d(biz.inventory_produce_units)
                + _d(biz.inventory_essentials_units)
                + _d(biz.inventory_protein_units)
            )

            latest_log = _latest_business_log(db, biz.id, day)
            days_left = _days_of_stock_left(biz, latest_log)

            # No inventory.
            if total_units <= Decimal("0"):
                alerts.append(_alert(
                    type_="business_alert",
                    severity="high",
                    cause=f"{biz_label} has no inventory.",
                    effect="The business cannot operate today.",
                    action="Restock inventory before running operations.",
                    target_screen="Business",
                ))
            elif days_left is not None and days_left <= Decimal("1"):
                alerts.append(_alert(
                    type_="business_alert",
                    severity="high",
                    cause=f"{biz_label} has {float(days_left):.1f} day of stock left.",
                    effect="You will run out of stock and lose sales.",
                    action="Restock inventory today.",
                    target_screen="Business",
                ))
            elif days_left is not None and days_left <= Decimal("3"):
                alerts.append(_alert(
                    type_="business_alert",
                    severity="medium",
                    cause=f"{biz_label} has {float(days_left):.1f} days of stock left.",
                    effect="Inventory will run thin within the week.",
                    action="Plan a restock soon.",
                    target_screen="Business",
                ))

            # Negative profit.
            if latest_log is not None and _d(latest_log.net_profit_xgp) < Decimal("0"):
                loss = abs(_d(latest_log.net_profit_xgp))
                alerts.append(_alert(
                    type_="business_alert",
                    severity="medium",
                    cause=f"{biz_label} lost {float(loss):.2f} XGP last operation.",
                    effect="Continued losses will tighten cash flow.",
                    action="Review costs and pricing before scaling.",
                    target_screen="Business",
                ))

            # High spoilage.
            if latest_log is not None:
                spoilage = _d(latest_log.spoilage_cost_xgp)
                revenue = _d(latest_log.gross_revenue_xgp)
                if spoilage >= Decimal("5") and (
                    revenue <= Decimal("0") or spoilage / max(revenue, Decimal("1")) >= Decimal("0.10")
                ):
                    alerts.append(_alert(
                        type_="business_alert",
                        severity="medium",
                        cause=f"{biz_label} spoilage was {float(spoilage):.2f} XGP.",
                        effect="High spoilage drags business margin.",
                        action="Sell faster or order smaller batches.",
                        target_screen="Business",
                    ))

            # Food truck + oil pressure.
            if "food_truck" in biz_type and (
                oil_index >= Decimal("140") or supply_stress >= Decimal("1.80")
            ):
                alerts.append(_alert(
                    type_="business_alert",
                    severity="high",
                    cause=f"Oil index is {float(oil_index):.1f} and supply stress is {float(supply_stress):.2f}.",
                    effect=f"Fuel costs are squeezing {biz_label} margin.",
                    action="Avoid extra runs today; conserve fuel.",
                    target_screen="Business",
                ))

            # Fruit shop + produce price pressure.
            if "fruit" in biz_type and produce_jump_pct >= Decimal("4.0"):
                alerts.append(_alert(
                    type_="business_alert",
                    severity="medium",
                    cause=f"Produce prices moved {float(produce_jump_pct):+.1f}% day-over-day.",
                    effect=f"{biz_label} input costs are rising.",
                    action="Adjust markup or restock before prices climb further.",
                    target_screen="Business",
                ))
        except Exception:
            continue

    # Sort by severity, cap.
    alerts.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 0), reverse=True)
    return alerts[:MAX_BUSINESS_ALERTS]


def _build_portfolio_alerts(
    player: Player,
    businesses: list[PlayerBusiness],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    cash = _d(player.cash_xgp)
    debt = _d(player.debt_xgp)
    net_worth = _d(player.net_worth_xgp)

    # Low cash (also a risk, but portfolio alerts cover net liquidity).
    if cash < Decimal("50") and debt > Decimal("0"):
        alerts.append(_alert(
            type_="portfolio_alert",
            severity="high",
            cause=f"Cash is {float(cash):.2f} XGP with debt of {float(debt):.2f} XGP.",
            effect="You are close to a forced default.",
            action="Hold cash; avoid new spending.",
            target_screen="Portfolio",
        ))

    # High debt (debt > cash * 3).
    if debt >= Decimal("500") and (cash <= Decimal("0") or debt > cash * Decimal("3")):
        alerts.append(_alert(
            type_="portfolio_alert",
            severity="high",
            cause=f"Debt is {float(debt):.2f} XGP versus cash {float(cash):.2f} XGP.",
            effect="Debt service is dominating your finances.",
            action="Pay down debt before optional spending.",
            target_screen="Portfolio",
        ))

    # Net worth down (using player.net_worth vs starting baseline of 1000 XGP).
    if net_worth > Decimal("0") and net_worth < Decimal("800"):
        alerts.append(_alert(
            type_="portfolio_alert",
            severity="medium",
            cause=f"Net worth is {float(net_worth):.2f} XGP.",
            effect="Your wealth trajectory is below baseline.",
            action="Check portfolio; net worth dropped.",
            target_screen="Portfolio",
        ))

    # Inventory value high vs cash (using inventory_units as crude proxy).
    total_inventory_units = Decimal("0")
    for biz in businesses:
        try:
            total_inventory_units += (
                _d(biz.inventory_produce_units)
                + _d(biz.inventory_essentials_units)
                + _d(biz.inventory_protein_units)
            )
        except Exception:
            continue
    if total_inventory_units > Decimal("100") and cash < Decimal("100"):
        alerts.append(_alert(
            type_="portfolio_alert",
            severity="medium",
            cause=(
                f"Business inventory is {float(total_inventory_units):.0f} units "
                f"while cash is {float(cash):.2f} XGP."
            ),
            effect="You are inventory-rich and cash-poor.",
            action="Sell through stock before buying more.",
            target_screen="Portfolio",
        ))

    alerts.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 0), reverse=True)
    return alerts[:MAX_PORTFOLIO_ALERTS]


def _build_map_opportunities(
    player: Player,
    businesses: list[PlayerBusiness],
) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []

    try:
        # Linked business mismatch: business region differs from player housing region.
        player_region = str(player.region or "suburban").lower()
        for biz in businesses:
            biz_region = str(biz.region or "").lower()
            if biz_region and biz_region != player_region:
                opportunities.append(_alert(
                    type_="map_opportunity",
                    severity="low",
                    cause=(
                        f"{biz.business_name or biz.business_id} runs in {biz_region} "
                        f"while you live in {player_region}."
                    ),
                    effect="Travel time is eating into the day.",
                    action="Consider relocating or running ops near home.",
                    target_screen="Map",
                ))
                break
    except Exception:
        pass

    # Owned-but-unused slot is approximated as: an active business that hasn't operated recently.
    # Without a dedicated slot model in the existing repo, this is the strongest proxy.
    try:
        for biz in businesses:
            if not bool(getattr(biz, "is_active", False)):
                continue
            last_op = getattr(biz, "last_operated_day", None)
            created = int(getattr(biz, "created_day", 0) or 0)
            if last_op is None and created > 0:
                opportunities.append(_alert(
                    type_="map_opportunity",
                    severity="low",
                    cause=f"{biz.business_name or biz.business_id} has not been operated yet.",
                    effect="An owned slot is sitting idle.",
                    action="Run the business to capture demand.",
                    target_screen="Map",
                ))
                break
    except Exception:
        pass

    return opportunities[:MAX_MAP_OPPORTUNITIES]


def _build_risk_warnings(
    player: Player,
    businesses: list[PlayerBusiness],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    stress = int(player.stress or 0)
    health = int(player.health or 100)
    cash = _d(player.cash_xgp)
    debt = _d(player.debt_xgp)
    distress = _d(player.distress_score)
    missed = int(getattr(player, "missed_payment_streak", 0) or 0)

    if stress >= 80:
        warnings.append(_alert(
            type_="risk_warning",
            severity="high",
            cause=f"Stress is {stress}/100.",
            effect="High-stress actions (rideshare, double shifts) will hurt you.",
            action="Avoid rideshare today; stress is too high.",
            target_screen="Life",
        ))

    if health <= 30:
        warnings.append(_alert(
            type_="risk_warning",
            severity="high",
            cause=f"Health is {health}/100.",
            effect="Low health blocks shifts and raises medical risk.",
            action="Eat and rest before working.",
            target_screen="Life",
        ))

    if cash < Decimal("20"):
        warnings.append(_alert(
            type_="risk_warning",
            severity="high",
            cause=f"Cash is {float(cash):.2f} XGP.",
            effect="You cannot afford essentials or restock.",
            action="Run a low-risk income action immediately.",
            target_screen="Work",
        ))

    if distress >= Decimal("0.8") and debt > Decimal("0"):
        warnings.append(_alert(
            type_="risk_warning",
            severity="high",
            cause=f"Distress score is {float(distress):.2f}.",
            effect="Bankruptcy risk is rising.",
            action="Service debt before optional spending.",
            target_screen="Life",
        ))

    if missed >= 1:
        warnings.append(_alert(
            type_="risk_warning",
            severity="medium",
            cause=f"You have {missed} missed payment(s) on record.",
            effect="Credit damage compounds with each miss.",
            action="Pay the minimum debt service today.",
            target_screen="Life",
        ))

    # Business cannot operate / insufficient inventory.
    for biz in businesses:
        try:
            total_units = (
                _d(biz.inventory_produce_units)
                + _d(biz.inventory_essentials_units)
                + _d(biz.inventory_protein_units)
            )
            if bool(getattr(biz, "is_active", False)) and total_units <= Decimal("0"):
                warnings.append(_alert(
                    type_="risk_warning",
                    severity="medium",
                    cause=f"{biz.business_name or biz.business_id} has no stock.",
                    effect="Business cannot operate today.",
                    action="Restock before running operations.",
                    target_screen="Business",
                ))
                break
        except Exception:
            continue

    warnings.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 0), reverse=True)
    return warnings[:MAX_RISK_WARNINGS]


def _alert_priority(alert: dict[str, Any]) -> int:
    type_ = alert.get("type")
    if type_ == "risk_warning":
        return _PRIORITY_SURVIVAL
    if type_ == "business_alert":
        return _PRIORITY_BUSINESS_BLOCKER
    if type_ == "portfolio_alert":
        return _PRIORITY_PORTFOLIO_RISK
    return _PRIORITY_OPPORTUNITY


def _build_recommended_actions(
    risk_warnings: list[dict[str, Any]],
    business_alerts: list[dict[str, Any]],
    portfolio_alerts: list[dict[str, Any]],
    map_opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pool = [*risk_warnings, *business_alerts, *portfolio_alerts, *map_opportunities]
    pool.sort(
        key=lambda a: (
            _alert_priority(a),
            -_SEVERITY_RANK.get(a.get("severity", "low"), 0),
        )
    )

    seen_actions: set[str] = set()
    actions: list[dict[str, Any]] = []
    for alert in pool:
        action_text = str(alert.get("action") or "").strip()
        if not action_text or action_text in seen_actions:
            continue
        seen_actions.add(action_text)
        actions.append({
            "action": action_text,
            "target_screen": alert.get("target_screen", "Life"),
            "severity": alert.get("severity", "low"),
            "source_type": alert.get("type", "risk_warning"),
        })
        if len(actions) >= MAX_RECOMMENDED_ACTIONS:
            break
    return actions


def _build_player_condition(player: Player) -> str:
    stress = int(player.stress or 0)
    health = int(player.health or 100)
    if stress >= 80 or health <= 30:
        return f"Critical — stress {stress}, health {health}."
    if stress >= 60 or health <= 60:
        return f"Strained — stress {stress}, health {health}."
    return f"Stable — stress {stress}, health {health}."


def _build_today_pressure(
    macro: MacroDailyState | None,
    risk_warnings: list[dict[str, Any]],
    business_alerts: list[dict[str, Any]],
) -> str:
    if any(a.get("severity") == "high" for a in risk_warnings):
        return "Survival pressure dominates today."
    if any(a.get("severity") == "high" for a in business_alerts):
        return "Business operations are under pressure today."
    if macro is not None:
        oil = _d(macro.oil_index)
        supply_stress = _d(macro.supply_chain_stress)
        if oil >= Decimal("140") or supply_stress >= Decimal("1.80"):
            return "Macro pressure on fuel and shipping."
        confidence = _d(macro.consumer_confidence)
        if confidence <= Decimal("40"):
            return "Soft demand — consumers are pulling back."
    return "Mixed conditions — no single pressure dominates."


def _build_macro_summary(macro: MacroDailyState | None) -> str:
    if macro is None:
        return "Macro data unavailable."
    return (
        f"Inflation {float(_d(macro.inflation_rate)):.2f}%, "
        f"unemployment {float(_d(macro.unemployment_rate)):.1f}%, "
        f"confidence {float(_d(macro.consumer_confidence)):.1f}, "
        f"oil {float(_d(macro.oil_index)):.1f}."
    )


def _build_headline(
    risk_warnings: list[dict[str, Any]],
    business_alerts: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> str:
    if actions:
        top = actions[0]
        return str(top.get("action") or "Run one cash-positive action today.")
    if risk_warnings:
        return str(risk_warnings[0].get("action") or "Protect health and cash today.")
    if business_alerts:
        return str(business_alerts[0].get("action") or "Review business operations.")
    return "Steady day — protect cash and progress."


def build_strategic_brief(
    db: Session,
    player_id: str | UUID,
    day: int,
) -> dict[str, Any]:
    """Build the strategic_brief payload for a player on a given day.

    Always returns a well-formed dict. Missing data degrades to empty sections.
    """
    empty: dict[str, Any] = {
        "headline": "Strategic brief unavailable.",
        "today_pressure": "",
        "macro_summary": "",
        "player_condition": "",
        "business_alerts": [],
        "portfolio_alerts": [],
        "map_opportunities": [],
        "risk_warnings": [],
        "recommended_actions": [],
    }

    player = _resolve_player(db, player_id)
    if player is None:
        return empty

    safe_day = int(day) if day and int(day) > 0 else 1

    try:
        businesses = (
            db.query(PlayerBusiness)
            .filter(
                PlayerBusiness.player_id == player.id,
                PlayerBusiness.is_active == True,  # noqa: E712
            )
            .all()
        )
    except Exception:
        businesses = []

    try:
        macro = _latest_macro(db, safe_day)
    except Exception:
        macro = None

    try:
        produce_today = _basket_price_index(db, BasketType.produce, safe_day)
        produce_prev = _basket_price_index(db, BasketType.produce, max(1, safe_day - 1))
    except Exception:
        produce_today = Decimal("0")
        produce_prev = Decimal("0")

    business_alerts = _build_business_alerts(
        db, businesses, macro, produce_today, produce_prev, safe_day
    )
    portfolio_alerts = _build_portfolio_alerts(player, businesses)
    map_opportunities = _build_map_opportunities(player, businesses)
    risk_warnings = _build_risk_warnings(player, businesses)
    recommended_actions = _build_recommended_actions(
        risk_warnings, business_alerts, portfolio_alerts, map_opportunities
    )

    return {
        "headline": _build_headline(risk_warnings, business_alerts, recommended_actions),
        "today_pressure": _build_today_pressure(macro, risk_warnings, business_alerts),
        "macro_summary": _build_macro_summary(macro),
        "player_condition": _build_player_condition(player),
        "business_alerts": business_alerts,
        "portfolio_alerts": portfolio_alerts,
        "map_opportunities": map_opportunities,
        "risk_warnings": risk_warnings,
        "recommended_actions": recommended_actions,
    }
