"""Integration tests for Project REST endpoints."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_project(client: AsyncClient) -> None:
    """Verify creating a project and retrieving it by ID."""
    payload = {
        "name": "Alpha-Kernel",
        "description": "Core operating system components",
    }
    create_res = await client.post("/api/v1/projects", json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == payload["name"]
    assert created_data["description"] == payload["description"]
    assert "id" in created_data

    project_id = created_data["id"]

    # Fetch by ID
    get_res = await client.get(f"/api/v1/projects/{project_id}")
    assert get_res.status_code == 200
    fetched_data = get_res.json()
    assert fetched_data["id"] == project_id
    assert fetched_data["name"] == payload["name"]


@pytest.mark.asyncio
async def test_list_projects_pagination(client: AsyncClient) -> None:
    """Verify listing projects with pagination."""
    # Ensure at least two projects exist
    for idx in range(3):
        await client.post(
            "/api/v1/projects",
            json={"name": f"Project Batch {idx}", "description": "Testing pagination"},
        )

    res = await client.get("/api/v1/projects?page=1&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) <= 2
    assert data["page"] == 1
    assert data["page_size"] == 2


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient) -> None:
    """Verify partially updating a project."""
    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "Initial Name", "description": "Initial Desc"},
    )
    project_id = create_res.json()["id"]

    update_res = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Updated Name"},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["name"] == "Updated Name"
    assert updated_data["description"] == "Initial Desc"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient) -> None:
    """Verify deleting a project returns 204 and subsequent fetch returns 404."""
    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "To Delete"},
    )
    project_id = create_res.json()["id"]

    del_res = await client.delete(f"/api/v1/projects/{project_id}")
    assert del_res.status_code == 204

    get_res = await client.get(f"/api/v1/projects/{project_id}")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_project(client: AsyncClient) -> None:
    """Verify 404 is returned when requesting a missing project."""
    random_uuid = str(uuid.uuid4())
    res = await client.get(f"/api/v1/projects/{random_uuid}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_create_project_validation_error(client: AsyncClient) -> None:
    """Verify 422 Unprocessable Entity when required field is empty or missing."""
    res = await client.post("/api/v1/projects", json={"name": ""})
    assert res.status_code == 422
