# RozgarPK

A production-grade job aggregation platform for Pakistan. It collects vacancies from sources that
permit aggregation, normalises them so they are actually comparable, removes duplicates, ranks
them against a candidate's profile, and sends people to the original posting to apply.

It is a working system, not a prototype: real connectors fetching real jobs, a real ingestion
pipeline, real background workers, and 242 passing tests.

---

## Quick start

```bash
cp .env.example .env                 # set JWT_SECRET
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

- Web → http://localhost:3000
- API docs → http://localhost:8000/docs
- Health → http://localhost:8000/health

Without Docker: `./infrastructure/scripts/dev_bootstrap.sh && ./infrastructure/scripts/dev_up.sh`

Then:

```bash
python infrastructure/scripts/manage.py create-admin --email you@example.com
python infrastructure/scripts/manage.py ingest        # fetch real jobs, no credentials needed
```

Full instructions: **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**

---

## What it does

**Aggregation.** Isolated connectors per source (GitHub API, Greenhouse, Lever, RSS). Adding a
source is one class plus a registry line — nothing else in the system changes. Per-source enable,
interval, priority, health tracking and full run history.

**A real pipeline.** fetch → parse → normalize → validate → classify → deduplicate → quality score
→ persist → index → alert match. Every stage after parsing is shared, which is what makes twenty
different sources comparable.

**Normalization built for Pakistan.** 40 cities with aliases (`Pindi` → Rawalpindi) mapped to all
7 provinces/territories; PKR salary parsing including `lac`/`crore`; local qualification levels
(Matric, FSc, DAE); BPS grade and public-sector detection.

**Deduplication that works across sources.** The same job posted as `Software Engineer / ABC /
Lahore` and `Software Engineer / ABC Technologies / Lahore` collapses into one listing that credits
both sources. Six weighted signals, indexed candidate pre-filtering, auto-merge above 0.86 and a
human review queue between 0.68 and 0.86.

**Search.** Postgres full-text with a generated `tsvector` (weighted title/company/description) and
a GIN index. Relevance blends text rank, recency decay and quality. Behind a `SearchBackend`
protocol so OpenSearch is a swap, not a rewrite.

**Personalisation.** Deterministic, explainable scoring across skills, category, location,
experience, remote preference, salary, freshness and quality — every recommendation states *why*
it matched. No black box, no AI dependency.

**Alerts.** Saved searches matched by a background worker, delivered as email digests
(instant / daily / weekly), idempotent so nobody is ever notified twice about the same job.

**Lifecycle.** Jobs expire on deadline, on prolonged absence from their source, or on a dead apply
URL. Nothing is deleted; every transition is an event, and a republished job is reactivated.

**Admin.** Overview with live system health, job moderation with quality/classification/duplicate
inspection, source control with run history, user management, report queue, analytics, and an
immutable audit log.

**AI, optional.** Multi-vendor (`openai` / `anthropic` / `gemini` / `local`), defaulting to `null`.
Rules run first; AI is consulted only when rule confidence is low. If AI is off or failing, every
feature still works and the response says `used_ai: false`.

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 (App Router, RSC), TypeScript, Tailwind v4 |
| API | FastAPI, Pydantic v2, SQLAlchemy 2 (async) |
| Workers | Celery + Redis, Celery beat |
| Database | PostgreSQL 16 (full-text search, generated columns, GIN) |
| Auth | Argon2id, JWT access + rotating opaque refresh tokens, Google OAuth |
| Infra | Docker, Alembic, structlog |

---

## Layout

```
apps/
  api/       FastAPI — routers → services → repositories
  worker/    Celery tasks + beat schedule
  web/       Next.js frontend
packages/
  core/      pakjobs_core — models, pipeline, connectors, services (shared by api/worker/CLI)
  types/     shared TypeScript domain types
  ui/        design-system components
  config/    shared build config
infrastructure/
  docker/    Dockerfiles + compose
  scripts/   management CLI, dev bootstrap
docs/        architecture, sources, development, deployment, legal
tests/       unit + integration
```

---

## Tests

```bash
pytest                      # 242 tests
pytest tests/unit           # pure logic, no database
pytest tests/integration    # real Postgres + live API
cd apps/web && npm run typecheck && npm run build
```

Integration tests build a throwaway database per session and roll back each test. They found four
genuine bugs during development (a company-suffix over-strip, a deadline regex gap, an unstripped
title prefix, and internships swallowing every functional category) — all fixed.

---

## How sources are handled

Only sources that permit aggregation: documented public APIs, ATS career boards, and RSS feeds.
No logins, CAPTCHAs, paywalls or anti-bot measures are bypassed anywhere in this codebase. A
`401`/`403` marks the source as needing credentials and **stops** — it is never retried around.
Every listing names its source and links to the original posting, and RozgarPK never accepts
applications or charges candidates.

Details: **[docs/SOURCES.md](docs/SOURCES.md)** and **[docs/LEGAL.md](docs/LEGAL.md)**

---

## Demo data

Sample data is completely separate from production flow: every record is prefixed
`[DEV SAMPLE]`, its source is flagged `is_seed`, and the connector refuses to run when
`ENVIRONMENT=production`. `manage.py seed --clear` removes it; deleting `seed_dev.py` and its
registry line removes the whole demo system.

---

## Built to extend, deliberately not built yet

Employer posting, the education ecosystem (institutions, programs, admissions, scholarships),
push/WhatsApp notifications, and monetization all have their schema, enums, roles and interfaces
in place — with no half-finished feature surface. See
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Docs

| | |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and the reasoning behind it |
| [SOURCES.md](docs/SOURCES.md) | Connectors, and how to write one |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local setup, CLI, conventions, troubleshooting |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production checklist, scaling, observability |
| [LEGAL.md](docs/LEGAL.md) | Aggregation rules, privacy, security posture |
