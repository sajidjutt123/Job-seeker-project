from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pakjobs_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from pakjobs_core.domain.enums import AlertFrequency, NotificationChannel, NotificationStatus

if TYPE_CHECKING:
    from pakjobs_core.models.user import User


class JobAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "job_alerts"
    __table_args__ = (Index("ix_job_alerts_active_frequency", "is_active", "frequency"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)

    # Criteria — mirrors the search API so an alert is a saved search.
    keywords: Mapped[str | None] = mapped_column(String(300))
    cities: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    provinces: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    employment_types: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    experience_levels: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    remote_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    government_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    internship_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    salary_min: Mapped[float | None] = mapped_column(Numeric(14, 2))

    frequency: Mapped[str] = mapped_column(String(20), default=AlertFrequency.DAILY, nullable=False)
    channels: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: [NotificationChannel.EMAIL.value], nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Watermark: only jobs created after this are considered, preventing duplicate notifications.
    last_job_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="alerts")


class AlertMatch(Base, UUIDPrimaryKeyMixin):
    """Which jobs were already delivered for which alert (idempotency guard)."""

    __tablename__ = "alert_matches"
    __table_args__ = (
        Index("ix_alert_matches_alert_job", "alert_id", "job_id", unique=True),
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Numeric(6, 3), default=0, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class Notification(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default=NotificationChannel.EMAIL, nullable=False)
    type: Mapped[str] = mapped_column(String(40), default="job_alert", nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=NotificationStatus.PENDING, nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
