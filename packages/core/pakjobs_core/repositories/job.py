"""Job data access (sync session — used by workers and scripts).

Repositories own SQL. Services own business rules. API routers own HTTP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pakjobs_core.domain.enums import JobStatus
from pakjobs_core.models import Job
from pakjobs_core.pipeline.text import slugify


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, job_id: uuid.UUID) -> Job | None:
        return self.session.get(Job, job_id)

    def get_by_slug(self, slug: str) -> Job | None:
        return self.session.execute(select(Job).where(Job.slug == slug)).unique().scalar_one_or_none()

    def get_by_source_job_id(self, source_id: uuid.UUID, source_job_id: str) -> Job | None:
        stmt = select(Job).where(Job.source_id == source_id, Job.source_job_id == source_job_id)
        return self.session.execute(stmt).unique().scalar_one_or_none()

    def build_unique_slug(self, title: str, company: str | None, city: str | None) -> str:
        """SEO-friendly, collision-free slug: title-company-city[-n]."""
        parts = [p for p in (title, company, city) if p]
        base = slugify("-".join(parts), max_length=110) or "job"
        candidate = base
        suffix = 1
        while self.session.execute(select(Job.id).where(Job.slug == candidate)).first() is not None:
            suffix += 1
            candidate = f"{base}-{suffix}"
            if suffix > 50:  # pathological collisions: fall back to a random tail
                candidate = f"{base}-{uuid.uuid4().hex[:8]}"
                break
        return candidate[:460]

    def stale_active_jobs(self, *, unseen_days: int, limit: int = 500) -> list[Job]:
        """Active jobs a source has not re-published for `unseen_days`."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=unseen_days)
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.ACTIVE,
                Job.last_seen_at.isnot(None),
                Job.last_seen_at < cutoff,
            )
            .order_by(Job.last_seen_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).unique().scalars().all())

    def jobs_past_deadline(self, limit: int = 1000) -> list[Job]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.ACTIVE, Job.deadline.isnot(None), Job.deadline < now)
            .limit(limit)
        )
        return list(self.session.execute(stmt).unique().scalars().all())

    def jobs_needing_url_check(self, *, older_than_days: int = 7, limit: int = 100) -> list[Job]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.ACTIVE,
                (Job.last_checked_at.is_(None)) | (Job.last_checked_at < cutoff),
            )
            .order_by(Job.last_checked_at.asc().nullsfirst())
            .limit(limit)
        )
        return list(self.session.execute(stmt).unique().scalars().all())

    def count_by_status(self) -> dict[str, int]:
        rows = self.session.execute(select(Job.status, func.count(Job.id)).group_by(Job.status)).all()
        return {status: count for status, count in rows}

    def jobs_created_since(self, since: datetime, limit: int = 500) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.created_at >= since, Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True))
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).unique().scalars().all())
