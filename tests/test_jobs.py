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
