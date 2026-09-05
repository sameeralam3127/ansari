"""Test fixtures backed by a real Postgres.

The suite used to build its schema with `Base.metadata.create_all` on in-memory
SQLite. That tested a schema Alembic never produced, on an engine the project
does not run in production, so a model change without a matching migration
passed CI silently. These fixtures apply the migrations instead: if a migration
is missing or wrong, the tests fail.
"""

import os
from collections.abc import Generator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alembic import command
from ansari.api.db import Base, get_db
from ansari.api.main import create_app

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://ansari:ansari@localhost:5432/ansari_test"

_UNAVAILABLE = (
    "PostgreSQL is not reachable at {url}.\n"
    "The API tests run against real Postgres so that migrations are exercised.\n"
    "Start one with `docker compose up -d db`, or point ANSARI_TEST_DATABASE_URL "
    "at your own instance."
)


def _test_database_url() -> str:
    return os.environ.get("ANSARI_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _create_database_if_missing(url: str) -> None:
    """Create the test database, connecting via the `postgres` maintenance DB.

    Keeps the test database separate from the development one so running the
    suite never destroys local data.
    """
    target = make_url(url)
    admin_engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def engine() -> Generator[Engine]:
    url = _test_database_url()
    try:
        _create_database_if_missing(url)
    except OperationalError:
        message = _UNAVAILABLE.format(url=url)
        # Skipping locally is a convenience; skipping in CI would silently
        # delete this suite's coverage, so there it is a failure.
        if os.environ.get("CI"):
            pytest.fail(message, pytrace=False)
        pytest.skip(message, allow_module_level=True)

    test_engine = create_engine(url, pool_pre_ping=True)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session]:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    with Session(engine) as session:
        yield session


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
