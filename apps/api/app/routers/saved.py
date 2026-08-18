"""Saved jobs. Fully server-side persisted, filterable and sortable."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from pakjobs_core.domain.enums import AnalyticsEventType
from pakjobs_core.models import Job, JobSkill, SavedJob

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import ConflictError, NotFoundError
from app.schemas.common import MessageResponse, Page
from app.schemas.job import SaveJobRequest, SavedJobItem
from app.services.analytics_service import record_event
from app.services.job_serializer import to_list_item

router = APIRouter(prefix="/saved-jobs", tags=["saved-jobs"])


@router.get("", response_model=Page[SavedJobItem])
async def list_saved_jobs(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=120)] = None,
    folder: Annotated[str | None, Query(max_length=80)] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    sort: Annotated[Literal["saved_newest", "saved_oldest", "posted_newest", "deadline"], Query()] = "saved_newest",
    page: Annotated[int, Query(ge=1, le=200)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
):
    conditions = [SavedJob.user_id == user.id]
    if folder:
        conditions.append(SavedJob.folder == folder)
    if q:
        conditions.append(Job.title.ilike(f"%{q[:80]}%"))
    if category:
        conditions.append(Job.category == category)
    if status_filter:
        conditions.append(Job.status == status_filter)

    base = select(SavedJob).join(Job, Job.id == SavedJob.job_id).where(*conditions)
    total = (
        await session.execute(
            select(func.count(SavedJob.id)).join(Job, Job.id == SavedJob.job_id).where(*conditions)
        )
    ).scalar_one()

    order = {
        "saved_newest": SavedJob.created_at.desc(),
        "saved_oldest": SavedJob.created_at.asc(),
        "posted_newest": Job.posted_at.desc().nullslast(),
        "deadline": Job.deadline.asc().nullslast(),
    }[sort]

    rows = (
        await session.execute(
            base.options(
                selectinload(SavedJob.job).selectinload(Job.skills).selectinload(JobSkill.skill)
            )
            .order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).unique().scalars().all()

    items = [
        SavedJobItem(
            id=row.id,
            job=to_list_item(row.job, profile=user.profile, saved_ids={row.job_id}, include_match=bool(user.profile)),
            note=row.note,
            folder=row.folder,
            created_at=row.created_at,
        )
        for row in rows
    ]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return Page[SavedJobItem](
        items=items, total=total, page=page, page_size=page_size,
        total_pages=total_pages, has_next=page < total_pages,
    )


@router.post("/{job_id}", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def save_job(job_id: uuid.UUID, payload: SaveJobRequest, user: CurrentUser, session: SessionDep):
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found.")

    existing = (
        await session.execute(
            select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("You have already saved this job.")

    session.add(SavedJob(user_id=user.id, job_id=job_id, note=payload.note, folder=payload.folder))
    await session.execute(
        update(Job).where(Job.id == job_id).values(save_count=Job.save_count + 1)
        .execution_options(synchronize_session=False)
    )
    await record_event(
        session, AnalyticsEventType.JOB_SAVE, user_id=user.id, entity_type="job", entity_id=str(job_id)
    )
    return MessageResponse(message="Job saved.")


@router.delete("/{job_id}", response_model=MessageResponse)
async def unsave_job(job_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    result = await session.execute(
        delete(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)
    )
    if result.rowcount == 0:
        raise NotFoundError("That job is not in your saved list.")
    await session.execute(
        update(Job).where(Job.id == job_id, Job.save_count > 0).values(save_count=Job.save_count - 1)
        .execution_options(synchronize_session=False)
    )
    await record_event(
        session, AnalyticsEventType.JOB_UNSAVE, user_id=user.id, entity_type="job", entity_id=str(job_id)
    )
    return MessageResponse(message="Removed from saved jobs.")


@router.get("/ids", response_model=list[uuid.UUID])
async def saved_job_ids(user: CurrentUser, session: SessionDep):
    """Lets the frontend render save-state without N extra requests."""
    rows = await session.execute(
        select(SavedJob.job_id).where(SavedJob.user_id == user.id).limit(1000)
    )
    return list(rows.scalars().all())
