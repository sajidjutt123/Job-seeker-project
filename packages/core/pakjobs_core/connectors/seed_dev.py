"""Development-only seed connector.

STRICTLY NON-PRODUCTION. Guarded three ways:
  1. `ENABLE_SEED_SOURCES` must be true.
  2. `ENVIRONMENT` must not be "production".
  3. Every posting is prefixed `[DEV SAMPLE]` and flagged `is_seed` in the registry.

Deleting this file (and its registry entry) removes the entire demo-data system without touching
any production code path.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pakjobs_core.config import settings
from pakjobs_core.connectors.base import SourceConnector
from pakjobs_core.domain.enums import SourceType
from pakjobs_core.pipeline.schemas import FetchResult, RawJob, SourceMetadata

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "seed" / "sample_jobs.json"
DEV_PREFIX = "[DEV SAMPLE]"


class SeedDevConnector(SourceConnector):
    key = "seed_dev"

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key,
            name="Development Sample Data",
            type=SourceType.SEED,
            attribution_label="Development sample",
            description=(
                "Local fixture data for development and UI testing. Never enabled in production; "
                "every record is visibly prefixed as a sample."
            ),
            requires_credentials=False,
            config_schema={"max_items": {"type": "integer", "required": False, "default": 60}},
            default_fetch_interval_minutes=1440,
            default_reliability=0.3,
            is_seed=True,
            legal_note="Synthetic data authored for this repository. Not real vacancies.",
        )

    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        if settings.is_production or not settings.enable_seed_sources:
            return FetchResult(
                ok=False,
                error="Seed source is disabled (ENABLE_SEED_SOURCES=false or ENVIRONMENT=production).",
                error_type="ConnectorConfigError",
            )
        if not FIXTURE_PATH.exists():
            return FetchResult(ok=False, error=f"Fixture missing: {FIXTURE_PATH}", error_type="FileNotFoundError")

        try:
            fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return FetchResult(ok=False, error=f"Fixture unreadable: {exc}", error_type=type(exc).__name__)

        max_items = int(limit or self.config.get("max_items", 60))
        jobs = [j for j in (self.parse_job(item) for item in fixtures[:max_items]) if j]
        return FetchResult(jobs=jobs, ok=True, stats={"fixture_count": len(fixtures), "is_seed": True})

    def parse_job(self, payload: dict[str, Any]) -> RawJob | None:
        title = payload.get("title")
        if not title:
            return None
        posted_days_ago = float(payload.get("posted_days_ago", 3))
        posted_at = datetime.now(timezone.utc) - timedelta(days=posted_days_ago)
        deadline_days = payload.get("deadline_in_days")
        deadline = (
            datetime.now(timezone.utc) + timedelta(days=float(deadline_days))
            if deadline_days is not None
            else None
        )
        return RawJob(
            source_job_id=f"seed-{payload['id']}",
            title=f"{DEV_PREFIX} {title}",
            apply_url=payload.get("apply_url", "https://example.com/apply"),
            company_name=payload.get("company"),
            company_website=payload.get("company_website"),
            description_text=payload.get("description", ""),
            location_raw=payload.get("location"),
            employment_type_raw=payload.get("employment_type"),
            experience_raw=payload.get("experience"),
            salary_min=payload.get("salary_min"),
            salary_max=payload.get("salary_max"),
            salary_currency=payload.get("currency", "PKR"),
            salary_period=payload.get("salary_period", "month"),
            posted_at_raw=posted_at,
            deadline_raw=deadline,
            source_url=payload.get("source_url", payload.get("apply_url")),
            tags=payload.get("tags", []),
            category_hint=payload.get("category"),
            is_remote_hint=payload.get("remote"),
            raw={"seed": True, "fixture_id": payload.get("id")},
        )
