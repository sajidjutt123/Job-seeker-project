from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pakjobs_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from pakjobs_core.domain.enums import SourceRunStatus, SourceStatus, SourceType

if TYPE_CHECKING:
    from pakjobs_core.models.job import Job


class JobSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Admin-managed registry row. One row per configured source instance.

    `connector_key` selects the code adapter; `config` holds per-instance settings
    (board token, feed URL, query, ...). Secrets are referenced by env var name in
    `credential_env_keys`, never stored here.
    """

    __tablename__ = "job_sources"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(40), default=SourceType.API, nullable=False, index=True)
    connector_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    website_url: Mapped[str | None] = mapped_column(String(600))
    attribution_label: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)  # 1 = highest
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credential_env_keys: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    status: Mapped[str] = mapped_column(String(40), default=SourceStatus.UNKNOWN, nullable=False, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_jobs_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    jobs: Mapped[list["Job"]] = relationship(back_populates="source")
    runs: Mapped[list["SourceRun"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", order_by="SourceRun.started_at.desc()"
    )

    @property
    def due_for_run(self) -> bool:
        if not self.enabled:
            return False
        if self.last_run_at is None:
            return True
        from datetime import timedelta, timezone

        return datetime.now(timezone.utc) - self.last_run_at >= timedelta(minutes=self.fetch_interval_minutes)


class SourceRun(Base, UUIDPrimaryKeyMixin):
    """One ingestion execution: full observability record for a fetch."""

    __tablename__ = "source_runs"
    __table_args__ = (Index("ix_source_runs_source_started", "source_id", "started_at"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=SourceRunStatus.RUNNING, nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(40), default="scheduler", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(120))
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    source: Mapped["JobSource"] = relationship(back_populates="runs")
