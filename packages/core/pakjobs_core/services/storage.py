"""S3-compatible object storage.

No credentials are required to run RozgarPK — nothing in the aggregation flow stores files. This
exists because the roadmap needs it (employer logos, CV uploads, cached company assets) and
because a half-configured storage layer that fails at the moment of first use is worse than one
that reports its own readiness up front.

Design:
  * `StorageAdapter` is the interface. `NullStorageAdapter` is the default and fails loudly with
    an actionable message rather than silently pretending to store a file.
  * `S3StorageAdapter` is real, working code against any S3-compatible endpoint (AWS S3,
    Cloudflare R2, MinIO, DigitalOcean Spaces) — none of which are reachable from this sandbox,
    so it is unit-tested against a stubbed client rather than a live bucket.
  * `check_configuration()` validates settings without touching the network, so `/health` and
    startup can tell an operator what is missing before a user hits an upload button.

Uploads are validated before they reach the network: content type against an allowlist, size
against a cap, and the key sanitised so a caller cannot traverse outside its prefix.
"""

from __future__ import annotations

import mimetypes
import posixpath
import re
import uuid
from dataclasses import dataclass, field
from typing import BinaryIO, Protocol, runtime_checkable

from pakjobs_core.config import settings
from pakjobs_core.logging import get_logger

logger = get_logger("storage")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB — generous for a CV or a logo

# Deliberately an allowlist. Never accept HTML or SVG from users: both execute script when served
# from your own origin, which turns an "upload" feature into stored XSS.
ALLOWED_CONTENT_TYPES: dict[str, tuple[str, ...]] = {
    "image": ("image/png", "image/jpeg", "image/webp", "image/gif"),
    "document": (
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
}

_SAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9._-]+")


class StorageError(RuntimeError):
    """Raised when a storage operation cannot be completed."""


@dataclass(slots=True)
class StoredObject:
    key: str
    url: str
    size: int
    content_type: str


@dataclass(slots=True)
class ConfigurationStatus:
    configured: bool
    provider: str
    problems: list[str] = field(default_factory=list)


@runtime_checkable
class StorageAdapter(Protocol):
    """Swap this out for GCS/Azure by implementing these three methods."""

    provider: str

    def upload(
        self, data: BinaryIO | bytes, *, key: str, content_type: str, public: bool = True
    ) -> StoredObject: ...

    def delete(self, key: str) -> bool: ...

    def url_for(self, key: str) -> str: ...


class NullStorageAdapter:
    """Default adapter. Refuses uploads with an actionable message instead of failing obscurely."""

    provider = "none"

    def upload(self, data, *, key: str, content_type: str, public: bool = True) -> StoredObject:
        raise StorageError(
            "File storage is not configured. Set STORAGE_PROVIDER=s3 and the S3_* environment "
            "variables (see .env.example and docs/DEPLOYMENT.md) to enable uploads."
        )

    def delete(self, key: str) -> bool:
        return False

    def url_for(self, key: str) -> str:
        raise StorageError("File storage is not configured.")


class S3StorageAdapter:
    """Works with any S3-compatible endpoint: AWS S3, Cloudflare R2, MinIO, Spaces."""

    provider = "s3"

    def __init__(self) -> None:
        status = check_configuration()
        if not status.configured:
            raise StorageError("S3 storage is misconfigured: " + "; ".join(status.problems))

        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise StorageError("boto3 is required for S3 storage") from exc

        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region or "auto",
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=20,
            ),
        )

    def upload(
        self, data: BinaryIO | bytes, *, key: str, content_type: str, public: bool = True
    ) -> StoredObject:
        payload = data if isinstance(data, bytes) else data.read()
        if not payload:
            raise StorageError("Refusing to upload an empty file.")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise StorageError(
                f"File is too large ({len(payload) // 1024} KB). "
                f"The limit is {MAX_UPLOAD_BYTES // 1024 // 1024} MB."
            )

        extra: dict[str, str] = {"ContentType": content_type, "CacheControl": "public, max-age=31536000"}
        if public:
            extra["ACL"] = "public-read"

        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=payload, **extra)
        except Exception as exc:  # noqa: BLE001 - surface a clean error, never a boto traceback
            logger.error("storage.upload_failed", key=key, error=str(exc))
            raise StorageError(f"Upload failed: {type(exc).__name__}") from exc

        logger.info("storage.uploaded", key=key, size=len(payload))
        return StoredObject(key=key, url=self.url_for(key), size=len(payload), content_type=content_type)

    def delete(self, key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            logger.error("storage.delete_failed", key=key, error=str(exc))
            return False
        return True

    def url_for(self, key: str) -> str:
        if settings.s3_public_base_url:
            return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
        if settings.s3_endpoint_url:
            return f"{settings.s3_endpoint_url.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"

    def presigned_upload(self, key: str, *, content_type: str, expires_in: int = 900) -> str:
        """Lets a browser upload straight to the bucket, keeping large files off the API."""
        try:
            return self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=expires_in,
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Could not create an upload URL: {type(exc).__name__}") from exc


def check_configuration() -> ConfigurationStatus:
    """Validate storage settings without any network call."""
    provider = settings.storage_provider

    if provider == "none":
        return ConfigurationStatus(configured=False, provider="none", problems=[])

    problems: list[str] = []
    if not settings.s3_bucket:
        problems.append("S3_BUCKET is not set")
    if not settings.s3_access_key_id:
        problems.append("S3_ACCESS_KEY_ID is not set")
    if not settings.s3_secret_access_key:
        problems.append("S3_SECRET_ACCESS_KEY is not set")
    if settings.s3_endpoint_url and not settings.s3_endpoint_url.startswith("https://"):
        # Plain HTTP is fine for a local MinIO, but never for a real deployment.
        if settings.is_production:
            problems.append("S3_ENDPOINT_URL must use https in production")

    return ConfigurationStatus(configured=not problems, provider=provider, problems=problems)


_adapter: StorageAdapter | None = None


def get_storage_adapter(*, refresh: bool = False) -> StorageAdapter:
    """Return the configured adapter, degrading to Null rather than raising at import time."""
    global _adapter
    if _adapter is not None and not refresh:
        return _adapter

    if settings.storage_provider == "s3":
        try:
            _adapter = S3StorageAdapter()
            logger.info("storage.ready", provider="s3", bucket=settings.s3_bucket)
        except StorageError as exc:
            logger.error("storage.unavailable", error=str(exc))
            _adapter = NullStorageAdapter()
    else:
        _adapter = NullStorageAdapter()

    return _adapter


def build_key(*, prefix: str, filename: str, owner_id: str | None = None) -> str:
    """Build a collision-free, traversal-safe object key.

    The caller's filename is never trusted for the path: it is sanitised and a UUID prefix is
    added, so two users uploading `cv.pdf` cannot overwrite each other and no input can escape
    the intended prefix.
    """
    name = posixpath.basename(filename or "file")
    stem, _, extension = name.rpartition(".")
    stem = _SAFE_SEGMENT.sub("-", stem or "file")[:40].strip("-") or "file"
    extension = _SAFE_SEGMENT.sub("", extension)[:10].lower()

    unique = uuid.uuid4().hex[:12]
    parts = [_SAFE_SEGMENT.sub("-", prefix).strip("-/")]
    if owner_id:
        parts.append(_SAFE_SEGMENT.sub("", str(owner_id)))
    parts.append(f"{stem}-{unique}.{extension}" if extension else f"{stem}-{unique}")
    return "/".join(p for p in parts if p)


def validate_upload(*, filename: str, content_type: str, size: int, kind: str = "image") -> None:
    """Raise StorageError unless the upload is acceptable. Call before touching the network."""
    allowed = ALLOWED_CONTENT_TYPES.get(kind)
    if allowed is None:
        raise StorageError(f"Unknown upload kind '{kind}'.")

    if content_type not in allowed:
        raise StorageError(
            f"Unsupported file type '{content_type}'. Allowed: {', '.join(allowed)}."
        )
    if size <= 0:
        raise StorageError("The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise StorageError(
            f"File is too large ({size // 1024} KB). Limit is {MAX_UPLOAD_BYTES // 1024 // 1024} MB."
        )

    # Guard against a mismatched extension (image.png declaring application/pdf and similar).
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed and guessed not in allowed:
        raise StorageError("The file extension does not match its content type.")
