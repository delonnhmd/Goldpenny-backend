"""Daily 04:00 UTC real-world event generation (Phase 3-B-1, task 4).

Three-tier fallback chain that always produces *some* event row for the
current game day, never crashes:

  1) RuleBasedEventGenerator (FRED-driven; today's market/macro signal)
  2) Yesterday's real-world-anchored row, copied with a "Quiet Day —" prefix
  3) Static event catalog via app.engine.event_service.run_daily_event_engine

Idempotency: at most one row per game day is enforced by the unique
constraint on DailyEconomyEvent.day. We additionally short-circuit so a
re-run doesn't even attempt generation when a row already exists.

The job is wrapped by a Celery beat task in app/jobs/realworld_tasks.py
and exposed as a manual override endpoint at POST /admin/realworld/regenerate.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.game_state import GameState
from app.services.realworld.cost_breaker import HARD_BREAKER_THRESHOLD, CostBreaker
from app.services.realworld.rule_generator import (
    RULE_TO_CATEGORY,
    RealWorldEvent,
    RuleBasedEventGenerator,
)

logger = logging.getLogger(__name__)


GenerationSource = Literal[
    "rule",
    "yesterday_fallback",
    "static_fallback",
    "skipped_idempotent",
    "skipped_static_exists",
    "error_no_gamestate",
    "error_static_failed",
]


_TONE_TO_DIRECTION = {"positive": "up", "neutral": "flat", "negative": "down"}
_SEVERITY_QUANT = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def run_daily_generation(
    target_date: date | None = None,
    *,
    db: Session | None = None,
    generator: RuleBasedEventGenerator | None = None,
) -> dict[str, Any]:
    """Run the daily generation chain. Safe to call multiple times.

    Returns a small log-friendly dict; never raises for expected failure
    modes (missing data, FRED outage, static-catalog crash). A bug in the
    rule generator or an unrelated DB error will surface normally.
    """
    started = perf_counter()
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    owns_session = db is None
    if db is None:
        db = SessionLocal()

    try:
        result = _run(db, target_date, generator)
        if result.get("source") in {"rule", "yesterday_fallback", "static_fallback"}:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()

    result["duration_ms"] = round((perf_counter() - started) * 1000, 2)
    result.setdefault("target_date", target_date.isoformat())
    logger.info(
        "realworld_generation source=%s target_date=%s event_id=%s duration_ms=%.2f",
        result.get("source"),
        result.get("target_date"),
        result.get("event_id"),
        result.get("duration_ms"),
    )
    return result


# ---------------------------------------------------------------------------
# Internals.
# ---------------------------------------------------------------------------


def _run(
    db: Session,
    target_date: date,
    generator: RuleBasedEventGenerator | None,
) -> dict[str, Any]:
    game_state = db.query(GameState).order_by(GameState.id.asc()).first()
    if game_state is None:
        logger.error("realworld_generation: no GameState row; cannot determine game day")
        return {"source": "error_no_gamestate", "event_id": None}
    day = int(game_state.current_day)

    existing = db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == day).first()
    if existing is not None:
        if existing.is_realworld_anchored:
            return {
                "source": "skipped_idempotent",
                "event_id": existing.event_key,
                "day": day,
            }
        # A static catalog row already claimed today's slot. Don't overwrite.
        return {
            "source": "skipped_static_exists",
            "event_id": existing.event_key,
            "day": day,
        }

    breaker = CostBreaker(db)
    if breaker.is_tripped():
        monthly_cost = breaker.monthly_cost_per_mau()
        reason = (
            "real-world generation skipped because cost breaker tripped: "
            f"monthly_cost_per_mau={monthly_cost:.4f} threshold={HARD_BREAKER_THRESHOLD:.2f}"
        )
        logger.error("realworld_generation: %s", reason)
        breaker.notify_operator(reason)
        return _run_static_fallback(db, day)

    # ── Tier 1: rule generator ──
    rule_event = _try_rule_generator(target_date, generator)
    if rule_event is not None:
        row = _persist_realworld(db, day, rule_event)
        breaker.record_generation_cost(row.event_key, 0.0)
        return {"source": "rule", "event_id": row.event_key, "day": day}

    # ── Tier 2: yesterday's real-world row ──
    yesterday_row = (
        db.query(DailyEconomyEvent)
        .filter(
            DailyEconomyEvent.day == day - 1,
            DailyEconomyEvent.is_realworld_anchored.is_(True),
        )
        .first()
    )
    if yesterday_row is not None:
        row = _persist_yesterday_quiet(db, day, target_date, yesterday_row)
        return {"source": "yesterday_fallback", "event_id": row.event_key, "day": day}

    # ── Tier 3: static catalog ──
    return _run_static_fallback(db, day)


def _run_static_fallback(db: Session, day: int) -> dict[str, Any]:
    try:
        # Imported lazily so the cron module doesn't pull engine internals at import time.
        from app.engine.event_service import run_daily_event_engine

        static_result = run_daily_event_engine(db, day)
        return {
            "source": "static_fallback",
            "event_id": static_result.get("event_key") or static_result.get("event_id"),
            "day": day,
        }
    except Exception as exc:  # noqa: BLE001 — last-ditch; log and keep brief renderable
        logger.critical(
            "realworld_generation: static catalog fallback FAILED for day=%d: %s",
            day,
            exc,
            exc_info=True,
        )
        return {"source": "error_static_failed", "event_id": None, "day": day}


def _try_rule_generator(
    target_date: date, generator: RuleBasedEventGenerator | None
) -> RealWorldEvent | None:
    try:
        gen = generator if generator is not None else RuleBasedEventGenerator()
    except Exception as exc:  # FRED_API_KEY missing, etc.
        logger.warning("realworld_generation: cannot construct generator: %s", exc)
        return None
    try:
        return gen.generate(target_date)
    except Exception as exc:  # noqa: BLE001 — defensive; spec says "return None rather than crash"
        logger.warning("realworld_generation: rule generator raised: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Persistence.
# ---------------------------------------------------------------------------


def _impact_tags_for(event: RealWorldEvent) -> list[dict[str, Any]]:
    direction = _TONE_TO_DIRECTION.get(event.tone, "flat")
    return [
        {"tag": sector, "direction": direction, "magnitude": event.magnitude}
        for sector in event.affected_sectors
    ]


def _category_for(event: RealWorldEvent) -> str:
    parts = event.event_id.split("-", 4)
    if len(parts) != 5 or parts[0] != "realworld":
        raise ValueError(f"Cannot derive rule slug from event_id={event.event_id!r}")
    rule_slug = parts[4]
    try:
        return RULE_TO_CATEGORY[rule_slug]
    except KeyError as exc:
        raise ValueError(f"Rule slug {rule_slug!r} has no event-category mapping") from exc


def _persist_realworld(db: Session, day: int, event: RealWorldEvent) -> DailyEconomyEvent:
    tags = _impact_tags_for(event)
    row = DailyEconomyEvent(
        day=day,
        event_key=event.event_id[:80],
        headline=event.event_name[:300],
        summary=event.narrative,
        event_category=_category_for(event)[:40],
        sentiment=event.tone,
        severity=Decimal(str(event.severity)).quantize(_SEVERITY_QUANT),
        impact_tags_json=json.dumps(tags),
        source_type="generated",
        # Phase 3-B-1 metadata.
        is_realworld_anchored=True,
        source_summary=event.source_summary,
        source_urls=list(event.source_urls),
        generated_at=event.generated_at,
        affected_sectors=list(event.affected_sectors),
        duration_days=event.duration_days,
        magnitude=event.magnitude,
    )
    db.add(row)
    db.flush()
    return row


def _persist_yesterday_quiet(
    db: Session,
    day: int,
    target_date: date,
    yesterday: DailyEconomyEvent,
) -> DailyEconomyEvent:
    headline = f"Quiet Day — {yesterday.headline}"[:300]
    summary = (
        "The world is quiet today; yesterday's pressure is still working through your city."
    )
    row = DailyEconomyEvent(
        day=day,
        event_key=f"realworld-{target_date.isoformat()}-quiet"[:80],
        headline=headline,
        summary=summary,
        event_category=yesterday.event_category,
        sentiment=yesterday.sentiment,
        severity=yesterday.severity,
        impact_tags_json=yesterday.impact_tags_json,
        source_type="generated",
        is_realworld_anchored=True,
        source_summary=yesterday.source_summary,
        source_urls=list(yesterday.source_urls or []),
        generated_at=datetime.now(timezone.utc),
        affected_sectors=list(yesterday.affected_sectors or []),
        duration_days=yesterday.duration_days,
        magnitude=yesterday.magnitude,
    )
    db.add(row)
    db.flush()
    return row
