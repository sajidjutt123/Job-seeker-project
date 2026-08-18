"""User profile management."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from pakjobs_core.models import Profile
from pakjobs_core.pipeline.normalizer import normalize_skill_list
from pakjobs_core.services.profile import compute_profile_completion, next_profile_steps

from app.core.deps import CurrentUser, SessionDep
from app.schemas.auth import ProfileResponse, ProfileUpdateRequest

router = APIRouter(prefix="/profile", tags=["profile"])


async def _get_or_create_profile(session, user) -> Profile:
    profile = (
        await session.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        session.add(profile)
        await session.flush()
    return profile


def _serialize(profile: Profile) -> ProfileResponse:
    response = ProfileResponse.model_validate(profile)
    response.next_steps = next_profile_steps(profile)
    return response


@router.get("", response_model=ProfileResponse)
async def get_profile(user: CurrentUser, session: SessionDep):
    return _serialize(await _get_or_create_profile(session, user))


@router.put("", response_model=ProfileResponse)
async def update_profile(payload: ProfileUpdateRequest, user: CurrentUser, session: SessionDep):
    profile = await _get_or_create_profile(session, user)

    data = payload.model_dump(exclude_unset=True)
    if "skills" in data and data["skills"] is not None:
        data["skills"] = normalize_skill_list(data["skills"])
    # Keep the salary range coherent regardless of the order fields arrive in.
    if data.get("expected_salary_min") and data.get("expected_salary_max"):
        if data["expected_salary_min"] > data["expected_salary_max"]:
            data["expected_salary_min"], data["expected_salary_max"] = (
                data["expected_salary_max"], data["expected_salary_min"],
            )

    for field, value in data.items():
        setattr(profile, field, value)

    # Derive province from city so location filters work without asking twice.
    if profile.city and not profile.province:
        from pakjobs_core.domain.locations import CITY_LOOKUP
        from pakjobs_core.pipeline.text import normalize_text

        city = CITY_LOOKUP.get(normalize_text(profile.city))
        if city:
            profile.province = city.province

    profile.profile_completion = compute_profile_completion(profile)
    await session.flush()
    return _serialize(profile)
