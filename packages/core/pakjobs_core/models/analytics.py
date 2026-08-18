from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pakjobs_core.db.base import Base, UUIDPrimaryKeyMixin


class SearchLog(Base, UUIDPrimaryKeyMixin):
    """Aggregate-friendly search telemetry. No IPs or raw user agents are stored."""

    __tablename__ = "search_logs"
    __table_args__ = (Index("ix_search_logs_created", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    query: Mapped[str | None] = mapped_column(String(300), index=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class AnalyticsEvent(Base, UUIDPrimaryKeyMixin):
    """Product events. Deliberately minimal PII: user id (optional) + anonymous session hash."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_type_created", "event_type", "created_at"),
        Index("ix_analytics_events_entity", "entity_type", "entity_id"),
    )

    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    anon_id: Mapped[str | None] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
