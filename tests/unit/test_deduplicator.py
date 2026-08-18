"""Unit tests for duplicate detection."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pakjobs_core.pipeline.deduplicator import (
    AUTO_MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
    apply_url_hash,
    canonical_url,
    content_fingerprint,
    find_duplicate,
    score_pair,
)
from pakjobs_core.pipeline.schemas import NormalizedJob

NOW = datetime.now(timezone.utc)


@dataclass
class FakeJob:
    """Minimal structural stand-in for the ORM row the engine compares against."""

    id: uuid.UUID
    normalized_title: str
    company_name_raw: str | None
    city: str | None
    apply_url: str
    apply_url_hash: str | None
    source_id: uuid.UUID | None
    source_job_id: str | None
    normalized_description: str
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    posted_at: datetime | None = None


def make_existing(**overrides) -> FakeJob:
    defaults = dict(
        id=uuid.uuid4(),
        normalized_title="software engineer",
        company_name_raw="ABC Technologies",
        city="Lahore",
        apply_url="https://abc.com/jobs/1",
        apply_url_hash=apply_url_hash("https://abc.com/jobs/1"),
        source_id=uuid.uuid4(),
        source_job_id="src-1",
        normalized_description="We are hiring a software engineer to build backend services in Lahore. "
        "You will design APIs, write tests and work with product.",
        salary_min=Decimal("150000"),
        salary_max=Decimal("250000"),
        posted_at=NOW - timedelta(days=1),
    )
    defaults.update(overrides)
    return FakeJob(**defaults)


def make_candidate(**overrides) -> NormalizedJob:
    defaults = dict(
        source_job_id="src-2",
        title="Software Engineer",
        normalized_title="software engineer",
        apply_url="https://linkedin.com/jobs/999",
        company_name="ABC",
        city="Lahore",
        normalized_description="We are hiring a software engineer to build backend services in Lahore. "
        "You will design APIs, write tests and work with product.",
        salary_min=Decimal("150000"),
        salary_max=Decimal("250000"),
        posted_at=NOW,
    )
    defaults.update(overrides)
    job = NormalizedJob(**{k: v for k, v in defaults.items() if k in NormalizedJob.__slots__})
    job.apply_url_hash = apply_url_hash(job.apply_url)
    return job


class TestCanonicalUrl:
    def test_strips_tracking_params(self) -> None:
        assert canonical_url("https://x.com/j/1?utm_source=fb&id=5") == "https://x.com/j/1?id=5"

    def test_normalises_host_and_trailing_slash(self) -> None:
        assert canonical_url("https://WWW.X.com/j/1/") == canonical_url("https://x.com/j/1")

    def test_drops_fragment(self) -> None:
        assert "#" not in canonical_url("https://x.com/j/1#apply")

    def test_empty(self) -> None:
        assert canonical_url(None) == ""


class TestScorePair:
    def test_spec_example_is_recognised(self) -> None:
        """LinkedIn 'Software Engineer — ABC — Lahore' vs site 'Software Engineer — ABC Technologies — Lahore'."""
        confidence, signals = score_pair(
            title_a="Software Engineer", title_b="Software Engineer",
            company_a="ABC", company_b="ABC Technologies",
            city_a="Lahore", city_b="Lahore",
            description_a="Build backend services and APIs for our platform in Lahore." * 4,
            description_b="Build backend services and APIs for our platform in Lahore." * 4,
            salary_a=(Decimal("150000"), Decimal("250000")),
            salary_b=(Decimal("150000"), Decimal("250000")),
            posted_a=NOW, posted_b=NOW - timedelta(days=1),
        )
        assert confidence >= AUTO_MERGE_THRESHOLD
        assert signals["company"] >= 0.9

    def test_different_jobs_score_low(self) -> None:
        confidence, _ = score_pair(
            title_a="Software Engineer", title_b="Marketing Manager",
            company_a="ABC Technologies", company_b="XYZ Foods",
            city_a="Lahore", city_b="Karachi",
            description_a="Build backend services." * 10,
            description_b="Run marketing campaigns." * 10,
        )
        assert confidence < REVIEW_THRESHOLD

    def test_same_title_different_company_is_not_a_duplicate(self) -> None:
        """A bare title comparison would wrongly merge these."""
        confidence, _ = score_pair(
            title_a="Software Engineer", title_b="Software Engineer",
            company_a="Systems Limited", company_b="NETSOL Technologies",
            city_a="Lahore", city_b="Karachi",
            description_a="Completely different role description one." * 10,
            description_b="An entirely unrelated set of responsibilities two." * 10,
        )
        assert confidence < AUTO_MERGE_THRESHOLD

    def test_missing_signals_stay_neutral(self) -> None:
        _, signals = score_pair(
            title_a="Engineer", title_b="Engineer",
            company_a=None, company_b=None, city_a=None, city_b=None,
            description_a=None, description_b=None,
        )
        assert signals["company"] == 0.5
        assert signals["location"] == 0.5


class TestFindDuplicate:
    def test_identical_apply_url_is_certain(self) -> None:
        existing = make_existing(apply_url="https://abc.com/jobs/1")
        candidate = make_candidate(apply_url="https://abc.com/jobs/1?utm_source=x")
        verdict = find_duplicate(candidate, [existing])
        assert verdict.confidence == 1.0
        assert verdict.is_duplicate

    def test_same_source_job_id_is_certain(self) -> None:
        source_id = uuid.uuid4()
        existing = make_existing(source_id=source_id, source_job_id="abc-1")
        candidate = make_candidate(source_job_id="abc-1")
        verdict = find_duplicate(candidate, [existing], source_id=source_id)
        assert verdict.confidence == 1.0

    def test_cross_source_duplicate_is_detected(self) -> None:
        verdict = find_duplicate(make_candidate(), [make_existing()])
        assert verdict.confidence >= AUTO_MERGE_THRESHOLD
        assert verdict.is_duplicate

    def test_unrelated_job_is_not_a_duplicate(self) -> None:
        existing = make_existing(
            normalized_title="marketing manager",
            company_name_raw="XYZ Foods",
            city="Karachi",
            apply_url="https://xyz.com/jobs/7",
            apply_url_hash=apply_url_hash("https://xyz.com/jobs/7"),
            normalized_description="Lead our marketing team and own the brand strategy." * 5,
        )
        verdict = find_duplicate(make_candidate(), [existing])
        assert not verdict.is_duplicate

    def test_no_candidates(self) -> None:
        verdict = find_duplicate(make_candidate(), [])
        assert verdict.confidence == 0.0
        assert verdict.matched_id is None

    def test_best_match_wins(self) -> None:
        weak = make_existing(
            normalized_title="data analyst", company_name_raw="Other Co", city="Multan",
            apply_url="https://o.com/1", apply_url_hash=apply_url_hash("https://o.com/1"),
            normalized_description="Analyse data sets." * 8,
        )
        strong = make_existing(apply_url="https://abc.com/x", apply_url_hash=apply_url_hash("https://abc.com/x"))
        verdict = find_duplicate(make_candidate(), [weak, strong])
        assert verdict.matched_id == strong.id


class TestFingerprint:
    def test_stable_for_equivalent_input(self) -> None:
        assert content_fingerprint("Senior Software Engineer", "ABC Technologies", "Lahore") == \
               content_fingerprint("Software Engineer", "ABC", "lahore")

    def test_differs_for_different_jobs(self) -> None:
        assert content_fingerprint("Software Engineer", "ABC", "Lahore") != \
               content_fingerprint("Data Scientist", "ABC", "Lahore")
