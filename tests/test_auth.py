"""Authentication and cross-tenant access control test suite."""

import io
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_missing_or_empty_key_returns_401(client: AsyncClient) -> None:
    """Verify that requests missing X-API-Key header or supplying empty keys return HTTP 401."""
    # 1. Unauthenticated client (no default headers)
    async with AsyncClient(transport=client._transport, base_url="http://test") as unauth_client:
        # Missing header on projects list
        res_no_header = await unauth_client.get("/api/v1/projects")
        assert res_no_header.status_code == 401
        assert "Missing or invalid API key" in res_no_header.json()["detail"]

        # Missing header on project creation
        res_create_unauth = await unauth_client.post(
            "/api/v1/projects",
            json={"name": "Unauthorized Project"},
        )
        assert res_create_unauth.status_code == 401

        # Missing header on document upload
        file_bytes = io.BytesIO(b"Secret content")
        res_upload_unauth = await unauth_client.post(
            "/api/v1/documents/upload",
            data={"project_id": "00000000-0000-0000-0000-000000000000"},
            files={"file": ("test.txt", file_bytes, "text/plain")},
        )
        assert res_upload_unauth.status_code == 401

    # 2. Empty string key
    res_empty_key = await client.get("/api/v1/projects", headers={"X-API-Key": ""})
    assert res_empty_key.status_code == 401

    # 3. Whitespace-only key
    res_whitespace_key = await client.get("/api/v1/projects", headers={"X-API-Key": "    "})
    assert res_whitespace_key.status_code == 401


@pytest.mark.asyncio
async def test_auth_cross_tenant_access_returns_403(client: AsyncClient) -> None:
    """Verify that cross-tenant access to projects, documents, search, and RAG returns HTTP 403."""
    tenant_a_headers = {"X-API-Key": "tenant-alpha"}
    tenant_b_headers = {"X-API-Key": "tenant-beta"}

    # 1. Tenant A creates Project A
    res_create = await client.post(
        "/api/v1/projects",
        json={"name": "Alpha Confidential Project", "description": "Proprietary IP"},
        headers=tenant_a_headers,
    )
    assert res_create.status_code == 201
    project_a = res_create.json()
    project_a_id = project_a["id"]
    assert project_a["tenant_id"] == "tenant-alpha"

    # 2. Tenant B attempts to read Project A
    res_cross_get = await client.get(
        f"/api/v1/projects/{project_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_get.status_code == 403
    assert "Forbidden" in res_cross_get.json()["detail"]

    # 3. Tenant B attempts to update Project A
    res_cross_patch = await client.patch(
        f"/api/v1/projects/{project_a_id}",
        json={"name": "Compromised Project"},
        headers=tenant_b_headers,
    )
    assert res_cross_patch.status_code == 403

    # 4. Tenant B attempts to delete Project A
    res_cross_delete = await client.delete(
        f"/api/v1/projects/{project_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_delete.status_code == 403

    # 5. Tenant B attempts to upload into Project A
    file_bytes = io.BytesIO(b"Malicious injection into Alpha")
    res_cross_upload = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_a_id},
        files={"file": ("infiltrate.txt", file_bytes, "text/plain")},
        headers=tenant_b_headers,
    )
    assert res_cross_upload.status_code == 403

    # 6. Tenant B attempts semantic search on Project A
    res_cross_search = await client.post(
        f"/api/v1/projects/{project_a_id}/search",
        json={"query": "secret roadmap", "top_k": 5},
        headers=tenant_b_headers,
    )
    assert res_cross_search.status_code == 403

    # 7. Tenant B attempts RAG question answering on Project A
    res_cross_rag = await client.post(
        f"/api/v1/projects/{project_a_id}/rag",
        json={"query": "What is the secret roadmap?"},
        headers=tenant_b_headers,
    )
    assert res_cross_rag.status_code == 403

    # 8. Tenant A uploads a document into Project A
    doc_bytes = io.BytesIO(b"Alpha internal documentation")
    res_doc_create = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_a_id},
        files={"file": ("alpha_docs.txt", doc_bytes, "text/plain")},
        headers=tenant_a_headers,
    )
    assert res_doc_create.status_code == 201
    doc_id = res_doc_create.json()["id"]

    # 9. Tenant B attempts to read Tenant A's document
    res_cross_doc_get = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_doc_get.status_code == 403

    # 10. Tenant B attempts to update Tenant A's document
    res_cross_doc_patch = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"filename": "tampered.txt"},
        headers=tenant_b_headers,
    )
    assert res_cross_doc_patch.status_code == 403

    # 11. Tenant B attempts to delete Tenant A's document
    res_cross_doc_del = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_doc_del.status_code == 403

    # 12. Tenant A creates a background processing job on Project A
    res_job_create = await client.post(
        "/api/v1/jobs",
        json={"project_id": project_a_id, "job_type": "embedding_generation"},
        headers=tenant_a_headers,
    )
    assert res_job_create.status_code == 201
    job_a_id = res_job_create.json()["id"]

    # 13. Tenant B attempts to read Tenant A's job -> 403 Forbidden
    res_cross_job_get = await client.get(
        f"/api/v1/jobs/{job_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_job_get.status_code == 403

    # 14. Tenant B attempts to update Tenant A's job via PATCH /jobs/{job_id}/status -> 403 Forbidden
    res_cross_job_patch = await client.patch(
        f"/api/v1/jobs/{job_a_id}/status",
        json={"status": "FAILED"},
        headers=tenant_b_headers,
    )
    assert res_cross_job_patch.status_code == 403

    # 15. Tenant B attempts to list jobs filtered by Project A -> 403 Forbidden
    res_cross_job_list = await client.get(
        f"/api/v1/jobs?project_id={project_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_job_list.status_code == 403

    # 16. Tenant B calls GET /api/v1/jobs (unfiltered) -> Assert Tenant A's job is not leaked
    res_unfiltered_jobs = await client.get(
        "/api/v1/jobs",
        headers=tenant_b_headers,
    )
    assert res_unfiltered_jobs.status_code == 200
    b_job_ids = [j["id"] for j in res_unfiltered_jobs.json()["items"]]
    assert job_a_id not in b_job_ids


@pytest.mark.asyncio
async def test_auth_valid_owner_lifecycle_success_200(client: AsyncClient) -> None:
    """Verify that a valid tenant owner can perform standard operations successfully (HTTP 200/201)."""
    owner_headers = {"X-API-Key": "tenant-charlie"}

    # 1. Create project
    res_create = await client.post(
        "/api/v1/projects",
        json={"name": "Charlie Project", "description": "Owner verification"},
        headers=owner_headers,
    )
    assert res_create.status_code == 201
    project_id = res_create.json()["id"]

    # 2. Get project
    res_get = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=owner_headers,
    )
    assert res_get.status_code == 200
    assert res_get.json()["name"] == "Charlie Project"

    # 3. Update project
    res_update = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Charlie Project Renamed"},
        headers=owner_headers,
    )
    assert res_update.status_code == 200
    assert res_update.json()["name"] == "Charlie Project Renamed"

    # 4. Ingest document
    file_bytes = io.BytesIO(b"Charlie project specifications and documentation.")
    res_upload = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files={"file": ("specs.txt", file_bytes, "text/plain")},
        headers=owner_headers,
    )
    assert res_upload.status_code == 201
    doc_id = res_upload.json()["id"]

    # 5. List documents with project filter
    res_docs = await client.get(
        f"/api/v1/documents?project_id={project_id}",
        headers=owner_headers,
    )
    assert res_docs.status_code == 200
    assert res_docs.json()["total"] >= 1

    # 6. Search project documents
    res_search = await client.post(
        f"/api/v1/projects/{project_id}/search",
        json={"query": "specifications", "top_k": 3},
        headers=owner_headers,
    )
    assert res_search.status_code == 200

    # 7. Delete document as owner
    res_del_doc = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=owner_headers,
    )
    assert res_del_doc.status_code == 204

    # 8. Delete project as owner
    res_del_proj = await client.delete(
        f"/api/v1/projects/{project_id}",
        headers=owner_headers,
    )
    assert res_del_proj.status_code == 204
