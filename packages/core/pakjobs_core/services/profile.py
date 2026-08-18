"""Profile completeness scoring and preference helpers."""

from __future__ import annotations

from pakjobs_core.models import Profile

# field -> weight (sums to 100)
COMPLETION_WEIGHTS: dict[str, int] = {
    "full_name": 12,
    "city": 10,
    "education_level": 8,
    "degree": 7,
    "years_of_experience": 8,
    "experience_level": 7,
    "skills": 18,
    "preferred_categories": 10,
    "preferred_locations": 8,
    "preferred_job_types": 5,
    "expected_salary_min": 4,
    "remote_preference": 3,
}

NEXT_STEP_LABELS: dict[str, str] = {
    "full_name": "Add your name",
    "city": "Add your city",
    "education_level": "Add your education level",
    "degree": "Add your degree",
    "years_of_experience": "Add your years of experience",
    "experience_level": "Set your experience level",
    "skills": "Add at least 3 skills",
    "preferred_categories": "Choose preferred job categories",
    "preferred_locations": "Choose preferred locations",
    "preferred_job_types": "Choose preferred job types",
    "expected_salary_min": "Set your expected salary",
    "remote_preference": "Set your remote work preference",
}


def compute_profile_completion(profile: Profile) -> int:
    """0–100. Lists need real content (3+ skills) to count, so the number means something."""
    score = 0
    for field_name, weight in COMPLETION_WEIGHTS.items():
        value = getattr(profile, field_name, None)
        if field_name == "skills":
            if value and len(value) >= 3:
                score += weight
            elif value:
                score += weight // 2
        elif isinstance(value, list):
            if value:
                score += weight
        elif value not in (None, "", 0):
            score += weight
    return min(score, 100)


def missing_profile_fields(profile: Profile) -> list[str]:
    missing = []
    for field_name in COMPLETION_WEIGHTS:
        value = getattr(profile, field_name, None)
        if field_name == "skills":
            if not value or len(value) < 3:
                missing.append(field_name)
        elif isinstance(value, list):
            if not value:
                missing.append(field_name)
        elif value in (None, "", 0):
            missing.append(field_name)
    return missing


def next_profile_steps(profile: Profile, limit: int = 3) -> list[str]:
    return [NEXT_STEP_LABELS[f] for f in missing_profile_fields(profile) if f in NEXT_STEP_LABELS][:limit]
