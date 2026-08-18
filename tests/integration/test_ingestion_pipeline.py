"""Integration tests for the full ingestion pipeline against a real database.

Covers the acceptance criteria path: source → fetch → parse → normalize → validate → classify
→ dedupe → quality → persist → searchable → expirable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from pakjobs_core.connectors.base import SourceConnector
from pakjobs_core.domain.enums import JobStatus, SourceRunStatus, SourceStatus, SourceType
from pakjobs_core.models import Company, Job, JobDuplicate, JobEvent, JobSource, Skill
from pakjobs_core.pipeline.schemas import FetchResult, RawJob, SourceMetadata
from pakjobs_core.services.expiration import ExpirationService
from pakjobs_core.services.ingestion import IngestionService

NOW = datetime.now(timezone.utc)


class StubConnector(SourceConnector):
    """In-memory connector — exercises the real pipeline without any network access."""

    key = "test_stub"
    payloads: list[RawJob] = []
    should_fail: str | None = None

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key, name="Test Stub", type=SourceType.API,
            description="Test connector", default_reliability=0.85,
        )

    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        if self.should_fail:
            return FetchResult(ok=False, error=self.should_fail, error_type="ConnectorError")
        return FetchResult(jobs=list(self.payloads), ok=True, stats={"stub": True})


@pytest.fixture(autouse=True)
def register_stub():
    from pakjobs_core.connectors.registry import _REGISTRY

    _REGISTRY[StubConnector.key] = StubConnector
    StubConnector.payloads = []
    StubConnector.should_fail = None
    yield
    _REGISTRY.pop(StubConnector.key, None)


@pytest.fixture
def source(session) -> JobSource:
    src = JobSource(
        name="Test Source", slug=f"test-source-{datetime.now().timestamp()}",
        type=SourceType.API, connector_key=StubConnector.key,
        enabled=True, reliability_score=0.85, fetch_interval_minutes=30,
    )
    session.add(src)
    session.flush()
    return src


def raw(**overrides) -> RawJob:
    defaults = dict(
        source_job_id="job-1",
        title="Senior Python Developer",
        apply_url="https://employer.example.com/jobs/1",
        company_name="ABC Technologies (Pvt) Ltd",
        description_text=(
            "We are hiring a senior Python developer in Lahore.\n\n"
            "Responsibilities:\n- Design and build REST APIs\n- Mentor junior engineers\n\n"
            "Requirements:\n- 5 years of Python experience\n- Strong PostgreSQL and Docker skills\n"
        ),
        location_raw="Lahore, Pakistan",
        employment_type_raw="Full Time",
        salary_raw="PKR 250,000 - 400,000 per month",
        posted_at_raw=(NOW - timedelta(days=1)).isoformat(),
    )
    defaults.update(overrides)
    return RawJob(**defaults)


class TestIngestionHappyPath:
    def test_job_is_fully_normalised_and_persisted(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        run = IngestionService(session).run_source(source, trigger="test")

        assert run.status == SourceRunStatus.SUCCESS
        assert run.created_count == 1

        job = session.execute(select(Job)).unique().scalar_one()
        assert job.title == "Senior Python Developer"
        assert job.city == "Lahore"
        assert job.province == "Punjab"
        assert job.country == "PK"
        assert job.employment_type == "full_time"
        assert job.experience_level == "senior"
        assert job.category == "software-engineering"
        assert job.salary_min == 250000
        assert job.salary_max == 400000
        assert job.salary_currency == "PKR"
        assert job.status == JobStatus.ACTIVE
        assert job.quality_score > 0
        assert job.slug
        assert job.apply_url_hash
        assert job.content_fingerprint

    def test_company_is_created_and_linked(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        company = session.execute(select(Company)).scalar_one()
        assert company.normalized_name == "abc"
        job = session.execute(select(Job)).unique().scalar_one()
        assert job.company_id == company.id

    def test_skills_are_extracted_and_linked(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        skill_names = {s.name for s in session.execute(select(Skill)).scalars()}
        assert {"Python", "PostgreSQL", "Docker"} <= skill_names

    def test_creation_event_is_recorded(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        events = list(session.execute(select(JobEvent)).scalars())
        assert any(e.event_type == "created" for e in events)

    def test_source_health_is_updated(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        session.refresh(source)
        assert source.status == SourceStatus.HEALTHY
        assert source.total_runs == 1
        assert source.total_jobs_collected == 1
        assert source.consecutive_failures == 0
        assert source.last_success_at is not None


class TestIdempotency:
    def test_rerunning_updates_instead_of_duplicating(self, session, source) -> None:
        service = IngestionService(session)
        StubConnector.payloads = [raw()]
        service.run_source(source, trigger="test")
        run2 = service.run_source(source, trigger="test")

        assert run2.created_count == 0
        assert run2.updated_count == 1
        assert session.execute(select(func.count(Job.id))).scalar_one() == 1

    def test_changed_fields_are_refreshed(self, session, source) -> None:
        service = IngestionService(session)
        StubConnector.payloads = [raw()]
        service.run_source(source, trigger="test")

        StubConnector.payloads = [raw(salary_raw="PKR 300,000 - 500,000 per month")]
        service.run_source(source, trigger="test")

        job = session.execute(select(Job)).unique().scalar_one()
        assert job.salary_max == 500000


class TestDuplicateDetection:
    def test_same_job_from_two_sources_is_linked(self, session, source) -> None:
        service = IngestionService(session)
        StubConnector.payloads = [raw()]
        service.run_source(source, trigger="test")

        other = JobSource(
            name="Aggregator", slug="aggregator-test", type=SourceType.API,
            connector_key=StubConnector.key, enabled=True, reliability_score=0.6,
        )
        session.add(other)
        session.flush()

        # Same role, different source, shortened company name and different URL.
        StubConnector.payloads = [
            raw(source_job_id="agg-1", company_name="ABC",
                apply_url="https://aggregator.example.com/listing/55")
        ]
        service.run_source(other, trigger="test")

        links = list(session.execute(select(JobDuplicate)).scalars())
        assert len(links) == 1
        assert links[0].confidence >= 0.68
        assert "title" in links[0].signals

        canonical_count = session.execute(
            select(func.count(Job.id)).where(Job.is_canonical.is_(True))
        ).scalar_one()
        assert canonical_count == 1, "users must see exactly one canonical job"

    def test_distinct_jobs_are_not_merged(self, session, source) -> None:
        StubConnector.payloads = [
            raw(),
            raw(source_job_id="job-2", title="Marketing Manager", company_name="XYZ Foods",
                apply_url="https://xyz.example.com/jobs/2", location_raw="Karachi",
                description_text="Lead the brand marketing team and own campaign strategy." * 5),
        ]
        IngestionService(session).run_source(source, trigger="test")

        assert session.execute(select(func.count(JobDuplicate.id))).scalar_one() == 0
        assert session.execute(select(func.count(Job.id))).scalar_one() == 2


class TestValidationGate:
    def test_invalid_jobs_are_rejected(self, session, source) -> None:
        StubConnector.payloads = [
            raw(),
            raw(source_job_id="bad-1", apply_url="javascript:alert(1)"),
            raw(source_job_id="bad-2", title="X"),
        ]
        run = IngestionService(session).run_source(source, trigger="test")

        assert run.created_count == 1
        assert run.rejected_count == 2
        assert session.execute(select(func.count(Job.id))).scalar_one() == 1

    def test_scam_listing_never_reaches_the_database(self, session, source) -> None:
        StubConnector.payloads = [
            raw(source_job_id="scam-1",
                description_text="Earn Rs 8000 daily. Pay 500 to register and join today!")
        ]
        run = IngestionService(session).run_source(source, trigger="test")

        assert run.created_count == 0
        assert "suspected_scam" in run.stats["rejection_reasons"]

    def test_suspicious_job_is_held_for_review(self, session, source) -> None:
        StubConnector.payloads = [
            raw(source_job_id="mlm-1",
                description_text="Network marketing opportunity. Be your own boss! " * 8)
        ]
        IngestionService(session).run_source(source, trigger="test")

        job = session.execute(select(Job)).unique().scalar_one()
        assert job.status == JobStatus.PENDING_REVIEW


class TestFailureHandling:
    def test_connector_failure_is_recorded_not_raised(self, session, source) -> None:
        StubConnector.should_fail = "Source returned HTTP 500"
        run = IngestionService(session).run_source(source, trigger="test")

        assert run.status == SourceRunStatus.FAILED
        assert run.error_message == "Source returned HTTP 500"

        session.refresh(source)
        assert source.consecutive_failures == 1
        assert source.error_count == 1
        assert source.last_error == "Source returned HTTP 500"

    def test_repeated_failures_mark_the_source_failing(self, session, source) -> None:
        StubConnector.should_fail = "boom"
        service = IngestionService(session)
        for _ in range(5):
            service.run_source(source, trigger="test")

        session.refresh(source)
        assert source.status == SourceStatus.FAILING

    def test_recovery_clears_the_failure_state(self, session, source) -> None:
        service = IngestionService(session)
        StubConnector.should_fail = "boom"
        service.run_source(source, trigger="test")

        StubConnector.should_fail = None
        StubConnector.payloads = [raw()]
        service.run_source(source, trigger="test")

        session.refresh(source)
        assert source.status == SourceStatus.HEALTHY
        assert source.consecutive_failures == 0

    def test_one_bad_record_does_not_abort_the_batch(self, session, source) -> None:
        StubConnector.payloads = [
            raw(source_job_id="ok-1"),
            raw(source_job_id="bad-1", apply_url="not-a-url"),
            raw(source_job_id="ok-2", title="Data Analyst",
                apply_url="https://employer.example.com/jobs/3"),
        ]
        run = IngestionService(session).run_source(source, trigger="test")
        assert run.created_count == 2
        assert run.rejected_count == 1


class TestExpiration:
    def test_deadline_passed_expires_the_job(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        job = session.execute(select(Job)).unique().scalar_one()
        job.deadline = NOW - timedelta(days=2)
        session.flush()

        expired = ExpirationService(session).expire_past_deadline()
        assert expired == 1
        session.refresh(job)
        assert job.status == JobStatus.EXPIRED
        assert job.expired_at is not None

    def test_unseen_jobs_expire(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        job = session.execute(select(Job)).unique().scalar_one()
        job.last_seen_at = NOW - timedelta(days=40)
        session.flush()

        assert ExpirationService(session).expire_unseen(unseen_days=21) == 1
        session.refresh(job)
        assert job.status == JobStatus.EXPIRED

    def test_recent_jobs_are_left_alone(self, session, source) -> None:
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        assert ExpirationService(session).expire_unseen(unseen_days=21) == 0

    def test_republished_job_is_reactivated(self, session, source) -> None:
        service = IngestionService(session)
        StubConnector.payloads = [raw()]
        service.run_source(source, trigger="test")

        job = session.execute(select(Job)).unique().scalar_one()
        job.status = JobStatus.EXPIRED
        session.flush()

        service.run_source(source, trigger="test")
        session.refresh(job)
        assert job.status == JobStatus.ACTIVE

        events = list(session.execute(select(JobEvent)).scalars())
        assert any(e.event_type == "reactivated" for e in events)


class TestFullTextSearchIndex:
    def test_search_vector_is_populated_by_postgres(self, session, source) -> None:
        """Proves the generated tsvector column works — the basis of all search."""
        StubConnector.payloads = [raw()]
        IngestionService(session).run_source(source, trigger="test")

        found = session.execute(
            select(Job).where(Job.search_vector.op("@@")(func.websearch_to_tsquery("english", "python")))
        ).unique().scalar_one_or_none()
        assert found is not None

        missing = session.execute(
            select(Job).where(Job.search_vector.op("@@")(func.websearch_to_tsquery("english", "welding")))
        ).unique().scalar_one_or_none()
        assert missing is None
