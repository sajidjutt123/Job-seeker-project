"""Source connector framework.

Every source is an isolated adapter implementing `SourceConnector`. A connector's ONLY job is to
talk to its source and emit `RawJob`s; parsing/normalization/validation/dedup/quality are shared
pipeline stages so behaviour is identical across sources.

Legal contract for all connectors:
  * Only official APIs, authorized partner feeds, RSS, or explicitly public endpoints.
  * Respect rate limits, send an identifying User-Agent, honour robots directives.
  * Never bypass authentication, CAPTCHAs, paywalls or anti-bot measures.
  * Always preserve `source_url` / `apply_url` attribution.
"""

from __future__ import annotations

import abc
import asyncio
from typing import Any

import httpx

from pakjobs_core.config import settings
from pakjobs_core.http import http_verify
from pakjobs_core.logging import get_logger
from pakjobs_core.pipeline.schemas import FetchResult, NormalizedJob, RawJob, SourceMetadata
from pakjobs_core.pipeline.stages import normalize_raw_job
from pakjobs_core.pipeline.validator import ValidationResult, validate_job

logger = get_logger("connector")


class ConnectorError(RuntimeError):
    """Recoverable connector failure — recorded on the run, retried with backoff."""

    def __init__(self, message: str, *, retryable: bool = True, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class ConnectorConfigError(ConnectorError):
    """Missing/invalid configuration or credentials — not retryable until an admin fixes it."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class SourceConnector(abc.ABC):
    """Base class for all source adapters."""

    #: unique registry key, referenced by JobSource.connector_key
    key: str = "base"

    def __init__(self, config: dict[str, Any] | None = None, *, source_slug: str | None = None):
        self.config: dict[str, Any] = config or {}
        self.source_slug = source_slug or self.key

    # --- required interface -------------------------------------------------
    @classmethod
    @abc.abstractmethod
    def get_source_metadata(cls) -> SourceMetadata:
        """Static self-description used by the registry, admin UI and docs."""

    @abc.abstractmethod
    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        """Retrieve raw postings from the source. Must not raise for expected failures."""

    # --- overridable hooks --------------------------------------------------
    def parse_job(self, payload: Any) -> RawJob | None:
        """Map one source-shaped item onto RawJob. Return None to skip the item."""
        raise NotImplementedError

    def normalize_job(self, raw: RawJob) -> NormalizedJob:
        """Shared normalization. Override only for genuinely source-specific quirks."""
        return normalize_raw_job(raw, source_reliability=self.reliability)

    def validate_job(self, job: NormalizedJob) -> ValidationResult:
        return validate_job(job)

    def check_configuration(self) -> list[str]:
        """Return a list of human-readable configuration problems (empty == ready to run)."""
        problems: list[str] = []
        meta = self.get_source_metadata()
        for key in meta.credential_env_keys:
            if not getattr(settings, key.lower(), "") and not self.config.get(key.lower()):
                problems.append(f"Missing credential: {key}")
        for field_name, spec in meta.config_schema.items():
            if spec.get("required") and not self.config.get(field_name):
                problems.append(f"Missing config field: {field_name}")
        return problems

    @property
    def reliability(self) -> float:
        return float(self.config.get("reliability", self.get_source_metadata().default_reliability))

    # --- shared HTTP client -------------------------------------------------
    def _client(self, **kwargs: Any) -> httpx.AsyncClient:
        headers = {
            "User-Agent": settings.ingest_user_agent,
            "Accept": "application/json, text/xml, application/xml, */*",
            **kwargs.pop("headers", {}),
        }
        return httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(settings.ingest_http_timeout),
            follow_redirects=True,
            verify=http_verify(),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            **kwargs,
        )

    async def _get_json(self, client: httpx.AsyncClient, url: str, **kwargs: Any) -> Any:
        response = await self._request(client, "GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorError(f"Invalid JSON from {url}: {exc}") from exc

    async def _request(
        self, client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """HTTP with source-friendly error semantics: 429/5xx retryable, 4xx not."""
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ConnectorError(f"Timeout contacting {url}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Network error contacting {url}: {exc}", retryable=True) from exc

        if response.status_code == 429:
            raise ConnectorError("Rate limited by source (HTTP 429)", retryable=True, status_code=429)
        if response.status_code in (401, 403):
            raise ConnectorConfigError(
                f"Source refused access (HTTP {response.status_code}). "
                "Credentials or permission required — automated access must not be forced."
            )
        if response.status_code >= 500:
            raise ConnectorError(f"Source server error (HTTP {response.status_code})", retryable=True,
                                 status_code=response.status_code)
        if response.status_code >= 400:
            raise ConnectorError(f"Source rejected request (HTTP {response.status_code})",
                                 retryable=False, status_code=response.status_code)
        return response

    @staticmethod
    async def _polite_delay(seconds: float = 0.4) -> None:
        """Small inter-request pause: we stay well below any published rate limit."""
        await asyncio.sleep(seconds)
