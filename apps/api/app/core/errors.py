"""Application error types and global exception handlers.

Users never see stack traces or SQL. Every error becomes a stable JSON envelope:
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from pakjobs_core.logging import get_logger

logger = get_logger("api.errors")


class AppError(Exception):
    """Base class for expected, user-presentable failures."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be completed."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None,
                 code: str | None = None, status_code: int | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Authentication is required."


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to do that."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "That resource already exists."


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "Some of the submitted values are invalid."


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Please slow down and try again shortly."


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    message = "This service is temporarily unavailable. Please try again shortly."


def _envelope(code: str, message: str, details: dict[str, Any] | None = None,
              request_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    if request_id:
        payload["error"]["request_id"] = request_id
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        if exc.status_code >= 500:
            logger.error("api.app_error", code=exc.code, message=exc.message, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details, request_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {401: "unauthorized", 403: "forbidden", 404: "not_found", 429: "rate_limited"}
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code_map.get(exc.status_code, "http_error"), detail,
                              request_id=getattr(request.state, "request_id", None)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for error in exc.errors():
            location = ".".join(str(p) for p in error.get("loc", ()) if p not in ("body", "query", "path"))
            fields[location or "request"] = error.get("msg", "Invalid value")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("validation_error", "Some of the submitted values are invalid.",
                              {"fields": fields}, getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("api.integrity_error", path=request.url.path, error=str(exc.orig)[:300])
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope("conflict", "That record conflicts with existing data.",
                              request_id=getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        incident = uuid.uuid4().hex[:12]
        logger.error("api.database_error", incident=incident, path=request.url.path,
                     error=str(exc)[:500], error_type=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_envelope("database_unavailable",
                              "We could not reach the database. Please try again shortly.",
                              {"incident": incident}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        incident = uuid.uuid4().hex[:12]
        logger.exception("api.unhandled_error", incident=incident, path=request.url.path,
                         error_type=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "Something went wrong on our side.",
                              {"incident": incident}),
        )
