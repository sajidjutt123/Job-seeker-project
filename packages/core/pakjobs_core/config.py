"""Environment-driven application configuration.

Every deployable (API, worker, CLI) reads the same contract so behaviour cannot drift between
processes. Nothing here has a production-safe default that could leak: secrets must be supplied.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- core ---
    environment: Environment = "development"
    app_name: str = "RozgarPK"
    log_level: str = "INFO"
    log_json: bool = False
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # --- database ---
    database_url: str = "postgresql+psycopg://rozgar:rozgar@localhost:5432/rozgar"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- redis / celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- auth ---
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    cookie_domain: str = ""
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # --- email ---
    email_provider: Literal["console", "smtp", "resend"] = "console"
    email_from: str = "RozgarPK <no-reply@rozgar.pk>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    resend_api_key: str = ""

    # --- storage ---
    storage_provider: Literal["none", "s3"] = "none"
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""
    upload_max_bytes: int = 5 * 1024 * 1024
    upload_allowed_mime: str = "application/pdf,image/png,image/jpeg"

    # --- search ---
    search_backend: Literal["postgres", "opensearch"] = "postgres"
    opensearch_url: str = ""
    opensearch_index: str = "jobs"

    # --- ai ---
    ai_enabled: bool = False
    ai_provider: Literal["null", "openai", "gemini", "anthropic", "local"] = "null"
    ai_timeout_seconds: int = 20
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    local_ai_base_url: str = ""

    # --- ingestion ---
    ingest_user_agent: str = "RozgarPKBot/1.0 (+https://rozgar.pk/bot)"
    ingest_http_timeout: int = 25
    ingest_max_retries: int = 4
    ingest_retry_base_seconds: int = 15
    ingest_global_concurrency: int = 4
    enable_seed_sources: bool = False
    github_token: str = ""
    # Optional custom CA bundle — required when outbound traffic passes through a
    # TLS-inspecting corporate proxy. Empty means "use certifi's default trust store".
    ingest_ca_bundle: str = ""

    # --- rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_anon_per_minute: int = 60
    rate_limit_auth_per_minute: int = 180

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_upload_mime(self) -> set[str]:
        return {m.strip() for m in self.upload_allowed_mime.split(",") if m.strip()}

    @property
    def sync_database_url(self) -> str:
        """psycopg3 driver works for both sync and async; alembic uses the sync form."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    def production_warnings(self) -> list[str]:
        """Configuration problems that must be fixed before going live."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if "change-me" in self.jwt_secret or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET is weak or unset")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if self.enable_seed_sources:
            problems.append("ENABLE_SEED_SOURCES must be false in production")
        if self.email_provider == "console":
            problems.append("EMAIL_PROVIDER=console will not deliver real email")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
