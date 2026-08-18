#!/usr/bin/env bash
# Development bootstrap: virtualenv, dependencies, embedded datastores, migrations, registry.
# Idempotent — safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "==> Python environment"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip wheel
./.venv/bin/pip install --quiet -r apps/api/requirements.txt
./.venv/bin/pip install --quiet -e packages/core
./.venv/bin/pip install --quiet pytest pytest-asyncio pgserver redislite

echo "==> Environment file"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET="$(./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  ./.venv/bin/python - "$SECRET" <<'PY'
import pathlib, sys
secret = sys.argv[1]
p = pathlib.Path(".env")
p.write_text(p.read_text().replace(
    "JWT_SECRET=change-me-to-a-long-random-string", f"JWT_SECRET={secret}"))
PY
  echo "    created .env with a generated JWT_SECRET"
fi

echo "==> Development datastores"
./.venv/bin/python infrastructure/scripts/dev_db.py start

echo "==> Database migrations"
(cd apps/api && ../../.venv/bin/alembic upgrade head)

echo "==> Source registry"
./.venv/bin/python infrastructure/scripts/manage.py sync-sources

echo "==> Frontend dependencies"
(cd apps/web && npm install --silent)
[ -f apps/web/.env.local ] || cat > apps/web/.env.local <<'ENV'
API_INTERNAL_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
ENV

cat <<'DONE'

Bootstrap complete.

  Start everything:   ./infrastructure/scripts/dev_up.sh
  Create an admin:    ./.venv/bin/python infrastructure/scripts/manage.py create-admin --email you@example.com
  Load sample data:   ./.venv/bin/python infrastructure/scripts/manage.py seed   (needs ENABLE_SEED_SOURCES=true)
  Fetch real jobs:    ./.venv/bin/python infrastructure/scripts/manage.py ingest

DONE
