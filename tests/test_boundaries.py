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
