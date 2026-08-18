"""Admin API.

Every route requires `role == admin`, enforced server-side by the `AdminUser` dependency.
Mutating actions write an `AdminAuditLog` row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import selectinload

from pakjobs_core.connectors.registry import available_connectors, get_connector_class
from pakjobs_core.domain.enums import JobEventType, JobStatus, SourceStatus, UserStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import (
    AdminAuditLog,
    Job,
    JobAlert,
    JobDuplicate,
    JobEvent,
    JobReport,
    JobSkill,
    JobSource,
    SourceRun,
    User,
)
from pakjobs_core.pipeline.text import slugify
from pakjobs_core.services.security import hash_ip

from app.core.deps import AdminUser, SessionDep
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.schemas.common import MessageResponse, Page
from app.schemas.job import JobAdminDetail, JobListItem
from app.services.analytics_service import analytics_overview
from app.services.job_serializer import to_admin_detail, to_list_items

logger = get_logger("api.admin")
router = APIRouter(prefix="/admin", tags=["admin"])


async def _audit(
    session, request: Request, admin: User, action: str, entity_type: str,
    entity_id: str | None = None, payload: dict[str, Any] | None = None,
) -> None:
    client = request.client.host if request.client else None
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id, action=action, entity_type=entity_type,
            entity_id=entity_id, payload=payload or {}, ip_hash=hash_ip(client),
        )
    )
    logger.info("admin.action", action=action, entity=entity_type, entity_id=entity_id,
                admin=str(admin.id))


# ---------------------------------------------------------------- overview --

@router.get("/overview")
async def overview(admin: AdminUser, session: SessionDep):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    job_stats = (
        await session.execute(
            select(
                func.count(Job.id),
                func.count(Job.id).filter(Job.status == JobStatus.ACTIVE),
                func.count(Job.id).filter(Job.status == JobStatus.EXPIRED),
                func.count(Job.id).filter(Job.status == JobStatus.PENDING_REVIEW),
                func.count(Job.id).filter(Job.created_at >= day_ago),
                func.count(Job.id).filter(Job.created_at >= week_ago),
                func.count(Job.id).filter(Job.hidden_by_admin.is_(True)),
                func.count(Job.id).filter(Job.is_canonical.is_(False)),
            )
        )
    ).one()

    user_stats = (
        await session.execute(
            select(
                func.count(User.id),
                func.count(User.id).filter(User.created_at >= week_ago),
                func.count(User.id).filter(User.status == UserStatus.SUSPENDED),
            )
        )
    ).one()

    source_stats = (
        await session.execute(
            select(
                func.count(JobSource.id),
                func.count(JobSource.id).filter(JobSource.enabled.is_(True)),
                func.count(JobSource.id).filter(JobSource.status == SourceStatus.FAILING),
                func.count(JobSource.id).filter(JobSource.status == SourceStatus.DEGRADED),
            )
        )
    ).one()

    failed_runs = (
        await session.execute(
            select(func.count(SourceRun.id)).where(
                SourceRun.status == "failed", SourceRun.started_at >= day_ago
            )
        )
    ).scalar_one()
    open_reports = (
        await session.execute(select(func.count(JobReport.id)).where(JobReport.status == "open"))
    ).scalar_one()
    duplicate_links = (await session.execute(select(func.count(JobDuplicate.id)))).scalar_one()
    active_alerts = (
        await session.execute(select(func.count(JobAlert.id)).where(JobAlert.is_active.is_(True)))
    ).scalar_one()

    return {
        "jobs": {
            "total": job_stats[0], "active": job_stats[1], "expired": job_stats[2],
            "pending_review": job_stats[3], "today": job_stats[4], "this_week": job_stats[5],
            "hidden": job_stats[6], "duplicates": job_stats[7],
        },
        "users": {"total": user_stats[0], "new_this_week": user_stats[1], "suspended": user_stats[2]},
        "sources": {
            "total": source_stats[0], "enabled": source_stats[1],
            "failing": source_stats[2], "degraded": source_stats[3],
            "failed_runs_24h": failed_runs,
        },
        "alerts": {"active": active_alerts},
        "moderation": {"open_reports": open_reports, "duplicate_links": duplicate_links},
    }


@router.get("/analytics")
async def admin_analytics(
    admin: AdminUser, session: SessionDep, days: Annotated[int, Query(ge=1, le=365)] = 30
):
    return await analytics_overview(session, days=days)


# -------------------------------------------------------------------- jobs --

@router.get("/jobs", response_model=Page[JobListItem])
async def admin_list_jobs(
    admin: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    source_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    hidden: Annotated[bool | None, Query()] = None,
    duplicates_only: Annotated[bool, Query()] = False,
    reported_only: Annotated[bool, Query()] = False,
    sort: Annotated[Literal["newest", "quality", "reports", "views"], Query()] = "newest",
    page: Annotated[int, Query(ge=1, le=2000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """Admin job browser — sees every status, including hidden and duplicate rows."""
    conditions = []
    if q:
        term = f"%{q[:100]}%"
        conditions.append(or_(Job.title.ilike(term), Job.company_name_raw.ilike(term),
                              cast(Job.id, String).ilike(term)))
    if status_filter:
        conditions.append(Job.status == status_filter)
    if source_id:
        conditions.append(Job.source_id == source_id)
    if category:
        conditions.append(Job.category == category)
    if hidden is not None:
        conditions.append(Job.hidden_by_admin.is_(hidden))
    if duplicates_only:
        conditions.append(Job.is_canonical.is_(False))
    if reported_only:
        conditions.append(Job.report_count > 0)

    where = and_(*conditions) if conditions else True
    total = (await session.execute(select(func.count(Job.id)).where(where))).scalar_one()

    order = {
        "newest": Job.created_at.desc(),
        "quality": Job.quality_score.desc(),
        "reports": Job.report_count.desc(),
        "views": Job.view_count.desc(),
    }[sort]

    rows = (
        await session.execute(
            select(Job)
            .options(selectinload(Job.skills).selectinload(JobSkill.skill))
            .where(where)
            .order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).unique().scalars().all()

    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return Page[JobListItem](
        items=to_list_items(rows), total=total, page=page, page_size=page_size,
        total_pages=total_pages, has_next=page < total_pages,
    )


@router.get("/jobs/{job_id}", response_model=JobAdminDetail)
async def admin_job_detail(job_id: uuid.UUID, admin: AdminUser, session: SessionDep):
    job = (
        await session.execute(
            select(Job).options(selectinload(Job.skills).selectinload(JobSkill.skill)).where(Job.id == job_id)
        )
    ).unique().scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found.")
    return to_admin_detail(job)


@router.get("/jobs/{job_id}/duplicates")
async def admin_job_duplicates(job_id: uuid.UUID, admin: AdminUser, session: SessionDep):
    """Both directions: duplicates of this job, and the canonical it was merged into."""
    rows = await session.execute(
        select(JobDuplicate, Job)
        .join(Job, Job.id == JobDuplicate.duplicate_job_id)
        .where(JobDuplicate.canonical_job_id == job_id)
    )
    as_canonical = [
        {
            "link_id": link.id, "confidence": link.confidence, "signals": link.signals,
            "job": {"id": dup.id, "title": dup.title, "slug": dup.slug,
                    "company": dup.company_name_raw, "source_id": dup.source_id,
                    "apply_url": dup.apply_url, "status": dup.status},
        }
        for link, dup in rows.all()
    ]
    reverse = await session.execute(
        select(JobDuplicate, Job)
        .join(Job, Job.id == JobDuplicate.canonical_job_id)
        .where(JobDuplicate.duplicate_job_id == job_id)
    )
    merged_into = [
        {
            "link_id": link.id, "confidence": link.confidence, "signals": link.signals,
            "job": {"id": canon.id, "title": canon.title, "slug": canon.slug,
                    "company": canon.company_name_raw, "status": canon.status},
        }
        for link, canon in reverse.all()
    ]
    return {"duplicates": as_canonical, "merged_into": merged_into}


@router.get("/jobs/{job_id}/events")
async def admin_job_events(job_id: uuid.UUID, admin: AdminUser, session: SessionDep):
    rows = await session.execute(
        select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.desc()).limit(100)
    )
    return [
        {"id": e.id, "type": e.event_type, "actor": e.actor, "detail": e.detail, "created_at": e.created_at}
        for e in rows.scalars().all()
    ]


class JobActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


@router.post("/jobs/{job_id}/hide", response_model=MessageResponse)
async def admin_hide_job(
    job_id: uuid.UUID, payload: JobActionRequest, admin: AdminUser, session: SessionDep, request: Request
):
    job = await _get_job(session, job_id)
    job.hidden_by_admin = True
    job.admin_note = payload.note
    session.add(JobEvent(job_id=job.id, event_type=JobEventType.HIDDEN, actor=f"admin:{admin.email}",
                         detail={"note": payload.note}))
    await _audit(session, request, admin, "job.hide", "job", str(job_id), {"note": payload.note})
    return MessageResponse(message="Job hidden from public listings.")


@router.post("/jobs/{job_id}/restore", response_model=MessageResponse)
async def admin_restore_job(job_id: uuid.UUID, admin: AdminUser, session: SessionDep, request: Request):
    job = await _get_job(session, job_id)
    job.hidden_by_admin = False
    if job.status == JobStatus.REMOVED:
        job.status = JobStatus.ACTIVE
    session.add(JobEvent(job_id=job.id, event_type=JobEventType.RESTORED, actor=f"admin:{admin.email}"))
    await _audit(session, request, admin, "job.restore", "job", str(job_id))
    return MessageResponse(message="Job restored.")


@router.post("/jobs/{job_id}/remove", response_model=MessageResponse)
async def admin_remove_job(
    job_id: uuid.UUID, payload: JobActionRequest, admin: AdminUser, session: SessionDep, request: Request
):
    """Soft delete: the row is kept so ingestion cannot silently resurrect it."""
    job = await _get_job(session, job_id)
    job.status = JobStatus.REMOVED
    job.hidden_by_admin = True
    job.admin_note = payload.note
    session.add(JobEvent(job_id=job.id, event_type=JobEventType.REMOVED, actor=f"admin:{admin.email}",
                         detail={"note": payload.note}))
    await _audit(session, request, admin, "job.remove", "job", str(job_id), {"note": payload.note})
    return MessageResponse(message="Job removed.")


@router.post("/jobs/{job_id}/approve", response_model=MessageResponse)
async def admin_approve_job(job_id: uuid.UUID, admin: AdminUser, session: SessionDep, request: Request):
    job = await _get_job(session, job_id)
    if job.status != JobStatus.PENDING_REVIEW:
        raise ValidationError("Only jobs pending review can be approved.")
    job.status = JobStatus.ACTIVE
    session.add(JobEvent(job_id=job.id, event_type=JobEventType.RESTORED, actor=f"admin:{admin.email}",
                         detail={"action": "approved"}))
    await _audit(session, request, admin, "job.approve", "job", str(job_id))
    return MessageResponse(message="Job approved and published.")


# ----------------------------------------------------------------- sources --

class SourceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    connector_key: str = Field(..., max_length=80)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    priority: int = Field(default=50, ge=1, le=100)
    fetch_interval_minutes: int = Field(default=60, ge=5, le=10080)
    website_url: str | None = Field(default=None, max_length=600)
    attribution_label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class SourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=100)
    fetch_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    reliability_score: float | None = Field(default=None, ge=0, le=1)
    website_url: str | None = Field(default=None, max_length=600)
    attribution_label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/connectors")
async def list_connectors(admin: AdminUser):
    """Available connector adapters and the config each one expects."""
    return [
        {
            "key": m.key, "name": m.name, "type": m.type, "description": m.description,
            "website": m.website, "requires_credentials": m.requires_credentials,
            "credential_env_keys": m.credential_env_keys, "config_schema": m.config_schema,
            "default_fetch_interval_minutes": m.default_fetch_interval_minutes,
            "default_reliability": m.default_reliability, "terms_url": m.terms_url,
            "legal_note": m.legal_note, "is_seed": m.is_seed,
        }
        for m in available_connectors()
    ]


@router.get("/sources")
async def admin_list_sources(admin: AdminUser, session: SessionDep):
    rows = await session.execute(
        select(JobSource, func.count(Job.id).filter(Job.status == JobStatus.ACTIVE))
        .outerjoin(Job, Job.source_id == JobSource.id)
        .group_by(JobSource.id)
        .order_by(JobSource.priority.asc(), JobSource.name.asc())
    )
    return [
        {
            "id": s.id, "name": s.name, "slug": s.slug, "type": s.type,
            "connector_key": s.connector_key, "enabled": s.enabled, "status": s.status,
            "priority": s.priority, "fetch_interval_minutes": s.fetch_interval_minutes,
            "reliability_score": s.reliability_score, "config": _redact(s.config),
            "requires_credentials": s.requires_credentials,
            "credential_env_keys": s.credential_env_keys,
            "last_run_at": s.last_run_at, "last_success_at": s.last_success_at,
            "last_failure_at": s.last_failure_at, "last_error": s.last_error,
            "consecutive_failures": s.consecutive_failures, "total_runs": s.total_runs,
            "total_jobs_collected": s.total_jobs_collected, "error_count": s.error_count,
            "active_jobs": active, "is_seed": s.is_seed, "notes": s.notes,
            "website_url": s.website_url, "attribution_label": s.attribution_label,
        }
        for s, active in rows.all()
    ]


@router.post("/sources", status_code=201)
async def admin_create_source(
    payload: SourceCreateRequest, admin: AdminUser, session: SessionDep, request: Request
):
    connector_cls = get_connector_class(payload.connector_key)
    if connector_cls is None:
        raise ValidationError(f"Unknown connector '{payload.connector_key}'.")
    meta = connector_cls.get_source_metadata()

    slug = slugify(payload.name, max_length=160)
    if (await session.execute(select(JobSource.id).where(JobSource.slug == slug))).first():
        raise ConflictError("A source with a similar name already exists.")

    source = JobSource(
        name=payload.name, slug=slug, type=meta.type, connector_key=payload.connector_key,
        website_url=payload.website_url or meta.website,
        attribution_label=payload.attribution_label or meta.attribution_label,
        description=meta.description, enabled=payload.enabled, priority=payload.priority,
        fetch_interval_minutes=payload.fetch_interval_minutes,
        reliability_score=meta.default_reliability,
        requires_credentials=meta.requires_credentials,
        credential_env_keys=meta.credential_env_keys, config=payload.config,
        status=SourceStatus.UNKNOWN if payload.enabled else SourceStatus.DISABLED,
        is_seed=meta.is_seed, notes=payload.notes,
    )
    session.add(source)
    await session.flush()
    await _audit(session, request, admin, "source.create", "source", str(source.id),
                 {"connector": payload.connector_key})
    return {"id": source.id, "slug": source.slug, "message": "Source created."}


@router.patch("/sources/{source_id}")
async def admin_update_source(
    source_id: uuid.UUID, payload: SourceUpdateRequest, admin: AdminUser,
    session: SessionDep, request: Request,
):
    source = await _get_source(session, source_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(source, field, value)
    if "enabled" in changes:
        source.status = SourceStatus.UNKNOWN if changes["enabled"] else SourceStatus.DISABLED
        if changes["enabled"]:
            source.consecutive_failures = 0
    await _audit(session, request, admin, "source.update", "source", str(source_id),
                 {"fields": sorted(changes)})
    return {"id": source.id, "message": "Source updated."}


@router.post("/sources/{source_id}/run")
async def admin_run_source(
    source_id: uuid.UUID, admin: AdminUser, session: SessionDep, request: Request,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """Queue an immediate ingestion run. Returns the Celery task id when a worker is reachable."""
    source = await _get_source(session, source_id)
    await _audit(session, request, admin, "source.run", "source", str(source_id))

    try:
        from worker.tasks import ingest_source

        task = ingest_source.delay(str(source_id), trigger="admin", limit=limit)
        return {"queued": True, "task_id": task.id,
                "message": f"Ingestion queued for {source.name}."}
    except Exception as exc:  # noqa: BLE001 - broker down must not 500 the dashboard
        logger.warning("admin.queue_failed", error=str(exc))
        return {
            "queued": False,
            "message": (
                "Could not reach the background worker. Check that Redis and the Celery worker "
                "are running, then try again."
            ),
            "detail": str(exc)[:200],
        }


@router.get("/sources/{source_id}/runs")
async def admin_source_runs(
    source_id: uuid.UUID, admin: AdminUser, session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    rows = await session.execute(
        select(SourceRun)
        .where(SourceRun.source_id == source_id)
        .order_by(SourceRun.started_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": r.id, "status": r.status, "trigger": r.trigger, "attempt": r.attempt,
            "started_at": r.started_at, "finished_at": r.finished_at, "duration_ms": r.duration_ms,
            "fetched": r.fetched_count, "valid": r.valid_count, "rejected": r.rejected_count,
            "duplicates": r.duplicate_count, "created": r.created_count, "updated": r.updated_count,
            "error_message": r.error_message, "error_type": r.error_type, "stats": r.stats,
        }
        for r in rows.scalars().all()
    ]


# ------------------------------------------------------------------- users --

@router.get("/users")
async def admin_list_users(
    admin: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    conditions = []
    if q:
        conditions.append(User.email.ilike(f"%{q[:100]}%"))
    if status_filter:
        conditions.append(User.status == status_filter)
    where = and_(*conditions) if conditions else True

    total = (await session.execute(select(func.count(User.id)).where(where))).scalar_one()
    rows = await session.execute(
        select(User).options(selectinload(User.profile)).where(where)
        .order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = rows.unique().scalars().all()
    return {
        "items": [
            {
                "id": u.id, "email": u.email, "role": u.role, "status": u.status,
                "email_verified": u.email_verified_at is not None,
                "created_at": u.created_at, "last_login_at": u.last_login_at,
                "full_name": u.profile.full_name if u.profile else None,
                "city": u.profile.city if u.profile else None,
                "profile_completion": u.profile.profile_completion if u.profile else 0,
            }
            for u in users
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/users/{user_id}/suspend", response_model=MessageResponse)
async def admin_suspend_user(
    user_id: uuid.UUID, admin: AdminUser, session: SessionDep, request: Request,
    reason: Annotated[str | None, Body(embed=True, max_length=500)] = None,
):
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    if target.id == admin.id:
        raise ValidationError("You cannot suspend your own account.")
    target.status = UserStatus.SUSPENDED
    target.token_version += 1  # immediately invalidates active sessions
    await _audit(session, request, admin, "user.suspend", "user", str(user_id), {"reason": reason})
    return MessageResponse(message="User suspended and signed out of all sessions.")


@router.post("/users/{user_id}/restore", response_model=MessageResponse)
async def admin_restore_user(user_id: uuid.UUID, admin: AdminUser, session: SessionDep, request: Request):
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    target.status = UserStatus.ACTIVE
    await _audit(session, request, admin, "user.restore", "user", str(user_id))
    return MessageResponse(message="User restored.")


@router.get("/users/{user_id}/activity")
async def admin_user_activity(user_id: uuid.UUID, admin: AdminUser, session: SessionDep):
    from pakjobs_core.models import AnalyticsEvent, SavedJob

    saved = (
        await session.execute(select(func.count(SavedJob.id)).where(SavedJob.user_id == user_id))
    ).scalar_one()
    alerts = (
        await session.execute(select(func.count(JobAlert.id)).where(JobAlert.user_id == user_id))
    ).scalar_one()
    events = await session.execute(
        select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
        .where(AnalyticsEvent.user_id == user_id)
        .group_by(AnalyticsEvent.event_type)
    )
    return {
        "saved_jobs": saved,
        "alerts": alerts,
        "events": {t: c for t, c in events.all()},
    }


# ----------------------------------------------------------------- reports --

@router.get("/reports")
async def admin_list_reports(
    admin: AdminUser,
    session: SessionDep,
    status_filter: Annotated[str, Query(alias="status")] = "open",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    where = JobReport.status == status_filter if status_filter != "all" else True
    total = (await session.execute(select(func.count(JobReport.id)).where(where))).scalar_one()
    rows = await session.execute(
        select(JobReport).options(selectinload(JobReport.job)).where(where)
        .order_by(JobReport.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    reports = rows.unique().scalars().all()
    return {
        "items": [
            {
                "id": r.id, "reason": r.reason, "details": r.details, "status": r.status,
                "reporter_email": r.reporter_email, "created_at": r.created_at,
                "resolution_note": r.resolution_note,
                "job": {
                    "id": r.job.id, "title": r.job.title, "slug": r.job.slug,
                    "company": r.job.company_name_raw, "status": r.job.status,
                    "apply_url": r.job.apply_url,
                } if r.job else None,
            }
            for r in reports
        ],
        "total": total, "page": page, "page_size": page_size,
    }


class ResolveReportRequest(BaseModel):
    action: Literal["resolve", "reject", "remove_job"]
    note: str | None = Field(default=None, max_length=1000)


@router.post("/reports/{report_id}/resolve", response_model=MessageResponse)
async def admin_resolve_report(
    report_id: uuid.UUID, payload: ResolveReportRequest, admin: AdminUser,
    session: SessionDep, request: Request,
):
    report = (
        await session.execute(
            select(JobReport).options(selectinload(JobReport.job)).where(JobReport.id == report_id)
        )
    ).unique().scalar_one_or_none()
    if report is None:
        raise NotFoundError("Report not found.")

    report.resolution_note = payload.note
    report.resolved_by = admin.id
    report.resolved_at = datetime.now(timezone.utc)

    if payload.action == "reject":
        report.status = "rejected"
        message = "Report rejected."
    else:
        report.status = "resolved"
        message = "Report resolved."
        if payload.action == "remove_job" and report.job:
            report.job.status = JobStatus.REMOVED
            report.job.hidden_by_admin = True
            session.add(
                JobEvent(job_id=report.job.id, event_type=JobEventType.REMOVED,
                         actor=f"admin:{admin.email}", detail={"reason": "report", "note": payload.note})
            )
            message = "Report resolved and job removed."

    await _audit(session, request, admin, f"report.{payload.action}", "report", str(report_id),
                 {"note": payload.note})
    return MessageResponse(message=message)


# ------------------------------------------------------------- audit trail --

@router.get("/audit-logs")
async def admin_audit_logs(
    admin: AdminUser, session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
):
    rows = await session.execute(
        select(AdminAuditLog, User.email)
        .outerjoin(User, User.id == AdminAuditLog.admin_user_id)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": log.id, "action": log.action, "entity_type": log.entity_type,
            "entity_id": log.entity_id, "payload": log.payload,
            "admin_email": email, "created_at": log.created_at,
        }
        for log, email in rows.all()
    ]


# ----------------------------------------------------------------- helpers --

async def _get_job(session, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    return job


async def _get_source(session, source_id: uuid.UUID) -> JobSource:
    source = await session.get(JobSource, source_id)
    if source is None:
        raise NotFoundError("Source not found.")
    return source


def _redact(config: dict[str, Any]) -> dict[str, Any]:
    """Never echo secret-looking config values back to the browser."""
    secret_like = ("token", "secret", "key", "password", "credential")
    return {
        k: ("***" if any(s in k.lower() for s in secret_like) and v else v)
        for k, v in (config or {}).items()
    }
