"""Job search service.

`SearchBackend` is an interface. `PostgresSearchBackend` is the v1 implementation using Postgres
full-text search over the generated `jobs.search_vector` column. An OpenSearch backend can be
added later by implementing the same protocol — routers and services never touch SQL directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Protocol, Sequence

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pakjobs_core.domain.enums import JobStatus
from pakjobs_core.models import Job, JobSkill, Skill

SortOption = Literal["newest", "relevance", "deadline", "salary", "quality"]
MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20


@dataclass(slots=True)
class SearchFilters:
    """Every filter is optional; empty filters mean "latest active jobs"."""

    q: str | None = None
    city: str | None = None
    cities: list[str] = field(default_factory=list)
    province: str | None = None
    category: str | None = None
    categories: list[str] = field(default_factory=list)
    employment_type: str | None = None
    employment_types: list[str] = field(default_factory=list)
    experience_level: str | None = None
    experience_levels: list[str] = field(default_factory=list)
    education: str | None = None
    company: str | None = None
    company_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    skills: list[str] = field(default_factory=list)
    remote: bool | None = None
    government: bool | None = None
    internship: bool | None = None
    fresh_graduate: bool | None = None
    featured: bool | None = None
    salary_min: Decimal | int | None = None
    salary_max: Decimal | int | None = None
    posted_within_days: int | None = None
    include_expired: bool = False
    sort: SortOption = "newest"
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def normalized_page_size(self) -> int:
        return max(1, min(self.page_size, MAX_PAGE_SIZE))

    def offset(self) -> int:
        return (max(1, self.page) - 1) * self.normalized_page_size()

    def is_empty_query(self) -> bool:
        return not any(
            [
                self.q, self.city, self.cities, self.province, self.category, self.categories,
                self.employment_type, self.employment_types, self.experience_level,
                self.experience_levels, self.education, self.company, self.company_id,
                self.source_id, self.skills, self.remote, self.government, self.internship,
                self.fresh_graduate, self.salary_min, self.salary_max, self.posted_within_days,
            ]
        )

    def as_log_payload(self) -> dict[str, Any]:
        return {
            k: (str(v) if isinstance(v, (uuid.UUID, Decimal)) else v)
            for k, v in {
                "remote": self.remote, "government": self.government, "internship": self.internship,
                "experience": self.experience_level, "employment_type": self.employment_type,
                "province": self.province, "sort": self.sort, "salary_min": self.salary_min,
                "posted_within_days": self.posted_within_days,
            }.items()
            if v is not None
        }


@dataclass(slots=True)
class SearchResult:
    items: list[Job]
    total: int
    page: int
    page_size: int
    took_ms: int = 0
    facets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        size = max(1, self.page_size)
        return (self.total + size - 1) // size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


class SearchBackend(Protocol):
    async def search(self, session: AsyncSession, filters: SearchFilters, *, with_facets: bool = False) -> SearchResult: ...


class PostgresSearchBackend:
    """Postgres full-text + structured filtering.

    Relevance uses `ts_rank_cd` over the weighted generated tsvector (title A, company/location B,
    description C), blended with recency and quality so good fresh jobs surface first.
    """

    async def search(
        self, session: AsyncSession, filters: SearchFilters, *, with_facets: bool = False
    ) -> SearchResult:
        started = datetime.now(timezone.utc)
        page_size = filters.normalized_page_size()

        base = self._base_conditions(filters)
        query_expr = self._tsquery(filters.q)
        if query_expr is not None:
            base.append(Job.search_vector.op("@@")(query_expr))

        count_stmt = select(func.count(Job.id)).where(and_(*base))
        if filters.skills:
            count_stmt = self._apply_skill_join(count_stmt, filters.skills)
        total = (await session.execute(count_stmt)).scalar_one()

        stmt: Select = (
            select(Job)
            .options(selectinload(Job.skills).selectinload(JobSkill.skill))
            .where(and_(*base))
        )
        if filters.skills:
            stmt = self._apply_skill_join(stmt, filters.skills)
        stmt = self._apply_sort(stmt, filters, query_expr)
        stmt = stmt.offset(filters.offset()).limit(page_size)

        rows = (await session.execute(stmt)).unique().scalars().all()

        facets: dict[str, list[dict[str, Any]]] = {}
        if with_facets:
            facets = await self._facets(session, base, filters)

        took = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return SearchResult(
            items=list(rows), total=total, page=max(1, filters.page), page_size=page_size,
            took_ms=took, facets=facets,
        )

    # --- internals ----------------------------------------------------------
    @staticmethod
    def _tsquery(q: str | None):
        if not q or not q.strip():
            return None
        cleaned = " ".join(q.split())[:200]
        # websearch_to_tsquery is injection-safe and understands quotes / OR / -term.
        return func.websearch_to_tsquery("english", cleaned)

    def _base_conditions(self, f: SearchFilters) -> list[Any]:
        conditions: list[Any] = [Job.hidden_by_admin.is_(False), Job.is_canonical.is_(True)]

        if f.include_expired:
            conditions.append(Job.status.in_([JobStatus.ACTIVE, JobStatus.EXPIRED, JobStatus.CLOSED]))
        else:
            conditions.append(Job.status == JobStatus.ACTIVE)

        cities = [c for c in ([f.city] if f.city else []) + f.cities if c]
        if cities:
            lowered = [c.lower() for c in cities]
            conditions.append(
                or_(func.lower(Job.city_slug).in_(lowered), func.lower(Job.city).in_(lowered))
            )
        if f.province:
            conditions.append(func.lower(Job.province) == f.province.lower())

        categories = [c for c in ([f.category] if f.category else []) + f.categories if c]
        if categories:
            conditions.append(Job.category.in_(categories))

        employment = [e for e in ([f.employment_type] if f.employment_type else []) + f.employment_types if e]
        if employment:
            conditions.append(Job.employment_type.in_(employment))

        experience = [e for e in ([f.experience_level] if f.experience_level else []) + f.experience_levels if e]
        if experience:
            conditions.append(Job.experience_level.in_(experience))

        if f.education:
            conditions.append(Job.education_requirement == f.education)
        if f.company:
            conditions.append(Job.company_name_raw.ilike(f"%{f.company[:80]}%"))
        if f.company_id:
            conditions.append(Job.company_id == f.company_id)
        if f.source_id:
            conditions.append(Job.source_id == f.source_id)
        if f.remote is not None:
            conditions.append(Job.is_remote.is_(f.remote))
        if f.government is not None:
            conditions.append(Job.is_government.is_(f.government))
        if f.internship is not None:
            conditions.append(Job.is_internship.is_(f.internship))
        if f.fresh_graduate is not None:
            conditions.append(Job.is_fresh_graduate_friendly.is_(f.fresh_graduate))
        if f.featured is not None:
            conditions.append(Job.is_featured.is_(f.featured))
        if f.salary_min is not None:
            # Match jobs whose upper bound (or single value) clears the requested floor.
            conditions.append(
                or_(Job.salary_max >= f.salary_min, and_(Job.salary_max.is_(None), Job.salary_min >= f.salary_min))
            )
        if f.salary_max is not None:
            conditions.append(or_(Job.salary_min <= f.salary_max, Job.salary_min.is_(None)))
        if f.posted_within_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=f.posted_within_days)
            conditions.append(Job.posted_at >= cutoff)
        return conditions

    @staticmethod
    def _apply_skill_join(stmt: Select, skills: Sequence[str]) -> Select:
        lowered = [s.lower() for s in skills if s]
        return (
            stmt.join(JobSkill, JobSkill.job_id == Job.id)
            .join(Skill, Skill.id == JobSkill.skill_id)
            .where(func.lower(Skill.slug).in_(lowered) | func.lower(Skill.name).in_(lowered))
            .distinct()
        )

    def _apply_sort(self, stmt: Select, f: SearchFilters, query_expr: Any) -> Select:
        featured_first = Job.is_featured.desc()
        if f.sort == "relevance" and query_expr is not None:
            rank = func.ts_rank_cd(Job.search_vector, query_expr)
            # Blend text relevance with freshness and quality (all bounded, no magic scaling).
            freshness = func.exp(
                -func.extract("epoch", func.now() - func.coalesce(Job.posted_at, Job.created_at)) / 1209600.0
            )
            score = (rank * 4.0) + (freshness * 1.5) + (Job.quality_score / 100.0)
            return stmt.order_by(featured_first, score.desc(), Job.posted_at.desc().nullslast())
        if f.sort == "deadline":
            return stmt.order_by(featured_first, Job.deadline.asc().nullslast(), Job.posted_at.desc())
        if f.sort == "salary":
            return stmt.order_by(
                featured_first,
                func.coalesce(Job.salary_max, Job.salary_min).desc().nullslast(),
                Job.posted_at.desc(),
            )
        if f.sort == "quality":
            return stmt.order_by(featured_first, Job.quality_score.desc(), Job.posted_at.desc().nullslast())
        return stmt.order_by(
            featured_first, func.coalesce(Job.posted_at, Job.created_at).desc(), Job.id.desc()
        )

    async def _facets(
        self, session: AsyncSession, base: list[Any], f: SearchFilters
    ) -> dict[str, list[dict[str, Any]]]:
        """Counts for the filter panel, computed against the same predicate set."""
        async def group(column: Any, limit: int = 12) -> list[dict[str, Any]]:
            stmt = (
                select(column, func.count(Job.id))
                .where(and_(*base, column.isnot(None)))
                .group_by(column)
                .order_by(func.count(Job.id).desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            return [{"value": value, "count": count} for value, count in rows if value]

        return {
            "city": await group(Job.city),
            "category": await group(Job.category, 24),
            "employment_type": await group(Job.employment_type),
            "experience_level": await group(Job.experience_level),
            "province": await group(Job.province),
        }


class SearchService:
    """Public entry point. Backend selection is config-driven."""

    def __init__(self, backend: SearchBackend | None = None):
        self.backend = backend or PostgresSearchBackend()

    async def search(
        self, session: AsyncSession, filters: SearchFilters, *, with_facets: bool = False
    ) -> SearchResult:
        return await self.backend.search(session, filters, with_facets=with_facets)


def build_search_service() -> SearchService:
    from pakjobs_core.config import settings

    if settings.search_backend == "opensearch":
        # Intentionally explicit: fail loudly rather than silently degrading in production.
        raise NotImplementedError(
            "OpenSearch backend is not implemented yet. Implement SearchBackend and register it here."
        )
    return SearchService(PostgresSearchBackend())
