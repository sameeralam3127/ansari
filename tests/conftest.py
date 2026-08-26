from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ansari.api.db import Base, get_db
from ansari.api.main import create_app


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
