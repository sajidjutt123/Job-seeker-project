"""Job lifecycle / expiration engine.

Three independent mechanisms, all safe to run repeatedly:
  1. deadline passed          → EXPIRED
  2. no longer republished    → EXPIRED (source-removal inference, per-source grace period)
  3. apply URL permanently gone (404/410) → CLOSED

Nothing is deleted; every transition writes a `JobEvent` so the history is auditable and a job
can be reactivated if the source publishes it again.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from pakjobs_core.config import settings
from pakjobs_core.domain.enums import JobEventType, JobStatus
from pakjobs_core.http import http_verify
from pakjobs_core.logging import get_logger
from pakjobs_core.models import Job, JobEvent
from pakjobs_core.pipeline.validator import is_safe_url
from pakjobs_core.repositories.job import JobRepository

logger = get_logger("expiration")

DEFAULT_UNSEEN_DAYS = 21
URL_CHECK_BATCH = 40


@dataclass(slots=True)
class ExpirationReport:
    deadline_expired: int = 0
    unseen_expired: int = 0
    url_closed: int = 0
    url_checked: int = 0
    url_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "deadline_expired": self.deadline_expired,
            "unseen_expired": self.unseen_expired,
            "url_closed": self.url_closed,
            "url_checked": self.url_checked,
            "url_errors": self.url_errors,
        }


class ExpirationService:
    def __init__(self, session: Session):
        self.session = session
        self.jobs = JobRepository(session)

    def expire_past_deadline(self) -> int:
        now = datetime.now(timezone.utc)
        count = 0
        for job in self.jobs.jobs_past_deadline():
            self._transition(job, JobStatus.EXPIRED, JobEventType.EXPIRED,
                             {"reason": "deadline_passed", "deadline": job.deadline.isoformat() if job.deadline else None}, now)
            count += 1
        self.session.flush()
        return count

    def expire_unseen(self, unseen_days: int = DEFAULT_UNSEEN_DAYS) -> int:
        """A job the source stopped publishing is very likely filled or withdrawn."""
        now = datetime.now(timezone.utc)
        count = 0
        for job in self.jobs.stale_active_jobs(unseen_days=unseen_days):
            self._transition(
                job, JobStatus.EXPIRED, JobEventType.EXPIRED,
                {"reason": "not_seen_in_source", "unseen_days": unseen_days,
                 "last_seen_at": job.last_seen_at.isoformat() if job.last_seen_at else None},
                now,
            )
            count += 1
        self.session.flush()
        return count

    def verify_apply_urls(self, limit: int = URL_CHECK_BATCH) -> ExpirationReport:
        """HEAD-check application URLs. Only 404/410 close a job; everything else is inconclusive."""
        report = ExpirationReport()
        jobs = [j for j in self.jobs.jobs_needing_url_check(limit=limit) if is_safe_url(j.apply_url)]
        if not jobs:
            return report

        results = asyncio.run(self._check_urls([j.apply_url for j in jobs]))
        now = datetime.now(timezone.utc)
        for job, status_code in zip(jobs, results):
            job.last_checked_at = now
            report.url_checked += 1
            if status_code is None:
                report.url_errors += 1
                continue
            if status_code in (404, 410):
                job.apply_url_ok = False
                self._transition(job, JobStatus.CLOSED, JobEventType.CLOSED,
                                 {"reason": "apply_url_gone", "status_code": status_code}, now)
                report.url_closed += 1
            else:
                job.apply_url_ok = 200 <= status_code < 400
                self.session.add(
                    JobEvent(job_id=job.id, event_type=JobEventType.APPLY_URL_CHECKED, actor="system",
                             detail={"status_code": status_code})
                )
        self.session.flush()
        return report

    async def _check_urls(self, urls: list[str]) -> list[int | None]:
        semaphore = asyncio.Semaphore(6)
        headers = {"User-Agent": settings.ingest_user_agent}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12), follow_redirects=True, headers=headers, verify=http_verify()
        ) as client:
            async def check(url: str) -> int | None:
                async with semaphore:
                    try:
                        response = await client.head(url)
                        # Some servers reject HEAD; retry once with a ranged GET.
                        if response.status_code in (403, 405, 501):
                            response = await client.get(url, headers={"Range": "bytes=0-1024"})
                        return response.status_code
                    except httpx.HTTPError:
                        return None

            return list(await asyncio.gather(*(check(u) for u in urls)))

    def run_all(self, *, unseen_days: int = DEFAULT_UNSEEN_DAYS, check_urls: bool = True) -> ExpirationReport:
        report = ExpirationReport()
        report.deadline_expired = self.expire_past_deadline()
        report.unseen_expired = self.expire_unseen(unseen_days)
        if check_urls:
            url_report = self.verify_apply_urls()
            report.url_closed = url_report.url_closed
            report.url_checked = url_report.url_checked
            report.url_errors = url_report.url_errors
        logger.info("expiration.run", **report.as_dict())
        return report

    def _transition(self, job: Job, status: str, event: str, detail: dict, now: datetime) -> None:
        previous = job.status
        job.status = status
        job.expired_at = now
        self.session.add(
            JobEvent(job_id=job.id, event_type=event, actor="system",
                     detail={**detail, "previous_status": previous})
        )
