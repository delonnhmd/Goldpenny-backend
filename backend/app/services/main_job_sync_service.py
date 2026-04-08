"""Canonical main-job sync and recovery helpers.

This service keeps ``player.main_job`` as the authoritative main-job field
while safely repairing legacy split-brain states where career/employment
mirrors drifted away from that source of truth.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.engine.career_config import CAREER_CONFIG
from app.models.player import Player
from app.models.player_career import PlayerCareer
from app.models.player_employment_state import PlayerEmploymentState
from app.services.job_key_service import normalize_main_job_key

logger = logging.getLogger(__name__)

JOB_SYNC_STATUS_HEALTHY = "healthy"
JOB_SYNC_STATUS_AUTO_REPAIRED = "auto_repaired"
JOB_SYNC_STATUS_REPAIR_NEEDED = "repair_needed"
JOB_SYNC_STATUS_MISSING = "missing"


def _job_label(job_key: str | None) -> str | None:
    canonical = normalize_main_job_key(job_key, allow_aliases=True)
    if not canonical:
        return None
    cfg = CAREER_CONFIG.get(canonical)
    if cfg is not None and str(getattr(cfg, "display_name", "")).strip():
        return str(cfg.display_name)
    return canonical.replace("_", " ").title()


def _latest_career_state(db: Session, player_id: Any) -> PlayerCareer | None:
    try:
        return (
            db.query(PlayerCareer)
            .filter(PlayerCareer.player_id == player_id)
            .order_by(PlayerCareer.updated_at.desc(), PlayerCareer.created_at.desc())
            .first()
        )
    except (OperationalError, ProgrammingError):
        return None


def _latest_employment_state(db: Session, player_id: Any) -> PlayerEmploymentState | None:
    try:
        return (
            db.query(PlayerEmploymentState)
            .filter(PlayerEmploymentState.player_id == player_id)
            .order_by(PlayerEmploymentState.day.desc(), PlayerEmploymentState.created_at.desc())
            .first()
        )
    except (OperationalError, ProgrammingError):
        return None


def inspect_and_repair_main_job_sync(
    db: Session,
    *,
    player: Player,
    trigger: str,
    apply_repair: bool,
) -> dict[str, Any]:
    """Inspect main-job mirrors and optionally repair safe drift.

    ``player.main_job`` is the canonical field. Repairs are intentionally
    conservative:
    - fill blank mirrors from the authoritative field
    - repair blank ``player.main_job`` from career state only when every
      non-empty mirror agrees on a single job key
    - never guess when two non-empty mirrors disagree
    """

    latest_career = _latest_career_state(db, player.id)
    latest_employment = _latest_employment_state(db, player.id)

    player_job_before = normalize_main_job_key(getattr(player, "main_job", None), allow_aliases=True)
    career_job_before = normalize_main_job_key(
        getattr(latest_career, "current_job_key", None) if latest_career is not None else None,
        allow_aliases=True,
    )
    employment_job_before = normalize_main_job_key(
        getattr(latest_employment, "current_job_code", None) if latest_employment is not None else None,
        allow_aliases=True,
    )

    sync_status = JOB_SYNC_STATUS_HEALTHY
    repair_source: str | None = None
    repaired_fields: list[str] = []
    warning_message: str | None = None

    mirror_candidates = {value for value in [career_job_before, employment_job_before] if value}
    conflicting_jobs = {
        value for value in [player_job_before, career_job_before, employment_job_before] if value
    }
    has_conflict = len(conflicting_jobs) > 1

    if player_job_before:
        if latest_career is not None and not career_job_before and apply_repair:
            latest_career.current_job_key = player_job_before
            repaired_fields.append("career.current_job_key")
        if latest_employment is not None and not employment_job_before and apply_repair:
            latest_employment.current_job_code = player_job_before
            repaired_fields.append("employment.current_job_code")
        if has_conflict:
            sync_status = JOB_SYNC_STATUS_REPAIR_NEEDED
            warning_message = "Your job data is syncing. Please retry in a moment."
    elif career_job_before and len(mirror_candidates) == 1:
        if apply_repair:
            player.main_job = career_job_before
            repaired_fields.append("player.main_job")
            if latest_employment is not None and not employment_job_before:
                latest_employment.current_job_code = career_job_before
                repaired_fields.append("employment.current_job_code")
        sync_status = JOB_SYNC_STATUS_AUTO_REPAIRED if apply_repair else JOB_SYNC_STATUS_HEALTHY
        repair_source = "career.current_job_key"
    elif not player_job_before and len(mirror_candidates) > 1:
        sync_status = JOB_SYNC_STATUS_REPAIR_NEEDED
        warning_message = "Your job data is syncing. Please retry in a moment."
    else:
        sync_status = JOB_SYNC_STATUS_MISSING

    player_job_after = normalize_main_job_key(getattr(player, "main_job", None), allow_aliases=True)
    career_job_after = normalize_main_job_key(
        getattr(latest_career, "current_job_key", None) if latest_career is not None else None,
        allow_aliases=True,
    )
    employment_job_after = normalize_main_job_key(
        getattr(latest_employment, "current_job_code", None) if latest_employment is not None else None,
        allow_aliases=True,
    )

    authoritative_main_job_key = player_job_after
    if authoritative_main_job_key and repaired_fields:
        sync_status = JOB_SYNC_STATUS_AUTO_REPAIRED

    if repaired_fields:
        db.flush()
        logger.info(
            "main_job.sync_repaired",
            extra={
                "player_id": str(player.id),
                "trigger": trigger,
                "before_authoritative_main_job_key": player_job_before,
                "career_current_job_key": career_job_before,
                "employment_current_job_code": employment_job_before,
                "repair_source": repair_source,
                "repaired_fields": repaired_fields,
                "final_main_job_key": authoritative_main_job_key,
            },
        )
    elif sync_status == JOB_SYNC_STATUS_REPAIR_NEEDED:
        logger.warning(
            "main_job.sync_repair_needed",
            extra={
                "player_id": str(player.id),
                "trigger": trigger,
                "before_authoritative_main_job_key": player_job_before,
                "career_current_job_key": career_job_before,
                "employment_current_job_code": employment_job_before,
                "final_main_job_key": authoritative_main_job_key,
            },
        )
    else:
        logger.info(
            "main_job.sync_checked",
            extra={
                "player_id": str(player.id),
                "trigger": trigger,
                "before_authoritative_main_job_key": player_job_before,
                "career_current_job_key": career_job_before,
                "employment_current_job_code": employment_job_before,
                "final_main_job_key": authoritative_main_job_key,
                "sync_status": sync_status,
            },
        )

    return {
        "authoritative_main_job_key": authoritative_main_job_key or "",
        "current_job_label": _job_label(authoritative_main_job_key) or "",
        "sync_status": sync_status,
        "sync_warning_message": warning_message or "",
        "repair_source": repair_source or "",
        "repair_applied": bool(repaired_fields),
        "repaired_fields": list(repaired_fields),
        "job_sources": {
            "player.main_job": player_job_after or "",
            "career.current_job_key": career_job_after or "",
            "employment.current_job_code": employment_job_after or "",
        },
        "has_conflict": len({value for value in [player_job_after, career_job_after, employment_job_after] if value}) > 1,
    }
