"""Product analytics.

Data-minimisation rules enforced here:
  * no IP addresses, no user agents, no free-text beyond the search query itself
  * anonymous visitors are identified by a rotating hashed session id, never a durable cookie id
  * analytics failures never break the request that triggered them
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pakjobs_core.domain.enums import AnalyticsEventType
from pakjobs_core.logging import get_logger
from pakjobs_core.models import AnalyticsEvent, Job, SearchLog

logger = get_logger("analytics")

ALLOWED_EVENTS = {e.value for e in AnalyticsEventType}


async def record_event(
    session: AsyncSession,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    if event_type not in ALLOWED_EVENTS:
        logger.debug("analytics.unknown_event", event_type=event_type)
        return
    try:
        session.add(
            AnalyticsEvent(
                event_type=event_type,
                user_id=user_id,
                anon_id=(anon_id or "")[:64] or None,
                entity_type=entity_type,
                entity_id=str(entity_id)[:100] if entity_id else None,
                properties=_sanitize(properties or {}),
            )
        )
    except Exception as exc:  # noqa: BLE001 - analytics must never break a request
        logger.warning("analytics.record_failed", error=str(exc))


async def record_search(
    session: AsyncSession,
    *,
    query: str | None,
    city: str | None,
    category: str | None,
    filters: dict[str, Any],
    result_count: int,
    duration_ms: int,
    user_id: uuid.UUID | None = None,
) -> None:
    try:
        session.add(
            SearchLog(
                user_id=user_id,
                query=(query or "")[:300] or None,
                city=(city or "")[:120] or None,
                category=(category or "")[:80] or None,
                filters=_sanitize(filters),
                result_count=result_count,
                duration_ms=duration_ms,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("analytics.search_log_failed", error=str(exc))


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop anything that looks like PII and bound the payload size."""
    blocked = {"email", "phone", "password", "token", "cnic", "address", "ip", "user_agent"}
    clean: dict[str, Any] = {}
    for key, value in list(payload.items())[:20]:
        if key.lower() in blocked:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key[:40]] = value if not isinstance(value, str) else value[:200]
        elif isinstance(value, (list, tuple)):
            clean[key[:40]] = [str(v)[:60] for v in list(value)[:10]]
    return clean


# --- reporting queries ------------------------------------------------------

async def analytics_overview(session: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    counts_stmt = (
        select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.event_type)
    )
    event_counts = {row[0]: row[1] for row in (await session.execute(counts_stmt)).all()}

    top_queries_stmt = (
        select(SearchLog.query, func.count(SearchLog.id).label("n"))
        .where(SearchLog.created_at >= since, SearchLog.query.isnot(None))
        .group_by(SearchLog.query)
        .order_by(func.count(SearchLog.id).desc())
        .limit(12)
    )
    top_cities_stmt = (
        select(SearchLog.city, func.count(SearchLog.id).label("n"))
        .where(SearchLog.created_at >= since, SearchLog.city.isnot(None))
        .group_by(SearchLog.city)
        .order_by(func.count(SearchLog.id).desc())
        .limit(12)
    )
    top_categories_stmt = (
        select(Job.category, func.count(Job.id).label("n"))
        .where(Job.status == "active")
        .group_by(Job.category)
        .order_by(func.count(Job.id).desc())
        .limit(12)
    )
    zero_result_stmt = (
        select(func.count(SearchLog.id))
        .where(SearchLog.created_at >= since, SearchLog.result_count == 0)
    )

    return {
        "period_days": days,
        "events": event_counts,
        "searches": event_counts.get(AnalyticsEventType.SEARCH.value, 0),
        "job_views": event_counts.get(AnalyticsEventType.JOB_VIEW.value, 0),
        "apply_clicks": event_counts.get(AnalyticsEventType.APPLY_CLICK.value, 0),
        "saves": event_counts.get(AnalyticsEventType.JOB_SAVE.value, 0),
        "alerts_created": event_counts.get(AnalyticsEventType.ALERT_CREATED.value, 0),
        "zero_result_searches": (await session.execute(zero_result_stmt)).scalar_one(),
        "top_queries": [{"value": q, "count": n} for q, n in (await session.execute(top_queries_stmt)).all()],
        "top_cities": [{"value": c, "count": n} for c, n in (await session.execute(top_cities_stmt)).all()],
        "top_categories": [
            {"value": c, "count": n} for c, n in (await session.execute(top_categories_stmt)).all()
        ],
    }
