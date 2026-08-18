from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pakjobs_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from pakjobs_core.models.job import Job


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    # Normalized key ("abc technologies" -> "abc") used to merge the same employer across sources.
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(260), nullable=False, unique=True, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(160), index=True)
    size: Mapped[str | None] = mapped_column(String(60))
    headquarters_city: Mapped[str | None] = mapped_column(String(120))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active_job_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")
