"""RAG API endpoints for grounded answer synthesis and citation verification."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_api_key, verify_project_tenant_access
from src.models.project import Project
from src.schemas.rag import RagQueryRequest, RagResponse
from src.services.rag import get_rag_service

router = APIRouter()


@router.post(
    "/{project_id}/rag",
    response_model=RagResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate grounded answer with citations from project documents",
)
async def generate_rag_answer(
    project_id: UUID,
    request: RagQueryRequest,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> RagResponse:
    """Perform semantic retrieval, assemble grounded context, and synthesize an answer with citations."""
    # 1. Verify project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' does not exist.",
        )
    verify_project_tenant_access(project, api_key)

    # 2. Delegate to RagService (includes retrieval, LLM synthesis, citation verification & anti-hallucination guardrails)
    rag_service = get_rag_service()
    return await rag_service.generate_grounded_answer(
        query=request.query,
        project_id=project_id,
        session=db,
        search_mode=request.search_mode,
        top_k=request.top_k,
        temperature=request.temperature,
        chunk_limit=request.chunk_limit,
    )
