"""Alert matching engine.

New job → matching engine → matching users → notification service.

Matching runs against the same criteria vocabulary the search API uses, so "save this search as
an alert" is a lossless operation. `AlertMatch` rows make delivery idempotent: a job is never
sent twice for the same alert even if the worker retries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from pakjobs_core.domain.enums import JobStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import AlertMatch, Job, JobAlert
from pakjobs_core.pipeline.text import normalize_text

logger = get_logger("alerts")

MAX_JOBS_PER_ALERT_RUN = 25


@dataclass(slots=True)
class AlertMatchResult:
    alert: JobAlert
    jobs: list[Job] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.jobs)


class AlertMatchingService:
    def __init__(self, session: Session):
        self.session = session

    def active_alerts(self, frequency: str | None = None) -> list[JobAlert]:
        stmt = select(JobAlert).where(JobAlert.is_active.is_(True))
        if frequency:
            stmt = stmt.where(JobAlert.frequency == frequency)
        return list(self.session.execute(stmt).scalars().all())

    def match_alert(self, alert: JobAlert, *, lookback_hours: int = 26) -> AlertMatchResult:
        """Find new active jobs matching this alert since its watermark."""
        since = alert.last_job_cursor or (datetime.now(timezone.utc) - timedelta(hours=lookback_hours))
        conditions = self._conditions(alert, since)

        already_sent = select(AlertMatch.job_id).where(AlertMatch.alert_id == alert.id)
        stmt = (
            select(Job)
            .where(and_(*conditions), Job.id.notin_(already_sent))
            .order_by(Job.quality_score.desc(), Job.posted_at.desc().nullslast())
            .limit(MAX_JOBS_PER_ALERT_RUN)
        )
        jobs = list(self.session.execute(stmt).unique().scalars().all())
        return AlertMatchResult(alert=alert, jobs=jobs)

    def record_matches(self, alert: JobAlert, jobs: list[Job], *, notified: bool) -> None:
        now = datetime.now(timezone.utc)
        for job in jobs:
            self.session.add(
                AlertMatch(alert_id=alert.id, job_id=job.id, notified=notified, score=Decimal("0"))
            )
        if jobs:
            alert.match_count += len(jobs)
            alert.last_matched_at = now
            newest = max((j.created_at for j in jobs if j.created_at), default=now)
            alert.last_job_cursor = newest
        if notified:
            alert.last_notified_at = now

    # --- criteria translation ----------------------------------------------
    def _conditions(self, alert: JobAlert, since: datetime) -> list:
        conditions = [
            Job.status == JobStatus.ACTIVE,
            Job.hidden_by_admin.is_(False),
            Job.is_canonical.is_(True),
            Job.created_at > since,
        ]

        if alert.keywords:
            terms = [t for t in alert.keywords.split() if len(t) > 1][:8]
            if terms:
                conditions.append(
                    Job.search_vector.op("@@")(
                        func.websearch_to_tsquery("english", " ".join(terms))
                    )
                )
        if alert.cities:
            lowered = [normalize_text(c) for c in alert.cities if c]
            conditions.append(
                or_(
                    func.lower(Job.city_slug).in_(lowered),
                    func.lower(Job.city).in_(lowered),
                )
            )
        if alert.provinces:
            conditions.append(Job.province.in_(alert.provinces))
        if alert.categories:
            conditions.append(Job.category.in_(alert.categories))
        if alert.employment_types:
            conditions.append(Job.employment_type.in_(alert.employment_types))
        if alert.experience_levels:
            conditions.append(Job.experience_level.in_(alert.experience_levels))
        if alert.remote_only:
            conditions.append(Job.is_remote.is_(True))
        if alert.government_only:
            conditions.append(Job.is_government.is_(True))
        if alert.internship_only:
            conditions.append(Job.is_internship.is_(True))
        if alert.salary_min:
            conditions.append(
                or_(Job.salary_max >= alert.salary_min, Job.salary_min >= alert.salary_min)
            )
        return conditions
