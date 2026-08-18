"""Generic RSS/Atom job feed connector.

Used for government portals, university career offices and employers that publish a feed.
A feed is an explicit invitation to syndicate, which makes this the safest aggregation channel.

Config:
    feed_url        (required)
    company_name    optional default employer name
    default_location optional fallback location
    category_hint   optional category slug
    government      bool — mark postings from this feed as government listings
"""

from __future__ import annotations

from typing import Any

import feedparser

from pakjobs_core.connectors.base import ConnectorError, SourceConnector
from pakjobs_core.domain.enums import SourceType
from pakjobs_core.logging import get_logger
from pakjobs_core.pipeline.schemas import FetchResult, RawJob, SourceMetadata
from pakjobs_core.pipeline.text import sha256_hex
from pakjobs_core.pipeline.validator import is_safe_url

logger = get_logger("connector.rss")


class RSSFeedConnector(SourceConnector):
    key = "rss_feed"

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key,
            name="RSS / Atom Job Feed",
            type=SourceType.RSS,
            website=None,
            attribution_label="RSS Feed",
            description=(
                "Generic RSS/Atom reader for government portals, universities and employers that "
                "publish a syndication feed. Publishing a feed is an explicit invitation to syndicate."
            ),
            requires_credentials=False,
            config_schema={
                "feed_url": {"type": "string", "required": True, "label": "Feed URL"},
                "company_name": {"type": "string", "required": False},
                "default_location": {"type": "string", "required": False},
                "category_hint": {"type": "string", "required": False},
                "government": {"type": "boolean", "required": False, "default": False},
                "max_items": {"type": "integer", "required": False, "default": 100},
            },
            default_fetch_interval_minutes=60,
            default_reliability=0.8,
            legal_note="Only fetches feeds the publisher has made available for syndication.",
        )

    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        feed_url = str(self.config.get("feed_url", "")).strip()
        if not feed_url:
            return FetchResult(ok=False, error="Config 'feed_url' is required.",
                               error_type="ConnectorConfigError")
        if not is_safe_url(feed_url):
            return FetchResult(ok=False, error="Config 'feed_url' is not a valid public http(s) URL.",
                               error_type="ConnectorConfigError")

        async with self._client(headers={"Accept": "application/rss+xml, application/atom+xml, text/xml"}) as client:
            try:
                response = await self._request(client, "GET", feed_url)
            except ConnectorError as exc:
                return FetchResult(ok=False, error=str(exc), error_type=type(exc).__name__)
            content = response.content

        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            return FetchResult(
                ok=False,
                error=f"Feed could not be parsed: {getattr(parsed, 'bozo_exception', 'unknown error')}",
                error_type="FeedParseError",
            )

        max_items = int(limit or self.config.get("max_items", 100))
        jobs: list[RawJob] = []
        for entry in parsed.entries[:max_items]:
            raw = self.parse_job(entry)
            if raw:
                jobs.append(raw)

        return FetchResult(
            jobs=jobs,
            ok=True,
            partial=bool(parsed.bozo and parsed.entries),
            stats={
                "feed_title": getattr(parsed.feed, "title", None),
                "entries": len(parsed.entries),
            },
        )

    def parse_job(self, payload: Any) -> RawJob | None:
        link = getattr(payload, "link", None)
        title = (getattr(payload, "title", "") or "").strip()
        if not title or not link:
            return None

        entry_id = getattr(payload, "id", None) or getattr(payload, "guid", None) or link
        description = ""
        if getattr(payload, "content", None):
            description = payload.content[0].get("value", "")
        description = description or getattr(payload, "summary", "") or getattr(payload, "description", "")

        author = getattr(payload, "author", None)
        tags = [t.get("term") for t in getattr(payload, "tags", []) or [] if isinstance(t, dict) and t.get("term")]

        published = (
            getattr(payload, "published", None)
            or getattr(payload, "updated", None)
            or getattr(payload, "created", None)
        )

        return RawJob(
            source_job_id=f"rss-{sha256_hex(str(entry_id))[:32]}",
            title=title,
            apply_url=link,
            company_name=self.config.get("company_name") or author,
            description_html=description,
            location_raw=self.config.get("default_location"),
            posted_at_raw=published,
            source_url=link,
            tags=tags[:8],
            category_hint=self.config.get("category_hint")
            or ("government" if self.config.get("government") else None),
            raw={"entry_id": str(entry_id), "author": author, "tags": tags},
        )
