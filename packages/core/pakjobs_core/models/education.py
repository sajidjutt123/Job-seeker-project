"""Education-ecosystem tables.

Deliberately schema-only for v1: the tables exist so admissions/scholarships/courses can be
built later without a disruptive migration, but no API surface is exposed yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pakjobs_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Institution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Universities, colleges and training providers."""

    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(40), default="university", nullable=False)
    sector: Mapped[str | None] = mapped_column(String(40))  # public | private
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    province: Mapped[str | None] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(600))
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    accreditation: Mapped[str | None] = mapped_column(String(200))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Campus(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "campuses"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    province: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)


class Program(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "programs"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campus_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campuses.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    level: Mapped[str | None] = mapped_column(String(60))  # bachelors | masters | phd | diploma
    field: Mapped[str | None] = mapped_column(String(160), index=True)
    duration_years: Mapped[float | None] = mapped_column(Numeric(4, 2))
    fee_per_semester: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="PKR", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class AdmissionCycle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admission_cycles"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    apply_url: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)


class Scholarship(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scholarships"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(240))
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL")
    )
    level: Mapped[str | None] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(8), default="PK", nullable=False)
    amount: Mapped[str | None] = mapped_column(String(160))
    eligibility: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    apply_url: Mapped[str | None] = mapped_column(String(2000))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)


class Course(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "courses"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(240))
    format: Mapped[str | None] = mapped_column(String(40))  # online | onsite | hybrid
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="PKR", nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))
    certification_offered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
