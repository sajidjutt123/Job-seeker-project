"""Structured logging shared by API, worker and CLI."""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator

import structlog

_configured = False


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    global _configured
    if _configured:
        return

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level, logging.INFO))

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _configured:  # safe default for tests / ad-hoc scripts
        configure_logging()
    return structlog.get_logger(name)


@contextmanager
def log_duration(logger: Any, event: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
    """Times a block and always emits one structured record (success or failure)."""
    started = time.perf_counter()
    payload: dict[str, Any] = dict(kwargs)
    try:
        yield payload
    except Exception as exc:  # noqa: BLE001 - we re-raise
        logger.error(event, duration_ms=round((time.perf_counter() - started) * 1000, 2),
                     error=str(exc), error_type=type(exc).__name__, **payload)
        raise
    else:
        logger.info(event, duration_ms=round((time.perf_counter() - started) * 1000, 2), **payload)
