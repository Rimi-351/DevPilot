"""Tests for read-only demo mode and safe demo credentials."""

import io
import pytest
from httpx import AsyncClient

from src.core.config import settings


@pytest.mark.asyncio
async def test_demo_mode_blocks_write_mutations(client: AsyncClient) -> None:
    """Verify that callers using demo credentials receive 403 Forbidden on write operations."""
    demo_headers = {"X-API-Key": settings.DEMO_API_KEY}

    # 1. Block project creation
    res_proj = await client.post(
        "/api/v1/projects",
        json={"name": "Malicious Demo Project", "description": "Should be blocked"},
        headers=demo_headers,
    )
    assert res_proj.status_code == 403
    assert "Demo Mode: Write operations" in res_proj.json()["detail"]

    # 2. Block document upload
    file_bytes = io.BytesIO(b"Unauthorized document content")
    res_upload = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": "00000000-0000-0000-0000-000000000000"},
        files={"file": ("test.txt", file_bytes, "text/plain")},
        headers=demo_headers,
    )
    assert res_upload.status_code == 403
    assert "Demo Mode: Write operations" in res_upload.json()["detail"]

    # 3. Block project deletion
    res_delete = await client.delete(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000",
        headers=demo_headers,
    )
    assert res_delete.status_code == 403
    assert "Demo Mode: Write operations" in res_delete.json()["detail"]


@pytest.mark.asyncio
async def test_demo_mode_allows_read_and_inference_operations(client: AsyncClient) -> None:
    """Verify that demo credentials can inspect projects, documents, search, and RAG."""
    # First, create a project with a regular tenant key
    owner_headers = {"X-API-Key": "devpilot-demo-key"}
    demo_headers = {"X-API-Key": settings.DEMO_API_KEY}

    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "DevPilot Evaluation Workspace", "description": "Seeded evaluation project"},
        headers=owner_headers,
    )
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 1. Demo key can list projects and see the evaluation workspace
    list_res = await client.get("/api/v1/projects", headers=demo_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(p["id"] == project_id for p in items)

    # 2. Demo key can inspect project by ID
    get_res = await client.get(f"/api/v1/projects/{project_id}", headers=demo_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == project_id

    # 3. Demo key can execute search (inference POST)
    search_res = await client.post(
        f"/api/v1/projects/{project_id}/search",
        json={"query": "architecture overview", "mode": "vector", "top_k": 3},
        headers=demo_headers,
    )
    assert search_res.status_code == 200
    assert "results" in search_res.json()

    # 4. Demo key can execute RAG (inference POST)
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "explain architecture"},
        headers=demo_headers,
    )
    assert rag_res.status_code == 200
    assert "answer" in rag_res.json()


@pytest.mark.asyncio
async def test_demo_mode_cannot_access_unrelated_private_tenant_project(client: AsyncClient) -> None:
    """Verify that demo credentials cannot access private projects owned by unrelated tenants."""
    private_headers = {"X-API-Key": "private-corp-tenant"}
    demo_headers = {"X-API-Key": settings.DEMO_API_KEY}

    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "Strictly Confidential Internal IP", "description": "Top secret"},
        headers=private_headers,
    )
    assert create_res.status_code == 201
    private_project_id = create_res.json()["id"]

    # Demo key attempting to access private project must return 403 Forbidden
    access_res = await client.get(f"/api/v1/projects/{private_project_id}", headers=demo_headers)
    assert access_res.status_code == 403
    assert "Forbidden" in access_res.json()["detail"]
