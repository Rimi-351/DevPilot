"""Integration tests for Document REST endpoints."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_document_success(client: AsyncClient) -> None:
    """Verify document creation linked to an existing project."""
    # First create project
    proj_res = await client.post("/api/v1/projects", json={"name": "Doc Host Project"})
    project_id = proj_res.json()["id"]

    doc_payload = {
        "project_id": project_id,
        "filename": "architecture.md",
        "file_type": "text/markdown",
        "file_size_bytes": 1024,
        "file_path": "/storage/docs/architecture.md",
    }
    doc_res = await client.post("/api/v1/documents", json=doc_payload)
    assert doc_res.status_code == 201
    doc_data = doc_res.json()
    assert doc_data["filename"] == "architecture.md"
    assert doc_data["project_id"] == project_id
    assert doc_data["file_size_bytes"] == 1024


@pytest.mark.asyncio
async def test_create_document_nonexistent_project(client: AsyncClient) -> None:
    """Verify 404 when associating a document to a non-existent project."""
    doc_payload = {
        "project_id": str(uuid.uuid4()),
        "filename": "orphan.txt",
        "file_type": "text/plain",
    }
    doc_res = await client.post("/api/v1/documents", json=doc_payload)
    assert doc_res.status_code == 404


@pytest.mark.asyncio
async def test_list_documents_filtered_by_project(client: AsyncClient) -> None:
    """Verify listing documents filtered by project_id."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Filter Project"})
    project_id = proj_res.json()["id"]

    # Add 2 documents
    for name in ["doc1.pdf", "doc2.pdf"]:
        await client.post(
            "/api/v1/documents",
            json={"project_id": project_id, "filename": name, "file_type": "application/pdf"},
        )

    res = await client.get(f"/api/v1/documents?project_id={project_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_update_and_delete_document(client: AsyncClient) -> None:
    """Verify updating document metadata and deleting document."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Doc Lifecycle Project"})
    project_id = proj_res.json()["id"]

    doc_res = await client.post(
        "/api/v1/documents",
        json={"project_id": project_id, "filename": "old_name.txt", "file_type": "text/plain"},
    )
    doc_id = doc_res.json()["id"]

    # Update
    patch_res = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"filename": "new_name.txt"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["filename"] == "new_name.txt"

    # Delete
    del_res = await client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 204

    # Verify 404
    get_res = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 404
