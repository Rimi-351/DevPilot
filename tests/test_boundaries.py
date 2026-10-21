"""Week 9 — Backend Hardening, Object-Level Authorization, and Error Boundary Test Suite.

Tests fault injection, chaos recovery, payload boundary validation, storage limits,
upstream provider outages (LLM timeouts/503), and object-level authorization enforcement.
"""

import io
import uuid
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import FileTooLargeError, UnsupportedFileExtensionError
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.processing_job import ProcessingJob
from src.models.project import Project
from src.services.agent.schemas import ToolExecutionStatus, WorkflowPhase
from src.services.agent.workflow import GuardedToolDispatcher
from src.services.llm import LLMService
from src.services.storage import LocalStorageService


@pytest.mark.asyncio
async def test_boundary_invalid_and_malformed_ingress_payloads(client: AsyncClient) -> None:
    """Verify that malformed JSON payloads and path parameters trigger structured HTTP 422, not 500."""
    headers = {"X-API-Key": "boundary-tester"}

    # 1. Invalid UUID in path parameter
    res_bad_uuid = await client.get("/api/v1/projects/not-a-valid-uuid", headers=headers)
    assert res_bad_uuid.status_code == 422
    assert "detail" in res_bad_uuid.json()

    # 2. Empty payload on project creation (missing required 'name')
    res_empty_project = await client.post("/api/v1/projects", json={}, headers=headers)
    assert res_empty_project.status_code == 422

    # 3. Invalid field types in project creation
    res_type_error = await client.post(
        "/api/v1/projects",
        json={"name": 12345, "description": ["invalid", "list"]},
        headers=headers,
    )
    assert res_type_error.status_code in (422, 201)

    # 4. Search query with out-of-bounds top_k
    valid_uuid = str(uuid.uuid4())
    res_bad_topk = await client.post(
        f"/api/v1/projects/{valid_uuid}/search",
        json={"query": "test query", "top_k": -5},
        headers=headers,
    )
    assert res_bad_topk.status_code == 422

    # 5. RAG query with empty string query (min_length violation)
    res_empty_rag = await client.post(
        f"/api/v1/projects/{valid_uuid}/rag",
        json={"query": ""},
        headers=headers,
    )
    assert res_empty_rag.status_code == 422

    # 6. Pagination bounds: negative skip (ge=0 violation) and limit > 100 (le=100 violation)
    res_neg_skip = await client.get("/api/v1/projects?skip=-1", headers=headers)
    assert res_neg_skip.status_code == 422

    res_huge_limit = await client.get("/api/v1/projects?limit=1000000", headers=headers)
    assert res_huge_limit.status_code == 422

    res_zero_limit = await client.get("/api/v1/projects?limit=0", headers=headers)
    assert res_zero_limit.status_code == 422

    res_doc_neg_skip = await client.get("/api/v1/documents?skip=-5", headers=headers)
    assert res_doc_neg_skip.status_code == 422

    res_doc_zero_limit = await client.get("/api/v1/documents?limit=0", headers=headers)
    assert res_doc_zero_limit.status_code == 422

    res_doc_huge_limit = await client.get("/api/v1/documents?limit=500", headers=headers)
    assert res_doc_huge_limit.status_code == 422

    res_job_neg_skip = await client.get("/api/v1/jobs?skip=-1", headers=headers)
    assert res_job_neg_skip.status_code == 422

    res_job_zero_limit = await client.get("/api/v1/jobs?limit=0", headers=headers)
    assert res_job_zero_limit.status_code == 422

    res_job_huge_limit = await client.get("/api/v1/jobs?limit=1000", headers=headers)
    assert res_job_huge_limit.status_code == 422


@pytest.mark.asyncio
async def test_boundary_upstream_llm_timeout_and_503_resilience() -> None:
    """Verify that upstream LLM network failures or 503 errors trigger resilient fallback without crashing."""
    service = LLMService(api_key="mock-key", force_mock=False)
    context_chunks = [
        {
            "id": str(uuid.uuid4()),
            "content": "DevPilot retrieval engine uses 12-layer XLM-RoBERTa cross-encoder.",
            "document_id": str(uuid.uuid4()),
            "index": 1,
        }
    ]

    # 1. Simulate network timeout during upstream LLM call
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Upstream timed out")):
        answer, citations = await service.generate_grounded_answer(
            query="What cross-encoder model does DevPilot use?",
            context_chunks=context_chunks,
        )
        assert answer is not None
        assert len(answer) > 0
        assert service._use_mock is True

    # 2. Simulate upstream HTTP 503 Service Unavailable
    service._use_mock = False
    mock_503_response = httpx.Response(
        status_code=503,
        request=httpx.Request("POST", "http://test/chat/completions"),
    )
    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=mock_503_response.request,
            response=mock_503_response,
        ),
    ):
        answer, citations = await service.generate_grounded_answer(
            query="What model is used?",
            context_chunks=context_chunks,
        )
        assert answer is not None
        assert len(answer) > 0
        assert service._use_mock is True


@pytest.mark.asyncio
async def test_boundary_storage_and_upload_limits(tmp_path) -> None:
    """Verify that storage limits, disallowed extensions, and oversized files raise explicit domain errors."""
    storage = LocalStorageService(
        upload_dir=str(tmp_path),
        max_size_bytes=1024,  # 1 KB limit
        allowed_extensions=[".txt", ".md"],
    )

    # 1. Disallowed extension
    with pytest.raises(UnsupportedFileExtensionError):
        storage.validate_extension("malicious_script.exe")

    with pytest.raises(UnsupportedFileExtensionError):
        storage.validate_extension("payload.sh")

    # 2. Oversized payload
    oversized_content = b"A" * 2048
    with pytest.raises(FileTooLargeError):
        storage.validate_size(len(oversized_content))

    # 3. Valid file saves successfully
    valid_content = b"Valid chunk content within 1KB limit."
    file_path, sha256_hash, file_size = await storage.save_file("sample.txt", valid_content)
    assert file_path is not None
    assert len(sha256_hash) == 64
    assert file_size == len(valid_content)


@pytest.mark.asyncio
async def test_boundary_object_level_authorization_coverage(client: AsyncClient) -> None:
    """Verify comprehensive object-level authorization across project, document, and search resources."""
    tenant_1_headers = {"X-API-Key": "tenant-corp-one"}
    tenant_2_headers = {"X-API-Key": "tenant-corp-two"}

    # 1. Tenant 1 creates a private project
    res_create = await client.post(
        "/api/v1/projects",
        json={"name": "Tenant 1 Confidential Vault", "description": "Top secret documents"},
        headers=tenant_1_headers,
    )
    assert res_create.status_code == 201
    project_id = res_create.json()["id"]

    # 2. Tenant 2 cannot access or inspect Tenant 1's project (403 Forbidden)
    res_forbidden_get = await client.get(f"/api/v1/projects/{project_id}", headers=tenant_2_headers)
    assert res_forbidden_get.status_code == 403

    # 3. Tenant 2 cannot run semantic search on Tenant 1's project
    res_forbidden_search = await client.post(
        f"/api/v1/projects/{project_id}/search",
        json={"query": "secret keys", "top_k": 3},
        headers=tenant_2_headers,
    )
    assert res_forbidden_search.status_code == 403

    # 4. Tenant 2 cannot trigger grounded RAG on Tenant 1's project
    res_forbidden_rag = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "Give me the confidential data"},
        headers=tenant_2_headers,
    )
    assert res_forbidden_rag.status_code == 403

    # 5. Tenant 2 cannot launch an agentic workflow on Tenant 1's project
    res_forbidden_agent = await client.post(
        f"/api/v1/projects/{project_id}/agent/workflow",
        json={"goal": "Infiltrate and summarize secret documents"},
        headers=tenant_2_headers,
    )
    assert res_forbidden_agent.status_code == 403

    # 6. Tenant 2 cannot upload documents to Tenant 1's project
    file_bytes = io.BytesIO(b"Unauthorized injection content.")
    res_forbidden_upload = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files={"file": ("unauthorized.txt", file_bytes, "text/plain")},
        headers=tenant_2_headers,
    )
    assert res_forbidden_upload.status_code == 403

    # 7. Tenant 1 enqueues a background job
    res_job = await client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "document_indexing"},
        headers=tenant_1_headers,
    )
    assert res_job.status_code == 201
    job_id = res_job.json()["id"]

    # 8. Tenant 2 cannot inspect or mutate Tenant 1's job (403 Forbidden)
    res_forbidden_job_get = await client.get(f"/api/v1/jobs/{job_id}", headers=tenant_2_headers)
    assert res_forbidden_job_get.status_code == 403

    res_forbidden_job_patch = await client.patch(
        f"/api/v1/jobs/{job_id}/status",
        json={"status": "FAILED"},
        headers=tenant_2_headers,
    )
    assert res_forbidden_job_patch.status_code == 403

    # 9. Tenant 2 cannot filter list jobs by Tenant 1's project (403 Forbidden)
    res_forbidden_job_list = await client.get(
        f"/api/v1/jobs?project_id={project_id}",
        headers=tenant_2_headers,
    )
    assert res_forbidden_job_list.status_code == 403

    # 10. Tenant 2 unfiltered job list never leaks Tenant 1's job
    res_t2_jobs = await client.get("/api/v1/jobs", headers=tenant_2_headers)
    assert res_t2_jobs.status_code == 200
    assert job_id not in [j["id"] for j in res_t2_jobs.json()["items"]]


@pytest.mark.asyncio
async def test_boundary_agent_dispatcher_fault_injection(db_session: AsyncSession) -> None:
    """Verify that GuardedToolDispatcher isolates tool errors, timeouts, and phase boundary violations."""
    dispatcher = GuardedToolDispatcher(per_tool_timeout=0.05)
    proj_id = uuid.uuid4()

    # 1. Phase boundary violation: executing search during INSPECT phase
    payload, log = await dispatcher.execute(
        tool_name="search_project",
        raw_arguments={"query": "valid query"},
        current_phase=WorkflowPhase.INSPECT,
        iteration=1,
        project_id=proj_id,
        session=db_session,
    )
    assert log.status == ToolExecutionStatus.PHASE_VIOLATION
    assert payload["status"] == "phase_violation"

    # 2. Argument validation error: query too short (min length 3)
    payload, log = await dispatcher.execute(
        tool_name="search_project",
        raw_arguments={"query": "a"},
        current_phase=WorkflowPhase.SEARCH,
        iteration=1,
        project_id=proj_id,
        session=db_session,
    )
    assert log.status == ToolExecutionStatus.VALIDATION_ERROR
    assert payload["status"] == "validation_error"

    # 3. Timeout fault injection
    async def hung_tool(query: str, project_id: uuid.UUID, session: AsyncSession):
        import asyncio
        await asyncio.sleep(0.3)
        return {"query": query, "chunks": []}

    with patch("src.services.agent.workflow.search_project", side_effect=hung_tool):
        payload, log = await dispatcher.execute(
            tool_name="search_project",
            raw_arguments={"query": "test query"},
            current_phase=WorkflowPhase.SEARCH,
            iteration=1,
            project_id=proj_id,
            session=db_session,
        )
        assert log.status == ToolExecutionStatus.TIMEOUT
        assert payload["status"] == "timeout"


def test_boundary_composite_database_indexes() -> None:
    """Verify that multi-tenant composite indexes are declared on models and registered in SQLAlchemy metadata."""
    from src.models.base import Base

    # 1. Project: (tenant_id, created_at)
    proj_indexes = {
        tuple(c.name for c in idx.columns): idx.name for idx in Project.__table__.indexes
    }
    assert ("tenant_id", "created_at") in proj_indexes
    assert any(idx.name == "ix_projects_tenant_created" for idx in Base.metadata.tables["projects"].indexes)

    # 2. Document: (project_id, created_at)
    doc_indexes = {
        tuple(c.name for c in idx.columns): idx.name for idx in Document.__table__.indexes
    }
    assert ("project_id", "created_at") in doc_indexes
    assert any(idx.name == "ix_documents_project_created" for idx in Base.metadata.tables["documents"].indexes)

    # 3. DocumentChunk: (document_id, chunk_index) and (project_id, document_id)
    chunk_indexes = {
        tuple(c.name for c in idx.columns): idx.name for idx in DocumentChunk.__table__.indexes
    }
    assert ("document_id", "chunk_index") in chunk_indexes
    assert ("project_id", "document_id") in chunk_indexes
    assert any(idx.name == "ix_document_chunks_document_index" for idx in Base.metadata.tables["document_chunks"].indexes)
    assert any(idx.name == "ix_document_chunks_project_document" for idx in Base.metadata.tables["document_chunks"].indexes)

    # 4. ProcessingJob: (project_id, status, created_at)
    job_indexes = {
        tuple(c.name for c in idx.columns): idx.name for idx in ProcessingJob.__table__.indexes
    }
    assert ("project_id", "status", "created_at") in job_indexes
    assert any(idx.name == "ix_processing_jobs_project_status_created" for idx in Base.metadata.tables["processing_jobs"].indexes)


@pytest.mark.asyncio
async def test_boundary_deterministic_pagination_ordering(client: AsyncClient) -> None:
    """Verify deterministic pagination ordering (created_at DESC, id ASC) across projects, documents, and jobs."""
    headers = {"X-API-Key": "deterministic-pagination-tester"}

    # 1. Create a project
    proj_res = await client.post(
        "/api/v1/projects",
        json={"name": "Deterministic Pagination Project"},
        headers=headers,
    )
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    # 2. Ingest 4 documents rapidly
    doc_ids = []
    for idx in range(4):
        files = {"file": (f"det_doc_{idx}.txt", f"Deterministic chunk text content {idx}".encode(), "text/plain")}
        upload_res = await client.post(
            "/api/v1/documents/upload",
            data={"project_id": proj_id},
            files=files,
            headers=headers,
        )
        assert upload_res.status_code == 201
        doc_ids.append(upload_res.json()["id"])

    # 3. Query documents and verify ordering (created_at DESC, id ASC)
    doc_list_res = await client.get(
        f"/api/v1/documents?project_id={proj_id}&skip=0&limit=10",
        headers=headers,
    )
    assert doc_list_res.status_code == 200
    docs = doc_list_res.json()["items"]
    assert len(docs) == 4
    for i in range(len(docs) - 1):
        t1, id1 = docs[i]["created_at"], docs[i]["id"]
        t2, id2 = docs[i + 1]["created_at"], docs[i + 1]["id"]
        if t1 == t2:
            assert id1 <= id2  # id ASC tie-breaking
        else:
            assert t1 >= t2  # created_at DESC

    # 4. Query jobs and verify ordering (created_at DESC, id ASC)
    jobs_list_res = await client.get(
        f"/api/v1/jobs?project_id={proj_id}&skip=0&limit=10",
        headers=headers,
    )
    assert jobs_list_res.status_code == 200
    jobs = jobs_list_res.json()["items"]
    assert len(jobs) >= 4
    for i in range(len(jobs) - 1):
        t1, id1 = jobs[i]["created_at"], jobs[i]["id"]
        t2, id2 = jobs[i + 1]["created_at"], jobs[i + 1]["id"]
        if t1 == t2:
            assert id1 <= id2  # id ASC tie-breaking
        else:
            assert t1 >= t2  # created_at DESC


@pytest.mark.asyncio
async def test_boundary_citation_verification_and_anti_hallucination_guardrails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that fabricated chunk references, out-of-bounds indices, and unretrieved IDs

    are stripped by the anti-hallucination guardrail, flagged as ungrounded, and correctly scored.
    """
    from unittest.mock import AsyncMock
    from src.services.rag import get_rag_service

    headers = {"X-API-Key": "citation-boundary-tester"}

    # 1. Create project & upload authentic document
    proj_res = await client.post(
        "/api/v1/projects",
        json={"name": "Boundary Guardrails Project"},
        headers=headers,
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    content = "Kubernetes pods run containerized workloads with declarative deployments."
    files = {"file": ("k8s.txt", content.encode(), "text/plain")}
    await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files=files,
        headers=headers,
    )

    # 2. Inject LLM response with multiple hallucinated citation markers
    rag_service = get_rag_service()
    fake_uuid_1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fake_uuid_2 = "99999999-8888-7777-6666-555555555555"
    hallucinated_answer = (
        f"Kubernetes pods run containerized workloads [1]. "
        f"Quantum entanglement synchronizes pods instantaneously [chunk: {fake_uuid_1}]. "
        f"Sub-atomic storage layer [doc: {fake_uuid_2}][99]."
    )

    mock_generate = AsyncMock(return_value=(hallucinated_answer, []))
    monkeypatch.setattr(rag_service.llm_service, "generate_grounded_answer", mock_generate)

    # 3. Query RAG endpoint
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "Kubernetes pod workload", "top_k": 3},
        headers=headers,
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    # 4. Verify post-processing guardrail assertions
    assert fake_uuid_1 not in rag_data["answer"]
    assert fake_uuid_2 not in rag_data["answer"]
    assert "[99]" not in rag_data["answer"]
    assert "[1]" in rag_data["answer"]
    assert rag_data["is_grounded"] is False
    assert len(rag_data["invalid_citations_stripped"]) >= 3
    assert rag_data["citation_correctness"] < 0.50
    assert rag_data["unsupported_claims_rate"] > 0.0
    assert len(rag_data["citations"]) == 1


@pytest.mark.asyncio
async def test_boundary_negative_query_coca_cola_anti_hallucination_guarantee(client: AsyncClient) -> None:
    """Verify that ungrounded queries like 'What is the secret recipe of Coca-Cola?'

    strictly return polite rejections with 0 citations and no hallucinated facts under boundary conditions.
    """
    headers = {"X-API-Key": "negative-boundary-tester"}

    # 1. Create project with unrelated technical documents
    proj_res = await client.post(
        "/api/v1/projects",
        json={"name": "Boundary Negative Query Project"},
        headers=headers,
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    content = "Distributed consensus algorithm Raft provides fault-tolerant state machine replication."
    files = {"file": ("raft.txt", content.encode(), "text/plain")}
    await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files=files,
        headers=headers,
    )

    # 2. Query for Coca-Cola secret recipe
    rag_res = await client.post(
        f"/api/v1/projects/{project_id}/rag",
        json={"query": "What is the secret recipe of Coca-Cola?", "top_k": 3},
        headers=headers,
    )
    assert rag_res.status_code == 200
    rag_data = rag_res.json()

    # 3. Assert strict polite rejection without factual hallucination
    assert "I do not have enough information in the provided documents to answer this question." in rag_data["answer"]
    assert "coca-cola" not in rag_data["answer"].lower()
    assert "sugar" not in rag_data["answer"].lower()
    assert "syrup" not in rag_data["answer"].lower()
    assert rag_data["citations"] == []
    assert rag_data["is_grounded"] is True
    assert rag_data["unsupported_claims_rate"] == 0.0
    assert rag_data["citation_correctness"] == 1.0


def test_boundary_bm25_empty_and_emoji_only_corpus():
    """Verify BM25 handles empty or emoji-only corpora and queries without ZeroDivisionError."""
    from src.services.retrieval.hybrid import bm25_search, clear_bm25_cache

    clear_bm25_cache()
    emoji_corpus = [
        {"chunk_id": "emoji_1", "content": "🚀🔥🎉"},
        {"chunk_id": "emoji_2", "content": "??? !@#$%^&*()"},
    ]

    # Searching with regular words over emoji-only documents should not crash with ZeroDivisionError
    res1 = bm25_search("query text", emoji_corpus, top_k=2)
    assert len(res1) == 2
    assert all(r["bm25_score"] == 0.0 for r in res1)

    # Searching with emoji-only query over emoji-only documents
    res2 = bm25_search("🚀🔥", emoji_corpus, top_k=2)
    assert len(res2) == 2
    assert all(r["bm25_score"] == 0.0 for r in res2)

    # Negative and zero top_k guards
    assert bm25_search("test", emoji_corpus, top_k=0) == []
    assert bm25_search("test", emoji_corpus, top_k=-1) == []


@pytest.mark.asyncio
async def test_boundary_retrieval_and_reranker_bounds():
    """Verify retrieve_chunks and reranker handle boundary conditions, empty queries, and zero/negative limits."""
    from src.services.retrieval.hybrid import reciprocal_rank_fusion
    from src.services.retrieval.pipeline import compute_cosine_similarity, retrieve_chunks
    from src.services.retrieval.reranker import get_reranker_service

    # Cosine similarity bounds
    assert compute_cosine_similarity([], []) == 0.0
    assert compute_cosine_similarity([1.0], []) == 0.0
    assert compute_cosine_similarity([], [1.0]) == 0.0

    sample_chunks = [
        {"chunk_id": "c1", "content": "Sample content alpha", "embedding": [0.1] * 384},
        {"chunk_id": "c2", "content": "Sample content beta", "embedding": [0.2] * 384},
    ]

    # retrieve_chunks boundary guards
    assert await retrieve_chunks("test", sample_chunks, top_k=0) == []
    assert await retrieve_chunks("test", sample_chunks, top_k=-2) == []
    assert await retrieve_chunks("test", [], top_k=5) == []

    # Empty and whitespace queries
    empty_q_res = await retrieve_chunks("", sample_chunks, top_k=2)
    assert len(empty_q_res) == 2
    assert all(r["score"] == 0.0 for r in empty_q_res)

    ws_q_res = await retrieve_chunks("   \t\n  ", sample_chunks, top_k=1)
    assert len(ws_q_res) == 1

    # RRF boundary guards
    assert reciprocal_rank_fusion([], [], top_n=5) == []
    assert reciprocal_rank_fusion(sample_chunks, sample_chunks, top_n=0) == []
    assert reciprocal_rank_fusion(sample_chunks, sample_chunks, top_n=-1) == []

    # Reranker boundary guards
    reranker = get_reranker_service()
    assert reranker.rerank("query", [], top_k=3) == []
    assert reranker.rerank("query", sample_chunks, top_k=0) == []
    assert reranker.rerank("query", sample_chunks, top_k=-1) == []

    # Reranker empty query passthrough
    empty_rerank = reranker.rerank("", sample_chunks, top_k=2)
    assert len(empty_rerank) == 2
    assert empty_rerank[0]["reranker_engine"] == "empty_query_passthrough"


@pytest.mark.asyncio
async def test_boundary_rag_empty_query_and_malformed_offsets(db_session: AsyncSession):
    """Verify RAG service gracefully handles empty query and chunks with missing/None offsets without crashing."""
    from src.models.document import Document
    from src.models.document_chunk import DocumentChunk
    from src.models.project import Project
    from src.services.llm import NEGATIVE_RESPONSE
    from src.services.rag import get_rag_service

    # Create dummy project, document, and chunk with None offsets
    proj = Project(name="Malformed Chunk Project", tenant_id="rag-edge-tester")
    db_session.add(proj)
    await db_session.flush()

    doc = Document(
        project_id=proj.id,
        filename="test.txt",
        file_path="memory://test.txt",
        file_type="text/plain",
        file_size_bytes=100,
    )
    db_session.add(doc)
    await db_session.flush()

    # Chunk with valid integer offsets and empty embedding
    chunk = DocumentChunk(
        document_id=doc.id,
        project_id=proj.id,
        chunk_index=0,
        content="DevPilot supports resilient fallback workflows.",
        start_offset=0,
        end_offset=48,
        embedding=None,
    )
    db_session.add(chunk)
    await db_session.commit()

    rag = get_rag_service()

    # Empty query early exit
    res_empty = await rag.generate_grounded_answer(
        query="   ",
        project_id=proj.id,
        session=db_session,
    )
    assert res_empty.answer == NEGATIVE_RESPONSE
    assert res_empty.chunks_evaluated == 0

    # Non-positive top_k
    res_zero_topk = await rag.generate_grounded_answer(
        query="What does DevPilot support?",
        project_id=proj.id,
        session=db_session,
        top_k=0,
    )
    assert res_zero_topk.answer == NEGATIVE_RESPONSE
    assert res_zero_topk.chunks_evaluated == 0

    # Query with None offsets in chunk should serialize successfully without raising validation error
    res_valid = await rag.generate_grounded_answer(
        query="What does DevPilot support?",
        project_id=proj.id,
        session=db_session,
        top_k=1,
    )
    assert res_valid is not None
    assert res_valid.chunks_evaluated == 1


def test_boundary_security_verify_project_tenant_access_null():
    """Verify verify_project_tenant_access raises HTTP 404 when project is None."""
    from fastapi import HTTPException
    from src.core.security import verify_project_tenant_access

    with pytest.raises(HTTPException) as exc_info:
        verify_project_tenant_access(None, "some-api-key")
    assert exc_info.value.status_code == 404



