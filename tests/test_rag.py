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


def test_citation_verification_service_unit() -> None:
    """Verify that CitationVerificationService accurately audits citations, strips invalid/hallucinated tags,

    normalizes valid references, and calculates grounding metrics.
    """
    from src.core.guardrails import CitationVerificationService

    service = CitationVerificationService(max_unsupported_threshold=0.20)
    fake_chunk_id = uuid.uuid4()
    context_chunks = [
        {
            "index": 1,
            "chunk_id": fake_chunk_id,
            "document_id": uuid.uuid4(),
            "filename": "database_guide.md",
            "content": "PostgreSQL database migrations using Alembic manage schema evolution.",
        },
        {
            "index": 2,
            "chunk_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "filename": "database_guide.md",
            "content": "SQLAlchemy 2.0 provides declarative mappings and async sessions.",
        },
    ]

    # 1. Pure valid citations
    raw1 = "PostgreSQL migrations manage schema evolution [1]. SQLAlchemy 2.0 provides declarative mappings [2]."
    res1 = service.verify_and_filter_citations(raw1, context_chunks)
    assert res1.is_grounded is True
    assert res1.citation_correctness == 1.0
    assert res1.unsupported_claims_rate == 0.0
    assert len(res1.valid_citations) == 2
    assert res1.invalid_citations == []
    assert res1.cleaned_answer == raw1

    # 2. Out-of-bounds citation index [99] and mixed multi-citation [1, 99]
    raw2 = "PostgreSQL migrations manage schema evolution [1, 99]. The warp engine operates at lightspeed [88]."
    res2 = service.verify_and_filter_citations(raw2, context_chunks)
    assert res2.is_grounded is False
    assert "[99]" in res2.invalid_citations
    assert "[88]" in res2.invalid_citations
    assert "[99]" not in res2.cleaned_answer
    assert "[88]" not in res2.cleaned_answer
    assert "[1]" in res2.cleaned_answer
    assert "warp engine" in res2.cleaned_answer
    assert res2.citation_correctness < 1.0

    # 3. Fabricated chunk UUID
    invented_uuid = "00000000-0000-0000-0000-000000000000"
    raw3 = f"Some claim referencing unretrieved chunk [chunk: {invented_uuid}]."
    res3 = service.verify_and_filter_citations(raw3, context_chunks)
    assert res3.is_grounded is False
    assert any(invented_uuid in c for c in res3.invalid_citations)
    assert invented_uuid not in res3.cleaned_answer

    # 4. Valid chunk UUID normalized to [1]
    raw4 = f"Grounded fact referencing known chunk [chunk: {fake_chunk_id}]."
    res4 = service.verify_and_filter_citations(raw4, context_chunks)
    assert "[1]" in res4.cleaned_answer
    assert len(res4.valid_citations) == 1
    assert res4.invalid_citations == []


@pytest.mark.asyncio
async def test_rag_endpoint_exposes_grounding_and_citation_metrics(client: AsyncClient) -> None:
    """Verify that the RAG endpoint exposes is_grounded, unsupported_claims_rate,

    citation_correctness, and invalid_citations_stripped in the response.
    """
    # 1. Create project & upload document
    proj_res = await client.post("/api/v1/projects", json={"name": "Grounding Metrics Project"})
    project_id = proj_res.json()["id"]

    doc_text = "FastAPI is a modern, fast web framework for building APIs with Python 3.8+."
    files = {"file": ("fastapi.txt", doc_text.encode(), "text/plain")}
    await client.post("/api/v1/documents/upload", data={"project_id": project_id}, files=files)

    # 2. Query RAG endpoint
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "FastAPI web framework", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    assert rag_data["is_grounded"] is True
    assert rag_data["unsupported_claims_rate"] == 0.0
    assert rag_data["citation_correctness"] == 1.0
    assert rag_data["invalid_citations_stripped"] == []
    assert len(rag_data["citations"]) >= 1


@pytest.mark.asyncio
async def test_rag_anti_hallucination_guardrail_strips_invalid_citations_and_flags_ungrounded(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that when an LLM synthesizes an answer containing hallucinated citation markers,

    the guardrail strips them from the response, logs them, and marks the answer as ungrounded.
    """
    from unittest.mock import AsyncMock
    from src.services.rag import get_rag_service

    # 1. Create project & upload document
    proj_res = await client.post("/api/v1/projects", json={"name": "Anti-Hallucination Project"})
    project_id = proj_res.json()["id"]

    doc_text = "PostgreSQL provides ACID compliant transactional database storage."
    files = {"file": ("postgres.txt", doc_text.encode(), "text/plain")}
    await client.post("/api/v1/documents/upload", data={"project_id": project_id}, files=files)

    # 2. Mock LLM service to simulate hallucinated citations [1] and [99]
    rag_service = get_rag_service()
    hallucinated_answer = (
        "PostgreSQL provides ACID compliant storage [1]. "
        "The server utilizes dark energy gravitational containment fields [99]."
    )

    mock_generate = AsyncMock(return_value=(hallucinated_answer, []))
    monkeypatch.setattr(rag_service.llm_service, "generate_grounded_answer", mock_generate)

    # 3. Query RAG endpoint
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "PostgreSQL storage features", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    # 4. Assert invalid citation [99] was stripped from answer
    assert "[99]" not in rag_data["answer"]
    assert "[1]" in rag_data["answer"]
    assert "[99]" in rag_data["invalid_citations_stripped"]
    assert rag_data["is_grounded"] is False
    assert rag_data["citation_correctness"] == 0.5
    assert rag_data["unsupported_claims_rate"] > 0.0
    assert len(rag_data["citations"]) == 1
    assert rag_data["citations"][0]["filename"] == "postgres.txt"


@pytest.mark.asyncio
async def test_rag_grounded_query_high_citation_correctness(client: AsyncClient) -> None:
    """Test 1: Grounded query where all cited sources exist in the retrieved chunks.

    Asserts high citation correctness (1.0), is_grounded=True, and valid chunk mappings.
    """
    proj_res = await client.post("/api/v1/projects", json={"name": "Grounded Citation Integrity Project"})
    project_id = proj_res.json()["id"]

    doc_text = (
        "PostgreSQL database migrations using Alembic manage schema evolution. "
        "Alembic automatically discovers model definitions from SQLAlchemy metadata."
    )
    files = {"file": ("alembic_docs.md", doc_text.encode(), "text/markdown")}
    await client.post("/api/v1/documents/upload", data={"project_id": project_id}, files=files)

    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "Alembic schema migrations", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    assert rag_data["is_grounded"] is True
    assert rag_data["citation_correctness"] == 1.0
    assert rag_data["unsupported_claims_rate"] == 0.0
    assert len(rag_data["citations"]) >= 1
    assert rag_data["invalid_citations_stripped"] == []
    for citation in rag_data["citations"]:
        assert citation["filename"] == "alembic_docs.md"
        assert citation["chunk_id"] is not None


@pytest.mark.asyncio
async def test_rag_ungrounded_hallucinated_source_rejection_telemetry(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 2: Ungrounded query / hallucinated source test where the answer references non-existent chunks.

    Asserts citation guardrail catches it, strips invalid citations, and returns ungrounded rejection telemetry.
    """
    from unittest.mock import AsyncMock
    from src.services.rag import get_rag_service

    proj_res = await client.post("/api/v1/projects", json={"name": "Hallucinated Source Rejection Project"})
    project_id = proj_res.json()["id"]

    doc_text = "DevPilot platform provides hybrid search retrieval with Reciprocal Rank Fusion."
    files = {"file": ("architecture.txt", doc_text.encode(), "text/plain")}
    await client.post("/api/v1/documents/upload", data={"project_id": project_id}, files=files)

    rag_service = get_rag_service()
    fake_chunk_id = "11111111-2222-3333-4444-555555555555"
    hallucinated_answer = (
        f"DevPilot uses RRF [1]. "
        f"Unicorn propulsion engines accelerate the server into hyper-space [chunk: {fake_chunk_id}][99]."
    )

    mock_generate = AsyncMock(return_value=(hallucinated_answer, []))
    monkeypatch.setattr(rag_service.llm_service, "generate_grounded_answer", mock_generate)

    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "DevPilot retrieval engine", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    # Verify invalid citations stripped and rejection telemetry recorded
    assert rag_data["is_grounded"] is False
    assert fake_chunk_id not in rag_data["answer"]
    assert "[99]" not in rag_data["answer"]
    assert "[1]" in rag_data["answer"]
    assert len(rag_data["invalid_citations_stripped"]) >= 2
    assert rag_data["citation_correctness"] < 1.0
    assert rag_data["unsupported_claims_rate"] > 0.0


@pytest.mark.asyncio
async def test_rag_negative_query_coca_cola_recipe_polite_rejection(client: AsyncClient) -> None:
    """Verify that negative queries ('What is the secret recipe of Coca-Cola?' when no such document exists)

    return polite rejections without hallucinating facts.
    """
    proj_res = await client.post("/api/v1/projects", json={"name": "Software Engineering Docs"})
    project_id = proj_res.json()["id"]

    tech_doc = (
        "DevPilot backend architecture runs on Python 3.11 with FastAPI, "
        "SQLAlchemy 2.0 async engine, and PostgreSQL 16 database."
    )
    files = {"file": ("tech_specs.txt", tech_doc.encode(), "text/plain")}
    await client.post("/api/v1/documents/upload", data={"project_id": project_id}, files=files)

    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "What is the secret recipe of Coca-Cola?", "top_k": 3},
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    # Assert polite rejection without hallucinating ingredients or facts
    assert "I do not have enough information in the provided documents to answer this question." in rag_data["answer"]
    assert "coca-cola" not in rag_data["answer"].lower()
    assert "recipe" not in rag_data["answer"].lower()
    assert rag_data["citations"] == []
    assert rag_data["is_grounded"] is True
    assert rag_data["unsupported_claims_rate"] == 0.0
    assert rag_data["citation_correctness"] == 1.0
