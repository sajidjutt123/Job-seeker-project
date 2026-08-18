# Architecture

## Why it is shaped this way

The product is an aggregator, so the hard problems are **data quality** and **source
independence**, not CRUD. The architecture optimises for three things:

1. **Adding a source must be cheap.** Write one connector class, register it, done. No changes to
   search, ranking, the admin UI, or the scheduler.
2. **One bad source must not degrade the platform.** Ingestion runs out-of-process; a connector
   that times out, returns garbage or gets rate limited produces a recorded failure, not an outage.
3. **Every subsystem must be replaceable.** Search, AI, notification channels and storage all sit
   behind interfaces so v2 (OpenSearch, a new email provider, push notifications) is a swap, not
   a rewrite.

---

## Runtime topology

```
                    ┌──────────────┐
   Browser ────────▶│  Next.js web │  SSR + static; proxies /api/* to the API
                    └──────┬───────┘
                           │ (server-side fetch, cookies forwarded)
                    ┌──────▼───────┐
                    │  FastAPI API │  auth, search, admin, analytics, health
                    └──┬────────┬──┘
                       │        │
        ┌──────────────▼─┐   ┌──▼──────────┐
        │  PostgreSQL 16 │   │   Redis     │
        │  (source of    │   │ broker +    │
        │   truth + FTS) │   │ rate limits │
        └──────────────▲─┘   └──▲──────────┘
                       │        │
                    ┌──┴────────┴──┐
                    │ Celery worker│  ingestion, expiration, alerts, notifications
                    │ Celery beat  │  scheduler (exactly one instance)
                    └──────┬───────┘
                           │ HTTPS (identified UA, rate-limit aware)
                    ┌──────▼───────────────────────┐
                    │ External sources             │
                    │ GitHub API · Greenhouse ·    │
                    │ Lever · RSS feeds            │
                    └──────────────────────────────┘
```

The web tier **never** calls an external source and never holds a database connection to anything
but the API. The worker **never** serves HTTP. This keeps a slow scrape from ever affecting page
load time.

---

## Repository layout

```
apps/
  api/          FastAPI app. Routers → services → repositories. No SQL in routers.
    app/core/   config plumbing, dependencies, middleware, error handlers
    app/routers/  HTTP surface only: parse, authorize, delegate, serialize
    app/schemas/  Pydantic request/response contracts
    app/services/ API-layer services (auth, email, analytics, serialization)
    alembic/    migrations
  worker/       Celery app, beat schedule, tasks
  web/          Next.js App Router frontend
packages/
  core/         pakjobs_core — the shared domain library
    config.py       one settings contract for every process
    models/         SQLAlchemy ORM
    domain/         enums, Pakistan geography reference data
    pipeline/       normalizer, classifier, validator, deduplicator, quality, stages
    connectors/     one isolated adapter per source + registry
    repositories/   data access (SQL lives here)
    services/       ingestion, search, alerts, expiration, notifications, AI, security
  types/        shared TypeScript domain types
  ui/           shared React primitives
  config/       shared tsconfig / tailwind preset
infrastructure/
  docker/       Dockerfiles + compose
  scripts/      management CLI, dev bootstrap
docs/
```

`pakjobs_core` is a real installable package, imported identically by the API, the worker and the
CLI. There is exactly one implementation of "what is a job" in the system.

---

## The ingestion pipeline

```
 FETCH ── connector talks to one source, returns RawJob[]
   │      (never raises past this boundary; failures become FetchResult.ok = False)
   ▼
 PARSE ── connector maps source fields onto RawJob
   ▼
 NORMALIZE ── shared engine: titles, companies, locations, salaries, dates, skills
   ▼
 VALIDATE ── hard errors reject; soft warnings route to pending_review
   ▼
 CLASSIFY ── weighted keyword rules → category + internship/government/fresh-grad flags
   ▼
 DEDUPE ── multi-signal confidence against pre-filtered candidates
   ▼
 QUALITY ── 0–100 internal score used for ranking and moderation triage
   ▼
 SAVE ── upsert on (source_id, source_job_id); JobEvent written for every transition
   ▼
 INDEX ── Postgres generated tsvector column; always in sync, no trigger to maintain
   ▼
 ALERT MATCH ── queued separately so notification failures cannot roll back ingestion
```

Every stage after FETCH/PARSE is **shared**. A connector cannot accidentally produce a job that
skips validation or gets classified differently — which is what keeps 20 sources comparable.

### Key design decisions

**Normalization is pure functions.** No database, no IO, no config. That makes the highest-risk
logic in the product exhaustively unit-testable, and it is: the normalizer alone has ~90 tests.

**Dedup never compares titles alone.** The spec's example — `Software Engineer / ABC / Lahore`
versus `Software Engineer / ABC Technologies / Lahore` — is handled by reducing company names to
a matching key (`abc`) and combining six weighted signals. Hard identity (same apply URL, same
`source_job_id`) short-circuits to certainty. Everything else scores; ≥0.86 auto-merges, 0.68–0.86
records the link and flags it for a human.

**Candidate pre-filtering is indexed.** Comparing every incoming job against the whole table would
be O(n²). Instead a coarse `content_fingerprint` (reduced title + company key + city) plus
`apply_url_hash` narrows to ≤60 candidates via an index before any fuzzy matching runs.

**Nothing is deleted.** Expiry, admin removal and dedup all set state and append a `JobEvent`.
A job the source republishes is reactivated automatically.

---

## Search

`SearchBackend` is a protocol. `PostgresSearchBackend` implements it with a **generated**
`tsvector` column (weights: title A, company/location B, description C) and a GIN index.
Relevance blends `ts_rank_cd` with a recency decay and the quality score, so a good fresh job
outranks a stale keyword-stuffed one.

Swapping in OpenSearch means implementing one protocol and changing `SEARCH_BACKEND`. Routers,
services and the frontend are untouched — none of them contain SQL or index-specific logic.

Queries use `websearch_to_tsquery`, which is injection-safe and gives users quoting and `-term`
for free.

---

## Authentication

- **Argon2id** password hashing (memory-hard, current OWASP guidance), with automatic rehash when
  parameters change.
- **Short-lived JWT access tokens** (30 min) + **opaque refresh tokens** stored hashed server-side
  so sessions are genuinely revocable. Refresh tokens rotate on every use.
- **httpOnly cookies for browsers, Bearer tokens for API clients** — both first class.
- `token_version` on the user row: bumping it invalidates every outstanding session instantly
  (used on password change and admin suspension).
- Login responses are identical for "unknown email" and "wrong password", and the unknown-email
  path still performs a hash comparison so timing does not leak account existence.

**Authorization is always server-side.** The `AdminUser` dependency gates every admin route; the
frontend's admin layout check only prevents a UI flash and is not a security boundary. This is
covered by tests that assert every admin route 403s for a regular user.

---

## Failure handling

| Failure | Behaviour |
|---|---|
| Source times out / 5xx | Run marked failed, retried with exponential backoff + jitter, max 4 attempts |
| Source 401/403 | `ConnectorConfigError` — **not** retried; source marked `needs_credentials` |
| Source 429 | Treated as retryable; connector also self-throttles before hitting limits |
| Malformed record | That record is rejected and counted; the batch continues |
| Persist error on one job | Rolled back individually; the rest of the batch still commits |
| 5 consecutive source failures | Source status → `failing`, surfaced on the admin dashboard |
| AI provider down | Deterministic fallback returns, `used_ai: false` |
| Email provider down | Notification row persists as `failed`, retried by a separate task |
| Redis down | API still serves reads; health endpoint reports degraded |
| Database down | API returns a controlled 503 with an incident id, never a stack trace |

---

## Extension points (built, not yet exposed)

- **Employer platform** — `jobs.origin` distinguishes `aggregated` from `direct`;
  `posted_by_user_id`, `is_featured`, `is_sponsored` and the `employer` role already exist.
- **Education ecosystem** — `institutions`, `campuses`, `programs`, `admission_cycles`,
  `scholarships`, `courses` tables exist with no API surface yet.
- **Notification channels** — `NotificationChannelAdapter` has an email implementation (console,
  SMTP and Resend), and carries optional per-message headers so RFC 8058 one-click unsubscribe
  works; push, WhatsApp and Telegram are enum values awaiting adapters.
- **Monetization** — featured/sponsored flags and `featured_until` are on the job model.

- **Object storage** — `StorageAdapter` with a working S3-compatible implementation (AWS S3,
  Cloudflare R2, MinIO, Spaces) plus presigned uploads. Defaults to `NullStorageAdapter`, which
  refuses uploads with an actionable message rather than silently discarding a file. Nothing in
  the aggregation flow needs it; it exists for employer logos and CV uploads. Uploads are
  validated before any network call: content-type allowlist (SVG and HTML are rejected — both
  execute script from your own origin), size cap, and keys sanitised against path traversal.
