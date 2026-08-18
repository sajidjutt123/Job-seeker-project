"""RawJob -> NormalizedJob transformation (the PARSE + NORMALIZE + CLASSIFY stages).

Connectors do not implement this themselves: they map source fields onto `RawJob` and the shared
engine guarantees every source produces identically-shaped, comparable records.
"""

from __future__ import annotations

from pakjobs_core.pipeline import normalizer as norm
from pakjobs_core.pipeline.classifier import classify_job
from pakjobs_core.pipeline.deduplicator import apply_url_hash, content_fingerprint
from pakjobs_core.pipeline.schemas import NormalizedJob, RawJob
from pakjobs_core.pipeline.text import collapse_whitespace, extract_bullets, strip_html, truncate

RESPONSIBILITY_HEADINGS = (
    "responsibilities", "key responsibilities", "job responsibilities", "duties",
    "what you will do", "what you'll do", "role", "job description",
)
REQUIREMENT_HEADINGS = (
    "requirements", "job requirements", "qualifications", "required skills", "skills required",
    "what we are looking for", "what we're looking for", "eligibility", "who you are",
    "required qualifications", "must have",
)
BENEFIT_HEADINGS = (
    "benefits", "what we offer", "we offer", "perks", "perks and benefits", "compensation and benefits",
)

MAX_DESCRIPTION_CHARS = 30_000


def normalize_raw_job(raw: RawJob, *, source_reliability: float = 0.7) -> NormalizedJob:
    """Deterministically convert a source payload into the canonical internal record."""
    title = norm.normalize_title(raw.title)

    description = raw.description_text or strip_html(raw.description_html) or ""
    description = truncate(description, MAX_DESCRIPTION_CHARS, suffix="")
    normalized_description = collapse_whitespace(description)

    company_name = norm.normalize_company_name(raw.company_name)
    company_key = norm.company_matching_key(raw.company_name)

    location = norm.normalize_location(
        raw.location_raw,
        extra_text=" ".join(filter(None, [raw.title, " ".join(raw.tags or []), description[:600]])),
    )
    is_remote = location.is_remote or bool(raw.is_remote_hint)
    work_mode = "remote" if is_remote and location.work_mode != "hybrid" else location.work_mode

    employment_type = norm.normalize_employment_type(
        raw.employment_type_raw, " ".join(raw.tags or []), raw.title, description[:1200]
    )
    experience_level = norm.normalize_experience_level(title, description, raw.experience_raw)

    salary = norm.normalize_salary(
        raw.salary_raw or description[:2000] if (raw.salary_raw or _mentions_salary(description)) else None,
        min_value=raw.salary_min,
        max_value=raw.salary_max,
        currency=raw.salary_currency,
        period=raw.salary_period,
    )

    posted_at = norm.parse_datetime(raw.posted_at_raw)
    deadline = norm.parse_datetime(raw.deadline_raw) or norm.extract_deadline(description)

    classification = classify_job(
        title=title,
        description=description,
        company_name=company_name,
        employment_type=employment_type,
        experience_level=experience_level,
        work_mode=work_mode,
        source_hint_category=raw.category_hint,
    )

    skills = norm.normalize_skill_list(
        [*norm.extract_skills(title, description[:8000]), *(raw.tags or [])]
    )

    return NormalizedJob(
        source_job_id=str(raw.source_job_id),
        title=title or collapse_whitespace(raw.title)[:400],
        normalized_title=norm.title_comparison_key(title),
        apply_url=raw.apply_url.strip(),
        company_name=company_name or None,
        company_key=company_key or None,
        company_website=raw.company_website,
        company_logo=raw.company_logo,
        description=description,
        normalized_description=normalized_description,
        responsibilities=extract_bullets(description, RESPONSIBILITY_HEADINGS),
        requirements=extract_bullets(description, REQUIREMENT_HEADINGS),
        benefits=extract_bullets(description, BENEFIT_HEADINGS),
        location_raw=raw.location_raw,
        location=location.location,
        city=location.city,
        city_slug=location.city_slug,
        province=location.province,
        country=location.country,
        work_mode=work_mode,
        is_remote=is_remote,
        employment_type=employment_type,
        experience_level=experience_level,
        category=classification.category,
        secondary_categories=classification.secondary_categories,
        is_internship=classification.is_internship,
        is_government=classification.is_government,
        is_fresh_graduate_friendly=classification.is_fresh_graduate_friendly,
        education_requirement=classification.education_requirement,
        classification_confidence=classification.confidence,
        classification_method=classification.method,
        skills=skills,
        salary_min=salary.min_amount,
        salary_max=salary.max_amount,
        salary_currency=salary.currency,
        salary_period=salary.period,
        posted_at=posted_at,
        deadline=deadline,
        source_url=raw.source_url or raw.apply_url,
        apply_url_hash=apply_url_hash(raw.apply_url),
        content_fingerprint=content_fingerprint(title, company_name, location.city),
        raw_payload=_trim_raw(raw.raw),
    )


def _mentions_salary(text: str) -> bool:
    low = text[:3000].lower()
    return any(token in low for token in ("salary", "pkr", "rs.", "rs ", "compensation", "package", "stipend"))


def _trim_raw(payload: dict, limit: int = 20_000) -> dict:
    """Keep raw payloads for debugging/attribution but bound their size."""
    import json

    try:
        encoded = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        return {"_unserializable": True}
    if len(encoded) <= limit:
        return payload
    return {"_truncated": True, "_preview": encoded[:limit]}
