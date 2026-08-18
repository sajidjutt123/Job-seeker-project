"""Shared outbound HTTP/TLS configuration.

Certificate verification is ALWAYS on. `INGEST_CA_BUNDLE` lets an operator point at an additional
trust store — required when egress passes through a TLS-inspecting proxy — instead of the
unacceptable alternative of disabling verification.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pakjobs_core.config import settings
from pakjobs_core.logging import get_logger

logger = get_logger("http")

# Common locations for a system trust store, checked only when explicitly requested.
_SYSTEM_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
)


@lru_cache
def http_verify() -> str | bool:
    """Return the value to pass to httpx's `verify=`.

    Order of precedence:
      1. INGEST_CA_BUNDLE (explicit path, or the literal "system")
      2. SSL_CERT_FILE / REQUESTS_CA_BUNDLE from the environment
      3. certifi default (True)
    """
    configured = (settings.ingest_ca_bundle or "").strip()
    if configured:
        if configured.lower() == "system":
            for path in _SYSTEM_BUNDLES:
                if os.path.exists(path):
                    logger.info("http.ca_bundle", source="system", path=path)
                    return path
            logger.warning("http.ca_bundle_missing", requested="system")
            return True
        if os.path.exists(configured):
            logger.info("http.ca_bundle", source="config", path=configured)
            return configured
        logger.warning("http.ca_bundle_missing", path=configured)

    for env_key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        path = os.environ.get(env_key)
        if path and os.path.exists(path):
            return path

    return True
