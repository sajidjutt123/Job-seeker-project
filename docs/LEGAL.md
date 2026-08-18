# Legal and data-handling rules

These are engineering constraints, not aspirations. They are enforced in code and covered by
tests. Read this before adding a source.

## 1. Only aggregate where aggregation is permitted

Acceptable sources:

- Documented public APIs (e.g. GitHub's REST API)
- Employer career boards published through an ATS (Greenhouse, Lever)
- RSS/Atom feeds — publishing a feed is an explicit invitation to syndicate
- Official government/public-sector portals that permit reuse
- Partner feeds under a signed agreement
- Employers posting directly to the platform

Not acceptable, and deliberately not implemented:

- Any site whose terms of service prohibit automated access
- Anything behind a login, paywall, CAPTCHA or anti-bot system
- Anything requiring a robots directive to be ignored

## 2. Never bypass a protection

`SourceConnector._request` codifies this:

- `401` / `403` → `ConnectorConfigError`, **not retried**. The source is marked
  `needs_credentials` and an admin must resolve it. The system does not attempt workarounds.
- `429` → retryable with exponential backoff. Connectors also self-throttle *before* hitting
  published limits (the GitHub connector paces search requests and stops when
  `x-ratelimit-remaining` drops below 5).
- Every request sends an identifying `User-Agent` containing a contact URL
  (`INGEST_USER_AGENT`).

There is no header spoofing, no proxy rotation, no CAPTCHA solving, and no headless browser
anywhere in this codebase.

## 3. Attribution is mandatory

- `source_url` and `apply_url` always point at the original posting.
- Every job card and detail page names its source.
- When duplicates merge, every contributing source is displayed.
- `/sources` publicly lists all active sources and these principles.
- RozgarPK never accepts applications and never charges candidates.

## 4. Honour removal requests

If a rights holder asks for removal: disable the source, remove its jobs from the admin panel, and
do not re-enable. The soft-delete model (`status = removed`, `hidden_by_admin = true`) means
ingestion cannot silently resurrect removed listings.

## 5. Data minimisation

Deliberately **not** stored:

- Raw IP addresses — only a salted hash, used for rate limiting
- User agents
- Browsing behaviour beyond aggregate product events
- Anything about a user on the employer's side

Analytics payloads are sanitised: keys matching `email`, `phone`, `password`, `token`, `cnic`,
`address`, `ip` or `user_agent` are dropped before persistence (`_sanitize` in
`analytics_service.py`).

## 6. Candidate safety

The validator rejects listings matching known advance-fee fraud patterns (registration/processing
fees, "earn Rs X daily", pay-to-apply) outright — they never reach the database. MLM-style
language flags the job for human review rather than auto-publishing.

The job detail page carries a standing warning that legitimate employers never charge a fee, and
every listing can be reported by anyone, signed in or not.

## 7. Security posture

- Argon2id password hashing; passwords never logged or returned.
- Refresh tokens stored hashed; revocable server-side.
- SSRF guard on every operator-supplied URL (feed URLs, apply URLs): loopback, private ranges,
  link-local and cloud metadata endpoints are rejected.
- SQL injection prevented structurally — parameterised SQLAlchemy throughout, and
  `websearch_to_tsquery` for user search input.
- XSS: React escapes by default. The single `dangerouslySetInnerHTML` is JSON-LD generated
  server-side from our own database, with no user input interpolated.
- All admin actions are audit-logged with actor and hashed IP.
- Admin authorization is enforced server-side on every route and covered by tests.

## 8. Before you launch

This document describes what the software does. It is not legal advice. Before operating a public
deployment:

- Have the terms, privacy policy and data-retention periods reviewed by a lawyer in your
  jurisdiction.
- Confirm each enabled source's terms individually — they change.
- Record the legal basis for each source in its `SourceMetadata.legal_note` and the registry
  `notes` field so the decision is auditable later.
