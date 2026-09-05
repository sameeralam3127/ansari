from fastapi.testclient import TestClient


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/projects",
        json={"name": "svc", "repo_url": "https://github.com/org/svc", "language": "python"},
    )
    return response.json()["id"]


def test_trigger_and_list_pipeline_runs(client: TestClient) -> None:
    project_id = _create_project(client)
    response = client.post(f"/projects/{project_id}/pipelines", json={"commit_sha": "a" * 40})
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "pending"

    listed = client.get(f"/projects/{project_id}/pipelines")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_update_pipeline_status_sets_finished_at(client: TestClient) -> None:
    project_id = _create_project(client)
    run = client.post(f"/projects/{project_id}/pipelines", json={"commit_sha": "a" * 40}).json()

    response = client.patch(
        f"/projects/{project_id}/pipelines/{run['id']}/status",
        json={"status": "succeeded"},
    )
    assert response.status_code == 200
    assert response.json()["finished_at"] is not None


def test_deploy_and_rollback(client: TestClient) -> None:
    project_id = _create_project(client)
    env = client.post(
        f"/projects/{project_id}/environments",
        json={"name": "production", "cluster": "prod-cluster", "namespace": "svc"},
    ).json()
    run = client.post(f"/projects/{project_id}/pipelines", json={"commit_sha": "a" * 40}).json()

    deployment = client.post(
        "/deployments",
        json={"environment_id": env["id"], "pipeline_run_id": run["id"], "image_tag": "svc:abc123"},
    )
    assert deployment.status_code == 201
    deployment_id = deployment.json()["id"]

    rollback = client.post(f"/deployments/{deployment_id}/rollback")
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"
