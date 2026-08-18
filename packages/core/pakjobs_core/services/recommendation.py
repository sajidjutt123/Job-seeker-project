"""Personalized ranking.

Deterministic, explainable scoring — no model inference required. Every component contributes a
bounded number of points and the reasons are returned so the UI can say *why* a job matched.
The AI layer may later re-rank the top N, but this must keep working on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from pakjobs_core.models import Job, Profile
from pakjobs_core.pipeline.text import normalize_text

WEIGHTS = {
    "skills": 30.0,
    "category": 18.0,
    "location": 15.0,
    "experience": 12.0,
    "remote": 8.0,
    "salary": 7.0,
    "freshness": 6.0,
    "quality": 4.0,
}

EXPERIENCE_ORDER = ["intern", "fresh_graduate", "entry", "mid", "senior", "lead", "executive"]


@dataclass(slots=True)
class MatchScore:
    score: float
    reasons: list[str] = field(default_factory=list)
    breakdown: dict[str, float] = field(default_factory=dict)


def score_job_for_profile(
    job: Job,
    profile: Profile | None,
    *,
    saved_categories: Iterable[str] = (),
    saved_skills: Iterable[str] = (),
    now: datetime | None = None,
) -> MatchScore:
    """Return a 0–100 match score with human-readable reasons."""
    now = now or datetime.now(timezone.utc)
    b: dict[str, float] = {}
    reasons: list[str] = []

    profile_skills = _lower_set(getattr(profile, "skills", None) or [])
    profile_skills |= _lower_set(saved_skills)
    job_skills = {normalize_text(js.skill.name) for js in (job.skills or []) if js.skill}

    if profile_skills and job_skills:
        overlap = profile_skills & job_skills
        ratio = len(overlap) / max(1, min(len(job_skills), 8))
        b["skills"] = round(WEIGHTS["skills"] * min(ratio, 1.0), 2)
        if overlap:
            display = sorted(js.skill.name for js in job.skills if js.skill and normalize_text(js.skill.name) in overlap)
            reasons.append(f"Matches your skills: {', '.join(display[:3])}")
    else:
        b["skills"] = WEIGHTS["skills"] * 0.25  # unknown, neutral-ish

    preferred_categories = _lower_set(getattr(profile, "preferred_categories", None) or [])
    preferred_categories |= _lower_set(saved_categories)
    if preferred_categories:
        if job.category and job.category.lower() in preferred_categories:
            b["category"] = WEIGHTS["category"]
            reasons.append("In a category you follow")
        elif any(c.lower() in preferred_categories for c in job.secondary_categories or []):
            b["category"] = WEIGHTS["category"] * 0.6
        else:
            b["category"] = 0.0
    else:
        b["category"] = WEIGHTS["category"] * 0.3

    preferred_locations = _lower_set(getattr(profile, "preferred_locations", None) or [])
    profile_city = normalize_text(getattr(profile, "city", None) or "")
    if profile_city:
        preferred_locations.add(profile_city)
    job_city = normalize_text(job.city or "")
    job_province = normalize_text(job.province or "")
    if preferred_locations:
        if job_city and job_city in preferred_locations:
            b["location"] = WEIGHTS["location"]
            reasons.append(f"Located in {job.city}")
        elif job_province and job_province in preferred_locations:
            b["location"] = WEIGHTS["location"] * 0.7
        elif job.is_remote:
            b["location"] = WEIGHTS["location"] * 0.85
            reasons.append("Remote — location independent")
        else:
            b["location"] = 0.0
    else:
        b["location"] = WEIGHTS["location"] * 0.4

    profile_level = (getattr(profile, "experience_level", None) or "").lower()
    if profile_level and job.experience_level and job.experience_level != "unknown":
        b["experience"] = round(WEIGHTS["experience"] * _experience_affinity(profile_level, job.experience_level), 2)
        if b["experience"] >= WEIGHTS["experience"] * 0.9:
            reasons.append("Matches your experience level")
    else:
        b["experience"] = WEIGHTS["experience"] * 0.4

    remote_pref = (getattr(profile, "remote_preference", None) or "").lower()
    if remote_pref in ("remote", "remote_only"):
        b["remote"] = WEIGHTS["remote"] if job.is_remote else 0.0
    elif remote_pref == "hybrid":
        b["remote"] = WEIGHTS["remote"] if job.work_mode in ("hybrid", "remote") else WEIGHTS["remote"] * 0.4
    elif remote_pref == "onsite":
        b["remote"] = WEIGHTS["remote"] if job.work_mode == "onsite" else WEIGHTS["remote"] * 0.3
    else:
        b["remote"] = WEIGHTS["remote"] * 0.5

    expected = getattr(profile, "expected_salary_min", None)
    job_top = job.salary_max or job.salary_min
    if expected and job_top:
        ratio = float(Decimal(str(job_top)) / Decimal(str(expected)))
        if ratio >= 1.0:
            b["salary"] = WEIGHTS["salary"]
            reasons.append("Meets your salary expectation")
        elif ratio >= 0.8:
            b["salary"] = WEIGHTS["salary"] * 0.6
        else:
            b["salary"] = 0.0
    else:
        b["salary"] = WEIGHTS["salary"] * 0.4

    posted = job.posted_at or job.created_at
    age_days = (now - posted).total_seconds() / 86400 if posted else 30
    b["freshness"] = round(WEIGHTS["freshness"] * max(0.0, min(1.0, 1.0 - age_days / 30.0)), 2)
    b["quality"] = round(WEIGHTS["quality"] * min(1.0, (job.quality_score or 0) / 100.0), 2)

    total = round(min(100.0, sum(b.values())), 1)
    return MatchScore(score=total, reasons=reasons[:3], breakdown=b)


def _experience_affinity(profile_level: str, job_level: str) -> float:
    try:
        pi = EXPERIENCE_ORDER.index(profile_level)
        ji = EXPERIENCE_ORDER.index(job_level)
    except ValueError:
        return 0.5
    distance = abs(pi - ji)
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.7
    if distance == 2:
        return 0.35
    return 0.1


def _lower_set(values: Iterable[Any]) -> set[str]:
    return {normalize_text(str(v)) for v in values if v}
