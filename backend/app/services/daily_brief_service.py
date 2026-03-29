"""Opportunity events + daily brief narrative service."""

from __future__ import annotations

from datetime import date
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.engine.supply_chain_service import compute_supply_chain_daily_snapshot
from app.models.basket_consumption_log import BasketConsumptionLog
from app.models.basket_daily_price import BasketDailyPrice
from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_brief_log import DailyBriefLog
from app.models.daily_settlement_log import DailySettlementLog
from app.models.debt_credit_log import DebtCreditLog
from app.models.enums import BasketType
from app.models.housing_daily_log import HousingDailyLog
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_employment_state import PlayerEmploymentState
from app.models.player_stock_holding import PlayerStockHolding
from app.models.stock_daily_price import StockDailyPrice
from app.services.basket_pricing_service import compute_daily_basket_price_updates
from app.services.job_market_service import compute_daily_job_market_updates

Q4 = Decimal("0.0001")
MONEY_Q = Decimal("0.01")


class DailyBriefError(Exception):
    """Base exception for daily brief generation."""


class DailyBriefNotFoundError(DailyBriefError):
    """Raised when required entities or logs are missing."""


class DailyBriefValidationError(DailyBriefError):
    """Raised for invalid user input."""


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise DailyBriefNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise DailyBriefNotFoundError("Player not found.")
    return player


def _parse_json(value: str | None, *, default: dict | list):
    if not value:
        return default
    try:
        parsed = json.loads(value)
        if isinstance(default, dict) and isinstance(parsed, dict):
            return parsed
        if isinstance(default, list) and isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return default


def _latest_macro_state(db: Session, day: int) -> MacroDailyState | None:
    row = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= day)
        .order_by(MacroDailyState.day.desc())
        .first()
    )
    if row is not None:
        return row
    return db.query(MacroDailyState).order_by(MacroDailyState.day.desc()).first()


def _macro_for_prev_day(db: Session, day: int) -> MacroDailyState | None:
    return (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day < day)
        .order_by(MacroDailyState.day.desc())
        .first()
    )


def _latest_basket_price_index(db: Session, basket_type: BasketType, day: int) -> Decimal:
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


def _stock_context_for_player(db: Session, player_id: UUID, day: int) -> dict:
    holdings = (
        db.query(PlayerStockHolding)
        .filter(
            PlayerStockHolding.player_id == player_id,
            PlayerStockHolding.shares_owned > 0,
        )
        .all()
    )

    latest_market_day = db.query(func.max(StockDailyPrice.day)).filter(StockDailyPrice.day <= day).scalar()
    latest_market_day = int(latest_market_day) if latest_market_day is not None else None

    if not holdings:
        market_avg = None
        if latest_market_day is not None:
            rows = db.query(StockDailyPrice).filter(StockDailyPrice.day == latest_market_day).all()
            if rows:
                market_avg = float(sum(_d(r.daily_change_pct) for r in rows) / Decimal(str(len(rows))))
        return {
            "has_positions": False,
            "weighted_daily_change_pct": None,
            "market_average_change_pct": market_avg,
            "market_day_used": latest_market_day,
        }

    weighted_total = Decimal("0")
    share_total = Decimal("0")
    tickers_with_prices = 0

    for holding in holdings:
        shares = Decimal(str(int(holding.shares_owned or 0)))
        if shares <= Decimal("0"):
            continue

        row = (
            db.query(StockDailyPrice)
            .filter(
                StockDailyPrice.ticker == holding.stock_id,
                StockDailyPrice.day <= day,
            )
            .order_by(StockDailyPrice.day.desc())
            .first()
        )
        if row is None:
            continue

        daily_change = _d(row.daily_change_pct)
        weighted_total += shares * daily_change
        share_total += shares
        tickers_with_prices += 1

    if share_total <= Decimal("0"):
        return {
            "has_positions": False,
            "weighted_daily_change_pct": None,
            "market_average_change_pct": None,
            "market_day_used": latest_market_day,
        }

    weighted_change = float(_q4(weighted_total / share_total))
    return {
        "has_positions": True,
        "weighted_daily_change_pct": weighted_change,
        "position_count": int(tickers_with_prices),
        "market_day_used": latest_market_day,
    }


def generate_global_daily_event(db: Session, day: int) -> dict:
    """Create deterministic daily macro event narrative for one day.

    Step 19: If the event engine has already fired for this day, use its
    headline and category directly.  Otherwise fall back to the original
    macro-delta heuristic so the function stays backward-compatible.
    """
    if day <= 0:
        raise DailyBriefValidationError("day must be greater than 0.")

    # Step 19 / 19.5: try to read the event engine row first.
    try:
        from app.models.daily_economy_event import DailyEconomyEvent
        event_row = db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == day).first()
        if event_row is not None:
            import json as _json
            tags = []
            try:
                parsed = _json.loads(event_row.impact_tags_json or "[]")
                tags = [
                    f"{t['tag']}_{t['direction']}" if isinstance(t, dict) else str(t)
                    for t in parsed
                ]
            except Exception:
                pass
            tags.append(event_row.event_category)
            if event_row.sentiment == "negative":
                tags.append("pressure")
            elif event_row.sentiment == "positive":
                tags.append("relief")

            # Step 19.5: Chain-aware headline narrative
            headline = str(event_row.headline)
            chain_stage = getattr(event_row, "chain_stage", None)
            chain_pos = int(getattr(event_row, "chain_position", 0) or 0)
            parent_key = getattr(event_row, "parent_event_key", None)

            if chain_stage == "mid" and chain_pos > 0:
                headline = f"{headline} — day {chain_pos + 1} of ongoing pressure"
                tags.append("chain_continuation")
            elif chain_stage == "escalation":
                headline = f"Conditions intensify: {headline}"
                tags.append("chain_escalation")
            elif chain_stage == "peak":
                headline = f"Crisis peaks: {headline}"
                tags.append("chain_peak")
            elif chain_stage == "recovery":
                headline = f"Signs of stabilization: {headline}"
                tags.append("chain_recovery")
            elif chain_stage == "start" and chain_pos == 0:
                pass  # Normal headline for chain start

            if parent_key:
                tags.append(f"follows_{parent_key}")

            return {
                "day": int(day),
                "headline": headline,
                "summary": str(event_row.summary or ""),
                "macro_tags_json": list(dict.fromkeys(tags)),
                "category": str(event_row.event_category),
            }
    except Exception:
        pass  # table may not exist yet — fall back to legacy logic

    macro = _latest_macro_state(db, day)
    if macro is None:
        headline = "Markets hold a quiet line as no major macro shock is detected"
        summary = "Economic signals are sparse today, so conditions are treated as stable and neutral."
        return {
            "day": int(day),
            "headline": headline,
            "summary": summary,
            "macro_tags_json": ["baseline", "low_signal_day"],
            "category": "baseline",
        }

    prev = _macro_for_prev_day(db, int(macro.day))

    inflation = _d(macro.inflation_rate)
    unemployment = _d(macro.unemployment_rate)
    confidence = _d(macro.consumer_confidence)
    oil = _d(macro.oil_index)
    supply_stress = _d(macro.supply_chain_stress)

    prev_inflation = _d(prev.inflation_rate) if prev is not None else inflation
    prev_unemployment = _d(prev.unemployment_rate) if prev is not None else unemployment
    prev_confidence = _d(prev.consumer_confidence) if prev is not None else confidence
    prev_oil = _d(prev.oil_index) if prev is not None else oil

    oil_delta = oil - prev_oil
    confidence_delta = confidence - prev_confidence
    unemployment_delta = unemployment - prev_unemployment
    inflation_delta = inflation - prev_inflation

    essentials_now = _latest_basket_price_index(db, BasketType.essentials, day)
    essentials_prev = _latest_basket_price_index(db, BasketType.essentials, max(1, day - 1))
    produce_now = _latest_basket_price_index(db, BasketType.produce, day)
    produce_prev = _latest_basket_price_index(db, BasketType.produce, max(1, day - 1))

    essentials_jump_pct = Decimal("0")
    if essentials_prev > Decimal("0"):
        essentials_jump_pct = ((essentials_now - essentials_prev) / essentials_prev) * Decimal("100")

    produce_jump_pct = Decimal("0")
    if produce_prev > Decimal("0"):
        produce_jump_pct = ((produce_now - produce_prev) / produce_prev) * Decimal("100")

    tags: list[str] = []

    if oil_delta >= Decimal("8") or oil >= Decimal("140") or supply_stress >= Decimal("1.80"):
        headline = "Fuel and shipping pressure climbs as logistics strain intensifies"
        summary = (
            f"Oil and transport stress are elevated (oil {oil:.1f}, supply stress {supply_stress:.2f}), "
            "raising cost pressure on transport-heavy activity."
        )
        tags.extend(["oil_up", "supply_stress", "transport_pressure"])
        category = "fuel_shipping"
    elif confidence <= Decimal("40") and unemployment >= Decimal("7.0"):
        headline = "Consumer confidence weakens as job pressure spreads"
        summary = (
            f"Confidence is soft ({confidence:.1f}) while unemployment remains high ({unemployment:.1f}%), "
            "signaling weaker household demand and tighter spending behavior."
        )
        tags.extend(["confidence_down", "unemployment_up", "consumer_slowdown"])
        category = "consumer_slowdown"
    elif essentials_jump_pct >= Decimal("4.0") or produce_jump_pct >= Decimal("5.0"):
        headline = "Grocery volatility rises as essentials and produce prices move"
        summary = (
            f"Basket prices are unstable (essentials {essentials_jump_pct:+.1f}%, produce {produce_jump_pct:+.1f}% day-over-day), "
            "which can tighten food budgets and increase nutrition pressure."
        )
        tags.extend(["grocery_volatility", "basket_pressure"])
        if essentials_jump_pct > Decimal("0") or produce_jump_pct > Decimal("0"):
            tags.append("food_inflation")
        category = "grocery_volatility"
    elif inflation <= Decimal("2.5") and supply_stress <= Decimal("0.70") and confidence_delta >= Decimal("0.8"):
        headline = "Price pressure eases as supply conditions stabilize"
        summary = (
            f"Inflation is moderating ({inflation:.2f}%) and supply stress has cooled ({supply_stress:.2f}), "
            "creating a more supportive environment for household budgets."
        )
        tags.extend(["inflation_easing", "supply_relief", "consumer_relief"])
        category = "relief"
    elif confidence >= Decimal("58") and unemployment <= Decimal("5.2") and confidence_delta >= Decimal("0"):
        headline = "Demand momentum improves as confidence strengthens"
        summary = (
            f"Confidence is firm ({confidence:.1f}) and unemployment is contained ({unemployment:.1f}%), "
            "supporting stronger demand conditions in the near term."
        )
        tags.extend(["confidence_up", "demand_growth", "labor_stable"])
        category = "growth"
    else:
        headline = "Economic conditions hold in a mixed but manageable range"
        summary = (
            f"Signals are mixed (inflation {inflation:.2f}%, confidence {confidence:.1f}, unemployment {unemployment:.1f}%), "
            "with no single macro shock dominating today."
        )
        tags.extend(["mixed_conditions", "baseline"])
        category = "baseline"

    if inflation_delta > Decimal("0.40"):
        tags.append("inflation_up")
    elif inflation_delta < Decimal("-0.40"):
        tags.append("inflation_down")

    if unemployment_delta > Decimal("0.30"):
        tags.append("unemployment_rising")

    if confidence_delta < Decimal("-1.00"):
        tags.append("confidence_falling")

    # Stable deterministic ordering and dedup.
    deduped_tags = list(dict.fromkeys(tags))

    return {
        "day": int(day),
        "headline": headline,
        "summary": summary,
        "macro_tags_json": deduped_tags,
        "category": category,
    }


def generate_player_daily_brief(
    db: Session,
    player_id: str | UUID,
    day: int,
    *,
    commit: bool = True,
) -> dict:
    """Generate and persist one player-tailored brief for a day."""
    if day <= 0:
        raise DailyBriefValidationError("day must be greater than 0.")

    try:
        player = _resolve_player(db, player_id)

        existing = (
            db.query(DailyBriefLog)
            .filter(
                DailyBriefLog.player_id == player.id,
                DailyBriefLog.day == day,
            )
            .first()
        )
        if existing is not None:
            payload = _serialize_brief_log(existing)
            payload["already_processed"] = True
            return payload

        global_event = generate_global_daily_event(db, day)
        macro_tags = list(global_event.get("macro_tags_json", []))

        settlement = (
            db.query(DailySettlementLog)
            .filter(
                DailySettlementLog.player_id == player.id,
                DailySettlementLog.day_number <= day,
            )
            .order_by(DailySettlementLog.day_number.desc(), DailySettlementLog.created_at.desc())
            .first()
        )
        settlement_summary = _parse_json(settlement.summary_json if settlement else None, default={})
        settlement_breakdown = settlement_summary.get("settlement_breakdown", {})
        if not isinstance(settlement_breakdown, dict):
            settlement_breakdown = {}
        yesterday_income_total_xgp = _money(
            _d(
                settlement_breakdown.get(
                    "total_income",
                    settlement_summary.get("total_income_xgp", getattr(settlement, "income_xgp", 0) if settlement else 0),
                )
            )
        )
        yesterday_expense_total_xgp = _money(
            _d(
                settlement_breakdown.get(
                    "total_expense",
                    settlement_summary.get(
                        "total_expense_xgp",
                        getattr(settlement, "expenses_xgp", 0) if settlement else 0,
                    ),
                )
            )
        )
        yesterday_net_change_xgp = _money(
            _d(
                settlement_breakdown.get(
                    "net_change",
                    settlement_summary.get("net_change_xgp", yesterday_income_total_xgp - yesterday_expense_total_xgp),
                )
            )
        )
        yesterday_biggest_expense_category = str(
            settlement_breakdown.get("biggest_expense_category", "none") or "none"
        )

        employment = (
            db.query(PlayerEmploymentState)
            .filter(
                PlayerEmploymentState.player_id == player.id,
                PlayerEmploymentState.day <= day,
            )
            .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
            .first()
        )

        housing_log = (
            db.query(HousingDailyLog)
            .filter(
                HousingDailyLog.player_id == player.id,
                HousingDailyLog.day <= day,
            )
            .order_by(HousingDailyLog.day.desc(), HousingDailyLog.created_at.desc())
            .first()
        )

        business_logs = (
            db.query(BusinessDailyLog)
            .filter(
                BusinessDailyLog.player_id == player.id,
                BusinessDailyLog.day == day,
            )
            .all()
        )

        consumption = (
            db.query(BasketConsumptionLog)
            .filter(
                BasketConsumptionLog.player_id == player.id,
                BasketConsumptionLog.day <= day,
            )
            .order_by(BasketConsumptionLog.day.desc(), BasketConsumptionLog.created_at.desc())
            .first()
        )

        debt = (
            db.query(DebtCreditLog)
            .filter(
                DebtCreditLog.player_id == player.id,
                DebtCreditLog.day <= day,
            )
            .order_by(DebtCreditLog.day.desc(), DebtCreditLog.created_at.desc())
            .first()
        )

        stock_context = _stock_context_for_player(db, player.id, day)

        pressures: list[tuple[int, str]] = []
        opportunities: list[tuple[int, str]] = []
        hints: list[str] = []
        system_scores: dict[str, int] = {
            "macro": 1,
            "housing": 0,
            "employment": 0,
            "business": 0,
            "consumption": 0,
            "debt_credit": 0,
            "stocks": 0,
        }

        # Macro framing.
        if "oil_up" in macro_tags or "transport_pressure" in macro_tags:
            pressures.append((2, "Fuel and transport costs are putting pressure on daily expenses."))
            hints.append("Fuel pressure may hurt transport-heavy businesses.")
            system_scores["macro"] += 2
        if "consumer_slowdown" in macro_tags or "confidence_down" in macro_tags:
            pressures.append((2, "Softer confidence points to weaker consumer demand today."))
            hints.append("Retail conditions are weaker today; preserve cash.")
            system_scores["macro"] += 2
        if "inflation_easing" in macro_tags or "consumer_relief" in macro_tags:
            opportunities.append((2, "Cooling inflation is giving household cash flow some relief."))
            system_scores["macro"] += 1

        # Housing context.
        if housing_log is not None:
            housing_cost = _d(housing_log.housing_cost_xgp)
            housing_stress = int(housing_log.stress_delta or 0)
            region = str(housing_log.region or player.region or "suburban")
            if housing_cost >= Decimal("30"):
                pressures.append((2, f"{region.title()} housing cost remained high at {housing_cost:.2f} XGP."))
                hints.append("Watch housing and convenience spending.")
                system_scores["housing"] += 2
            if housing_stress >= 2:
                pressures.append((2, "Housing and commute pressure added extra stress today."))
                system_scores["housing"] += 2
            elif housing_stress < 0:
                opportunities.append((1, "Lower housing stress helped stabilize your daily pressure."))
                system_scores["housing"] += 1
            if region == "downtown" and _d(housing_log.opportunity_modifier) >= Decimal("1.05"):
                opportunities.append((1, "Downtown location keeps opportunity flow stronger despite higher cost."))
                hints.append("Downtown opportunity remains strong, but stress is higher.")
                system_scores["housing"] += 1

        # Employment context.
        employment_event = str(
            settlement_summary.get("employment_event")
            or getattr(employment, "last_employment_event", None)
            or "none"
        ).lower()
        employment_status = str(
            settlement_summary.get("employment_status")
            or getattr(employment, "job_status", None)
            or ("employed" if bool(getattr(employment, "employed_flag", False)) else "seeking")
        ).lower()

        if employment_event == "layoff" or employment_status in {"seeking", "laid_off"}:
            pressures.append((3, "Employment conditions are fragile, increasing income uncertainty."))
            hints.append("Protect cash reserves while employment pressure is high.")
            system_scores["employment"] += 3
        elif employment_event == "promotion":
            opportunities.append((3, "A promotion event improved your income trajectory."))
            system_scores["employment"] += 3

        layoff_risk = _d(settlement_summary.get("layoff_risk_pct", getattr(employment, "layoff_risk_pct", 0)))
        if layoff_risk >= Decimal("14"):
            pressures.append((2, f"Layoff risk is elevated at {layoff_risk:.1f}% for your job context."))
            system_scores["employment"] += 2

        # Business context.
        business_net = Decimal("0")
        if business_logs:
            business_net = sum((_d(row.net_profit_xgp) for row in business_logs), Decimal("0"))
        else:
            business_net = _d(settlement_summary.get("total_business_profit_xgp", 0))

        if business_net > Decimal("5"):
            opportunities.append((2, f"Business operations added {business_net:.2f} XGP net today."))
            hints.append("Keep reinforcing the business line that is producing net gains.")
            system_scores["business"] += 2
        elif business_net < Decimal("-5"):
            pressures.append((2, f"Business operations lost {abs(business_net):.2f} XGP and tightened cash flow."))
            hints.append("Review business costs before scaling operations.")
            system_scores["business"] += 2

        # Debt and credit context.
        if debt is not None:
            payment_status = str(debt.payment_status or "no_debt")
            score_change = int(debt.credit_score_change or 0)
            if payment_status == "missed":
                pressures.append((3, "You missed debt service today, which damaged credit momentum."))
                hints.append("Your debt pressure is rising; protect cash flow.")
                system_scores["debt_credit"] += 3
            elif payment_status == "paid_partial":
                pressures.append((2, "Debt payment was partial, leaving ongoing delinquency pressure."))
                hints.append("Prioritize minimum debt servicing before optional spend.")
                system_scores["debt_credit"] += 2
            elif payment_status == "paid_full":
                opportunities.append((2, "You covered debt due in full, helping credit stability."))
                system_scores["debt_credit"] += 2

            if bool(debt.delinquency_flag):
                pressures.append((2, "Delinquency remains active, so repeated misses would stack credit damage."))
                system_scores["debt_credit"] += 2

            if score_change > 0:
                opportunities.append((1, "Credit score direction improved after today's payment behavior."))
                system_scores["debt_credit"] += 1
            elif score_change < 0:
                pressures.append((1, "Credit score moved down, signaling higher borrowing pressure."))
                system_scores["debt_credit"] += 1

        # Consumption context.
        if consumption is not None:
            budget_pressure = _d(consumption.budget_pressure_score)
            nutrition_pressure = _d(consumption.nutrition_pressure_score)
            if budget_pressure >= Decimal("0.90"):
                pressures.append((3, "Consumption budget pressure is severe and squeezing flexibility."))
                hints.append("Cut convenience spend until liquidity improves.")
                system_scores["consumption"] += 3
            elif budget_pressure >= Decimal("0.70"):
                pressures.append((2, "Consumption pressure is high, so daily spending is less forgiving."))
                hints.append("Track essentials first, then flexible basket categories.")
                system_scores["consumption"] += 2
            elif budget_pressure <= Decimal("0.35"):
                opportunities.append((1, "Daily basket pressure is currently manageable."))
                system_scores["consumption"] += 1

            if nutrition_pressure >= Decimal("0.65"):
                pressures.append((1, "Nutrition pressure is elevated as food pricing and budget stress combine."))
                hints.append("Shift spending toward essentials and produce for better recovery.")
                system_scores["consumption"] += 1

        # Stock context.
        if stock_context.get("has_positions"):
            weighted_pct = _d(stock_context.get("weighted_daily_change_pct", 0))
            if weighted_pct >= Decimal("1.50"):
                opportunities.append((2, f"Your held stocks moved +{weighted_pct:.2f}% on the day."))
                system_scores["stocks"] += 2
            elif weighted_pct <= Decimal("-1.50"):
                pressures.append((2, f"Your held stocks moved {weighted_pct:.2f}% and added market drag."))
                hints.append("Avoid overexposure while market swings are unfavorable.")
                system_scores["stocks"] += 2
        else:
            market_avg = stock_context.get("market_average_change_pct")
            if market_avg is not None and abs(float(market_avg)) >= 1.2:
                if market_avg > 0:
                    opportunities.append((1, "Broad market tone improved, which may open investing opportunities."))
                else:
                    pressures.append((1, "Broad market tone was weak, favoring a cautious posture."))
                system_scores["stocks"] += 1

        if not hints:
            hints.append("Keep balancing income stability, debt servicing, and daily essentials.")

        biggest_pressure = (
            sorted(pressures, key=lambda x: x[0], reverse=True)[0][1]
            if pressures
            else "No acute pressure spike dominated your day."
        )
        biggest_opportunity = (
            sorted(opportunities, key=lambda x: x[0], reverse=True)[0][1]
            if opportunities
            else "No major upside swing stood out today."
        )

        system_changed_most = max(system_scores.items(), key=lambda item: item[1])[0]

        player_summary = (
            f"{global_event['summary']} "
            f"For you: {biggest_pressure} "
            f"Main opportunity: {biggest_opportunity}"
        )

        player_impact = {
            "biggest_pressure": biggest_pressure,
            "biggest_opportunity": biggest_opportunity,
            "system_changed_most": system_changed_most,
            "yesterday_income_total_xgp": float(yesterday_income_total_xgp),
            "yesterday_expense_total_xgp": float(yesterday_expense_total_xgp),
            "yesterday_biggest_expense_category": yesterday_biggest_expense_category,
            "yesterday_net_change_xgp": float(yesterday_net_change_xgp),
            "notable_signals": [
                entry[1] for entry in sorted(pressures + opportunities, key=lambda x: x[0], reverse=True)[:4]
            ],
        }

        deduped_hints = list(dict.fromkeys(hints))[:5]

        row = DailyBriefLog(
            player_id=player.id,
            day=int(day),
            headline=str(global_event["headline"]),
            summary=player_summary,
            macro_tags_json=json.dumps(macro_tags),
            player_impact_json=json.dumps(player_impact),
            action_hints_json=json.dumps(deduped_hints),
        )
        db.add(row)
        db.flush()

        if commit:
            db.commit()
            db.refresh(row)

        payload = _serialize_brief_log(row)
        payload["already_processed"] = False
        return payload

    except DailyBriefError:
        if commit:
            db.rollback()
        raise
    except Exception as exc:
        if commit:
            db.rollback()
        raise DailyBriefError("Unexpected daily brief generation error.") from exc


def get_player_latest_daily_brief(db: Session, player_id: str | UUID) -> dict:
    """Return latest stored daily brief for a player."""
    player = _resolve_player(db, player_id)
    row = (
        db.query(DailyBriefLog)
        .filter(DailyBriefLog.player_id == player.id)
        .order_by(DailyBriefLog.day.desc(), DailyBriefLog.created_at.desc())
        .first()
    )
    if row is None:
        raise DailyBriefNotFoundError("No daily brief found for player.")
    return _serialize_brief_log(row)


def get_player_daily_brief_history(db: Session, player_id: str | UUID, limit: int = 10) -> dict:
    """Return recent daily briefs for a player."""
    if limit <= 0:
        raise DailyBriefValidationError("limit must be greater than 0.")

    player = _resolve_player(db, player_id)
    rows = (
        db.query(DailyBriefLog)
        .filter(DailyBriefLog.player_id == player.id)
        .order_by(DailyBriefLog.day.desc(), DailyBriefLog.created_at.desc())
        .limit(int(limit))
        .all()
    )

    return {
        "player_id": str(player.id),
        "count": len(rows),
        "briefs": [_serialize_brief_log(row) for row in rows],
    }


def _serialize_brief_log(row: DailyBriefLog) -> dict:
    return {
        "id": str(row.id),
        "player_id": str(row.player_id) if row.player_id else None,
        "day": int(row.day),
        "headline": str(row.headline),
        "summary": str(row.summary),
        "macro_tags_json": _parse_json(row.macro_tags_json, default=[]),
        "player_impact_json": _parse_json(row.player_impact_json, default={}),
        "action_hints_json": _parse_json(row.action_hints_json, default=[]),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def build_daily_economy_brief(
    db: Session,
    as_of_date: date | None = None,
    *,
    day: int | None = None,
    supply_chain_snapshot: dict | None = None,
    basket_pricing_daily: dict | None = None,
    job_market_daily: dict | None = None,
) -> dict:
    """Build a deterministic explainability brief from supply/basket/job outputs."""
    if day is not None and int(day) <= 0:
        raise DailyBriefValidationError("day must be greater than 0.")

    if supply_chain_snapshot is None:
        supply_chain_snapshot = compute_supply_chain_daily_snapshot(
            db,
            as_of_date=as_of_date if day is None else None,
            macro_day=int(day) if day is not None else None,
        )

    resolved_day = int(day) if day is not None else int(supply_chain_snapshot["debug_meta"]["macro_day"])
    resolved_as_of_date = (
        as_of_date
        if as_of_date is not None
        else (
            supply_chain_snapshot.get("as_of_date")
            if isinstance(supply_chain_snapshot.get("as_of_date"), date)
            else date.today()
        )
    )

    if basket_pricing_daily is None:
        basket_pricing_daily = compute_daily_basket_price_updates(
            db,
            as_of_date=as_of_date if day is None else None,
            day=resolved_day,
            persist=False,
            commit=False,
        )

    if job_market_daily is None:
        job_market_daily = compute_daily_job_market_updates(
            db,
            as_of_date=as_of_date if day is None else None,
            day=resolved_day,
        )

    bottlenecks = list(supply_chain_snapshot.get("bottlenecks", []))
    basket_updates = list(basket_pricing_daily.get("basket_updates", []))
    job_updates = list(job_market_daily.get("job_updates", []))

    top_bottlenecks_rows = bottlenecks[:3]
    top_bottlenecks = [str(row["node_key"]) for row in top_bottlenecks_rows]

    basket_ranked = sorted(
        basket_updates,
        key=lambda row: (-abs(_d(row.get("daily_change", 0))), str(row.get("basket_key", ""))),
    )
    top_basket_rows = basket_ranked[:3]
    top_basket_movers = [str(row.get("basket_key")) for row in top_basket_rows if row.get("basket_key")]

    job_ranked = sorted(
        job_updates,
        key=lambda row: (
            -max(abs(_d(row.get("pressure", 0))), abs(_d(row.get("opportunity_modifier", 0)))),
            str(row.get("job_key", "")),
        ),
    )
    top_job_rows = job_ranked[:3]
    top_job_changes = [str(row.get("job_key")) for row in top_job_rows if row.get("job_key")]

    if top_bottlenecks and top_basket_movers:
        lead_bottleneck = top_bottlenecks[0].replace("_", " ")
        second_bottleneck = top_bottlenecks[1].replace("_", " ") if len(top_bottlenecks) > 1 else "supply"
        lead_basket = top_basket_movers[0].replace("_", " ")
        headline = f"{lead_bottleneck.title()} and {second_bottleneck} pressure tightened {lead_basket} supply."
    elif top_basket_movers:
        lead_basket = top_basket_movers[0].replace("_", " ")
        headline = f"{lead_basket.title()} pricing moved as macro and supply signals shifted."
    else:
        headline = "Economic conditions held in a mixed range with limited basket and labor movement."

    summary_lines: list[str] = []

    if top_basket_rows:
        basket_row = top_basket_rows[0]
        basket_key = str(basket_row.get("basket_key", "basket")).replace("_", " ")
        daily_change = _d(basket_row.get("daily_change", 0))
        if daily_change >= Decimal("0"):
            summary_lines.append(
                f"{basket_key.title()} prices rose ({daily_change * Decimal('100'):+.2f} bps) as supply tightened."
            )
        else:
            summary_lines.append(
                f"{basket_key.title()} prices eased ({daily_change * Decimal('100'):+.2f} bps) as pressure cooled."
            )

    if top_job_rows:
        job_row = top_job_rows[0]
        job_key = str(job_row.get("job_key", "job")).replace("_", " ")
        direction = str(job_row.get("direction", "neutral"))
        pressure = _d(job_row.get("pressure", 0))
        if direction == "up":
            summary_lines.append(
                f"{job_key.title()} demand improved as pressure moved {pressure:+.2f}."
            )
        elif direction == "down":
            summary_lines.append(
                f"{job_key.title()} conditions softened as pressure moved {pressure:+.2f}."
            )
        else:
            summary_lines.append(
                f"{job_key.title()} stayed broadly stable despite mixed macro signals."
            )

    if top_bottlenecks:
        readable = ", ".join(node.replace("_", " ") for node in top_bottlenecks[:2])
        summary_lines.append(f"Top bottlenecks today: {readable}.")
    else:
        summary_lines.append("No major bottleneck crossed the severity threshold today.")

    return {
        "as_of_date": resolved_as_of_date,
        "day": int(resolved_day),
        "headline": headline,
        "summary_lines": summary_lines[:3],
        "top_bottlenecks": top_bottlenecks,
        "top_basket_movers": top_basket_movers,
        "top_job_changes": top_job_changes,
        "debug_meta": {
            "constants_version": "daily_economy_brief_v1",
            "supply_chain_macro_state_id": supply_chain_snapshot.get("macro_state_id"),
            "basket_pricing_macro_state_id": basket_pricing_daily.get("macro_state_id"),
            "job_market_macro_state_id": job_market_daily.get("macro_state_id"),
            "bottleneck_count": len(bottlenecks),
            "basket_update_count": len(basket_updates),
            "job_update_count": len(job_updates),
        },
    }
