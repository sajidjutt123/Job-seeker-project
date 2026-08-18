"""Source registry management.

Default source definitions live here as data. `sync_default_sources` is idempotent — it creates
missing rows and refreshes connector metadata without clobbering admin edits (enabled flag,
interval, notes, config).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pakjobs_core.config import settings
from pakjobs_core.connectors.registry import get_connector_class
from pakjobs_core.domain.enums import SourceStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import JobSource

logger = get_logger("source_registry")


@dataclass(slots=True)
class DefaultSource:
    slug: str
    name: str
    connector_key: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    priority: int = 50
    fetch_interval_minutes: int | None = None
    notes: str = ""
    attribution_label: str | None = None
    website_url: str | None = None
    is_seed: bool = False


# ---------------------------------------------------------------------------
# Default registry.
#
# Only sources that are legally and technically usable without bypassing anything are enabled by
# default. Everything else ships disabled with documentation of what an operator must supply.
# ---------------------------------------------------------------------------
DEFAULT_SOURCES: list[DefaultSource] = [
    # --- live, works out of the box (GitHub public REST API) ---
    DefaultSource(
        slug="github-hiring-issues",
        name="GitHub Community Hiring Board",
        connector_key="github_issues",
        config={
            "repository": "poteto/hiring-without-whiteboards",
            "labels": "",
            "state": "open",
            "since_days": 120,
            "max_items": 60,
        },
        enabled=True,
        priority=20,
        fetch_interval_minutes=30,
        website_url="https://github.com/poteto/hiring-without-whiteboards",
        attribution_label="GitHub",
        notes=(
            "Live source. Uses GitHub's documented public REST API with an identifying User-Agent. "
            "Set GITHUB_TOKEN to raise the rate limit from 60/h to 5000/h."
        ),
    ),
    DefaultSource(
        slug="github-hiring-search",
        name="GitHub Hiring Issues (search)",
        connector_key="github_issues",
        config={
            "search_query": "is:issue is:open label:hiring",
            "max_items": 60,
            "require_job_signal": True,
        },
        enabled=True,
        priority=30,
        fetch_interval_minutes=45,
        website_url="https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests",
        attribution_label="GitHub",
        notes=(
            "Live source. Discovers vacancies posted as hiring-labelled issues across public "
            "repositories via GitHub's documented Search API. Search is rate limited to 30 req/min "
            "authenticated, so the connector paces itself deliberately."
        ),
    ),
    DefaultSource(
        slug="github-jobs-label-search",
        name="GitHub Job Postings (search)",
        connector_key="github_issues",
        config={
            "search_query": "is:issue is:open label:job",
            "max_items": 50,
            "require_job_signal": True,
        },
        enabled=True,
        priority=32,
        fetch_interval_minutes=60,
        website_url="https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests",
        attribution_label="GitHub",
        notes="Live source. Companion query covering repositories that use a `job` label.",
    ),

    # --- employer career boards: enable per employer, no credentials needed ---
    DefaultSource(
        slug="greenhouse-employer-template",
        name="Greenhouse Employer Board (template)",
        connector_key="greenhouse_board",
        config={"board_token": "", "include_content": True, "default_location": "Pakistan"},
        enabled=False,
        priority=40,
        fetch_interval_minutes=120,
        website_url="https://developers.greenhouse.io/job-board.html",
        attribution_label="Greenhouse",
        notes=(
            "Duplicate this row per employer and set `board_token` to their Greenhouse board token. "
            "Only public boards the employer chose to publish are readable."
        ),
    ),
    DefaultSource(
        slug="lever-employer-template",
        name="Lever Employer Board (template)",
        connector_key="lever_postings",
        config={"company": "", "default_location": "Pakistan"},
        enabled=False,
        priority=40,
        fetch_interval_minutes=120,
        website_url="https://github.com/lever/postings-api",
        attribution_label="Lever",
        notes="Duplicate per employer and set `company` to their Lever slug.",
    ),

    # --- RSS: government / institutional feeds ---
    DefaultSource(
        slug="rss-government-template",
        name="Government Portal RSS (template)",
        connector_key="rss_feed",
        config={
            "feed_url": "",
            "government": True,
            "category_hint": "government",
            "default_location": "Pakistan",
            "max_items": 100,
        },
        enabled=False,
        priority=25,
        fetch_interval_minutes=60,
        attribution_label="Government portal",
        notes=(
            "Set `feed_url` to a government/institutional job feed that permits syndication. "
            "Verify the publisher's terms before enabling."
        ),
    ),
    DefaultSource(
        slug="rss-employer-template",
        name="Employer Careers RSS (template)",
        connector_key="rss_feed",
        config={"feed_url": "", "company_name": "", "default_location": "Pakistan"},
        enabled=False,
        priority=45,
        fetch_interval_minutes=90,
        attribution_label="Employer feed",
        notes="Generic reader for any employer that publishes a careers RSS/Atom feed.",
    ),

    # --- development only ---
    DefaultSource(
        slug="dev-sample-data",
        name="Development Sample Data",
        connector_key="seed_dev",
        config={"max_items": 60},
        enabled=False,
        priority=99,
        fetch_interval_minutes=1440,
        attribution_label="Development sample",
        is_seed=True,
        notes="Local fixtures for UI development. Refuses to run when ENVIRONMENT=production.",
    ),
]


def sync_default_sources(session: Session, *, enable_seed: bool | None = None) -> dict[str, int]:
    """Create/refresh the default registry rows. Safe to run on every deploy."""
    enable_seed = settings.enable_seed_sources if enable_seed is None else enable_seed
    created = updated = 0

    for definition in DEFAULT_SOURCES:
        connector_cls = get_connector_class(definition.connector_key)
        if connector_cls is None:
            logger.warning("source_registry.unknown_connector", connector=definition.connector_key)
            continue
        meta = connector_cls.get_source_metadata()

        existing = session.execute(
            select(JobSource).where(JobSource.slug == definition.slug)
        ).scalar_one_or_none()

        if existing is None:
            source = JobSource(
                slug=definition.slug,
                name=definition.name,
                type=meta.type,
                connector_key=definition.connector_key,
                website_url=definition.website_url or meta.website,
                attribution_label=definition.attribution_label or meta.attribution_label,
                description=meta.description,
                enabled=(definition.enabled and (not definition.is_seed or enable_seed)),
                priority=definition.priority,
                fetch_interval_minutes=definition.fetch_interval_minutes or meta.default_fetch_interval_minutes,
                reliability_score=meta.default_reliability,
                requires_credentials=meta.requires_credentials,
                credential_env_keys=meta.credential_env_keys,
                config=definition.config,
                status=SourceStatus.UNKNOWN if definition.enabled else SourceStatus.DISABLED,
                is_seed=definition.is_seed or meta.is_seed,
                notes=definition.notes,
            )
            session.add(source)
            created += 1
        else:
            # Refresh connector-derived metadata only; never override operator decisions.
            existing.description = meta.description
            existing.requires_credentials = meta.requires_credentials
            existing.credential_env_keys = meta.credential_env_keys
            existing.type = meta.type
            if not existing.attribution_label:
                existing.attribution_label = definition.attribution_label or meta.attribution_label
            if not existing.notes:
                existing.notes = definition.notes
            if existing.is_seed and not enable_seed and existing.enabled:
                existing.enabled = False
                existing.status = SourceStatus.DISABLED
            updated += 1

    session.flush()
    logger.info("source_registry.synced", created=created, updated=updated)
    return {"created": created, "updated": updated}


def due_sources(session: Session, *, priority_max: int | None = None) -> list[JobSource]:
    """Enabled sources whose fetch interval has elapsed, highest priority first."""
    stmt = select(JobSource).where(JobSource.enabled.is_(True))
    if priority_max is not None:
        stmt = stmt.where(JobSource.priority <= priority_max)
    sources = list(session.execute(stmt).scalars().all())
    return sorted([s for s in sources if s.due_for_run], key=lambda s: s.priority)
