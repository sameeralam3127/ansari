"""Coverage for the data-layer defects fixed in #19."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ansari.api.models import Project


def _create_projects(client: TestClient, count: int) -> None:
    for i in range(count):
        response = client.post(
            "/projects",
            json={
                "name": f"svc-{i:03d}",
                "repo_url": f"https://github.com/org/svc-{i:03d}",
                "language": "python",
            },
        )
        assert response.status_code == 201


def test_list_projects_is_paginated(client: TestClient) -> None:
    _create_projects(client, 5)

    first = client.get("/projects", params={"limit": 2}).json()
    assert len(first) == 2

    second = client.get("/projects", params={"limit": 2, "offset": 2}).json()
    assert len(second) == 2
    assert {p["id"] for p in first}.isdisjoint({p["id"] for p in second})


def test_pagination_is_stable_across_pages(client: TestClient) -> None:
    # Without a deterministic ORDER BY, LIMIT/OFFSET may repeat or skip rows.
    _create_projects(client, 6)
    paged = [
        p["name"]
        for offset in (0, 2, 4)
        for p in client.get("/projects", params={"limit": 2, "offset": offset}).json()
    ]
    assert paged == sorted(paged)
    assert len(set(paged)) == 6


def test_page_size_over_the_cap_is_rejected(client: TestClient) -> None:
    assert client.get("/projects", params={"limit": 10_000}).status_code == 422
    assert client.get("/projects", params={"offset": -1}).status_code == 422


def test_pipeline_status_is_updated_through_the_body_not_the_query(client: TestClient) -> None:
    project = client.post(
        "/projects",
        json={"name": "svc", "repo_url": "https://github.com/org/svc", "language": "python"},
    ).json()
    run = client.post(f"/projects/{project['id']}/pipelines", json={"commit_sha": "a" * 40}).json()
    url = f"/projects/{project['id']}/pipelines/{run['id']}/status"

    # A query parameter would leak a state change into access logs and proxy caches.
    assert client.patch(url, params={"status": "succeeded"}).status_code == 422
    assert client.patch(url, json={"status": "succeeded"}).status_code == 200


def test_timestamps_round_trip_as_timezone_aware(client: TestClient, db_session: Session) -> None:
    client.post(
        "/projects",
        json={"name": "svc", "repo_url": "https://github.com/org/svc", "language": "python"},
    )
    project = db_session.query(Project).one()

    # A naive column would silently drop the offset written by datetime.now(UTC).
    assert project.created_at.tzinfo is not None
    assert abs((datetime.now(UTC) - project.created_at).total_seconds()) < 300


def test_enum_values_are_stored_lowercase(client: TestClient, db_session: Session) -> None:
    project = client.post(
        "/projects",
        json={"name": "svc", "repo_url": "https://github.com/org/svc", "language": "python"},
    ).json()
    client.post(f"/projects/{project['id']}/pipelines", json={"commit_sha": "a" * 40})

    # SQLAlchemy defaults to storing member names, which would make direct SQL
    # disagree with the API response.
    stored = db_session.execute(text("SELECT status::text FROM pipeline_runs")).scalar()
    assert stored == "pending"


def test_foreign_keys_are_indexed(db_session: Session) -> None:
    # Postgres does not index foreign keys automatically.
    inspector = inspect(db_session.get_bind())
    for table, column in (
        ("environments", "project_id"),
        ("pipeline_runs", "project_id"),
        ("deployments", "environment_id"),
        ("deployments", "pipeline_run_id"),
    ):
        indexed = {col for idx in inspector.get_indexes(table) for col in idx["column_names"]}
        assert column in indexed, f"{table}.{column} is not indexed"
