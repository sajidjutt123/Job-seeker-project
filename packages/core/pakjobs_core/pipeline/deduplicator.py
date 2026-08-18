"""Duplicate detection engine.

Multi-signal confidence scoring — never a bare title comparison. The same opening posted on a
company career page and on an aggregator must collapse to one canonical job while every source
record is preserved for attribution.

Signals: apply-URL identity, source job id, company key similarity, normalized title similarity,
location agreement, salary agreement, description similarity, posting-date proximity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids a circular import at runtime
    from pakjobs_core.pipeline.schemas import NormalizedJob

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Protocol
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from rapidfuzz import fuzz

from pakjobs_core.pipeline.normalizer import company_matching_key, title_comparison_key
from pakjobs_core.pipeline.text import normalize_text, sha256_hex

# Confidence thresholds
AUTO_MERGE_THRESHOLD = 0.86   # collapse into canonical automatically
REVIEW_THRESHOLD = 0.68       # record the link, keep both, flag for admin review

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "ref", "referrer", "source", "src", "trk", "trackingid",
    "mc_cid", "mc_eid", "_hsenc", "_hsmi", "igshid",
}


def canonical_url(url: str | None) -> str:
    """Normalize a URL for identity comparison: lowercase host, drop tracking params/fragment."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    query = "&".join(
        f"{k}={v}" for k, v in sorted(parse_qsl(parts.query, keep_blank_values=False))
        if k.lower() not in _TRACKING_PARAMS
    )
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def apply_url_hash(url: str | None) -> str | None:
    canon = canonical_url(url)
    return sha256_hex(canon) if canon else None


def content_fingerprint(title: str, company: str | None, city: str | None) -> str:
    """Coarse bucket key: cheap DB-side candidate retrieval before expensive scoring."""
    return sha256_hex(title_comparison_key(title), company_matching_key(company), normalize_text(city))


class DuplicateCandidate(Protocol):
    """Structural type: any object (ORM row or dataclass) exposing these fields works."""

    id: object
    normalized_title: str
    company_name_raw: str | None
    city: str | None
    apply_url: str
    apply_url_hash: str | None
    source_id: object
    source_job_id: str | None
    normalized_description: str
    salary_min: object
    salary_max: object
    posted_at: datetime | None


@dataclass(slots=True)
class DuplicateVerdict:
    is_duplicate: bool
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)
    matched_id: object | None = None
    needs_review: bool = False

    @property
    def should_auto_merge(self) -> bool:
        return self.confidence >= AUTO_MERGE_THRESHOLD


# Signal weights (sum to 1.0 for the "soft" path).
_WEIGHTS = {
    "title": 0.34,
    "company": 0.26,
    "location": 0.14,
    "description": 0.16,
    "salary": 0.05,
    "recency": 0.05,
}


def score_pair(
    *,
    title_a: str,
    title_b: str,
    company_a: str | None,
    company_b: str | None,
    city_a: str | None,
    city_b: str | None,
    description_a: str | None,
    description_b: str | None,
    salary_a: tuple[Decimal | None, Decimal | None] = (None, None),
    salary_b: tuple[Decimal | None, Decimal | None] = (None, None),
    posted_a: datetime | None = None,
    posted_b: datetime | None = None,
) -> tuple[float, dict[str, float]]:
    """Weighted similarity in [0, 1] plus the per-signal breakdown (for auditability)."""
    signals: dict[str, float] = {}

    key_a, key_b = title_comparison_key(title_a), title_comparison_key(title_b)
    signals["title"] = round(fuzz.token_set_ratio(key_a, key_b) / 100.0, 3) if key_a and key_b else 0.0

    comp_a, comp_b = company_matching_key(company_a), company_matching_key(company_b)
    if comp_a and comp_b:
        if comp_a == comp_b:
            company_score = 1.0
        else:
            partial = fuzz.partial_ratio(comp_a, comp_b) / 100.0
            token = fuzz.token_set_ratio(comp_a, comp_b) / 100.0
            company_score = max(partial, token)
            # "abc" vs "abc technologies" — containment is a strong signal.
            if comp_a in comp_b or comp_b in comp_a:
                company_score = max(company_score, 0.95)
        signals["company"] = round(company_score, 3)
    else:
        signals["company"] = 0.5  # unknown, stay neutral

    city_x, city_y = normalize_text(city_a), normalize_text(city_b)
    if city_x and city_y:
        signals["location"] = 1.0 if city_x == city_y else round(fuzz.ratio(city_x, city_y) / 100.0, 3)
    else:
        signals["location"] = 0.5

    desc_a = normalize_text((description_a or "")[:2500])
    desc_b = normalize_text((description_b or "")[:2500])
    if len(desc_a) > 120 and len(desc_b) > 120:
        signals["description"] = round(fuzz.token_sort_ratio(desc_a, desc_b) / 100.0, 3)
    else:
        signals["description"] = 0.5

    signals["salary"] = _salary_signal(salary_a, salary_b)
    signals["recency"] = _recency_signal(posted_a, posted_b)

    confidence = sum(signals[name] * weight for name, weight in _WEIGHTS.items())
    return round(min(confidence, 1.0), 4), signals


def _salary_signal(a: tuple[Decimal | None, Decimal | None], b: tuple[Decimal | None, Decimal | None]) -> float:
    a_min, a_max = a
    b_min, b_max = b
    if not any([a_min, a_max]) or not any([b_min, b_max]):
        return 0.5
    ref_a = a_max or a_min
    ref_b = b_max or b_min
    if ref_a is None or ref_b is None or ref_a <= 0 or ref_b <= 0:
        return 0.5
    ratio = float(min(ref_a, ref_b) / max(ref_a, ref_b))
    return round(ratio, 3)


def _recency_signal(a: datetime | None, b: datetime | None) -> float:
    if not a or not b:
        return 0.5
    days = abs((a - b).total_seconds()) / 86400
    if days <= 2:
        return 1.0
    if days <= 7:
        return 0.85
    if days <= 21:
        return 0.6
    if days <= 60:
        return 0.3
    return 0.1


def find_duplicate(
    candidate: "NormalizedJob",
    existing: Iterable[DuplicateCandidate],
    *,
    source_id: object = None,
) -> DuplicateVerdict:
    """Compare one incoming normalized job against pre-filtered existing rows.

    Hard identity signals (same source+source_job_id, identical canonical apply URL) short-circuit
    to confidence 1.0. Otherwise the weighted score decides merge vs review vs distinct.
    """
    best = DuplicateVerdict(is_duplicate=False, confidence=0.0)
    candidate_hash = candidate.apply_url_hash or apply_url_hash(candidate.apply_url)

    for row in existing:
        # --- hard identity ---
        if source_id is not None and row.source_id == source_id and row.source_job_id == candidate.source_job_id:
            return DuplicateVerdict(True, 1.0, {"source_job_id": 1.0}, row.id)
        if candidate_hash and row.apply_url_hash and candidate_hash == row.apply_url_hash:
            return DuplicateVerdict(True, 1.0, {"apply_url": 1.0}, row.id)

        confidence, signals = score_pair(
            title_a=candidate.normalized_title or candidate.title,
            title_b=row.normalized_title,
            company_a=candidate.company_name,
            company_b=row.company_name_raw,
            city_a=candidate.city,
            city_b=row.city,
            description_a=candidate.normalized_description,
            description_b=row.normalized_description,
            salary_a=(candidate.salary_min, candidate.salary_max),
            salary_b=(_dec(row.salary_min), _dec(row.salary_max)),
            posted_a=candidate.posted_at,
            posted_b=row.posted_at,
        )
        if confidence > best.confidence:
            best = DuplicateVerdict(
                is_duplicate=confidence >= AUTO_MERGE_THRESHOLD,
                confidence=confidence,
                signals=signals,
                matched_id=row.id,
                needs_review=REVIEW_THRESHOLD <= confidence < AUTO_MERGE_THRESHOLD,
            )
    return best


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None
