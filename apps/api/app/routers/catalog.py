"""Reference data: categories, cities, provinces, sources, skills.

Drives filter panels and SEO landing pages. Cheap, cacheable, no authentication.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from pakjobs_core.domain.enums import (
    CATEGORY_LABELS,
    EmploymentType,
    ExperienceLevel,
    JobCategorySlug,
    JobStatus,
)
from pakjobs_core.domain.locations import CITIES, PROVINCES
from pakjobs_core.models import Job, JobSource, Skill

router = APIRouter(tags=["catalog"])

CACHE_HEADER = "public, max-age=300, stale-while-revalidate=600"


@router.get("/categories")
async def list_categories(response: Response, session=None):
    """Static category vocabulary (counts come from /jobs/facets to keep this cacheable)."""
    response.headers["Cache-Control"] = CACHE_HEADER
    return [
        {"slug": slug.value, "label": CATEGORY_LABELS[slug.value]}
        for slug in JobCategorySlug
    ]


@router.get("/cities")
async def list_cities(response: Response, major_only: Annotated[bool, Query()] = False):
    response.headers["Cache-Control"] = CACHE_HEADER
    cities = [c for c in CITIES if c.is_major] if major_only else list(CITIES)
    return [
        {"name": c.name, "slug": c.slug, "province": c.province, "is_major": c.is_major}
        for c in cities
    ]


@router.get("/provinces")
async def list_provinces(response: Response):
    response.headers["Cache-Control"] = CACHE_HEADER
    return [{"name": p} for p in PROVINCES]


@router.get("/filters")
async def filter_options(response: Response):
    """Everything the search filter panel needs in one request."""
    response.headers["Cache-Control"] = CACHE_HEADER
    return {
        "categories": [{"value": s.value, "label": CATEGORY_LABELS[s.value]} for s in JobCategorySlug],
        "employment_types": [
            {"value": e.value, "label": e.value.replace("_", " ").title()}
            for e in EmploymentType if e != EmploymentType.UNKNOWN
        ],
        "experience_levels": [
            {"value": e.value, "label": e.value.replace("_", " ").title()}
            for e in ExperienceLevel if e != ExperienceLevel.UNKNOWN
        ],
        "provinces": [{"value": p, "label": p} for p in PROVINCES],
        "cities": [{"value": c.slug, "label": c.name, "province": c.province} for c in CITIES],
        "education_levels": [
            {"value": v, "label": l} for v, l in [
                ("matric", "Matric"), ("intermediate", "Intermediate"), ("diploma", "Diploma"),
                ("bachelors", "Bachelors"), ("masters", "Masters"), ("phd", "PhD"),
            ]
        ],
        "date_posted": [
            {"value": 1, "label": "Last 24 hours"}, {"value": 3, "label": "Last 3 days"},
            {"value": 7, "label": "Last week"}, {"value": 30, "label": "Last month"},
        ],
        "sort_options": [
            {"value": "newest", "label": "Newest"},
            {"value": "relevance", "label": "Most relevant"},
            {"value": "deadline", "label": "Closing soon"},
            {"value": "salary", "label": "Highest salary"},
        ],
    }


@router.get("/sources")
async def list_public_sources(response: Response, session=None):
    """Public attribution page: which sources this platform aggregates from."""
    from pakjobs_core.db.session import AsyncSessionLocal

    response.headers["Cache-Control"] = CACHE_HEADER
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(
                JobSource.name,
                JobSource.slug,
                JobSource.type,
                JobSource.website_url,
                JobSource.attribution_label,
                func.count(Job.id).filter(Job.status == JobStatus.ACTIVE),
            )
            .outerjoin(Job, Job.source_id == JobSource.id)
            .where(JobSource.enabled.is_(True), JobSource.is_seed.is_(False))
            .group_by(
                JobSource.name, JobSource.slug, JobSource.type,
                JobSource.website_url, JobSource.attribution_label,
            )
            .order_by(func.count(Job.id).desc())
        )
        return [
            {
                "name": name, "slug": slug, "type": type_, "website_url": website,
                "label": label or name, "active_jobs": count,
            }
            for name, slug, type_, website, label, count in rows.all()
        ]


@router.get("/skills")
async def list_skills(
    response: Response,
    q: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
):
    """Skill autocomplete, ranked by how often the skill appears in live jobs."""
    from pakjobs_core.db.session import AsyncSessionLocal

    response.headers["Cache-Control"] = CACHE_HEADER
    async with AsyncSessionLocal() as db:
        stmt = select(Skill.name, Skill.slug, Skill.usage_count).order_by(Skill.usage_count.desc())
        if q:
            stmt = stmt.where(Skill.name.ilike(f"%{q}%"))
        rows = await db.execute(stmt.limit(limit))
        return [{"name": n, "slug": s, "count": c} for n, s, c in rows.all()]
