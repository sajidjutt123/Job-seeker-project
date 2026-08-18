"""Job quality engine.

Produces an internal 0–100 score used for ranking and moderation triage only. It is explicitly
NOT surfaced to end users as a verdict about an employer — the API exposes it only to admins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids a circular import at runtime
    from pakjobs_core.pipeline.schemas import NormalizedJob

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pakjobs_core.pipeline.validator import is_safe_url

# factor -> max points (total 100)
WEIGHTS: dict[str, float] = {
    "source_reliability": 20.0,
    "apply_url": 15.0,
    "company_presence": 12.0,
    "description_completeness": 18.0,
    "dates_valid": 10.0,
    "salary_present": 8.0,
    "classification_confidence": 7.0,
    "freshness": 10.0,
}
DUPLICATE_PENALTY = 12.0


@dataclass(slots=True)
class QualityResult:
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def tier(self) -> str:
        if self.score >= 75:
            return "high"
        if self.score >= 50:
            return "medium"
        return "low"


def score_quality(
    job: "NormalizedJob",
    *,
    source_reliability: float = 0.7,
    duplicate_confidence: float = 0.0,
    company_verified: bool = False,
    now: datetime | None = None,
) -> QualityResult:
    now = now or datetime.now(timezone.utc)
    b: dict[str, float] = {}

    b["source_reliability"] = round(WEIGHTS["source_reliability"] * max(0.0, min(source_reliability, 1.0)), 2)

    if is_safe_url(job.apply_url):
        url_points = WEIGHTS["apply_url"] * (1.0 if job.apply_url.lower().startswith("https://") else 0.75)
    else:
        url_points = 0.0
    b["apply_url"] = round(url_points, 2)

    company_points = 0.0
    if job.company_name:
        company_points += 0.5
    if job.company_website:
        company_points += 0.25
    if company_verified:
        company_points += 0.25
    b["company_presence"] = round(WEIGHTS["company_presence"] * min(company_points, 1.0), 2)

    b["description_completeness"] = round(
        WEIGHTS["description_completeness"] * _description_ratio(job), 2
    )

    date_points = 0.0
    if job.posted_at:
        date_points += 0.6
        if job.posted_at <= now:
            date_points += 0.1
    if job.deadline and job.deadline > now:
        date_points += 0.3
    b["dates_valid"] = round(WEIGHTS["dates_valid"] * min(date_points, 1.0), 2)

    salary_ratio = 0.0
    if job.salary_min or job.salary_max:
        salary_ratio = 1.0 if (job.salary_min and job.salary_max) else 0.65
    b["salary_present"] = round(WEIGHTS["salary_present"] * salary_ratio, 2)

    b["classification_confidence"] = round(
        WEIGHTS["classification_confidence"] * max(0.0, min(job.classification_confidence, 1.0)), 2
    )

    b["freshness"] = round(WEIGHTS["freshness"] * _freshness_ratio(job.posted_at, now), 2)

    penalty = round(DUPLICATE_PENALTY * max(0.0, min(duplicate_confidence, 1.0)), 2)
    if penalty:
        b["duplicate_penalty"] = -penalty

    total = max(0.0, min(sum(b.values()), 100.0))
    return QualityResult(score=round(total, 2), breakdown=b)


def _description_ratio(job: "NormalizedJob") -> float:
    text = job.normalized_description or job.description or ""
    length = len(text)
    if length < 80:
        ratio = 0.05
    elif length < 250:
        ratio = 0.35
    elif length < 700:
        ratio = 0.65
    elif length < 6000:
        ratio = 1.0
    else:
        ratio = 0.85  # extremely long JDs are usually boilerplate-heavy
    structure_bonus = 0.0
    if job.requirements:
        structure_bonus += 0.08
    if job.responsibilities:
        structure_bonus += 0.08
    if job.skills:
        structure_bonus += 0.06
    return min(ratio + structure_bonus, 1.0)


def _freshness_ratio(posted_at: datetime | None, now: datetime) -> float:
    if not posted_at:
        return 0.35
    age_days = (now - posted_at).total_seconds() / 86400
    if age_days < 0:
        return 0.5
    if age_days <= 2:
        return 1.0
    if age_days <= 7:
        return 0.88
    if age_days <= 14:
        return 0.72
    if age_days <= 30:
        return 0.5
    if age_days <= 60:
        return 0.28
    return 0.1
