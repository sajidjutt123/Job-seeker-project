"""Job classification engine.

Weighted keyword rules with title-biased scoring. Deliberately deterministic and dependency-free
so it works offline; `ClassificationResult` is the same shape an AI classifier must return, so
`AIJobClassification` can be layered on top (see `services/ai`) without touching callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pakjobs_core.domain.enums import EmploymentType, ExperienceLevel, JobCategorySlug, WorkMode
from pakjobs_core.pipeline.text import normalize_text

# category -> (keyword, weight)
CATEGORY_RULES: dict[str, tuple[tuple[str, float], ...]] = {
    JobCategorySlug.SOFTWARE_ENGINEERING: (
        ("software engineer", 6), ("software engineering", 6), ("software development", 5),
        ("software developer", 6), ("full stack", 5), ("frontend", 5),
        ("front end", 4), ("backend", 5), ("back end", 4), ("web developer", 5), ("mobile developer", 5),
        ("android developer", 5), ("ios developer", 5), ("php developer", 5), ("laravel", 4),
        ("react", 3), ("angular", 3), ("vue", 3), ("node.js", 3), (".net developer", 5),
        ("java developer", 5), ("python developer", 5), ("flutter", 4), ("wordpress developer", 4),
        ("programmer", 4), ("sde", 4), ("technical lead", 3), ("api", 2), ("qa engineer", 4),
        ("quality assurance", 3), ("software architect", 5), ("game developer", 5),
    ),
    JobCategorySlug.DATA_SCIENCE: (
        ("data scientist", 7), ("data analyst", 6), ("data engineer", 6), ("business intelligence", 5),
        ("power bi", 4), ("tableau", 4), ("etl", 3), ("data warehouse", 4), ("analytics", 2),
        ("statistician", 5), ("big data", 4), ("spark", 3),
    ),
    JobCategorySlug.AI_ML: (
        ("machine learning", 7), ("ml engineer", 7), ("artificial intelligence", 6), ("ai engineer", 7),
        ("deep learning", 6), ("computer vision", 6), ("nlp", 5), ("llm", 5), ("generative ai", 6),
        ("pytorch", 3), ("tensorflow", 3), ("data science", 2),
    ),
    JobCategorySlug.CYBERSECURITY: (
        ("cyber security", 7), ("cybersecurity", 7), ("information security", 6), ("soc analyst", 6),
        ("penetration test", 6), ("ethical hacker", 6), ("security engineer", 6), ("infosec", 5),
        ("vulnerability", 3), ("iso 27001", 4),
    ),
    JobCategorySlug.NETWORKING: (
        ("network engineer", 7), ("network administrator", 6), ("ccna", 5), ("ccnp", 5),
        ("routing and switching", 5), ("noc engineer", 5), ("telecom engineer", 4), ("rf engineer", 4),
    ),
    JobCategorySlug.DEVOPS: (
        ("devops", 7), ("site reliability", 7), ("sre", 5), ("platform engineer", 5),
        ("cloud engineer", 6), ("kubernetes", 4), ("infrastructure engineer", 5), ("system administrator", 4),
        ("linux administrator", 5), ("aws engineer", 5), ("ci/cd", 3),
    ),
    JobCategorySlug.FINANCE: (
        ("finance manager", 6), ("financial analyst", 6), ("treasury", 5), ("investment", 4),
        ("credit analyst", 5), ("banking", 3), ("fp&a", 5), ("financial controller", 6), ("actuarial", 5),
    ),
    JobCategorySlug.ACCOUNTING: (
        ("accountant", 7), ("accounts officer", 6), ("bookkeeper", 6), ("audit", 5), ("auditor", 6),
        ("taxation", 5), ("acca", 4), ("chartered accountant", 6), ("accounts payable", 5),
        ("accounts receivable", 5), ("billing", 3),
    ),
    JobCategorySlug.HR: (
        ("human resource", 7), ("hr manager", 7), ("hr officer", 6), ("recruiter", 6),
        ("talent acquisition", 6), ("people operations", 5), ("hr generalist", 6), ("payroll", 4),
    ),
    JobCategorySlug.MARKETING: (
        ("marketing", 5), ("digital marketing", 7), ("seo", 5), ("brand manager", 6),
        ("social media", 5), ("content marketing", 6), ("growth", 3), ("ppc", 4), ("media buyer", 5),
        ("marketing executive", 6),
    ),
    JobCategorySlug.SALES: (
        ("sales", 5), ("business development", 6), ("account executive", 5), ("key account", 5),
        ("sales officer", 6), ("sales manager", 6), ("telesales", 6), ("area sales", 6), ("retail sales", 5),
    ),
    JobCategorySlug.EDUCATION: (
        ("teacher", 7), ("lecturer", 7), ("professor", 7), ("instructor", 6), ("tutor", 6),
        ("academic", 4), ("principal", 5), ("curriculum", 4), ("trainer", 4), ("education officer", 6),
        ("subject specialist", 6),
    ),
    JobCategorySlug.MEDICAL: (
        ("doctor", 7), ("nurse", 7), ("medical officer", 7), ("pharmacist", 7), ("physiotherapist", 7),
        ("dentist", 7), ("radiologist", 6), ("lab technician", 6), ("clinical", 4), ("healthcare", 4),
        ("consultant physician", 7), ("surgeon", 7), ("paramedic", 6),
    ),
    JobCategorySlug.ENGINEERING: (
        ("mechanical engineer", 7), ("electrical engineer", 7), ("chemical engineer", 7),
        ("industrial engineer", 6), ("maintenance engineer", 6), ("production engineer", 6),
        ("design engineer", 5), ("autocad", 4), ("hvac", 5), ("quality engineer", 5),
        ("textile engineer", 6), ("petroleum engineer", 7),
    ),
    JobCategorySlug.CONSTRUCTION: (
        ("civil engineer", 7), ("site engineer", 7), ("construction", 6), ("architect", 5),
        ("quantity surveyor", 7), ("surveyor", 5), ("foreman", 5), ("project engineer", 4),
        ("structural", 5), ("draftsman", 5),
    ),
    JobCategorySlug.LEGAL: (
        ("legal", 6), ("lawyer", 7), ("advocate", 6), ("legal advisor", 7), ("compliance officer", 5),
        ("company secretary", 5), ("paralegal", 6), ("litigation", 6),
    ),
    JobCategorySlug.ADMINISTRATION: (
        ("administrative", 6), ("admin officer", 7), ("office manager", 6), ("receptionist", 6),
        ("secretary", 5), ("data entry", 6), ("clerk", 5), ("executive assistant", 6),
        ("office assistant", 6), ("front desk", 5),
    ),
    JobCategorySlug.CUSTOMER_SUPPORT: (
        ("customer support", 7), ("customer service", 7), ("call center", 7), ("csr", 5),
        ("technical support", 6), ("help desk", 6), ("client relations", 5), ("customer success", 6),
    ),
    JobCategorySlug.DESIGN: (
        ("graphic designer", 7), ("ui/ux", 7), ("ux designer", 7), ("ui designer", 7),
        ("product designer", 6), ("motion graphics", 6), ("illustrator", 4), ("video editor", 5),
        ("creative designer", 6), ("3d artist", 6),
    ),
    JobCategorySlug.OPERATIONS: (
        ("operations manager", 7), ("supply chain", 6), ("logistics", 6), ("procurement", 6),
        ("warehouse", 5), ("inventory", 5), ("production manager", 5), ("operations executive", 6),
        ("store keeper", 5), ("dispatch", 4),
    ),
    JobCategorySlug.GOVERNMENT: (
        ("government of", 6), ("ministry of", 6), ("public service commission", 8), ("fpsc", 8),
        ("ppsc", 8), ("nts", 5), ("bps-", 7), ("bps ", 5), ("federal government", 6),
        ("provincial government", 6), ("municipal", 5), ("wapda", 6), ("nadra", 6), ("pia", 4),
        ("civil service", 6), ("cantonment board", 6), ("district government", 6),
    ),
    JobCategorySlug.INTERNSHIPS: (
        ("internship", 8), ("intern", 6), ("management trainee", 6), ("graduate trainee", 6),
        ("apprentice", 6), ("summer intern", 8),
    ),
}

_COMPILED_RULES: dict[str, tuple[tuple[re.Pattern[str], float], ...]] = {
    category: tuple(
        (re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z])", re.IGNORECASE), weight)
        for kw, weight in rules
    )
    for category, rules in CATEGORY_RULES.items()
}

# A functional category must clear this to outrank the Internships/Government flags. Set low:
# a single strong title keyword (weight 5 x 3.0 = 15) always wins, while weak body-only evidence
# does not.
MIN_FUNCTIONAL_SCORE = 4.0

_GOVERNMENT_HINTS = re.compile(
    r"\b(government|govt|ministry|federal|provincial|public sector|fpsc|ppsc|spsc|kppsc|bpsc|nts|ots|pts|"
    r"bps[\s\-]?\d{1,2}|scale bps|autonomous body|municipal|district council|cantonment)\b",
    re.IGNORECASE,
)
_FRESH_GRAD_HINTS = re.compile(
    r"\b(fresh graduate|fresh candidates|freshers?|no experience required|0-1 year|entry[\s\-]level|"
    r"recent graduate|graduate program|trainee)\b",
    re.IGNORECASE,
)
_EDUCATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(ph\.?d|doctorate)\b", re.IGNORECASE), "phd"),
    (re.compile(r"\b(m\.?s\.?c?|masters?|mba|m\.?phil|ms/mphil)\b", re.IGNORECASE), "masters"),
    (re.compile(r"\b(b\.?s\.?c?|bachelors?|bs\s|be\b|b\.?tech|bba|b\.?com|16 years of education)\b", re.IGNORECASE), "bachelors"),
    (re.compile(r"\b(diploma|dae|associate degree)\b", re.IGNORECASE), "diploma"),
    (re.compile(r"\b(intermediate|f\.?sc|f\.?a\b|hssc|12th)\b", re.IGNORECASE), "intermediate"),
    (re.compile(r"\b(matric|ssc|10th)\b", re.IGNORECASE), "matric"),
)


@dataclass(slots=True)
class ClassificationResult:
    category: str = JobCategorySlug.OTHER
    secondary_categories: list[str] = field(default_factory=list)
    confidence: float = 0.0
    method: str = "rules"
    is_internship: bool = False
    is_government: bool = False
    is_fresh_graduate_friendly: bool = False
    education_requirement: str | None = None
    work_mode: str = WorkMode.UNKNOWN
    scores: dict[str, float] = field(default_factory=dict)


def classify_job(
    *,
    title: str,
    description: str | None = None,
    company_name: str | None = None,
    employment_type: str | None = None,
    experience_level: str | None = None,
    work_mode: str = WorkMode.UNKNOWN,
    source_hint_category: str | None = None,
) -> ClassificationResult:
    """Score every category; title matches count triple, description matches once (capped)."""
    title_text = normalize_text(title)
    body_text = normalize_text((description or "")[:6000])
    company_text = normalize_text(company_name or "")
    combined = f"{title_text} {body_text} {company_text}"

    scores: dict[str, float] = {}
    for category, rules in _COMPILED_RULES.items():
        score = 0.0
        for pattern, weight in rules:
            if pattern.search(title_text):
                score += weight * 3.0
            elif pattern.search(company_text):
                score += weight * 1.2
            elif pattern.search(body_text):
                # Body evidence is weaker and capped to avoid long-JD keyword spam.
                score += min(weight, 4.0) * 0.6
        if score > 0:
            scores[category] = round(score, 2)

    if source_hint_category and source_hint_category in CATEGORY_RULES:
        scores[source_hint_category] = scores.get(source_hint_category, 0) + 4.0

    is_internship = (
        employment_type == EmploymentType.INTERNSHIP
        or experience_level == ExperienceLevel.INTERN
        or scores.get(JobCategorySlug.INTERNSHIPS, 0) >= 12
    )
    is_government = bool(_GOVERNMENT_HINTS.search(f"{title} {company_name or ''}")) or (
        scores.get(JobCategorySlug.GOVERNMENT, 0) >= 12
    )
    if not is_government and description:
        is_government = bool(_GOVERNMENT_HINTS.search(description[:2500])) and scores.get(
            JobCategorySlug.GOVERNMENT, 0
        ) >= 6

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    # Internships and Government are cross-cutting flags, not fields of work. A "Software
    # Engineering Intern" belongs in Software Engineering with an internship flag — otherwise the
    # Internships bucket silently swallows every discipline and category filters become useless.
    functional = [
        (c, s) for c, s in ranked if c not in (JobCategorySlug.INTERNSHIPS, JobCategorySlug.GOVERNMENT)
    ]
    if functional and functional[0][1] >= MIN_FUNCTIONAL_SCORE:
        category, top_score = functional[0]
    elif ranked:
        category, top_score = ranked[0]
    else:
        category, top_score = JobCategorySlug.OTHER, 0.0

    if category == JobCategorySlug.OTHER and is_internship:
        category = JobCategorySlug.INTERNSHIPS
    if category == JobCategorySlug.OTHER and is_government:
        category = JobCategorySlug.GOVERNMENT

    secondary = [c for c, s in ranked if c != category and s >= max(4.0, top_score * 0.4)][:3]
    if is_internship and JobCategorySlug.INTERNSHIPS not in secondary and category != JobCategorySlug.INTERNSHIPS:
        secondary.append(JobCategorySlug.INTERNSHIPS)
    if is_government and JobCategorySlug.GOVERNMENT not in secondary and category != JobCategorySlug.GOVERNMENT:
        secondary.append(JobCategorySlug.GOVERNMENT)

    runner_up = next((s for c, s in ranked if c != category), 0.0)
    confidence = _confidence(top_score, runner_up)

    return ClassificationResult(
        category=category,
        secondary_categories=secondary[:4],
        confidence=confidence,
        method="rules",
        is_internship=is_internship,
        is_government=is_government,
        is_fresh_graduate_friendly=_is_fresh_friendly(combined, experience_level, is_internship),
        education_requirement=detect_education_requirement(f"{title} {description or ''}"),
        work_mode=work_mode,
        scores=dict(ranked[:6]),
    )


def _confidence(top: float, runner_up: float) -> float:
    if top <= 0:
        return 0.0
    magnitude = min(top / 24.0, 1.0)
    separation = 1.0 if runner_up <= 0 else min(max((top - runner_up) / top, 0.0), 1.0)
    return round(min(0.35 * separation + 0.65 * magnitude, 0.99), 3)


def _is_fresh_friendly(text: str, experience_level: str | None, is_internship: bool) -> bool:
    if is_internship:
        return True
    if experience_level in (ExperienceLevel.FRESH_GRADUATE, ExperienceLevel.INTERN, ExperienceLevel.ENTRY):
        return True
    return bool(_FRESH_GRAD_HINTS.search(text))


def detect_education_requirement(text: str | None) -> str | None:
    """Highest education level explicitly mentioned."""
    if not text:
        return None
    for pattern, level in _EDUCATION_PATTERNS:
        if pattern.search(text):
            return level
    return None
