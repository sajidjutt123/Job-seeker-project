"""Connector registry.

Adding a new source is: write a connector class, register it here. Nothing else in the codebase
needs to change — the admin UI, scheduler and docs all read from this registry.
"""

from __future__ import annotations

from pakjobs_core.connectors.base import SourceConnector
from pakjobs_core.connectors.github_issues import GitHubIssuesConnector
from pakjobs_core.connectors.greenhouse import GreenhouseConnector
from pakjobs_core.connectors.lever import LeverConnector
from pakjobs_core.connectors.rss_feed import RSSFeedConnector
from pakjobs_core.connectors.seed_dev import SeedDevConnector
from pakjobs_core.pipeline.schemas import SourceMetadata

_REGISTRY: dict[str, type[SourceConnector]] = {}


def register(connector_cls: type[SourceConnector]) -> type[SourceConnector]:
    _REGISTRY[connector_cls.key] = connector_cls
    return connector_cls


for _cls in (
    GitHubIssuesConnector,
    GreenhouseConnector,
    LeverConnector,
    RSSFeedConnector,
    SeedDevConnector,
):
    register(_cls)


def get_connector_class(key: str) -> type[SourceConnector] | None:
    return _REGISTRY.get(key)


def build_connector(key: str, config: dict | None = None, *, source_slug: str | None = None) -> SourceConnector:
    connector_cls = _REGISTRY.get(key)
    if connector_cls is None:
        raise KeyError(f"Unknown connector '{key}'. Registered: {sorted(_REGISTRY)}")
    return connector_cls(config or {}, source_slug=source_slug)


def available_connectors() -> list[SourceMetadata]:
    return [cls.get_source_metadata() for cls in _REGISTRY.values()]


def connector_keys() -> list[str]:
    return sorted(_REGISTRY)
