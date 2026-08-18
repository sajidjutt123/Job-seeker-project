"""Health and readiness endpoints for load balancers, uptime checks and the admin dashboard."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select, text

from pakjobs_core.config import settings
from pakjobs_core.db.session import AsyncSessionLocal
from pakjobs_core.models import SourceRun

from app.schemas.common import HealthComponent, HealthResponse

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


@router.get("/health/live")
async def liveness():
    """Process is up. Never touches dependencies — used by container orchestrators."""
    return {"status": "ok"}


@router.get("/health", response_model=HealthResponse)
async def health(response: Response):
    """Full dependency check: database, redis, worker heartbeat."""
    components: dict[str, HealthComponent] = {
        "database": await _check_database(),
        "redis": _check_redis(),
        "worker": await _check_worker(),
        "storage": _check_storage(),
    }
    # Storage and the worker are not on the critical read path: the site still serves jobs
    # without them, so they degrade rather than fail the deployment.
    NON_CRITICAL = {"worker", "storage"}
    failing = [name for name, c in components.items() if c.status not in ("ok", "disabled")]
    overall = (
        "ok" if not failing
        else "degraded" if set(failing) <= NON_CRITICAL
        else "unhealthy"
    )
    if overall == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status=overall,
        environment=settings.environment,
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc),
        components=components,
        warnings=settings.production_warnings(),
    )


@router.get("/health/ready")
async def readiness(response: Response):
    """Ready to serve traffic: database must be reachable."""
    db = await _check_database()
    if db.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "detail": db.detail}
    return {"status": "ready"}


async def _check_database() -> HealthComponent:
    started = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return HealthComponent(
            status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2)
        )
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=_safe(exc))


def _check_redis() -> HealthComponent:
    started = time.perf_counter()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        client.close()
        return HealthComponent(
            status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2)
        )
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=_safe(exc))


async def _check_worker() -> HealthComponent:
    """Infers worker liveness from recent ingestion activity — no extra infrastructure."""
    try:
        async with AsyncSessionLocal() as session:
            last_run = (
                await session.execute(select(func.max(SourceRun.started_at)))
            ).scalar_one_or_none()
        if last_run is None:
            return HealthComponent(status="unknown", detail="No source run recorded yet")
        age = datetime.now(timezone.utc) - last_run
        if age < timedelta(hours=2):
            return HealthComponent(status="ok", detail=f"Last run {int(age.total_seconds() // 60)}m ago")
        return HealthComponent(
            status="stale", detail=f"No source run for {int(age.total_seconds() // 3600)}h"
        )
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=_safe(exc))


def _check_storage() -> HealthComponent:
    """Reports readiness without a network call, so a missing bucket is visible before first use."""
    from pakjobs_core.services.storage import check_configuration

    status = check_configuration()
    if status.provider == "none":
        return HealthComponent(status="disabled", detail="No file storage configured (not required)")
    if not status.configured:
        return HealthComponent(status="error", detail="; ".join(status.problems))
    return HealthComponent(status="ok", detail=f"provider={status.provider}")


def _safe(exc: Exception) -> str:
    """Never leak connection strings or credentials in a health response."""
    message = str(exc)
    for secret in (settings.database_url, settings.redis_url, settings.jwt_secret):
        if secret:
            message = message.replace(secret, "***")
    return f"{type(exc).__name__}: {message[:180]}"
