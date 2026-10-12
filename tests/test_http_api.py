"""HTTP contract checks without starting external services."""

import re


def test_create_and_read_tenant_and_task(api_client):
    created = api_client.post(
        "/tenants", json={"slug": "acme-prod", "name": "Acme Production"}
    )
    assert created.status_code == 202
    tenant = created.json()
    task_id = created.headers["X-Task-ID"]
    assert tenant["status"] == "provisioning"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT.*\.\d{3}Z", tenant["created_at"])

    listed_tasks = api_client.get("/tasks", params={"tenant_id": tenant["id"]})
    assert listed_tasks.status_code == 200
    assert listed_tasks.json()[0]["id"] == task_id
    assert api_client.get(f"/tasks/{task_id}").json()["status"] == "accepted"


def test_errors_are_structured(api_client):
    duplicate = {"slug": "acme-prod", "name": "Acme"}
    api_client.post("/tenants", json=duplicate)
    response = api_client.post("/tenants", json=duplicate)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tenant_already_exists"

    missing = api_client.get("/tenants/no-such-tenant")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "tenant_not_found"


def test_bad_slug_returns_machine_readable_validation_error(api_client):
    response = api_client.post("/tenants", json={"slug": "Bad", "name": "Acme"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
