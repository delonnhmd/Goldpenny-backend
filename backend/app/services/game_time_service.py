"""Backend-owned game clock helpers.

Phase 3-C uses this module as the single server authority for timer metadata
that the client may count down locally after receipt.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

GAME_TIMEZONE = "America/Chicago"


def _as_game_time(value: datetime | None = None) -> datetime:
    tz = ZoneInfo(GAME_TIMEZONE)
    now = value or get_server_now()
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def get_server_now() -> datetime:
    return datetime.now(ZoneInfo(GAME_TIMEZONE))


def get_next_settlement_at(now: datetime | None = None) -> datetime:
    local_now = _as_game_time(now)
    tz = ZoneInfo(GAME_TIMEZONE)
    tomorrow = local_now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time(0, 0), tzinfo=tz)


def get_next_morning_brief_at(now: datetime | None = None) -> datetime:
    local_now = _as_game_time(now)
    tz = ZoneInfo(GAME_TIMEZONE)
    today_brief = datetime.combine(local_now.date(), time(7, 0), tzinfo=tz)
    if local_now < today_brief:
        return today_brief
    tomorrow = local_now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time(7, 0), tzinfo=tz)


def _seconds_until(target: datetime, now: datetime) -> int:
    elapsed = target.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    return max(0, int(elapsed.total_seconds()))


def get_game_time_payload(now: datetime | None = None) -> dict:
    local_now = _as_game_time(now)
    next_settlement = get_next_settlement_at(local_now)
    next_brief = get_next_morning_brief_at(local_now)

    return {
        "server_now": local_now.isoformat(),
        "timezone": GAME_TIMEZONE,
        # TODO(push): use next_settlement_at for settlement reminder scheduling.
        "next_settlement_at": next_settlement.isoformat(),
        # TODO(push): use next_morning_brief_at for daily brief notification scheduling.
        "next_morning_brief_at": next_brief.isoformat(),
        "seconds_until_settlement": _seconds_until(next_settlement, local_now),
        "seconds_until_morning_brief": _seconds_until(next_brief, local_now),
    }
