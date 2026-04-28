"""Celery tasks for the Real-World Event Pipeline (Phase 3-B-1, task 4).

Beat schedule:
- ``daily_realworld_generation`` runs every day at 04:00 UTC.

To run beat alongside the existing worker:

    celery -A app.jobs.celery_worker beat --loglevel=info

The task delegates to :func:`run_daily_generation` and is intentionally
thin — orchestration, idempotency, and fallback live in the service layer.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.schedules import crontab

from app.jobs.celery_worker import celery_app
from app.services.realworld.daily_generation_job import run_daily_generation

logger = logging.getLogger(__name__)


@celery_app.task(name="app.jobs.realworld_tasks.daily_realworld_generation")
def daily_realworld_generation() -> dict[str, Any]:
    """Beat-scheduled wrapper around the realworld pipeline."""
    result = run_daily_generation()
    logger.info("daily_realworld_generation result=%s", result)
    return result


# Register the schedule on the shared celery_app. Celery beat picks this up
# when it starts; no action needed in main.py.
celery_app.conf.beat_schedule = {
    **(celery_app.conf.beat_schedule or {}),
    "realworld-daily-04utc": {
        "task": "app.jobs.realworld_tasks.daily_realworld_generation",
        "schedule": crontab(hour=4, minute=0),
    },
}
