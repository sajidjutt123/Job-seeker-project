"""Celery application and beat schedule.

Scheduling strategy (spec §8):
  * every 15 min — high-priority sources (priority <= 25)
  * every 30 min — normal sources (priority <= 60)
  * every 3 hours — everything else that is due
  * hourly       — expiration sweep
  * every 20 min — instant alerts;  daily/weekly digests on their own cadence

`due_for_run` on each source is the real gate, so beat frequency is an upper bound and a source
is never fetched more often than its configured interval.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from pakjobs_core.config import settings
from pakjobs_core.logging import configure_logging

configure_logging(settings.log_level, settings.log_json)

celery_app = Celery(
    "rozgar",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Karachi",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=900,          # hard kill after 15 min
    task_soft_time_limit=840,     # graceful abort first
    task_acks_late=True,          # redeliver if a worker dies mid-task
    worker_prefetch_multiplier=1,  # long tasks: do not hoard messages
    worker_max_tasks_per_child=200,  # bound memory growth
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_default_queue="default",
    task_routes={
        "worker.tasks.ingest_source": {"queue": "ingestion"},
        "worker.tasks.schedule_due_sources": {"queue": "default"},
        "worker.tasks.run_expiration": {"queue": "maintenance"},
        "worker.tasks.verify_apply_urls": {"queue": "maintenance"},
        "worker.tasks.dispatch_alerts": {"queue": "notifications"},
    },
)

celery_app.conf.beat_schedule = {
    "high-priority-sources": {
        "task": "worker.tasks.schedule_due_sources",
        "schedule": 15 * 60.0,
        "kwargs": {"priority_max": 25},
    },
    "normal-sources": {
        "task": "worker.tasks.schedule_due_sources",
        "schedule": 30 * 60.0,
        "kwargs": {"priority_max": 60},
    },
    "slow-sources": {
        "task": "worker.tasks.schedule_due_sources",
        "schedule": 3 * 60 * 60.0,
        "kwargs": {"priority_max": None},
    },
    "expiration-sweep": {
        "task": "worker.tasks.run_expiration",
        "schedule": crontab(minute=5),  # hourly at :05
    },
    "apply-url-verification": {
        "task": "worker.tasks.verify_apply_urls",
        "schedule": crontab(minute=25, hour="*/6"),
    },
    "instant-alerts": {
        "task": "worker.tasks.dispatch_alerts",
        "schedule": 20 * 60.0,
        "kwargs": {"frequency": "instant"},
    },
    "daily-alerts": {
        "task": "worker.tasks.dispatch_alerts",
        "schedule": crontab(hour=9, minute=0),  # 09:00 PKT
        "kwargs": {"frequency": "daily"},
    },
    "weekly-alerts": {
        "task": "worker.tasks.dispatch_alerts",
        "schedule": crontab(day_of_week=1, hour=9, minute=30),  # Monday 09:30 PKT
        "kwargs": {"frequency": "weekly"},
    },
    "refresh-counters": {
        "task": "worker.tasks.refresh_counters",
        "schedule": crontab(minute=45),
    },
}
