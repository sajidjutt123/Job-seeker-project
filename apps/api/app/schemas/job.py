"""Pydantic response/request models for jobs.

These are the API contract. ORM internals (raw payloads, quality breakdowns, source configs)
never leak: quality score is admin-only, raw payloads are never serialised.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pakjobs_core.domain.enums import CATEGORY_LABELS


class SourceBadge(BaseModel):
    """Attribution shown on every job card and detail page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    name: str
    slug: str | None = None
    label: str | None = None
    website_url: str | None = None
    type: str | None = None


class CompanySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None = None
    website: str | None = None
    industry: str | None = None
    verified: bool = False


class SalaryRange(BaseModel):
    min: Decimal | None = None
    max: Decimal | None = None
    currency: str | None = None
    period: str | None = None

    @property
    def is_disclosed(self) -> bool:
        return self.min is not None or self.max is not None


class JobListItem(BaseModel):
    """Compact shape used by search results, feeds and saved lists."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    company_name: str | None = None
    company: CompanySummary | None = None
    location: str | None = None
    city: str | None = None
    province: str | None = None
    country: str = "PK"
    is_remote: bool = False
    work_mode: str = "unknown"
    employment_type: str = "unknown"
    experience_level: str = "unknown"
    category: str = "other"
    category_label: str | None = None
    is_internship: bool = False
    is_government: bool = False
    is_fresh_graduate_friendly: bool = False
    is_featured: bool = False
    salary: SalaryRange | None = None
    posted_at: datetime | None = None
    deadline: datetime | None = None
    status: str = "active"
    source: SourceBadge | None = None
    apply_url: str
    skills: list[str] = Field(default_factory=list)
    # Present only for authenticated users
    match_score: float | None = None
    match_reasons: list[str] = Field(default_factory=list)
    is_saved: bool | None = None


class JobDetail(JobListItem):
    """Full record for the job detail page."""

    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    education_requirement: str | None = None
    source_url: str | None = None
    origin: str = "aggregated"
    view_count: int = 0
    duplicate_count: int = 0
    other_sources: list[SourceBadge] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobAdminDetail(JobDetail):
    """Adds internal-only signals. Served exclusively on admin routes."""

    quality_score: float = 0.0
    quality_breakdown: dict[str, Any] = Field(default_factory=dict)
    classification_confidence: float = 0.0
    classification_method: str = "rules"
    source_job_id: str | None = None
    content_fingerprint: str | None = None
    canonical_job_id: uuid.UUID | None = None
    is_canonical: bool = True
    hidden_by_admin: bool = False
    admin_note: str | None = None
    report_count: int = 0
    apply_url_ok: bool | None = None
    last_seen_at: datetime | None = None
    last_checked_at: datetime | None = None


class Facet(BaseModel):
    value: str
    count: int
    label: str | None = None


class JobSearchResponse(BaseModel):
    items: list[JobListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    took_ms: int = 0
    facets: dict[str, list[Facet]] = Field(default_factory=dict)


class SaveJobRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    folder: str | None = Field(default=None, max_length=80)


class SavedJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job: JobListItem
    note: str | None = None
    folder: str | None = None
    created_at: datetime


class ReportJobRequest(BaseModel):
    reason: str = Field(..., max_length=40)
    details: str | None = Field(default=None, max_length=2000)
    reporter_email: str | None = Field(default=None, max_length=320)

    @field_validator("reason")
    @classmethod
    def _valid_reason(cls, value: str) -> str:
        from pakjobs_core.domain.enums import ReportReason

        allowed = {r.value for r in ReportReason}
        if value not in allowed:
            raise ValueError(f"reason must be one of: {', '.join(sorted(allowed))}")
        return value


def category_label(slug: str | None) -> str | None:
    if not slug:
        return None
    return CATEGORY_LABELS.get(slug, slug.replace("-", " ").title())
