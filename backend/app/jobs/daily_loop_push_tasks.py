"""Celery beat task for Phase 3-C Push Scheduling.

Runs every 5 minutes and dispatches the morning-brief and settlement
reminder notifications to active players whose game time falls inside
the appropriate window. The actual decision logic lives in
:mod:`app.services.daily_loop_notifications_service` so it can be
tested without a Celery worker.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.schedules import crontab

from app.jobs.celery_worker import celery_app
from app.services.daily_loop_notifications_service import run_daily_loop_notifications

logger = logging.getLogger(__name__)

DAILY_LOOP_PUSH_TASK_NAME = "app.jobs.daily_loop_push_tasks.send_due_daily_loop_notifications"


@celery_app.task(name=DAILY_LOOP_PUSH_TASK_NAME)
def send_due_daily_loop_notifications() -> dict[str, Any]:
    """Beat-scheduled wrapper around the daily-loop notification dispatcher."""
    summary = run_daily_loop_notifications()
    logger.info("send_due_daily_loop_notifications summary=%s", {
        k: v for k, v in summary.items() if k != "results"
    })
    return summary


celery_app.conf.beat_schedule = {
    **(celery_app.conf.beat_schedule or {}),
    "daily-loop-push-every-5min": {
        "task": DAILY_LOOP_PUSH_TASK_NAME,
        "schedule": crontab(minute="*/5"),
    },
}
