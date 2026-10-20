"""Agent workflow execution REST endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.security import get_current_api_key, verify_project_tenant_access
from src.models.project import Project
from src.services.agent import BoundedAgent, WorkflowReport

router = APIRouter()


class AgentWorkflowRequest(BaseModel):
    """Payload for invoking the bounded agentic research workflow."""

    goal: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="High-level engineering or research goal",
    )


@router.post(
    "/{project_id}/agent/workflow",
    response_model=WorkflowReport,
    status_code=status.HTTP_200_OK,
    summary="Execute bounded agentic research workflow on project data",
)
async def run_agent_workflow(
    project_id: UUID,
    request: AgentWorkflowRequest,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db_session),
) -> WorkflowReport:
    """Execute the bounded FSM agentic workflow for the specified project.

    Security & Access Control:
      - Validates caller API key via X-API-Key header.
      - Verifies target project exists (404 Not Found).
      - Enforces tenant isolation (403 Forbidden on tenant mismatch).

    Workflow Execution:
      - Bounded by 4 strict phases: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE.
      - Max 5 iterations loop cap with runtime input validation and per-tool timeout isolation.
      - Produces an end-to-end execution audit trail and structured proposal.
    """
    # 1. Fetch project and verify existence
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # 2. Verify tenant ownership / access
    verify_project_tenant_access(project, api_key)

    # 3. Instantiate and run BoundedAgent
    agent = BoundedAgent(session=db, project_id=project_id)
    report = await agent.run(user_goal=request.goal)

    return report
