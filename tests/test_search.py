"""Integration tests for semantic retrieval, chunk persistence, and search provenance."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document_chunk import DocumentChunk


@pytest.mark.asyncio
async def test_document_upload_persists_chunks_and_embeddings(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify document upload runs background task, persisting DocumentChunk rows with embeddings."""
    # 1. Create project
    proj_res = await client.post("/api/v1/projects", json={"name": "Embedding Project"})
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 2. Upload text document
    content = b"DevPilot integrates FastAPI and SQLAlchemy 2.0 with vector embeddings for semantic search."
    files = {"file": ("integration.txt", content, "text/plain")}
    data = {"project_id": project_id}

    upload_res = await client.post("/api/v1/documents/upload", data=data, files=files)
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # 3. Verify job metadata
    job_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["status"] == "COMPLETED"
    assert job_data["result"]["embedded"] is True
    assert job_data["result"]["chunks_count"] >= 1
    assert job_data["result"]["dimensions"] == 384

    # 4. Query DB directly to verify DocumentChunk rows
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == uuid.UUID(doc_id))
        .order_by(DocumentChunk.chunk_index)
    )
    res = await db_session.execute(stmt)
    chunks = res.scalars().all()

    assert len(chunks) >= 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(content.decode("utf-8"))
    assert chunks[0].content == content.decode("utf-8")
    assert chunks[0].embedding is not None
    assert len(chunks[0].embedding) == 384


@pytest.mark.asyncio
async def test_semantic_search_returns_relevant_chunk(client: AsyncClient) -> None:
    """Verify semantic search query returns chunk with high cosine similarity score."""
    # 1. Create project
    proj_res = await client.post("/api/v1/projects", json={"name": "Semantic Project"})
    project_id = proj_res.json()["id"]

    # 2. Upload document with distinctive technical terms
    text = (
        "PostgreSQL database migrations using Alembic manage schema evolution. "
        "Alembic auto-generates migration scripts from SQLAlchemy 2.0 declarative metadata."
    )
    files = {"file": ("alembic_guide.md", text.encode("utf-8"), "text/markdown")}
    upload_res = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files=files,
    )
    assert upload_res.status_code == 201

    # 3. Perform semantic search for matching terms
    search_res = await client.post(
        f"/api/v1/projects/{project_id}/search",
        json={"query": "Alembic database migrations", "top_k": 3},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()

    assert search_data["query"] == "Alembic database migrations"
    assert search_data["total_results"] >= 1
    top_hit = search_data["results"][0]
    assert "Alembic" in top_hit["content"]
    assert top_hit["score"] > 0.0


@pytest.mark.asyncio
async def test_search_multi_tenant_isolation(client: AsyncClient) -> None:
    """Verify searches in Project A never leak documents or chunks from Project B."""
    # Create Project A and Project B
    res_a = await client.post("/api/v1/projects", json={"name": "Project Alpha"})
    project_a_id = res_a.json()["id"]

    res_b = await client.post("/api/v1/projects", json={"name": "Project Beta"})
    project_b_id = res_b.json()["id"]

    # Upload unique doc to Project A
    doc_a_text = "Alpha project manages front-end client components and UI state."
    await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_a_id},
        files={"file": ("frontend.txt", doc_a_text.encode("utf-8"), "text/plain")},
    )

    # Upload unique doc to Project B
    doc_b_text = "Beta project manages Kubernetes cluster infrastructure and container orchestration."
    await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_b_id},
        files={"file": ("k8s.txt", doc_b_text.encode("utf-8"), "text/plain")},
    )

    # Search in Project A for Kubernetes content from Project B
    search_a = await client.post(
        f"/api/v1/projects/{project_a_id}/search",
        json={"query": "Kubernetes cluster container orchestration", "top_k": 5},
    )
    assert search_a.status_code == 200
    results_a = search_a.json()["results"]

    # Ensure none of Project B's chunks appear in Project A's search results
    for result in results_a:
        assert result["filename"] != "k8s.txt"
        assert "Kubernetes" not in result["content"]

    # Search in Project B for front-end content from Project A
    search_b = await client.post(
        f"/api/v1/projects/{project_b_id}/search",
        json={"query": "front-end client components", "top_k": 5},
    )
    assert search_b.status_code == 200
    results_b = search_b.json()["results"]

    for result in results_b:
        assert result["filename"] != "frontend.txt"
        assert "front-end" not in result["content"]


@pytest.mark.asyncio
async def test_search_provenance_verification(client: AsyncClient) -> None:
    """Verify search response returns full provenance: filename, chunk index, and offsets."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Provenance Project"})
    project_id = proj_res.json()["id"]

    filename = "provenance_doc.txt"
    content = "Detailed provenance tracking includes character offsets and source file metadata."
    upload_res = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files={"file": (filename, content.encode("utf-8"), "text/plain")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    search_res = await client.post(
        f"/api/v1/projects/{project_id}/search",
        json={"query": "provenance tracking", "top_k": 1},
    )
    assert search_res.status_code == 200
    results = search_res.json()["results"]
    assert len(results) == 1

    item = results[0]
    assert item["document_id"] == doc_id
    assert item["filename"] == filename
    assert item["chunk_index"] == 0
    assert item["start_offset"] == 0
    assert item["end_offset"] == len(content)
    assert item["content"] == content
    assert isinstance(item["score"], float)
    assert uuid.UUID(item["chunk_id"]) is not None


@pytest.mark.asyncio
async def test_search_nonexistent_project_returns_404(client: AsyncClient) -> None:
    """Verify search on a non-existent project returns HTTP 404."""
    random_id = uuid.uuid4()
    search_res = await client.post(
        f"/api/v1/projects/{random_id}/search",
        json={"query": "test query", "top_k": 5},
    )
    assert search_res.status_code == 404
    assert f"Project with ID '{random_id}' does not exist." in search_res.json()["detail"]
