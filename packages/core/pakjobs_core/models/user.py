from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pakjobs_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from pakjobs_core.domain.enums import UserRole, UserStatus

if TYPE_CHECKING:
    from pakjobs_core.models.alert import JobAlert
    from pakjobs_core.models.job import SavedJob


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    # Null for OAuth-only accounts; never expose through the API.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.USER, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=UserStatus.PENDING_VERIFICATION, nullable=False, index=True
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Bumped on password change / global logout to invalidate outstanding refresh tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    saved_jobs: Mapped[list["SavedJob"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alerts: Mapped[list["JobAlert"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_active(self) -> bool:
        return self.status in (UserStatus.ACTIVE, UserStatus.PENDING_VERIFICATION)


class Profile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(String(160))
    headline: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    province: Mapped[str | None] = mapped_column(String(120))
    education_level: Mapped[str | None] = mapped_column(String(80))
    degree: Mapped[str | None] = mapped_column(String(160))
    institution: Mapped[str | None] = mapped_column(String(200))
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    years_of_experience: Mapped[int | None] = mapped_column(Integer)
    experience_level: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[str | None] = mapped_column(Text)

    skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_locations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_categories: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_job_types: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    expected_salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    expected_salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str] = mapped_column(String(8), default="PKR", nullable=False)
    remote_preference: Mapped[str | None] = mapped_column(String(20))
    open_to_relocation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cv_object_key: Mapped[str | None] = mapped_column(String(500))
    profile_completion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped["User"] = relationship(back_populates="profile")


class RefreshToken(Base, UUIDPrimaryKeyMixin):
    """Server-side refresh token registry so sessions can be revoked."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_expires", "user_id", "expires_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class VerificationToken(Base, UUIDPrimaryKeyMixin):
    """Single-use tokens for email verification and password reset (hashed at rest)."""

    __tablename__ = "verification_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_verification_tokens_token_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)  # email_verify | password_reset
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class AdminAuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable trail of privileged actions."""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (Index("ix_admin_audit_logs_created", "created_at"),)

    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
