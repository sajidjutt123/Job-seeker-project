"""Pipeline data contracts.

`RawJob` is what a connector emits (source-shaped, untrusted).
`NormalizedJob` is the canonical internal record every downstream stage consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pakjobs_core.domain.enums import EmploymentType, ExperienceLevel, JobStatus, WorkMode


@dataclass(slots=True)
class RawJob:
    """Untouched payload from a source, plus whatever the connector could map cheaply."""

    source_job_id: str
    title: str
    apply_url: str
    raw: dict[str, Any] = field(default_factory=dict)

    company_name: str | None = None
    company_website: str | None = None
    company_logo: str | None = None
    description_html: str | None = None
    description_text: str | None = None
    location_raw: str | None = None
    employment_type_raw: str | None = None
    experience_raw: str | None = None
    category_hint: str | None = None
    salary_raw: str | None = None
    salary_min: float | str | None = None
    salary_max: float | str | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    posted_at_raw: Any = None
    deadline_raw: Any = None
    source_url: str | None = None
    tags: list[str] = field(default_factory=list)
    is_remote_hint: bool | None = None


@dataclass(slots=True)
class NormalizedJob:
    """Canonical representation persisted by the repository layer."""

    source_job_id: str
    title: str
    normalized_title: str
    apply_url: str

    company_name: str | None = None
    company_key: str | None = None
    company_website: str | None = None
    company_logo: str | None = None

    description: str = ""
    normalized_description: str = ""
    responsibilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)

    location_raw: str | None = None
    location: str | None = None
    city: str | None = None
    city_slug: str | None = None
    province: str | None = None
    country: str = "PK"
    work_mode: str = WorkMode.UNKNOWN
    is_remote: bool = False

    employment_type: str = EmploymentType.UNKNOWN
    experience_level: str = ExperienceLevel.UNKNOWN
    category: str = "other"
    secondary_categories: list[str] = field(default_factory=list)
    is_internship: bool = False
    is_government: bool = False
    is_fresh_graduate_friendly: bool = False
    education_requirement: str | None = None
    classification_confidence: float = 0.0
    classification_method: str = "rules"

    skills: list[str] = field(default_factory=list)

    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None

    posted_at: datetime | None = None
    deadline: datetime | None = None
    status: str = JobStatus.ACTIVE

    source_url: str | None = None
    apply_url_hash: str | None = None
    content_fingerprint: str | None = None
    quality_score: float = 0.0
    quality_breakdown: dict[str, Any] = field(default_factory=dict)

    raw_payload: dict[str, Any] = field(default_factory=dict)
    validation_warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourceMetadata:
    """Static self-description a connector publishes to the registry and admin UI."""

    key: str
    name: str
    type: str
    website: str | None = None
    attribution_label: str | None = None
    description: str = ""
    requires_credentials: bool = False
    credential_env_keys: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    default_fetch_interval_minutes: int = 60
    default_reliability: float = 0.7
    terms_url: str | None = None
    legal_note: str = ""
    is_seed: bool = False


@dataclass(slots=True)
class FetchResult:
    """Outcome of one connector fetch — never raises past the pipeline boundary."""

    jobs: list[RawJob] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    error_type: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    partial: bool = False
