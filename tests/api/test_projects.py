from fastapi.testclient import TestClient


def _create_project(client: TestClient, name: str = "payment-api") -> dict:
    response = client.post(
        "/projects",
        json={"name": name, "repo_url": "https://github.com/org/payment-api", "language": "python"},
    )
    assert response.status_code == 201
    return response.json()


def test_create_and_get_project(client: TestClient) -> None:
    created = _create_project(client)
    response = client.get(f"/projects/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "payment-api"


def test_create_duplicate_project_conflicts(client: TestClient) -> None:
    _create_project(client)
    response = client.post(
        "/projects",
        json={
            "name": "payment-api",
            "repo_url": "https://github.com/org/payment-api",
            "language": "python",
        },
    )
    assert response.status_code == 409


def test_list_projects(client: TestClient) -> None:
    _create_project(client, "svc-a")
    _create_project(client, "svc-b")
    response = client.get("/projects")
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"svc-a", "svc-b"}


def test_get_missing_project_404(client: TestClient) -> None:
    response = client.get("/projects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_project(client: TestClient) -> None:
    created = _create_project(client)
    response = client.delete(f"/projects/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/projects/{created['id']}").status_code == 404
