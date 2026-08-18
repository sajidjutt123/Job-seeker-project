"""Validation gate.

Rejects unusable or unsafe records before they can reach the database, and flags
suspicious-but-salvageable ones for admin review instead of silently publishing them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids a circular import at runtime
    from pakjobs_core.pipeline.schemas import NormalizedJob

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from pakjobs_core.pipeline.text import collapse_whitespace

MIN_TITLE_LENGTH = 3
MAX_TITLE_LENGTH = 300
MIN_DESCRIPTION_LENGTH = 40
MAX_FUTURE_POSTING_DAYS = 2
MAX_POSTING_AGE_DAYS = 180

_ALLOWED_SCHEMES = {"http", "https"}
_SCAM_PATTERNS = (
    re.compile(r"\b(registration|processing|security|joining)\s+fee\b", re.IGNORECASE),
    re.compile(r"\bpay\s+(?:rs\.?|pkr|\$)?\s*\d+\s*(?:to|for)\s+(?:apply|register|join)", re.IGNORECASE),
    re.compile(r"\bearn\s+(?:rs\.?|pkr|\$)?\s*\d{4,}\s*(?:daily|per day|a day)\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:experience|qualification|interview)\s+(?:required|needed)\b.*\bhigh\s+salary\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(send|deposit)\s+money\b", re.IGNORECASE),
    re.compile(r"\bwhatsapp\s+only\b", re.IGNORECASE),
)
_MLM_PATTERNS = (
    re.compile(r"\b(network marketing|mlm|multi[\s-]level marketing|pyramid)\b", re.IGNORECASE),
    re.compile(r"\bbe your own boss\b", re.IGNORECASE),
)


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_review: bool = False

    @property
    def reason(self) -> str:
        return "; ".join(self.errors) or "ok"


def is_safe_url(url: str | None) -> bool:
    """Reject non-http(s), credential-bearing and internal-network URLs (SSRF guard)."""
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return False
    if not parsed.netloc or "@" in parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}:
        return False
    if host.endswith((".local", ".internal", ".localhost")):
        return False
    if re.match(r"^(10\.|127\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", host):
        return False
    if len(url) > 2000:
        return False
    return True


def validate_job(payload: "NormalizedJob") -> ValidationResult:
    """Hard errors block ingestion; warnings mark the job for review."""
    errors: list[str] = []
    warnings: list[str] = []

    title = collapse_whitespace(payload.title or "")
    if len(title) < MIN_TITLE_LENGTH:
        errors.append("title_too_short")
    elif len(title) > MAX_TITLE_LENGTH:
        warnings.append("title_too_long")
    if title and not re.search(r"[a-zA-Z]{2}", title):
        errors.append("title_not_textual")

    if not is_safe_url(payload.apply_url):
        errors.append("invalid_apply_url")
    if payload.source_url and not is_safe_url(payload.source_url):
        warnings.append("invalid_source_url")

    description = payload.description or ""
    if len(collapse_whitespace(description)) < MIN_DESCRIPTION_LENGTH:
        warnings.append("thin_description")

    now = datetime.now(timezone.utc)
    if payload.posted_at:
        if payload.posted_at > now + timedelta(days=MAX_FUTURE_POSTING_DAYS):
            warnings.append("posted_in_future")
        elif payload.posted_at < now - timedelta(days=MAX_POSTING_AGE_DAYS):
            warnings.append("posting_too_old")
    if payload.deadline and payload.posted_at and payload.deadline < payload.posted_at:
        warnings.append("deadline_before_posting")
    if payload.deadline and payload.deadline < now - timedelta(days=1):
        warnings.append("deadline_passed")

    if payload.salary_min and payload.salary_max and payload.salary_min > payload.salary_max:
        warnings.append("salary_range_inverted")

    scam_text = f"{title}\n{description[:4000]}"
    if any(p.search(scam_text) for p in _SCAM_PATTERNS):
        errors.append("suspected_scam")
    if any(p.search(scam_text) for p in _MLM_PATTERNS):
        warnings.append("possible_mlm")

    if not payload.company_name:
        warnings.append("missing_company")

    needs_review = bool(
        {"possible_mlm", "posted_in_future", "title_too_long"} & set(warnings)
    ) or len(warnings) >= 3

    return ValidationResult(
        is_valid=not errors, errors=errors, warnings=warnings, needs_review=needs_review
    )
