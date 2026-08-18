# Development

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16 and Redis 7 — either installed locally, via Docker, or via the embedded
  development datastores described below.

## Fastest path: Docker

```bash
cp .env.example .env
# set JWT_SECRET to any long random string
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

- web → http://localhost:3000
- api → http://localhost:8000/docs
- flower (optional) → `--profile monitoring`, http://localhost:5555

Migrations and source-registry sync run automatically in the `migrate` service before the app
starts.

## Local, without Docker

```bash
./infrastructure/scripts/dev_bootstrap.sh     # venv, deps, embedded Postgres + Redis, migrations
./infrastructure/scripts/dev_up.sh            # api + worker + beat + web
```

`dev_bootstrap.sh` starts an embedded PostgreSQL 16 (via `pgserver`) and Redis under `.devdata/`,
so no root access or system services are required. Production uses real Postgres/Redis through
`DATABASE_URL` / `REDIS_URL`; nothing in the application imports the dev helpers.

### Manual equivalent

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt -e packages/core
pip install pytest pytest-asyncio          # for tests
cp .env.example .env                        # fill DATABASE_URL, REDIS_URL, JWT_SECRET

cd apps/api && alembic upgrade head && cd ../..
python infrastructure/scripts/manage.py sync-sources

# terminal 1 — API
cd apps/api && PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# terminal 2 — worker
cd apps/worker && PYTHONPATH=. celery -A worker.celery_app worker \
  --loglevel=info -Q default,ingestion,maintenance,notifications

# terminal 3 — scheduler
cd apps/worker && PYTHONPATH=. celery -A worker.celery_app beat --loglevel=info

# terminal 4 — web
cd apps/web && npm install && npm run dev
```

---

## Getting data in

### Real data (works immediately, no credentials)

Two GitHub-backed sources are enabled by default and fetch genuine job postings:

```bash
python infrastructure/scripts/manage.py ingest --source github-hiring-search
python infrastructure/scripts/manage.py stats
```

Set `GITHUB_TOKEN` in `.env` to raise the API rate limit from 60/h to 5000/h.

### Development sample data

Clearly separated from production, and refuses to run when `ENVIRONMENT=production`:

```bash
# .env: ENABLE_SEED_SOURCES=true
python infrastructure/scripts/manage.py seed          # load ~60 sample jobs
python infrastructure/scripts/manage.py seed --clear  # remove them all
```

Every seeded job is prefixed `[DEV SAMPLE]` and its source row is flagged `is_seed`, so it is
impossible to mistake for real inventory. Deleting `packages/core/pakjobs_core/connectors/seed_dev.py`
plus its registry entry removes the entire demo system without touching production code.

### Create an admin

```bash
python infrastructure/scripts/manage.py create-admin --email you@example.com
```

Then sign in and open `/admin`.

---

## Management CLI

```bash
python infrastructure/scripts/manage.py sync-sources          # refresh the source registry
python infrastructure/scripts/manage.py ingest                # run all enabled sources
python infrastructure/scripts/manage.py ingest --source SLUG --limit 20
python infrastructure/scripts/manage.py expire --check-urls   # lifecycle sweep
python infrastructure/scripts/manage.py alerts --frequency daily
python infrastructure/scripts/manage.py stats
```

---

## Tests

```bash
pytest                      # everything
pytest tests/unit           # pure logic — no database, fast
pytest tests/integration    # real Postgres + running API
pytest tests/e2e            # user journeys through the running frontend
```

**Layers.** Unit tests cover the pipeline as pure functions. Integration tests run the real
ingestion pipeline against a throwaway Postgres database and exercise the HTTP API. E2E tests
drive the **frontend** over HTTP the way a browser does — following redirects, carrying cookies
across requests and asserting on rendered HTML — which catches pages that render but show an
error state, redirects that never fire, and SSR that drops the session.

E2E tests give each test a distinct `X-Forwarded-For`, because the web tier forwards the
visitor's IP to the API; without it the whole suite shares one rate-limit bucket.

**Adding Playwright.** For click-level interaction and visual regression, add
`@playwright/test` in `apps/web` and drive the same journeys in a real browser. The current
suite covers them at the transport level; the browser binary could not be downloaded in this
environment, so it was not added speculatively.

**242 tests.** Integration tests create a throwaway database per session and roll back every test,
so they never touch your development data. API tests skip automatically if the server is not
running.

```bash
cd apps/web && npm run typecheck && npm run lint && npm run build
```

---

## Migrations

```bash
cd apps/api
alembic revision --autogenerate -m "add employer tables"
alembic upgrade head
alembic downgrade -1
```

Always read the generated migration before committing — autogenerate does not detect every change
(notably server defaults and some index modifications).

---

## Conventions

**Layering.** Routers parse/authorize/serialize. Services hold business rules. Repositories hold
SQL. A router containing a `select()` is a bug.

**The pipeline is pure.** Everything in `packages/core/pakjobs_core/pipeline/` must stay free of IO
so it remains exhaustively unit-testable. If you need the database, you are writing a service.

**Async vs sync.** The API is fully async (`AsyncSession`). Celery workers are sync
(`session_scope()`), which is simpler and safer under prefork. Never mix them in one call path.

**A common async trap:** a bulk `UPDATE` expires loaded ORM attributes. Serialize the object
*before* issuing counter updates, or use `.execution_options(synchronize_session=False)` — see
`_bump()` in `apps/api/app/routers/jobs.py`.

**Errors.** Raise the typed errors in `app/core/errors.py`. They render as a consistent JSON
envelope. Never let a stack trace or SQL reach a user.

**Frontend data.** Server Components use `lib/server-api.ts`, which returns a `Result<T>` instead
of throwing, so pages render real error states rather than 500s. Client components use `lib/api.ts`
and catch `ApiError`.

---

## Troubleshooting

**`certificate verify failed` during ingestion** — you are behind a TLS-inspecting proxy. Set
`INGEST_CA_BUNDLE=system` (or an absolute path to a PEM bundle). Verification is never disabled.

**Worker not picking up tasks** — confirm Redis is reachable and the worker is consuming the right
queues: `-Q default,ingestion,maintenance,notifications`.

**`greenlet_spawn has not been called`** — lazy IO on an async session. See the async trap above.

**Search returns nothing after ingesting** — check `Job.status == 'active'` and
`is_canonical = true`; duplicates are hidden from search by design.
