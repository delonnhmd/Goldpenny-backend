"""Step 19 / 19.5: Event engine — deterministic daily event selection, macro impact,
and multi-day event chain support.

Public surface:
    run_daily_event_engine(db, day)        – main entry: select + apply + persist
    select_daily_event(db, day)            – pick event template for a day (chain-aware)
    apply_event_impacts_to_macro(db, day, template, chain_intensity)
    get_event_history(db, limit)           – recent events
    get_event_snapshot(db, day)            – single-day event detail
    force_daily_event(db, day, event_key)  – admin/debug override
    get_or_create_daily_event(db, day)     – idempotent wrapper
    get_active_chains(db, day)             – return active chain summaries
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.engine.event_catalog import (
    EVENT_CATALOG,
    EVENT_CATALOG_BY_KEY,
    EventTemplate,
    NEGATIVE_KEYS,
    POSITIVE_KEYS,
)
from app.models.daily_economy_event import DailyEconomyEvent
from app.models.daily_economy_event_log import DailyEconomyEventLog
from app.models.macro_daily_state import MacroDailyState

# ── Precision helpers ─────────────────────────────────────────────────────────

Q4 = Decimal("0.0001")


def _d(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


# ── Bounded delta caps (per-day max change) ──────────────────────────────────

_CAPS: dict[str, Decimal] = {
    "inflation_rate": Decimal("0.3000"),
    "interest_rate": Decimal("0.1500"),
    "unemployment_rate": Decimal("0.5000"),
    "oil_index": Decimal("6.0000"),        # ±6% of index value → absolute
    "consumer_confidence": Decimal("3.0000"),
    "supply_chain_stress": Decimal("0.2500"),
}


def _clamp(value: Decimal, cap: Decimal) -> Decimal:
    if value > cap:
        return cap
    if value < -cap:
        return -cap
    return value


# ── Floor / ceiling for macro fields ─────────────────────────────────────────

_FLOORS: dict[str, Decimal] = {
    "inflation_rate": Decimal("0.0000"),
    "interest_rate": Decimal("0.5000"),
    "unemployment_rate": Decimal("1.0000"),
    "oil_index": Decimal("30.0000"),
    "consumer_confidence": Decimal("10.0000"),
    "supply_chain_stress": Decimal("0.0000"),
}

_CEILINGS: dict[str, Decimal] = {
    "inflation_rate": Decimal("15.0000"),
    "interest_rate": Decimal("20.0000"),
    "unemployment_rate": Decimal("25.0000"),
    "oil_index": Decimal("250.0000"),
    "consumer_confidence": Decimal("100.0000"),
    "supply_chain_stress": Decimal("3.0000"),
}


# ── Deterministic helpers ─────────────────────────────────────────────────────

def _deterministic_ratio(seed: str) -> Decimal:
    """SHA-256 → [0, 1) deterministic decimal, matching business_service pattern."""
    digest = sha256(seed.encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return Decimal(n) / Decimal((16 ** 16) - 1)


def _deterministic_int(seed: str, upper: int) -> int:
    """Return deterministic integer in [0, upper)."""
    if upper <= 0:
        return 0
    ratio = _deterministic_ratio(seed)
    result = int((ratio * Decimal(str(upper))).to_integral_value())
    if result >= upper:
        result = upper - 1
    return result


# ── Chain stage constants ─────────────────────────────────────────────────────

CHAIN_STAGES = ("start", "mid", "escalation", "peak", "recovery", "end")


# ── Chain helpers ─────────────────────────────────────────────────────────────

def _get_previous_day_event(db: Session, day: int) -> DailyEconomyEvent | None:
    """Fetch the event row for (day - 1)."""
    if day <= 1:
        return None
    return (
        db.query(DailyEconomyEvent)
        .filter(DailyEconomyEvent.day == day - 1)
        .first()
    )


def _evaluate_chain_continuation(day: int, prev_event: DailyEconomyEvent) -> bool:
    """Deterministically decide whether a chain continues from prev_event."""
    if prev_event.chain_id is None:
        return False
    if prev_event.chain_stage in ("recovery", "end"):
        return False
    prob = float(prev_event.continuation_probability or 0)
    if prob <= 0:
        return False
    # Respect max_chain_length via chain_length_expected
    pos = int(prev_event.chain_position or 0)
    max_len = int(prev_event.chain_length_expected or 4)
    if pos >= max_len:
        return False
    ratio = float(_deterministic_ratio(f"chain:continue:{day}:{prev_event.chain_id}"))
    return ratio < prob


def _compute_chain_stage(position: int, max_length: int) -> str:
    """Determine chain stage from position within chain."""
    if position == 0:
        return "start"
    # Last position → peak (sets up recovery next)
    if position >= max_length - 1:
        return "peak"
    # Middle positions scale toward escalation
    frac = position / max(max_length - 1, 1)
    if frac >= 0.6:
        return "escalation"
    return "mid"


def _compute_decay_factor(position: int, decay_per_day: float) -> Decimal:
    """Compute cumulative decay: (1 - decay_per_day)^position, floored at 0.3."""
    if position <= 0:
        return Decimal("1.0000")
    factor = (1.0 - decay_per_day) ** position
    return _q4(max(Decimal(str(factor)), Decimal("0.3000")))


def _select_chain_event(
    db: Session,
    day: int,
    prev_event: DailyEconomyEvent,
) -> tuple[EventTemplate, str]:
    """Pick the next event within a chain. Returns (template, stage).

    Logic:
    - Check escalation conditions based on chain stage
    - Otherwise pick from next_possible_events
    - If nothing valid, pick first available recovery event → triggers recovery stage
    """
    prev_template = EVENT_CATALOG_BY_KEY.get(prev_event.event_key)
    if prev_template is None:
        return EVENT_CATALOG_BY_KEY["mixed_signals"], "end"

    pos = int(prev_event.chain_position or 0) + 1
    max_len = prev_template.max_chain_length

    stage = _compute_chain_stage(pos, max_len)

    # At peak → trigger recovery
    if stage == "peak" and prev_template.recovery_events:
        for rk in prev_template.recovery_events:
            if rk in EVENT_CATALOG_BY_KEY:
                macro = _get_macro(db, day)
                tmpl = EVENT_CATALOG_BY_KEY[rk]
                if macro is None or _check_preconditions(tmpl, macro):
                    return tmpl, "recovery"
        # No valid recovery — end chain
        return prev_template, "end"

    # Escalation check: at escalation stage, try escalation events first
    if stage == "escalation" and prev_template.escalation_events:
        esc_seed = f"chain:escalate:{day}:{prev_event.chain_id}"
        ratio = float(_deterministic_ratio(esc_seed))
        esc_prob = prev_template.severity_escalation_factor - 1.0  # e.g., 1.15 → 0.15
        if ratio < esc_prob:
            for ek in prev_template.escalation_events:
                if ek in EVENT_CATALOG_BY_KEY:
                    macro = _get_macro(db, day)
                    tmpl = EVENT_CATALOG_BY_KEY[ek]
                    if macro is None or _check_preconditions(tmpl, macro):
                        return tmpl, "escalation"

    # Normal continuation: pick from next_possible_events
    next_pool = [
        EVENT_CATALOG_BY_KEY[k]
        for k in prev_template.next_possible_events
        if k in EVENT_CATALOG_BY_KEY
    ]
    if next_pool:
        macro = _get_macro(db, day)
        valid = [t for t in next_pool if macro is None or _check_preconditions(t, macro)]
        if valid:
            idx = _deterministic_int(f"chain:next:{day}:{prev_event.chain_id}", len(valid))
            return valid[idx], stage

    # Fallback: repeat current event with decay (same template continues)
    return prev_template, stage


# ── Macro state helpers ───────────────────────────────────────────────────────

def _get_macro(db: Session, day: int) -> MacroDailyState | None:
    return (
        db.query(MacroDailyState)
        .filter(MacroDailyState.day <= day)
        .order_by(MacroDailyState.day.desc())
        .first()
    )


def _macro_snapshot(macro: MacroDailyState) -> dict[str, float]:
    return {
        "inflation_rate": float(_d(macro.inflation_rate)),
        "interest_rate": float(_d(macro.interest_rate)),
        "unemployment_rate": float(_d(macro.unemployment_rate)),
        "oil_index": float(_d(macro.oil_index)),
        "consumer_confidence": float(_d(macro.consumer_confidence)),
        "supply_chain_stress": float(_d(macro.supply_chain_stress)),
    }


# ── Precondition check ───────────────────────────────────────────────────────

def _check_preconditions(template: EventTemplate, macro: MacroDailyState) -> bool:
    """Return True if macro state satisfies the template's preconditions."""
    for key, threshold in template.preconditions.items():
        field_name = key.rsplit("_", 1)[0]  # e.g. "oil_index_min" → "oil_index"
        suffix = key.rsplit("_", 1)[-1]     # "min" or "max"
        current = float(_d(getattr(macro, field_name, 0)))
        if suffix == "min" and current < threshold:
            return False
        if suffix == "max" and current > threshold:
            return False
    return True


# ── Anti-repetition & recovery balancing ──────────────────────────────────────

def _recent_event_keys(db: Session, day: int, lookback: int = 5) -> list[str]:
    """Return event_keys for the last `lookback` days (most recent first)."""
    rows = (
        db.query(DailyEconomyEvent.event_key)
        .filter(DailyEconomyEvent.day < day)
        .order_by(DailyEconomyEvent.day.desc())
        .limit(lookback)
        .all()
    )
    return [r[0] for r in rows]


def _negative_streak(recent_keys: list[str]) -> int:
    """Count consecutive negative-sentiment events from most recent."""
    streak = 0
    for key in recent_keys:
        if key in NEGATIVE_KEYS:
            streak += 1
        else:
            break
    return streak


# ── Core selection ────────────────────────────────────────────────────────────

def select_daily_event(
    db: Session, day: int,
) -> tuple[EventTemplate, dict[str, Any]]:
    """Pick event template for `day` — chain-aware, deterministic, anti-repeat, recovery-biased.

    Returns (template, chain_info) where chain_info contains chain state metadata.
    chain_info keys: chain_id, chain_position, chain_stage, chain_length_expected,
                     parent_event_key, continuation_probability, decay_factor.
    For non-chain events chain_info values are defaults.
    """
    macro = _get_macro(db, day)
    if macro is None:
        return EVENT_CATALOG_BY_KEY["mixed_signals"], _empty_chain_info()

    # ── Step 19.5: Check for active chain continuation ────────────────────
    prev_event = _get_previous_day_event(db, day)
    if prev_event is not None and _evaluate_chain_continuation(day, prev_event):
        template, stage = _select_chain_event(db, day, prev_event)
        prev_template = EVENT_CATALOG_BY_KEY.get(prev_event.event_key)
        pos = int(prev_event.chain_position or 0) + 1
        decay = _compute_decay_factor(pos, prev_template.decay_per_day if prev_template else 0.15)
        # Reduce continuation probability for next day
        base_prob = float(prev_event.continuation_probability or 0)
        next_prob = max(base_prob * 0.85, 0.10) if stage not in ("recovery", "end") else 0.0
        chain_info = {
            "chain_id": prev_event.chain_id,
            "chain_position": pos,
            "chain_stage": stage,
            "chain_length_expected": int(prev_event.chain_length_expected or 4),
            "parent_event_key": prev_event.event_key,
            "continuation_probability": round(next_prob, 4),
            "decay_factor": float(decay),
        }
        return template, chain_info

    # ── Standard Step 19 selection (may start a new chain) ────────────────
    recent = _recent_event_keys(db, day, lookback=5)
    neg_streak = _negative_streak(recent)

    last_key = recent[0] if recent else None
    eligible: list[EventTemplate] = []
    for t in EVENT_CATALOG:
        if t.event_key == last_key:
            continue
        if not _check_preconditions(t, macro):
            continue
        eligible.append(t)

    if not eligible:
        eligible = [t for t in EVENT_CATALOG if t.event_key != last_key]
    if not eligible:
        eligible = list(EVENT_CATALOG)

    # Recovery bias: after 2+ consecutive negatives, strongly prefer positive.
    if neg_streak >= 2:
        recovery_pool = [t for t in eligible if t.sentiment == "positive"]
        if recovery_pool:
            idx = _deterministic_int(f"event:recovery:{day}", len(recovery_pool))
            template = recovery_pool[idx]
            return template, _new_chain_info(template, day)

    # Weighted deterministic selection.
    total_weight = sum(t.severity_weight for t in eligible)
    target = float(_deterministic_ratio(f"event:select:{day}")) * total_weight
    cumulative = 0.0
    selected = eligible[-1]
    for t in eligible:
        cumulative += t.severity_weight
        if cumulative >= target:
            selected = t
            break

    return selected, _new_chain_info(selected, day)


def _empty_chain_info() -> dict[str, Any]:
    """Default chain info for non-chain events (no chain)."""
    return {
        "chain_id": None,
        "chain_position": 0,
        "chain_stage": None,
        "chain_length_expected": None,
        "parent_event_key": None,
        "continuation_probability": 0.0,
        "decay_factor": 1.0,
    }


def _new_chain_info(template: EventTemplate, day: int) -> dict[str, Any]:
    """Generate chain info for a newly selected event (start of chain or standalone)."""
    if not template.can_chain:
        return _empty_chain_info()
    # New chain starts
    chain_id = sha256(f"chain:start:{day}:{template.event_key}".encode()).hexdigest()[:20]
    return {
        "chain_id": chain_id,
        "chain_position": 0,
        "chain_stage": "start",
        "chain_length_expected": template.max_chain_length,
        "parent_event_key": None,
        "continuation_probability": round(template.base_continuation_probability, 4),
        "decay_factor": 1.0,
    }


def build_event_headline(template: EventTemplate, _day: int) -> str:
    """Resolve headline from template (currently static, supports future templating)."""
    return template.headline_template


# ── Impact application ────────────────────────────────────────────────────────

def apply_event_impacts_to_macro(
    db: Session,
    day: int,
    template: EventTemplate,
    *,
    chain_intensity: float = 1.0,
) -> dict[str, Any]:
    """Apply bounded event impacts to macro state for `day`.

    chain_intensity (0.3–1.0) scales raw deltas for chain decay.
    Returns a dict with pre/post cap deltas and resulting macro snapshot.
    Does NOT commit — caller is responsible.
    """
    macro = _get_macro(db, day)
    if macro is None:
        return {"applied": False, "reason": "no_macro_state"}

    intensity = max(0.3, min(1.0, chain_intensity))
    snapshot_before = _macro_snapshot(macro)

    pre_cap_deltas: dict[str, float] = {}
    post_cap_deltas: dict[str, float] = {}

    for field_name, raw_magnitude in template.impact_tags.items():
        if not hasattr(macro, field_name):
            continue
        raw_delta = _q4(Decimal(str(raw_magnitude)) * Decimal(str(intensity)))
        pre_cap_deltas[field_name] = float(raw_delta)

        cap = _CAPS.get(field_name, Decimal("1.0000"))
        capped = _clamp(raw_delta, cap)
        post_cap_deltas[field_name] = float(capped)

        current = _d(getattr(macro, field_name))
        new_val = _q4(current + capped)

        # Apply floor / ceiling.
        floor = _FLOORS.get(field_name, Decimal("-9999"))
        ceiling = _CEILINGS.get(field_name, Decimal("9999"))
        if new_val < floor:
            new_val = floor
        if new_val > ceiling:
            new_val = ceiling

        setattr(macro, field_name, new_val)

    # Stamp headline on macro row.
    macro.event_headline = template.headline_template[:200]
    macro.event_summary = template.summary_template

    db.flush()

    snapshot_after = _macro_snapshot(macro)

    return {
        "applied": True,
        "pre_cap_deltas": pre_cap_deltas,
        "post_cap_deltas": post_cap_deltas,
        "macro_before": snapshot_before,
        "macro_after": snapshot_after,
    }


# ── Persistence helpers ───────────────────────────────────────────────────────

def _persist_event(
    db: Session,
    day: int,
    template: EventTemplate,
    impact_result: dict,
    source_type: str = "generated",
    chain_info: dict[str, Any] | None = None,
) -> DailyEconomyEvent:
    tags = [
        {"tag": k, "direction": "up" if v > 0 else ("down" if v < 0 else "flat"), "magnitude": abs(v)}
        for k, v in impact_result.get("post_cap_deltas", {}).items()
    ]
    ci = chain_info or _empty_chain_info()
    row = DailyEconomyEvent(
        day=day,
        event_key=template.event_key,
        headline=template.headline_template[:300],
        summary=template.summary_template,
        event_category=template.category,
        sentiment=template.sentiment,
        severity=_q4(Decimal(str(template.severity_weight))),
        impact_tags_json=json.dumps(tags),
        source_type=source_type,
        debug_json=json.dumps({
            "severity_weight": template.severity_weight,
            "preconditions": template.preconditions,
        }),
        # Step 19.5 chain fields
        chain_id=ci.get("chain_id"),
        chain_position=ci.get("chain_position", 0),
        chain_length_expected=ci.get("chain_length_expected"),
        chain_stage=ci.get("chain_stage"),
        parent_event_key=ci.get("parent_event_key"),
        continuation_probability=Decimal(str(ci.get("continuation_probability", 0))),
        decay_factor=Decimal(str(ci.get("decay_factor", 1.0))),
        chain_debug_json=json.dumps(ci) if ci.get("chain_id") else None,
    )
    db.add(row)
    db.flush()
    return row


def _persist_event_log(
    db: Session,
    day: int,
    event_key: str,
    impact_result: dict,
) -> DailyEconomyEventLog:
    row = DailyEconomyEventLog(
        day=day,
        event_key=event_key,
        pre_cap_deltas_json=json.dumps(impact_result.get("pre_cap_deltas", {})),
        post_cap_deltas_json=json.dumps(impact_result.get("post_cap_deltas", {})),
        macro_before_json=json.dumps(impact_result.get("macro_before", {})),
        macro_after_json=json.dumps(impact_result.get("macro_after", {})),
    )
    db.add(row)
    db.flush()
    return row


# ── Public API ────────────────────────────────────────────────────────────────

def run_daily_event_engine(db: Session, day: int) -> dict:
    """Main entry: select event, apply bounded impacts, persist, return summary.

    Idempotent — if an event already exists for `day`, returns its data
    without re-applying impacts.
    """
    existing = db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == day).first()
    if existing is not None:
        return _serialize_event(existing, already_processed=True)

    template, chain_info = select_daily_event(db, day)
    chain_intensity = chain_info.get("decay_factor", 1.0)
    impact_result = apply_event_impacts_to_macro(db, day, template, chain_intensity=chain_intensity)
    event_row = _persist_event(db, day, template, impact_result, source_type="generated", chain_info=chain_info)
    _persist_event_log(db, day, template.event_key, impact_result)

    return _serialize_event(event_row, already_processed=False, impact_result=impact_result)


def get_or_create_daily_event(db: Session, day: int) -> dict:
    """Idempotent wrapper — alias for run_daily_event_engine."""
    return run_daily_event_engine(db, day)


def force_daily_event(db: Session, day: int, event_key: str) -> dict:
    """Admin/debug override: force a specific event for a day.

    If an event already exists for the day it is replaced.
    """
    template = EVENT_CATALOG_BY_KEY.get(event_key)
    if template is None:
        return {"error": f"Unknown event_key: {event_key}"}

    # Remove existing event row for the day (if any).
    existing = db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == day).first()
    if existing is not None:
        db.delete(existing)
        db.flush()

    chain_info = _new_chain_info(template, day)
    impact_result = apply_event_impacts_to_macro(db, day, template)
    event_row = _persist_event(db, day, template, impact_result, source_type="forced", chain_info=chain_info)
    _persist_event_log(db, day, template.event_key, impact_result)

    return _serialize_event(event_row, already_processed=False, impact_result=impact_result)


def get_event_history(db: Session, limit: int = 10) -> list[dict]:
    """Return recent events, most recent first."""
    rows = (
        db.query(DailyEconomyEvent)
        .order_by(DailyEconomyEvent.day.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [_serialize_event(r) for r in rows]


def get_event_snapshot(db: Session, day: int) -> dict | None:
    """Return event detail for a specific day, or None."""
    row = db.query(DailyEconomyEvent).filter(DailyEconomyEvent.day == day).first()
    if row is None:
        return None
    log = db.query(DailyEconomyEventLog).filter(DailyEconomyEventLog.day == day).first()
    result = _serialize_event(row)
    if log is not None:
        result["macro_before"] = _safe_json(log.macro_before_json)
        result["macro_after"] = _safe_json(log.macro_after_json)
        result["pre_cap_deltas"] = _safe_json(log.pre_cap_deltas_json)
        result["post_cap_deltas"] = _safe_json(log.post_cap_deltas_json)
    return result


def get_catalog() -> list[dict]:
    """Return the full static event catalog for client/debug display."""
    return [
        {
            "event_key": t.event_key,
            "headline": t.headline_template,
            "category": t.category,
            "sentiment": t.sentiment,
            "severity_weight": t.severity_weight,
            "impact_tags": t.impact_tags,
            "preconditions": t.preconditions,
            "can_chain": t.can_chain,
            "chain_group_key": t.chain_group_key or None,
        }
        for t in EVENT_CATALOG
    ]


def get_active_chains(db: Session, day: int) -> list[dict]:
    """Return summaries of chains that were active on the given day.

    An active chain is one where the event on `day` has a non-null chain_id
    and chain_stage not in ('end', 'recovery').
    """
    rows = (
        db.query(DailyEconomyEvent)
        .filter(
            DailyEconomyEvent.chain_id.isnot(None),
            DailyEconomyEvent.day <= day,
        )
        .order_by(DailyEconomyEvent.day.desc())
        .all()
    )
    seen_chains: dict[str, dict] = {}
    for r in rows:
        cid = r.chain_id
        if cid in seen_chains:
            continue
        seen_chains[cid] = {
            "chain_id": cid,
            "latest_day": int(r.day),
            "latest_event_key": r.event_key,
            "chain_position": int(r.chain_position or 0),
            "chain_stage": r.chain_stage,
            "chain_length_expected": int(r.chain_length_expected or 0),
            "decay_factor": float(r.decay_factor or 1),
            "continuation_probability": float(r.continuation_probability or 0),
            "is_active": r.chain_stage not in ("end", "recovery", None),
        }
    return [v for v in seen_chains.values() if v["is_active"]]


# ── Serialization ─────────────────────────────────────────────────────────────

def _safe_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _serialize_event(
    row: DailyEconomyEvent,
    *,
    already_processed: bool = False,
    impact_result: dict | None = None,
) -> dict:
    result: dict[str, Any] = {
        "id": str(row.id),
        "day": int(row.day),
        "event_key": row.event_key,
        "headline": row.headline,
        "summary": row.summary,
        "event_category": row.event_category,
        "sentiment": row.sentiment,
        "severity": float(_d(row.severity)),
        "impact_tags": _safe_json(row.impact_tags_json),
        "source_type": row.source_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "already_processed": already_processed,
        # Step 19.5 chain fields
        "chain_id": row.chain_id,
        "chain_position": int(row.chain_position or 0),
        "chain_stage": row.chain_stage,
        "chain_length_expected": int(row.chain_length_expected) if row.chain_length_expected is not None else None,
        "parent_event_key": row.parent_event_key,
        "is_chain_continuation": row.chain_id is not None and int(row.chain_position or 0) > 0,
        "continuation_probability": float(row.continuation_probability or 0),
        "decay_factor": float(row.decay_factor or 1),
    }
    if impact_result is not None:
        result["macro_before"] = impact_result.get("macro_before")
        result["macro_after"] = impact_result.get("macro_after")
        result["pre_cap_deltas"] = impact_result.get("pre_cap_deltas")
        result["post_cap_deltas"] = impact_result.get("post_cap_deltas")
    return result
