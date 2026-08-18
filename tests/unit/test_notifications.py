"""Unit tests for notification rendering and unsubscribe signing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pakjobs_core.services.notifications import render_alert_email
from pakjobs_core.services.security import sign_unsubscribe, verify_unsubscribe

UNSUB = "https://rozgar.pk/unsubscribe?alert=abc&token=deadbeef"


def fake_job(**overrides):
    defaults = dict(
        title="Senior Python Developer",
        slug="senior-python-developer-abc-lahore",
        company_name_raw="ABC Technologies",
        location="Lahore, Punjab",
        is_remote=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestUnsubscribeSigning:
    def test_token_is_stable(self) -> None:
        assert sign_unsubscribe("alert-1") == sign_unsubscribe("alert-1")

    def test_token_differs_per_alert(self) -> None:
        assert sign_unsubscribe("alert-1") != sign_unsubscribe("alert-2")

    def test_valid_token_verifies(self) -> None:
        assert verify_unsubscribe("alert-1", sign_unsubscribe("alert-1"))

    @pytest.mark.parametrize("bad", ["", "deadbeef", "0" * 32, None])
    def test_forged_tokens_are_rejected(self, bad) -> None:
        assert not verify_unsubscribe("alert-1", bad)

    def test_token_for_another_alert_is_rejected(self) -> None:
        """Prevents unsubscribing someone else by swapping the id in the URL."""
        assert not verify_unsubscribe("alert-2", sign_unsubscribe("alert-1"))

    def test_token_is_not_trivially_guessable(self) -> None:
        token = sign_unsubscribe("alert-1")
        assert len(token) >= 32
        assert "alert-1" not in token


class TestAlertEmail:
    def test_subject_reflects_count(self) -> None:
        subject, _, _ = render_alert_email("SE Lahore", [fake_job()], "https://rozgar.pk")
        assert "1 new job" in subject
        subject, _, _ = render_alert_email("SE Lahore", [fake_job(), fake_job()], "https://rozgar.pk")
        assert "2 new jobs" in subject

    def test_both_bodies_list_every_job(self) -> None:
        jobs = [fake_job(slug="a", title="Job A"), fake_job(slug="b", title="Job B")]
        _, text, html = render_alert_email("Alert", jobs, "https://rozgar.pk")
        for fragment in ("Job A", "Job B", "/jobs/a", "/jobs/b"):
            assert fragment in text, fragment
            assert fragment in html, fragment

    def test_plain_text_alternative_always_present(self) -> None:
        """Plenty of Pakistani users read mail in clients that block HTML."""
        _, text, _ = render_alert_email("Alert", [fake_job()], "https://rozgar.pk")
        assert "<" not in text
        assert "Senior Python Developer" in text

    def test_unsubscribe_link_appears_in_both_bodies(self) -> None:
        _, text, html = render_alert_email(
            "Alert", [fake_job()], "https://rozgar.pk", unsubscribe_url=UNSUB
        )
        assert UNSUB in text
        assert UNSUB in html
        assert "unsubscribe" in html.lower()

    def test_omitting_unsubscribe_still_renders(self) -> None:
        _, text, html = render_alert_email("Alert", [fake_job()], "https://rozgar.pk")
        assert "Manage your alerts" in text
        assert "<html>" in html.lower() or "<html" in html.lower()

    def test_html_is_escaped(self) -> None:
        """A job title from an external source must never inject markup into our email."""
        job = fake_job(title='<script>alert(1)</script>', company_name_raw='A & B "Co"')
        _, _, html = render_alert_email("Alert", [job], "https://rozgar.pk")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html

    def test_missing_company_and_location_are_handled(self) -> None:
        job = fake_job(company_name_raw=None, location=None, is_remote=True)
        _, text, _ = render_alert_email("Alert", [job], "https://rozgar.pk")
        assert "Company not stated" in text
        assert "Remote" in text
