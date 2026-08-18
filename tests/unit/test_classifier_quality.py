"""Unit tests for classification, validation and the quality engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pakjobs_core.domain.enums import EmploymentType, ExperienceLevel, JobCategorySlug
from pakjobs_core.pipeline.classifier import classify_job, detect_education_requirement
from pakjobs_core.pipeline.quality import score_quality
from pakjobs_core.pipeline.schemas import NormalizedJob
from pakjobs_core.pipeline.validator import is_safe_url, validate_job

NOW = datetime.now(timezone.utc)


def make_job(**overrides) -> NormalizedJob:
    defaults = dict(
        source_job_id="s-1",
        title="Software Engineer",
        normalized_title="software engineer",
        apply_url="https://example.com/apply/1",
        company_name="ABC Technologies",
        company_website="https://abc.com",
        description="We are hiring a software engineer. " * 20,
        normalized_description="We are hiring a software engineer. " * 20,
        posted_at=NOW - timedelta(days=1),
        classification_confidence=0.8,
        skills=["Python", "Django"],
        requirements=["3 years experience"],
        responsibilities=["Build APIs"],
        salary_min=Decimal("150000"),
        salary_max=Decimal("250000"),
    )
    defaults.update(overrides)
    return NormalizedJob(**defaults)


class TestClassification:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Senior Software Engineer", JobCategorySlug.SOFTWARE_ENGINEERING),
            ("Data Scientist", JobCategorySlug.DATA_SCIENCE),
            ("Machine Learning Engineer", JobCategorySlug.AI_ML),
            ("Cyber Security Analyst", JobCategorySlug.CYBERSECURITY),
            ("Network Engineer", JobCategorySlug.NETWORKING),
            ("DevOps Engineer", JobCategorySlug.DEVOPS),
            ("Financial Analyst", JobCategorySlug.FINANCE),
            ("Accounts Officer", JobCategorySlug.ACCOUNTING),
            ("HR Manager", JobCategorySlug.HR),
            ("Digital Marketing Executive", JobCategorySlug.MARKETING),
            ("Business Development Manager", JobCategorySlug.SALES),
            ("Lecturer Computer Science", JobCategorySlug.EDUCATION),
            ("Medical Officer", JobCategorySlug.MEDICAL),
            ("Mechanical Engineer", JobCategorySlug.ENGINEERING),
            ("Civil Site Engineer", JobCategorySlug.CONSTRUCTION),
            ("Legal Advisor", JobCategorySlug.LEGAL),
            ("Admin Officer", JobCategorySlug.ADMINISTRATION),
            ("Customer Support Representative", JobCategorySlug.CUSTOMER_SUPPORT),
            ("Graphic Designer", JobCategorySlug.DESIGN),
            ("Operations Manager", JobCategorySlug.OPERATIONS),
        ],
    )
    def test_titles_map_to_categories(self, title: str, expected: str) -> None:
        assert classify_job(title=title, description="").category == expected

    def test_unknown_title_falls_back_to_other(self) -> None:
        assert classify_job(title="Zorbomancer", description="").category == JobCategorySlug.OTHER

    def test_internship_flag(self) -> None:
        result = classify_job(
            title="Software Engineering Intern",
            description="A six month internship for final year students.",
            employment_type=EmploymentType.INTERNSHIP,
        )
        assert result.is_internship
        assert result.is_fresh_graduate_friendly

    def test_internship_keeps_functional_category(self) -> None:
        """Internship is a cross-cutting flag, not a replacement for the field."""
        result = classify_job(title="Software Engineering Intern", description="Write code.")
        assert result.category == JobCategorySlug.SOFTWARE_ENGINEERING
        assert JobCategorySlug.INTERNSHIPS in result.secondary_categories

    def test_government_detection(self) -> None:
        result = classify_job(
            title="Assistant Director (BPS-17)",
            description="Applications are invited by the Punjab Public Service Commission.",
            company_name="Punjab Public Service Commission",
        )
        assert result.is_government

    def test_private_job_is_not_government(self) -> None:
        result = classify_job(title="Software Engineer", description="Join our startup.",
                              company_name="ABC Technologies")
        assert not result.is_government

    def test_fresh_graduate_detection(self) -> None:
        result = classify_job(
            title="Customer Support Representative",
            description="Fresh graduates are encouraged to apply. No experience required.",
        )
        assert result.is_fresh_graduate_friendly

    def test_confidence_is_bounded(self) -> None:
        result = classify_job(title="Senior Software Engineer", description="Python Django")
        assert 0.0 <= result.confidence <= 1.0

    def test_low_confidence_for_ambiguous_title(self) -> None:
        assert classify_job(title="Associate", description="").confidence < 0.6

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Must have a PhD in Computer Science", "phd"),
            ("MS or MPhil required", "masters"),
            ("BS Computer Science required", "bachelors"),
            ("DAE Diploma holders may apply", "diploma"),
            ("Intermediate / FSc pass", "intermediate"),
            ("Matric pass candidates", "matric"),
            ("No education stated", None),
        ],
    )
    def test_education_detection(self, text: str, expected: str | None) -> None:
        assert detect_education_requirement(text) == expected


class TestUrlSafety:
    @pytest.mark.parametrize("url", [
        "https://example.com/jobs/1",
        "http://careers.company.com.pk/apply",
    ])
    def test_valid_urls(self, url: str) -> None:
        assert is_safe_url(url)

    @pytest.mark.parametrize("url", [
        None, "", "not a url", "javascript:alert(1)", "file:///etc/passwd",
        "ftp://example.com/x", "https://localhost/admin", "http://127.0.0.1:8000",
        "http://192.168.1.1/x", "http://10.0.0.5/x", "http://169.254.169.254/latest/meta-data",
        "https://user:pass@example.com/x", "https://metadata.google.internal/x",
        "https://intranet.local/jobs",
    ])
    def test_rejects_unsafe_urls(self, url: str | None) -> None:
        """Blocks XSS vectors and SSRF targets, not just malformed strings."""
        assert not is_safe_url(url)


class TestValidation:
    def test_good_job_passes(self) -> None:
        result = validate_job(make_job())
        assert result.is_valid
        assert not result.needs_review

    def test_short_title_rejected(self) -> None:
        result = validate_job(make_job(title="X"))
        assert not result.is_valid
        assert "title_too_short" in result.errors

    def test_bad_apply_url_rejected(self) -> None:
        result = validate_job(make_job(apply_url="javascript:alert(1)"))
        assert not result.is_valid
        assert "invalid_apply_url" in result.errors

    def test_scam_pattern_rejected(self) -> None:
        result = validate_job(make_job(
            description="Earn Rs 5000 daily! Pay 500 to register and start immediately."
        ))
        assert not result.is_valid
        assert "suspected_scam" in result.errors

    def test_thin_description_warns_but_passes(self) -> None:
        result = validate_job(make_job(description="Apply now", normalized_description="Apply now"))
        assert result.is_valid
        assert "thin_description" in result.warnings

    def test_future_posting_flagged_for_review(self) -> None:
        result = validate_job(make_job(posted_at=NOW + timedelta(days=30)))
        assert result.is_valid
        assert result.needs_review

    def test_mlm_flagged_for_review(self) -> None:
        result = validate_job(make_job(
            description="Join our network marketing team and be your own boss! " * 5
        ))
        assert result.is_valid
        assert result.needs_review

    def test_passed_deadline_warns(self) -> None:
        result = validate_job(make_job(deadline=NOW - timedelta(days=10)))
        assert "deadline_passed" in result.warnings


class TestQuality:
    def test_complete_job_scores_well(self) -> None:
        result = score_quality(make_job(), source_reliability=0.9)
        assert result.score >= 70
        assert result.tier == "high"

    def test_sparse_job_scores_low(self) -> None:
        sparse = make_job(
            description="Job", normalized_description="Job", company_name=None,
            company_website=None, salary_min=None, salary_max=None,
            posted_at=NOW - timedelta(days=120), skills=[], requirements=[],
            responsibilities=[], classification_confidence=0.1,
        )
        result = score_quality(sparse, source_reliability=0.3)
        assert result.score < 40

    def test_duplicate_penalty_applies(self) -> None:
        clean = score_quality(make_job(), source_reliability=0.8).score
        penalised = score_quality(make_job(), source_reliability=0.8, duplicate_confidence=1.0).score
        assert penalised < clean

    def test_score_always_bounded(self) -> None:
        result = score_quality(make_job(), source_reliability=1.0, company_verified=True)
        assert 0 <= result.score <= 100

    def test_freshness_matters(self) -> None:
        fresh = score_quality(make_job(posted_at=NOW)).score
        stale = score_quality(make_job(posted_at=NOW - timedelta(days=90))).score
        assert fresh > stale

    def test_http_url_scores_below_https(self) -> None:
        secure = score_quality(make_job(apply_url="https://example.com/a")).score
        insecure = score_quality(make_job(apply_url="http://example.com/a")).score
        assert secure > insecure

    def test_breakdown_is_auditable(self) -> None:
        result = score_quality(make_job())
        assert "source_reliability" in result.breakdown
        assert "freshness" in result.breakdown
