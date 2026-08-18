"""Cross-cutting HTTP middleware: request IDs, access logging, security headers, rate limiting."""

from __future__ import annotations

import time
import uuid
from collections import deque
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from pakjobs_core.config import settings
from pakjobs_core.logging import get_logger
from pakjobs_core.services.security import hash_ip

logger = get_logger("api.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches a request id, logs one structured line per request, sets timing headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Health checks are noisy; log them at debug level only.
        log = logger.debug if request.url.path in ("/health", "/health/live") else logger.info
        log(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline hardening headers. The API serves JSON only, so the CSP can be very strict."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window in-process limiter.

    Adequate for a single API instance and as defence-in-depth. For multi-instance deployments put
    the authoritative limit at the edge (Cloudflare) or swap the counter for Redis — the interface
    stays the same.
    """

    EXEMPT_PATHS = ("/health", "/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc")
    WINDOW_SECONDS = 60

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self._buckets: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.rate_limit_enabled or request.url.path.startswith(self.EXEMPT_PATHS):
            return await call_next(request)

        identity, limit = self._identify(request)
        now = time.time()
        bucket = self._buckets.setdefault(identity, deque())
        while bucket and now - bucket[0] > self.WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = max(1, int(self.WINDOW_SECONDS - (now - bucket[0])))
            logger.warning("http.rate_limited", path=request.url.path, identity=identity[:16])
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please slow down and try again shortly.",
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        # Opportunistic cleanup so the dict cannot grow unbounded.
        if len(self._buckets) > 10_000:
            self._buckets = {k: v for k, v in self._buckets.items() if v and now - v[-1] < self.WINDOW_SECONDS}

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(bucket)))
        return response

    @staticmethod
    def _identify(request: Request) -> tuple[str, int]:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return f"token:{auth[7:40]}", settings.rate_limit_auth_per_minute
        client_host = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            client_host = forwarded.split(",")[0].strip()
        return f"ip:{hash_ip(client_host)}", settings.rate_limit_anon_per_minute


def register_middleware(app: FastAPI) -> None:
    # Order matters: outermost first.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
