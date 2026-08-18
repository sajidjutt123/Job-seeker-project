"""Unit tests for the normalization engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pakjobs_core.domain.enums import EmploymentType, ExperienceLevel, WorkMode
from pakjobs_core.pipeline.normalizer import (
    company_matching_key,
    extract_deadline,
    extract_skills,
    extract_years_of_experience,
    normalize_company_name,
    normalize_employment_type,
    normalize_experience_level,
    normalize_location,
    normalize_salary,
    normalize_skill_list,
    normalize_title,
    parse_datetime,
    title_comparison_key,
)


class TestNormalizeTitle:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Software Engineer", "Software Engineer"),
            ("  Software   Engineer  ", "Software Engineer"),
            ("URGENT REQUIRED: Software Engineer", "Software Engineer"),
            ("Software Engineer - Lahore", "Software Engineer"),
            ("Software Engineer, Karachi", "Software Engineer"),
            ("Software Engineer - Pakistan", "Software Engineer"),
            ("[Hiring] Data Analyst", "[Hiring] Data Analyst"),
            ("Backend Developer | Node.js", "Backend Developer - Node.js"),
        ],
    )
    def test_cleans_titles(self, raw: str, expected: str) -> None:
        assert normalize_title(raw) == expected

    def test_strips_emoji(self) -> None:
        assert "🚀" not in normalize_title("Software Engineer 🚀")

    def test_shouty_titles_are_recased(self) -> None:
        assert normalize_title("SENIOR SOFTWARE ENGINEER") == "Senior Software Engineer"

    def test_preserves_acronyms_when_recasing(self) -> None:
        assert normalize_title("QA AUTOMATION ENGINEER") == "QA Automation Engineer"

    def test_handles_empty(self) -> None:
        assert normalize_title(None) == ""
        assert normalize_title("") == ""


class TestTitleComparisonKey:
    def test_seniority_is_ignored(self) -> None:
        assert title_comparison_key("Senior Software Engineer") == title_comparison_key("Software Engineer")

    def test_trailing_level_is_ignored(self) -> None:
        assert title_comparison_key("Software Engineer II") == title_comparison_key("Software Engineer")

    def test_different_roles_differ(self) -> None:
        assert title_comparison_key("Software Engineer") != title_comparison_key("Data Scientist")


class TestCompanyNormalization:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("ABC", "ABC Technologies"),
            ("ABC", "ABC (Pvt) Ltd"),
            ("ABC Technologies", "ABC Technologies Private Limited"),
            ("Systems Limited", "Systems"),
        ],
    )
    def test_variants_share_a_key(self, a: str, b: str) -> None:
        """This is the case the spec calls out explicitly."""
        assert company_matching_key(a) == company_matching_key(b)

    def test_different_companies_differ(self) -> None:
        assert company_matching_key("Systems Limited") != company_matching_key("NETSOL Technologies")

    def test_display_name_is_tidied_not_stripped(self) -> None:
        assert normalize_company_name("  ABC Technologies (Pvt) Ltd.  ") == "ABC Technologies (Pvt) Ltd"

    def test_empty_input(self) -> None:
        assert company_matching_key(None) == ""


class TestNormalizeLocation:
    def test_city_and_country(self) -> None:
        result = normalize_location("Lahore, Pakistan")
        assert result.city == "Lahore"
        assert result.province == "Punjab"
        assert result.country == "PK"
        assert result.work_mode == WorkMode.ONSITE

    def test_city_embedded_in_free_text(self) -> None:
        assert normalize_location("Software Engineer - Karachi Office").city == "Karachi"

    def test_remote(self) -> None:
        result = normalize_location("Remote (Pakistan)")
        assert result.is_remote is True
        assert result.work_mode == WorkMode.REMOTE

    def test_hybrid_beats_remote(self) -> None:
        result = normalize_location("Hybrid — Lahore")
        assert result.work_mode == WorkMode.HYBRID
        assert result.is_remote is False
        assert result.city == "Lahore"

    def test_work_from_home_alias(self) -> None:
        assert normalize_location("Work From Home").is_remote is True

    @pytest.mark.parametrize(
        "raw,province",
        [
            ("Peshawar", "Khyber Pakhtunkhwa"),
            ("Quetta", "Balochistan"),
            ("Islamabad", "Islamabad Capital Territory"),
            ("Gilgit", "Gilgit-Baltistan"),
            ("Muzaffarabad", "Azad Jammu and Kashmir"),
            ("Karachi", "Sindh"),
        ],
    )
    def test_province_inference(self, raw: str, province: str) -> None:
        assert normalize_location(raw).province == province

    def test_multiword_city(self) -> None:
        assert normalize_location("Rahim Yar Khan").city == "Rahim Yar Khan"

    def test_city_alias(self) -> None:
        assert normalize_location("Pindi").city == "Rawalpindi"

    def test_unknown_location_is_preserved(self) -> None:
        result = normalize_location("Somewhere Else")
        assert result.city is None
        assert result.location == "Somewhere Else"

    def test_empty(self) -> None:
        result = normalize_location(None)
        assert result.city is None
        assert result.work_mode == WorkMode.UNKNOWN


class TestEmploymentType:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Full Time", EmploymentType.FULL_TIME),
            ("full-time", EmploymentType.FULL_TIME),
            ("Permanent", EmploymentType.FULL_TIME),
            ("Part Time", EmploymentType.PART_TIME),
            ("Contract", EmploymentType.CONTRACT),
            ("Internship", EmploymentType.INTERNSHIP),
            ("Freelance", EmploymentType.FREELANCE),
            ("", EmploymentType.UNKNOWN),
        ],
    )
    def test_mapping(self, raw: str, expected: str) -> None:
        assert normalize_employment_type(raw) == expected

    def test_internship_wins_over_full_time(self) -> None:
        assert normalize_employment_type("Full time internship") == EmploymentType.INTERNSHIP


class TestExperience:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Senior Software Engineer", ExperienceLevel.SENIOR),
            ("Junior Developer", ExperienceLevel.ENTRY),
            ("Software Engineering Intern", ExperienceLevel.INTERN),
            ("Lead Data Scientist", ExperienceLevel.LEAD),
            ("Head of Engineering", ExperienceLevel.EXECUTIVE),
        ],
    )
    def test_from_title(self, title: str, expected: str) -> None:
        assert normalize_experience_level(title) == expected

    def test_years_drive_level_when_title_is_neutral(self) -> None:
        assert normalize_experience_level("Software Engineer", "We need 6+ years of experience") == ExperienceLevel.SENIOR
        assert normalize_experience_level("Software Engineer", "1 year of experience required") == ExperienceLevel.ENTRY

    def test_extract_years_range(self) -> None:
        assert extract_years_of_experience("3-5 years of experience") == (3, 5)
        assert extract_years_of_experience("5+ years experience") == (5, None)
        assert extract_years_of_experience("no numbers here") == (None, None)

    def test_absurd_years_rejected(self) -> None:
        assert extract_years_of_experience("99 years experience") == (None, None)


class TestSalary:
    def test_range_with_currency_and_period(self) -> None:
        result = normalize_salary("Rs. 80,000 - 120,000 per month")
        assert result.min_amount == Decimal("80000")
        assert result.max_amount == Decimal("120000")
        assert result.currency == "PKR"
        assert result.period == "month"

    def test_usd_with_k_suffix(self) -> None:
        result = normalize_salary("USD 60k/year")
        assert result.min_amount == Decimal("60000")
        assert result.currency == "USD"
        assert result.period == "year"

    def test_lac_multiplier(self) -> None:
        assert normalize_salary("Rs. 1.2 lac").min_amount == Decimal("120000")

    def test_structured_fields_take_priority(self) -> None:
        result = normalize_salary(None, min_value=50000, max_value=90000, currency="PKR", period="month")
        assert (result.min_amount, result.max_amount) == (Decimal("50000"), Decimal("90000"))

    def test_inverted_range_is_corrected(self) -> None:
        result = normalize_salary(None, min_value=120000, max_value=80000)
        assert result.min_amount < result.max_amount

    def test_no_salary_returns_nothing(self) -> None:
        result = normalize_salary("Competitive salary")
        assert result.min_amount is None and result.max_amount is None

    def test_years_are_not_mistaken_for_salary(self) -> None:
        assert normalize_salary("Established 2019, apply now").min_amount is None

    def test_period_inferred_from_magnitude(self) -> None:
        assert normalize_salary("PKR 90,000").period == "month"
        assert normalize_salary("PKR 3,000,000").period == "year"


class TestDates:
    def test_iso(self) -> None:
        assert parse_datetime("2026-03-15T10:30:00Z").year == 2026

    def test_unix_seconds_and_millis(self) -> None:
        assert parse_datetime(1767841111).year == 2026
        assert parse_datetime(1767841111000).year == 2026

    def test_relative(self) -> None:
        parsed = parse_datetime("3 days ago")
        assert parsed is not None
        assert (datetime.now(timezone.utc) - parsed).days == 3

    def test_common_formats(self) -> None:
        for value in ("2026-03-15", "15-03-2026", "15 Mar 2026", "Mar 15, 2026"):
            assert parse_datetime(value) is not None, value

    def test_always_timezone_aware(self) -> None:
        assert parse_datetime("2026-03-15").tzinfo is not None

    def test_garbage_returns_none(self) -> None:
        assert parse_datetime("not a date") is None
        assert parse_datetime(None) is None

    def test_deadline_extraction(self) -> None:
        future = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%d %b %Y")
        assert extract_deadline(f"Last date to apply: {future}") is not None

    def test_absurd_deadline_rejected(self) -> None:
        assert extract_deadline("Last date: 15 Mar 1999") is None


class TestSkills:
    def test_extraction(self) -> None:
        skills = extract_skills("Senior Python Developer", "Django, PostgreSQL, Docker and AWS required")
        assert {"Python", "Django", "PostgreSQL", "Docker", "AWS"} <= set(skills)

    def test_no_false_positive_substrings(self) -> None:
        # "go" inside "going" must not match the Go language.
        assert "Go" not in extract_skills("Ongoing project management role", "")

    def test_alias_canonicalisation(self) -> None:
        assert normalize_skill_list(["reactjs", "postgres"]) == ["React", "PostgreSQL"]

    def test_deduplicates(self) -> None:
        assert normalize_skill_list(["Python", "python", "PYTHON"]) == ["Python"]

    def test_empty(self) -> None:
        assert extract_skills(None, None) == []
        assert normalize_skill_list(None) == []
