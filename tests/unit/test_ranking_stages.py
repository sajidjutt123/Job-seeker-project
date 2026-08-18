"""Unit tests for the RawJob→NormalizedJob stage and the recommendation ranker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from pakjobs_core.domain.enums import EmploymentType, ExperienceLevel, JobCategorySlug, WorkMode
from pakjobs_core.pipeline.schemas import RawJob
from pakjobs_core.pipeline.stages import normalize_raw_job
from pakjobs_core.pipeline.text import extract_bullets, slugify, strip_html
from pakjobs_core.services.recommendation import score_job_for_profile

NOW = datetime.now(timezone.utc)


class TestTextUtils:
    def test_strip_html_produces_readable_text(self) -> None:
        html = "<p>Hello <b>world</b></p><ul><li>One</li><li>Two</li></ul><script>bad()</script>"
        text = strip_html(html)
        assert "Hello world" in text
        assert "One" in text and "Two" in text
        assert "bad()" not in text
        assert "<" not in text

    def test_strip_html_decodes_entities(self) -> None:
        assert "R&D" in strip_html("<p>R&amp;D team</p>")

    def test_slugify(self) -> None:
        assert slugify("Senior Software Engineer — Lahore!") == "senior-software-engineer-lahore"

    def test_slugify_handles_empty(self) -> None:
        assert slugify("!!!") == "item"

    def test_extract_bullets_under_heading(self) -> None:
        text = "Requirements:\n- 3 years experience\n- Strong SQL\n\nBenefits:\n- Health cover"
        items = extract_bullets(text, ("requirements",))
        assert items == ["3 years experience", "Strong SQL"]

    def test_extract_bullets_returns_empty_when_absent(self) -> None:
        assert extract_bullets("Just a paragraph with no structure.", ("requirements",)) == []


class TestNormalizeRawJob:
    def test_full_pipeline(self) -> None:
        raw = RawJob(
            source_job_id="abc-1",
            title="URGENT: Senior Python Developer - Lahore",
            apply_url="https://abc.com/jobs/1?utm_source=x",
            company_name="ABC Technologies (Pvt) Ltd",
            description_html=(
                "<p>Build backend services.</p>"
                "<p>Responsibilities:</p><ul><li>Design APIs</li><li>Write tests</li></ul>"
                "<p>Requirements:</p><ul><li>5 years Python experience</li><li>PostgreSQL and Docker</li></ul>"
            ),
            location_raw="Lahore, Pakistan",
            employment_type_raw="Full Time",
            salary_raw="PKR 250,000 - 400,000 per month",
            posted_at_raw="2026-03-01T00:00:00Z",
        )
        job = normalize_raw_job(raw)

        assert job.title == "Senior Python Developer"
        assert job.company_name == "ABC Technologies (Pvt) Ltd"
        assert job.company_key == "abc"
        assert job.city == "Lahore"
        assert job.province == "Punjab"
        assert job.country == "PK"
        assert job.work_mode == WorkMode.ONSITE
        assert job.employment_type == EmploymentType.FULL_TIME
        assert job.experience_level == ExperienceLevel.SENIOR
        assert job.category == JobCategorySlug.SOFTWARE_ENGINEERING
        assert job.salary_min == Decimal("250000")
        assert job.salary_max == Decimal("400000")
        assert job.salary_currency == "PKR"
        assert "Python" in job.skills
        assert len(job.responsibilities) == 2
        assert len(job.requirements) == 2
        assert job.apply_url_hash is not None
        assert job.content_fingerprint is not None
        assert "<p>" not in job.description

    def test_remote_job(self) -> None:
        job = normalize_raw_job(RawJob(
            source_job_id="r-1", title="Remote Full Stack Developer",
            apply_url="https://x.com/1", location_raw="Remote",
            description_text="Work from anywhere in Pakistan.",
        ))
        assert job.is_remote
        assert job.work_mode == WorkMode.REMOTE

    def test_minimal_input_does_not_crash(self) -> None:
        job = normalize_raw_job(RawJob(source_job_id="m-1", title="Job", apply_url="https://x.com/1"))
        assert job.title == "Job"
        assert job.category == JobCategorySlug.OTHER
        assert job.salary_min is None

    def test_raw_payload_is_size_bounded(self) -> None:
        job = normalize_raw_job(RawJob(
            source_job_id="b-1", title="Job", apply_url="https://x.com/1",
            raw={"blob": "x" * 50_000},
        ))
        assert job.raw_payload.get("_truncated") is True

    def test_government_job(self) -> None:
        job = normalize_raw_job(RawJob(
            source_job_id="g-1",
            title="Assistant Director (BPS-17)",
            apply_url="https://ppsc.gop.pk/apply",
            company_name="Punjab Public Service Commission",
            description_text="Applications are invited for BPS-17 posts. Masters degree required.",
            location_raw="Lahore",
        ))
        assert job.is_government
        assert job.education_requirement == "masters"


def fake_skill(name: str):
    return SimpleNamespace(skill=SimpleNamespace(name=name))


def fake_job(**overrides):
    defaults = dict(
        skills=[fake_skill("Python"), fake_skill("Django")],
        category="software-engineering",
        secondary_categories=[],
        city="Lahore",
        province="Punjab",
        is_remote=False,
        work_mode="onsite",
        experience_level="mid",
        salary_min=Decimal("150000"),
        salary_max=Decimal("250000"),
        posted_at=NOW - timedelta(days=1),
        created_at=NOW - timedelta(days=1),
        quality_score=80.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def fake_profile(**overrides):
    defaults = dict(
        skills=["Python", "Django"],
        preferred_categories=["software-engineering"],
        preferred_locations=["Lahore"],
        city="Lahore",
        experience_level="mid",
        remote_preference="any",
        expected_salary_min=Decimal("150000"),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestRecommendationRanking:
    def test_perfect_match_scores_high(self) -> None:
        result = score_job_for_profile(fake_job(), fake_profile())
        assert result.score >= 75
        assert result.reasons

    def test_poor_match_scores_low(self) -> None:
        job = fake_job(
            skills=[fake_skill("Nursing")], category="medical", city="Quetta", province="Balochistan",
            experience_level="executive", salary_min=Decimal("40000"), salary_max=Decimal("60000"),
            posted_at=NOW - timedelta(days=60), quality_score=30.0,
        )
        assert score_job_for_profile(job, fake_profile()).score < 45

    def test_score_is_bounded(self) -> None:
        assert 0 <= score_job_for_profile(fake_job(), fake_profile()).score <= 100

    def test_works_without_a_profile(self) -> None:
        """Anonymous ranking must not crash — it just returns a neutral score."""
        result = score_job_for_profile(fake_job(), None)
        assert 0 <= result.score <= 100

    def test_remote_preference_is_respected(self) -> None:
        profile = fake_profile(remote_preference="remote")
        remote = score_job_for_profile(fake_job(is_remote=True, work_mode="remote"), profile)
        onsite = score_job_for_profile(fake_job(is_remote=False, work_mode="onsite"), profile)
        assert remote.score > onsite.score

    def test_reasons_are_human_readable(self) -> None:
        reasons = score_job_for_profile(fake_job(), fake_profile()).reasons
        assert any("skill" in r.lower() for r in reasons)

    def test_freshness_boosts_score(self) -> None:
        fresh = score_job_for_profile(fake_job(posted_at=NOW), fake_profile())
        stale = score_job_for_profile(fake_job(posted_at=NOW - timedelta(days=45)), fake_profile())
        assert fresh.score > stale.score
