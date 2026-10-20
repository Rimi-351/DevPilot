"""Integration and unit test suite for Bounded Agentic Workflow and API endpoint.

Covers:
  1. test_agent_bounded_phase_progression
  2. test_agent_argument_validation_and_self_correction
  3. test_agent_phase_boundary_violation
  4. test_agent_per_tool_timeout_guardrail
  5. test_agent_loop_cap_enforcement
  6. test_agent_endpoint_auth_and_tenant_isolation
"""

import asyncio
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.services.agent.schemas import (
    AgentProposal,
    ToolExecutionStatus,
    WorkflowPhase,
    WorkflowReport,
)
from src.services.agent.workflow import BoundedAgent, GuardedToolDispatcher


@pytest.mark.asyncio
async def test_agent_bounded_phase_progression(client: AsyncClient) -> None:
    """Ingest document chunk into a test project, run agent workflow, and verify

    complete 4-phase progression: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE.
    """
    # 1. Create a project
    proj_res = await client.post(
        "/api/v1/projects",
        json={"name": "Agent Progression Test Project", "description": "FSM Verification"},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 2. Ingest document with technical content
    doc_text = (
        "PostgreSQL 16 and SQLAlchemy 2.0 with asyncpg provide native async connection pooling. "
        "Alembic manages database schema evolution using declarative migration revisions. "
        "DevPilot enforces multi-tenant row-level access control via API key headers."
    )
    upload_res = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files={"file": ("architecture_guide.md", doc_text.encode("utf-8"), "text/markdown")},
    )
    assert upload_res.status_code == 201

    # 3. Trigger the agent workflow endpoint
    response = await client.post(
        f"/api/v1/projects/{project_id}/agent/workflow",
        json={"goal": "Analyze SQLAlchemy async connection pooling and migrations"},
    )
    assert response.status_code == 200
    data = response.json()

    # 4. Validate WorkflowReport structure
    report = WorkflowReport.model_validate(data)
    assert report.status == "COMPLETED"
    assert report.phase_history == ["SEARCH", "INSPECT", "SUMMARIZE", "PROPOSE"]
    assert report.total_iterations == 4
    assert report.total_runtime_seconds >= 0.0
    assert len(report.execution_logs) == 3  # SEARCH, INSPECT, SUMMARIZE logs

    # Verify tool logs all succeeded
    assert all(log.status == ToolExecutionStatus.SUCCESS for log in report.execution_logs)
    assert [log.tool_name for log in report.execution_logs] == [
        "search_project",
        "inspect_chunk",
        "summarize_text",
    ]

    # Verify final proposal
    assert report.final_proposal is not None
    assert isinstance(report.final_proposal, AgentProposal)
    assert len(report.final_proposal.title) > 0
    assert len(report.final_proposal.executive_summary) > 0
    assert len(report.final_proposal.action_items) >= 1
    assert 0.0 <= report.final_proposal.confidence_score <= 1.0


@pytest.mark.asyncio
async def test_agent_argument_validation_and_self_correction(db_session: AsyncSession) -> None:
    """Verify that malformed arguments trigger VALIDATION_ERROR, get reflected

    into context, and the agent self-corrects on the next iteration.
    """
    proj_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    content = "FastAPI dependency injection manages async database sessions with automatic commit."

    # Seed in-memory chunk
    doc = Document(
        id=doc_id,
        project_id=proj_id,
        filename="di.md",
        file_type="text/markdown",
        file_size_bytes=len(content),
    )
    chunk = DocumentChunk(
        id=chunk_id,
        project_id=proj_id,
        document_id=doc_id,
        content=content,
        start_offset=0,
        end_offset=len(content),
        chunk_index=0,
    )
    db_session.add(doc)
    db_session.add(chunk)
    await db_session.commit()

    agent = BoundedAgent(project_id=proj_id, session=db_session)

    # Mock tool caller:
    # Iter 1 (SEARCH): invalid query (length < 3) -> VALIDATION_ERROR
    # Iter 2 (SEARCH): valid query -> SUCCESS
    # Iter 3 (INSPECT): valid chunk_id -> SUCCESS
    # Iter 4 (SUMMARIZE): valid text -> SUCCESS
    # Iter 5 (PROPOSE): synthesis -> COMPLETED
    call_step = {"count": 0}

    async def dynamic_llm_tool_call(messages: list[dict[str, Any]], phase: WorkflowPhase) -> dict[str, Any]:
        call_step["count"] += 1
        if call_step["count"] == 1:
            # Inject short query violating min_length=3 constraint
            return {"tool_name": "search_project", "arguments": {"query": "ab"}}
        elif call_step["count"] == 2:
            return {"tool_name": "search_project", "arguments": {"query": "FastAPI dependency injection"}}
        elif phase == WorkflowPhase.INSPECT:
            return {"tool_name": "inspect_chunk", "arguments": {"chunk_id": str(chunk_id)}}
        elif phase == WorkflowPhase.SUMMARIZE:
            return {"tool_name": "summarize_text", "arguments": {"text": content}}
        return agent._mock_tool_call(messages, phase)

    agent._call_llm_for_tool = dynamic_llm_tool_call  # type: ignore[assignment]

    report = await agent.run(user_goal="Investigate FastAPI dependency injection")

    assert report.status == "COMPLETED"
    # Total iterations = 5 (1 validation failure + 3 tool successes + 1 propose)
    assert report.total_iterations == 5
    assert len(report.execution_logs) == 4

    # First execution log must record VALIDATION_ERROR
    val_log = report.execution_logs[0]
    assert val_log.status == ToolExecutionStatus.VALIDATION_ERROR
    assert val_log.tool_name == "search_project"
    assert "query" in str(val_log.output_or_error)

    # Second execution log must succeed for search_project
    succ_log = report.execution_logs[1]
    assert succ_log.status == ToolExecutionStatus.SUCCESS
    assert succ_log.tool_name == "search_project"

    assert report.final_proposal is not None


@pytest.mark.asyncio
async def test_agent_phase_boundary_violation(db_session: AsyncSession) -> None:
    """Verify that GuardedToolDispatcher immediately rejects out-of-order tool calls

    with ToolExecutionStatus.PHASE_VIOLATION.
    """
    dispatcher = GuardedToolDispatcher()
    proj_id = uuid.uuid4()

    # Calling summarize_text during SEARCH phase
    payload, log = await dispatcher.execute(
        tool_name="summarize_text",
        raw_arguments={"text": "A" * 30},
        current_phase=WorkflowPhase.SEARCH,
        iteration=1,
        project_id=proj_id,
        session=db_session,
    )

    assert log.status == ToolExecutionStatus.PHASE_VIOLATION
    assert log.validated_inputs is None
    assert payload["status"] == "phase_violation"
    assert "belongs to phase" in payload["message"]
    assert "called during phase 'SEARCH'" in payload["message"]

    # Calling inspect_chunk during SUMMARIZE phase
    _payload2, log2 = await dispatcher.execute(
        tool_name="inspect_chunk",
        raw_arguments={"chunk_id": str(uuid.uuid4())},
        current_phase=WorkflowPhase.SUMMARIZE,
        iteration=2,
        project_id=proj_id,
        session=db_session,
    )
    assert log2.status == ToolExecutionStatus.PHASE_VIOLATION


@pytest.mark.asyncio
async def test_agent_per_tool_timeout_guardrail(db_session: AsyncSession) -> None:
    """Verify that slow tool execution triggers TIMEOUT cleanly without crashing the loop."""
    dispatcher = GuardedToolDispatcher(per_tool_timeout=0.05)
    proj_id = uuid.uuid4()

    async def slow_tool(query: str, project_id: uuid.UUID, session: AsyncSession) -> dict[str, Any]:
        await asyncio.sleep(0.3)
        return {"query": query, "chunks": []}

    with patch("src.services.agent.workflow.search_project", side_effect=slow_tool):
        payload, log = await dispatcher.execute(
            tool_name="search_project",
            raw_arguments={"query": "Timeout testing query"},
            current_phase=WorkflowPhase.SEARCH,
            iteration=1,
            project_id=proj_id,
            session=db_session,
        )

    assert log.status == ToolExecutionStatus.TIMEOUT
    assert log.runtime_seconds >= 0.04
    assert payload["status"] == "timeout"
    assert "exceeded" in payload["message"] and "timeout" in payload["message"]
    # Inputs were validated before timeout was triggered
    assert log.validated_inputs == {"query": "Timeout testing query"}


@pytest.mark.asyncio
async def test_agent_loop_cap_enforcement(db_session: AsyncSession) -> None:
    """Verify that repeated non-advancing failures cause the agent to halt

    strictly at MAX_ITERATIONS = 5 with status MAX_ITERATIONS_REACHED.
    """
    proj_id = uuid.uuid4()
    agent = BoundedAgent(project_id=proj_id, session=db_session, max_iterations=5)

    async def permanently_failing_tool(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Transient infrastructure outage")

    with patch("src.services.agent.workflow.search_project", side_effect=permanently_failing_tool):
        report = await agent.run(user_goal="Attempt an impossible search")

    assert report.status == "MAX_ITERATIONS_REACHED"
    assert report.total_iterations == 5
    assert len(report.execution_logs) == 5
    assert all(l.status == ToolExecutionStatus.EXECUTION_ERROR for l in report.execution_logs)
    assert report.final_proposal is None


@pytest.mark.asyncio
async def test_agent_endpoint_auth_and_tenant_isolation(client: AsyncClient) -> None:
    """Verify endpoint security: 401 unauthenticated, 403 cross-tenant, 404 missing project,

    and 200 OK for authorized tenant owner.
    """
    tenant_alpha = {"X-API-Key": "tenant-alpha-key"}
    tenant_beta = {"X-API-Key": "tenant-beta-key"}

    # 1. Create project owned by Tenant Alpha
    res_create = await client.post(
        "/api/v1/projects",
        json={"name": "Tenant Alpha Project", "description": "Proprietary Alpha Corpus"},
        headers=tenant_alpha,
    )
    assert res_create.status_code == 201
    project_id = res_create.json()["id"]

    # Ingest a sample chunk into Tenant Alpha's project
    doc_text = "Tenant Alpha proprietary data chunk for agent research."
    res_upload = await client.post(
        "/api/v1/documents/upload",
        data={"project_id": project_id},
        files={"file": ("alpha_doc.txt", doc_text.encode("utf-8"), "text/plain")},
        headers=tenant_alpha,
    )
    assert res_upload.status_code == 201

    # 2. Missing X-API-Key -> 401 Unauthorized
    async with AsyncClient(transport=client._transport, base_url="http://test") as unauth_client:
        res_no_auth = await unauth_client.post(
            f"/api/v1/projects/{project_id}/agent/workflow",
            json={"goal": "Exfiltrate proprietary data"},
        )
        assert res_no_auth.status_code == 401
        assert "Missing or invalid API key" in res_no_auth.json()["detail"]

    # 3. Cross-tenant access -> 403 Forbidden (Tenant Beta calling Tenant Alpha's project)
    res_forbidden = await client.post(
        f"/api/v1/projects/{project_id}/agent/workflow",
        json={"goal": "Analyze unauthorized project"},
        headers=tenant_beta,
    )
    assert res_forbidden.status_code == 403

    # 4. Non-existent project -> 404 Not Found
    non_existent_id = str(uuid.uuid4())
    res_not_found = await client.post(
        f"/api/v1/projects/{non_existent_id}/agent/workflow",
        json={"goal": "Research ghost project"},
        headers=tenant_alpha,
    )
    assert res_not_found.status_code == 404
    assert res_not_found.json()["detail"] == "Project not found"

    # 5. Invalid request payload (goal < 5 chars) -> 422 Unprocessable Entity
    res_invalid_payload = await client.post(
        f"/api/v1/projects/{project_id}/agent/workflow",
        json={"goal": "tiny"},
        headers=tenant_alpha,
    )
    assert res_invalid_payload.status_code == 422

    # 6. Authorized Tenant Alpha execution -> 200 OK
    res_success = await client.post(
        f"/api/v1/projects/{project_id}/agent/workflow",
        json={"goal": "Analyze proprietary data chunk and summarize"},
        headers=tenant_alpha,
    )
    assert res_success.status_code == 200
    report_data = res_success.json()
    assert report_data["status"] == "COMPLETED"
    assert "phase_history" in report_data
    assert "final_proposal" in report_data
    assert report_data["final_proposal"] is not None
