# Job sources

## The rule

**We only aggregate from sources that permit it.** In practice that means documented public APIs,
employer career boards published through an ATS, and RSS/Atom feeds — a feed is an explicit
invitation to syndicate.

Nothing in this repository bypasses authentication, CAPTCHAs, paywalls, anti-bot protection, rate
limits or robots directives. If a source refuses access (401/403), the connector records a
`ConnectorConfigError`, marks the source `needs_credentials`, and **stops** — it does not retry
and it does not attempt to work around the block. That behaviour is enforced in
`SourceConnector._request` and covered by tests.

---

## Connectors that ship

| Connector | Type | Works out of the box | What an operator must supply |
|---|---|---|---|
| `github_issues` | Public REST API | ✅ **Yes — live** | Nothing. `GITHUB_TOKEN` optional (60→5000 req/h) |
| `greenhouse_board` | Public JSON API | ✅ Yes | The employer's `board_token` |
| `lever_postings` | Public JSON API | ✅ Yes | The employer's `company` slug |
| `rss_feed` | RSS / Atom | ✅ Yes | A `feed_url` you have verified is syndication-friendly |
| `seed_dev` | Local fixtures | dev only | `ENABLE_SEED_SOURCES=true` and a non-production environment |

### `github_issues` — the reference implementation

Many organisations publish openings as labelled issues in a public repository. GitHub's REST API
is documented, explicitly public and permits automated read access with an identifying User-Agent.

Two modes:

- **Repository mode** — `{"repository": "owner/name", "labels": "job,hiring"}`
- **Search mode** — `{"search_query": "is:issue is:open label:hiring"}` — discovers postings
  across all public repositories

Search mode is noisy by nature (project tasks also get hiring labels), so `require_job_signal`
gates every result: the issue must mention a role noun *and* a hiring signal. Non-vacancies are
counted in `skipped_non_jobs` on the run record rather than silently dropped.

Rate limiting is respected in both directions: the connector paces itself (2.2s between search
pages — the Search API allows 30 req/min) and stops early when `x-ratelimit-remaining` drops
below 5.

### `greenhouse_board` / `lever_postings`

The cleanest possible source: the employer chose to publish a public board, the data is
structured, and attribution is unambiguous. **Duplicate the template source row once per
employer** and set the board token / company slug.

```json
{ "board_token": "acme", "include_content": true, "default_location": "Lahore, Pakistan" }
```

### `rss_feed`

Generic reader for government portals, universities and employers with a careers feed.

```json
{
  "feed_url": "https://example.gov.pk/jobs/feed",
  "government": true,
  "category_hint": "government",
  "default_location": "Pakistan"
}
```

Verify the publisher's terms before enabling. `feed_url` is validated against the SSRF guard, so
internal/loopback addresses are rejected.

---

## Sources that require a commercial agreement

Several large job boards do **not** permit automated aggregation under their terms of service.
They are deliberately **not** implemented, and no partial scraper exists in this codebase for
them. If you obtain authorization, the correct path is:

1. Sign the partner/API agreement.
2. Write a connector implementing `SourceConnector` (typically 100–150 lines).
3. Register it in `packages/core/pakjobs_core/connectors/registry.py`.
4. Add the credential env vars to `.env.example` and `SourceMetadata.credential_env_keys`.
5. Create the source row from the admin panel and enable it.

Nothing else changes. The pipeline, admin UI, scheduler and docs pick it up automatically.

---

## Writing a connector

```python
class MySourceConnector(SourceConnector):
    key = "my_source"

    @classmethod
    def get_source_metadata(cls) -> SourceMetadata:
        return SourceMetadata(
            key=cls.key,
            name="My Source",
            type=SourceType.API,
            requires_credentials=True,
            credential_env_keys=["MY_SOURCE_API_KEY"],
            config_schema={"region": {"type": "string", "required": True}},
            terms_url="https://mysource.example/terms",
            legal_note="Partner API. Agreement signed 2026-01-15.",
        )

    async def fetch_jobs(self, *, limit=None) -> FetchResult:
        async with self._client() as client:
            try:
                payload = await self._get_json(client, "https://api.mysource.example/jobs")
            except ConnectorError as exc:
                return FetchResult(ok=False, error=str(exc), error_type=type(exc).__name__)
        jobs = [j for j in (self.parse_job(i) for i in payload["results"]) if j]
        return FetchResult(jobs=jobs, ok=True)

    def parse_job(self, payload) -> RawJob | None:
        if not payload.get("title"):
            return None
        return RawJob(
            source_job_id=str(payload["id"]),
            title=payload["title"],
            apply_url=payload["url"],
            company_name=payload.get("company"),
            description_html=payload.get("description"),
            location_raw=payload.get("location"),
            posted_at_raw=payload.get("published_at"),
            source_url=payload["url"],
            raw=payload,
        )
```

**Do not** normalize, classify, validate or deduplicate in a connector. Map the fields onto
`RawJob` and the shared pipeline handles the rest — that is what keeps every source comparable.

### Connector checklist

- [ ] `fetch_jobs` returns `FetchResult(ok=False, ...)` on failure — it never raises
- [ ] `parse_job` returns `None` for unusable items rather than raising
- [ ] `source_url` and `apply_url` always point at the original posting
- [ ] `source_job_id` is stable across runs (otherwise every fetch creates duplicates)
- [ ] Credentials come from env vars, never from `config`
- [ ] Rate limits respected; polite delay between pages
- [ ] `terms_url` and `legal_note` filled in so the legal basis is auditable

---

## Operating sources

The admin panel (`/admin/sources`) exposes, per source: enable/disable, fetch interval, priority,
health status, consecutive failures, total collected, last error, and full run history with
per-stage counters (fetched / valid / rejected / duplicates / created / updated).

Scheduling is driven by `priority` and `fetch_interval_minutes`:

- priority ≤ 25 → considered every 15 minutes
- priority ≤ 60 → every 30 minutes
- everything else → every 3 hours

`JobSource.due_for_run` is the real gate, so beat frequency is only an upper bound and a source is
never fetched more often than its configured interval.

---

## Attribution

Non-negotiable, and enforced by tests:

- Every job card and detail page names its source and links to the original posting.
- `apply_url` always points at the original publisher — RozgarPK never accepts applications.
- When duplicates merge, **all** contributing sources are shown on the detail page.
- The public `/sources` page lists every active source and the platform's aggregation principles.

If a rights holder asks for removal, disable the source and remove its jobs from the admin panel.
