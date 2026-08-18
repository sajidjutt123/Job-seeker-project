"""Shared test fixtures.

Integration tests run against a real PostgreSQL database (schema features such as tsvector
generated columns and GIN indexes cannot be faked with SQLite). Each test gets a fresh schema in
an isolated database so tests never interfere with development data.
"""

from __future__ import annotations

import os
import pathlib
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DB_PREFIX = "rozgar_test_"


def _load_dotenv() -> None:
    """Load .env manually: pytest runs before the app settings object is constructed."""
    env_file = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _admin_url() -> str | None:
    """Connection URL to the `postgres` maintenance database, or None if unavailable."""
    _load_dotenv()
    base = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not base:
        return None
    if "+psycopg" not in base and base.startswith("postgresql://"):
        base = base.replace("postgresql://", "postgresql+psycopg://", 1)
    # Swap the database name for the maintenance database.
    head, _, _tail = base.rpartition("/")
    return f"{head}/postgres"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Creates a throwaway database for the session and drops it afterwards."""
    admin_url = _admin_url()
    if not admin_url:
        pytest.skip("No DATABASE_URL configured for integration tests")

    db_name = f"{TEST_DB_PREFIX}{uuid.uuid4().hex[:10]}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Cannot create a test database: {exc}")

    head, _, _ = admin_url.rpartition("/")
    test_url = f"{head}/{db_name}"

    # The application reads settings at import time, so point it at the test database
    # before any model/session module is imported.
    os.environ["DATABASE_URL"] = test_url

    yield test_url

    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"),
                {"n": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def engine(database_url: str):
    from pakjobs_core.models import Base

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    """A transactional session: every test rolls back, leaving the schema pristine."""
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    db = factory()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
