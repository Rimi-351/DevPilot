"""Integration tests for ProcessingJob REST endpoints."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_job_lifecycle(client: AsyncClient) -> None:
    """Verify full job lifecycle: create (PENDING) -> update (IN_PROGRESS) -> complete (COMPLETED)."""
    # Create project and document
    proj_res = await client.post("/api/v1/projects", json={"name": "Job Test Project"})
    project_id = proj_res.json()["id"]

    doc_res = await client.post(
        "/api/v1/documents",
        json={"project_id": project_id, "filename": "spec.md", "file_type": "text/markdown"},
    )
    document_id = doc_res.json()["id"]

    # 1. Enqueue job
    job_payload = {
        "project_id": project_id,
        "document_id": document_id,
        "job_type": "document_indexing",
        "payload": {"chunk_size": 512, "embedding_model": "text-embedding-3-small"},
    }
    create_res = await client.post("/api/v1/jobs", json=job_payload)
    assert create_res.status_code == 201
    job = create_res.json()
    assert job["status"] == "PENDING"
    assert job["job_type"] == "document_indexing"
    assert job["payload"]["chunk_size"] == 512
    job_id = job["id"]

    # 2. Update to IN_PROGRESS
    progress_res = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"status": "IN_PROGRESS"},
    )
    assert progress_res.status_code == 200
    assert progress_res.json()["status"] == "IN_PROGRESS"

    # 3. Update to COMPLETED with result payload
    complete_res = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "status": "COMPLETED",
            "result": {"chunks_processed": 42, "status": "success"},
        },
    )
    assert complete_res.status_code == 200
    completed_job = complete_res.json()
    assert completed_job["status"] == "COMPLETED"
    assert completed_job["result"]["chunks_processed"] == 42

    # 4. Fetch job by ID
    get_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id


@pytest.mark.asyncio
async def test_create_job_nonexistent_project(client: AsyncClient) -> None:
    """Verify 404 when creating job with missing project."""
    res = await client.post(
        "/api/v1/jobs",
        json={
            "project_id": str(uuid.uuid4()),
            "job_type": "ast_parsing",
        },
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_filter_status(client: AsyncClient) -> None:
    """Verify filtering jobs by job status."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Job Filter Project"})
    project_id = proj_res.json()["id"]

    # Create 1 job
    await client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "code_linting"},
    )

    list_res = await client.get(f"/api/v1/jobs?project_id={project_id}&job_status=PENDING")
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["status"] == "PENDING"


@pytest.mark.asyncio
async def test_job_cross_tenant_isolation_returns_403(client: AsyncClient) -> None:
    """Verify that cross-tenant access to create, list, read, update, or delete jobs returns 403."""
    tenant_a_headers = {"X-API-Key": "tenant-alpha"}
    tenant_b_headers = {"X-API-Key": "tenant-beta"}

    # 1. Tenant A creates Project A
    proj_res = await client.post(
        "/api/v1/projects",
        json={"name": "Alpha Jobs Project"},
        headers=tenant_a_headers,
    )
    assert proj_res.status_code == 201
    project_a_id = proj_res.json()["id"]

    # 2. Tenant B attempts to enqueue a job on Tenant A's project -> 403 Forbidden
    res_cross_create = await client.post(
        "/api/v1/jobs",
        json={"project_id": project_a_id, "job_type": "indexing"},
        headers=tenant_b_headers,
    )
    assert res_cross_create.status_code == 403

    # 3. Tenant A creates Job A
    res_job_a = await client.post(
        "/api/v1/jobs",
        json={"project_id": project_a_id, "job_type": "indexing"},
        headers=tenant_a_headers,
    )
    assert res_job_a.status_code == 201
    job_a_id = res_job_a.json()["id"]

    # 4. Tenant B attempts to read Tenant A's job -> 403 Forbidden
    res_cross_get = await client.get(
        f"/api/v1/jobs/{job_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_get.status_code == 403

    # 5. Tenant B attempts to update Tenant A's job via PATCH /jobs/{id} -> 403 Forbidden
    res_cross_patch = await client.patch(
        f"/api/v1/jobs/{job_a_id}",
        json={"status": "FAILED"},
        headers=tenant_b_headers,
    )
    assert res_cross_patch.status_code == 403

    # 6. Tenant B attempts to update Tenant A's job via PATCH /jobs/{id}/status -> 403 Forbidden
    res_cross_status = await client.patch(
        f"/api/v1/jobs/{job_a_id}/status",
        json={"status": "FAILED"},
        headers=tenant_b_headers,
    )
    assert res_cross_status.status_code == 403

    # 7. Tenant B attempts to delete Tenant A's job -> 403 Forbidden
    res_cross_delete = await client.delete(
        f"/api/v1/jobs/{job_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_delete.status_code == 403

    # 8. Tenant B lists jobs with filter project_id=project_a_id -> 403 Forbidden
    res_cross_list = await client.get(
        f"/api/v1/jobs?project_id={project_a_id}",
        headers=tenant_b_headers,
    )
    assert res_cross_list.status_code == 403

    # 9. Tenant B lists jobs without project_id -> returns empty list without leaking Tenant A's job
    res_tenant_b_jobs = await client.get(
        "/api/v1/jobs",
        headers=tenant_b_headers,
    )
    assert res_tenant_b_jobs.status_code == 200
    job_ids = [j["id"] for j in res_tenant_b_jobs.json()["items"]]
    assert job_a_id not in job_ids


@pytest.mark.asyncio
async def test_job_status_dedicated_endpoint(client: AsyncClient) -> None:
    """Verify that dedicated PATCH /jobs/{id}/status endpoint functions for owner."""
    owner_headers = {"X-API-Key": "tenant-delta"}

    # 1. Create project & job
    proj_res = await client.post(
        "/api/v1/projects",
        json={"name": "Delta Status Project"},
        headers=owner_headers,
    )
    project_id = proj_res.json()["id"]

    job_res = await client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "status_check"},
        headers=owner_headers,
    )
    job_id = job_res.json()["id"]

    # 2. Call PATCH /jobs/{id}/status
    status_res = await client.patch(
        f"/api/v1/jobs/{job_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=owner_headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_job_ingestion_failure_transitions_to_failed_with_error_message(client: AsyncClient) -> None:
    """Verify that a failed background ingestion job transitions to FAILED with non-empty error_message."""
    from unittest.mock import patch

    # 1. Create project
    proj_res = await client.post("/api/v1/projects", json={"name": "Job Failure Test Project"})
    project_id = proj_res.json()["id"]

    # 2. Simulate extraction failure on document upload
    simulated_err = "Simulated text extraction parser failure"
    with patch("src.services.ingestion.pipeline.extract_text_from_file", side_effect=ValueError(simulated_err)):
        files = {
            "file": ("corrupt.pdf", b"%PDF-corrupt-binary", "application/pdf"),
        }
        upload_res = await client.post("/api/v1/documents/upload", data={"project_id": project_id}, files=files)
        assert upload_res.status_code == 201
        job_id = upload_res.json()["job_id"]

    # 3. Poll job status
    job_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()

    assert job_data["status"] == "FAILED"
    assert job_data["error_message"] is not None
    assert len(job_data["error_message"]) > 0
    assert simulated_err in job_data["error_message"]
    assert job_data["started_at"] is not None
    assert job_data["completed_at"] is not None


@pytest.mark.asyncio
async def test_job_pagination_bounds_and_deterministic_slicing(client: AsyncClient) -> None:
    """Verify pagination bounds (422 on skip < 0 or limit > 100 or limit < 1) and deterministic slicing on jobs."""
    # Bounds checking
    res_neg_skip = await client.get("/api/v1/jobs?skip=-1")
    assert res_neg_skip.status_code == 422

    res_zero_limit = await client.get("/api/v1/jobs?limit=0")
    assert res_zero_limit.status_code == 422

    res_large_limit = await client.get("/api/v1/jobs?limit=101")
    assert res_large_limit.status_code == 422

    # Deterministic multi-page slicing
    proj_res = await client.post("/api/v1/projects", json={"name": "Jobs Slicing Project"})
    proj_id = proj_res.json()["id"]

    created_job_ids = []
    for i in range(5):
        j_res = await client.post("/api/v1/jobs", json={"project_id": proj_id, "job_type": f"task_{i}"})
        assert j_res.status_code == 201
        created_job_ids.append(j_res.json()["id"])

    # Slice 1: skip=0, limit=2
    res_s1 = await client.get(f"/api/v1/jobs?project_id={proj_id}&skip=0&limit=2")
    assert res_s1.status_code == 200
    page1 = res_s1.json()
    assert len(page1["items"]) == 2
    assert page1["skip"] == 0
    assert page1["limit"] == 2

    # Slice 2: skip=2, limit=2
    res_s2 = await client.get(f"/api/v1/jobs?project_id={proj_id}&skip=2&limit=2")
    assert res_s2.status_code == 200
    page2 = res_s2.json()
    assert len(page2["items"]) == 2
    assert page2["skip"] == 2

    # Assert no overlap between slices
    p1_ids = {j["id"] for j in page1["items"]}
    p2_ids = {j["id"] for j in page2["items"]}
    assert p1_ids.isdisjoint(p2_ids)


