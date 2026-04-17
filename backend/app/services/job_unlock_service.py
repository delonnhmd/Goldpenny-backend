"""Shared job board unlock rules for map-first progression."""

from __future__ import annotations

from typing import Any

from app.engine.career_config import CAREER_CONFIG
from app.services.job_key_service import normalize_main_job_key


def _job_label(job_key: str) -> str:
    cfg = CAREER_CONFIG.get(job_key)
    if cfg is not None:
        return str(cfg.display_name or job_key.replace("_", " ").title())
    return job_key.replace("_", " ").title()


JOB_UNLOCK_RULES: dict[str, dict[str, Any]] = {
    "retail": {
        "level_requirement": 1,
        "experience_requirement_shifts": 0,
        "prerequisite_job_keys": [],
        "path_hint": "Starter survival lane.",
    },
    "delivery": {
        "level_requirement": 1,
        "experience_requirement_shifts": 0,
        "prerequisite_job_keys": [],
        "path_hint": "Starter survival lane.",
    },
    "cleaner": {
        "level_requirement": 1,
        "experience_requirement_shifts": 0,
        "prerequisite_job_keys": [],
        "path_hint": "Starter survival lane.",
    },
    "warehouse_operator": {
        "level_requirement": 2,
        "experience_requirement_shifts": 3,
        "prerequisite_job_keys": ["delivery", "retail", "cleaner"],
        "path_hint": "Food Truck Crew / Fruit Stall Clerk / Labor Helper -> Warehouse Manager",
    },
    "chef": {
        "level_requirement": 2,
        "experience_requirement_shifts": 2,
        "prerequisite_job_keys": ["delivery", "retail"],
        "path_hint": "Food Truck Crew / Fruit Stall Clerk -> Chef",
    },
    "auto_mechanic": {
        "level_requirement": 2,
        "experience_requirement_shifts": 4,
        "prerequisite_job_keys": ["cleaner", "warehouse_operator"],
        "path_hint": "Labor Helper / Warehouse Manager -> Auto Mechanic",
    },
    "real_estate_agent": {
        "level_requirement": 3,
        "experience_requirement_shifts": 6,
        "prerequisite_job_keys": ["retail", "warehouse_operator"],
        "path_hint": "Fruit Stall Clerk / Warehouse Manager -> Real Estate Agent",
    },
    "banker": {
        "level_requirement": 3,
        "experience_requirement_shifts": 7,
        "prerequisite_job_keys": ["warehouse_operator"],
        "path_hint": "Warehouse Manager -> Banker",
    },
    "aircraft_mechanic": {
        "level_requirement": 4,
        "experience_requirement_shifts": 8,
        "prerequisite_job_keys": ["auto_mechanic", "warehouse_operator"],
        "path_hint": "Auto Mechanic / Warehouse Manager -> Aircraft Mechanic",
    },
}


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _has_progress_for_job(progression_by_job: dict[str, dict[str, Any]], job_key: str) -> bool:
    snapshot = progression_by_job.get(job_key) or {}
    return bool(
        _safe_int(snapshot.get("shifts_completed"), 0) > 0
        or _safe_int(snapshot.get("xp_total"), 0) > 0
        or _safe_int(snapshot.get("job_xp"), 0) > 0
    )


def overall_player_level(*, player: Any, progression_by_job: dict[str, dict[str, Any]] | None = None) -> int:
    snapshots = progression_by_job or {}
    snapshot_level = max(
        (_safe_int((entry or {}).get("job_level"), 1) for entry in snapshots.values()),
        default=1,
    )
    player_level = _safe_int(getattr(player, "skill_level", 1), 1)
    return max(1, player_level, snapshot_level)


def total_completed_shifts(progression_by_job: dict[str, dict[str, Any]] | None = None) -> int:
    snapshots = progression_by_job or {}
    return max(
        0,
        sum(_safe_int((entry or {}).get("shifts_completed"), 0) for entry in snapshots.values()),
    )


def evaluate_job_unlock(
    job_key: str | None,
    *,
    player: Any,
    progression_by_job: dict[str, dict[str, Any]] | None = None,
    certification_completed: bool = True,
    certification_name: str | None = None,
) -> dict[str, Any]:
    normalized_job_key = normalize_main_job_key(job_key, allow_aliases=True) or str(job_key or "").strip().lower()
    rule = JOB_UNLOCK_RULES.get(normalized_job_key) or {
        "level_requirement": 1,
        "experience_requirement_shifts": 0,
        "prerequisite_job_keys": [],
        "path_hint": "",
    }
    snapshots = progression_by_job or {}
    required_level = max(1, _safe_int(rule.get("level_requirement"), 1))
    required_shifts = max(0, _safe_int(rule.get("experience_requirement_shifts"), 0))
    prerequisite_job_keys = [
        normalize_main_job_key(entry, allow_aliases=True) or str(entry or "").strip().lower()
        for entry in list(rule.get("prerequisite_job_keys") or [])
        if str(entry or "").strip()
    ]
    prerequisite_job_labels = [_job_label(entry) for entry in prerequisite_job_keys]
    current_level = overall_player_level(player=player, progression_by_job=snapshots)
    current_total_shifts = total_completed_shifts(snapshots)
    prerequisite_met = not prerequisite_job_keys or any(
        _has_progress_for_job(snapshots, entry) for entry in prerequisite_job_keys
    )
    level_met = current_level >= required_level
    experience_met = current_total_shifts >= required_shifts
    certification_met = bool(certification_completed)

    missing_parts: list[str] = []
    if not prerequisite_met and prerequisite_job_labels:
        missing_parts.append(f"Work one of: {', '.join(prerequisite_job_labels)}")
    if not level_met:
        missing_parts.append(f"Reach worker level {required_level}")
    if not experience_met:
        shift_label = "shift" if required_shifts == 1 else "shifts"
        missing_parts.append(f"Complete {required_shifts} total {shift_label}")
    if not certification_met and certification_name:
        missing_parts.append(f"Finish {certification_name}")

    return {
        "job_key": normalized_job_key,
        "level_requirement": required_level,
        "experience_requirement_shifts": required_shifts,
        "prerequisite_job_keys": prerequisite_job_keys,
        "prerequisite_job_labels": prerequisite_job_labels,
        "path_hint": str(rule.get("path_hint") or ""),
        "current_worker_level": current_level,
        "current_total_shifts": current_total_shifts,
        "prerequisite_met": prerequisite_met,
        "level_met": level_met,
        "experience_met": experience_met,
        "certification_met": certification_met,
        "unlocked": bool(prerequisite_met and level_met and experience_met and certification_met),
        "missing_parts": missing_parts,
    }
