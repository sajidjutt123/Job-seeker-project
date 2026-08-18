"""GitHub Issues job-board connector.

Many organisations and communities publish job openings as labelled issues in a public
repository. GitHub's REST API is documented, explicitly public, and permits this use:
https://docs.github.com/en/rest/issues/issues

Compliance notes:
  * Uses only the documented REST API — no HTML scraping, no auth bypass.
  * Sends an identifying User-Agent as GitHub requires.
  * Honours `Retry-After` / rate-limit headers and stops instead of hammering.
  * Unauthenticated: 60 req/h. Setting GITHUB_TOKEN raises it to 5,000 req/h.
  * Attribution (`source_url`) always points back to the original issue.
"""

from __future__ import annotations

import re
from typing import Any


from pakjobs_core.config import settings
from pakjobs_core.connectors.base import ConnectorError, SourceConnector
from pakjobs_core.domain.enums import SourceType
from pakjobs_core.logging import get_logger
from pakjobs_core.pipeline.schemas import FetchResult, RawJob, SourceMetadata

logger = get_logger("connector.github_issues")

API_ROOT = "https://api.github.com"
MAX_PAGES = 5
PER_PAGE = 50

# Conservative company/title splitting. A wrong split invents a fake employer, which is worse
# than leaving the company blank, so only unambiguous shapes are accepted:
#   "[Company] Title"   "Title @ Company"   "Title at Company"   "Company | Title"
_TITLE_PATTERNS = (
    re.compile(r"^\s*\[(?P<company>[^\]]{2,60})\]\s*[-–—:]?\s*(?P<title>.{3,200})$"),
    re.compile(r"^\s*(?P<title>.{3,200}?)\s+(?:@|at)\s+(?P<company>[A-Z][\w&.,' -]{1,60})\s*$"),
    re.compile(r"^\s*(?P<company>[A-Z][\w&.' -]{1,45})\s*\|\s*(?P<title>.{3,200})$"),
)
# Tokens that prove a fragment is NOT a company name (status words, versions, meta prefixes).
_NOT_A_COMPANY = re.compile(
    r"\b(review|hiring|recruitment|update|status|roadmap|sprint|week|q[1-4]|phase|epic|task|"
    r"proposal|discussion|wanted|needed|urgent|apply|opening|vacancy|position|role|new|open|"
    r"senior|junior|lead|staff|principal|remote|full[- ]?time|part[- ]?time|contract|intern)\b"
    r"|^\d|\d\.\d",
    re.IGNORECASE,
)
_HIRING_PREFIX = re.compile(r"^\s*(?:\[?hiring\]?|job|vacancy|position|opening)\s*[:\-–—]\s*", re.IGNORECASE)
_APPLY_LINK = re.compile(
    r"(?:apply|application|apply here|apply now|job link|posting)\s*(?:link)?\s*[:\-–—]?\s*"
    r"<?(?P<url>https?://[^\s>)\]]+)",
    re.IGNORECASE,
)
_ANY_URL = re.compile(r"https?://[^\s>)\]\"']+")
_MD_LINK = re.compile(r"\[(?P<text>[^\]]{1,80})\]\((?P<url>https?://[^)]+)\)")
_FIELD_RE = re.compile(
    r"^\s*[*_#\-\s]*(?P<key>company|employer|organisation|organization|location|city|salary|"
    r"compensation|pay|type|job type|employment type|experience|level|seniority|remote|"
    r"deadline|apply|apply link|application link|website|category)\s*[:|]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_NON_JOB_HINTS = re.compile(
    r"\b(bug|error|crash|feature request|question|typo|documentation fix|refactor|"
    r"dependency|bump|chore\(|fix\(|ci failure|test failure)\b",
    re.IGNORECASE,
)


class GitHubIssuesConnector(SourceConnector):
    """Reads job postings published as labelled GitHub issues.

    Two modes:
      * repository mode — read issues from one repository (`repository`)
      * search mode     — read hiring issues across GitHub (`search_query`), using the
                          documented Search API

    Config:
        repository   "owner/name"  (repository mode)
        search_query GitHub issue-search query (search mode), e.g.
                     'is:issue is:open label:hiring'
        labels       optional comma-joined list, e.g. "job,hiring"
        state        "open" (default) | "all"
        since_days   only issues updated in the last N days (default 90)
        max_items    hard cap per run (default 120)
        category_hint optional category slug to bias classification
        default_location fallback location when the issue does not state one
        require_job_signal  when true (default in search mode), skip issues that do not
                            look like an actual vacancy
    """

    key = "github_issues"

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key,
            name="GitHub Issues Job Board",
            type=SourceType.API,
            website="https://docs.github.com/en/rest/issues/issues",
            attribution_label="GitHub",
            description=(
                "Aggregates job openings that organisations publish as labelled issues in public "
                "GitHub repositories, via GitHub's documented public REST API."
            ),
            requires_credentials=False,
            credential_env_keys=["GITHUB_TOKEN"],  # optional: raises the rate limit
            config_schema={
                "repository": {"type": "string", "required": False, "label": "Repository (owner/name)"},
                "search_query": {"type": "string", "required": False,
                                 "label": "GitHub issue search query (alternative to repository)"},
                "labels": {"type": "string", "required": False, "label": "Issue labels (comma separated)"},
                "state": {"type": "string", "required": False, "default": "open", "label": "Issue state"},
                "since_days": {"type": "integer", "required": False, "default": 90},
                "max_items": {"type": "integer", "required": False, "default": 120},
                "category_hint": {"type": "string", "required": False},
                "default_location": {"type": "string", "required": False},
                "require_job_signal": {"type": "boolean", "required": False, "default": False},
            },
            default_fetch_interval_minutes=30,
            default_reliability=0.72,
            terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
            legal_note=(
                "GitHub's public REST API explicitly permits automated read access with an "
                "identifying User-Agent and rate-limit compliance."
            ),
        )

    # --- fetch --------------------------------------------------------------
    async def fetch_jobs(self, *, limit: int | None = None) -> FetchResult:
        repository = str(self.config.get("repository", "")).strip().strip("/")
        search_query = str(self.config.get("search_query", "")).strip()

        if search_query:
            return await self._fetch_via_search(search_query, limit)
        if not repository or "/" not in repository:
            return FetchResult(
                ok=False,
                error="Set either 'repository' (owner/name) or 'search_query'.",
                error_type="ConnectorConfigError",
            )

        max_items = int(limit or self.config.get("max_items", 120))
        state = self.config.get("state", "open")
        labels = str(self.config.get("labels", "") or "").strip()
        since_days = int(self.config.get("since_days", 90) or 90)

        params: dict[str, Any] = {
            "state": state if state in ("open", "closed", "all") else "open",
            "per_page": min(PER_PAGE, max_items),
            "sort": "created",
            "direction": "desc",
        }
        if labels:
            params["labels"] = labels
        if since_days > 0:
            from datetime import datetime, timedelta, timezone

            params["since"] = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        jobs: list[RawJob] = []
        skipped = 0
        pages_read = 0
        rate_limit_remaining: str | None = None

        async with self._client(headers=headers) as client:
            for page in range(1, MAX_PAGES + 1):
                if len(jobs) >= max_items:
                    break
                page_params = {**params, "page": page}
                try:
                    response = await self._request(
                        client, "GET", f"{API_ROOT}/repos/{repository}/issues", params=page_params
                    )
                except ConnectorError as exc:
                    if jobs:  # keep what we already have instead of failing the whole run
                        logger.warning("github_issues.partial", repository=repository, error=str(exc))
                        return FetchResult(
                            jobs=jobs, ok=True, partial=True, error=str(exc),
                            error_type=type(exc).__name__,
                            stats={"pages": pages_read, "skipped": skipped},
                        )
                    return FetchResult(ok=False, error=str(exc), error_type=type(exc).__name__)

                rate_limit_remaining = response.headers.get("x-ratelimit-remaining")
                try:
                    items = response.json()
                except ValueError as exc:
                    return FetchResult(ok=False, error=f"Invalid JSON: {exc}", error_type="ValueError")
                if not isinstance(items, list) or not items:
                    break

                pages_read += 1
                for item in items:
                    if len(jobs) >= max_items:
                        break
                    if item.get("pull_request"):  # issues endpoint also returns PRs
                        continue
                    raw = self.parse_job(item)
                    if raw is None:
                        skipped += 1
                        continue
                    jobs.append(raw)

                if len(items) < params["per_page"]:
                    break
                if rate_limit_remaining is not None and int(rate_limit_remaining) < 5:
                    logger.warning("github_issues.rate_limit_guard", remaining=rate_limit_remaining)
                    break
                await self._polite_delay(0.35)

        return FetchResult(
            jobs=jobs,
            ok=True,
            stats={
                "repository": repository,
                "pages": pages_read,
                "skipped_non_jobs": skipped,
                "rate_limit_remaining": rate_limit_remaining,
                "authenticated": bool(settings.github_token),
            },
        )

    async def _fetch_via_search(self, query: str, limit: int | None) -> FetchResult:
        """Search mode: GitHub's documented Issues Search API (30 req/min authenticated)."""
        max_items = int(limit or self.config.get("max_items", 100))
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        jobs: list[RawJob] = []
        skipped = 0
        pages_read = 0
        rate_limit_remaining: str | None = None

        async with self._client(headers=headers) as client:
            for page in range(1, MAX_PAGES + 1):
                if len(jobs) >= max_items:
                    break
                params = {
                    "q": query,
                    "sort": "created",
                    "order": "desc",
                    "per_page": min(PER_PAGE, max_items),
                    "page": page,
                }
                try:
                    response = await self._request(client, "GET", f"{API_ROOT}/search/issues", params=params)
                except ConnectorError as exc:
                    if jobs:
                        return FetchResult(jobs=jobs, ok=True, partial=True, error=str(exc),
                                           error_type=type(exc).__name__,
                                           stats={"mode": "search", "pages": pages_read})
                    return FetchResult(ok=False, error=str(exc), error_type=type(exc).__name__)

                rate_limit_remaining = response.headers.get("x-ratelimit-remaining")
                try:
                    payload = response.json()
                except ValueError as exc:
                    return FetchResult(ok=False, error=f"Invalid JSON: {exc}", error_type="ValueError")

                items = payload.get("items") or []
                if not items:
                    break
                pages_read += 1

                for item in items:
                    if len(jobs) >= max_items:
                        break
                    if item.get("pull_request"):
                        continue
                    if not self._looks_like_vacancy(item):
                        skipped += 1
                        continue
                    raw = self.parse_job(item)
                    if raw is None:
                        skipped += 1
                        continue
                    jobs.append(raw)

                if len(items) < params["per_page"]:
                    break
                # The Search API is rate limited far more tightly than the REST API.
                await self._polite_delay(2.2)

        return FetchResult(
            jobs=jobs,
            ok=True,
            stats={
                "mode": "search",
                "query": query,
                "pages": pages_read,
                "skipped_non_jobs": skipped,
                "rate_limit_remaining": rate_limit_remaining,
                "authenticated": bool(settings.github_token),
            },
        )

    def _looks_like_vacancy(self, payload: dict[str, Any]) -> bool:
        """Heuristic gate for search mode: an issue must actually advertise a role.

        Search results are noisy (project tasks, meta-discussion), so we require a positive
        signal rather than assuming every labelled issue is a vacancy.
        """
        if not self.config.get("require_job_signal", True):
            return True
        title = payload.get("title") or ""
        body = (payload.get("body") or "")[:3000]
        labels = " ".join(
            (label.get("name") if isinstance(label, dict) else str(label)) or ""
            for label in payload.get("labels") or []
        )

        if _NON_JOB_HINTS.search(title):
            return False
        positive = re.compile(
            r"\b(hiring|we[' ]?re looking for|looking for a|job opening|vacancy|open (?:role|position)|"
            r"apply|salary|compensation|full[- ]time|part[- ]time|contract|remote|role:|position:)\b",
            re.IGNORECASE,
        )
        role_noun = re.compile(
            r"\b(engineer|developer|designer|manager|analyst|scientist|specialist|consultant|"
            r"administrator|officer|architect|lead|director|intern|writer|marketer|recruiter|"
            r"accountant|teacher|nurse|technician)\b",
            re.IGNORECASE,
        )
        if not role_noun.search(f"{title} {body[:600]}"):
            return False
        return bool(positive.search(f"{title} {labels} {body}"))

    # --- parse --------------------------------------------------------------
    def parse_job(self, payload: dict[str, Any]) -> RawJob | None:
        title_raw = (payload.get("title") or "").strip()
        if not title_raw or len(title_raw) < 5:
            return None

        labels = [
            (label.get("name") if isinstance(label, dict) else str(label)) or ""
            for label in payload.get("labels") or []
        ]
        body = payload.get("body") or ""

        # Skip obvious non-job issues unless a label explicitly marks it as a posting.
        job_labelled = any(
            re.search(r"\b(job|hiring|vacancy|position|opening|career|recruit)\b", label, re.IGNORECASE)
            for label in labels
        )
        if not job_labelled and _NON_JOB_HINTS.search(title_raw):
            return None

        fields = {
            m.group("key").lower(): m.group("value").strip()
            for m in _FIELD_RE.finditer(body[:8000])
        }

        cleaned_title = _HIRING_PREFIX.sub("", title_raw).strip()
        company, title = self._split_company_title(cleaned_title, fields)

        html_url = payload.get("html_url") or ""
        apply_url = self._find_apply_url(fields, body) or html_url
        if not apply_url:
            return None

        location = (
            fields.get("location")
            or fields.get("city")
            or self.config.get("default_location")
            or ""
        )
        remote_hint = None
        if "remote" in fields:
            remote_hint = fields["remote"].strip().lower() in ("yes", "true", "remote", "full", "fully")

        return RawJob(
            source_job_id=f"gh-{payload.get('id')}",
            title=title,
            apply_url=apply_url,
            company_name=company,
            company_website=fields.get("website"),
            description_text=self._build_description(body, payload, fields),
            location_raw=location or None,
            employment_type_raw=fields.get("type") or fields.get("job type") or fields.get("employment type"),
            experience_raw=fields.get("experience") or fields.get("level") or fields.get("seniority"),
            salary_raw=fields.get("salary") or fields.get("compensation") or fields.get("pay"),
            posted_at_raw=payload.get("created_at"),
            deadline_raw=fields.get("deadline"),
            source_url=html_url,
            tags=[label for label in labels if label][:12],
            category_hint=self.config.get("category_hint") or fields.get("category"),
            is_remote_hint=remote_hint,
            raw={
                "id": payload.get("id"),
                "number": payload.get("number"),
                "state": payload.get("state"),
                "labels": labels,
                "html_url": html_url,
                "user": (payload.get("user") or {}).get("login"),
                "comments": payload.get("comments"),
                "updated_at": payload.get("updated_at"),
                "closed_at": payload.get("closed_at"),
            },
        )

    # --- helpers ------------------------------------------------------------
    def _split_company_title(self, text: str, fields: dict[str, str]) -> tuple[str | None, str]:
        explicit = fields.get("company") or fields.get("employer") or fields.get("organisation") or fields.get("organization")
        if explicit:
            # An explicit field wins; strip it from the title if duplicated.
            company = re.sub(r"\[|\]", "", explicit).strip()
            title = re.sub(re.escape(company), "", text, flags=re.IGNORECASE).strip(" -–—:|")
            return company[:200] or None, (title or text)[:300]

        for pattern in _TITLE_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue
            company = match.group("company").strip(" -–—:|")
            title = match.group("title").strip(" -–—:|")
            if len(company) < 2 or len(title) < 3:
                continue
            # Reject fragments that are clearly not employer names.
            if _NOT_A_COMPANY.search(company):
                continue
            if not re.search(r"[A-Za-z]{2}", company):
                continue
            return company[:200], title[:300]
        return None, text[:300]

    def _find_apply_url(self, fields: dict[str, str], body: str) -> str | None:
        for key in ("apply", "apply link", "application link"):
            value = fields.get(key)
            if value:
                md = _MD_LINK.search(value)
                if md:
                    return md.group("url")
                url = _ANY_URL.search(value)
                if url:
                    return url.group(0).rstrip(".,);")
        match = _APPLY_LINK.search(body[:6000])
        if match:
            return match.group("url").rstrip(".,);")
        for md in _MD_LINK.finditer(body[:6000]):
            if re.search(r"\b(apply|application|job|posting|careers?)\b", md.group("text"), re.IGNORECASE):
                return md.group("url").rstrip(".,);")
        return None

    def _build_description(self, body: str, payload: dict[str, Any], fields: dict[str, str]) -> str:
        text = (body or "").strip()
        if not text:
            title = payload.get("title") or ""
            return f"{title}\n\nSee the original posting on GitHub for full details."
        # Strip HTML comments (issue templates) and image tags for readability.
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
        text = re.sub(r"<img[^>]*>", " ", text)
        return text[:20000]
