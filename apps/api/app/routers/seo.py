"""SEO support endpoints: sitemap data and JSON-LD structured data.

The Next.js app consumes these to generate `sitemap.xml` and JobPosting structured data.
Only real, indexable content is exposed — no mass-generated thin pages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from pakjobs_core.config import settings
from pakjobs_core.domain.enums import JobStatus
from pakjobs_core.models import Job

from app.core.deps import SessionDep
from app.core.errors import NotFoundError

router = APIRouter(prefix="/seo", tags=["seo"])

# Only surface landing pages that have enough real inventory to be useful.
MIN_JOBS_FOR_LANDING_PAGE = 3


@router.get("/sitemap")
async def sitemap_data(
    response: Response,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=20000)] = 5000,
):
    response.headers["Cache-Control"] = "public, max-age=3600"

    job_rows = await session.execute(
        select(Job.slug, Job.updated_at, Job.posted_at)
        .where(Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True), Job.hidden_by_admin.is_(False))
        .order_by(Job.posted_at.desc().nullslast())
        .limit(limit)
    )
    jobs = [
        {"slug": slug, "lastmod": (updated or posted or datetime.now(timezone.utc)).isoformat()}
        for slug, updated, posted in job_rows.all()
    ]

    city_rows = await session.execute(
        select(Job.city_slug, func.count(Job.id))
        .where(
            Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True),
            Job.hidden_by_admin.is_(False), Job.city_slug.isnot(None),
        )
        .group_by(Job.city_slug)
        .having(func.count(Job.id) >= MIN_JOBS_FOR_LANDING_PAGE)
    )
    category_rows = await session.execute(
        select(Job.category, func.count(Job.id))
        .where(Job.status == JobStatus.ACTIVE, Job.is_canonical.is_(True), Job.hidden_by_admin.is_(False))
        .group_by(Job.category)
        .having(func.count(Job.id) >= MIN_JOBS_FOR_LANDING_PAGE)
    )

    return {
        "site_url": settings.web_base_url,
        "jobs": jobs,
        "cities": [{"slug": slug, "count": count} for slug, count in city_rows.all()],
        "categories": [{"slug": slug, "count": count} for slug, count in category_rows.all()],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/jobs/{slug}/structured-data")
async def job_structured_data(slug: str, session: SessionDep):
    """schema.org JobPosting JSON-LD for a single job."""
    job = (
        await session.execute(select(Job).where(Job.slug == slug))
    ).unique().scalar_one_or_none()
    if job is None or job.hidden_by_admin or job.status == JobStatus.REMOVED:
        raise NotFoundError("Job not found.")

    data: dict = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job.title,
        "description": (job.description or job.title)[:5000],
        "identifier": {"@type": "PropertyValue", "name": "RozgarPK", "value": str(job.id)},
        "datePosted": (job.posted_at or job.created_at).isoformat(),
        "employmentType": _employment_type(job.employment_type),
        "hiringOrganization": {
            "@type": "Organization",
            "name": job.company_name_raw or "Not disclosed",
            **({"sameAs": job.company.website} if job.company and job.company.website else {}),
            **({"logo": job.company.logo_url} if job.company and job.company.logo_url else {}),
        },
        "directApply": False,  # applications complete on the original source
        "url": f"{settings.web_base_url}/jobs/{job.slug}",
    }

    if job.deadline:
        data["validThrough"] = job.deadline.isoformat()

    if job.is_remote:
        data["jobLocationType"] = "TELECOMMUTE"
        data["applicantLocationRequirements"] = {"@type": "Country", "name": "Pakistan"}
    if job.city:
        data["jobLocation"] = {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": job.city,
                "addressRegion": job.province,
                "addressCountry": "PK",
            },
        }

    if job.salary_min or job.salary_max:
        value: dict = {"@type": "QuantitativeValue", "unitText": _unit(job.salary_period)}
        if job.salary_min and job.salary_max:
            value["minValue"] = float(job.salary_min)
            value["maxValue"] = float(job.salary_max)
        else:
            value["value"] = float(job.salary_min or job.salary_max)
        data["baseSalary"] = {
            "@type": "MonetaryAmount", "currency": job.salary_currency or "PKR", "value": value,
        }

    return data


def _employment_type(value: str) -> str:
    return {
        "full_time": "FULL_TIME", "part_time": "PART_TIME", "contract": "CONTRACTOR",
        "temporary": "TEMPORARY", "internship": "INTERN", "freelance": "CONTRACTOR",
        "volunteer": "VOLUNTEER",
    }.get(value, "OTHER")


def _unit(period: str | None) -> str:
    return {"hour": "HOUR", "day": "DAY", "week": "WEEK", "month": "MONTH", "year": "YEAR"}.get(
        period or "month", "MONTH"
    )
