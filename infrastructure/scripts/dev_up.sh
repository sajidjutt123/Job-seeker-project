#!/usr/bin/env bash
# Runs API, worker, beat and web together. Ctrl-C stops all of them.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
mkdir -p .runtime

if [ ! -d .venv ]; then
  echo "Run ./infrastructure/scripts/dev_bootstrap.sh first." >&2
  exit 1
fi

pids=()
cleanup() {
  echo ""
  echo "Stopping..."
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> API        http://localhost:8000/docs"
(cd apps/api && PYTHONPATH=. ../../.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 --reload \
  --reload-dir . --reload-dir ../../packages/core) &
pids+=($!)

echo "==> Worker"
(cd apps/worker && PYTHONPATH=. ../../.venv/bin/celery -A worker.celery_app worker \
  --loglevel=info -Q default,ingestion,maintenance,notifications --concurrency=2) &
pids+=($!)

echo "==> Beat"
(cd apps/worker && PYTHONPATH=. ../../.venv/bin/celery -A worker.celery_app beat \
  --loglevel=info --schedule=../../.runtime/celerybeat-schedule) &
pids+=($!)

echo "==> Web        http://localhost:3000"
(cd apps/web && npm run dev -- --hostname 0.0.0.0 --port 3000) &
pids+=($!)

wait
