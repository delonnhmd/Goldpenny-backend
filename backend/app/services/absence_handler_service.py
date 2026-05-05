"""Phase 3-C Player Absence Handling.

Catches up players who were offline for one or more real-world days and
returns a friendly summary that the frontend renders inside an absence
modal.

Design constraints (from the phase brief):
- DO NOT change economy / business / map formulas.
- DO NOT auto-run work or business operations.
- DO NOT auto-buy inventory.
- Business inventory MAY decay (spoilage) while the player is away.
- Salary only pays through existing pay-period logic — not here.

The handler is intentionally self-contained: it applies a small,
fixed-rate vitals/cash penalty and a per-day inventory spoilage rate to
any active player_businesses. Existing dinner_survival / shift_state
catch-up modules continue to run their own deeper logic; this service
exists so the gameplay loop bundle can produce a single, player-facing
absence_summary that matches the spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.player_business import PlayerBusiness
from app.services.game_time_service import GAME_TIMEZONE, get_server_now


logger = logging.getLogger("goldpenny.absence")

# Per-day deltas. Kept small so a long absence doesn't instantly bankrupt
# the player; the spec's example (2 missed days → -6 health, +8 stress)
# matches these constants exactly.
HEALTH_LOSS_PER_DAY = 3
STRESS_GAIN_PER_DAY = 4

# Bills/debt pressure: required_daily_debt_payment_xgp accrues per missed
# day, applied as a cash deduction (only if the player actually owes a
# daily payment and has cash to spend). This does not change debt totals
# or credit score — those remain in the existing finance services.
BILLS_PRESSURE_FRACTION = Decimal("1.00")

# Business inventory spoilage rate per missed day. 10% per day on each
# stocked produce/essentials/protein bucket, compounded.
SPOIL_PCT_PER_DAY = Decimal("0.10")

# Hard cap on how many missed days we will retroactively process. A
# month-long break should not delete the player's account.
MAX_ABSENCE_DAYS = 7

ACTIVE_RUN_STATUS = "active"

EMPTY_SUMMARY: dict[str, Any] = {
    "missed_days": 0,
    "health_change": 0,
    "stress_change": 0,
    "cash_change": 0.0,
    "inventory_spoilage": 0.0,
    "warnings": [],
    "skipped_reason": None,
}


@dataclass
class _AbsenceResult:
    missed_days: int = 0
    health_change: int = 0
    stress_change: int = 0
    cash_change: Decimal = Decimal("0.00")
    inventory_spoilage: Decimal = Decimal("0.00")
    warnings: list[str] = field(default_factory=list)
    truncated_days: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "missed_days": int(self.missed_days),
            "truncated_days": int(self.truncated_days),
            "health_change": int(self.health_change),
            "stress_change": int(self.stress_change),
            "cash_change": float(self.cash_change.quantize(Decimal("0.01"))),
            "inventory_spoilage": float(self.inventory_spoilage.quantize(Decimal("0.0001"))),
            "warnings": list(self.warnings),
            "skipped_reason": None,
        }


def _to_chicago(value: datetime) -> datetime:
    tz = ZoneInfo(GAME_TIMEZONE)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _anchor_datetime(player: Player) -> datetime | None:
    """Pick the latest available "the player was here" timestamp."""
    candidates = [
        getattr(player, "last_settlement_at", None),
        getattr(player, "last_seen_at", None),
    ]
    candidates = [c for c in candidates if isinstance(c, datetime)]
    if not candidates:
        return None
    return max(_to_chicago(c) for c in candidates)


def _missed_full_days(anchor: datetime, server_now: datetime) -> int:
    """Full local game days strictly between anchor and server_now."""
    today = _to_chicago(server_now).date()
    last_day = _to_chicago(anchor).date()
    delta = (today - last_day).days
    # delta == 0: same day, no missed full day.
    # delta == 1: yesterday → today, 0 missed full days.
    # delta == 2: 1 missed full day, etc.
    return max(0, delta - 1)


def _apply_vitals(player: Player, missed_days: int, result: _AbsenceResult) -> None:
    health_loss = HEALTH_LOSS_PER_DAY * missed_days
    stress_gain = STRESS_GAIN_PER_DAY * missed_days

    new_health = max(0, int(getattr(player, "health", 100) or 0) - health_loss)
    new_stress = min(100, int(getattr(player, "stress", 0) or 0) + stress_gain)

    actual_health_loss = int(getattr(player, "health", 100) or 0) - new_health
    actual_stress_gain = new_stress - int(getattr(player, "stress", 0) or 0)

    player.health = new_health
    player.stress = new_stress

    result.health_change -= actual_health_loss
    result.stress_change += actual_stress_gain

    if actual_health_loss > 0:
        result.warnings.append(
            f"You missed {missed_days} day{'s' if missed_days != 1 else ''}. "
            "Your health dropped because you did not eat."
        )
    if actual_stress_gain > 0:
        result.warnings.append(
            "Stress climbed while you were away from the game."
        )


def _apply_bills_pressure(player: Player, missed_days: int, result: _AbsenceResult) -> None:
    daily_required = Decimal(str(getattr(player, "required_daily_debt_payment_xgp", 0) or 0))
    if daily_required <= 0:
        return

    pressure = (daily_required * BILLS_PRESSURE_FRACTION * Decimal(missed_days))
    available_cash = Decimal(str(getattr(player, "cash", 0) or 0))
    deduction = min(pressure, available_cash)
    if deduction <= 0:
        return

    player.cash = (available_cash - deduction).quantize(Decimal("0.01"))
    result.cash_change -= deduction
    result.warnings.append(
        "Debt payments came due while you were away."
    )


def _apply_business_spoilage(
    db: Session, player: Player, missed_days: int, result: _AbsenceResult
) -> None:
    businesses = (
        db.query(PlayerBusiness)
        .filter(PlayerBusiness.player_id == player.id, PlayerBusiness.is_active.is_(True))
        .all()
    )
    if not businesses:
        return

    survival = (Decimal("1.00") - SPOIL_PCT_PER_DAY) ** missed_days
    spoiled_any = False
    for biz in businesses:
        for field_name in (
            "inventory_produce_units",
            "inventory_essentials_units",
            "inventory_protein_units",
        ):
            current = Decimal(str(getattr(biz, field_name, 0) or 0))
            if current <= 0:
                continue
            remaining = (current * survival).quantize(Decimal("0.0001"))
            spoilage = (current - remaining).quantize(Decimal("0.0001"))
            if spoilage > 0:
                setattr(biz, field_name, remaining)
                result.inventory_spoilage += spoilage
                spoiled_any = True

    if spoiled_any:
        result.warnings.append(
            "Your business inventory spoiled while you were away."
        )


def run_absence_check(
    db: Session,
    player: Player,
    *,
    server_now: datetime | None = None,
    update_last_seen: bool = True,
) -> dict[str, Any]:
    """Detect missed days and apply absence penalties.

    Returns the absence_summary payload. Ended runs (bankrupt / retired)
    are skipped with a `skipped_reason` so the frontend can keep the
    modal closed without a special-case branch.
    """

    run_status = str(getattr(player, "run_status", ACTIVE_RUN_STATUS) or ACTIVE_RUN_STATUS)
    server_now = server_now or get_server_now()
    server_now_chi = _to_chicago(server_now)

    if run_status != ACTIVE_RUN_STATUS:
        # Still update last_seen_at so the next active session uses this
        # moment as the anchor — but never apply penalties to ended runs.
        if update_last_seen:
            player.last_seen_at = server_now_chi
        payload = dict(EMPTY_SUMMARY)
        payload["skipped_reason"] = run_status
        return payload

    anchor = _anchor_datetime(player)
    if anchor is None:
        # First observation — set the baseline; no penalty.
        if update_last_seen:
            player.last_seen_at = server_now_chi
        payload = dict(EMPTY_SUMMARY)
        payload["skipped_reason"] = "no_baseline"
        return payload

    missed = _missed_full_days(anchor, server_now_chi)
    if missed <= 0:
        if update_last_seen:
            player.last_seen_at = server_now_chi
        return dict(EMPTY_SUMMARY)

    truncated = max(0, missed - MAX_ABSENCE_DAYS)
    days_to_apply = min(missed, MAX_ABSENCE_DAYS)

    result = _AbsenceResult(missed_days=missed, truncated_days=truncated)

    _apply_vitals(player, days_to_apply, result)
    _apply_bills_pressure(player, days_to_apply, result)
    _apply_business_spoilage(db, player, days_to_apply, result)

    if truncated > 0:
        result.warnings.append(
            f"Only the most recent {MAX_ABSENCE_DAYS} days of absence were applied."
        )

    if update_last_seen:
        player.last_seen_at = server_now_chi

    db.flush()

    logger.info(
        "absence.run_absence_check applied",
        extra={
            "player_id": str(player.id),
            "missed_days": result.missed_days,
            "applied_days": days_to_apply,
            "health_change": result.health_change,
            "stress_change": result.stress_change,
            "cash_change": float(result.cash_change),
            "inventory_spoilage": float(result.inventory_spoilage),
        },
    )

    return result.to_payload()


def stamp_settlement_now(player: Player, *, server_now: datetime | None = None) -> None:
    """Anchor `last_settlement_at` after a successful settlement.

    Pure metadata update — no economy effect. Called from the daily
    settlement flow so future absence checks measure from the last real
    settlement rather than the last loop fetch.
    """
    now = _to_chicago(server_now or get_server_now())
    player.last_settlement_at = now
    player.last_seen_at = now
