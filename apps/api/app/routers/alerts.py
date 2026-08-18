"""Job alerts: saved searches that notify the user when new matches appear."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from pakjobs_core.domain.enums import AnalyticsEventType, NotificationChannel, NotificationStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import JobAlert, Notification
from pakjobs_core.services.security import verify_unsubscribe

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import ConflictError, NotFoundError
from app.schemas.common import (
    AlertCreateRequest,
    AlertResponse,
    AlertUpdateRequest,
    MessageResponse,
    NotificationResponse,
)
from app.services.analytics_service import record_event

logger = get_logger("api.alerts")
router = APIRouter(tags=["alerts"])

MAX_ALERTS_PER_USER = 20


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(user: CurrentUser, session: SessionDep):
    rows = await session.execute(
        select(JobAlert).where(JobAlert.user_id == user.id).order_by(JobAlert.created_at.desc())
    )
    return [AlertResponse.model_validate(a) for a in rows.scalars().all()]


@router.post("/alerts", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreateRequest, user: CurrentUser, session: SessionDep):
    count = (
        await session.execute(select(func.count(JobAlert.id)).where(JobAlert.user_id == user.id))
    ).scalar_one()
    if count >= MAX_ALERTS_PER_USER:
        raise ConflictError(
            f"You can have at most {MAX_ALERTS_PER_USER} alerts. Delete one to create another."
        )

    alert = JobAlert(
        user_id=user.id,
        name=payload.name,
        keywords=payload.keywords,
        cities=payload.cities,
        provinces=payload.provinces,
        categories=payload.categories,
        employment_types=payload.employment_types,
        experience_levels=payload.experience_levels,
        remote_only=payload.remote_only,
        government_only=payload.government_only,
        internship_only=payload.internship_only,
        salary_min=payload.salary_min,
        frequency=payload.frequency,
        channels=[NotificationChannel.EMAIL.value],
    )
    session.add(alert)
    await session.flush()
    await record_event(
        session, AnalyticsEventType.ALERT_CREATED, user_id=user.id,
        entity_type="alert", entity_id=str(alert.id),
        properties={"frequency": payload.frequency, "remote_only": payload.remote_only},
    )
    return AlertResponse.model_validate(alert)


@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: uuid.UUID, payload: AlertUpdateRequest, user: CurrentUser, session: SessionDep
):
    alert = await _owned_alert(session, user.id, alert_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None or field in ("keywords", "salary_min"):
            setattr(alert, field, value)
    await session.flush()
    return AlertResponse.model_validate(alert)


@router.delete("/alerts/{alert_id}", response_model=MessageResponse)
async def delete_alert(alert_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    alert = await _owned_alert(session, user.id, alert_id)
    await session.execute(delete(JobAlert).where(JobAlert.id == alert.id))
    return MessageResponse(message="Alert deleted.")


@router.post("/alerts/{alert_id}/preview")
async def preview_alert(alert_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    """Shows what the alert would match right now — no notification is sent."""
    from sqlalchemy import and_
    from sqlalchemy.orm import selectinload

    from pakjobs_core.models import Job, JobSkill

    from app.services.job_serializer import to_list_items

    alert = await _owned_alert(session, user.id, alert_id)
    conditions = _preview_conditions(alert)
    rows = await session.execute(
        select(Job)
        .options(selectinload(Job.skills).selectinload(JobSkill.skill))
        .where(and_(*conditions))
        .order_by(Job.posted_at.desc().nullslast())
        .limit(10)
    )
    jobs = list(rows.unique().scalars().all())
    return {"count": len(jobs), "items": to_list_items(jobs, profile=user.profile)}


def _preview_conditions(alert: JobAlert):
    """Same criteria as the worker's matcher, without the "since last run" watermark."""
    from datetime import datetime, timedelta, timezone

    from pakjobs_core.services.alerts import AlertMatchingService

    class _Preview(AlertMatchingService):
        def __init__(self):  # no session needed for condition building
            pass

    since = datetime.now(timezone.utc) - timedelta(days=30)
    return _Preview()._conditions(alert, since)


class UnsubscribeRequest(BaseModel):
    alert: uuid.UUID
    token: str = Field(..., min_length=8, max_length=128)


@router.post("/alerts/unsubscribe", response_model=MessageResponse)
async def unsubscribe_alert(payload: UnsubscribeRequest, session: SessionDep):
    """One-click unsubscribe from an email link — deliberately unauthenticated.

    The signed token proves the request came from a message we sent, so a recipient can stop the
    mail without signing in. Bulk senders without a working one-click unsubscribe get filtered as
    spam, and requiring a login to stop email is user-hostile.

    The response is identical whether or not the alert exists, so the endpoint cannot be used to
    probe for valid alert ids.
    """
    done = MessageResponse(message="You will no longer receive emails for this alert.")

    if not verify_unsubscribe(str(payload.alert), payload.token):
        raise NotFoundError("This unsubscribe link is not valid.")

    alert = (
        await session.execute(select(JobAlert).where(JobAlert.id == payload.alert))
    ).scalar_one_or_none()
    if alert is None:
        return done

    alert.is_active = False
    logger.info("alert.unsubscribed", alert_id=str(alert.id))
    return done


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    user: CurrentUser, session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 20
):
    rows = await session.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return [NotificationResponse.model_validate(n) for n in rows.scalars().all()]


@router.post("/notifications/{notification_id}/read", response_model=MessageResponse)
async def mark_notification_read(notification_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    from datetime import datetime, timezone

    notification = (
        await session.execute(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if notification is None:
        raise NotFoundError("Notification not found.")
    notification.read_at = datetime.now(timezone.utc)
    notification.status = NotificationStatus.READ
    await record_event(
        session, AnalyticsEventType.ALERT_OPENED, user_id=user.id,
        entity_type="notification", entity_id=str(notification_id),
    )
    return MessageResponse(message="Marked as read.")


async def _owned_alert(session, user_id: uuid.UUID, alert_id: uuid.UUID) -> JobAlert:
    alert = (
        await session.execute(
            select(JobAlert).where(JobAlert.id == alert_id, JobAlert.user_id == user_id)
        )
    ).scalar_one_or_none()
    if alert is None:
        raise NotFoundError("Alert not found.")
    return alert
