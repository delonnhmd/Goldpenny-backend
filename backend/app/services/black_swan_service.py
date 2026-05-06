"""Black swan event promotion service.

This service is intentionally presentation-only. It reads existing economy and
event rows, promotes rare high-impact moments into a player log, and never
changes economy, business, or map calculations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.basket_daily_price import BasketDailyPrice
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.macro_daily_state import MacroDailyState
from app.models.player import Player
from app.models.player_black_swan_event import PlayerBlackSwanEvent
from app.models.stock_daily_price import StockDailyPrice
from app.services.run_end_service import RUN_STATUS_ACTIVE, normalize_run_status

Q4 = Decimal("0.0001")
COOLDOWN_DAYS = 14

OIL_MOVE_THRESHOLD_PCT = Decimal("5.0")
INFLATION_INCREASE_THRESHOLD = Decimal("0.25")
UNEMPLOYMENT_INCREASE_THRESHOLD = Decimal("0.4")
CONSUMER_CONFIDENCE_DROP_THRESHOLD = Decimal("4")
SUPPLY_CHAIN_INCREASE_THRESHOLD = Decimal("5")
BASKET_MOVE_THRESHOLD_PCT = Decimal("4")
STOCK_MOVE_THRESHOLD_PCT = Decimal("5")
HIGH_EVENT_SEVERITY_THRESHOLD = Decimal("2.20")
HIGH_EVENT_MAGNITUDE_THRESHOLD = Decimal("0.80")


class BlackSwanError(Exception):
    """Base exception for black swan failures."""


class BlackSwanNotFoundError(BlackSwanError):
    """Raised when the player or black swan event cannot be found."""


@dataclass(frozen=True)
class BlackSwanCandidate:
    day: int
    event_type: str
    title: str
    description: str
    severity_score: Decimal
    payload: dict
    source_event_id: UUID | None = None


def _d(value: object) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _percent_value(value: object) -> Decimal:
    raw = _d(value)
    magnitude = abs(raw)
    if magnitude > Decimal("0") and magnitude <= Decimal("1"):
        magnitude *= Decimal("100")
    return _q4(magnitude)


def _percent_change(current: object, previous: object) -> Decimal:
    previous_value = _d(previous)
    if previous_value == Decimal("0"):
        return Decimal("0")
    return _q4(((_d(current) - previous_value) / abs(previous_value)) * Decimal("100"))


def _delta_text(label: str, value: Decimal, unit: str = "") -> str:
    prefix = "+" if value >= 0 else ""
    suffix = f" {unit}" if unit else ""
    return f"{label} {prefix}{float(_q4(value)):.2f}{suffix}"


def _safe_uuid(value: str | UUID) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError as exc:
        raise BlackSwanNotFoundError("Player not found.") from exc


def _resolve_player(db: Session, player_id: str | UUID) -> Player:
    player = db.query(Player).filter(Player.id == _safe_uuid(player_id)).first()
    if player is None:
        raise BlackSwanNotFoundError("Player not found.")
    return player


def _table_available(db: Session, table_name: str) -> bool:
    normalized = str(table_name or "").strip()
    if not normalized:
        return False
    table_cache = db.info.setdefault("_table_exists_cache", {})
    cached = table_cache.get(normalized)
    if cached is not None:
        return bool(cached)
    try:
        available = bool(inspect(db.connection()).has_table(normalized))
    except Exception:
        available = True
    table_cache[normalized] = available
    return available


def _json_loads(raw: object) -> object:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return None


def _json_list(raw: object) -> list:
    if isinstance(raw, list):
        return raw
    return []


def _push_payload(event_id: UUID | str) -> dict:
    return {
        "type": "black_swan",
        "screen": "BlackSwan",
        "event_id": str(event_id),
    }


def _candidate_payload(
    *,
    affected_systems: list[str],
    what_changed_today: list[str],
    what_this_means: list[str],
    source: dict,
) -> dict:
    return {
        "affected_systems": affected_systems[:6],
        "what_changed_today": what_changed_today[:5],
        "what_this_means": what_this_means[:3],
        "source": source,
    }


def _oil_candidate(day: int, change_pct: Decimal, current: MacroDailyState, previous: MacroDailyState) -> BlackSwanCandidate:
    rising = change_pct >= 0
    title = "Oil Shock Hits the City" if rising else "Oil Market Breaks Lower"
    description = (
        "Fuel costs surged today, raising pressure on deliveries, food trucks, and transportation."
        if rising
        else "Oil moved sharply lower today, changing fuel pressure across transportation and supply chains."
    )
    return BlackSwanCandidate(
        day=day,
        event_type="oil_shock",
        title=title,
        description=description,
        severity_score=Decimal("500") + abs(change_pct) * Decimal("10"),
        payload=_candidate_payload(
            affected_systems=["Fuel", "Transportation", "Food", "Deliveries"],
            what_changed_today=[
                f"Oil index moved {float(change_pct):+.2f}% from {float(_d(previous.oil_index)):.2f} to {float(_d(current.oil_index)):.2f}.",
            ],
            what_this_means=[
                "Food truck margins may shrink.",
                "Rideshare fuel costs may rise.",
                "Produce and protein costs may increase.",
            ],
            source={"kind": "macro_daily_state", "field": "oil_index"},
        ),
    )


def _macro_candidates(db: Session, day: int) -> list[BlackSwanCandidate]:
    current = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day == int(day))
        .order_by(MacroDailyState.created_at.desc())
        .first()
    )
    previous = (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day < int(day))
        .order_by(MacroDailyState.day.desc(), MacroDailyState.created_at.desc())
        .first()
    )
    if current is None or previous is None:
        return []

    candidates: list[BlackSwanCandidate] = []
    oil_change = _percent_change(current.oil_index, previous.oil_index)
    if abs(oil_change) >= OIL_MOVE_THRESHOLD_PCT:
        candidates.append(_oil_candidate(day, oil_change, current, previous))

    inflation_delta = _q4(_d(current.inflation_rate) - _d(previous.inflation_rate))
    if inflation_delta >= INFLATION_INCREASE_THRESHOLD:
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type="inflation_spike",
            title="Inflation Spike Hits Wallets",
            description="Prices jumped enough today to make basic costs and debt pressure feel tighter.",
            severity_score=Decimal("600") + inflation_delta * Decimal("200"),
            payload=_candidate_payload(
                affected_systems=["Food", "Housing", "Debt", "Daily spending"],
                what_changed_today=[_delta_text("Inflation moved", inflation_delta, "points.")],
                what_this_means=[
                    "Groceries and essentials may cost more.",
                    "Daily savings targets become harder to hit.",
                    "Debt pressure can feel heavier when cash flow tightens.",
                ],
                source={"kind": "macro_daily_state", "field": "inflation_rate"},
            ),
        ))

    unemployment_delta = _q4(_d(current.unemployment_rate) - _d(previous.unemployment_rate))
    if unemployment_delta >= UNEMPLOYMENT_INCREASE_THRESHOLD:
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type="job_market_shock",
            title="Job Market Shock",
            description="Unemployment rose sharply today, making work stability and advancement more fragile.",
            severity_score=Decimal("590") + unemployment_delta * Decimal("150"),
            payload=_candidate_payload(
                affected_systems=["Jobs", "Income", "Career progression"],
                what_changed_today=[_delta_text("Unemployment moved", unemployment_delta, "points.")],
                what_this_means=[
                    "Job openings may feel more competitive.",
                    "Missing work becomes more dangerous.",
                    "Training and reliability matter more.",
                ],
                source={"kind": "macro_daily_state", "field": "unemployment_rate"},
            ),
        ))

    confidence_drop = _q4(_d(previous.consumer_confidence) - _d(current.consumer_confidence))
    if confidence_drop >= CONSUMER_CONFIDENCE_DROP_THRESHOLD:
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type="confidence_crash",
            title="Confidence Drops Across the City",
            description="Consumer confidence fell hard today, weakening demand and making the city feel cautious.",
            severity_score=Decimal("580") + confidence_drop * Decimal("12"),
            payload=_candidate_payload(
                affected_systems=["Customer demand", "Small business", "Stocks"],
                what_changed_today=[f"Consumer confidence fell {float(confidence_drop):.2f} points."],
                what_this_means=[
                    "Customer demand may soften.",
                    "Business revenue can become less predictable.",
                    "Market sentiment may stay nervous.",
                ],
                source={"kind": "macro_daily_state", "field": "consumer_confidence"},
            ),
        ))

    supply_delta = _q4(_d(current.supply_chain_stress) - _d(previous.supply_chain_stress))
    if supply_delta >= SUPPLY_CHAIN_INCREASE_THRESHOLD:
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type="supply_chain_shock",
            title="Supply Chain Shock",
            description="Supply chain stress jumped today, putting pressure on inventory, food costs, and deliveries.",
            severity_score=Decimal("570") + supply_delta * Decimal("8"),
            payload=_candidate_payload(
                affected_systems=["Inventory", "Food costs", "Deliveries", "Small business"],
                what_changed_today=[_delta_text("Supply chain stress moved", supply_delta, "points.")],
                what_this_means=[
                    "Restocking may feel riskier.",
                    "Produce and protein costs may increase.",
                    "Low inventory can become more expensive to fix.",
                ],
                source={"kind": "macro_daily_state", "field": "supply_chain_stress"},
            ),
        ))
    return candidates


def _basket_candidates(db: Session, day: int) -> list[BlackSwanCandidate]:
    rows = (
        db.query(BasketDailyPrice)
        .filter(BasketDailyPrice.day == int(day))
        .order_by(BasketDailyPrice.daily_change_pct.desc())
        .all()
    )
    candidates: list[BlackSwanCandidate] = []
    for row in rows:
        change_pct = _percent_value(row.daily_change_pct)
        if change_pct < BASKET_MOVE_THRESHOLD_PCT:
            continue
        raw_change = _d(row.daily_change_pct)
        label = str(getattr(row.basket_type, "value", row.basket_type) or "basket").replace("_", " ")
        direction = "rose" if raw_change >= 0 else "fell"
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type="basket_price_shock",
            title=f"{label.title()} Basket Shock",
            description=f"{label.title()} prices {direction} sharply today, changing the pressure on daily spending.",
            severity_score=Decimal("560") + change_pct * Decimal("10"),
            payload=_candidate_payload(
                affected_systems=["Daily spending", "Food", "Budget pressure"],
                what_changed_today=[f"{label.title()} basket moved {float(raw_change):+.2f}% today."],
                what_this_means=[
                    "Daily food planning matters more.",
                    "Cash buffers can shrink faster.",
                    "Business input costs may feel tighter.",
                ],
                source={"kind": "basket_daily_price", "basket_type": label},
            ),
        ))
    return candidates


def _stock_candidates(db: Session, day: int) -> list[BlackSwanCandidate]:
    rows = (
        db.query(StockDailyPrice)
        .filter(StockDailyPrice.day == int(day))
        .order_by(StockDailyPrice.daily_change_pct.desc())
        .all()
    )
    candidates: list[BlackSwanCandidate] = []
    for row in rows:
        change_pct = _percent_value(row.daily_change_pct)
        if change_pct < STOCK_MOVE_THRESHOLD_PCT:
            continue
        raw_change = _d(row.daily_change_pct)
        sector = str(row.sector or row.ticker or "market").replace("_", " ")
        direction = "jumped" if raw_change >= 0 else "dropped"
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type="stock_sector_shock",
            title=f"{sector.title()} Sector Shock",
            description=f"The {sector} sector {direction} sharply today, changing portfolio risk.",
            severity_score=Decimal("550") + change_pct * Decimal("8"),
            payload=_candidate_payload(
                affected_systems=["Stocks", "Net worth", "Portfolio risk"],
                what_changed_today=[f"{row.ticker} moved {float(raw_change):+.2f}% today."],
                what_this_means=[
                    "Portfolio value may swing harder.",
                    "Cash reserves can matter more than chasing volatility.",
                    "Diversification risk becomes more visible.",
                ],
                source={"kind": "stock_daily_price", "ticker": str(row.ticker or ""), "sector": sector},
            ),
        ))
    return candidates


def _impact_tags_include_high(raw: object) -> bool:
    parsed = _json_loads(raw)
    for entry in _json_list(parsed):
        if not isinstance(entry, dict):
            continue
        impact_level = str(
            entry.get("impact_level")
            or entry.get("level")
            or entry.get("severity")
            or ""
        ).strip().lower()
        if impact_level == "high":
            return True
    return False


def _event_candidates(db: Session, day: int) -> list[BlackSwanCandidate]:
    rows = (
        db.query(DailyEconomyEvent)
        .filter(DailyEconomyEvent.day == int(day))
        .order_by(DailyEconomyEvent.severity.desc(), DailyEconomyEvent.created_at.desc())
        .all()
    )
    candidates: list[BlackSwanCandidate] = []
    for row in rows:
        severity = _d(row.severity)
        magnitude = _d(getattr(row, "magnitude", 0))
        if (
            severity < HIGH_EVENT_SEVERITY_THRESHOLD
            and magnitude < HIGH_EVENT_MAGNITUDE_THRESHOLD
            and not _impact_tags_include_high(row.impact_tags_json)
        ):
            continue
        affected = []
        sectors = getattr(row, "affected_sectors", None)
        if isinstance(sectors, list):
            affected = [str(item).replace("_", " ").title() for item in sectors if str(item or "").strip()]
        if not affected:
            affected = [str(row.event_category or "Economy").replace("_", " ").title()]
        candidates.append(BlackSwanCandidate(
            day=day,
            event_type=str(row.event_category or "economy_event")[:60],
            title=str(row.headline or "Major Economy Shock"),
            description=str(row.summary or "A major economy event moved through the city today."),
            severity_score=Decimal("700") + severity * Decimal("100") + magnitude * Decimal("100"),
            source_event_id=row.id,
            payload=_candidate_payload(
                affected_systems=affected,
                what_changed_today=[str(row.summary or row.headline or "A high-impact economy event was recorded.")],
                what_this_means=[
                    "Review today's costs before committing time.",
                    "Watch cash, debt, and inventory decisions closely.",
                    "Use the daily brief before planning work.",
                ],
                source={
                    "kind": "daily_economy_event",
                    "event_key": str(row.event_key or ""),
                    "sentiment": str(row.sentiment or "neutral"),
                    "severity": float(severity),
                },
            ),
        ))
    return candidates


def find_black_swan_candidates(db: Session, day_number: int) -> list[BlackSwanCandidate]:
    """Return black swan candidates for a day without creating rows."""
    day = max(1, int(day_number))
    candidates: list[BlackSwanCandidate] = []
    if _table_available(db, MacroDailyState.__tablename__):
        candidates.extend(_macro_candidates(db, day))
    if _table_available(db, BasketDailyPrice.__tablename__):
        candidates.extend(_basket_candidates(db, day))
    if _table_available(db, StockDailyPrice.__tablename__):
        candidates.extend(_stock_candidates(db, day))
    if _table_available(db, DailyEconomyEvent.__tablename__):
        candidates.extend(_event_candidates(db, day))
    return sorted(
        candidates,
        key=lambda candidate: (candidate.severity_score, candidate.event_type, candidate.title),
        reverse=True,
    )


def _existing_same_day(db: Session, player: Player, day: int) -> PlayerBlackSwanEvent | None:
    return (
        db.query(PlayerBlackSwanEvent)
        .filter(
            PlayerBlackSwanEvent.player_id == player.id,
            PlayerBlackSwanEvent.day == int(day),
        )
        .order_by(PlayerBlackSwanEvent.created_at.desc())
        .first()
    )


def _cooldown_event(db: Session, player: Player, day: int) -> PlayerBlackSwanEvent | None:
    cooldown_start = max(1, int(day) - COOLDOWN_DAYS + 1)
    return (
        db.query(PlayerBlackSwanEvent)
        .filter(
            PlayerBlackSwanEvent.player_id == player.id,
            PlayerBlackSwanEvent.day >= cooldown_start,
            PlayerBlackSwanEvent.day < int(day),
        )
        .order_by(PlayerBlackSwanEvent.day.desc(), PlayerBlackSwanEvent.created_at.desc())
        .first()
    )


def evaluate_black_swan_for_player(
    db: Session,
    player_or_id: Player | str | UUID,
    *,
    day_number: int,
    commit: bool = False,
) -> PlayerBlackSwanEvent | None:
    """Create a black swan event for an active player when a rare candidate exists."""
    player = player_or_id if isinstance(player_or_id, Player) else _resolve_player(db, player_or_id)
    if normalize_run_status(player) != RUN_STATUS_ACTIVE:
        return None
    if not _table_available(db, PlayerBlackSwanEvent.__tablename__):
        return None

    day = max(1, int(day_number))
    existing = _existing_same_day(db, player, day)
    if existing is not None:
        return existing
    if _cooldown_event(db, player, day) is not None:
        return None

    candidates = find_black_swan_candidates(db, day)
    if not candidates:
        return None

    selected = candidates[0]
    row = PlayerBlackSwanEvent(
        player_id=player.id,
        day=selected.day,
        event_type=selected.event_type[:60],
        title=selected.title[:220],
        description=selected.description,
        severity_score=_q4(selected.severity_score),
        source_event_id=selected.source_event_id,
        payload_json=json.dumps(selected.payload, sort_keys=True),
    )
    db.add(row)
    db.flush()
    payload = dict(selected.payload)
    payload["push_payload"] = _push_payload(row.id)
    row.payload_json = json.dumps(payload, sort_keys=True)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def _serialize_datetime(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def serialize_black_swan_event(row: PlayerBlackSwanEvent) -> dict:
    payload = _json_loads(row.payload_json)
    if not isinstance(payload, dict):
        payload = {}
    if "push_payload" not in payload:
        payload["push_payload"] = _push_payload(row.id)
    return {
        "id": str(row.id),
        "player_id": str(row.player_id),
        "day": int(row.day),
        "event_type": str(row.event_type or "economy_event"),
        "title": str(row.title or "Major Event"),
        "description": str(row.description or "A major event moved through the city today."),
        "severity_score": float(_q4(_d(row.severity_score))),
        "source_event_id": str(row.source_event_id) if row.source_event_id else None,
        "payload": payload,
        "push_payload": payload.get("push_payload") or _push_payload(row.id),
        "seen_at": _serialize_datetime(row.seen_at),
        "created_at": _serialize_datetime(row.created_at),
    }


def get_pending_black_swan_event(db: Session, player_id: str | UUID) -> dict | None:
    player = _resolve_player(db, player_id)
    if normalize_run_status(player) != RUN_STATUS_ACTIVE:
        return None
    row = (
        db.query(PlayerBlackSwanEvent)
        .filter(
            PlayerBlackSwanEvent.player_id == player.id,
            PlayerBlackSwanEvent.seen_at.is_(None),
        )
        .order_by(PlayerBlackSwanEvent.day.desc(), PlayerBlackSwanEvent.created_at.desc())
        .first()
    )
    return serialize_black_swan_event(row) if row is not None else None


def mark_black_swan_seen(db: Session, player_id: str | UUID, event_id: str | UUID) -> dict:
    player = _resolve_player(db, player_id)
    try:
        eid = event_id if isinstance(event_id, UUID) else UUID(str(event_id))
    except ValueError as exc:
        raise BlackSwanNotFoundError("Black swan event not found.") from exc
    row = (
        db.query(PlayerBlackSwanEvent)
        .filter(
            PlayerBlackSwanEvent.id == eid,
            PlayerBlackSwanEvent.player_id == player.id,
        )
        .first()
    )
    if row is None:
        raise BlackSwanNotFoundError("Black swan event not found.")
    if row.seen_at is None:
        row.seen_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return serialize_black_swan_event(row)
