"""Ingestion pipeline orchestrator.

FETCH → PARSE → NORMALIZE → VALIDATE → CLASSIFY → DUPLICATE CHECK → QUALITY → SAVE → INDEX
→ (alert matching is queued separately by the worker)

Runs on the sync SQLAlchemy session because it executes inside Celery prefork workers.
Every run is recorded as a `SourceRun` row with full counters so source health is observable.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from pakjobs_core.connectors.base import SourceConnector
from pakjobs_core.connectors.registry import build_connector
from pakjobs_core.domain.enums import (
    JobEventType,
    JobStatus,
    SourceRunStatus,
    SourceStatus,
)
from pakjobs_core.logging import get_logger
from pakjobs_core.models import Company, Job, JobDuplicate, JobEvent, JobSource, SourceRun
from pakjobs_core.pipeline.deduplicator import (
    AUTO_MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
    find_duplicate,
)
from pakjobs_core.pipeline.quality import score_quality
from pakjobs_core.pipeline.schemas import FetchResult, NormalizedJob
from pakjobs_core.repositories.company import CompanyRepository
from pakjobs_core.repositories.job import JobRepository
from pakjobs_core.services.skills import sync_job_skills

logger = get_logger("ingestion")

CANDIDATE_LOOKBACK_DAYS = 75
MAX_CANDIDATES = 60


@dataclass(slots=True)
class IngestionStats:
    fetched: int = 0
    parsed: int = 0
    valid: int = 0
    rejected: int = 0
    duplicates: int = 0
    created: int = 0
    updated: int = 0
    review_flagged: int = 0
    errors: list[str] = field(default_factory=list)
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "parsed": self.parsed,
            "valid": self.valid,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "created": self.created,
            "updated": self.updated,
            "review_flagged": self.review_flagged,
            "rejection_reasons": self.rejection_reasons,
            "errors": self.errors[:10],
        }


class IngestionService:
    """Executes one source run end-to-end and persists the results."""

    def __init__(self, session: Session):
        self.session = session
        self.jobs = JobRepository(session)
        self.companies = CompanyRepository(session)

    # --- public API ---------------------------------------------------------
    def run_source(
        self,
        source: JobSource,
        *,
        trigger: str = "scheduler",
        attempt: int = 1,
        limit: int | None = None,
    ) -> SourceRun:
        run = SourceRun(
            source_id=source.id,
            status=SourceRunStatus.RUNNING,
            trigger=trigger,
            attempt=attempt,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()

        log = logger.bind(source=source.slug, connector=source.connector_key, run_id=str(run.id))
        log.info("ingest.start", trigger=trigger, attempt=attempt)

        try:
            connector = build_connector(source.connector_key, source.config, source_slug=source.slug)
        except KeyError as exc:
            return self._finish_failed(run, source, str(exc), "UnknownConnector", log)

        config_problems = connector.check_configuration()
        if config_problems:
            source.status = SourceStatus.NEEDS_CREDENTIALS
            return self._finish_failed(
                run, source, "; ".join(config_problems), "ConnectorConfigError", log, count_error=False
            )

        try:
            result: FetchResult = _run_async(connector.fetch_jobs(limit=limit))
        except Exception as exc:  # noqa: BLE001 - a connector must never crash the worker
            log.exception("ingest.connector_crash")
            return self._finish_failed(run, source, str(exc), type(exc).__name__, log)

        if not result.ok:
            return self._finish_failed(
                run, source, result.error or "Unknown connector error", result.error_type or "ConnectorError", log
            )

        stats = self._process(source, connector, result, log)

        run.fetched_count = stats.fetched
        run.parsed_count = stats.parsed
        run.valid_count = stats.valid
        run.rejected_count = stats.rejected
        run.duplicate_count = stats.duplicates
        run.created_count = stats.created
        run.updated_count = stats.updated
        run.stats = {**result.stats, **stats.as_dict()}
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        run.status = SourceRunStatus.PARTIAL if (result.partial or stats.errors) else SourceRunStatus.SUCCESS

        source.last_run_at = run.finished_at
        source.last_success_at = run.finished_at
        source.total_runs += 1
        source.total_jobs_collected += stats.created
        source.consecutive_failures = 0
        source.last_error = result.error if result.partial else None
        source.status = SourceStatus.DEGRADED if result.partial else SourceStatus.HEALTHY

        # Flush so the run record and source health are queryable by anything sharing this
        # session (and are not lost if the caller only refreshes objects).
        self.session.flush()
        log.info("ingest.finish", **stats.as_dict(), duration_ms=run.duration_ms)
        return run

    # --- pipeline -----------------------------------------------------------
    def _process(
        self, source: JobSource, connector: SourceConnector, result: FetchResult, log: Any
    ) -> IngestionStats:
        stats = IngestionStats(fetched=len(result.jobs))
        now = datetime.now(timezone.utc)

        for raw in result.jobs:
            try:
                normalized = connector.normalize_job(raw)
                stats.parsed += 1
            except Exception as exc:  # noqa: BLE001
                stats.rejected += 1
                stats.errors.append(f"normalize:{type(exc).__name__}:{exc}")
                self._count_reason(stats, "normalize_error")
                log.warning("ingest.normalize_failed", source_job_id=raw.source_job_id, error=str(exc))
                continue

            validation = connector.validate_job(normalized)
            if not validation.is_valid:
                stats.rejected += 1
                for err in validation.errors:
                    self._count_reason(stats, err)
                log.debug("ingest.rejected", source_job_id=raw.source_job_id, reasons=validation.errors)
                continue

            normalized.validation_warnings = validation.warnings
            stats.valid += 1

            try:
                created = self._persist(source, normalized, validation.needs_review, now, stats)
            except Exception as exc:  # noqa: BLE001 - isolate one bad record
                self.session.rollback()
                stats.errors.append(f"persist:{type(exc).__name__}:{exc}")
                self._count_reason(stats, "persist_error")
                log.warning("ingest.persist_failed", source_job_id=raw.source_job_id, error=str(exc))
                continue

            if created:
                stats.created += 1
            else:
                stats.updated += 1

        return stats

    def _persist(
        self,
        source: JobSource,
        normalized: NormalizedJob,
        needs_review: bool,
        now: datetime,
        stats: IngestionStats,
    ) -> bool:
        """Upsert one normalized job. Returns True when a new row was created."""
        existing = self.jobs.get_by_source_job_id(source.id, normalized.source_job_id)

        company = None
        if normalized.company_name:
            company = self.companies.get_or_create(
                name=normalized.company_name,
                matching_key=normalized.company_key or normalized.company_name,
                website=normalized.company_website,
                logo_url=normalized.company_logo,
            )

        duplicate_verdict = None
        if existing is None:
            candidates = self._duplicate_candidates(normalized)
            duplicate_verdict = find_duplicate(normalized, candidates, source_id=source.id)
            if duplicate_verdict.confidence >= AUTO_MERGE_THRESHOLD and duplicate_verdict.matched_id:
                stats.duplicates += 1

        quality = score_quality(
            normalized,
            source_reliability=source.reliability_score,
            duplicate_confidence=duplicate_verdict.confidence if duplicate_verdict else 0.0,
            company_verified=bool(company and company.verified),
        )
        normalized.quality_score = quality.score
        normalized.quality_breakdown = quality.breakdown

        if existing is not None:
            self._update_job(existing, normalized, now)
            self.session.flush()
            sync_job_skills(self.session, existing, normalized.skills)
            return False

        job = self._create_job(source, normalized, company, needs_review, now)
        self.session.add(job)
        self.session.flush()
        sync_job_skills(self.session, job, normalized.skills)

        if duplicate_verdict and duplicate_verdict.matched_id and duplicate_verdict.confidence >= REVIEW_THRESHOLD:
            self._link_duplicate(job, duplicate_verdict, stats)

        self.session.add(
            JobEvent(job_id=job.id, event_type=JobEventType.CREATED, actor="ingestion",
                     detail={"source": source.slug, "quality": quality.score})
        )
        return True

    def _create_job(
        self,
        source: JobSource,
        n: NormalizedJob,
        company: Company | None,
        needs_review: bool,
        now: datetime,
    ) -> Job:
        status = JobStatus.PENDING_REVIEW if needs_review else JobStatus.ACTIVE
        if n.deadline and n.deadline < now:
            status = JobStatus.EXPIRED
        return Job(
            source_id=source.id,
            source_job_id=n.source_job_id,
            company_id=company.id if company else None,
            company_name_raw=n.company_name,
            title=n.title,
            normalized_title=n.normalized_title or n.title.lower(),
            slug=self.jobs.build_unique_slug(n.title, n.company_name, n.city),
            description=n.description,
            normalized_description=n.normalized_description,
            responsibilities=n.responsibilities,
            requirements=n.requirements,
            benefits=n.benefits,
            location_raw=n.location_raw,
            location=n.location,
            city=n.city,
            city_slug=n.city_slug,
            province=n.province,
            country=n.country,
            work_mode=n.work_mode,
            is_remote=n.is_remote,
            employment_type=n.employment_type,
            experience_level=n.experience_level,
            category=n.category,
            secondary_categories=n.secondary_categories,
            is_internship=n.is_internship,
            is_government=n.is_government,
            is_fresh_graduate_friendly=n.is_fresh_graduate_friendly,
            education_requirement=n.education_requirement,
            classification_confidence=n.classification_confidence,
            classification_method=n.classification_method,
            salary_min=n.salary_min,
            salary_max=n.salary_max,
            salary_currency=n.salary_currency,
            salary_period=n.salary_period,
            status=status,
            posted_at=n.posted_at or now,
            deadline=n.deadline,
            last_seen_at=now,
            apply_url=n.apply_url,
            apply_url_hash=n.apply_url_hash,
            source_url=n.source_url,
            quality_score=n.quality_score,
            quality_breakdown=n.quality_breakdown,
            content_fingerprint=n.content_fingerprint,
            raw_payload=n.raw_payload,
            extra={"validation_warnings": n.validation_warnings} if n.validation_warnings else {},
        )

    def _update_job(self, job: Job, n: NormalizedJob, now: datetime) -> None:
        """Refresh a previously-seen posting; reactivate if the source is publishing it again."""
        changed: dict[str, Any] = {}
        for attr, value in (
            ("title", n.title),
            ("normalized_title", n.normalized_title or n.title.lower()),
            ("description", n.description),
            ("normalized_description", n.normalized_description),
            ("responsibilities", n.responsibilities),
            ("requirements", n.requirements),
            ("benefits", n.benefits),
            ("location", n.location),
            ("city", n.city),
            ("city_slug", n.city_slug),
            ("province", n.province),
            ("work_mode", n.work_mode),
            ("is_remote", n.is_remote),
            ("employment_type", n.employment_type),
            ("experience_level", n.experience_level),
            ("category", n.category),
            ("secondary_categories", n.secondary_categories),
            ("is_internship", n.is_internship),
            ("is_government", n.is_government),
            ("is_fresh_graduate_friendly", n.is_fresh_graduate_friendly),
            ("education_requirement", n.education_requirement),
            ("salary_min", n.salary_min),
            ("salary_max", n.salary_max),
            ("salary_currency", n.salary_currency),
            ("salary_period", n.salary_period),
            ("deadline", n.deadline),
            ("apply_url", n.apply_url),
            ("apply_url_hash", n.apply_url_hash),
            ("source_url", n.source_url),
            ("quality_score", n.quality_score),
            ("quality_breakdown", n.quality_breakdown),
            ("content_fingerprint", n.content_fingerprint),
        ):
            if getattr(job, attr) != value and value not in (None, [], ""):
                setattr(job, attr, value)
                changed[attr] = True

        job.last_seen_at = now
        was_expired = job.status in (JobStatus.EXPIRED, JobStatus.CLOSED, JobStatus.REMOVED)
        if was_expired and not job.hidden_by_admin and (not n.deadline or n.deadline > now):
            job.status = JobStatus.ACTIVE
            job.expired_at = None
            self.session.add(
                JobEvent(job_id=job.id, event_type=JobEventType.REACTIVATED, actor="ingestion",
                         detail={"previous_status": JobStatus.EXPIRED})
            )
        elif changed:
            self.session.add(
                JobEvent(job_id=job.id, event_type=JobEventType.UPDATED, actor="ingestion",
                         detail={"fields": sorted(changed)[:15]})
            )

    def _duplicate_candidates(self, n: NormalizedJob) -> Sequence[Job]:
        """Cheap pre-filter: same fingerprint OR same apply-url hash OR same company+city recently."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=CANDIDATE_LOOKBACK_DAYS)
        conditions = []
        if n.content_fingerprint:
            conditions.append(Job.content_fingerprint == n.content_fingerprint)
        if n.apply_url_hash:
            conditions.append(Job.apply_url_hash == n.apply_url_hash)
        if n.company_name and n.normalized_title:
            conditions.append(
                Job.company_name_raw.ilike(f"%{n.company_name[:40]}%")
                & (Job.normalized_title == n.normalized_title)
            )
        if not conditions:
            return []
        stmt = (
            select(Job)
            .where(
                or_(*conditions),
                Job.created_at >= cutoff,
                Job.status.notin_([JobStatus.REMOVED]),
            )
            .order_by(Job.created_at.desc())
            .limit(MAX_CANDIDATES)
        )
        return self.session.execute(stmt).unique().scalars().all()

    def _link_duplicate(self, job: Job, verdict: Any, stats: IngestionStats) -> None:
        canonical_id = verdict.matched_id
        canonical = self.session.get(Job, canonical_id)
        if canonical is None or canonical.id == job.id:
            return
        # Follow the chain so duplicates always point at the true canonical row.
        while canonical.canonical_job_id and canonical.canonical_job_id != canonical.id:
            parent = self.session.get(Job, canonical.canonical_job_id)
            if parent is None:
                break
            canonical = parent

        self.session.add(
            JobDuplicate(
                canonical_job_id=canonical.id,
                duplicate_job_id=job.id,
                confidence=verdict.confidence,
                signals=verdict.signals,
                method="heuristic",
            )
        )
        canonical.duplicate_count += 1

        if verdict.confidence >= AUTO_MERGE_THRESHOLD:
            job.canonical_job_id = canonical.id
            job.is_canonical = False
            # Keep the higher-quality record visible as canonical.
            if job.quality_score > canonical.quality_score + 5:
                job.is_canonical, canonical.is_canonical = True, False
                job.canonical_job_id = None
                canonical.canonical_job_id = job.id
        else:
            stats.review_flagged += 1

        self.session.add(
            JobEvent(
                job_id=job.id,
                event_type=JobEventType.DUPLICATE_LINKED,
                actor="ingestion",
                detail={"canonical_job_id": str(canonical.id), "confidence": verdict.confidence,
                        "signals": verdict.signals},
            )
        )

    # --- failure handling ---------------------------------------------------
    def _finish_failed(
        self,
        run: SourceRun,
        source: JobSource,
        message: str,
        error_type: str,
        log: Any,
        *,
        count_error: bool = True,
    ) -> SourceRun:
        run.status = SourceRunStatus.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        run.error_message = message[:2000]
        run.error_type = error_type

        source.last_run_at = run.finished_at
        source.last_failure_at = run.finished_at
        source.last_error = message[:2000]
        source.total_runs += 1
        if count_error:
            source.error_count += 1
            source.consecutive_failures += 1
            if source.consecutive_failures >= 5:
                source.status = SourceStatus.FAILING
            elif source.consecutive_failures >= 2:
                source.status = SourceStatus.DEGRADED
        self.session.flush()
        log.error("ingest.failed", error=message, error_type=error_type)
        return run

    @staticmethod
    def _count_reason(stats: IngestionStats, reason: str) -> None:
        stats.rejection_reasons[reason] = stats.rejection_reasons.get(reason, 0) + 1


def _run_async(coro: Any) -> Any:
    """Run an async connector from sync worker code, safely in any loop context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop (e.g. called from an async test) — use a dedicated thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
