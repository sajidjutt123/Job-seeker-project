from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pakjobs_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from pakjobs_core.domain.enums import (
    EmploymentType,
    ExperienceLevel,
    JobOrigin,
    JobStatus,
    WorkMode,
)

if TYPE_CHECKING:
    from pakjobs_core.models.company import Company
    from pakjobs_core.models.source import JobSource
    from pakjobs_core.models.user import User


class JobCategory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "job_categories"

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    active_job_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Skill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "skills"

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_jobs_source_id_source_job_id"),
        Index("ix_jobs_status_posted", "status", "posted_at"),
        Index("ix_jobs_city_status", "city", "status"),
        Index("ix_jobs_category_status", "category", "status"),
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_jobs_fingerprint", "content_fingerprint"),
        Index("ix_jobs_status_quality", "status", "quality_score"),
        Index("ix_jobs_apply_url_hash", "apply_url_hash"),
    )

    # --- provenance ---
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_sources.id", ondelete="SET NULL"), index=True
    )
    source_job_id: Mapped[str | None] = mapped_column(String(255), index=True)
    origin: Mapped[str] = mapped_column(String(20), default=JobOrigin.AGGREGATED, nullable=False, index=True)
    posted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_name_raw: Mapped[str | None] = mapped_column(String(300))

    # --- content ---
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(460), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    responsibilities: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    requirements: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    benefits: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    # --- location ---
    location_raw: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    city_slug: Mapped[str | None] = mapped_column(String(140), index=True)
    province: Mapped[str | None] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(8), default="PK", nullable=False, index=True)
    work_mode: Mapped[str] = mapped_column(String(20), default=WorkMode.UNKNOWN, nullable=False, index=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # --- classification ---
    employment_type: Mapped[str] = mapped_column(
        String(30), default=EmploymentType.UNKNOWN, nullable=False, index=True
    )
    experience_level: Mapped[str] = mapped_column(
        String(30), default=ExperienceLevel.UNKNOWN, nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(80), default="other", nullable=False, index=True)
    secondary_categories: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_internship: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_government: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_fresh_graduate_friendly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    education_requirement: Mapped[str | None] = mapped_column(String(80), index=True)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    classification_method: Mapped[str] = mapped_column(String(30), default="rules", nullable=False)

    # --- compensation ---
    salary_min: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(16))  # month | year | hour
    salary_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- lifecycle ---
    status: Mapped[str] = mapped_column(String(30), default=JobStatus.ACTIVE, nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apply_url_ok: Mapped[bool | None] = mapped_column(Boolean)

    # --- links ---
    apply_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    apply_url_hash: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(2000))

    # --- quality / dedupe ---
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    quality_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    canonical_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- moderation / monetization ---
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_sponsored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    featured_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    admin_note: Mapped[str | None] = mapped_column(Text)
    report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- metrics ---
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    apply_click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    save_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Postgres full-text index. Generated column => always in sync, no trigger to maintain.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(company_name_raw, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(city, '') || ' ' || coalesce(province, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(normalized_description, '')), 'C')",
            persisted=True,
        ),
    )

    source: Mapped["JobSource | None"] = relationship(back_populates="jobs", lazy="joined")
    company: Mapped["Company | None"] = relationship(back_populates="jobs", lazy="joined")
    skills: Mapped[list["JobSkill"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    events: Mapped[list["JobEvent"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    @property
    def is_open(self) -> bool:
        return self.status == JobStatus.ACTIVE and not self.hidden_by_admin


class JobSkill(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id", name="uq_job_skills_job_id_skill_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship(lazy="joined")


class JobLocation(Base, UUIDPrimaryKeyMixin):
    """Secondary locations for multi-city postings (primary stays denormalized on `jobs`)."""

    __tablename__ = "job_locations"
    __table_args__ = (UniqueConstraint("job_id", "city_slug", name="uq_job_locations_job_id_city_slug"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    city: Mapped[str | None] = mapped_column(String(120))
    city_slug: Mapped[str | None] = mapped_column(String(140), index=True)
    province: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(8), default="PK", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class JobDuplicate(Base, UUIDPrimaryKeyMixin):
    """Recorded link between a canonical job and a duplicate found on another source."""

    __tablename__ = "job_duplicates"
    __table_args__ = (
        UniqueConstraint("canonical_job_id", "duplicate_job_id", name="uq_job_duplicates_pair"),
        Index("ix_job_duplicates_confidence", "confidence"),
    )

    canonical_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    duplicate_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    method: Mapped[str] = mapped_column(String(40), default="heuristic", nullable=False)
    reviewed_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class JobEvent(Base, UUIDPrimaryKeyMixin):
    """Append-only lifecycle history for a job."""

    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    job: Mapped["Job"] = relationship(back_populates="events")


class SavedJob(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_jobs_user_id_job_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    folder: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    user: Mapped["User"] = relationship(back_populates="saved_jobs")
    job: Mapped["Job"] = relationship(lazy="joined")


class JobReport(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_status_created", "status", "created_at"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(Text)
    reporter_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    job: Mapped["Job"] = relationship(lazy="joined")


class JobViewDaily(Base, UUIDPrimaryKeyMixin):
    """Pre-aggregated per-day counters (avoids scanning raw analytics for dashboards)."""

    __tablename__ = "job_view_daily"
    __table_args__ = (UniqueConstraint("job_id", "day", name="uq_job_view_daily_job_id_day"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    apply_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
