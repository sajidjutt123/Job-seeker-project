"""Client-side analytics ingestion (minimal, privacy-conscious)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.deps import OptionalUser, SessionDep
from app.schemas.common import AnalyticsEventRequest, MessageResponse
from app.services.analytics_service import record_event

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/events", response_model=MessageResponse)
async def track_event(
    payload: AnalyticsEventRequest, request: Request, session: SessionDep, user: OptionalUser
):
    from app.routers.jobs import _anon_id

    await record_event(
        session,
        payload.event_type,
        user_id=user.id if user else None,
        anon_id=_anon_id(request),
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        properties=payload.properties,
    )
    return MessageResponse(message="Recorded.")
