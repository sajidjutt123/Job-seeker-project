"""Background tasks.

Every task is defensive: a failing source, provider or job must never take down the worker or
block the web application. Retries use exponential backoff with jitter and a bounded max.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import func, select, update

from pakjobs_core.config import settings
from pakjobs_core.db.session import session_scope
from pakjobs_core.domain.enums import AlertFrequency, JobStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import (
    Company,
    Job,
    JobAlert,
    JobCategory,
    JobSource,
    Notification,
    SourceRun,
    User,
)
from pakjobs_core.services.alerts import AlertMatchingService
from pakjobs_core.services.expiration import ExpirationService
from pakjobs_core.services.ingestion import IngestionService
from pakjobs_core.services.notifications import NotificationService, render_alert_email
from pakjobs_core.services.source_registry import due_sources, sync_default_sources


logger = get_logger("worker")

MAX_RETRIES = settings.ingest_max_retries
RETRY_BASE = settings.ingest_retry_base_seconds


def _backoff(attempt: int) -> int:
    """Exponential backoff with full jitter, capped at 30 minutes."""
    base = min(RETRY_BASE * (2 ** max(0, attempt - 1)), 1800)
    return int(base * (0.5 + random.random() / 2))


# ------------------------------------------------------------------ ingest --

@shared_task(bind=True, name="worker.tasks.ingest_source", max_retries=MAX_RETRIES)
def ingest_source(self, source_id: str, *, trigger: str = "scheduler", limit: int | None = None) -> dict[str, Any]:
    """Run the full ingestion pipeline for one source."""
    attempt = self.request.retries + 1
    try:
        with session_scope() as session:
            source = session.get(JobSource, uuid.UUID(source_id))
            if source is None:
                logger.warning("worker.source_missing", source_id=source_id)
                return {"ok": False, "reason": "source_not_found"}
            if not source.enabled and trigger == "scheduler":
                return {"ok": False, "reason": "source_disabled"}

            run = IngestionService(session).run_source(
                source, trigger=trigger, attempt=attempt, limit=limit
            )
            result = {
                "ok": run.status != "failed",
                "status": run.status,
                "source": source.slug,
                "created": run.created_count,
                "updated": run.updated_count,
                "duplicates": run.duplicate_count,
                "rejected": run.rejected_count,
                "error": run.error_message,
                "error_type": run.error_type,
            }
            retryable = (
                run.status == "failed"
                and run.error_type not in ("ConnectorConfigError", "UnknownConnector")
            )

        # Retry outside the session so the failure record is already committed.
        if retryable and attempt <= MAX_RETRIES:
            delay = _backoff(attempt)
            logger.warning("worker.ingest_retry", source_id=source_id, attempt=attempt, delay=delay)
            raise self.retry(countdown=delay)
        return result

    except SoftTimeLimitExceeded:
        logger.error("worker.ingest_timeout", source_id=source_id)
        return {"ok": False, "reason": "timeout"}
    except Exception as exc:  # noqa: BLE001
        if self.request.retries >= MAX_RETRIES:
            logger.error("worker.ingest_exhausted", source_id=source_id, error=str(exc))
            return {"ok": False, "reason": "retries_exhausted", "error": str(exc)[:300]}
        raise


@shared_task(name="worker.tasks.schedule_due_sources")
def schedule_due_sources(priority_max: int | None = None) -> dict[str, Any]:
    """Fan out ingestion tasks for every source whose interval has elapsed."""
    with session_scope() as session:
        sources = due_sources(session, priority_max=priority_max)
        payload = [(str(s.id), s.slug) for s in sources]

    for source_id, slug in payload:
        ingest_source.apply_async(args=[source_id], kwargs={"trigger": "scheduler"})
        logger.info("worker.scheduled", source=slug)

    return {"scheduled": len(payload), "sources": [slug for _, slug in payload]}


@shared_task(name="worker.tasks.sync_sources")
def sync_sources() -> dict[str, Any]:
    """Idempotent registry sync — safe to run on deploy."""
    with session_scope() as session:
        return sync_default_sources(session)


# -------------------------------------------------------------- lifecycle --

@shared_task(name="worker.tasks.run_expiration")
def run_expiration(unseen_days: int = 21) -> dict[str, Any]:
    with session_scope() as session:
        report = ExpirationService(session).run_all(unseen_days=unseen_days, check_urls=False)
        return report.as_dict()


@shared_task(name="worker.tasks.verify_apply_urls")
def verify_apply_urls(limit: int = 40) -> dict[str, Any]:
    """Network-bound; kept separate from the fast expiration sweep."""
    with session_scope() as session:
        report = ExpirationService(session).verify_apply_urls(limit=limit)
        return report.as_dict()


@shared_task(name="worker.tasks.refresh_counters")
def refresh_counters() -> dict[str, Any]:
    """Denormalised counts used by the UI (company + category job counts)."""
    with session_scope() as session:
        active = (
            select(Job.company_id, func.count(Job.id).label("n"))
            .where(Job.status == JobStatus.ACTIVE, Job.company_id.isnot(None), Job.is_canonical.is_(True))
            .group_by(Job.company_id)
            .subquery()
        )
        session.execute(update(Company).values(active_job_count=0))
        session.execute(
            update(Company)
            .where(Company.id == active.c.company_id)
            .values(active_job_count=active.c.n)
        )

        category_counts = session.execute(
            select(Job.category, func.count(Job.id))
            .where(Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True))
            .group_by(Job.category)
        ).all()
        for slug, count in category_counts:
            category = session.execute(
                select(JobCategory).where(JobCategory.slug == slug)
            ).scalar_one_or_none()
            if category is None:
                from pakjobs_core.domain.enums import CATEGORY_LABELS

                category = JobCategory(slug=slug, name=CATEGORY_LABELS.get(slug, slug.title()))
                session.add(category)
            category.active_job_count = count

        return {"companies_updated": True, "categories": len(category_counts)}


# ------------------------------------------------------------------ alerts --

@shared_task(name="worker.tasks.dispatch_alerts")
def dispatch_alerts(frequency: str = AlertFrequency.DAILY.value) -> dict[str, Any]:
    """Match new jobs against active alerts and send one digest per alert."""
    processed = matched = notified = failed = 0

    with session_scope() as session:
        matcher = AlertMatchingService(session)
        alert_ids = [a.id for a in matcher.active_alerts(frequency=frequency)]

    for alert_id in alert_ids:
        try:
            with session_scope() as session:
                matcher = AlertMatchingService(session)
                notifier = NotificationService(session)

                alert = session.get(JobAlert, alert_id)
                if alert is None or not alert.is_active:
                    continue
                processed += 1

                result = matcher.match_alert(alert)
                if not result.jobs:
                    continue
                matched += len(result.jobs)

                user = session.get(User, alert.user_id)
                if user is None or user.status in ("suspended", "deleted"):
                    continue

                subject, text, html = render_alert_email(alert.name, result.jobs, settings.web_base_url)
                notification = notifier.queue(
                    user=user, subject=subject, body=text, notification_type="job_alert",
                    payload={
                        "alert_id": str(alert.id),
                        "job_ids": [str(j.id) for j in result.jobs][:25],
                        "count": len(result.jobs),
                    },
                )
                sent = notifier.deliver(notification, to_email=user.email, html_body=html)
                matcher.record_matches(alert, result.jobs, notified=sent)
                if sent:
                    notified += 1
                else:
                    failed += 1
        except Exception as exc:  # noqa: BLE001 - one bad alert must not stop the batch
            failed += 1
            logger.error("worker.alert_failed", alert_id=str(alert_id), error=str(exc))

    logger.info("worker.alerts_dispatched", frequency=frequency, processed=processed,
                matched=matched, notified=notified, failed=failed)
    return {"frequency": frequency, "processed": processed, "matched": matched,
            "notified": notified, "failed": failed}


@shared_task(name="worker.tasks.retry_failed_notifications")
def retry_failed_notifications(limit: int = 50) -> dict[str, Any]:
    """Second chance for notifications that failed due to a transient provider error."""
    retried = succeeded = 0
    with session_scope() as session:
        notifier = NotificationService(session)
        rows = session.execute(
            select(Notification)
            .where(
                Notification.status == "failed",
                Notification.attempts < 3,
                Notification.created_at >= datetime.now(timezone.utc) - timedelta(days=2),
            )
            .limit(limit)
        ).scalars().all()

        for notification in rows:
            user = session.get(User, notification.user_id)
            if user is None:
                continue
            retried += 1
            if notifier.deliver(notification, to_email=user.email):
                succeeded += 1
    return {"retried": retried, "succeeded": succeeded}


# ------------------------------------------------------------ housekeeping --

@shared_task(name="worker.tasks.prune_old_data")
def prune_old_data(run_retention_days: int = 60, event_retention_days: int = 180) -> dict[str, Any]:
    """Keep observability tables bounded."""
    from sqlalchemy import delete

    from pakjobs_core.models import AnalyticsEvent, RefreshToken, SearchLog

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        runs = session.execute(
            delete(SourceRun).where(SourceRun.started_at < now - timedelta(days=run_retention_days))
        ).rowcount
        searches = session.execute(
            delete(SearchLog).where(SearchLog.created_at < now - timedelta(days=event_retention_days))
        ).rowcount
        events = session.execute(
            delete(AnalyticsEvent).where(
                AnalyticsEvent.created_at < now - timedelta(days=event_retention_days)
            )
        ).rowcount
        tokens = session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < now - timedelta(days=7))
        ).rowcount
    return {"source_runs": runs, "search_logs": searches, "analytics_events": events,
            "refresh_tokens": tokens}
