"""Guided sandbox mode for Days 1-5.

Returns a single, deterministic "next step" nudge per early-game day so new
players have direction without collapsing sandbox freedom. Days 6+ have no
nudge — the sandbox runs fully free.

Nudges are *guidance, not gates*: the player can ignore them. Completion
detection is intentionally loose and is expected to be refined later.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

GUIDED_SANDBOX_DAY_WINDOW = 5


@dataclass(frozen=True)
class GuidedNudge:
    key: str
    day_number: int
    title: str
    message: str
    target_node_key: str
    completion_hint: str


NUDGES_BY_DAY: dict[int, GuidedNudge] = {
    1: GuidedNudge(
        key="day1_first_work",
        day_number=1,
        title="Day 1 — Get your first shift",
        message="Travel to Work on the map and complete a full shift to earn your first XGP.",
        target_node_key="work",
        completion_hint="Finish one work shift today.",
    ),
    2: GuidedNudge(
        key="day2_meal_from_map",
        day_number=2,
        title="Day 2 — Eat from the map",
        message="Open the Grocery tile and buy a meal. Food stress drags everything down if you skip it.",
        target_node_key="grocery",
        completion_hint="Buy one meal from the Grocery tile.",
    ),
    3: GuidedNudge(
        key="day3_job_board",
        day_number=3,
        title="Day 3 — Scout the job board",
        message="Visit the Job Center tile and review which roles pay better, what's locked, and what needs certification.",
        target_node_key="job_center",
        completion_hint="Open the Job Center tile.",
    ),
    4: GuidedNudge(
        key="day4_business_listing",
        day_number=4,
        title="Day 4 — Inspect a business for sale",
        message="Open the Business tile and read one listing. You're not buying yet — you're calibrating what an asset costs.",
        target_node_key="business_spot",
        completion_hint="Open at least one business listing.",
    ),
    5: GuidedNudge(
        key="day5_save_for_asset",
        day_number=5,
        title="Day 5 — Save toward your first asset",
        message="Visit the Bank tile and start setting cash aside. First asset is how the sandbox actually opens up.",
        target_node_key="bank",
        completion_hint="Visit the Bank tile.",
    ),
}


def is_active(day_number: object) -> bool:
    try:
        day = int(day_number)
    except (TypeError, ValueError):
        return False
    return 1 <= day <= GUIDED_SANDBOX_DAY_WINDOW


def resolve_day_nudge(day_number: object) -> dict[str, Any] | None:
    """Return the nudge for a day, or None outside the 1-5 window."""
    try:
        day = int(day_number)
    except (TypeError, ValueError):
        return None

    nudge = NUDGES_BY_DAY.get(day)
    if nudge is None:
        return None

    payload = asdict(nudge)
    payload["days_remaining"] = max(0, GUIDED_SANDBOX_DAY_WINDOW - day)
    payload["window_size"] = GUIDED_SANDBOX_DAY_WINDOW
    payload["is_final_day"] = day == GUIDED_SANDBOX_DAY_WINDOW
    return payload


def list_all_nudges() -> list[dict[str, Any]]:
    return [
        {**asdict(nudge), "days_remaining": max(0, GUIDED_SANDBOX_DAY_WINDOW - nudge.day_number)}
        for nudge in NUDGES_BY_DAY.values()
    ]
