"""ORM → API mapping for jobs.

Single place that decides what the public sees. Internal signals (quality breakdown, raw payload,
source config, fingerprints) are only exposed through the explicit admin serializer.
"""

from __future__ import annotations

import uuid
from typing import Iterable, Sequence

from pakjobs_core.models import Company, Job, JobSource, Profile
from pakjobs_core.services.recommendation import score_job_for_profile

from app.schemas.job import (
    CompanySummary,
    JobAdminDetail,
    JobDetail,
    JobListItem,
    SalaryRange,
    SourceBadge,
    category_label,
)


def _source_badge(source: JobSource | None) -> SourceBadge | None:
    if source is None:
        return SourceBadge(name="Direct posting", label="Posted directly", type="employer_direct")
    return SourceBadge(
        id=source.id,
        name=source.name,
        slug=source.slug,
        label=source.attribution_label or source.name,
        website_url=source.website_url,
        type=source.type,
    )


def _company_summary(company: Company | None) -> CompanySummary | None:
    if company is None:
        return None
    return CompanySummary.model_validate(company)


def _salary(job: Job) -> SalaryRange | None:
    if job.salary_min is None and job.salary_max is None:
        return None
    return SalaryRange(
        min=job.salary_min, max=job.salary_max,
        currency=job.salary_currency or "PKR", period=job.salary_period,
    )


def _skill_names(job: Job) -> list[str]:
    return [link.skill.name for link in (job.skills or []) if link.skill][:12]


def to_list_item(
    job: Job,
    *,
    profile: Profile | None = None,
    saved_ids: set[uuid.UUID] | None = None,
    include_match: bool = False,
) -> JobListItem:
    item = JobListItem(
        id=job.id,
        slug=job.slug,
        title=job.title,
        company_name=job.company_name_raw or (job.company.name if job.company else None),
        company=_company_summary(job.company),
        location=job.location,
        city=job.city,
        province=job.province,
        country=job.country,
        is_remote=job.is_remote,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        category=job.category,
        category_label=category_label(job.category),
        is_internship=job.is_internship,
        is_government=job.is_government,
        is_fresh_graduate_friendly=job.is_fresh_graduate_friendly,
        is_featured=job.is_featured,
        salary=_salary(job),
        posted_at=job.posted_at,
        deadline=job.deadline,
        status=job.status,
        source=_source_badge(job.source),
        apply_url=job.apply_url,
        skills=_skill_names(job),
    )
    if saved_ids is not None:
        item.is_saved = job.id in saved_ids
    if include_match and profile is not None:
        match = score_job_for_profile(job, profile)
        item.match_score = match.score
        item.match_reasons = match.reasons
    return item


def to_detail(
    job: Job,
    *,
    profile: Profile | None = None,
    saved_ids: set[uuid.UUID] | None = None,
    include_match: bool = False,
    other_sources: Sequence[JobSource] = (),
) -> JobDetail:
    base = to_list_item(job, profile=profile, saved_ids=saved_ids, include_match=include_match)
    return JobDetail(
        **base.model_dump(),
        description=job.description,
        responsibilities=job.responsibilities or [],
        requirements=job.requirements or [],
        benefits=job.benefits or [],
        education_requirement=job.education_requirement,
        source_url=job.source_url,
        origin=job.origin,
        view_count=job.view_count,
        duplicate_count=job.duplicate_count,
        other_sources=[b for b in (_source_badge(s) for s in other_sources) if b],
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def to_admin_detail(job: Job, *, other_sources: Sequence[JobSource] = ()) -> JobAdminDetail:
    detail = to_detail(job, other_sources=other_sources)
    return JobAdminDetail(
        **detail.model_dump(),
        quality_score=job.quality_score,
        quality_breakdown=job.quality_breakdown or {},
        classification_confidence=job.classification_confidence,
        classification_method=job.classification_method,
        source_job_id=job.source_job_id,
        content_fingerprint=job.content_fingerprint,
        canonical_job_id=job.canonical_job_id,
        is_canonical=job.is_canonical,
        hidden_by_admin=job.hidden_by_admin,
        admin_note=job.admin_note,
        report_count=job.report_count,
        apply_url_ok=job.apply_url_ok,
        last_seen_at=job.last_seen_at,
        last_checked_at=job.last_checked_at,
    )


def to_list_items(
    jobs: Iterable[Job],
    *,
    profile: Profile | None = None,
    saved_ids: set[uuid.UUID] | None = None,
    include_match: bool = False,
) -> list[JobListItem]:
    return [
        to_list_item(job, profile=profile, saved_ids=saved_ids, include_match=include_match)
        for job in jobs
    ]
