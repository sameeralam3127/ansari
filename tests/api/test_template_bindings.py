"""The template-bindings cache: one row per attached template, per project."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ansari.api.models import TemplateBinding


def _project(client: TestClient, name: str = "payment-api") -> str:
    response = client.post(
        "/projects",
        json={"name": name, "repo_url": f"https://github.com/org/{name}", "language": "python"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _binding(template: str = "python-service", **overrides: Any) -> dict[str, Any]:
    return {
        "template": template,
        "version": "1.1.0",
        "rendered_at": "2026-09-14T10:00:00+00:00",
        "files": {f"{template}.txt": "sha256:a"},
        **overrides,
    }


def test_put_then_get_keeps_manifest_order_and_drift_flags(client: TestClient) -> None:
    project_id = _project(client)
    payload = [_binding(), _binding("k8s-scaling", version="0.1.0", behind=True)]

    put = client.put(f"/projects/{project_id}/template-bindings", json=payload)
    assert put.status_code == 200, put.text

    got = client.get(f"/projects/{project_id}/template-bindings").json()
    assert [(b["position"], b["template"], b["behind"]) for b in got] == [
        (0, "python-service", False),
        (1, "k8s-scaling", True),
    ]
    assert got == put.json()


def test_put_replaces_the_whole_set(client: TestClient) -> None:
    """A manifest is a set: a template the repo dropped must not linger."""
    project_id = _project(client)
    url = f"/projects/{project_id}/template-bindings"
    client.put(url, json=[_binding(), _binding("k8s-scaling")])

    assert client.put(url, json=[_binding()]).status_code == 200
    assert [b["template"] for b in client.get(url).json()] == ["python-service"]

    assert client.put(url, json=[]).status_code == 200
    assert client.get(url).json() == []


def test_the_same_template_can_be_attached_twice(client: TestClient) -> None:
    project_id = _project(client)
    payload = [
        _binding("terraform-module", files={"network/main.tf": "sha256:a"}),
        _binding("terraform-module", files={"storage/main.tf": "sha256:b"}),
    ]
    response = client.put(f"/projects/{project_id}/template-bindings", json=payload)
    assert response.status_code == 200
    assert [b["position"] for b in response.json()] == [0, 1]


def test_a_file_with_two_owners_is_rejected_and_nothing_changes(client: TestClient) -> None:
    """The manifest's own invariant, applied to what's reported about it."""
    project_id = _project(client)
    url = f"/projects/{project_id}/template-bindings"
    client.put(url, json=[_binding()])

    clash = [
        _binding(files={"README.md": "sha256:a"}),
        _binding("k8s-scaling", files={"README.md": "sha256:b"}),
    ]
    response = client.put(url, json=clash)

    assert response.status_code == 422
    assert "README.md" in response.text
    assert [b["template"] for b in client.get(url).json()] == ["python-service"]


def test_a_naive_timestamp_is_rejected(client: TestClient) -> None:
    project_id = _project(client)
    response = client.put(
        f"/projects/{project_id}/template-bindings",
        json=[_binding(rendered_at="2026-09-14T10:00:00")],
    )
    assert response.status_code == 422


def test_a_binding_without_a_template_is_rejected(client: TestClient) -> None:
    project_id = _project(client)
    payload = [_binding()]
    del payload[0]["template"]
    assert client.put(f"/projects/{project_id}/template-bindings", json=payload).status_code == 422


def test_an_unknown_project_is_a_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.put(f"/projects/{missing}/template-bindings", json=[]).status_code == 404
    assert client.get(f"/projects/{missing}/template-bindings").status_code == 404


def test_the_fleet_listing_answers_who_is_behind(client: TestClient) -> None:
    payments = _project(client, "payments")
    orders = _project(client, "orders")
    client.put(f"/projects/{payments}/template-bindings", json=[_binding(behind=True)])
    client.put(
        f"/projects/{orders}/template-bindings",
        json=[_binding(), _binding("terraform-module", edited=True)],
    )

    behind = client.get("/template-bindings", params={"template": "python-service", "behind": True})
    assert [b["project_id"] for b in behind.json()] == [payments]

    edited = client.get("/template-bindings", params={"edited": True}).json()
    assert [(b["project_id"], b["template"]) for b in edited] == [(orders, "terraform-module")]

    everything = client.get("/template-bindings").json()
    assert len(everything) == 3
    assert [b["template"] for b in everything] == sorted(b["template"] for b in everything)


def test_the_fleet_listing_is_paginated(client: TestClient) -> None:
    assert client.get("/template-bindings", params={"limit": 10_000}).status_code == 422
    assert client.get("/template-bindings", params={"offset": -1}).status_code == 422


def test_deleting_a_project_removes_its_bindings(client: TestClient) -> None:
    project_id = _project(client)
    client.put(f"/projects/{project_id}/template-bindings", json=[_binding()])

    assert client.delete(f"/projects/{project_id}").status_code == 204
    assert client.get("/template-bindings").json() == []


def test_reported_at_is_timezone_aware(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    client.put(f"/projects/{project_id}/template-bindings", json=[_binding()])
    binding = db_session.query(TemplateBinding).one()
    assert binding.reported_at.tzinfo is not None
    assert binding.rendered_at.tzinfo is not None


def test_fleet_filters_are_indexed_and_positions_are_unique(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())
    indexed = {
        col for idx in inspector.get_indexes("template_bindings") for col in idx["column_names"]
    }
    assert {"project_id", "template"} <= indexed

    unique = {
        tuple(c["column_names"]) for c in inspector.get_unique_constraints("template_bindings")
    }
    assert ("project_id", "position") in unique
