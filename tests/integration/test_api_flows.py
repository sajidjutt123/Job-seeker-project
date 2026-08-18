"""End-to-end API tests against the running application and a real database.

These exercise the HTTP surface exactly as the frontend does: register → search → save →
alert → admin, plus the authorization and error-handling contracts.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("TEST_API_URL", "http://localhost:8000")
API = f"{BASE_URL}/api/v1"

# The API rate-limits per client identity. A fast test suite legitimately exceeds a human
# browsing rate, so each test client gets a distinct identity via X-Forwarded-For. This
# exercises the same middleware path production uses behind a proxy.
def _identity_headers() -> dict[str, str]:
    octet = uuid.uuid4().int % 250 + 1
    return {"X-Forwarded-For": f"198.51.100.{octet}"}


def api_available() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/health/live", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not api_available(), reason="API server is not running")


@pytest.fixture
def client():
    with httpx.Client(base_url=API, timeout=30, follow_redirects=False,
                      headers=_identity_headers()) as c:
        yield c


@pytest.fixture
def user_client():
    """A freshly registered, signed-in user with cookies held by the client."""
    with httpx.Client(base_url=API, timeout=30, headers=_identity_headers()) as c:
        email = f"test-{uuid.uuid4().hex[:12]}@example.com"
        response = c.post("/auth/register", json={
            "email": email, "password": "TestPass123", "full_name": "Test User", "city": "Lahore",
        })
        assert response.status_code == 201, response.text
        c.email = email  # type: ignore[attr-defined]
        yield c


class TestHealth:
    def test_liveness(self) -> None:
        assert httpx.get(f"{BASE_URL}/health/live", timeout=10).json()["status"] == "ok"

    def test_health_reports_components(self) -> None:
        payload = httpx.get(f"{BASE_URL}/health", timeout=15).json()
        assert payload["status"] in ("ok", "degraded", "unhealthy")
        assert "database" in payload["components"]
        assert "redis" in payload["components"]
        assert "worker" in payload["components"]

    def test_health_never_leaks_secrets(self) -> None:
        body = httpx.get(f"{BASE_URL}/health", timeout=15).text
        assert "password" not in body.lower()
        assert "jwt_secret" not in body.lower()


class TestPublicSearch:
    def test_search_returns_page_envelope(self, client) -> None:
        payload = client.get("/jobs", params={"page_size": 5}).json()
        assert {"items", "total", "page", "page_size", "total_pages", "has_next"} <= payload.keys()
        assert len(payload["items"]) <= 5

    def test_every_job_carries_attribution(self, client) -> None:
        """Source attribution is a hard product requirement, not a nice-to-have."""
        for job in client.get("/jobs", params={"page_size": 10}).json()["items"]:
            assert job["source"] is not None
            assert job["source"]["name"]
            assert job["apply_url"].startswith("http")

    def test_keyword_search(self, client) -> None:
        payload = client.get("/jobs", params={"q": "engineer", "page_size": 5}).json()
        assert payload["total"] >= 0
        assert payload["took_ms"] >= 0

    def test_filters_narrow_results(self, client) -> None:
        everything = client.get("/jobs", params={"page_size": 1}).json()["total"]
        remote = client.get("/jobs", params={"remote": "true", "page_size": 1}).json()["total"]
        assert remote <= everything

    def test_facets(self, client) -> None:
        payload = client.get("/jobs", params={"facets": "true", "page_size": 1}).json()
        assert "city" in payload["facets"]
        assert "category" in payload["facets"]

    def test_nonsense_query_returns_empty_not_error(self, client) -> None:
        payload = client.get("/jobs", params={"q": "zzqqxx-not-a-real-job"}).json()
        assert payload["total"] == 0
        assert payload["items"] == []

    def test_invalid_page_size_is_rejected(self, client) -> None:
        assert client.get("/jobs", params={"page_size": 9999}).status_code == 422

    def test_sort_options_all_work(self, client) -> None:
        for sort in ("newest", "relevance", "deadline", "salary"):
            assert client.get("/jobs", params={"sort": sort, "page_size": 3}).status_code == 200

    def test_facets_endpoint(self, client) -> None:
        payload = client.get("/jobs/facets").json()
        assert "totals" in payload and "active" in payload["totals"]
        assert isinstance(payload["categories"], list)

    def test_job_detail_and_404(self, client) -> None:
        items = client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        detail = client.get(f"/jobs/{items[0]['slug']}").json()
        assert detail["slug"] == items[0]["slug"]
        assert "description" in detail
        assert detail["source"] is not None

        missing = client.get("/jobs/definitely-not-a-real-slug-xyz")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"

    def test_structured_data_is_valid_schema_org(self, client) -> None:
        items = client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        data = client.get(f"/seo/jobs/{items[0]['slug']}/structured-data").json()
        assert data["@type"] == "JobPosting"
        assert data["@context"] == "https://schema.org/"
        assert data["title"] and data["datePosted"]


class TestAuthentication:
    def test_register_login_logout_cycle(self) -> None:
        with httpx.Client(base_url=API, timeout=30, headers=_identity_headers()) as c:
            email = f"cycle-{uuid.uuid4().hex[:10]}@example.com"

            assert c.post("/auth/register", json={"email": email, "password": "TestPass123"}).status_code == 201
            assert c.get("/auth/me").json()["user"]["email"] == email

            c.post("/auth/logout")
            assert c.get("/auth/me").status_code == 401

            assert c.post("/auth/login", json={"email": email, "password": "TestPass123"}).status_code == 200
            assert c.get("/auth/me").json()["user"]["email"] == email

    def test_weak_passwords_are_rejected(self, client) -> None:
        response = client.post("/auth/register", json={
            "email": f"weak-{uuid.uuid4().hex[:8]}@example.com", "password": "password",
        })
        assert response.status_code == 422
        assert "password" in response.json()["error"].get("details", {}).get("fields", {})

    def test_short_password_rejected_by_schema(self, client) -> None:
        response = client.post("/auth/register", json={
            "email": f"short-{uuid.uuid4().hex[:8]}@example.com", "password": "ab1",
        })
        assert response.status_code == 422

    def test_duplicate_email_conflicts(self, user_client) -> None:
        response = user_client.post("/auth/register", json={
            "email": user_client.email, "password": "TestPass123",  # type: ignore[attr-defined]
        })
        assert response.status_code == 409

    def test_wrong_password_is_generic(self, user_client) -> None:
        response = user_client.post("/auth/login", json={
            "email": user_client.email, "password": "WrongPass123",  # type: ignore[attr-defined]
        })
        assert response.status_code == 401
        # Must not reveal whether the account exists.
        assert "incorrect email or password" in response.json()["error"]["message"].lower()

    def test_unknown_email_gives_same_error(self, client) -> None:
        response = client.post("/auth/login", json={
            "email": "nobody-here-at-all@example.com", "password": "TestPass123",
        })
        assert response.status_code == 401
        assert "incorrect email or password" in response.json()["error"]["message"].lower()

    def test_forgot_password_never_reveals_account_existence(self, client) -> None:
        known = client.post("/auth/forgot-password", json={"email": "admin@rozgar.pk"})
        unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 200
        assert known.json()["message"] == unknown.json()["message"]

    def test_protected_routes_require_auth(self, client) -> None:
        for path in ("/auth/me", "/saved-jobs", "/alerts", "/profile", "/notifications"):
            assert client.get(path).status_code == 401, path

    def test_invalid_token_is_rejected(self, client) -> None:
        response = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401

    def test_google_config_is_advertised(self, client) -> None:
        assert "enabled" in client.get("/auth/google/config").json()


class TestSavedJobsFlow:
    def test_save_list_and_remove(self, user_client) -> None:
        items = user_client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        job_id = items[0]["id"]

        assert user_client.post(f"/saved-jobs/{job_id}", json={"note": "Interesting"}).status_code == 201
        assert user_client.post(f"/saved-jobs/{job_id}", json={}).status_code == 409

        saved = user_client.get("/saved-jobs").json()
        assert saved["total"] == 1
        assert saved["items"][0]["note"] == "Interesting"
        assert saved["items"][0]["job"]["id"] == job_id

        # Detail view reflects the saved state for this user.
        assert user_client.get(f"/jobs/{items[0]['slug']}").json()["is_saved"] is True

        assert user_client.delete(f"/saved-jobs/{job_id}").status_code == 200
        assert user_client.get("/saved-jobs").json()["total"] == 0
        assert user_client.delete(f"/saved-jobs/{job_id}").status_code == 404

    def test_saving_a_missing_job_404s(self, user_client) -> None:
        assert user_client.post(f"/saved-jobs/{uuid.uuid4()}", json={}).status_code == 404


class TestProfileAndRecommendations:
    def test_profile_completion_increases(self, user_client) -> None:
        before = user_client.get("/profile").json()["profile_completion"]

        updated = user_client.put("/profile", json={
            "skills": ["Python", "React", "PostgreSQL", "Docker"],
            "preferred_categories": ["software-engineering"],
            "preferred_locations": ["Lahore"],
            "preferred_job_types": ["full_time"],
            "experience_level": "mid",
            "years_of_experience": 4,
            "education_level": "bachelors",
            "degree": "BS Computer Science",
            "expected_salary_min": 200000,
            "remote_preference": "hybrid",
        }).json()

        assert updated["profile_completion"] > before
        assert updated["skills"] == ["Python", "React", "PostgreSQL", "Docker"]
        assert updated["province"] == "Punjab", "province should be derived from city"

    def test_invalid_remote_preference_rejected(self, user_client) -> None:
        assert user_client.put("/profile", json={"remote_preference": "teleport"}).status_code == 422

    def test_recommendations_carry_scores_and_reasons(self, user_client) -> None:
        user_client.put("/profile", json={
            "skills": ["Python", "Django"],
            "preferred_categories": ["software-engineering"],
            "preferred_locations": ["Lahore"],
            "experience_level": "mid",
        })
        recommendations = user_client.get("/jobs/recommended", params={"limit": 5}).json()
        assert isinstance(recommendations, list)
        for job in recommendations:
            assert job["match_score"] is not None
            assert 0 <= job["match_score"] <= 100

    def test_anonymous_recommendations_are_empty_not_an_error(self, client) -> None:
        assert client.get("/jobs/recommended").json() == []


class TestAlertsFlow:
    def test_create_preview_update_delete(self, user_client) -> None:
        created = user_client.post("/alerts", json={
            "name": "Software Engineer — Lahore",
            "keywords": "software engineer",
            "cities": ["lahore"],
            "experience_levels": ["entry", "mid"],
            "remote_only": False,
            "frequency": "daily",
        })
        assert created.status_code == 201
        alert = created.json()
        assert alert["name"] == "Software Engineer — Lahore"
        assert alert["is_active"] is True

        assert len(user_client.get("/alerts").json()) == 1

        preview = user_client.post(f"/alerts/{alert['id']}/preview").json()
        assert "count" in preview and isinstance(preview["items"], list)

        paused = user_client.patch(f"/alerts/{alert['id']}", json={"is_active": False}).json()
        assert paused["is_active"] is False

        assert user_client.delete(f"/alerts/{alert['id']}").status_code == 200
        assert user_client.get("/alerts").json() == []

    def test_cannot_touch_another_users_alert(self, user_client) -> None:
        created = user_client.post("/alerts", json={"name": "Mine", "frequency": "daily"}).json()

        with httpx.Client(base_url=API, timeout=30, headers=_identity_headers()) as other:
            other.post("/auth/register", json={
                "email": f"other-{uuid.uuid4().hex[:10]}@example.com", "password": "TestPass123",
            })
            assert other.get("/alerts").json() == []
            assert other.delete(f"/alerts/{created['id']}").status_code == 404

    def test_invalid_frequency_rejected(self, user_client) -> None:
        response = user_client.post("/alerts", json={"name": "Bad", "frequency": "hourly"})
        assert response.status_code == 422


class TestReporting:
    def test_signed_in_user_can_report(self, user_client) -> None:
        items = user_client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        response = user_client.post(f"/jobs/{items[0]['id']}/report", json={
            "reason": "expired", "details": "This role has been filled.",
        })
        assert response.status_code == 201

    def test_anonymous_report_requires_an_email(self, client) -> None:
        items = client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        assert client.post(f"/jobs/{items[0]['id']}/report", json={"reason": "spam"}).status_code == 422
        assert client.post(f"/jobs/{items[0]['id']}/report", json={
            "reason": "spam", "reporter_email": "reporter@example.com",
        }).status_code == 201

    def test_invalid_reason_rejected(self, user_client) -> None:
        items = user_client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        assert user_client.post(f"/jobs/{items[0]['id']}/report", json={
            "reason": "i_dont_like_it",
        }).status_code == 422


class TestAdminAuthorization:
    def test_all_admin_routes_reject_regular_users(self, user_client) -> None:
        for path in ("/admin/overview", "/admin/jobs", "/admin/sources", "/admin/users",
                     "/admin/reports", "/admin/analytics", "/admin/audit-logs", "/admin/connectors"):
            response = user_client.get(path)
            assert response.status_code == 403, f"{path} returned {response.status_code}"
            assert response.json()["error"]["code"] == "forbidden"

    def test_admin_routes_reject_anonymous(self, client) -> None:
        assert client.get("/admin/overview").status_code == 401


class TestCatalog:
    def test_filter_options(self, client) -> None:
        payload = client.get("/filters").json()
        for key in ("categories", "employment_types", "experience_levels", "provinces", "cities"):
            assert payload[key], f"{key} should not be empty"

    def test_provinces_cover_all_of_pakistan(self, client) -> None:
        names = {p["name"] for p in client.get("/provinces").json()}
        assert {
            "Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan",
            "Islamabad Capital Territory", "Gilgit-Baltistan", "Azad Jammu and Kashmir",
        } == names

    def test_public_sources_never_expose_config(self, client) -> None:
        for source in client.get("/sources").json():
            assert "config" not in source
            assert "credential_env_keys" not in source

    def test_sitemap_data(self, client) -> None:
        payload = client.get("/seo/sitemap").json()
        assert "jobs" in payload and "cities" in payload


class TestSecurityHeaders:
    def test_security_headers_present(self) -> None:
        headers = httpx.get(f"{BASE_URL}/health/live", timeout=10).headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in headers

    def test_request_id_is_echoed(self) -> None:
        headers = httpx.get(f"{BASE_URL}/health/live", timeout=10).headers
        assert headers.get("X-Request-ID")


class TestAIGracefulDegradation:
    def test_ai_status_is_reported(self, client) -> None:
        payload = client.get("/ai/status").json()
        assert "enabled" in payload and "features" in payload

    def test_summary_falls_back_when_ai_is_off(self, client) -> None:
        items = client.get("/jobs", params={"page_size": 1}).json()["items"]
        if not items:
            pytest.skip("no jobs indexed")
        payload = client.get(f"/ai/jobs/{items[0]['id']}/summary").json()
        # With AI disabled this must still return a usable summary.
        assert payload["summary"]
        assert payload["used_ai"] is False


class TestFrontendRouteGuards:
    """The frontend's three-layer guard, verified over real HTTP.

    Layer 1 (edge proxy) must redirect signed-out visitors without rendering; layers 2 and 3
    (server component + API) are covered by TestAdminAuthorization above.
    """

    WEB_URL = os.environ.get("TEST_WEB_URL", "http://localhost:3000")

    @staticmethod
    def _web_available() -> bool:
        try:
            return httpx.get(f"{TestFrontendRouteGuards.WEB_URL}/", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    @pytest.mark.parametrize("path", ["/admin", "/dashboard", "/dashboard/saved", "/dashboard/alerts"])
    def test_signed_out_visitors_are_redirected(self, path: str) -> None:
        if not self._web_available():
            pytest.skip("web server is not running")
        response = httpx.get(f"{self.WEB_URL}{path}", follow_redirects=False, timeout=15)
        assert response.status_code in (307, 308)
        location = response.headers["location"]
        assert "/login" in location
        # The originally requested page is preserved so sign-in returns the user there.
        assert "next=" in location

    @pytest.mark.parametrize("path", ["/", "/jobs", "/login", "/register", "/sources", "/about"])
    def test_public_pages_are_not_gated(self, path: str) -> None:
        if not self._web_available():
            pytest.skip("web server is not running")
        assert httpx.get(f"{self.WEB_URL}{path}", follow_redirects=False, timeout=15).status_code == 200

    def test_redirect_is_never_cached(self) -> None:
        """A cached per-visitor redirect would sign everyone out (or let anyone in)."""
        if not self._web_available():
            pytest.skip("web server is not running")
        response = httpx.get(f"{self.WEB_URL}/dashboard", follow_redirects=False, timeout=15)
        assert "no-store" in response.headers.get("cache-control", "")


class TestUnsubscribe:
    """One-click unsubscribe must work from an email link, with no session."""

    def _signed_token(self, alert_id: str) -> str:
        from pakjobs_core.services.security import sign_unsubscribe

        return sign_unsubscribe(alert_id)

    def test_unsubscribe_without_signing_in(self, user_client, client) -> None:
        alert = user_client.post("/alerts", json={"name": "Unsub flow", "frequency": "daily"}).json()
        assert alert["is_active"] is True

        # `client` has no session cookie — exactly like clicking a link from an inbox.
        response = client.post(
            "/alerts/unsubscribe",
            json={"alert": alert["id"], "token": self._signed_token(alert["id"])},
        )
        assert response.status_code == 200

        after = next(a for a in user_client.get("/alerts").json() if a["id"] == alert["id"])
        assert after["is_active"] is False

    def test_forged_token_is_rejected(self, user_client, client) -> None:
        alert = user_client.post("/alerts", json={"name": "Forged", "frequency": "daily"}).json()
        response = client.post(
            "/alerts/unsubscribe", json={"alert": alert["id"], "token": "0" * 32}
        )
        assert response.status_code == 404

        after = next(a for a in user_client.get("/alerts").json() if a["id"] == alert["id"])
        assert after["is_active"] is True, "a forged token must not disable the alert"

    def test_cannot_probe_for_valid_alert_ids(self, client) -> None:
        """An unknown id and a bad signature must be indistinguishable."""
        unknown = client.post(
            "/alerts/unsubscribe",
            json={"alert": "00000000-0000-0000-0000-000000000000", "token": "a" * 32},
        )
        assert unknown.status_code == 404

    def test_unsubscribing_leaves_other_alerts_alone(self, user_client, client) -> None:
        first = user_client.post("/alerts", json={"name": "Keep me", "frequency": "daily"}).json()
        second = user_client.post("/alerts", json={"name": "Drop me", "frequency": "daily"}).json()

        client.post(
            "/alerts/unsubscribe",
            json={"alert": second["id"], "token": self._signed_token(second["id"])},
        )

        alerts = {a["id"]: a["is_active"] for a in user_client.get("/alerts").json()}
        assert alerts[first["id"]] is True
        assert alerts[second["id"]] is False
