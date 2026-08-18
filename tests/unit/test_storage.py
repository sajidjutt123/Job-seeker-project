"""Unit tests for the storage layer.

No S3-compatible endpoint is reachable from CI, so the adapter is exercised against a stubbed
client. The validation and key-building logic — which is where the security-relevant decisions
live — is tested directly.
"""

from __future__ import annotations

import pytest

from pakjobs_core.services.storage import (
    MAX_UPLOAD_BYTES,
    NullStorageAdapter,
    StorageError,
    build_key,
    check_configuration,
    get_storage_adapter,
    validate_upload,
)


class TestDefaultBehaviour:
    def test_storage_is_optional(self) -> None:
        """Nothing in the aggregation flow needs storage, so the default must be inert."""
        status = check_configuration()
        assert status.provider == "none"
        assert status.configured is False
        assert status.problems == []

    def test_null_adapter_is_the_default(self) -> None:
        assert isinstance(get_storage_adapter(refresh=True), NullStorageAdapter)

    def test_null_adapter_fails_loudly_with_a_fix(self) -> None:
        """Silently pretending to store a file is far worse than refusing."""
        with pytest.raises(StorageError) as exc:
            NullStorageAdapter().upload(b"data", key="k", content_type="image/png")
        message = str(exc.value)
        assert "STORAGE_PROVIDER" in message
        assert "not configured" in message

    def test_null_delete_is_a_no_op(self) -> None:
        assert NullStorageAdapter().delete("anything") is False


class TestConfigurationValidation:
    def test_missing_credentials_are_reported_individually(self, monkeypatch) -> None:
        from pakjobs_core.config import settings

        monkeypatch.setattr(settings, "storage_provider", "s3")
        monkeypatch.setattr(settings, "s3_bucket", "")
        monkeypatch.setattr(settings, "s3_access_key_id", "")
        monkeypatch.setattr(settings, "s3_secret_access_key", "")

        status = check_configuration()
        assert status.configured is False
        assert any("S3_BUCKET" in p for p in status.problems)
        assert any("S3_ACCESS_KEY_ID" in p for p in status.problems)
        assert any("S3_SECRET_ACCESS_KEY" in p for p in status.problems)

    def test_complete_configuration_validates(self, monkeypatch) -> None:
        from pakjobs_core.config import settings

        monkeypatch.setattr(settings, "storage_provider", "s3")
        monkeypatch.setattr(settings, "s3_bucket", "rozgar-uploads")
        monkeypatch.setattr(settings, "s3_access_key_id", "key")
        monkeypatch.setattr(settings, "s3_secret_access_key", "secret")
        monkeypatch.setattr(settings, "s3_endpoint_url", "")

        assert check_configuration().configured is True


class TestKeyBuilding:
    def test_key_is_namespaced_and_unique(self) -> None:
        a = build_key(prefix="logos", filename="logo.png", owner_id="user-1")
        b = build_key(prefix="logos", filename="logo.png", owner_id="user-1")
        assert a.startswith("logos/user-1/")
        assert a.endswith(".png")
        assert a != b, "two uploads of the same filename must not collide"

    def test_path_traversal_is_neutralised(self) -> None:
        key = build_key(prefix="cv", filename="../../../etc/passwd")
        assert ".." not in key
        assert key.startswith("cv/")

    def test_hostile_filenames_are_sanitised(self) -> None:
        key = build_key(prefix="cv", filename="my resume;rm -rf /.pdf")
        assert " " not in key
        assert ";" not in key
        assert key.endswith(".pdf")

    def test_absurdly_long_names_are_truncated(self) -> None:
        key = build_key(prefix="cv", filename="a" * 500 + ".pdf")
        assert len(key) < 120


class TestUploadValidation:
    @pytest.mark.parametrize(
        "filename,content_type,kind",
        [
            ("photo.png", "image/png", "image"),
            ("photo.jpg", "image/jpeg", "image"),
            ("cv.pdf", "application/pdf", "document"),
        ],
    )
    def test_allowed_uploads_pass(self, filename: str, content_type: str, kind: str) -> None:
        validate_upload(filename=filename, content_type=content_type, size=1024, kind=kind)

    @pytest.mark.parametrize(
        "content_type",
        ["image/svg+xml", "text/html", "application/javascript", "text/plain"],
    )
    def test_script_capable_types_are_blocked(self, content_type: str) -> None:
        """SVG and HTML execute script when served from our own origin — stored XSS."""
        with pytest.raises(StorageError):
            validate_upload(filename="x", content_type=content_type, size=100, kind="image")

    def test_oversized_uploads_are_rejected(self) -> None:
        with pytest.raises(StorageError, match="too large"):
            validate_upload(
                filename="big.png", content_type="image/png",
                size=MAX_UPLOAD_BYTES + 1, kind="image",
            )

    def test_empty_uploads_are_rejected(self) -> None:
        with pytest.raises(StorageError):
            validate_upload(filename="x.png", content_type="image/png", size=0, kind="image")

    def test_extension_must_match_content_type(self) -> None:
        """Blocks a .html file declaring itself image/png to sneak past the allowlist."""
        with pytest.raises(StorageError, match="does not match"):
            validate_upload(
                filename="payload.html", content_type="image/png", size=100, kind="image",
            )

    def test_unknown_kind_is_rejected(self) -> None:
        with pytest.raises(StorageError):
            validate_upload(filename="x.png", content_type="image/png", size=10, kind="video")


class TestS3AdapterAgainstAStub:
    """Exercises the adapter's own logic without a live bucket."""

    @pytest.fixture
    def adapter(self, monkeypatch):
        from pakjobs_core.config import settings
        from pakjobs_core.services import storage

        monkeypatch.setattr(settings, "storage_provider", "s3")
        monkeypatch.setattr(settings, "s3_bucket", "rozgar-test")
        monkeypatch.setattr(settings, "s3_access_key_id", "key")
        monkeypatch.setattr(settings, "s3_secret_access_key", "secret")
        monkeypatch.setattr(settings, "s3_endpoint_url", "")
        monkeypatch.setattr(settings, "s3_region", "auto")
        monkeypatch.setattr(settings, "s3_public_base_url", "https://cdn.example.com")

        calls: list[dict] = []

        class StubClient:
            def put_object(self, **kwargs):
                calls.append(kwargs)

            def delete_object(self, **kwargs):
                calls.append(kwargs)

        instance = storage.S3StorageAdapter.__new__(storage.S3StorageAdapter)
        instance._bucket = "rozgar-test"
        instance._client = StubClient()
        return instance, calls

    def test_upload_sends_the_payload_and_returns_a_public_url(self, adapter) -> None:
        instance, calls = adapter
        result = instance.upload(b"binary-content", key="logos/a.png", content_type="image/png")

        assert calls[0]["Bucket"] == "rozgar-test"
        assert calls[0]["Key"] == "logos/a.png"
        assert calls[0]["Body"] == b"binary-content"
        assert calls[0]["ContentType"] == "image/png"
        assert result.size == len(b"binary-content")
        assert result.url == "https://cdn.example.com/logos/a.png"

    def test_empty_payload_never_reaches_the_network(self, adapter) -> None:
        instance, calls = adapter
        with pytest.raises(StorageError):
            instance.upload(b"", key="k", content_type="image/png")
        assert calls == []

    def test_oversized_payload_never_reaches_the_network(self, adapter) -> None:
        instance, calls = adapter
        with pytest.raises(StorageError, match="too large"):
            instance.upload(b"x" * (MAX_UPLOAD_BYTES + 1), key="k", content_type="image/png")
        assert calls == []
