from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
