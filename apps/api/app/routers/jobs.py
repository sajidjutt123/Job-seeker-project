"""Public job endpoints: search, detail, apply tracking, reporting, facets."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from pakjobs_core.domain.enums import AnalyticsEventType, JobStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import Job, JobReport, JobSkill, JobSource, SavedJob
from pakjobs_core.services.search import SearchFilters, build_search_service

from app.core.deps import OptionalUser, SessionDep
from app.core.errors import NotFoundError, ValidationError
from app.schemas.job import (
    Facet,
    JobDetail,
    JobListItem,
    JobSearchResponse,
    ReportJobRequest,
    category_label,
)
from app.schemas.common import MessageResponse
from app.services.analytics_service import record_event, record_search
from app.services.job_serializer import to_detail, to_list_items

logger = get_logger("api.jobs")
router = APIRouter(prefix="/jobs", tags=["jobs"])

search_service = build_search_service()


def _anon_id(request: Request) -> str:
    """Coarse, non-durable visitor bucket derived from request metadata (no cookie set)."""
    from pakjobs_core.services.security import hash_ip

    client = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        client = forwarded.split(",")[0].strip()
    return (hash_ip(client) or "anon")[:32]


async def _saved_ids(session, user, job_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if user is None or not job_ids:
        return set()
    rows = await session.execute(
        select(SavedJob.job_id).where(SavedJob.user_id == user.id, SavedJob.job_id.in_(job_ids))
    )
    return set(rows.scalars().all())


@router.get("", response_model=JobSearchResponse)
async def search_jobs(
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    q: Annotated[str | None, Query(max_length=200, description="Keyword or job title")] = None,
    city: Annotated[str | None, Query(max_length=120)] = None,
    province: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[list[str] | None, Query()] = None,
    employment_type: Annotated[list[str] | None, Query()] = None,
    experience: Annotated[list[str] | None, Query()] = None,
    education: Annotated[str | None, Query(max_length=40)] = None,
    company: Annotated[str | None, Query(max_length=120)] = None,
    skills: Annotated[list[str] | None, Query()] = None,
    remote: Annotated[bool | None, Query()] = None,
    government: Annotated[bool | None, Query()] = None,
    internship: Annotated[bool | None, Query()] = None,
    fresh_graduate: Annotated[bool | None, Query()] = None,
    salary_min: Annotated[int | None, Query(ge=0, le=100_000_000)] = None,
    salary_max: Annotated[int | None, Query(ge=0, le=100_000_000)] = None,
    posted_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    sort: Annotated[Literal["newest", "relevance", "deadline", "salary", "quality"], Query()] = "newest",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    facets: Annotated[bool, Query(description="Include filter counts")] = False,
):
    """Search active jobs. Every filter is expressed in the URL so results are shareable."""
    filters = SearchFilters(
        q=q,
        city=city,
        province=province,
        categories=category or [],
        employment_types=employment_type or [],
        experience_levels=experience or [],
        education=education,
        company=company,
        skills=skills or [],
        remote=remote,
        government=government,
        internship=internship,
        fresh_graduate=fresh_graduate,
        salary_min=Decimal(salary_min) if salary_min is not None else None,
        salary_max=Decimal(salary_max) if salary_max is not None else None,
        posted_within_days=posted_within_days,
        sort="relevance" if (q and sort == "newest") else sort,
        page=page,
        page_size=page_size,
    )

    result = await search_service.search(session, filters, with_facets=facets)

    saved = await _saved_ids(session, user, [j.id for j in result.items])
    profile = user.profile if user else None
    items = to_list_items(result.items, profile=profile, saved_ids=saved, include_match=bool(profile))

    await record_search(
        session,
        query=q, city=city, category=(category or [None])[0],
        filters=filters.as_log_payload(), result_count=result.total,
        duration_ms=result.took_ms, user_id=user.id if user else None,
    )
    await record_event(
        session, AnalyticsEventType.SEARCH,
        user_id=user.id if user else None, anon_id=_anon_id(request),
        properties={"q": q, "city": city, "results": result.total},
    )

    return JobSearchResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
        has_next=result.has_next,
        took_ms=result.took_ms,
        facets={
            name: [
                Facet(value=f["value"], count=f["count"],
                      label=category_label(f["value"]) if name == "category" else None)
                for f in values
            ]
            for name, values in result.facets.items()
        },
    )


@router.get("/latest", response_model=list[JobListItem])
async def latest_jobs(
    session: SessionDep,
    user: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=24)] = 12,
    remote: Annotated[bool | None, Query()] = None,
    government: Annotated[bool | None, Query()] = None,
    internship: Annotated[bool | None, Query()] = None,
    city: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
):
    """Homepage feeds. Cheap, cacheable, no facets."""
    filters = SearchFilters(
        remote=remote, government=government, internship=internship,
        city=city, category=category, sort="newest", page=1, page_size=limit,
    )
    result = await search_service.search(session, filters)
    saved = await _saved_ids(session, user, [j.id for j in result.items])
    return to_list_items(result.items, profile=user.profile if user else None, saved_ids=saved)


@router.get("/recommended", response_model=list[JobListItem])
async def recommended_jobs(
    session: SessionDep, user: OptionalUser, limit: Annotated[int, Query(ge=1, le=30)] = 12
):
    """Personalised feed. Requires sign-in; returns an empty list for anonymous visitors."""
    if user is None or user.profile is None:
        return []

    profile = user.profile
    # Prefilter cheaply on the user's declared preferences, then rank in Python.
    filters = SearchFilters(
        cities=[c for c in (profile.preferred_locations or [])][:5] or ([profile.city] if profile.city else []),
        categories=(profile.preferred_categories or [])[:5],
        remote=True if (profile.remote_preference == "remote") else None,
        sort="newest", page=1, page_size=60,
    )
    result = await search_service.search(session, filters)
    candidates = result.items
    if len(candidates) < 10:
        # Widen the net rather than showing an almost-empty feed.
        fallback = await search_service.search(
            session, SearchFilters(sort="newest", page=1, page_size=60)
        )
        seen = {j.id for j in candidates}
        candidates += [j for j in fallback.items if j.id not in seen]

    from pakjobs_core.services.recommendation import score_job_for_profile

    saved_rows = await session.execute(
        select(SavedJob.job_id).where(SavedJob.user_id == user.id).limit(200)
    )
    saved = set(saved_rows.scalars().all())

    scored = sorted(
        ((score_job_for_profile(job, profile), job) for job in candidates),
        key=lambda pair: pair[0].score,
        reverse=True,
    )
    items = []
    for match, job in scored[:limit]:
        item = to_list_items([job], profile=profile, saved_ids=saved)[0]
        item.match_score = match.score
        item.match_reasons = match.reasons
        items.append(item)
    return items


@router.get("/facets")
async def job_facets(session: SessionDep):
    """Aggregate counts used by the homepage (categories, cities) — one round trip."""
    category_rows = await session.execute(
        select(Job.category, func.count(Job.id))
        .where(Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True), Job.hidden_by_admin.is_(False))
        .group_by(Job.category)
        .order_by(func.count(Job.id).desc())
    )
    city_rows = await session.execute(
        select(Job.city, Job.city_slug, Job.province, func.count(Job.id))
        .where(
            Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True),
            Job.hidden_by_admin.is_(False), Job.city.isnot(None),
        )
        .group_by(Job.city, Job.city_slug, Job.province)
        .order_by(func.count(Job.id).desc())
        .limit(24)
    )
    totals = await session.execute(
        select(
            func.count(Job.id),
            func.count(Job.id).filter(Job.is_remote.is_(True)),
            func.count(Job.id).filter(Job.is_government.is_(True)),
            func.count(Job.id).filter(Job.is_internship.is_(True)),
            func.count(Job.id).filter(Job.is_fresh_graduate_friendly.is_(True)),
            func.count(Job.id).filter(
                Job.posted_at >= datetime.now(timezone.utc) - timedelta(days=1)
            ),
        ).where(Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True), Job.hidden_by_admin.is_(False))
    )
    total, remote, government, internship, fresh, today = totals.one()

    return {
        "totals": {
            "active": total, "remote": remote, "government": government,
            "internships": internship, "fresh_graduate": fresh, "posted_today": today,
        },
        "categories": [
            {"slug": slug, "label": category_label(slug), "count": count}
            for slug, count in category_rows.all()
        ],
        "cities": [
            {"name": name, "slug": slug, "province": province, "count": count}
            for name, slug, province, count in city_rows.all()
        ],
    }


@router.get("/{slug}", response_model=JobDetail)
async def job_detail(slug: str, request: Request, session: SessionDep, user: OptionalUser):
    job = (
        await session.execute(
            select(Job)
            .options(selectinload(Job.skills).selectinload(JobSkill.skill))
            .where(Job.slug == slug)
        )
    ).unique().scalar_one_or_none()

    if job is None or job.status == JobStatus.REMOVED or job.hidden_by_admin:
        raise NotFoundError("We could not find that job. It may have been removed by the source.")

    # A duplicate URL should show the canonical record rather than a dead end.
    if job.canonical_job_id and not job.is_canonical:
        canonical = (
            await session.execute(
                select(Job)
                .options(selectinload(Job.skills).selectinload(JobSkill.skill))
                .where(Job.id == job.canonical_job_id)
            )
        ).unique().scalar_one_or_none()
        if canonical is not None and not canonical.hidden_by_admin:
            job = canonical

    other_sources = await _duplicate_sources(session, job)
    saved = await _saved_ids(session, user, [job.id])

    # Serialize BEFORE issuing the UPDATE: a bulk update expires loaded attributes, and any
    # subsequent attribute access would trigger lazy IO that async sessions cannot perform.
    detail = to_detail(
        job,
        profile=user.profile if user else None,
        saved_ids=saved,
        include_match=bool(user and user.profile),
        other_sources=other_sources,
    )

    await _bump(session, Job.id == job.id, view_count=Job.view_count + 1)
    await record_event(
        session, AnalyticsEventType.JOB_VIEW,
        user_id=user.id if user else None, anon_id=_anon_id(request),
        entity_type="job", entity_id=str(job.id),
        properties={"category": detail.category, "city": detail.city},
    )
    return detail


async def _bump(session, condition, **values):
    """Counter increment that does not expire in-memory ORM state."""
    await session.execute(
        update(Job).where(condition).values(**values).execution_options(synchronize_session=False)
    )


async def _duplicate_sources(session, job: Job) -> list[JobSource]:
    """Sources of merged duplicates — attribution for every place the job was found."""
    from pakjobs_core.models import JobDuplicate

    rows = await session.execute(
        select(JobSource)
        .join(Job, Job.source_id == JobSource.id)
        .join(JobDuplicate, JobDuplicate.duplicate_job_id == Job.id)
        .where(JobDuplicate.canonical_job_id == job.id)
        .distinct()
        .limit(6)
    )
    sources = list(rows.scalars().all())
    return [s for s in sources if job.source_id != s.id]


@router.post("/{job_id}/apply-click", response_model=MessageResponse)
async def track_apply_click(job_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser):
    """Records intent to apply. The browser navigates to the source regardless of the outcome."""
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    await _bump(session, Job.id == job_id, apply_click_count=Job.apply_click_count + 1)
    await record_event(
        session, AnalyticsEventType.APPLY_CLICK,
        user_id=user.id if user else None, anon_id=_anon_id(request),
        entity_type="job", entity_id=str(job_id),
        properties={"category": job.category, "source_id": str(job.source_id) if job.source_id else None},
    )
    return MessageResponse(message="Recorded.")


@router.post("/{job_id}/report", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def report_job(job_id: uuid.UUID, payload: ReportJobRequest, session: SessionDep, user: OptionalUser):
    """Anyone can report a listing; admins triage from the dashboard."""
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found.")

    if user is None and not payload.reporter_email:
        raise ValidationError(
            "Please provide an email address so we can follow up, or sign in to report.",
            details={"fields": {"reporter_email": "Required when not signed in"}},
        )

    session.add(
        JobReport(
            job_id=job_id,
            user_id=user.id if user else None,
            reason=payload.reason,
            details=payload.details,
            reporter_email=payload.reporter_email or (user.email if user else None),
        )
    )
    await _bump(session, Job.id == job_id, report_count=Job.report_count + 1)
    logger.info("job.reported", job_id=str(job_id), reason=payload.reason)
    return MessageResponse(message="Thank you. Our team will review this listing.")
