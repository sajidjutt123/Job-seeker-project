"""End-to-end user journeys.

These drive the **frontend** over real HTTP the way a browser does — following redirects,
carrying cookies across requests, and asserting on rendered HTML — rather than calling the API
directly. They catch the class of bug integration tests miss: a page that renders but shows an
error state, a redirect that never fires, SSR that fails to pass the session through, or a
missing attribution link.

A headless-browser suite (Playwright) is the right tool for click-level interaction and visual
regression; the browser binary cannot be downloaded in this environment, so these cover the same
journeys at the transport level. `docs/DEVELOPMENT.md` documents how to add the Playwright layer.

Skips automatically unless both the web and API servers are running.
"""

from __future__ import annotations

import os
import re
import uuid

import httpx
import pytest

WEB = os.environ.get("TEST_WEB_URL", "http://localhost:3000")
API = os.environ.get("TEST_API_URL", "http://localhost:8000")


def _stack_up() -> bool:
    try:
        return (
            httpx.get(f"{WEB}/", timeout=5).status_code == 200
            and httpx.get(f"{API}/health/live", timeout=5).status_code == 200
        )
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _stack_up(), reason="web + API servers are not running")


def _visitor_headers() -> dict[str, str]:
    """Give each test a distinct client IP.

    The web tier forwards the visitor's IP to the API, so without this the whole suite is
    charged to one rate-limit bucket and later tests fail for reasons unrelated to what they
    assert. This mirrors how real traffic arrives through a proxy.
    """
    return {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


@pytest.fixture
def browser():
    """A cookie-carrying client that follows redirects, like a real browser."""
    with httpx.Client(
        base_url=WEB, timeout=30, follow_redirects=True, headers=_visitor_headers()
    ) as client:
        yield client


def text_of(response: httpx.Response) -> str:
    """Strip tags so assertions match visible copy, not markup."""
    return re.sub(r"<[^>]+>", " ", response.text)


class TestJobSeekerDiscoversAJob:
    """The core journey: land, search, filter, open a job, reach the employer."""

    def test_homepage_shows_real_inventory(self, browser) -> None:
        page = browser.get("/")
        assert page.status_code == 200
        body = text_of(page)
        assert "Find the right job in Pakistan" in body
        # Not an empty shell: the homepage must render actual counts and listings.
        assert "Active jobs" in body
        assert "Latest jobs" in body

    def test_search_returns_results_not_an_error_state(self, browser) -> None:
        page = browser.get("/jobs", params={"q": "engineer"})
        assert page.status_code == 200
        body = text_of(page)
        assert "jobs found" in body
        assert "Search is unavailable" not in body
        assert "Something went wrong" not in body

    def test_search_with_no_matches_shows_guidance_not_a_crash(self, browser) -> None:
        page = browser.get("/jobs", params={"q": "zzqq-not-a-real-job-xyz"})
        assert page.status_code == 200
        body = text_of(page)
        assert "No jobs found" in body
        # An empty state must offer a way forward.
        assert "alert" in body.lower()

    def test_filters_are_reflected_in_the_url_and_page(self, browser) -> None:
        page = browser.get("/jobs", params={"remote": "true"})
        assert page.status_code == 200
        assert "Remote jobs" in text_of(page)

    def test_job_detail_reaches_the_original_source(self, browser) -> None:
        """The whole product promise: attribution plus a working apply link."""
        listing = httpx.get(
            f"{API}/api/v1/jobs", params={"page_size": 1}, timeout=15, headers=_visitor_headers()
        ).json()
        if not listing["items"]:
            pytest.skip("no jobs indexed")
        job = listing["items"][0]

        page = browser.get(f"/jobs/{job['slug']}")
        assert page.status_code == 200
        body = text_of(page)

        assert job["title"][:30] in page.text
        assert "Apply on original source" in body
        assert "Where this job came from" in body
        # The real apply URL must be present and point off-site.
        assert job["apply_url"] in page.text
        # Candidate-safety notice must survive template changes.
        assert "never" in body.lower() and "fee" in body.lower()

    def test_job_detail_emits_structured_data(self, browser) -> None:
        listing = httpx.get(
            f"{API}/api/v1/jobs", params={"page_size": 1}, timeout=15, headers=_visitor_headers()
        ).json()
        if not listing["items"]:
            pytest.skip("no jobs indexed")
        page = browser.get(f"/jobs/{listing['items'][0]['slug']}")
        assert '"@type":"JobPosting"' in page.text.replace(" ", "")

    def test_unknown_job_shows_a_404_page_and_is_not_indexable(self, browser) -> None:
        """A removed job must never be presented — or indexed — as a live listing.

        The `noindex` directive is the assertion that matters: on Next.js 16 a `notFound()` in a
        route that also exports `generateMetadata` renders under HTTP 200, so the status code
        alone is not a reliable signal here.
        """
        page = browser.get("/jobs/definitely-not-a-real-slug-xyz")
        assert "could not find" in text_of(page).lower()
        assert 'name="robots" content="noindex"' in page.text.replace("'", '"')

    def test_a_real_job_stays_indexable(self, browser) -> None:
        listing = httpx.get(
            f"{API}/api/v1/jobs", params={"page_size": 1}, timeout=15, headers=_visitor_headers()
        ).json()
        if not listing["items"]:
            pytest.skip("no jobs indexed")
        page = browser.get(f"/jobs/{listing['items'][0]['slug']}")
        assert "noindex" not in page.text


class TestSeoLandingPages:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/jobs-in-lahore", "Jobs in Lahore"),
            ("/jobs-in-karachi", "Jobs in Karachi"),
            ("/remote-jobs", "Remote jobs in Pakistan"),
            ("/government-jobs", "Government jobs in Pakistan"),
            ("/internships", "Internships in Pakistan"),
        ],
    )
    def test_landing_pages_render(self, browser, path: str, expected: str) -> None:
        page = browser.get(path)
        assert page.status_code == 200
        assert expected in text_of(page)

    def test_unknown_city_does_not_generate_a_thin_page(self, browser) -> None:
        page = browser.get("/jobs-in-notarealcity")
        assert "could not find" in text_of(page).lower()

    def test_sitemap_lists_real_jobs(self, browser) -> None:
        page = browser.get("/sitemap.xml")
        assert page.status_code == 200
        assert "<urlset" in page.text
        assert "/jobs/" in page.text

    def test_robots_protects_private_areas(self, browser) -> None:
        body = browser.get("/robots.txt").text
        assert "Sitemap:" in body
        for private in ("/admin", "/dashboard", "/api/"):
            assert private in body

    def test_sources_page_is_transparent_about_aggregation(self, browser) -> None:
        body = text_of(browser.get("/sources"))
        assert "Where our jobs come from" in body
        assert "bypass" in body.lower()


class TestAccountJourney:
    """Register → land on the dashboard → save a job → see it persisted."""

    def test_full_signup_and_save_flow(self) -> None:
        """Saved jobs render client-side, so this asserts the page loads for a signed-in user
        rather than grepping SSR HTML for the job title."""
        email = f"e2e-{uuid.uuid4().hex[:10]}@example.com"

        with httpx.Client(timeout=30, follow_redirects=True, headers=_visitor_headers()) as client:
            # Register through the API the way the browser form does, keeping the cookies.
            registered = client.post(
                f"{API}/api/v1/auth/register",
                json={"email": email, "password": "TestPass123", "full_name": "E2E User"},
            )
            assert registered.status_code == 201
            assert client.cookies.get("rozgar_access")

            # SSR must recognise the session and render the private dashboard.
            dashboard = client.get(f"{WEB}/dashboard")
            assert dashboard.status_code == 200
            assert "/login" not in str(dashboard.url), "signed-in user was bounced to login"
            body = text_of(dashboard)
            assert "Saved jobs" in body
            assert "Profile complete" in body

            # Save a job, then confirm the saved page reflects it.
            listing = client.get(f"{API}/api/v1/jobs", params={"page_size": 1}).json()
            if not listing["items"]:
                pytest.skip("no jobs indexed")
            job = listing["items"][0]

            saved = client.post(f"{API}/api/v1/saved-jobs/{job['id']}", json={})
            assert saved.status_code == 201

            page = client.get(f"{WEB}/dashboard/saved")
            assert page.status_code == 200
            assert "/login" not in str(page.url)
            assert "Saved jobs" in text_of(page)

            # The data itself is asserted at the API layer, which is what the client fetches.
            saved_list = client.get(f"{API}/api/v1/saved-jobs").json()
            assert saved_list["total"] == 1
            assert saved_list["items"][0]["job"]["id"] == job["id"]

    def test_signed_out_visitor_is_sent_to_login_and_told_where_back_to(self, browser) -> None:
        page = browser.get("/dashboard/saved")
        assert "/login" in str(page.url)
        assert "next=" in str(page.url)
        assert "Sign in" in text_of(page)

    def test_login_page_offers_recovery(self, browser) -> None:
        body = text_of(browser.get("/login"))
        assert "Forgot password" in body
        assert "Create an account" in body


class TestAdminJourney:
    def test_regular_user_cannot_reach_the_admin_console(self) -> None:
        headers = {"X-Forwarded-For": f"203.0.113.{uuid.uuid4().int % 200 + 1}"}
        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            registered = client.post(
                f"{API}/api/v1/auth/register",
                json={"email": f"e2e-reg-{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123"},
            )
            assert registered.status_code == 201

            page = client.get(f"{WEB}/admin")
            # No admin chrome is rendered for a non-admin, whatever the final URL.
            body = text_of(page)
            assert "Admin mode" not in body
            assert "Audit log" not in body

    def test_admin_sees_the_console(self) -> None:
        headers = {"X-Forwarded-For": f"203.0.113.{uuid.uuid4().int % 200 + 1}"}
        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            login = client.post(
                f"{API}/api/v1/auth/login",
                json={"email": "admin@rozgar.pk", "password": "AdminPass123"},
            )
            if login.status_code != 200:
                pytest.skip("no admin account in this environment")

            page = client.get(f"{WEB}/admin")
            assert page.status_code == 200
            body = text_of(page)
            assert "Admin mode" in body
            assert "Overview" in body

            for section in ("/admin/jobs", "/admin/sources", "/admin/users", "/admin/reports"):
                assert client.get(f"{WEB}{section}").status_code == 200, section


class TestResilience:
    def test_pages_do_not_leak_internals_on_error(self, browser) -> None:
        """No stack traces, SQL or connection strings in any rendered page."""
        for path in ("/", "/jobs", "/jobs/does-not-exist", "/dashboard"):
            body = browser.get(path).text.lower()
            for leak in ("traceback", "psycopg", "sqlalchemy.exc", "postgresql://", "jwt_secret"):
                assert leak not in body, f"{path} leaked {leak}"

    def test_security_headers_on_html_responses(self, browser) -> None:
        headers = browser.get("/").headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert "Referrer-Policy" in headers

    def test_html_pages_are_not_absurdly_heavy(self, browser) -> None:
        """A first-load regression guard for users on slow mobile connections."""
        size = len(browser.get("/").content)
        assert size < 600_000, f"homepage HTML is {size // 1024} KB"
