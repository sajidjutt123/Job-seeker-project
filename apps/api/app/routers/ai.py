"""AI-assisted endpoints.

Every route degrades gracefully: when AI is disabled or failing, the deterministic fallback is
returned with `used_ai: false`. The frontend labels AI output accordingly.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pakjobs_core.config import settings
from pakjobs_core.models import Job, JobSkill
from pakjobs_core.services.ai import AICareerAssistant, AIJobSummary, get_ai_provider

from app.core.deps import CurrentUser, OptionalUser, SessionDep
from app.core.errors import NotFoundError

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
async def ai_status():
    """Lets the UI hide AI features instead of showing broken buttons."""
    provider = get_ai_provider()
    return {
        "enabled": settings.ai_enabled and provider.available,
        "provider": provider.name,
        "features": {
            "job_summary": provider.available,
            "career_assistant": provider.available,
            "skill_extraction": True,   # rules fallback always works
            "classification": True,     # rules fallback always works
        },
    }


@router.get("/jobs/{job_id}/summary")
async def job_summary(job_id: uuid.UUID, session: SessionDep, user: OptionalUser):
    job = (
        await session.execute(
            select(Job).options(selectinload(Job.skills).selectinload(JobSkill.skill)).where(Job.id == job_id)
        )
    ).unique().scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found.")

    result = await AIJobSummary().summarize(
        title=job.title, description=job.description, company=job.company_name_raw
    )
    return {"summary": result.value, "used_ai": result.used_ai, "provider": result.provider}


class AssistantRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    context: str | None = Field(default=None, max_length=2000)


@router.post("/assistant")
async def career_assistant(payload: AssistantRequest, user: CurrentUser):
    """Signed-in only: keeps AI spend attributable and rate-limitable per account."""
    result = await AICareerAssistant().ask(payload.question, context=payload.context)
    return {"answer": result.value, "used_ai": result.used_ai, "provider": result.provider,
            "note": result.note}
