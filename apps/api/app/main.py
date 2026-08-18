"""RozgarPK API application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pakjobs_core.config import settings
from pakjobs_core.logging import configure_logging, get_logger

from app.core.errors import register_exception_handlers
from app.core.middleware import register_middleware
from app.routers import admin, ai, alerts, analytics, auth, catalog, health, jobs, profile, saved, seo

configure_logging(settings.log_level, settings.log_json)
logger = get_logger("api")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    warnings = settings.production_warnings()
    if warnings:
        logger.error("api.production_misconfiguration", problems=warnings)
    logger.info(
        "api.startup",
        environment=settings.environment,
        search_backend=settings.search_backend,
        ai_enabled=settings.ai_enabled,
        email_provider=settings.email_provider,
    )
    yield
    from pakjobs_core.db.session import async_engine

    await async_engine.dispose()
    logger.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="RozgarPK API",
        description=(
            "Pakistan-wide job aggregation platform. Aggregates from authorized sources, "
            "normalises and de-duplicates listings, and always links back to the original source."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time"],
        max_age=600,
    )
    register_middleware(app)
    register_exception_handlers(app)

    # Health lives at the root so probes do not depend on the API version prefix.
    app.include_router(health.router)

    for router in (
        auth.router, jobs.router, saved.router, alerts.router, profile.router,
        catalog.router, analytics.router, seo.router, ai.router, admin.router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "status": "ok",
            "docs": None if settings.is_production else "/docs",
            "health": "/health",
        }

    return app


app = create_app()
