"""Integration tests for grounded RAG, citation synthesis, multi-tenant isolation, and evaluation benchmarks."""

import uuid
import pytest
from httpx import AsyncClient

from src.evaluation.benchmark import (
    DEFAULT_BENCHMARK_DATASET,
    BenchmarkRunner,
    compute_mrr,
    compute_recall_at_k,
    compute_reciprocal_rank,
)


@pytest.mark.asyncio
async def test_end_to_end_grounded_rag(client: AsyncClient) -> None:
    """Verify end-to-end grounded RAG: upload doc -> query RAG endpoint -> grounded answer with citation provenance."""
    # 1. Create project
    proj_res = await client.post("/api/v1/projects", json={"name": "RAG Grounded Project"})
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 2. Upload technical document
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
    doc_id = upload_res.json()["id"]

    # 3. Query RAG endpoint
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "Alembic database migrations", "top_k": 3, "temperature": 0.0},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    # 4. Verify grounded response and citation markers
    assert rag_data["query"] == "Alembic database migrations"
    assert "[1]" in rag_data["answer"]
    assert "Alembic" in rag_data["answer"]
    assert rag_data["chunks_evaluated"] >= 1
    assert len(rag_data["citations"]) >= 1

    citation = rag_data["citations"][0]
    assert citation["citation_id"] == 1
    assert citation["filename"] == "alembic_guide.md"
    assert citation["document_id"] == doc_id
    assert uuid.UUID(citation["chunk_id"]) is not None
    assert citation["start_offset"] == 0
    assert citation["end_offset"] > 0


@pytest.mark.asyncio
async def test_ungrounded_negative_query(client: AsyncClient) -> None:
    """Verify that asking for unavailable information returns polite rejection without hallucinations."""
    # 1. Create project and upload document
    proj_res = await client.post("/api/v1/projects", json={"name": "Negative RAG Project"})
    project_id = proj_res.json()["id"]

    text = "DevPilot uses Python 3.11 with FastAPI and SQLAlchemy 2.0 for backend services."
    files = {"file": ("tech_stack.txt", text.encode("utf-8"), "text/plain")}
    upload_res = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files=files,
    )
    assert upload_res.status_code == 201

    # 2. Query for completely unavailable topic
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "quantum entanglement laser teleportation protocol", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    assert "I do not have enough information in the provided documents to answer this question." in rag_data["answer"]
    assert rag_data["citations"] == []
    assert rag_data["chunks_evaluated"] >= 1


@pytest.mark.asyncio
async def test_rag_multi_tenant_isolation(client: AsyncClient) -> None:
    """Verify strict multi-tenant isolation: Project A never answers using or cites Project B chunks."""
    # 1. Create Project Alpha and Project Beta
    res_a = await client.post("/api/v1/projects", json={"name": "Tenant Alpha"})
    project_a = res_a.json()["id"]

    res_b = await client.post("/api/v1/projects", json={"name": "Tenant Beta"})
    project_b = res_b.json()["id"]

    # 2. Upload distinct documents
    doc_a = "Alpha system handles front-end React component rendering and state stores."
    await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_a},
        files={"file": ("frontend.txt", doc_a.encode("utf-8"), "text/plain")},
    )

    doc_b = "Beta system handles Terraform infrastructure provisioning and VPC networking."
    await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_b},
        files={"file": ("terraform.txt", doc_b.encode("utf-8"), "text/plain")},
    )

    # 3. Query Project Alpha for Beta's content -> must be rejected
    rag_a = await client.post(
        f"/api/v1/projects/{project_a}/rag",
        json={"query": "Terraform infrastructure provisioning VPC networking", "top_k": 3},
    )
    assert rag_a.status_code == 200
    assert "I do not have enough information in the provided documents to answer this question." in rag_a.json()["answer"]
    assert rag_a.json()["citations"] == []

    # 4. Query Project Beta for Alpha's content -> must be rejected
    rag_b = await client.post(
        f"/api/v1/projects/{project_b}/rag",
        json={"query": "React component rendering state stores", "top_k": 3},
    )
    assert rag_b.status_code == 200
    assert "I do not have enough information in the provided documents to answer this question." in rag_b.json()["answer"]
    assert rag_b.json()["citations"] == []

    # 5. Query Project Alpha for Alpha's content -> must succeed with citations only for frontend.txt
    rag_a_valid = await client.post(
        f"/api/v1/projects/{project_a}/rag",
        json={"query": "React component rendering", "top_k": 3},
    )
    assert rag_a_valid.status_code == 200
    assert "[1]" in rag_a_valid.json()["answer"]
    assert len(rag_a_valid.json()["citations"]) >= 1
    for cit in rag_a_valid.json()["citations"]:
        assert cit["filename"] == "frontend.txt"


def test_benchmark_metrics_calculation() -> None:
    """Verify calculation of Recall@k, Reciprocal Rank, and Mean Reciprocal Rank (MRR)."""
    # 1. Recall@k
    retrieved = ["doc1.md", "doc2.md", "doc3.md"]
    assert compute_recall_at_k(retrieved, "doc1.md", k=1) == 1.0
    assert compute_recall_at_k(retrieved, "doc2.md", k=1) == 0.0
    assert compute_recall_at_k(retrieved, "doc2.md", k=2) == 1.0
    assert compute_recall_at_k(retrieved, "doc4.md", k=3) == 0.0
    assert compute_recall_at_k(retrieved, "doc1.md", k=0) == 0.0

    # 2. Reciprocal Rank
    assert compute_reciprocal_rank(retrieved, "doc1.md") == 1.0
    assert compute_reciprocal_rank(retrieved, "doc2.md") == 0.5
    assert compute_reciprocal_rank(retrieved, "doc3.md") == pytest.approx(1.0 / 3, rel=1e-3)
    assert compute_reciprocal_rank(retrieved, "missing.md") == 0.0

    # 3. MRR
    rankings = [1, 2, 4, None]
    expected_mrr = (1.0 / 1 + 1.0 / 2 + 1.0 / 4 + 0.0) / 4  # 1.75 / 4 = 0.4375
    assert compute_mrr(rankings) == pytest.approx(expected_mrr, rel=1e-3)
    assert compute_mrr([]) == 0.0

    # 4. Benchmark Runner evaluation of static predictions
    predictions = [
        {"expected": "docA.md", "retrieved": ["docA.md", "docB.md", "docC.md"]},
        {"expected": "docB.md", "retrieved": ["docX.md", "docB.md", "docC.md"]},
        {"expected": "docC.md", "retrieved": ["docX.md", "docY.md", "docC.md"]},
        {"expected": "docD.md", "retrieved": ["docX.md", "docY.md", "docZ.md"]},
    ]
    result = BenchmarkRunner.evaluate_static_predictions(predictions)
    assert result.queries_evaluated == 4
    assert result.recall_at_1 == 0.25  # 1 out of 4 (only first query)
    assert result.recall_at_3 == 0.75  # 3 out of 4 (first 3 queries)
    # MRR = (1 + 0.5 + 1/3 + 0) / 4 = (1.8333) / 4 = 0.4583
    assert result.mrr == pytest.approx(0.4583, rel=1e-3)


@pytest.mark.asyncio
async def test_benchmark_runner_with_retriever() -> None:
    """Verify BenchmarkRunner executing against the default dataset."""
    assert len(DEFAULT_BENCHMARK_DATASET) >= 5

    # Mock retriever function mapping queries to predicted documents
    async def mock_retriever(query: str, top_k: int) -> list[str]:
        # Return the expected document ranked first for odd indices, second for even
        for idx, item in enumerate(DEFAULT_BENCHMARK_DATASET):
            if item.query == query:
                if idx % 2 == 0:
                    return [item.expected_doc, "other.md"][:top_k]
                return ["distractor.md", item.expected_doc][:top_k]
        return ["unknown.md"][:top_k]

    runner = BenchmarkRunner()
    res = await runner.run(mock_retriever, top_k=3)
    assert res.queries_evaluated == len(DEFAULT_BENCHMARK_DATASET)
    assert res.recall_at_3 == 1.0
    assert res.mrr > 0.5


@pytest.mark.asyncio
async def test_rag_nonexistent_project_returns_404(client: AsyncClient) -> None:
    """Verify RAG query on a non-existent project returns HTTP 404."""
    random_id = uuid.uuid4()
    rag_res = await client.post(
        f"/api/v1/projects/{random_id}/rag",
        json={"query": "test query", "top_k": 3},
    )
    assert rag_res.status_code == 404
    assert f"Project with ID '{random_id}' does not exist." in rag_res.json()["detail"]


@pytest.mark.asyncio
async def test_rag_empty_project_returns_polite_rejection(client: AsyncClient) -> None:
    """Verify RAG query on a project with no documents returns polite rejection."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Empty Project"})
    project_id = proj_res.json()["id"]

    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "What is this project about?", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()
    assert "I do not have enough information in the provided documents to answer this question." in rag_data["answer"]
    assert rag_data["citations"] == []
    assert rag_data["chunks_evaluated"] == 0


@pytest.mark.asyncio
async def test_rag_query_validation_error(client: AsyncClient) -> None:
    """Verify input validation for invalid RAG request payloads."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Validation Project"})
    project_id = proj_res.json()["id"]

    # Empty query
    res1 = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "", "top_k": 3},
    )
    assert res1.status_code == 422

    # Invalid top_k > 10
    res2 = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "valid query", "top_k": 15},
    )
    assert res2.status_code == 422

    # Invalid temperature > 1.0
    res3 = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "valid query", "temperature": 2.0},
    )
    assert res3.status_code == 422


# Added tests for new search functionality and benchmark comparison

import asyncio
from typing import List

import pytest
from httpx import AsyncClient

from src.services.search import lexical_keyword_search
from src.evaluation.benchmark import BenchmarkRunner, DEFAULT_BENCHMARK_DATASET

# Simple mock chunk class for lexical_keyword_search tests
class MockChunk:
    def __init__(self, content: str):
        self.content = content

@pytest.mark.asyncio
async def test_lexical_keyword_search():
    """Verify lexical_keyword_search ranks chunks by token overlap."""
    query = "fastembed model"
    chunks = [
        MockChunk("Fastembed provides a model for embeddings."),  # contains both tokens
        MockChunk("This is unrelated text.",),
        MockChunk("Fastembed is a library."),
        MockChunk("Model serves many purposes."),
    ]
    results = lexical_keyword_search(query, chunks)
    # Expect the chunk containing both tokens to be first
    assert results[0].content.lower().count("fastembed") > 0
    assert results[0].content.lower().count("model") > 0
    # Ensure that subsequent chunks have non‑increasing overlap scores
    overlaps = []
    query_tokens = set([t for t in query.lower().split()])
    for chunk in results:
        chunk_tokens = set([t for t in chunk.content.lower().split()])
        overlaps.append(len(query_tokens & chunk_tokens))
    assert overlaps == sorted(overlaps, reverse=True)

@pytest.mark.asyncio
async def test_compare_retrieval_modes():
    """Run BenchmarkRunner.compare_retrieval_modes with mock retrievers.

    The mock retrievers simply return the expected document ID as the top result.
    """
    runner = BenchmarkRunner()

    async def mock_keyword_retriever(query: str, top_k: int) -> List[str]:
        # Find the matching BenchmarkQuery and return its expected_doc as the sole result
        for q in DEFAULT_BENCHMARK_DATASET:
            if q.query == query:
                return [q.expected_doc]
        return []

    async def mock_vector_retriever(query: str, top_k: int) -> List[str]:
        # Same behavior as keyword retriever for testing purposes
        return await mock_keyword_retriever(query, top_k)

    results = await runner.compare_retrieval_modes(mock_keyword_retriever, mock_vector_retriever, top_k=3)
    # Both modes should achieve perfect Recall@1 and MRR because the expected doc is returned first
    for mode in ("keyword", "vector"):
        res = results[mode]
        assert res.recall_at_1 == 1.0
        assert res.recall_at_3 == 1.0
        assert res.mrr == 1.0
