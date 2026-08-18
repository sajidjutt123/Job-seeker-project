# Deployment

## Deployable units

| Unit | Scales on | Notes |
|---|---|---|
| `web` (Next.js) | Traffic | Stateless. Vercel, or the provided container |
| `api` (FastAPI) | Traffic | Stateless. Run 2+ replicas behind a load balancer |
| `worker` (Celery) | Source count / volume | Stateless. Scale horizontally |
| `beat` (Celery beat) | — | **Exactly one instance.** Two instances double-fire every schedule |
| PostgreSQL | Data | Managed service recommended |
| Redis | — | Managed service recommended |

---

## Pre-launch checklist

- [ ] `JWT_SECRET` is a long random string (`openssl rand -base64 48`), unique per environment
- [ ] `ENVIRONMENT=production` (disables `/docs`, enables strict config checks)
- [ ] `COOKIE_SECURE=true` and the whole site is served over HTTPS
- [ ] `ENABLE_SEED_SOURCES=false`
- [ ] `EMAIL_PROVIDER` is `smtp` or `resend` — `console` delivers nothing
- [ ] `CORS_ORIGINS` lists only your real frontend origins
- [ ] `DATABASE_URL` points at a managed Postgres with automated backups
- [ ] `alembic upgrade head` has run
- [ ] An admin user exists
- [ ] `INTERNAL_API_KEY` is set on **both** the API and the web tier (same value)
- [ ] `TRUSTED_PROXIES` lists your load balancer / web tier, so client IPs resolve correctly
- [ ] `/health` returns `ok` with an empty `warnings` array

`GET /health` returns a `warnings` array that flags every one of the misconfigurations above.
**Treat a non-empty `warnings` array as a failed deploy.**

---

## Docker Compose (single host / staging)

```bash
cp .env.example .env   # fill in real secrets
docker compose -f infrastructure/docker/docker-compose.yml up -d --build
docker compose -f infrastructure/docker/docker-compose.yml exec api \
  python /app/infrastructure/scripts/manage.py create-admin --email you@example.com
```

The `migrate` service runs `alembic upgrade head` and syncs the source registry before the API,
worker and beat start, so a deploy never races the schema.

---

## Vercel (frontend) + containers (backend)

The frontend is Vercel-ready. Set:

```
API_INTERNAL_URL   = https://api.yourdomain.com
NEXT_PUBLIC_SITE_URL = https://yourdomain.com
```

Root directory: `apps/web`.

The browser only ever calls same-origin `/api/*`, which `next.config.ts` rewrites to
`API_INTERNAL_URL`. That keeps auth cookies first-party and means no CORS preflight in the
browser. Set `CORS_ORIGINS` on the API to your frontend origin anyway, for direct API clients.

---

## Rate limiting and client IPs

Two settings work together, and getting them wrong is a real outage risk:

- **`INTERNAL_API_KEY`** — a shared secret between the web tier and the API. Server-rendered
  pages call the API on behalf of many visitors from one host; without this key their traffic is
  charged to a single IP bucket and roughly a minute of normal traffic rate-limits the whole
  site. Set the same value on both services. It is server-side only and never reaches a browser.

- **`TRUSTED_PROXIES`** — hosts whose `X-Forwarded-For` may be believed (comma-separated IPs or
  CIDRs). Empty means the header is ignored and the socket peer is used. Set this to your load
  balancer and web tier. If you leave it empty behind a proxy, every visitor looks like the
  proxy; if you set it to `*` on a publicly reachable API, anyone can spoof the header to reset
  their own rate limit.

## Cloudflare

The architecture is proxy-friendly:

- The API reads `X-Forwarded-For` for rate limiting (and stores only a salted hash).
- Uvicorn runs with `--proxy-headers`.
- Enable Cloudflare caching for `/`, `/jobs-in-*`, `/sitemap.xml`, `/robots.txt`.
- **Bypass cache** for `/api/*`, `/dashboard/*` and `/admin/*`.
- Put the authoritative rate limit at the Cloudflare edge; the in-process limiter is
  defence in depth, not the primary control.

---

## Database

Indexes that matter are already in the initial migration: GIN on `search_vector`, plus composite
indexes on `(status, posted_at)`, `(city, status)`, `(category, status)`, `(status, quality_score)`,
and lookup indexes on `content_fingerprint` and `apply_url_hash`.

Operational notes:

- `jobs` is the only table that grows without bound; everything else is bounded or pruned.
- `worker.tasks.prune_old_data` trims `source_runs`, `search_logs`, `analytics_events` and expired
  refresh tokens. Schedule it (daily) once you have real traffic.
- Backups: daily full + PITR. The job index can be rebuilt from sources, but users, saved jobs and
  alerts cannot.

---

## Scaling path

The current design handles roughly **low hundreds of thousands of jobs** on a single Postgres
instance. In order:

1. **Read replicas** — point search at a replica; ingestion keeps the primary.
2. **Partition `jobs`** by `posted_at` once the table passes a few million rows.
3. **OpenSearch** — implement `SearchBackend`, set `SEARCH_BACKEND=opensearch`. No other code
   changes; `build_search_service()` deliberately raises `NotImplementedError` today rather than
   silently degrading.
4. **Split worker queues** onto separate deployments (`ingestion` is IO-bound, `notifications` is
   latency-sensitive) — the routing is already configured in `celery_app.py`.

---

## Observability

- **Structured logs** — JSON when `LOG_JSON=true`. Every request logs method, path, status,
  duration and request id. Every ingestion run logs per-stage counters.
- **Health** — `/health/live` (process), `/health/ready` (database), `/health` (full: database,
  Redis, worker heartbeat, config warnings).
- **Source health** — `SourceRun` rows carry full per-run counters and errors, surfaced in the
  admin dashboard.
- **Audit** — every privileged action writes an `AdminAuditLog` row with the actor and a hashed IP.

Recommended alerts:

| Alert | Condition |
|---|---|
| API down | `/health/live` fails twice |
| Database unreachable | `/health` `components.database.status != ok` |
| Worker stalled | `/health` `components.worker.status == stale` |
| Source failing | `sources.failing > 0` on `/api/v1/admin/overview` |
| Ingestion stopped | No job created in 6 hours |
| Moderation backlog | `moderation.open_reports > 20` |

---

## Secrets

Never commit `.env`. Provide secrets through your platform's secret manager. The application
validates at startup and refuses to start quietly misconfigured in production — check the
`warnings` array on `/health` after every deploy.

Rotating `JWT_SECRET` invalidates all sessions immediately (both access tokens and the HMAC used
for refresh-token hashes). That is the intended emergency logout mechanism.
