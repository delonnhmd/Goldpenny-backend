"""Computed player timeline events for lifelong-run story surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.models.business_daily_log import BusinessDailyLog
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_settlement_log import DailySettlementLog
from app.models.game_state import GameState
from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.models.player_daily_state import PlayerDailyState
from app.models.player_net_worth_snapshot import PlayerNetWorthSnapshot
from app.models.player_black_swan_event import PlayerBlackSwanEvent
from app.models.player_progression_state import PlayerProgressionState

MONEY_Q = Decimal("0.01")
DEFAULT_LIMIT = 100
MAX_LIMIT = 200
MAX_EVENTS_PER_DAY = 3

MAJOR_ECONOMY_SEVERITY = Decimal("1.50")
REALWORLD_ECONOMY_MAGNITUDE = 0.60
BUSINESS_PROFIT_SPIKE_XGP = Decimal("250.00")
BUSINESS_LOSS_SPIKE_XGP = Decimal("100.00")
BUSINESS_SPOILAGE_WARNING_XGP = Decimal("40.00")
BUSINESS_LOW_INVENTORY_UNITS = Decimal("2.00")
NET_WORTH_MILESTONES = (
    Decimal("10000.00"),
    Decimal("50000.00"),
    Decimal("100000.00"),
)
DEBT_SPIKE_MIN_INCREASE_XGP = Decimal("500.00")
DEBT_SPIKE_MIN_TOTAL_XGP = Decimal("2500.00")
STREAK_MILESTONES = (3, 7, 14)

TYPE_PRIORITY = {
    "finance": 40,
    "business": 35,
    "life": 30,
    "economy": 25,
}
IMPACT_PRIORITY = {
    "high": 30,
    "medium": 20,
    "low": 10,
}


class TimelineError(Exception):
    """Base timeline exception."""


class TimelineNotFoundError(TimelineError):
    """Raised when a player cannot be found."""


@dataclass(frozen=True)
class TimelineEvent:
    day: int
    type: str
    title: str
    description: str
    impact_level: str
    icon: str
    priority: int

    def as_payload(self) -> dict:
        return {
            "day": int(self.day),
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "impact_level": self.impact_level,
            "icon": self.icon,
        }


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: object) -> Decimal:
    return _d(value).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(fallback)


def _money_text(value: object) -> str:
    amount = _money(value)
    return f"{amount:,.2f} XGP"


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    try:
        pid = player_id if isinstance(player_id, UUID) else UUID(str(player_id))
    except ValueError as exc:
        raise TimelineNotFoundError("Player not found.") from exc

    player = db.query(Player).filter(Player.id == pid).first()
    if player is None:
        raise TimelineNotFoundError("Player not found.")
    return player


def _current_player_day(db: Session, player: Player) -> int:
    candidates = [
        _safe_int(getattr(player, "last_settled_day", 0), 0),
        _safe_int(getattr(player, "run_end_day", 0), 0),
    ]

    max_daily_state_day = (
        db.query(func.max(PlayerDailyState.day_number))
        .filter(PlayerDailyState.player_id == player.id)
        .scalar()
    )
    max_settlement_day = (
        db.query(func.max(DailySettlementLog.day_number))
        .filter(DailySettlementLog.player_id == player.id)
        .scalar()
    )
    max_snapshot_day = (
        db.query(func.max(PlayerNetWorthSnapshot.day))
        .filter(PlayerNetWorthSnapshot.player_id == player.id)
        .scalar()
    )
    max_business_day = (
        db.query(func.max(BusinessDailyLog.day))
        .filter(BusinessDailyLog.player_id == player.id)
        .scalar()
    )
    candidates.extend([
        _safe_int(max_daily_state_day, 0),
        _safe_int(max_settlement_day, 0),
        _safe_int(max_snapshot_day, 0),
        _safe_int(max_business_day, 0),
    ])

    state = db.query(GameState).order_by(GameState.id.asc()).first()
    if state is not None:
        candidates.append(_safe_int(getattr(state, "current_day", 1), 1))

    return max(1, *candidates)


def _impact_priority(impact_level: str) -> int:
    return IMPACT_PRIORITY.get(impact_level, IMPACT_PRIORITY["low"])


def _event_priority(event_type: str, impact_level: str, boost: int = 0) -> int:
    return TYPE_PRIORITY.get(event_type, 10) + _impact_priority(impact_level) + int(boost)


def _event(
    *,
    day: int,
    event_type: str,
    title: str,
    description: str,
    impact_level: str,
    icon: str,
    boost: int = 0,
) -> TimelineEvent:
    return TimelineEvent(
        day=max(1, _safe_int(day, 1)),
        type=event_type,
        title=str(title or "Timeline event").strip() or "Timeline event",
        description=str(description or "A meaningful run event was recorded.").strip()
        or "A meaningful run event was recorded.",
        impact_level=impact_level if impact_level in IMPACT_PRIORITY else "low",
        icon=str(icon or "circle").strip() or "circle",
        priority=_event_priority(event_type, impact_level, boost),
    )


def _humanize_key(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "business"
    return raw.replace("_", " ").replace("-", " ").lower()


def _build_economy_events(db: Session, current_day: int) -> list[TimelineEvent]:
    rows = (
        db.query(DailyEconomyEvent)
        .filter(DailyEconomyEvent.day <= int(current_day))
        .order_by(DailyEconomyEvent.day.asc())
        .all()
    )
    events: list[TimelineEvent] = []
    for row in rows:
        severity = _d(getattr(row, "severity", 0))
        magnitude = getattr(row, "magnitude", None)
        magnitude_value = float(magnitude) if magnitude is not None else 0.0
        anchored = bool(getattr(row, "is_realworld_anchored", False))
        major = severity >= MAJOR_ECONOMY_SEVERITY or (
            anchored and magnitude_value >= REALWORLD_ECONOMY_MAGNITUDE
        )
        if not major:
            continue

        sentiment = str(getattr(row, "sentiment", "neutral") or "neutral").lower()
        impact = "high" if severity >= Decimal("2.20") or magnitude_value >= 0.80 else "medium"
        icon = "trending-up" if sentiment == "positive" else "alert-triangle"
        events.append(_event(
            day=_safe_int(row.day, 1),
            event_type="economy",
            title=str(row.headline or "Major economy shift"),
            description=str(row.summary or f"{_humanize_key(row.event_category).title()} conditions shifted."),
            impact_level=impact,
            icon=icon,
            boost=5 if anchored else 0,
        ))
    return events


def _table_available(db: Session, table_name: str) -> bool:
    try:
        return bool(inspect(db.get_bind()).has_table(table_name))
    except Exception:
        return True


def _build_black_swan_events(db: Session, player: Player, current_day: int) -> list[TimelineEvent]:
    if not _table_available(db, PlayerBlackSwanEvent.__tablename__):
        return []
    rows = (
        db.query(PlayerBlackSwanEvent)
        .filter(
            PlayerBlackSwanEvent.player_id == player.id,
            PlayerBlackSwanEvent.day <= int(current_day),
        )
        .order_by(PlayerBlackSwanEvent.day.asc(), PlayerBlackSwanEvent.created_at.asc())
        .all()
    )
    return [
        _event(
            day=_safe_int(row.day, 1),
            event_type="economy",
            title=str(row.title or "Black swan event"),
            description=str(row.description or "A rare major event moved through the city."),
            impact_level="high",
            icon="alert-triangle",
            boost=35,
        )
        for row in rows
    ]


def _build_business_events(db: Session, player: Player, current_day: int) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    first_business = (
        db.query(PlayerBusiness)
        .filter(
            PlayerBusiness.player_id == player.id,
            PlayerBusiness.created_day <= int(current_day),
        )
        .order_by(PlayerBusiness.created_day.asc(), PlayerBusiness.created_at.asc())
        .first()
    )
    if first_business is not None:
        label = _humanize_key(getattr(first_business, "business_name", None) or first_business.business_id)
        events.append(_event(
            day=_safe_int(first_business.created_day, 1),
            event_type="business",
            title="First business opened",
            description=f"Opened your first {label}.",
            impact_level="high",
            icon="store",
            boost=20,
        ))

    rows = (
        db.query(BusinessDailyLog)
        .filter(
            BusinessDailyLog.player_id == player.id,
            BusinessDailyLog.day <= int(current_day),
        )
        .order_by(BusinessDailyLog.day.asc(), BusinessDailyLog.created_at.asc())
        .all()
    )
    for row in rows:
        day = _safe_int(row.day, 1)
        label = _humanize_key(getattr(row, "business_type", None) or "business")
        profit = _money(row.net_profit_xgp)
        if profit >= BUSINESS_PROFIT_SPIKE_XGP:
            events.append(_event(
                day=day,
                event_type="business",
                title="Business profit spike",
                description=f"Your {label} cleared {_money_text(profit)} in daily profit.",
                impact_level="high" if profit >= BUSINESS_PROFIT_SPIKE_XGP * 2 else "medium",
                icon="store",
                boost=8,
            ))
        elif profit <= -BUSINESS_LOSS_SPIKE_XGP:
            events.append(_event(
                day=day,
                event_type="business",
                title="Business loss spike",
                description=f"Your {label} lost {_money_text(abs(profit))} in one day.",
                impact_level="high" if abs(profit) >= BUSINESS_LOSS_SPIKE_XGP * 2 else "medium",
                icon="warning",
                boost=8,
            ))

        spoilage = _money(getattr(row, "spoilage_cost_xgp", 0))
        if spoilage >= BUSINESS_SPOILAGE_WARNING_XGP:
            events.append(_event(
                day=day,
                event_type="business",
                title="Inventory spoilage hit",
                description=f"Spoilage cost the {label} {_money_text(spoilage)}.",
                impact_level="medium",
                icon="inventory",
            ))

        inventory_end = _d(getattr(row, "inventory_end_units", 0))
        units_sold = _safe_int(getattr(row, "units_sold", 0), 0)
        if units_sold > 0 and inventory_end <= BUSINESS_LOW_INVENTORY_UNITS:
            events.append(_event(
                day=day,
                event_type="business",
                title="Inventory warning",
                description=f"Your {label} ended the day nearly out of stock.",
                impact_level="low",
                icon="inventory",
            ))
    return events


def _build_life_events(db: Session, player: Player, current_day: int) -> list[TimelineEvent]:
    rows = (
        db.query(PlayerDailyState)
        .filter(
            PlayerDailyState.player_id == player.id,
            PlayerDailyState.day_number <= int(current_day),
        )
        .order_by(PlayerDailyState.day_number.asc())
        .all()
    )
    events: list[TimelineEvent] = []
    previous_missed_day: int | None = None
    stress_alert_active = False
    health_alert_active = False
    for row in rows:
        day = _safe_int(row.day_number, 1)
        missed = bool(getattr(row, "missed_shift", False))
        if missed and previous_missed_day != day - 1:
            penalty = _money(getattr(row, "missed_penalty", 0))
            description = "A scheduled work day was missed."
            if penalty > Decimal("0.00"):
                description = f"Missed work triggered {_money_text(penalty)} in penalties."
            events.append(_event(
                day=day,
                event_type="life",
                title="Missed work day",
                description=description,
                impact_level="medium",
                icon="calendar-x",
                boost=6,
            ))
        if missed:
            previous_missed_day = day

        stress_end = _safe_int(getattr(row, "stress_end", 0), 0)
        if stress_end >= 80 and not stress_alert_active:
            events.append(_event(
                day=day,
                event_type="life",
                title="Stress warning",
                description=f"Stress reached {stress_end}. Recovery became more important.",
                impact_level="high" if stress_end >= 90 else "medium",
                icon="heart-pulse",
            ))
            stress_alert_active = True
        elif stress_end < 70:
            stress_alert_active = False

        health_end = _safe_int(getattr(row, "health_end", 100), 100)
        if health_end <= 35 and not health_alert_active:
            events.append(_event(
                day=day,
                event_type="life",
                title="Health warning",
                description=f"Health dropped to {health_end}. The run entered a fragile state.",
                impact_level="high" if health_end <= 25 else "medium",
                icon="heart",
            ))
            health_alert_active = True
        elif health_end > 45:
            health_alert_active = False

    progression = (
        db.query(PlayerProgressionState)
        .filter(PlayerProgressionState.player_id == player.id)
        .first()
    )
    if progression is not None:
        events.extend(_build_streak_events(progression, current_day))
    return events


def _build_streak_events(progression: PlayerProgressionState, current_day: int) -> list[TimelineEvent]:
    streaks = [
        ("login", "Login streak", "showed up for consecutive days", "calendar-check"),
        ("productive_day", "Productive streak", "kept productive days alive", "flame"),
        ("positive_cash_flow", "Cash-flow streak", "stayed cash-flow positive", "wallet"),
        ("training", "Training streak", "kept training momentum", "graduation-cap"),
        ("business_consistency", "Business streak", "kept business operations consistent", "store"),
        ("low_distress", "Low-distress streak", "kept distress under control", "shield"),
    ]
    events: list[TimelineEvent] = []
    seen: set[tuple[int, int, str]] = set()
    for prefix, title_prefix, description_fragment, icon in streaks:
        best = _safe_int(getattr(progression, f"{prefix}_streak_best", 0), 0)
        last_day = _safe_int(getattr(progression, f"{prefix}_streak_last_day", 0), 0)
        for threshold in STREAK_MILESTONES:
            if best < threshold:
                continue
            milestone_day = threshold
            if last_day > 0:
                milestone_day = max(1, last_day - best + threshold)
            milestone_day = min(max(1, milestone_day), max(1, current_day))
            key = (milestone_day, threshold, title_prefix)
            if key in seen:
                continue
            seen.add(key)
            events.append(_event(
                day=milestone_day,
                event_type="life",
                title=f"{threshold}-day {title_prefix.lower()}",
                description=f"You {description_fragment} for {threshold} days.",
                impact_level="high" if threshold >= 14 else "medium",
                icon=icon,
                boost=threshold,
            ))
    return events


def _build_finance_events(db: Session, player: Player, current_day: int) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    snapshots = (
        db.query(PlayerNetWorthSnapshot)
        .filter(
            PlayerNetWorthSnapshot.player_id == player.id,
            PlayerNetWorthSnapshot.day <= int(current_day),
        )
        .order_by(PlayerNetWorthSnapshot.day.asc(), PlayerNetWorthSnapshot.created_at.asc())
        .all()
    )
    previous_net_worth = Decimal("0.00")
    previous_debt = Decimal("0.00")
    crossed_positive = False
    crossed_milestones: set[Decimal] = set()
    for snapshot in snapshots:
        day = _safe_int(snapshot.day, 1)
        net_worth = _money(snapshot.net_worth_xgp)
        debt = _money(snapshot.debt_xgp)
        if not crossed_positive and previous_net_worth <= Decimal("0.00") < net_worth:
            events.append(_event(
                day=day,
                event_type="finance",
                title="First positive net worth",
                description=f"Net worth crossed above zero at {_money_text(net_worth)}.",
                impact_level="high",
                icon="wallet",
                boost=20,
            ))
            crossed_positive = True

        for milestone in NET_WORTH_MILESTONES:
            if milestone in crossed_milestones:
                continue
            if previous_net_worth < milestone <= net_worth:
                events.append(_event(
                    day=day,
                    event_type="finance",
                    title=f"Reached {_money_text(milestone)} net worth",
                    description=f"Net worth climbed to {_money_text(net_worth)}.",
                    impact_level="high",
                    icon="trophy",
                    boost=25,
                ))
                crossed_milestones.add(milestone)

        debt_increase = debt - previous_debt
        if previous_debt > Decimal("0.00") and debt >= DEBT_SPIKE_MIN_TOTAL_XGP and debt_increase >= DEBT_SPIKE_MIN_INCREASE_XGP:
            events.append(_event(
                day=day,
                event_type="finance",
                title="Debt spike",
                description=f"Debt rose by {_money_text(debt_increase)} to {_money_text(debt)}.",
                impact_level="high",
                icon="credit-card",
                boost=8,
            ))

        if net_worth <= Decimal("-1000.00") and previous_net_worth > Decimal("-1000.00"):
            events.append(_event(
                day=day,
                event_type="finance",
                title="Bankruptcy warning",
                description=f"Net worth fell to {_money_text(net_worth)}.",
                impact_level="high",
                icon="alert-octagon",
                boost=18,
            ))

        previous_net_worth = net_worth
        previous_debt = debt

    settlements = (
        db.query(DailySettlementLog)
        .filter(
            DailySettlementLog.player_id == player.id,
            DailySettlementLog.day_number <= int(current_day),
        )
        .order_by(DailySettlementLog.day_number.asc(), DailySettlementLog.created_at.asc())
        .all()
    )
    previous_missed_day: int | None = None
    for row in settlements:
        day = _safe_int(row.day_number, 1)
        missed_payment = bool(getattr(row, "debt_payment_missed", False))
        if missed_payment and previous_missed_day != day - 1:
            due = _money(getattr(row, "debt_payment_due_xgp", 0))
            late_fee = _money(getattr(row, "late_fee_xgp", 0))
            parts = []
            if due > Decimal("0.00"):
                parts.append(f"{_money_text(due)} due")
            if late_fee > Decimal("0.00"):
                parts.append(f"{_money_text(late_fee)} late fee")
            detail = ", ".join(parts) if parts else "Debt payment was missed."
            events.append(_event(
                day=day,
                event_type="finance",
                title="Missed payment",
                description=detail,
                impact_level="high",
                icon="credit-card",
                boost=18,
            ))
        if missed_payment:
            previous_missed_day = day

        distress_state = str(getattr(row, "distress_state_after", "") or "").lower()
        distress_score = _d(getattr(row, "distress_score_after", 0))
        if distress_state in {"crisis", "default", "bankruptcy_warning"} or distress_score >= Decimal("80"):
            events.append(_event(
                day=day,
                event_type="finance",
                title="Bankruptcy warning",
                description="Debt distress reached a dangerous level.",
                impact_level="high",
                icon="alert-octagon",
                boost=16,
            ))
    return events


def _dedupe_and_cap(events: list[TimelineEvent], limit: int) -> list[TimelineEvent]:
    unique: dict[tuple[int, str, str], TimelineEvent] = {}
    for event in events:
        key = (event.day, event.type, event.title.lower())
        current = unique.get(key)
        if current is None or event.priority > current.priority:
            unique[key] = event

    grouped: dict[int, list[TimelineEvent]] = {}
    for event in unique.values():
        grouped.setdefault(event.day, []).append(event)

    capped: list[TimelineEvent] = []
    for day in sorted(grouped.keys(), reverse=True):
        rows = sorted(
            grouped[day],
            key=lambda item: (item.priority, item.title),
            reverse=True,
        )
        capped.extend(rows[:MAX_EVENTS_PER_DAY])

    capped.sort(key=lambda item: (item.day, item.priority, item.title), reverse=True)
    return capped[:limit]


def build_player_timeline(
    db: Session,
    player_id: str | UUID,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Build a filtered, read-only timeline for a player's current run."""
    player = _resolve_player(db, player_id)
    safe_limit = max(1, min(MAX_LIMIT, _safe_int(limit, DEFAULT_LIMIT)))
    current_day = _current_player_day(db, player)

    events: list[TimelineEvent] = []
    events.extend(_build_economy_events(db, current_day))
    events.extend(_build_black_swan_events(db, player, current_day))
    events.extend(_build_business_events(db, player, current_day))
    events.extend(_build_life_events(db, player, current_day))
    events.extend(_build_finance_events(db, player, current_day))

    return [event.as_payload() for event in _dedupe_and_cap(events, safe_limit)]
