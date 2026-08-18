"""Greenhouse job board connector.

Greenhouse publishes a documented public Job Board API that employers opt into when they host
their careers page there: https://developers.greenhouse.io/job-board.html

This is the preferred way to ingest an employer's own openings — official, structured, and
authorized by the employer choosing to publish a public board.

Config:
    board_token   (required) the employer's board token, e.g. "acme"
    include_content  bool, fetch full descriptions (default true)
    default_location optional fallback location
"""

from __future__ import annotations

from typing import Any

from pakjobs_core.connectors.base import ConnectorError, SourceConnector
from pakjobs_core.domain.enums import SourceType
from pakjobs_core.logging import get_logger
from pakjobs_core.pipeline.schemas import FetchResult, RawJob, SourceMetadata

logger = get_logger("connector.greenhouse")

API_ROOT = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseConnector(SourceConnector):
    key = "greenhouse_board"

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key,
            name="Greenhouse Job Board",
            type=SourceType.CAREER_PAGE,
            website="https://developers.greenhouse.io/job-board.html",
            attribution_label="Greenhouse",
            description=(
                "Official employer career boards hosted on Greenhouse, read through Greenhouse's "
                "documented public Job Board API. One source row per employer board token."
            ),
            requires_credentials=False,
            credential_env_keys=[],
            config_schema={
                "board_token": {"type": "string", "required": True, "label": "Greenhouse board token"},
                "include_content": {"type": "boolean", "required": False, "default": True},
                "default_location": {"type": "string", "required": False},
                "company_name": {"type": "string", "required": False,
                                 "label": "Override company name (defaults to board token)"},
            },
            default_fetch_interval_minutes=120,
            default_reliability=0.92,
            terms_url="https://www.greenhouse.io/legal/terms-of-service",
            legal_note=(
                "Public Job Board API. Only boards the employer has chosen to publish are readable; "
                "no authentication is bypassed."
            ),
        )

    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        board_token = str(self.config.get("board_token", "")).strip()
        if not board_token:
            return FetchResult(
                ok=False,
                error="Config 'board_token' is required (the employer's Greenhouse board token).",
                error_type="ConnectorConfigError",
            )
        include_content = bool(self.config.get("include_content", True))
        url = f"{API_ROOT}/{board_token}/jobs"
        params = {"content": "true"} if include_content else {}

        async with self._client() as client:
            try:
                payload = await self._get_json(client, url, params=params)
            except ConnectorError as exc:
                return FetchResult(ok=False, error=str(exc), error_type=type(exc).__name__)

        items = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return FetchResult(ok=False, error="Unexpected Greenhouse payload shape",
                               error_type="ParseError")

        jobs: list[RawJob] = []
        for item in items[: limit or len(items)]:
            raw = self.parse_job(item)
            if raw:
                jobs.append(raw)
        return FetchResult(jobs=jobs, ok=True, stats={"board_token": board_token, "returned": len(items)})

    def parse_job(self, payload: dict[str, Any]) -> RawJob | None:
        job_id = payload.get("id")
        title = (payload.get("title") or "").strip()
        apply_url = payload.get("absolute_url")
        if not job_id or not title or not apply_url:
            return None

        location = (payload.get("location") or {}).get("name") if isinstance(payload.get("location"), dict) else None
        if not location:
            offices = payload.get("offices") or []
            location = ", ".join(o.get("name", "") for o in offices if isinstance(o, dict)) or None
        location = location or self.config.get("default_location")

        departments = [d.get("name") for d in payload.get("departments") or [] if isinstance(d, dict)]
        metadata = {m.get("name"): m.get("value") for m in payload.get("metadata") or [] if isinstance(m, dict)}

        return RawJob(
            source_job_id=f"gh-board-{job_id}",
            title=title,
            apply_url=apply_url,
            company_name=self.config.get("company_name") or (payload.get("company_name") or self.config.get("board_token")),
            description_html=payload.get("content"),
            location_raw=location,
            employment_type_raw=str(metadata.get("Employment Type") or ""),
            experience_raw=str(metadata.get("Experience") or ""),
            posted_at_raw=payload.get("updated_at") or payload.get("first_published"),
            source_url=apply_url,
            tags=[d for d in departments if d][:8],
            category_hint=self.config.get("category_hint"),
            raw={"id": job_id, "departments": departments, "metadata": metadata,
                 "requisition_id": payload.get("requisition_id")},
        )
