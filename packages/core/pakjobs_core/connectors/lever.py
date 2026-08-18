"""Lever postings connector.

Lever exposes a documented public postings API for employers who publish a public careers site:
https://github.com/lever/postings-api

Config:
    company   (required) the employer's Lever account slug, e.g. "acme"
    location_filter optional substring filter applied to Lever's location field
"""

from __future__ import annotations

from typing import Any

from pakjobs_core.connectors.base import ConnectorError, SourceConnector
from pakjobs_core.domain.enums import SourceType
from pakjobs_core.pipeline.schemas import FetchResult, RawJob, SourceMetadata

API_ROOT = "https://api.lever.co/v0/postings"


class LeverConnector(SourceConnector):
    key = "lever_postings"

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key,
            name="Lever Postings",
            type=SourceType.CAREER_PAGE,
            website="https://github.com/lever/postings-api",
            attribution_label="Lever",
            description=(
                "Official employer career sites hosted on Lever, read through Lever's documented "
                "public postings API. One source row per employer account."
            ),
            requires_credentials=False,
            config_schema={
                "company": {"type": "string", "required": True, "label": "Lever company slug"},
                "location_filter": {"type": "string", "required": False},
                "company_name": {"type": "string", "required": False},
            },
            default_fetch_interval_minutes=120,
            default_reliability=0.9,
            terms_url="https://www.lever.co/legal/terms-of-service/",
            legal_note="Public postings API for boards the employer has chosen to publish.",
        )

    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        company = str(self.config.get("company", "")).strip()
        if not company:
            return FetchResult(ok=False, error="Config 'company' (Lever slug) is required.",
                               error_type="ConnectorConfigError")

        async with self._client() as client:
            try:
                payload = await self._get_json(client, f"{API_ROOT}/{company}", params={"mode": "json"})
            except ConnectorError as exc:
                return FetchResult(ok=False, error=str(exc), error_type=type(exc).__name__)

        if not isinstance(payload, list):
            return FetchResult(ok=False, error="Unexpected Lever payload shape", error_type="ParseError")

        location_filter = (self.config.get("location_filter") or "").strip().lower()
        jobs: list[RawJob] = []
        for item in payload:
            raw = self.parse_job(item)
            if raw is None:
                continue
            if location_filter and location_filter not in (raw.location_raw or "").lower():
                continue
            jobs.append(raw)
            if limit and len(jobs) >= limit:
                break
        return FetchResult(jobs=jobs, ok=True, stats={"company": company, "returned": len(payload)})

    def parse_job(self, payload: dict[str, Any]) -> RawJob | None:
        job_id = payload.get("id")
        title = (payload.get("text") or "").strip()
        apply_url = payload.get("hostedUrl") or payload.get("applyUrl")
        if not job_id or not title or not apply_url:
            return None

        categories = payload.get("categories") or {}
        lists = payload.get("lists") or []
        description_parts = [payload.get("descriptionPlain") or payload.get("description") or ""]
        for section in lists:
            if isinstance(section, dict):
                description_parts.append(f"\n{section.get('text', '')}\n{section.get('content', '')}")
        description_parts.append(payload.get("additionalPlain") or payload.get("additional") or "")

        return RawJob(
            source_job_id=f"lever-{job_id}",
            title=title,
            apply_url=apply_url,
            company_name=self.config.get("company_name") or self.config.get("company"),
            description_html="\n".join(p for p in description_parts if p),
            location_raw=categories.get("location") or self.config.get("default_location"),
            employment_type_raw=categories.get("commitment"),
            posted_at_raw=payload.get("createdAt"),
            source_url=payload.get("hostedUrl"),
            tags=[t for t in [categories.get("team"), categories.get("department")] if t],
            category_hint=self.config.get("category_hint"),
            raw={"id": job_id, "categories": categories, "country": payload.get("country")},
        )
